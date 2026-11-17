import { test } from "node:test";
import assert from "node:assert/strict";
import * as cl from "../src/clientes.js";
import * as dje from "../src/dje.js";
import * as ads from "../src/ads.js";
import * as plat from "../src/plataforma.js";
import * as auth from "../src/auth.js";

const ITEM = {
  id: 123456, data_disponibilizacao: "2026-11-10", siglaTribunal: "TJRJ", tipoComunicacao: "Intimação",
  nomeOrgao: "1ª Vara Cível", texto: "<p>Fica a parte <b>intimada</b> para&nbsp;manifestar-se.</p><br>Prazo: 15 dias &amp; mais.",
  numero_processo: "08012345620268190001", link: "https://x/doc", tipoDocumento: "Despacho", nomeClasse: "PROCEDIMENTO COMUM",
  destinatarios: [{ nome: "MARIA DA SILVA", polo: "A" }],
  destinatarioadvogados: [{ advogado: { nome: "MATHEUS GOMES", numero_oab: "256690", uf_oab: "RJ" } }],
};

test("CPF/CNPJ e normalização", () => {
  assert.ok(cl.cpfValido("529.982.247-25"));
  assert.ok(!cl.cpfValido("529.982.247-24"));
  assert.ok(!cl.cpfValido("11111111111"));
  assert.ok(cl.cnpjValido("11.222.333/0001-81"));
  assert.ok(!cl.cnpjValido("11.222.333/0001-80"));
  const c = cl.normalizar({ nome: " Maria   da Silva ", cpf_cnpj: "52998224725", telefone: "21999998888", cep: "20040002", email: "M@X.com" });
  assert.equal(c.nome, "Maria da Silva");
  assert.equal(c.cpf_cnpj, "529.982.247-25");
  assert.equal(c.telefone, "(21) 99999-8888");
  assert.equal(c.cep, "20040-002");
  assert.equal(c.email, "m@x.com");
  assert.equal(c.rg, null);
  assert.throws(() => cl.normalizar({ nome: "Empresa", tipo: "PJ", cpf_cnpj: "52998224725" }), cl.ValidacaoErro);
  assert.throws(() => cl.normalizar({ nome: "Ab" }), cl.ValidacaoErro);
});

test("DJEN: parse", () => {
  const i = dje.parseItem(ITEM);
  assert.equal(i.djen_id, "123456");
  assert.equal(i.texto, "Fica a parte intimada para manifestar-se.\n\nPrazo: 15 dias & mais.");
  assert.deepEqual(i.destinatarios, ["MARIA DA SILVA (A)"]);
  assert.deepEqual(i.advogados, ["MATHEUS GOMES - OAB 256690/RJ"]);
  assert.equal(dje.formatarCnj(i.numero_processo), "0801234-56.2026.8.19.0001");
  assert.equal(dje.parseItem({ ...ITEM, id: 0 }).djen_id, "0");
});

test("DJEN: paginação e parâmetros", async () => {
  const urls = [];
  const paginas = [{ count: 101, items: Array.from({ length: 100 }, (_, n) => ({ ...ITEM, id: n })) }, { count: 101, items: [{ ...ITEM, id: 100 }] }];
  const fetchFn = async (url) => { urls.push(new URL(url)); const p = Number(urls.at(-1).searchParams.get("pagina")); return new Response(JSON.stringify(paginas[p - 1])); };
  const r = await dje.buscar({ oab: "256.690", uf: "rj", inicio: "2026-11-01", fim: "2026-11-10" }, { fetchFn });
  assert.equal(r.length, 101);
  assert.equal(urls.length, 2);
  assert.equal(urls[0].searchParams.get("numeroOab"), "256690");
  assert.equal(urls[0].searchParams.get("ufOab"), "RJ");
  await assert.rejects(dje.buscar({ inicio: "2026-11-01", fim: "2026-11-10" }, { fetchFn }), dje.DjeErro);
});

test("prazo em dias úteis", () => {
  assert.equal(dje.prazoDiasUteis("2026-11-06", 15), "2026-11-30");
  assert.equal(dje.prazoDiasUteis("2026-11-06", 5, ["2026-11-10"]), "2026-11-17");
});

test("Google Ads: conformidade, validação e operações", () => {
  assert.ok(ads.conformidadeOab(["Consulta Grátis"]).length);
  assert.equal(ads.conformidadeOab(["Ofertamos orientação", "Agende uma consulta"]).length, 0);
  const c = { nome: "Trab", orcamento_diario: 30, url_final: "https://g.adv.br", palavras_chave: ["advogado trabalhista"],
    titulos: ["A", "B", "C"], descricoes: ["D1", "D2"], cpc_maximo: 2.555, correspondencia: "PHRASE" };
  assert.deepEqual(ads.validarCampanha(c), []);
  assert.throws(() => ads.validarCampanha({ ...c, titulos: ["x".repeat(31), "b", "c"] }), ads.AdsErro);
  const ops = ads.operacoesCampanha("123", c, ["geoTargetConstants/1001773"]);
  assert.equal(ops[0].campaignBudgetOperation.create.amountMicros, "30000000");
  assert.equal(ops[1].campaignOperation.create.status, "PAUSED");
  assert.equal(ops[3].campaignCriterionOperation.create.location.geoTargetConstant, "geoTargetConstants/1001773");
  assert.equal(ops[4].adGroupOperation.create.cpcBidMicros, "2560000");
  assert.equal(ops.at(-1).adGroupAdOperation.create.ad.responsiveSearchAd.headlines.length, 3);
});

