// Google Ads API (REST): campanhas de pesquisa e métricas.
// Credenciais vêm dos segredos do Worker; customer_id fica na configuração.

export const LIMITE_TITULO = 30;
export const LIMITE_DESCRICAO = 90;
const IDIOMA_PT = "languageConstants/1014";

// Provimento OAB 205/2021: vedada publicidade mercantil, promessa de resultado, preço etc.
export const TERMOS_VEDADOS = [
  "gratis", "gratuito", "gratuita", "barato", "barata", "menor preco", "preco",
  "promocao", "desconto", "oferta", "garantido", "garantida", "garantia de",
  "resultado garantido", "100%", "melhor advogado", "melhores advogados",
  "o melhor", "imbativel", "ganhe", "causa ganha", "sem risco", "parcelamos",
];

export class AdsErro extends Error {}

const semAcento = (s) => s.toLowerCase().normalize("NFD").replace(/[̀-ͯ]/g, "");
const escRe = (s) => s.replace(/[.*+?^${}()|[\]\\]/g, "\\$&");

export function conformidadeOab(textos) {
  const alertas = [];
  for (const t of textos) {
    const n = semAcento(t);
    for (const termo of TERMOS_VEDADOS) {
      if (new RegExp(`(?<![\\p{L}\\d])${escRe(termo)}(?![\\p{L}\\d])`, "u").test(n))
        alertas.push(`"${t}" contém "${termo}" (vedado pelo Prov. OAB 205/2021)`);
    }
  }
  return alertas;
}

export const micros = (v) => String(Math.round(Number(v) * 100) * 10_000);

