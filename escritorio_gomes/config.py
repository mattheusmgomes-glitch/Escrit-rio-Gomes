"""Configurações do sistema, guardadas em JSON na pasta do usuário.

As credenciais (Google Ads, plataforma do escritório) ficam apenas no
computador local, em ~/.escritorio_gomes/config.json — nunca no repositório.
"""

from __future__ import annotations

import copy
import json
import os
from pathlib import Path

APP_DIR = Path(os.environ.get("ESCRITORIO_GOMES_HOME", Path.home() / ".escritorio_gomes"))
CONFIG_PATH = APP_DIR / "config.json"
DB_PATH = APP_DIR / "escritorio.db"

DEFAULTS: dict = {
    "escritorio": {
        "nome": "Gomes Advogados",
        "advogado": "Matheus Gomes",
        "oab_numero": "256690",
        "oab_uf": "RJ",
        "site": "",
    },
    "dje": {
        # API pública do Diário de Justiça Eletrônico Nacional (CNJ / Comunica PJe)
        "api_url": "https://comunicaapi.pje.jus.br/api/v1/comunicacao",
        "dias_retroativos": 7,
        "buscar_ao_abrir": True,
        # OABs adicionais monitoradas, ex.: [{"numero": "123456", "uf": "RJ"}]
        "oabs_extras": [],
    },
    "google_ads": {
        "developer_token": "",
        "client_id": "",
        "client_secret": "",
        "refresh_token": "",
        "customer_id": "",
        "login_customer_id": "",
    },
    "plataforma": {
        # Conector REST genérico para a plataforma de gestão do escritório
        "ativo": False,
        "base_url": "",
        "endpoint_clientes": "/clientes",
        "auth_header": "Authorization",
        "auth_prefix": "Bearer ",
        "token": "",
        # Mapeia campo local -> campo na plataforma. Vazio = mesmo nome.
        "mapeamento": {},
        # Campo da resposta que contém o ID do cliente criado na plataforma
        "campo_id_resposta": "id",
    },
}


def _merge(base: dict, override: dict) -> dict:
    out = copy.deepcopy(base)
    for k, v in override.items():
        if isinstance(v, dict) and isinstance(out.get(k), dict):
            out[k] = _merge(out[k], v)
        else:
            out[k] = v
    return out


def load() -> dict:
    if CONFIG_PATH.exists():
        try:
            data = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
            return _merge(DEFAULTS, data)
        except (json.JSONDecodeError, OSError):
            pass
    return copy.deepcopy(DEFAULTS)


def save(cfg: dict) -> None:
    APP_DIR.mkdir(parents=True, exist_ok=True)
    CONFIG_PATH.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        os.chmod(CONFIG_PATH, 0o600)
    except OSError:
        pass
