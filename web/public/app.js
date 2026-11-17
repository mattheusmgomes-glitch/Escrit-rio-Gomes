// Interface do sistema (sem frameworks). Todo conteúdo externo é inserido via textContent.

const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const UFS = ["", "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS", "MG", "PA", "PB",
  "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO"];
const brl = (v) => Number(v || 0).toLocaleString("pt-BR", { style: "currency", currency: "BRL" });
const int = (v) => Number(v || 0).toLocaleString("pt-BR");
const dataBr = (iso) => (iso && /^\d{4}-\d{2}-\d{2}/.test(iso) ? iso.slice(0, 10).split("-").reverse().join("/") : iso || "");
const hojeIso = () => { const d = new Date(); d.setMinutes(d.getMinutes() - d.getTimezoneOffset()); return d.toISOString().slice(0, 10); };
const cnj = (n) => { const d = String(n || "").replace(/\D/g, ""); return d.length === 20 ? `${d.slice(0, 7)}-${d.slice(7, 9)}.${d.slice(9, 13)}.${d[13]}.${d.slice(14, 16)}.${d.slice(16)}` : n || ""; };
const linhas = (t) => String(t || "").split("\n").map((s) => s.trim()).filter(Boolean);

let cfgEscritorio = {};

// ------------------------------------------------------------------ utilidades

class ApiErro extends Error { constructor(status, msg) { super(msg); this.status = status; } }

async function api(caminho, { method = "GET", body } = {}) {
  const r = await fetch(caminho, {
    method, credentials: "same-origin",
    headers: { "X-Requested-With": "app", ...(body !== undefined && { "Content-Type": "application/json" }) },
    body: body !== undefined ? JSON.stringify(body) : undefined,
  });
  const j = await r.json().catch(() => ({}));
  if (r.status === 401 && caminho !== "/api/login") { mostrarLogin(); throw new ApiErro(401, j.erro || "Sessão expirada."); }
  if (!r.ok) throw new ApiErro(r.status, j.erro || `Erro ${r.status}`);
  return j;
}

let toastTimer;
function avisar(msg, erro = false) {
  const t = $("#aviso");
  t.textContent = msg;
  t.classList.toggle("erro-toast", erro);
  t.hidden = false;
  clearTimeout(toastTimer);
  toastTimer = setTimeout(() => (t.hidden = true), erro ? 7000 : 3500);
}

async function ocupado(botao, fn) {
  const txt = botao?.textContent;
  if (botao) { botao.disabled = true; botao.textContent = "Aguarde…"; }
  try { return await fn(); }
  catch (e) { if (e.status !== 401) avisar(e.message, true); }
  finally { if (botao) { botao.disabled = false; botao.textContent = txt; } }
}

function el(tag, props = {}, ...filhos) {
  const e = document.createElement(tag);
  for (const [k, v] of Object.entries(props)) {
    if (k === "class") e.className = v;
    else if (k.startsWith("on")) e.addEventListener(k.slice(2), v);
    else if (k === "dataset") Object.assign(e.dataset, v);
    else e[k] = v;
  }
  for (const f of filhos.flat()) if (f != null) e.append(f instanceof Node ? f : String(f));
  return e;
}