test("Google Ads: chamadas REST", async () => {
  const chamadas = [];
  const fetchFn = async (url, init) => {
    chamadas.push({ url, init });
    if (url.includes("oauth2")) return new Response(JSON.stringify({ access_token: "tok" }));
    if (url.includes("suggest")) return new Response(JSON.stringify({ geoTargetConstantSuggestions: [{ searchTerm: "Rio de Janeiro", geoTargetConstant: { resourceName: "geoTargetConstants/1" } }] }));
    if (url.endsWith("googleAds:mutate")) return new Response(JSON.stringify({ mutateOperationResponses: [{}, { campaignResult: { resourceName: "customers/1234567890/campaigns/555" } }] }));
    if (url.endsWith("googleAds:search")) return new Response(JSON.stringify({ results: [
      { campaign: { id: "9", name: "C", status: "ENABLED" }, campaignBudget: { amountMicros: "30000000" }, metrics: { impressions: "100", clicks: "10", costMicros: "25000000", conversions: 2 } },
      { campaign: { id: "9", name: "C", status: "ENABLED" }, campaignBudget: { amountMicros: "30000000" }, metrics: { impressions: "100", clicks: "10", costMicros: "25000000", conversions: 0 } }] }));
    return new Response(JSON.stringify({ error: { message: "x", details: [{ errors: [{ message: "Falhou" }] }] } }), { status: 400 });
  };
  const env = { GOOGLE_ADS_DEVELOPER_TOKEN: "d", GOOGLE_ADS_CLIENT_ID: "c", GOOGLE_ADS_CLIENT_SECRET: "s", GOOGLE_ADS_REFRESH_TOKEN: "r" };
  const g = new ads.GoogleAds(env, { customer_id: "123-456-7890", login_customer_id: "111" }, fetchFn);
  const id = await g.criarCampanha({ nome: "T", orcamento_diario: 30, url_final: "https://g", palavras_chave: ["a"], titulos: ["a", "b", "c"], descricoes: ["d", "e"], locais: ["Rio de Janeiro"] });
  assert.equal(id, "555");
  const mut = chamadas.find((c) => c.url.endsWith("googleAds:mutate"));
  assert.ok(mut.url.includes("/v26/customers/1234567890/"));
  assert.equal(mut.init.headers["login-customer-id"], "111");
  assert.equal(mut.init.headers["developer-token"], "d");
  const [l] = await g.listarCampanhas();
  assert.equal(l.impressoes, 200);
  assert.equal(l.custo, 50);
  assert.equal(l.cpc_medio, 2.5);
  await assert.rejects(g.chamar("outra", {}), /Falhou/);
});

test("plataforma: payload e ID", () => {
  const c = { nome: "Maria", tipo: "PF", cpf_cnpj: "529.982.247-25", rg: "1", email: "m@x.com" };
  assert.deepEqual(plat.payload(c, { nome: "name", cpf_cnpj: "document", rg: "" }), { tipo: "PF", name: "Maria", document: "52998224725", email: "m@x.com" });
  assert.equal(plat.extrairId({ data: { id: 9 } }, "data.id"), "9");
  assert.equal(plat.extrairId({}, "id"), null);
  assert.equal(plat.valorAuth("Bearer", "t"), "Bearer t");
  assert.equal(plat.valorAuth("Bearer ", "t"), "Bearer t");
  assert.equal(plat.valorAuth("", "t"), "t");
});

test("sessão assinada", async () => {
  const env = { APP_PASSWORD: "senha-forte", SESSION_SECRET: "x".repeat(40) };
  assert.ok(await auth.senhaCorreta(env, "senha-forte"));
  assert.ok(!(await auth.senhaCorreta(env, "errada")));
  const cookie = (await auth.criarCookie(env)).split(";")[0];
  const req = (c) => new Request("https://a/", { headers: { Cookie: c } });
  assert.ok(await auth.autenticado(req(cookie), env));
  assert.ok(!(await auth.autenticado(req(cookie.replace(/.$/, (ch) => (ch === "A" ? "B" : "A"))), env)));
  const [nome, valor] = cookie.split("=");
  const forjado = `${nome}=${Number(valor.split(".")[0]) + 999}.${valor.split(".")[1]}`;
  assert.ok(!(await auth.autenticado(req(forjado), env)));
  const velho = (await auth.criarCookie(env, Date.now() - 13 * 3600e3)).split(";")[0];
  assert.ok(!(await auth.autenticado(req(velho), env)));
  await assert.rejects(auth.senhaCorreta({ APP_PASSWORD: "a", SESSION_SECRET: "curto" }, "a"));
});