export function validarCampanha(c) {
  const erros = [];
  if (!c.nome?.trim()) erros.push("Informe o nome da campanha.");
  if (!(Number(c.orcamento_diario) >= 1)) erros.push("Orçamento diário mínimo: R$ 1,00.");
  if (!/^https?:\/\//.test(c.url_final ?? "")) erros.push("URL final deve começar com http:// ou https://.");
  if (!c.palavras_chave?.length) erros.push("Informe ao menos uma palavra-chave.");
  if (!(c.titulos?.length >= 3 && c.titulos.length <= 15)) erros.push("Anúncio responsivo exige de 3 a 15 títulos.");
  if (!(c.descricoes?.length >= 2 && c.descricoes.length <= 4)) erros.push("Anúncio responsivo exige de 2 a 4 descrições.");
  for (const t of c.titulos ?? []) if (t.length > LIMITE_TITULO) erros.push(`Título com mais de ${LIMITE_TITULO} caracteres: "${t}"`);
  for (const d of c.descricoes ?? []) if (d.length > LIMITE_DESCRICAO) erros.push(`Descrição com mais de ${LIMITE_DESCRICAO} caracteres: "${d}"`);
  if (!["EXACT", "PHRASE", "BROAD"].includes(c.correspondencia ?? "PHRASE")) erros.push("Correspondência inválida.");
  if (erros.length) throw new AdsErro(erros.join("\n"));
  return conformidadeOab([...c.titulos, ...c.descricoes]);
}

/** Monta as operações de googleAds:mutate (atômico, com IDs temporários). */
export function operacoesCampanha(cid, c, geoTargets) {
  const budget = `customers/${cid}/campaignBudgets/-1`;
  const camp = `customers/${cid}/campaigns/-2`;
  const grupo = `customers/${cid}/adGroups/-3`;
  return [
    { campaignBudgetOperation: { create: {
      resourceName: budget, name: `Orçamento - ${c.nome} - ${Date.now()}`, deliveryMethod: "STANDARD",
      amountMicros: micros(c.orcamento_diario), explicitlyShared: false } } },
    { campaignOperation: { create: {
      resourceName: camp, name: c.nome, advertisingChannelType: "SEARCH", status: "PAUSED",
      manualCpc: {}, campaignBudget: budget,
      networkSettings: { targetGoogleSearch: true, targetSearchNetwork: true,
        targetContentNetwork: false, targetPartnerSearchNetwork: false },
      containsEuPoliticalAdvertising: "DOES_NOT_CONTAIN_EU_POLITICAL_ADVERTISING" } } },
    { campaignCriterionOperation: { create: { campaign: camp, language: { languageConstant: IDIOMA_PT } } } },
    ...geoTargets.map((g) => ({ campaignCriterionOperation: { create: { campaign: camp, location: { geoTargetConstant: g } } } })),
    { adGroupOperation: { create: {
      resourceName: grupo, name: `${c.nome} - Grupo 1`, campaign: camp, type: "SEARCH_STANDARD",
      status: "ENABLED", cpcBidMicros: micros(c.cpc_maximo ?? 3) } } },
    ...c.palavras_chave.map((kw) => ({ adGroupCriterionOperation: { create: {
      adGroup: grupo, status: "ENABLED", keyword: { text: kw, matchType: c.correspondencia ?? "PHRASE" } } } })),
    { adGroupAdOperation: { create: { adGroup: grupo, status: "ENABLED", ad: {
      finalUrls: [c.url_final],
      responsiveSearchAd: { headlines: c.titulos.map((text) => ({ text })), descriptions: c.descricoes.map((text) => ({ text })) },
    } } } },
  ];
}

export class GoogleAds {
  constructor(env, cfg, fetchFn = fetch) {
    this.env = env;
    this.fetch = fetchFn;
    this.versao = env.GOOGLE_ADS_API_VERSION || "v26";
    this.cid = String(cfg.customer_id ?? "").replace(/\D/g, "");
    this.login = String(cfg.login_customer_id ?? "").replace(/\D/g, "");
  }

  get configurado() {
    const e = this.env;
    return Boolean(e.GOOGLE_ADS_DEVELOPER_TOKEN && e.GOOGLE_ADS_CLIENT_ID && e.GOOGLE_ADS_CLIENT_SECRET
      && e.GOOGLE_ADS_REFRESH_TOKEN && this.cid);
  }

  async token() {
    if (this._token) return this._token;
    const r = await this.fetch("https://oauth2.googleapis.com/token", {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams({
        grant_type: "refresh_token", refresh_token: this.env.GOOGLE_ADS_REFRESH_TOKEN,
        client_id: this.env.GOOGLE_ADS_CLIENT_ID, client_secret: this.env.GOOGLE_ADS_CLIENT_SECRET,
      }),
    });
    const j = await r.json().catch(() => ({}));
    if (!r.ok) throw new AdsErro(`Falha na autenticação Google: ${j.error_description || j.error || r.status}`);
    return (this._token = j.access_token);
  }

  async chamar(caminho, corpo) {
    if (!this.configurado) throw new AdsErro("Google Ads não configurado (segredos do Worker e ID da conta).");
    const headers = {
      Authorization: `Bearer ${await this.token()}`,
      "developer-token": this.env.GOOGLE_ADS_DEVELOPER_TOKEN,
      "Content-Type": "application/json",
    };
    if (this.login) headers["login-customer-id"] = this.login;
    const r = await this.fetch(`https://googleads.googleapis.com/${this.versao}/${caminho}`, {
      method: "POST", headers, body: JSON.stringify(corpo),
    });
    const j = await r.json().catch(() => ({}));
    if (!r.ok) {
      const det = (j.error?.details ?? []).flatMap((d) => d.errors ?? []).map((e) => e.message);
      throw new AdsErro(det.length ? det.join("\n") : j.error?.message || `Google Ads respondeu ${r.status}`);
    }
    return j;
  }

  async listarCampanhas(periodo = "LAST_30_DAYS") {
    const ok = ["TODAY", "YESTERDAY", "LAST_7_DAYS", "LAST_14_DAYS", "LAST_30_DAYS", "THIS_MONTH", "LAST_MONTH"];
    if (!ok.includes(periodo)) throw new AdsErro("Período inválido.");
    const query = `SELECT campaign.id, campaign.name, campaign.status, campaign_budget.amount_micros,
      metrics.impressions, metrics.clicks, metrics.cost_micros, metrics.conversions
      FROM campaign WHERE campaign.status != 'REMOVED' AND segments.date DURING ${periodo}`;
    const linhas = new Map();
    let pageToken;
    do {
      const j = await this.chamar(`customers/${this.cid}/googleAds:search`, { query, ...(pageToken && { pageToken }) });
      for (const r of j.results ?? []) {
        const id = String(r.campaign.id);
        const l = linhas.get(id) ?? {
          id, nome: r.campaign.name, status: r.campaign.status,
          orcamento_diario: Number(r.campaignBudget?.amountMicros ?? 0) / 1e6,
          impressoes: 0, cliques: 0, custo: 0, conversoes: 0,
        };
        l.impressoes += Number(r.metrics?.impressions ?? 0);
        l.cliques += Number(r.metrics?.clicks ?? 0);
        l.custo += Number(r.metrics?.costMicros ?? 0) / 1e6;
        l.conversoes += Number(r.metrics?.conversions ?? 0);
        linhas.set(id, l);
      }
      pageToken = j.nextPageToken;
    } while (pageToken);
    return [...linhas.values()]
      .map((l) => ({ ...l, ctr: l.impressoes ? (l.cliques / l.impressoes) * 100 : 0, cpc_medio: l.cliques ? l.custo / l.cliques : 0 }))
      .sort((a, b) => b.custo - a.custo);
  }

  async alterarStatus(campaignId, ativar) {
    if (!/^\d+$/.test(String(campaignId))) throw new AdsErro("ID de campanha inválido.");
    await this.chamar(`customers/${this.cid}/campaigns:mutate`, {
      operations: [{ update: { resourceName: `customers/${this.cid}/campaigns/${campaignId}`, status: ativar ? "ENABLED" : "PAUSED" }, updateMask: "status" }],
    });
  }

  async resolverLocais(nomes) {
    nomes = nomes.map((n) => n.trim()).filter(Boolean);
    if (!nomes.length) return ["geoTargetConstants/2076"]; // Brasil
    const j = await this.chamar("geoTargetConstants:suggest", { locale: "pt", countryCode: "BR", locationNames: { names: nomes } });
    const porTermo = new Map();
    for (const s of j.geoTargetConstantSuggestions ?? []) {
      const k = String(s.searchTerm ?? "").toLowerCase();
      if (!porTermo.has(k)) porTermo.set(k, s.geoTargetConstant.resourceName);
    }
    const faltando = nomes.filter((n) => !porTermo.has(n.toLowerCase()));
    if (faltando.length) throw new AdsErro(`Local não encontrado no Google Ads: ${faltando.join(", ")}`);
    return [...new Set(porTermo.values())];
  }

  async criarCampanha(c) {
    validarCampanha(c);
    const geos = await this.resolverLocais(c.locais ?? []);
    const j = await this.chamar(`customers/${this.cid}/googleAds:mutate`, { mutateOperations: operacoesCampanha(this.cid, c, geos) });
    const rn = j.mutateOperationResponses?.[1]?.campaignResult?.resourceName ?? "";
    return rn.split("/").pop();
  }
}