function baixarCsv(nome, cabecalho, linhasCsv) {
  const esc = (v) => `"${String(v ?? "").replace(/"/g, '""')}"`;
  const csv = [cabecalho, ...linhasCsv].map((l) => l.map(esc).join(";")).join("\r\n");
  const a = el("a", { href: URL.createObjectURL(new Blob(["﻿" + csv], { type: "text/csv" })), download: nome });
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

const debounce = (fn, ms = 250) => { let t; return (...a) => { clearTimeout(t); t = setTimeout(() => fn(...a), ms); }; };

function linhaVazia(tbody, colunas, texto) {
  tbody.replaceChildren(el("tr", { class: "vazio-linha" }, el("td", { colSpan: colunas }, texto)));
}

// ------------------------------------------------------------------ login e navegação

function mostrarLogin() {
  $("#tela-app").hidden = true;
  $("#tela-login").hidden = false;
  $("#form-login [name=senha]").focus();
}

$("#form-login").addEventListener("submit", async (ev) => {
  ev.preventDefault();
  const senha = ev.target.senha.value;
  $("#erro-login").textContent = "";
  try {
    await api("/api/login", { method: "POST", body: { senha } });
    ev.target.reset();
    iniciar();
  } catch (e) { $("#erro-login").textContent = e.message; }
});

$("#sair").addEventListener("click", async () => { await api("/api/logout", { method: "POST" }).catch(() => {}); mostrarLogin(); });

function trocarAba(nome) {
  for (const b of $$(".abas button")) b.setAttribute("aria-selected", String(b.dataset.aba === nome));
  for (const s of $$(".aba")) s.hidden = s.id !== `aba-${nome}`;
  try { localStorage.setItem("aba", nome); } catch {}
  ({ intimacoes: carregarIntimacoes, clientes: carregarClientes, config: carregarConfig, ads: () => carregarAds() })[nome]?.();
}
for (const b of $$(".abas button")) b.addEventListener("click", () => trocarAba(b.dataset.aba));

for (const s of $$("[data-ufs]")) s.replaceChildren(...UFS.map((u) => el("option", { value: u }, u)));
for (const v of $$(".voltar")) v.addEventListener("click", () => v.closest(".dividido").classList.remove("mostrando-detalhe"));

async function atualizarCabecalho() {
  const me = await api("/api/me");
  cfgEscritorio = me.escritorio;
  $("#nome-escritorio").textContent = me.escritorio.nome;
  $("#oab-escritorio").textContent = `${me.escritorio.advogado} · OAB/${me.escritorio.oab_uf} ${me.escritorio.oab_numero}`;
  document.title = `${me.escritorio.nome} — Sistema`;
  const b = $("#badge-nao-lidas");
  b.textContent = me.nao_lidas;
  b.hidden = !me.nao_lidas;
  const u = me.ultima_busca;
  $("#ultima-busca").textContent = u
    ? `Última busca (${u.origem}) em ${new Date(u.em.replace(" ", "T") + "Z").toLocaleString("pt-BR")}: ` +
      (u.erro ? `falhou — ${u.erro}` : `${u.encontradas} encontrada(s), ${u.novas} nova(s).`)
    : "Nenhuma busca realizada ainda.";
  return me;
}

async function iniciar() {
  let me;
  try { me = await atualizarCabecalho(); } catch (e) { if (e.status === 401) return; avisar(e.message, true); return; }
  $("#tela-login").hidden = true;
  $("#tela-app").hidden = false;
  const f = $("#form-djen");
  f.fim.value = hojeIso();
  const ini = new Date(); ini.setDate(ini.getDate() - 7);
  f.inicio.value = ini.toISOString().slice(0, 10);
  f.oab.value = cfgEscritorio.oab_numero || "";
  f.uf.value = cfgEscritorio.oab_uf || "";
  if (!$("#form-ads").url_final.value) $("#form-ads").url_final.value = cfgEscritorio.site || "";
  let aba = "intimacoes";
  try { aba = localStorage.getItem("aba") || aba; } catch {}
  trocarAba(aba);
  // O DJEN só responde a acessos do Brasil; a busca agendada pode rodar no exterior.
  // Se não há busca bem-sucedida nas últimas 3 horas, busca agora a partir do navegador.
  const ultimaOk = me.ultima_ok ? Date.parse(me.ultima_ok.replace(" ", "T") + "Z") : 0;
  if (cfgEscritorio.oab_numero && Date.now() - ultimaOk > 3 * 36e5) buscaAutomatica();
}

async function buscaAutomatica() {
  try {
    const r = await api("/api/intimacoes/buscar", { method: "POST", body: { oab: cfgEscritorio.oab_numero, uf: cfgEscritorio.oab_uf, incluir_extras: true } });
    if (r.novas) avisar(`${r.novas} nova(s) intimação(ões) no DJEN.`);
  } catch { /* o erro fica registrado em "Última busca" */ }
  carregarIntimacoes();
}

// ------------------------------------------------------------------ intimações

let intimacoes = [];
let intimAtual = null;
let clientesCache = [];

$("#form-djen").addEventListener("submit", (ev) => {
  ev.preventDefault();
  const f = ev.target;
  const dados = Object.fromEntries(new FormData(f));
  dados.incluir_extras = dados.oab === cfgEscritorio.oab_numero && !dados.parte && !dados.processo;
  ocupado(f.querySelector("button[type=submit]"), async () => {
    const r = await api("/api/intimacoes/buscar", { method: "POST", body: dados });
    avisar(`DJEN: ${r.encontradas} intimação(ões) no período, ${r.novas} nova(s).`);
    await carregarIntimacoes();
  });
});

async function carregarIntimacoes() {
  const q = new URLSearchParams({ q: $("#filtro-intim").value, nao_lidas: $("#so-nao-lidas").checked ? "1" : "0" });
  const [lista] = await Promise.all([api(`/api/intimacoes?${q}`), atualizarCabecalho()]).catch((e) => { avisar(e.message, true); return [[]]; });
  intimacoes = lista;
  const tbody = $("#tabela-intim tbody");
  if (!lista.length) linhaVazia(tbody, 6, "Nenhuma intimação. Use “Buscar” para consultar o DJEN.");
  else tbody.replaceChildren(...lista.map((i) => el("tr", {
    class: `${i.lida ? "" : "nao-lida"} ${intimAtual?.id === i.id ? "sel" : ""}`, dataset: { id: i.id },
    onclick: () => abrirIntimacao(i.id),
  }, el("td", {}, dataBr(i.data_disponibilizacao)), el("td", {}, i.tribunal), el("td", {}, cnj(i.numero_processo)),
    el("td", {}, i.tipo_comunicacao), el("td", {}, i.cliente_nome || "—"), el("td", {}, i.prazo || ""))));
  const nl = lista.filter((i) => !i.lida).length;
  $("#resumo-intim").textContent = `${lista.length} intimação(ões) · ${nl} não lida(s)`;
}

$("#filtro-intim").addEventListener("input", debounce(carregarIntimacoes));
$("#so-nao-lidas").addEventListener("change", carregarIntimacoes);

async function abrirIntimacao(id) {
  const i = intimacoes.find((x) => x.id === id);
  if (!i) return;
  intimAtual = i;
  const d = $("#detalhe-intim");
  d.closest(".dividido").classList.add("mostrando-detalhe");
  $(".vazio", d).hidden = true;
  $(".conteudo", d).hidden = false;
  const c = (n) => $(`[data-campo=${n}]`, d);
  c("processo").textContent = `${cnj(i.numero_processo)} — ${i.tribunal}`;
  c("orgao").textContent = i.orgao || "—";
  c("tipo").textContent = [i.tipo_comunicacao, i.tipo_documento, i.classe].filter(Boolean).join(" · ");
  c("data").textContent = dataBr(i.data_disponibilizacao);
  c("destinatarios").textContent = (i.destinatarios || "").replace(/\n/g, "; ") || "—";
  c("texto").textContent = i.texto || "(sem texto)";
  const link = c("link");
  link.hidden = !/^https?:\/\//.test(i.link || "");
  link.href = link.hidden ? "#" : i.link;
  c("prazo").value = i.prazo || "";
  c("observacao").value = i.observacao || "";
  if (!clientesCache.length) clientesCache = await api("/api/clientes").catch(() => []);
  c("cliente").replaceChildren(el("option", { value: "" }, "— nenhum —"),
    ...clientesCache.map((cl) => el("option", { value: cl.id, selected: cl.id === i.cliente_id }, cl.nome)));
  if (!i.lida) {
    await api(`/api/intimacoes/${i.id}`, { method: "PATCH", body: { lida: true } }).catch(() => {});
    i.lida = 1;
    await carregarIntimacoes();
  } else {
    for (const tr of $$("#tabela-intim tbody tr")) tr.classList.toggle("sel", Number(tr.dataset.id) === i.id);
  }
  $("[data-acao=lida]", d).textContent = i.lida ? "Marcar como não lida" : "Marcar como lida";
}

$("#detalhe-intim").addEventListener("click", (ev) => {
  const acao = ev.target.dataset?.acao;
  if (!acao || !intimAtual) return;
  const d = $("#detalhe-intim");
  const c = (n) => $(`[data-campo=${n}]`, d);
  const i = intimAtual;
  ocupado(ev.target, async () => {
    if (acao === "lida") {
      i.lida = i.lida ? 0 : 1;
      await api(`/api/intimacoes/${i.id}`, { method: "PATCH", body: { lida: Boolean(i.lida) } });
      ev.target.textContent = i.lida ? "Marcar como não lida" : "Marcar como lida";
      await carregarIntimacoes();
    } else if (acao === "vincular") {
      if (!c("cliente").value) throw new Error("Escolha o cliente.");
      await api(`/api/intimacoes/${i.id}/vincular`, { method: "POST", body: { cliente_id: Number(c("cliente").value) } });
      avisar("Processo vinculado — próximas intimações dele irão para este cliente.");
      await carregarIntimacoes();
    } else if (acao === "calcular") {
      const r = await api(`/api/prazo?data=${i.data_disponibilizacao}&dias=${c("dias").value}`);
      c("prazo").value = dataBr(r.vencimento);
    } else if (acao === "anotar") {
      await api(`/api/intimacoes/${i.id}`, { method: "PATCH", body: { prazo: c("prazo").value.trim(), observacao: c("observacao").value.trim() } });
      avisar("Anotações salvas.");
      await carregarIntimacoes();
    }
  });
});

$("#csv-intim").addEventListener("click", () => baixarCsv("intimacoes.csv",
  ["data", "tribunal", "orgao", "processo", "tipo", "cliente", "destinatarios", "prazo", "observacao", "link", "texto"],
  intimacoes.map((i) => [dataBr(i.data_disponibilizacao), i.tribunal, i.orgao, cnj(i.numero_processo), i.tipo_comunicacao,
    i.cliente_nome, (i.destinatarios || "").replace(/\n/g, "; "), i.prazo, i.observacao, i.link, i.texto])));

// ------------------------------------------------------------------ clientes

let clientes = [];
let cliAtual = null;
const formCli = $("#form-cli");
const CAMPOS_CLI = ["tipo", "nome", "cpf_cnpj", "rg", "data_nascimento", "estado_civil", "profissao", "email", "telefone",
  "cep", "logradouro", "numero", "complemento", "bairro", "cidade", "uf", "area", "origem", "observacoes"];

async function carregarClientes() {
  clientes = await api(`/api/clientes?q=${encodeURIComponent($("#busca-cli").value)}`).catch((e) => { avisar(e.message, true); return []; });
  if (!$("#busca-cli").value) clientesCache = clientes;
  const tbody = $("#tabela-cli tbody");
  if (!clientes.length) linhaVazia(tbody, 4, "Nenhum cliente encontrado.");
  else tbody.replaceChildren(...clientes.map((c) => el("tr", {
    class: cliAtual?.id === c.id ? "sel" : "", onclick: () => abrirCliente(c),
  }, el("td", {}, c.nome), el("td", {}, c.cpf_cnpj || ""), el("td", {}, c.telefone || ""),
    el("td", {}, c.plataforma_id ? "✔ enviado" : "—"))));
  $("#resumo-cli").textContent = `${clientes.length} cliente(s)`;
  if (!cliAtual && !formCli.nome.value) novoCliente(false);
}

function ajustarTipo() {
  const pj = formCli.tipo.value === "PJ";
  $("[data-rotulo-doc]").textContent = pj ? "CNPJ" : "CPF";
  $("[data-rotulo-nome]").textContent = pj ? "Razão social *" : "Nome completo *";
}
formCli.tipo.addEventListener("change", ajustarTipo);

function abrirCliente(c) {
  cliAtual = c;
  for (const k of CAMPOS_CLI) formCli[k].value = c[k] ?? "";
  ajustarTipo();
  $("#titulo-cli").textContent = c.nome;
  $("#excluir-cli").hidden = false;
  $("#sync-cli").textContent = c.plataforma_id
    ? `Na plataforma: ID ${c.plataforma_id} (enviado em ${dataBr(c.sincronizado_em)})`
    : "Ainda não enviado à plataforma do escritório.";
  for (const tr of $$("#tabela-cli tbody tr")) tr.classList.remove("sel");
  const idx = clientes.findIndex((x) => x.id === c.id);
  $$("#tabela-cli tbody tr")[idx]?.classList.add("sel");
  formCli.closest(".dividido").classList.add("mostrando-detalhe");
}

function novoCliente(focar = true) {
  cliAtual = null;
  formCli.reset();
  formCli.uf.value = cfgEscritorio.oab_uf || "";
  ajustarTipo();
  $("#titulo-cli").textContent = "Novo cliente";
  $("#excluir-cli").hidden = true;
  $("#sync-cli").textContent = "";
  for (const tr of $$("#tabela-cli tbody tr")) tr.classList.remove("sel");
  if (focar) { formCli.closest(".dividido").classList.add("mostrando-detalhe"); formCli.nome.focus(); }
}
$("#novo-cli").addEventListener("click", () => novoCliente());
$("#busca-cli").addEventListener("input", debounce(carregarClientes));

async function salvarCliente() {
  const dados = Object.fromEntries(CAMPOS_CLI.map((k) => [k, formCli[k].value]));
  const salvo = cliAtual
    ? await api(`/api/clientes/${cliAtual.id}`, { method: "PUT", body: dados })
    : await api("/api/clientes", { method: "POST", body: dados });
  clientesCache = [];
  await carregarClientes();
  abrirCliente(salvo);
  return salvo;
}

formCli.addEventListener("submit", (ev) => {
  ev.preventDefault();
  ocupado(ev.submitter, async () => { const c = await salvarCliente(); avisar(`Cliente “${c.nome}” salvo.`); });
});

$("#enviar-cli").addEventListener("click", (ev) => ocupado(ev.target, async () => {
  const c = await salvarCliente();
  const enviado = await api(`/api/clientes/${c.id}/enviar`, { method: "POST" });
  await carregarClientes();
  abrirCliente(enviado);
  avisar(`Enviado à plataforma (ID ${enviado.plataforma_id}).`);
}));

$("#excluir-cli").addEventListener("click", (ev) => {
  if (!cliAtual || !confirm(`Excluir “${cliAtual.nome}” do sistema?\n(O cadastro na plataforma do escritório não é apagado.)`)) return;
  ocupado(ev.target, async () => {
    await api(`/api/clientes/${cliAtual.id}`, { method: "DELETE" });
    clientesCache = [];
    novoCliente(false);
    formCli.closest(".dividido").classList.remove("mostrando-detalhe");
    await carregarClientes();
    avisar("Cliente excluído.");
  });
});

// CEP direto no ViaCEP (consulta pública)
formCli.cep.addEventListener("blur", async () => {
  const cep = formCli.cep.value.replace(/\D/g, "");
  if (cep.length !== 8) return;
  try {
    const r = await (await fetch(`https://viacep.com.br/ws/${cep}/json/`)).json();
    if (r.erro) return avisar("CEP não encontrado.", true);
    formCli.logradouro.value = r.logradouro || formCli.logradouro.value;
    formCli.bairro.value = r.bairro || formCli.bairro.value;
    formCli.cidade.value = r.localidade || formCli.cidade.value;
    formCli.uf.value = r.uf || formCli.uf.value;
    if (!formCli.complemento.value) formCli.complemento.value = r.complemento || "";
    formCli.numero.focus();
  } catch { avisar("Não foi possível consultar o CEP.", true); }
});

$("#csv-cli").addEventListener("click", () => baixarCsv("clientes.csv", [...CAMPOS_CLI, "plataforma_id", "criado_em"],
  clientes.map((c) => [...CAMPOS_CLI.map((k) => c[k]), c.plataforma_id, c.criado_em])));

// ------------------------------------------------------------------ Google Ads

// Modelos informativos, em conformidade com o Provimento OAB 205/2021.
const MODELOS = {
  "Trabalhista": {
    palavras: ["advogado trabalhista", "advogado trabalhista rio de janeiro", "rescisão trabalhista", "verbas rescisórias", "horas extras advogado", "demissão sem justa causa"],
    titulos: ["Advogado Trabalhista no RJ", "Direitos Trabalhistas", "Orientação Jurídica", "Rescisão e Verbas Rescisórias", "Gomes Advogados", "Atendimento no Rio de Janeiro", "Agende uma Consulta"],
    descricoes: ["Orientação jurídica em Direito do Trabalho: rescisão, horas extras e FGTS.", "Escritório de advocacia no Rio de Janeiro. Atendimento presencial e online."],
  },
  "Cível / Consumidor": {
    palavras: ["advogado cível", "advogado direito do consumidor", "advogado rio de janeiro", "indenização danos morais advogado", "cobrança indevida advogado"],
    titulos: ["Advogado Cível no RJ", "Direito do Consumidor", "Gomes Advogados", "Orientação Jurídica", "Atendimento Online e no RJ", "Agende uma Consulta"],
    descricoes: ["Atuação em Direito Civil e do Consumidor. Conheça seus direitos.", "Escritório de advocacia no Rio de Janeiro. Atendimento presencial e online."],
  },
  "Previdenciário": {
    palavras: ["advogado previdenciário", "aposentadoria advogado", "benefício inss negado", "revisão de aposentadoria", "auxílio doença advogado"],
    titulos: ["Advogado Previdenciário RJ", "Aposentadoria e INSS", "Gomes Advogados", "Orientação Previdenciária", "Benefício Negado pelo INSS", "Agende uma Consulta"],
    descricoes: ["Orientação em aposentadorias, revisões e benefícios do INSS.", "Escritório de advocacia no Rio de Janeiro. Atendimento presencial e online."],
  },
  "Família": {
    palavras: ["advogado de família", "advogado divórcio", "pensão alimentícia advogado", "guarda de filhos advogado", "inventário advogado"],
    titulos: ["Advogado de Família no RJ", "Divórcio e Pensão", "Gomes Advogados", "Orientação Jurídica", "Guarda e Inventário", "Agende uma Consulta"],
    descricoes: ["Atuação em divórcio, guarda, pensão alimentícia e inventário.", "Escritório de advocacia no Rio de Janeiro. Atendimento presencial e online."],
  },
};
const TERMOS_VEDADOS = ["gratis", "gratuito", "gratuita", "barato", "barata", "menor preco", "preco", "promocao", "desconto",
  "oferta", "garantido", "garantida", "garantia de", "resultado garantido", "100%", "melhor advogado", "melhores advogados",
  "o melhor", "imbativel", "ganhe", "causa ganha", "sem risco", "parcelamos"];
const semAcento = (s) => s.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");

const formAds = $("#form-ads");
$("#modelo-ads").append(...Object.keys(MODELOS).map((m) => el("option", { value: m }, m)));
$("#modelo-ads").addEventListener("change", (ev) => {
  const m = MODELOS[ev.target.value];
  if (!m) return;
  formAds.nome.value = `${ev.target.value.split(" /")[0]} - RJ - Pesquisa`;
  formAds.palavras_chave.value = m.palavras.join("\n");
  formAds.titulos.value = m.titulos.join("\n");
  formAds.descricoes.value = m.descricoes.join("\n");
  previaAds();
});

function dadosAds() {
  const f = formAds;
  return {
    nome: f.nome.value.trim(), orcamento_diario: Number(f.orcamento_diario.value), cpc_maximo: Number(f.cpc_maximo.value),
    url_final: f.url_final.value.trim(), locais: f.locais.value.split(",").map((s) => s.trim()).filter(Boolean),
    correspondencia: f.correspondencia.value, palavras_chave: linhas(f.palavras_chave.value),
    titulos: linhas(f.titulos.value), descricoes: linhas(f.descricoes.value),
  };
}

function previaAds() {
  const d = dadosAds();
  let dominio = "seusite.com.br";
  try { dominio = new URL(d.url_final).hostname; } catch {}
  $("#previa-ads").replaceChildren(
    el("small", {}, el("b", {}, "Patrocinado"), ` · ${dominio}`),
    el("div", { class: "t" }, d.titulos.slice(0, 3).join(" | ") || "Título 1 | Título 2 | Título 3"),
    el("div", {}, d.descricoes.slice(0, 2).join(" ") || "Descrição do anúncio."));
  const alertas = [
    ...d.titulos.filter((t) => t.length > 30).map((t) => `Título com ${t.length} caracteres (máx. 30): ${t}`),
    ...d.descricoes.filter((t) => t.length > 90).map((t) => `Descrição com ${t.length} caracteres (máx. 90)`),
  ];
  for (const t of [...d.titulos, ...d.descricoes]) {
    const n = semAcento(t);
    for (const termo of TERMOS_VEDADOS)
      if (new RegExp(`(?<![\\p{L}\\d])${termo.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}(?![\\p{L}\\d])`, "u").test(n))
        alertas.push(`OAB: “${t}” contém “${termo}” (Prov. 205/2021)`);
  }
  $("#alertas-ads").replaceChildren(...alertas.map((a) => el("li", {}, a)));
}
formAds.addEventListener("input", previaAds);
previaAds();

formAds.addEventListener("submit", (ev) => {
  ev.preventDefault();
  const dados = dadosAds();
  ocupado(ev.submitter, async () => {
    const { alertas } = await api("/api/ads/validar", { method: "POST", body: dados });
    if (alertas.length && !confirm(`Possíveis termos vedados pelo Provimento OAB 205/2021:\n\n${alertas.join("\n")}\n\nCriar mesmo assim?`)) return;
    const r = await api("/api/ads/campanhas", { method: "POST", body: dados });
    avisar(`Campanha criada (ID ${r.id}) e deixada PAUSADA. Revise e ative quando quiser.`);
    carregarAds();
  });
});

async function carregarAds(botao) {
  await ocupado(botao, async () => {
    let lista;
    try { lista = await api(`/api/ads/campanhas?periodo=${$("#periodo-ads").value}`); }
    catch (e) {
      $("#aviso-ads").textContent = e.message;
      linhaVazia($("#tabela-ads tbody"), 10, "Não foi possível carregar as campanhas.");
      return;
    }
    $("#aviso-ads").textContent = "";
    const tot = lista.reduce((a, c) => ({ imp: a.imp + c.impressoes, cli: a.cli + c.cliques, custo: a.custo + c.custo, conv: a.conv + c.conversoes }),
      { imp: 0, cli: 0, custo: 0, conv: 0 });
    $("#kpis-ads").replaceChildren(
      ...[["Impressões", int(tot.imp)], ["Cliques", int(tot.cli)], ["Investido", brl(tot.custo)],
        ["Custo por conversão", tot.conv ? brl(tot.custo / tot.conv) : "—"]]
        .map(([r, v]) => el("div", { class: "kpi" }, el("span", {}, r), el("strong", {}, v))));
    const tbody = $("#tabela-ads tbody");
    if (!lista.length) return linhaVazia(tbody, 10, "Nenhuma campanha no período.");
    tbody.replaceChildren(...lista.map((c) => {
      const ativa = c.status === "ENABLED";
      return el("tr", {},
        el("td", {}, c.nome), el("td", {}, el("span", { class: `pill ${ativa ? "ativa" : ""}` }, ativa ? "Ativa" : c.status === "PAUSED" ? "Pausada" : c.status)),
        el("td", { class: "num" }, brl(c.orcamento_diario)), el("td", { class: "num" }, int(c.impressoes)),
        el("td", { class: "num" }, int(c.cliques)), el("td", { class: "num" }, `${c.ctr.toFixed(2)}%`),
        el("td", { class: "num" }, brl(c.cpc_medio)), el("td", { class: "num" }, brl(c.custo)),
        el("td", { class: "num" }, c.conversoes.toFixed(1)),
        el("td", {}, el("button", { class: "sec", onclick: (ev) => {
          if (!confirm(`${ativa ? "Pausar" : "Ativar"} a campanha “${c.nome}”?`)) return;
          ocupado(ev.target, async () => { await api(`/api/ads/campanhas/${c.id}/status`, { method: "POST", body: { ativar: !ativa } }); carregarAds(); });
        } }, ativa ? "Pausar" : "Ativar")));
    }));
  });
}
$("#atualizar-ads").addEventListener("click", (ev) => carregarAds(ev.target));
$("#periodo-ads").addEventListener("change", () => carregarAds());

// ------------------------------------------------------------------ configurações

const formCfg = $("#form-config");
async function carregarConfig() {
  const cfg = await api("/api/config").catch((e) => { avisar(e.message, true); return null; });
  if (!cfg) return;
  for (const campo of $$("[data-cfg]", formCfg)) {
    const [s, k] = campo.dataset.cfg.split(".");
    const v = cfg[s]?.[k];
    if (campo.type === "checkbox") campo.checked = Boolean(v);
    else campo.value = "json" in campo.dataset ? JSON.stringify(v ?? (k === "mapeamento" ? {} : [])) : v ?? "";
  }
  const st = (id, ok, txt) => { const e = $(id); e.className = `status ${ok ? "ok" : "nao"}`; e.textContent = txt; };
  st("#st-ads", cfg.status.google_ads, cfg.status.google_ads ? "● conectado" : cfg.status.segredos_ads ? "○ falta o ID da conta" : "○ segredos não configurados");
  st("#st-plat", cfg.status.plataforma, cfg.status.plataforma ? "● ativa" : cfg.status.segredo_plataforma ? "○ inativa" : "○ segredo PLATAFORMA_TOKEN não configurado");
}

formCfg.addEventListener("submit", (ev) => {
  ev.preventDefault();
  const cfg = {};
  try {
    for (const campo of $$("[data-cfg]", formCfg)) {
      const [s, k] = campo.dataset.cfg.split(".");
      cfg[s] ??= {};
      if (campo.type === "checkbox") cfg[s][k] = campo.checked;
      else if (campo.type === "number") cfg[s][k] = Number(campo.value);
      else if ("json" in campo.dataset) {
        try { cfg[s][k] = JSON.parse(campo.value || (k === "mapeamento" ? "{}" : "[]")); }
        catch { throw new Error(`JSON inválido em “${campo.closest("label").firstChild.textContent.trim()}”.`); }
      } else cfg[s][k] = campo.value.trim();
    }
  } catch (e) { return avisar(e.message, true); }
  ocupado(ev.submitter, async () => {
    await api("/api/config", { method: "PUT", body: cfg });
    avisar("Configurações salvas.");
    await atualizarCabecalho();
    carregarConfig();
  });
});

iniciar();
