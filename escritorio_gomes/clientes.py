"""Cadastro de clientes: validação, CRUD local e consulta de CEP."""

from __future__ import annotations

import re
import sqlite3
from dataclasses import asdict, dataclass, fields

import requests

CAMPOS_EDITAVEIS = (
    "tipo", "nome", "cpf_cnpj", "rg", "data_nascimento", "estado_civil", "profissao",
    "email", "telefone", "cep", "logradouro", "numero", "complemento", "bairro",
    "cidade", "uf", "area", "origem", "observacoes",
)

AREAS = ["Trabalhista", "Cível", "Consumidor", "Família", "Previdenciário",
         "Empresarial", "Tributário", "Criminal", "Imobiliário", "Outra"]
ORIGENS = ["Google Ads", "Indicação", "Site", "Instagram", "WhatsApp", "Retorno", "Outra"]
ESTADOS_CIVIS = ["", "Solteiro(a)", "Casado(a)", "Divorciado(a)", "Viúvo(a)", "União estável"]
UFS = ["", "AC", "AL", "AP", "AM", "BA", "CE", "DF", "ES", "GO", "MA", "MT", "MS", "MG",
       "PA", "PB", "PR", "PE", "PI", "RJ", "RN", "RS", "RO", "RR", "SC", "SP", "SE", "TO"]


class ValidacaoErro(ValueError):
    pass


def so_digitos(valor: str | None) -> str:
    return re.sub(r"\D", "", valor or "")


def cpf_valido(cpf: str) -> bool:
    d = so_digitos(cpf)
    if len(d) != 11 or d == d[0] * 11:
        return False
    for n in (9, 10):
        soma = sum(int(d[i]) * (n + 1 - i) for i in range(n))
        dv = (soma * 10) % 11 % 10
        if dv != int(d[n]):
            return False
    return True


def cnpj_valido(cnpj: str) -> bool:
    d = so_digitos(cnpj)
    if len(d) != 14 or d == d[0] * 14:
        return False
    pesos1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2]
    pesos2 = [6] + pesos1
    for pesos, pos in ((pesos1, 12), (pesos2, 13)):
        soma = sum(int(d[i]) * pesos[i] for i in range(pos))
        resto = soma % 11
        dv = 0 if resto < 2 else 11 - resto
        if dv != int(d[pos]):
            return False
    return True


def formatar_documento(doc: str) -> str:
    d = so_digitos(doc)
    if len(d) == 11:
        return f"{d[:3]}.{d[3:6]}.{d[6:9]}-{d[9:]}"
    if len(d) == 14:
        return f"{d[:2]}.{d[2:5]}.{d[5:8]}/{d[8:12]}-{d[12:]}"
    return doc


def formatar_telefone(tel: str) -> str:
    d = so_digitos(tel)
    if len(d) == 11:
        return f"({d[:2]}) {d[2:7]}-{d[7:]}"
    if len(d) == 10:
        return f"({d[:2]}) {d[2:6]}-{d[6:]}"
    return tel


@dataclass
class Cliente:
    nome: str
    tipo: str = "PF"
    cpf_cnpj: str = ""
    rg: str = ""
    data_nascimento: str = ""
    estado_civil: str = ""
    profissao: str = ""
    email: str = ""
    telefone: str = ""
    cep: str = ""
    logradouro: str = ""
    numero: str = ""
    complemento: str = ""
    bairro: str = ""
    cidade: str = ""
    uf: str = ""
    area: str = ""
    origem: str = ""
    observacoes: str = ""
    id: int | None = None
    plataforma_id: str | None = None
    sincronizado_em: str | None = None
    criado_em: str | None = None
    atualizado_em: str | None = None

    @classmethod
    def from_row(cls, row: sqlite3.Row) -> "Cliente":
        nomes = {f.name for f in fields(cls)}
        return cls(**{k: (row[k] if row[k] is not None else ("" if k in CAMPOS_EDITAVEIS else None))
                      for k in row.keys() if k in nomes})

    def to_dict(self) -> dict:
        return asdict(self)

    def validar(self) -> None:
        self.nome = " ".join(self.nome.split())
        if len(self.nome) < 3:
            raise ValidacaoErro("Informe o nome completo do cliente.")
        if self.tipo not in ("PF", "PJ"):
            raise ValidacaoErro("Tipo deve ser PF ou PJ.")
        if self.cpf_cnpj:
            if self.tipo == "PF" and not cpf_valido(self.cpf_cnpj):
                raise ValidacaoErro("CPF inválido.")
            if self.tipo == "PJ" and not cnpj_valido(self.cpf_cnpj):
                raise ValidacaoErro("CNPJ inválido.")
            self.cpf_cnpj = formatar_documento(self.cpf_cnpj)
        if self.email and not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", self.email.strip()):
            raise ValidacaoErro("E-mail inválido.")
        self.email = self.email.strip().lower()
        if self.telefone:
            if len(so_digitos(self.telefone)) not in (10, 11):
                raise ValidacaoErro("Telefone deve ter DDD + número (10 ou 11 dígitos).")
            self.telefone = formatar_telefone(self.telefone)
        if self.cep:
            if len(so_digitos(self.cep)) != 8:
                raise ValidacaoErro("CEP deve ter 8 dígitos.")
            c = so_digitos(self.cep)
            self.cep = f"{c[:5]}-{c[5:]}"
        self.uf = self.uf.upper()


