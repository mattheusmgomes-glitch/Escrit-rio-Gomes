// Intimações do DJEN — Diário de Justiça Eletrônico Nacional (CNJ / Comunica PJe).
import { soDigitos } from "./clientes.js";

export const API_DJEN = "https://comunicaapi.pje.jus.br/api/v1/comunicacao";
const POR_PAGINA = 100;

export class DjeErro extends Error {}

export const GEOBLOQUEIO = "O DJEN só aceita consultas originadas no Brasil e esta saiu de um servidor no exterior. " +
  "Faça a busca pelo site (seu acesso parte do Brasil) — o sistema já tenta isso automaticamente ao abrir.";

const ENTIDADES = { amp: "&", lt: "<", gt: ">", quot: '"', apos: "'", nbsp: " " };

export function limparHtml(texto) {
  if (!texto) return "";
  return String(texto)
    .replace(/<\s*br\s*\/?\s*>|<\/p>/gi, "\n")
    .replace(/<[^>]+>/g, "")
    .replace(/&(#x[0-9a-f]+|#\d+|\w+);/gi, (m, e) => {
      if (e[0] === "#") {
        const cp = e[1].toLowerCase() === "x" ? parseInt(e.slice(2), 16) : parseInt(e.slice(1), 10);
        return cp === 160 ? " " : String.fromCodePoint(cp);
      }
      return ENTIDADES[e.toLowerCase()] ?? m;
    })
    .replace(/\u00a0/g, " ")
    .replace(/[ \t]+/g, " ")
    .replace(/\n\s*\n+/g, "\n\n")
    .trim();
}

export function formatarCnj(n) {
  const d = soDigitos(n);
  return d.length === 20
    ? `${d.slice(0, 7)}-${d.slice(7, 9)}.${d.slice(9, 13)}.${d[13]}.${d.slice(14, 16)}.${d.slice(16)}`
    : n || "";
}

function normalizarData(v) {
  v = String(v ?? "").trim();
  let m = v.match(/^(\d{4})-(\d{2})-(\d{2})/);
  if (m) return m[0];
  m = v.match(/^(\d{2})\/(\d{2})\/(\d{4})/);
  return m ? `${m[3]}-${m[2]}-${m[1]}` : v;
}

export function parseItem(it) {
  return {
    djen_id: String(it.id ?? it.hash ?? ""),
    data_disponibilizacao: normalizarData(it.data_disponibilizacao ?? it.datadisponibilizacao),
    tribunal: it.siglaTribunal ?? "",
    orgao: it.nomeOrgao ?? "",
    tipo_comunicacao: it.tipoComunicacao ?? "",
    tipo_documento: it.tipoDocumento ?? "",
    classe: it.nomeClasse ?? "",
    numero_processo: soDigitos(it.numero_processo ?? it.numeroprocessocommascara),
    destinatarios: (it.destinatarios ?? []).map((d) => `${(d.nome ?? "").trim()}${d.polo ? ` (${d.polo})` : ""}`),
    advogados: (it.destinatarioadvogados ?? []).filter((a) => a.advogado)
      .map(({ advogado: a }) => `${(a.nome ?? "").trim()} - OAB ${a.numero_oab ?? ""}/${a.uf_oab ?? ""}`),
    texto: limparHtml(it.texto),
    link: it.link ?? "",
  };
}

const iso = (d) => d.toISOString().slice(0, 10);

/** Consulta o DJEN com paginação. `fetchFn` permite testes. */
export async function buscar(f, { apiUrl = API_DJEN, fetchFn = fetch, maxPaginas = 50 } = {}) {
  const fim = f.fim || iso(new Date());
  const inicio = f.inicio || iso(new Date(Date.parse(fim) - 7 * 864e5));
  if (inicio > fim) throw new DjeErro("A data inicial não pode ser posterior à final.");
  const params = new URLSearchParams({
    dataDisponibilizacaoInicio: inicio, dataDisponibilizacaoFim: fim, itensPorPagina: String(POR_PAGINA),
  });
  if (f.oab) {
    params.set("numeroOab", soDigitos(f.oab));
    if (f.uf) params.set("ufOab", f.uf.toUpperCase());
  }
  if (f.parte) params.set("nomeParte", f.parte);
  if (f.processo) params.set("numeroProcesso", soDigitos(f.processo));
  if (f.tribunal) params.set("siglaTribunal", f.tribunal.toUpperCase());
  if (!f.oab && !f.parte && !f.processo) throw new DjeErro("Informe OAB, nome da parte ou número do processo.");

  const out = [];
  const vistos = new Set();
  for (let pagina = 1; pagina <= maxPaginas; pagina++) {
    params.set("pagina", String(pagina));
    const data = await getJson(`${apiUrl}?${params}`, fetchFn);
    const itens = data.items ?? [];
    for (const it of itens) {
      const i = parseItem(it);
      if (i.djen_id && !vistos.has(i.djen_id)) { vistos.add(i.djen_id); out.push(i); }
    }
    if (itens.length < POR_PAGINA || (Number.isInteger(data.count) && out.length >= data.count)) break;
  }
  return out;
}

