"""Integração com a API do Google Ads: criar campanhas de pesquisa e ver métricas.

Requer (Configurações > Google Ads):
  developer_token, client_id, client_secret, refresh_token, customer_id
  e, se a conta for gerenciada por uma MCC, login_customer_id.

Campanhas são sempre criadas PAUSADAS, para revisão antes de gastar.
"""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass, field

LIMITE_TITULO = 30
LIMITE_DESCRICAO = 90
IDIOMA_PORTUGUES = "languageConstants/1014"

# Provimento OAB 205/2021: publicidade da advocacia deve ser informativa,
# sem mercantilização, captação, promessa de resultado ou preço.
TERMOS_VEDADOS_OAB = [
    "gratis", "gratuito", "gratuita", "barato", "barata", "menor preco", "preco",
    "promocao", "desconto", "oferta", "garantido", "garantida", "garantia de",
    "resultado garantido", "100%", "melhor advogado", "melhores advogados",
    "o melhor", "imbativel", "ganhe", "causa ganha", "sem risco", "parcelamos",
]


class GoogleAdsErro(RuntimeError):
    pass


def _sem_acento(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", s.lower()) if unicodedata.category(c) != "Mn")


def verificar_conformidade_oab(textos: list[str]) -> list[str]:
    """Retorna alertas para termos que podem violar o Provimento 205/2021 da OAB."""
    alertas = []
    for t in textos:
        norm = _sem_acento(t)
        for termo in TERMOS_VEDADOS_OAB:
            if re.search(rf"(?<!\w){re.escape(termo)}(?!\w)", norm):
                alertas.append(f'"{t}" contém "{termo}" (vedado pelo Prov. OAB 205/2021)')
    return alertas


@dataclass
class NovaCampanha:
    nome: str
    orcamento_diario: float
    url_final: str
    palavras_chave: list[str]
    titulos: list[str]
    descricoes: list[str]
    locais: list[str] = field(default_factory=lambda: ["Rio de Janeiro"])
    cpc_maximo: float = 3.0
    correspondencia: str = "PHRASE"  # EXACT, PHRASE ou BROAD

    def validar(self) -> list[str]:
        """Levanta erro em problemas bloqueantes; retorna alertas de conformidade."""
        erros = []
        if not self.nome.strip():
            erros.append("Informe o nome da campanha.")
        if self.orcamento_diario < 1:
            erros.append("Orçamento diário mínimo: R$ 1,00.")
        if not re.match(r"https?://", self.url_final or ""):
            erros.append("URL final deve começar com http:// ou https://.")
        if not self.palavras_chave:
            erros.append("Informe ao menos uma palavra-chave.")
        if not 3 <= len(self.titulos) <= 15:
            erros.append("Anúncio responsivo exige de 3 a 15 títulos.")
        if not 2 <= len(self.descricoes) <= 4:
            erros.append("Anúncio responsivo exige de 2 a 4 descrições.")
        erros += [f'Título com mais de {LIMITE_TITULO} caracteres: "{t}"' for t in self.titulos if len(t) > LIMITE_TITULO]
        erros += [f'Descrição com mais de {LIMITE_DESCRICAO} caracteres: "{d}"' for d in self.descricoes if len(d) > LIMITE_DESCRICAO]
        if self.correspondencia not in ("EXACT", "PHRASE", "BROAD"):
            erros.append("Correspondência inválida.")
        if erros:
            raise GoogleAdsErro("\n".join(erros))
        return verificar_conformidade_oab(self.titulos + self.descricoes)


def _micros(valor: float) -> int:
    # Google Ads exige múltiplos de 10.000 micros (R$ 0,01)
    return int(round(valor * 100)) * 10_000


class GoogleAdsService:
    def __init__(self, cfg: dict):
        self.cfg = cfg
        self.customer_id = re.sub(r"\D", "", cfg.get("customer_id", ""))
        self._client = None

    @property
    def configurado(self) -> bool:
        return all(self.cfg.get(k) for k in
                   ("developer_token", "client_id", "client_secret", "refresh_token", "customer_id"))

    @property
    def client(self):
        if self._client is None:
            if not self.configurado:
                raise GoogleAdsErro("Google Ads não configurado. Acesse Configurações > Google Ads.")
            try:
                from google.ads.googleads.client import GoogleAdsClient
            except ImportError as e:
                raise GoogleAdsErro("Biblioteca 'google-ads' não instalada (pip install google-ads).") from e
            dados = {
                "developer_token": self.cfg["developer_token"],
                "client_id": self.cfg["client_id"],
                "client_secret": self.cfg["client_secret"],
                "refresh_token": self.cfg["refresh_token"],
                "use_proto_plus": True,
            }
            login = re.sub(r"\D", "", self.cfg.get("login_customer_id", ""))
            if login:
                dados["login_customer_id"] = login
            self._client = GoogleAdsClient.load_from_dict(dados)
        return self._client

    # ------------------------------------------------------------ leitura

    def listar_campanhas(self, periodo: str = "LAST_30_DAYS") -> list[dict]:
        periodos = {"TODAY", "YESTERDAY", "LAST_7_DAYS", "LAST_14_DAYS", "LAST_30_DAYS", "THIS_MONTH", "LAST_MONTH"}
        if periodo not in periodos:
            raise GoogleAdsErro("Período inválido.")
        query = f"""
            SELECT campaign.id, campaign.name, campaign.status,
                   campaign_budget.amount_micros,
                   metrics.impressions, metrics.clicks, metrics.ctr,
                   metrics.average_cpc, metrics.cost_micros, metrics.conversions
            FROM campaign
            WHERE campaign.status != 'REMOVED' AND segments.date DURING {periodo}
            ORDER BY metrics.cost_micros DESC"""
        linhas = {}
        try:
            svc = self.client.get_service("GoogleAdsService")
            for row in svc.search(customer_id=self.customer_id, query=query):
                cid = row.campaign.id
                atual = linhas.setdefault(cid, {
                    "id": str(cid), "nome": row.campaign.name, "status": row.campaign.status.name,
                    "orcamento_diario": row.campaign_budget.amount_micros / 1e6,
                    "impressoes": 0, "cliques": 0, "custo": 0.0, "conversoes": 0.0,
                })
                atual["impressoes"] += row.metrics.impressions
                atual["cliques"] += row.metrics.clicks
                atual["custo"] += row.metrics.cost_micros / 1e6
                atual["conversoes"] += row.metrics.conversions
        except Exception as e:  # GoogleAdsException e erros de rede
            raise GoogleAdsErro(self._mensagem(e)) from e
        for linha in linhas.values():
            linha["ctr"] = (linha["cliques"] / linha["impressoes"] * 100) if linha["impressoes"] else 0.0
            linha["cpc_medio"] = (linha["custo"] / linha["cliques"]) if linha["cliques"] else 0.0
        return list(linhas.values())

    # ------------------------------------------------------------ escrita

    def alterar_status(self, campaign_id: str, ativar: bool) -> None:
        c = self.client
        try:
            from google.api_core import protobuf_helpers
            op = c.get_type("CampaignOperation")
            camp = op.update
            camp.resource_name = c.get_service("CampaignService").campaign_path(self.customer_id, campaign_id)
            camp.status = c.enums.CampaignStatusEnum.ENABLED if ativar else c.enums.CampaignStatusEnum.PAUSED
            c.copy_from(op.update_mask, protobuf_helpers.field_mask(None, camp._pb))
            c.get_service("CampaignService").mutate_campaigns(customer_id=self.customer_id, operations=[op])
        except GoogleAdsErro:
            raise
        except Exception as e:
            raise GoogleAdsErro(self._mensagem(e)) from e

    def criar_campanha(self, nova: NovaCampanha) -> str:
        """Cria orçamento, campanha de pesquisa (pausada), segmentação, grupo,
        palavras-chave e anúncio responsivo. Retorna o ID da campanha."""
        nova.validar()
        c = self.client
        cid = self.customer_id
        try:
            # 1. Orçamento
            op = c.get_type("CampaignBudgetOperation")
            b = op.create
            b.name = f"Orçamento - {nova.nome}"
            b.delivery_method = c.enums.BudgetDeliveryMethodEnum.STANDARD
            b.amount_micros = _micros(nova.orcamento_diario)
            b.explicitly_shared = False
            budget_rn = c.get_service("CampaignBudgetService").mutate_campaign_budgets(
                customer_id=cid, operations=[op]).results[0].resource_name

            # 2. Campanha de pesquisa, pausada
            op = c.get_type("CampaignOperation")
            camp = op.create
            camp.name = nova.nome
            camp.advertising_channel_type = c.enums.AdvertisingChannelTypeEnum.SEARCH
            camp.status = c.enums.CampaignStatusEnum.PAUSED
            camp.manual_cpc = c.get_type("ManualCpc")
            camp.campaign_budget = budget_rn
            camp.network_settings.target_google_search = True
            camp.network_settings.target_search_network = True
            camp.network_settings.target_content_network = False
            camp.network_settings.target_partner_search_network = False
            if hasattr(c.enums, "EuPoliticalAdvertisingStatusEnum"):
                camp.contains_eu_political_advertising = (
                    c.enums.EuPoliticalAdvertisingStatusEnum.DOES_NOT_CONTAIN_EU_POLITICAL_ADVERTISING)
            campaign_rn = c.get_service("CampaignService").mutate_campaigns(
                customer_id=cid, operations=[op]).results[0].resource_name

            # 3. Idioma (português) e locais
            ops = []
            op = c.get_type("CampaignCriterionOperation")
            op.create.campaign = campaign_rn
            op.create.language.language_constant = IDIOMA_PORTUGUES
            ops.append(op)
            for geo in self._resolver_locais(nova.locais):
                op = c.get_type("CampaignCriterionOperation")
                op.create.campaign = campaign_rn
                op.create.location.geo_target_constant = geo
                ops.append(op)
            c.get_service("CampaignCriterionService").mutate_campaign_criteria(customer_id=cid, operations=ops)

            # 4. Grupo de anúncios
            op = c.get_type("AdGroupOperation")
            g = op.create
            g.name = f"{nova.nome} - Grupo 1"
            g.campaign = campaign_rn
            g.type_ = c.enums.AdGroupTypeEnum.SEARCH_STANDARD
            g.status = c.enums.AdGroupStatusEnum.ENABLED
            g.cpc_bid_micros = _micros(nova.cpc_maximo)
            ad_group_rn = c.get_service("AdGroupService").mutate_ad_groups(
                customer_id=cid, operations=[op]).results[0].resource_name

            # 5. Palavras-chave
            match = getattr(c.enums.KeywordMatchTypeEnum, nova.correspondencia)
            ops = []
            for kw in nova.palavras_chave:
                op = c.get_type("AdGroupCriterionOperation")
                crit = op.create
                crit.ad_group = ad_group_rn
                crit.status = c.enums.AdGroupCriterionStatusEnum.ENABLED
                crit.keyword.text = kw
                crit.keyword.match_type = match
                ops.append(op)
            c.get_service("AdGroupCriterionService").mutate_ad_group_criteria(customer_id=cid, operations=ops)

            # 6. Anúncio responsivo de pesquisa
            op = c.get_type("AdGroupAdOperation")
            aga = op.create
            aga.ad_group = ad_group_rn
            aga.status = c.enums.AdGroupAdStatusEnum.ENABLED
            aga.ad.final_urls.append(nova.url_final)
            for t in nova.titulos:
                asset = c.get_type("AdTextAsset")
                asset.text = t
                aga.ad.responsive_search_ad.headlines.append(asset)
            for d in nova.descricoes:
                asset = c.get_type("AdTextAsset")
                asset.text = d
                aga.ad.responsive_search_ad.descriptions.append(asset)
            c.get_service("AdGroupAdService").mutate_ad_group_ads(customer_id=cid, operations=[op])
        except GoogleAdsErro:
            raise
        except Exception as e:
            raise GoogleAdsErro(self._mensagem(e)) from e
        return campaign_rn.split("/")[-1]

    def _resolver_locais(self, nomes: list[str]) -> list[str]:
        nomes = [n.strip() for n in nomes if n.strip()]
        if not nomes:
            return ["geoTargetConstants/2076"]  # Brasil
        svc = self.client.get_service("GeoTargetConstantService")
        req = self.client.get_type("SuggestGeoTargetConstantsRequest")
        req.locale = "pt"
        req.country_code = "BR"
        req.location_names.names.extend(nomes)
        resp = svc.suggest_geo_target_constants(request=req)
        # A API devolve várias sugestões por nome, já ordenadas por relevância:
        # usa a primeira de cada termo pesquisado.
        por_termo: dict[str, str] = {}
        for s in resp.geo_target_constant_suggestions:
            por_termo.setdefault(s.search_term.lower(), s.geo_target_constant.resource_name)
        faltando = [n for n in nomes if n.lower() not in por_termo]
        if faltando:
            raise GoogleAdsErro(f"Local não encontrado no Google Ads: {', '.join(faltando)}")
        return list(dict.fromkeys(por_termo.values()))

    @staticmethod
    def _mensagem(e: Exception) -> str:
        falha = getattr(e, "failure", None)
        if falha is not None:
            try:
                return "\n".join(err.message for err in falha.errors)
            except Exception:
                pass
        return str(e)