# --------------------------------------------------------------------- CRUD

def salvar(conn: sqlite3.Connection, cliente: Cliente) -> Cliente:
    cliente.validar()
    dados = {k: getattr(cliente, k) or None for k in CAMPOS_EDITAVEIS}
    dados["nome"] = cliente.nome
    dados["tipo"] = cliente.tipo
    try:
        if cliente.id:
            sets = ", ".join(f"{k} = :{k}" for k in dados)
            conn.execute(
                f"UPDATE clientes SET {sets}, atualizado_em = datetime('now','localtime') WHERE id = :id",
                {**dados, "id": cliente.id},
            )
        else:
            cols = ", ".join(dados)
            vals = ", ".join(f":{k}" for k in dados)
            cur = conn.execute(f"INSERT INTO clientes ({cols}) VALUES ({vals})", dados)
            cliente.id = cur.lastrowid
        conn.commit()
    except sqlite3.IntegrityError as e:
        conn.rollback()
        if "cpf_cnpj" in str(e):
            raise ValidacaoErro("Já existe um cliente com este CPF/CNPJ.") from e
        raise
    return obter(conn, cliente.id)


def obter(conn: sqlite3.Connection, cliente_id: int) -> Cliente | None:
    row = conn.execute("SELECT * FROM clientes WHERE id = ?", (cliente_id,)).fetchone()
    return Cliente.from_row(row) if row else None


def listar(conn: sqlite3.Connection, busca: str = "") -> list[Cliente]:
    if busca.strip():
        termo = f"%{busca.strip()}%"
        dig = so_digitos(busca)
        rows = conn.execute(
            """SELECT * FROM clientes
               WHERE nome LIKE :t OR email LIKE :t OR telefone LIKE :t OR cidade LIKE :t
                  OR (:d <> '' AND REPLACE(REPLACE(REPLACE(cpf_cnpj,'.',''),'-',''),'/','') LIKE :dl)
               ORDER BY nome COLLATE NOCASE""",
            {"t": termo, "d": dig, "dl": f"%{dig}%"},
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM clientes ORDER BY nome COLLATE NOCASE").fetchall()
    return [Cliente.from_row(r) for r in rows]


def excluir(conn: sqlite3.Connection, cliente_id: int) -> None:
    conn.execute("DELETE FROM clientes WHERE id = ?", (cliente_id,))
    conn.commit()


def marcar_sincronizado(conn: sqlite3.Connection, cliente_id: int, plataforma_id: str) -> None:
    conn.execute(
        "UPDATE clientes SET plataforma_id = ?, sincronizado_em = datetime('now','localtime') WHERE id = ?",
        (plataforma_id, cliente_id),
    )
    conn.commit()


def vincular_processo(conn: sqlite3.Connection, numero_processo: str, cliente_id: int) -> None:
    conn.execute(
        "INSERT INTO processos_clientes (numero_processo, cliente_id) VALUES (?, ?) "
        "ON CONFLICT(numero_processo) DO UPDATE SET cliente_id = excluded.cliente_id",
        (so_digitos(numero_processo), cliente_id),
    )
    conn.execute(
        "UPDATE intimacoes SET cliente_id = ? WHERE numero_processo = ?",
        (cliente_id, so_digitos(numero_processo)),
    )
    conn.commit()


# --------------------------------------------------------------------- CEP

def buscar_cep(cep: str, timeout: float = 10) -> dict:
    """Consulta o ViaCEP e devolve logradouro, bairro, cidade e UF."""
    c = so_digitos(cep)
    if len(c) != 8:
        raise ValidacaoErro("CEP deve ter 8 dígitos.")
    r = requests.get(f"https://viacep.com.br/ws/{c}/json/", timeout=timeout)
    r.raise_for_status()
    data = r.json()
    if data.get("erro"):
        raise ValidacaoErro("CEP não encontrado.")
    return {
        "logradouro": data.get("logradouro", ""),
        "bairro": data.get("bairro", ""),
        "cidade": data.get("localidade", ""),
        "uf": data.get("uf", ""),
        "complemento": data.get("complemento", ""),
    }
