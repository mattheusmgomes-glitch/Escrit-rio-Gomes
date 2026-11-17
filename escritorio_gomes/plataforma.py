"""Conector REST genérico para a plataforma de gestão do escritório.

Funciona com qualquer sistema que aceite cadastro de cliente por API REST
(JSON + token). Configure em Configurações > Plataforma:
  - URL base e endpoint de clientes
  - cabeçalho/prefixo do token
  - mapeamento de campos (campo local -> campo da plataforma)
"""

from __future__ import annotations

import requests

from .clientes import CAMPOS_EDITAVEIS, Cliente, so_digitos


class PlataformaErro(RuntimeError):
    pass


class PlataformaClient:
    def __init__(self, cfg: dict, timeout: float = 20):
        self.cfg = cfg
        self.timeout = timeout

    @property
    def configurada(self) -> bool:
        return bool(self.cfg.get("ativo") and self.cfg.get("base_url") and self.cfg.get("token"))

    def _url(self, sufixo: str = "") -> str:
        base = self.cfg["base_url"].rstrip("/")
        ep = "/" + self.cfg.get("endpoint_clientes", "/clientes").strip("/")
        return f"{base}{ep}{sufixo}"

    def _headers(self) -> dict:
        return {
            self.cfg.get("auth_header") or "Authorization":
                f"{self.cfg.get('auth_prefix', '')}{self.cfg['token']}",
            "Content-Type": "application/json",
            "Accept": "application/json",
        }

    def montar_payload(self, cliente: Cliente) -> dict:
        mapa: dict = self.cfg.get("mapeamento") or {}
        payload = {}
        for campo in CAMPOS_EDITAVEIS:
            valor = getattr(cliente, campo)
            if not valor:
                continue
            if campo in ("cpf_cnpj", "cep"):
                valor = so_digitos(valor)
            destino = mapa.get(campo, campo)
            if destino:  # mapear para "" omite o campo
                payload[destino] = valor
        return payload

    def enviar_cliente(self, cliente: Cliente) -> str:
        """Cria (POST) ou atualiza (PUT) o cliente na plataforma. Retorna o ID remoto."""
        if not self.configurada:
            raise PlataformaErro("Plataforma não configurada. Acesse Configurações > Plataforma.")
        payload = self.montar_payload(cliente)
        try:
            if cliente.plataforma_id:
                r = requests.put(self._url(f"/{cliente.plataforma_id}"), json=payload,
                                 headers=self._headers(), timeout=self.timeout)
            else:
                r = requests.post(self._url(), json=payload, headers=self._headers(),
                                  timeout=self.timeout)
        except requests.RequestException as e:
            raise PlataformaErro(f"Falha de conexão com a plataforma: {e}") from e
        if r.status_code >= 400:
            raise PlataformaErro(f"Plataforma respondeu {r.status_code}: {r.text[:300]}")
        if cliente.plataforma_id:
            return cliente.plataforma_id
        try:
            data = r.json()
        except ValueError:
            data = {}
        remoto = self._extrair_id(data)
        if not remoto:
            raise PlataformaErro("Cliente enviado, mas a resposta não trouxe um ID.")
        return str(remoto)

    def _extrair_id(self, data) -> str | None:
        caminho = (self.cfg.get("campo_id_resposta") or "id").split(".")
        atual = data
        for parte in caminho:
            if isinstance(atual, dict) and parte in atual:
                atual = atual[parte]
            else:
                return None
        return atual if isinstance(atual, (str, int)) else None