async function getJson(url, fetchFn, tentativas = 3) {
  let erro;
  for (let t = 0; t < tentativas; t++) {
    try {
      const r = await fetchFn(url, { headers: { Accept: "application/json", "User-Agent": "EscritorioGomes/1.0" } });
      if (r.status === 429) { await esperar(2000 * (t + 1)); continue; }
      if (!r.ok) {
        const corpo = await r.text();
        if (r.status === 403 && /block access from your country/i.test(corpo))
          throw new DjeErro(GEOBLOQUEIO);
        throw new DjeErro(`DJEN respondeu ${r.status}: ${corpo.slice(0, 200)}`);
      }
      return await r.json();
    } catch (e) {
      erro = e;
      if (e instanceof DjeErro && !/ 5\d\d:/.test(e.message)) throw e;
      await esperar(1000 * (t + 1));
    }
  }
  throw new DjeErro(`Não foi possível consultar o DJEN: ${erro?.message ?? "limite de requisições"}`);
}

const esperar = (ms) => new Promise((r) => setTimeout(r, ms));

// ------------------------------------------------------------------ D1

export async function salvar(db, intimacoes) {
  let novas = 0;
  for (const i of intimacoes) {
    const clienteId = await identificarCliente(db, i);
    const r = await db.prepare(
      `INSERT OR IGNORE INTO intimacoes
       (djen_id, data_disponibilizacao, tribunal, orgao, tipo_comunicacao, tipo_documento, classe,
        numero_processo, destinatarios, advogados, texto, link, cliente_id)
       VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)`,
    ).bind(i.djen_id, i.data_disponibilizacao, i.tribunal, i.orgao, i.tipo_comunicacao, i.tipo_documento,
      i.classe, i.numero_processo, i.destinatarios.join("\n"), i.advogados.join("\n"), i.texto, i.link,
      clienteId).run();
    novas += r.meta.changes;
  }
  return novas;
}

async function identificarCliente(db, i) {
  if (i.numero_processo) {
    const r = await db.prepare("SELECT cliente_id FROM processos_clientes WHERE numero_processo = ?")
      .bind(i.numero_processo).first();
    if (r) return r.cliente_id;
  }
  for (const dest of i.destinatarios) {
    const nome = dest.replace(/\s*\([^)]*\)$/, "").trim();
    if (nome.length < 5) continue;
    const r = await db.prepare("SELECT id FROM clientes WHERE UPPER(nome) = UPPER(?)").bind(nome).first();
    if (r) {
      if (i.numero_processo)
        await db.prepare("INSERT OR IGNORE INTO processos_clientes VALUES (?, ?)").bind(i.numero_processo, r.id).run();
      return r.id;
    }
  }
  return null;
}

export async function listar(db, { naoLidas = false, busca = "", limite = 500 } = {}) {
  const sql = ["SELECT i.*, c.nome AS cliente_nome FROM intimacoes i LEFT JOIN clientes c ON c.id = i.cliente_id WHERE 1=1"];
  const args = [];
  if (naoLidas) sql.push("AND i.lida = 0");
  if (busca.trim()) {
    const t = `%${busca.trim()}%`;
    sql.push("AND (i.texto LIKE ? OR i.destinatarios LIKE ? OR i.numero_processo LIKE ? OR i.tribunal LIKE ? OR c.nome LIKE ?)");
    args.push(t, t, `%${soDigitos(busca) || busca.trim()}%`, t, t);
  }
  sql.push("ORDER BY i.data_disponibilizacao DESC, i.id DESC LIMIT ?");
  args.push(limite);
  return (await db.prepare(sql.join(" ")).bind(...args).all()).results;
}

// ------------------------------------------------------------------ prazos

/** Prazo em dias úteis (CPC 219/224): publicação = 1º dia útil após a
 *  disponibilização; contagem começa no dia útil seguinte. Datas ISO. */
export function prazoDiasUteis(disponibilizacao, dias, feriados = []) {
  const fer = new Set(feriados);
  const d = new Date(`${disponibilizacao}T12:00:00Z`);
  const util = () => d.getUTCDay() % 6 !== 0 && !fer.has(iso(d));
  d.setUTCDate(d.getUTCDate() + 1);
  while (!util()) d.setUTCDate(d.getUTCDate() + 1);
  for (let n = 0; n < dias;) {
    d.setUTCDate(d.getUTCDate() + 1);
    if (util()) n++;
  }
  return iso(d);
}
