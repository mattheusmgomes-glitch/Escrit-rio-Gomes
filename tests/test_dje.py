from datetime import date

from escritorio_gomes import clientes as cl
from escritorio_gomes import dje

ITEM = {
    "id": 123456,
    "data_disponibilizacao": "2026-11-10",
    "siglaTribunal": "TJRJ",
    "tipoComunicacao": "Intimação",
    "nomeOrgao": "1ª Vara Cível da Capital",
    "texto": "<p>Fica a parte <b>intimada</b> para&nbsp;manifestar-se.</p><br>Prazo: 15 dias.",
    "numero_processo": "08012345620268190001",
    "link": "https://tjrj.example/doc/1",
    "tipoDocumento": "Despacho",
    "nomeClasse": "PROCEDIMENTO COMUM CÍVEL",
    "destinatarios": [{"nome": "MARIA DA SILVA", "polo": "A"}],
    "destinatarioadvogados": [{"advogado": {"nome": "MATHEUS GOMES", "numero_oab": "256690", "uf_oab": "RJ"}}],
}


class FakeResp:
    def __init__(self, data, status=200):
        self._data, self.status_code, self.text = data, status, ""

    def json(self):
        return self._data


class FakeSession:
    def __init__(self, paginas):
        self.paginas, self.chamadas, self.headers = paginas, [], {}

    def get(self, url, params=None, timeout=None):
        self.chamadas.append(params)
        return FakeResp(self.paginas[params["pagina"] - 1])


def test_parse():
    i = dje.Intimacao.from_api(ITEM)
    assert i.djen_id == "123456"
    assert i.numero_processo == "08012345620268190001"
    assert dje.formatar_cnj(i.numero_processo) == "0801234-56.2026.8.19.0001"
    assert "intimada para manifestar-se." in i.texto and "<" not in i.texto
    assert i.destinatarios == ["MARIA DA SILVA (A)"]
    assert i.advogados == ["MATHEUS GOMES - OAB 256690/RJ"]


def test_buscar_pagina(monkeypatch):
    p1 = {"count": 101, "items": [dict(ITEM, id=n) for n in range(100)]}
    p2 = {"count": 101, "items": [dict(ITEM, id=100)]}
    s = FakeSession([p1, p2])
    res = dje.DjenClient(session=s).buscar("256.690", "rj", date(2026, 11, 1), date(2026, 11, 10))
    assert len(res) == 101
    assert s.chamadas[0]["numeroOab"] == "256690" and s.chamadas[0]["ufOab"] == "RJ"
    assert s.chamadas[0]["dataDisponibilizacaoInicio"] == "2026-11-01"
    assert len(s.chamadas) == 2


def test_salvar_dedup_e_vinculo(conn):
    c = cl.salvar(conn, cl.Cliente(nome="Maria da Silva"))
    i = dje.Intimacao.from_api(ITEM)
    assert dje.salvar_intimacoes(conn, [i]) == 1
    assert dje.salvar_intimacoes(conn, [i]) == 0
    row = dje.listar(conn)[0]
    assert row["cliente_id"] == c.id and row["lida"] == 0
    # processo ficou vinculado: nova intimação com outro destinatário também é associada
    outra = dje.Intimacao.from_api(dict(ITEM, id=999, destinatarios=[{"nome": "RÉU QUALQUER"}]))
    dje.salvar_intimacoes(conn, [outra])
    assert all(r["cliente_id"] == c.id for r in dje.listar(conn))
    dje.marcar_lida(conn, row["id"])
    assert len(dje.listar(conn, somente_nao_lidas=True)) == 1
    assert len(dje.listar(conn, busca="0801234")) == 2


def test_prazo():
    # disponibilizada sexta 06/11/2026 -> publicação seg 09/11 -> 15 dias úteis -> 30/11
    assert dje.prazo_dias_uteis(date(2026, 11, 6), 15) == date(2026, 11, 30)
    assert dje.prazo_dias_uteis(date(2026, 11, 6), 5, {date(2026, 11, 10)}) == date(2026, 11, 17)
