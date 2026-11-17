"""Busca de intimações no DJEN — Diário de Justiça Eletrônico Nacional (CNJ).

Usa a API pública do Comunica PJe (https://comunicaapi.pje.jus.br), que
concentra as publicações/intimações de todos os tribunais desde 2025
(Res. CNJ 455/2022). Não exige login.
"""

from __future__ import annotations

import html
import json
import re
import sqlite3
import time
from dataclasses import dataclass, field
from datetime import date, timedelta

import requests

from .clientes import so_digitos

API_PADRAO = "https://comunicaapi.pje.jus.br/api/v1/comunicacao"
ITENS_POR_PAGINA = 100


class DjeErro(RuntimeError):
    pass


def limpar_html(texto: str | None) -> str:
    if not texto:
        return ""
    t = re.sub(r"<\s*br\s*/?\s*>|</p>", "\n", texto, flags=re.I)
    t = re.sub(r"<[^>]+>", "", t)
    t = html.unescape(t).replace("\xa0", " ")
    t = re.sub(r"[ \t]+", " ", t)
    return re.sub(r"\n\s*\n+", "\n\n", t).strip()


def formatar_cnj(numero: str) -> str:
    d = so_digitos(numero)
    if len(d) == 20:
        return f"{d[:7]}-{d[7:9]}.{d[9:13]}.{d[13]}.{d[14:16]}.{d[16:]}"
    return numero


@dataclass
class Intimacao:
    djen_id: str
    data_disponibilizacao: str
    tribunal: str
    orgao: str
    tipo_comunicacao: str
    tipo_documento: str
    classe: str
    numero_processo: str
    destinatarios: list[str] = field(default_factory=list)
    advogados: list[str] = field(default_factory=list)
    texto: str = ""
    link: str = ""

    @classmethod
    def from_api(cls, item: dict) -> "Intimacao":
        destinatarios = [
            f"{d.get('nome', '').strip()}" + (f" ({d['polo']})" if d.get("polo") else "")
            for d in item.get("destinatarios") or []
        ]
        advogados = []
        for a in item.get("destinatarioadvogados") or []:
            adv = a.get("advogado") or {}
            if adv:
                advogados.append(f"{adv.get('nome', '').strip()} - OAB {adv.get('numero_oab', '')}/{adv.get('uf_oab', '')}")
        data = item.get("data_disponibilizacao") or item.get("datadisponibilizacao") or ""
        data = _normalizar_data(data)
        return cls(
            djen_id=str(item["id"] if item.get("id") is not None else item.get("hash") or ""),
            data_disponibilizacao=data,
            tribunal=item.get("siglaTribunal") or "",
            orgao=item.get("nomeOrgao") or "",
            tipo_comunicacao=item.get("tipoComunicacao") or "",
            tipo_documento=item.get("tipoDocumento") or "",
            classe=item.get("nomeClasse") or "",
            numero_processo=so_digitos(item.get("numero_processo") or item.get("numeroprocessocommascara") or ""),
            destinatarios=destinatarios,
            advogados=advogados,
            texto=limpar_html(item.get("texto")),
            link=item.get("link") or "",
        )


def _normalizar_data(valor: str) -> str:
    """Aceita 'AAAA-MM-DD...' ou 'DD/MM/AAAA' e devolve ISO 'AAAA-MM-DD'."""
    valor = (valor or "").strip()
    m = re.match(r"(\d{4})-(\d{2})-(\d{2})", valor)
    if m:
        return m.group(0)
    m = re.match(r"(\d{2})/(\d{2})/(\d{4})", valor)
    if m:
        return f"{m.group(3)}-{m.group(2)}-{m.group(1)}"
    return valor


class DjenClient:
    def __init__(self, api_url: str = API_PADRAO, timeout: float = 30, session: requests.Session | None = None):
        self.api_url = api_url
        self.timeout = timeout
        self.session = session or requests.Session()
        self.session.headers.setdefault("Accept", "application/json")
        self.session.headers.setdefault("User-Agent", "EscritorioGomes/1.0")

    def buscar(
        self,
        oab_numero: str = "",
        oab_uf: str = "",
        inicio: date | None = None,
        fim: date | None = None,
        nome_parte: str = "",
        nome_advogado: str = "",
        numero_processo: str = "",
        tribunal: str = "",
        max_paginas: int = 50,
    ) -> list[Intimacao]:
        fim = fim or date.today()
        inicio = inicio or (fim - timedelta(days=7))
        if inicio > fim:
            raise DjeErro("A data inicial não pode ser posterior à final.")
        params = {
            "dataDisponibilizacaoInicio": inicio.isoformat(),
            "dataDisponibilizacaoFim": fim.isoformat(),
            "itensPorPagina": ITENS_POR_PAGINA,
        }
        if oab_numero:
            params["numeroOab"] = so_digitos(oab_numero)
            if oab_uf:
                params["ufOab"] = oab_uf.upper()
        if nome_parte:
            params["nomeParte"] = nome_parte
        if nome_advogado:
            params["nomeAdvogado"] = nome_advogado
        if numero_processo:
            params["numeroProcesso"] = so_digitos(numero_processo)
        if tribunal:
            params["siglaTribunal"] = tribunal.upper()
        if not any(k in params for k in ("numeroOab", "nomeParte", "nomeAdvogado", "numeroProcesso")):
            raise DjeErro("Informe OAB, nome da parte, nome do advogado ou número do processo.")

        resultados: list[Intimacao] = []
        vistos: set[str] = set()
        for pagina in range(1, max_paginas + 1):
            data = self._get({**params, "pagina": pagina})
            itens = data.get("items") or []
            for it in itens:
                intim = Intimacao.from_api(it)
                if intim.djen_id and intim.djen_id not in vistos:
                    vistos.add(intim.djen_id)
                    resultados.append(intim)
            total = data.get("count")
            if len(itens) < ITENS_POR_PAGINA or (isinstance(total, int) and len(resultados) >= total):
                break
        return resultados

    def _get(self, params: dict, tentativas: int = 3) -> dict:
        ultimo_erro: Exception | None = None
        for t in range(tentativas):
            try:
                r = self.session.get(self.api_url, params=params, timeout=self.timeout)
                if r.status_code == 429:  # limite de requisições
                    time.sleep(2 * (t + 1))
                    continue
                if r.status_code >= 400:
                    raise DjeErro(f"DJEN respondeu {r.status_code}: {r.text[:200]}")
                return r.json()
            except (requests.RequestException, json.JSONDecodeError) as e:
                ultimo_erro = e
                time.sleep(1 + t)
        raise DjeErro(f"Não foi possível consultar o DJEN: {ultimo_erro or 'limite de requisições'}")


