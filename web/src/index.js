// Worker principal: API do sistema + busca agendada de intimações.
import * as auth from "./auth.js";
import * as cl from "./clientes.js";
import * as dje from "./dje.js";
import { AdsErro, GoogleAds, validarCampanha } from "./ads.js";
import { PlataformaErro, configurada, enviarCliente } from "./plataforma.js";

export const CONFIG_PADRAO = {
  escritorio: { nome: "Gomes Advogados", advogado: "Matheus Gomes", oab_numero: "256690", oab_uf: "RJ", site: "" },
  dje: { dias_retroativos: 7, oabs_extras: [] },
  google_ads: { customer_id: "", login_customer_id: "" },
  plataforma: { ativo: false, base_url: "", endpoint_clientes: "/clientes", auth_header: "Authorization",
    auth_prefix: "Bearer ", campo_id_resposta: "id", mapeamento: {} },
};

class HttpErro extends Error {
  constructor(status, msg) { super(msg); this.status = status; }
}

const json = (data, status = 200, headers = {}) => new Response(JSON.stringify(data), {
  status, headers: { "Content-Type": "application/json; charset=utf-8", "Cache-Control": "no-store", ...headers },
});

// ------------------------------------------------------------------ configuração

export async function lerConfig(db) {
  const rows = (await db.prepare("SELECT chave, valor FROM config").all()).results;
  const cfg = structuredClone(CONFIG_PADRAO);
  for (const { chave, valor } of rows) {
    if (chave in cfg) Object.assign(cfg[chave], JSON.parse(valor));
  }
  return cfg;
}

async function salvarConfig(db, nova) {
  const stmts = [];
  for (const secao of Object.keys(CONFIG_PADRAO)) {
    if (!nova?.[secao] || typeof nova[secao] !== "object") continue;
    const limpo = {};
    for (const k of Object.keys(CONFIG_PADRAO[secao])) if (k in nova[secao]) limpo[k] = nova[secao][k];
    stmts.push(db.prepare("INSERT INTO config (chave, valor) VALUES (?, ?) ON CONFLICT(chave) DO UPDATE SET valor = excluded.valor")
      .bind(secao, JSON.stringify(limpo)));
  }
  if (stmts.length) await db.batch(stmts);
}

// ------------------------------------------------------------------ busca DJEN

const isoHoje = () => new Date(Date.now() - 3 * 36e5).toISOString().slice(0, 10); // horário de Brasília

export async function buscarIntimacoes(env, filtros, origem = "manual") {
  const cfg = await lerConfig(env.DB);
  const fim = filtros.fim || isoHoje();
  const inicio = filtros.inicio || new Date(Date.parse(fim) - cfg.dje.dias_retroativos * 864e5).toISOString().slice(0, 10);
  const base = { inicio, fim, parte: filtros.parte, processo: filtros.processo, tribunal: filtros.tribunal };
  let oabs = [];
  if (filtros.oab) oabs.push({ numero: filtros.oab, uf: filtros.uf });
  else if (origem === "agendada") oabs.push({ numero: cfg.escritorio.oab_numero, uf: cfg.escritorio.oab_uf });
  if (origem === "agendada" || filtros.incluir_extras) oabs.push(...(cfg.dje.oabs_extras ?? []));
  oabs = oabs.filter((o) => o.numero);

  const itens = [];
  try {
    if (oabs.length) for (const o of oabs) itens.push(...await dje.buscar({ ...base, oab: o.numero, uf: o.uf }));
    else itens.push(...await dje.buscar(base));
    const novas = await dje.salvar(env.DB, itens);
    await env.DB.prepare("INSERT INTO log_buscas (origem, encontradas, novas) VALUES (?, ?, ?)").bind(origem, itens.length, novas).run();
    return { encontradas: itens.length, novas };
  } catch (e) {
    await env.DB.prepare("INSERT INTO log_buscas (origem, encontradas, novas, erro) VALUES (?, 0, 0, ?)").bind(origem, e.message).run();
    throw e;
  }
}

// ------------------------------------------------------------------ rotas

async function corpo(request) {
  try { return await request.json(); } catch { throw new HttpErro(400, "JSON inválido."); }
}

