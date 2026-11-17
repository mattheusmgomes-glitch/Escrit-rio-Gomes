"""Banco de dados local (SQLite)."""

from __future__ import annotations

import sqlite3
from pathlib import Path

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS clientes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    tipo            TEXT NOT NULL DEFAULT 'PF',
    nome            TEXT NOT NULL,
    cpf_cnpj        TEXT UNIQUE,
    rg              TEXT,
    data_nascimento TEXT,
    estado_civil    TEXT,
    profissao       TEXT,
    email           TEXT,
    telefone        TEXT,
    cep             TEXT,
    logradouro      TEXT,
    numero          TEXT,
    complemento     TEXT,
    bairro          TEXT,
    cidade          TEXT,
    uf              TEXT,
    area            TEXT,
    origem          TEXT,
    observacoes     TEXT,
    plataforma_id   TEXT,
    sincronizado_em TEXT,
    criado_em       TEXT NOT NULL DEFAULT (datetime('now','localtime')),
    atualizado_em   TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);

CREATE TABLE IF NOT EXISTS intimacoes (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    djen_id             TEXT UNIQUE,
    data_disponibilizacao TEXT,
    tribunal            TEXT,
    orgao               TEXT,
    tipo_comunicacao    TEXT,
    tipo_documento      TEXT,
    classe              TEXT,
    numero_processo     TEXT,
    destinatarios       TEXT,
    advogados           TEXT,
    texto               TEXT,
    link                TEXT,
    cliente_id          INTEGER REFERENCES clientes(id) ON DELETE SET NULL,
    lida                INTEGER NOT NULL DEFAULT 0,
    prazo               TEXT,
    observacao          TEXT,
    capturada_em        TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
CREATE INDEX IF NOT EXISTS idx_intim_data ON intimacoes(data_disponibilizacao);
CREATE INDEX IF NOT EXISTS idx_intim_proc ON intimacoes(numero_processo);

CREATE TABLE IF NOT EXISTS processos_clientes (
    numero_processo TEXT PRIMARY KEY,
    cliente_id      INTEGER NOT NULL REFERENCES clientes(id) ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS campanhas (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    google_id       TEXT,
    nome            TEXT,
    orcamento_diario REAL,
    palavras_chave  TEXT,
    url_final       TEXT,
    criada_em       TEXT NOT NULL DEFAULT (datetime('now','localtime'))
);
"""


def connect(path: Path | str | None = None) -> sqlite3.Connection:
    path = Path(path) if path else config.DB_PATH
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA)
    return conn
