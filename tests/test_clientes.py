import pytest

from escritorio_gomes import clientes as cl
from escritorio_gomes.plataforma import PlataformaClient


def test_cpf_cnpj():
    assert cl.cpf_valido("529.982.247-25")
    assert not cl.cpf_valido("529.982.247-24")
    assert not cl.cpf_valido("111.111.111-11")
    assert cl.cnpj_valido("11.222.333/0001-81")
    assert not cl.cnpj_valido("11.222.333/0001-80")


def test_salvar_formata_e_busca(conn):
    c = cl.salvar(conn, cl.Cliente(nome="  Maria   da Silva ", cpf_cnpj="52998224725",
                                   telefone="21999998888", cep="20040002", email="Maria@Ex.com"))
    assert c.id and c.nome == "Maria da Silva"
    assert c.cpf_cnpj == "529.982.247-25"
    assert c.telefone == "(21) 99999-8888"
    assert c.cep == "20040-002"
    assert c.email == "maria@ex.com"
    assert [x.id for x in cl.listar(conn, "52998224725")] == [c.id]
    assert [x.id for x in cl.listar(conn, "maria")] == [c.id]
    c.profissao = "Professora"
    assert cl.salvar(conn, c).profissao == "Professora"


def test_duplicado_e_invalidos(conn):
    cl.salvar(conn, cl.Cliente(nome="João Souza", cpf_cnpj="52998224725"))
    with pytest.raises(cl.ValidacaoErro, match="Já existe"):
        cl.salvar(conn, cl.Cliente(nome="Outro Nome", cpf_cnpj="529.982.247-25"))
    with pytest.raises(cl.ValidacaoErro):
        cl.salvar(conn, cl.Cliente(nome="Empresa X", tipo="PJ", cpf_cnpj="52998224725"))
    with pytest.raises(cl.ValidacaoErro):
        cl.salvar(conn, cl.Cliente(nome="Ab"))


def test_payload_plataforma():
    p = PlataformaClient({"ativo": True, "base_url": "https://x", "token": "t",
                          "mapeamento": {"nome": "name", "cpf_cnpj": "document", "rg": ""}})
    c = cl.Cliente(nome="Maria", cpf_cnpj="529.982.247-25", rg="123", email="m@x.com")
    assert p.montar_payload(c) == {"name": "Maria", "tipo": "PF", "document": "52998224725", "email": "m@x.com"}
    assert p._extrair_id({"data": {"id": 9}}) is None
    p.cfg["campo_id_resposta"] = "data.id"
    assert p._extrair_id({"data": {"id": 9}}) == 9