const idDe = (s) => {
  const n = Number(s);
  if (!Number.isInteger(n) || n <= 0) throw new HttpErro(400, "ID inválido.");
  return n;
};

async function login(request, env) {
  const ip = request.headers.get("CF-Connecting-IP") ?? "local";
  const { n } = await env.DB.prepare(
    "SELECT COUNT(*) AS n FROM login_falhas WHERE ip = ? AND em > datetime('now', '-15 minutes')").bind(ip).first();
  if (n >= 10) throw new HttpErro(429, "Muitas tentativas. Aguarde 15 minutos.");
  const { senha } = await corpo(request);
  if (!(await auth.senhaCorreta(env, senha))) {
    await env.DB.prepare("INSERT INTO login_falhas (ip) VALUES (?)").bind(ip).run();
    throw new HttpErro(401, "Senha incorreta.");
  }
  await env.DB.prepare("DELETE FROM login_falhas WHERE ip = ? OR em < datetime('now', '-1 day')").bind(ip).run();
  return json({ ok: true }, 200, { "Set-Cookie": await auth.criarCookie(env) });
}

async function api(request, env, url) {
  const { pathname: p, searchParams: q } = url;
  const m = request.method;
  const db = env.DB;

  if (p === "/api/login" && m === "POST") return login(request, env);
  if (p === "/api/logout" && m === "POST") return json({ ok: true }, 200, { "Set-Cookie": auth.cookieSaida() });
  if (!(await auth.autenticado(request, env))) throw new HttpErro(401, "Faça login.");
  // Proteção CSRF extra (além do SameSite=Strict): escrita só via fetch do próprio app
  if (m !== "GET" && request.headers.get("X-Requested-With") !== "app") throw new HttpErro(403, "Requisição recusada.");

  let r;
  // ---- sessão / configuração
  if (p === "/api/me" && m === "GET") {
    const cfg = await lerConfig(db);
    const naoLidas = (await db.prepare("SELECT COUNT(*) AS n FROM intimacoes WHERE lida = 0").first()).n;
    const ultima = await db.prepare("SELECT * FROM log_buscas ORDER BY id DESC LIMIT 1").first();
    return json({ escritorio: cfg.escritorio, nao_lidas: naoLidas, ultima_busca: ultima });
  }
  if (p === "/api/config" && m === "GET") {
    const cfg = await lerConfig(db);
    const ads = new GoogleAds(env, cfg.google_ads);
    return json({ ...cfg, status: {
      google_ads: ads.configurado, plataforma: configurada(cfg.plataforma, env),
      segredos_ads: Boolean(env.GOOGLE_ADS_DEVELOPER_TOKEN && env.GOOGLE_ADS_REFRESH_TOKEN),
      segredo_plataforma: Boolean(env.PLATAFORMA_TOKEN) } });
  }
  if (p === "/api/config" && m === "PUT") { await salvarConfig(db, await corpo(request)); return json({ ok: true }); }

  // ---- clientes
  if (p === "/api/clientes" && m === "GET") return json(await cl.listar(db, q.get("q") ?? ""));
  if (p === "/api/clientes" && m === "POST") return json(await cl.salvar(db, await corpo(request)), 201);
  if ((r = p.match(/^\/api\/clientes\/([^/]+)$/))) {
    const id = idDe(r[1]);
    if (m === "GET") return json((await cl.obter(db, id)) ?? (() => { throw new HttpErro(404, "Cliente não encontrado."); })());
    if (m === "PUT") {
      const c = await cl.salvar(db, await corpo(request), id);
      if (!c) throw new HttpErro(404, "Cliente não encontrado.");
      return json(c);
    }
    if (m === "DELETE") { await cl.excluir(db, id); return json({ ok: true }); }
  }
  if ((r = p.match(/^\/api\/clientes\/([^/]+)\/enviar$/)) && m === "POST") {
    const c = await cl.obter(db, idDe(r[1]));
    if (!c) throw new HttpErro(404, "Cliente não encontrado.");
    const cfg = await lerConfig(db);
    const remoto = await enviarCliente(c, cfg.plataforma, env);
    await db.prepare("UPDATE clientes SET plataforma_id = ?, sincronizado_em = datetime('now') WHERE id = ?").bind(remoto, c.id).run();
    return json(await cl.obter(db, c.id));
  }

  // ---- intimações
  if (p === "/api/intimacoes" && m === "GET")
    return json(await dje.listar(db, { naoLidas: q.get("nao_lidas") === "1", busca: q.get("q") ?? "" }));
  if (p === "/api/intimacoes/buscar" && m === "POST") return json(await buscarIntimacoes(env, await corpo(request)));
  if ((r = p.match(/^\/api\/intimacoes\/([^/]+)$/)) && m === "PATCH") {
    const id = idDe(r[1]);
    const b = await corpo(request);
    const sets = [], args = [];
    if ("lida" in b) { sets.push("lida = ?"); args.push(b.lida ? 1 : 0); }
    if ("prazo" in b) { sets.push("prazo = ?"); args.push(b.prazo || null); }
    if ("observacao" in b) { sets.push("observacao = ?"); args.push(b.observacao || null); }
    if (sets.length) await db.prepare(`UPDATE intimacoes SET ${sets.join(", ")} WHERE id = ?`).bind(...args, id).run();
    return json({ ok: true });
  }
  if ((r = p.match(/^\/api\/intimacoes\/([^/]+)\/vincular$/)) && m === "POST") {
    const i = await db.prepare("SELECT numero_processo FROM intimacoes WHERE id = ?").bind(idDe(r[1])).first();
    const { cliente_id } = await corpo(request);
    if (!i?.numero_processo) throw new HttpErro(400, "Intimação sem número de processo.");
    await cl.vincularProcesso(db, i.numero_processo, idDe(cliente_id));
    return json({ ok: true });
  }
  if (p === "/api/prazo" && m === "GET") {
    const data = q.get("data") ?? "";
    if (!/^\d{4}-\d{2}-\d{2}$/.test(data)) throw new HttpErro(400, "Data inválida.");
    return json({ vencimento: dje.prazoDiasUteis(data, Math.min(Math.max(Number(q.get("dias")) || 15, 1), 365)) });
  }

  // ---- Google Ads
  if (p.startsWith("/api/ads/")) {
    const ads = new GoogleAds(env, (await lerConfig(db)).google_ads);
    if (p === "/api/ads/campanhas" && m === "GET") return json(await ads.listarCampanhas(q.get("periodo") ?? "LAST_30_DAYS"));
    if (p === "/api/ads/validar" && m === "POST") return json({ alertas: validarCampanha(await corpo(request)) });
    if (p === "/api/ads/campanhas" && m === "POST") {
      const c = await corpo(request);
      const id = await ads.criarCampanha(c);
      await db.prepare("INSERT INTO campanhas (google_id, nome, orcamento_diario, palavras_chave, url_final) VALUES (?,?,?,?,?)")
        .bind(id, c.nome, Number(c.orcamento_diario), c.palavras_chave.join("\n"), c.url_final).run();
      return json({ id }, 201);
    }
    if ((r = p.match(/^\/api\/ads\/campanhas\/(\d+)\/status$/)) && m === "POST") {
      await ads.alterarStatus(r[1], Boolean((await corpo(request)).ativar));
      return json({ ok: true });
    }
  }
  throw new HttpErro(404, "Rota não encontrada.");
}

export default {
  async fetch(request, env) {
    const url = new URL(request.url);
    if (!url.pathname.startsWith("/api/")) return env.ASSETS ? env.ASSETS.fetch(request) : new Response("Not found", { status: 404 });
    try {
      return await api(request, env, url);
    } catch (e) {
      if (e instanceof HttpErro) return json({ erro: e.message }, e.status);
      if (e instanceof cl.ValidacaoErro || e instanceof AdsErro) return json({ erro: e.message }, 422);
      if (e instanceof dje.DjeErro || e instanceof PlataformaErro) return json({ erro: e.message }, 502);
      console.error(e);
      return json({ erro: "Erro interno. Verifique os logs do Worker." }, 500);
    }
  },

  async scheduled(_evento, env, ctx) {
    ctx.waitUntil(buscarIntimacoes(env, {}, "agendada").catch((e) => console.error("DJEN agendado:", e.message)));
  },
};
