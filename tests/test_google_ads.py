from unittest.mock import MagicMock

import pytest

from escritorio_gomes import google_ads as ga


def nova(**kw):
    base = dict(nome="Trabalhista RJ", orcamento_diario=30, url_final="https://gomes.adv.br",
                palavras_chave=["advogado trabalhista"], titulos=["Advogado Trabalhista", "Gomes Advogados", "Agende"],
                descricoes=["Orientação jurídica trabalhista.", "Atendimento no Rio de Janeiro."])
    base.update(kw)
    return ga.NovaCampanha(**base)


def test_conformidade_oab():
    assert ga.verificar_conformidade_oab(["Consulta Grátis", "Resultado garantido"])
    assert not ga.verificar_conformidade_oab(["Orientação jurídica", "Agende uma consulta"])
    assert not ga.verificar_conformidade_oab(["Ofertamos"])  # só palavra inteira


def test_validacao():
    assert nova().validar() == []
    with pytest.raises(ga.GoogleAdsErro):
        nova(titulos=["a", "b"]).validar()
    with pytest.raises(ga.GoogleAdsErro):
        nova(titulos=["x" * 31, "b", "c"]).validar()
    assert ga._micros(30) == 30_000_000 and ga._micros(2.555) % 10_000 == 0


def test_criar_campanha_monta_operacoes():
    pytest.importorskip("google.ads.googleads")
    from google.ads.googleads.client import GoogleAdsClient

    real = GoogleAdsClient(credentials=None, developer_token="x", use_proto_plus=True)
    servicos = {}

    def get_service(nome):
        if nome not in servicos:
            m = MagicMock(name=nome)
            res = MagicMock()
            res.results = [MagicMock(resource_name=f"customers/1/{nome}/99")]
            for metodo in ("mutate_campaign_budgets", "mutate_campaigns", "mutate_campaign_criteria",
                           "mutate_ad_groups", "mutate_ad_group_criteria", "mutate_ad_group_ads"):
                getattr(m, metodo).return_value = res
            sug = MagicMock(search_term="Rio de Janeiro")
            sug.geo_target_constant.resource_name = "geoTargetConstants/1001773"
            m.suggest_geo_target_constants.return_value.geo_target_constant_suggestions = [sug]
            servicos[nome] = m
        return servicos[nome]

    real.get_service = get_service
    svc = ga.GoogleAdsService({"customer_id": "123-456-7890"})
    svc._client = real
    assert svc.criar_campanha(nova()) == "99"

    camp = servicos["CampaignService"].mutate_campaigns.call_args.kwargs["operations"][0].create
    assert camp.status == real.enums.CampaignStatusEnum.PAUSED
    assert servicos["CampaignService"].mutate_campaigns.call_args.kwargs["customer_id"] == "1234567890"
    crits = servicos["CampaignCriterionService"].mutate_campaign_criteria.call_args.kwargs["operations"]
    assert crits[0].create.language.language_constant == ga.IDIOMA_PORTUGUES
    assert crits[1].create.location.geo_target_constant == "geoTargetConstants/1001773"
    ad = servicos["AdGroupAdService"].mutate_ad_group_ads.call_args.kwargs["operations"][0].create.ad
    assert [h.text for h in ad.responsive_search_ad.headlines][0] == "Advogado Trabalhista"