# --------------------------------------------------------------------- persistência

def salvar_intimacoes(conn: sqlite3.Connection, intimacoes: list[Intimacao]) -> int:
    """Grava as intimações novas e vincula ao cliente. Retorna quantas são novas."""
    novas = 0
    for i in intimacoes:
        cliente_id = _identificar_cliente(conn, i)
        cur = conn.execute(
            """INSERT OR IGNORE INTO intimacoes
               (djen_id, data_disponibilizacao, tribunal, orgao, tipo_comunicacao, tipo_documento,
                classe, numero_processo, destinatarios, advogados, texto, link, cliente_id)
               VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)""",
            (i.djen_id, i.data_disponibilizacao, i.tribunal, i.orgao, i.tipo_comunicacao,
             i.tipo_documento, i.classe, i.numero_processo, "\n".join(i.destinatarios),
             "\n".join(i.advogados), i.texto, i.link, cliente_id),
        )
        novas += cur.rowcount
    conn.commit()
    return novas


def _identificar_cliente(conn: sqlite3.Connection, i: Intimacao) -> int | None:
    if i.numero_processo:
        row = conn.execute("SELECT cliente_id FROM processos_clientes WHERE numero_processo = ?",
                           (i.numero_processo,)).fetchone()
        if row:
            return row[0]
    for dest in i.destinatarios:
        nome = re.sub(r"\s*\([^)]*\)$", "", dest).strip()
        if len(nome) < 5:
            continue
        row = conn.execute("SELECT id FROM clientes WHERE UPPER(nome) = UPPER(?)", (nome,)).fetchone()
        if row:
            if i.numero_processo:
                conn.execute("INSERT OR IGNORE INTO processos_clientes VALUES (?, ?)",
                             (i.numero_processo, row[0]))
            return row[0]
    return None


def listar(conn: sqlite3.Connection, somente_nao_lidas: bool = False, busca: str = "",
           inicio: str = "", fim: str = "") -> list[sqlite3.Row]:
    sql = ["SELECT i.*, c.nome AS cliente_nome FROM intimacoes i "
           "LEFT JOIN clientes c ON c.id = i.cliente_id WHERE 1=1"]
    args: list = []
    if somente_nao_lidas:
        sql.append("AND i.lida = 0")
    if inicio:
        sql.append("AND i.data_disponibilizacao >= ?")
        args.append(inicio)
    if fim:
        sql.append("AND i.data_disponibilizacao <= ?")
        args.append(fim)
    if busca.strip():
        t = f"%{busca.strip()}%"
        sql.append("AND (i.texto LIKE ? OR i.destinatarios LIKE ? OR i.numero_processo LIKE ? "
                   "OR i.tribunal LIKE ? OR c.nome LIKE ?)")
        args += [t, t, f"%{so_digitos(busca) or busca}%", t, t]
    sql.append("ORDER BY i.data_disponibilizacao DESC, i.id DESC")
    return conn.execute(" ".join(sql), args).fetchall()


def marcar_lida(conn: sqlite3.Connection, intimacao_id: int, lida: bool = True) -> None:
    conn.execute("UPDATE intimacoes SET lida = ? WHERE id = ?", (1 if lida else 0, intimacao_id))
    conn.commit()


def atualizar_anotacoes(conn: sqlite3.Connection, intimacao_id: int, prazo: str, observacao: str) -> None:
    conn.execute("UPDATE intimacoes SET prazo = ?, observacao = ? WHERE id = ?",
                 (prazo or None, observacao or None, intimacao_id))
    conn.commit()


def prazo_dias_uteis(inicio: date, dias: int, feriados: set[date] | None = None) -> date:
    """Conta prazo em dias úteis (art. 219 CPC), a partir do dia útil seguinte
    à publicação. A publicação no DJEN considera-se feita no 1º dia útil após a
    disponibilização (art. 224 §2º CPC); passe aqui a data de disponibilização."""
    feriados = feriados or set()

    def util(d: date) -> bool:
        return d.weekday() < 5 and d not in feriados

    publicacao = inicio + timedelta(days=1)
    while not util(publicacao):
        publicacao += timedelta(days=1)
    d = publicacao
    contados = 0
    while contados < dias:
        d += timedelta(days=1)
        if util(d):
            contados += 1
    return d
