CREATE TABLE clientes (
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
    criado_em       TEXT NOT NULL DEFAULT (datetime('now')),
    atualizado_em   TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE intimacoes (
    id                    INTEGER PRIMARY KEY AUTOINCREMENT,
    djen_id               TEXT UNIQUE,
    data_disponibilizacao TEXT,
    tribunal              TEXT,
    orgao                 TEXT,
    tipo_comunicacao      TEXT,
    tipo_documento        TEXT,
    classe                TEXT,
    numero_processo       TEXT,
    destinatarios         TEXT,
    advogados             TEXT,
    texto                 TEXT,
    link                  TEXT,
    cliente_id            INTEGER REFERENCES clientes(id) ON DELETE SET NULL,
    lida                  INTEGER NOT NULL DEFAULT 0,
    prazo                 TEXT,
    observacao            TEXT,
    capturada_em          TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_intim_data ON intimacoes(data_disponibilizacao);
CREATE INDEX idx_intim_proc ON intimacoes(numero_processo);

CREATE TABLE processos_clientes (
    numero_processo TEXT PRIMARY KEY,
    cliente_id      INTEGER NOT NULL REFERENCES clientes(id) ON DELETE CASCADE
);

CREATE TABLE campanhas (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    google_id        TEXT,
    nome             TEXT,
    orcamento_diario REAL,
    palavras_chave   TEXT,
    url_final        TEXT,
    criada_em        TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE config (
    chave TEXT PRIMARY KEY,
    valor TEXT NOT NULL
);

CREATE TABLE log_buscas (
    id         INTEGER PRIMARY KEY AUTOINCREMENT,
    origem     TEXT,
    encontradas INTEGER,
    novas      INTEGER,
    erro       TEXT,
    em         TEXT NOT NULL DEFAULT (datetime('now'))
);

CREATE TABLE login_falhas (
    ip TEXT NOT NULL,
    em TEXT NOT NULL DEFAULT (datetime('now'))
);
CREATE INDEX idx_login_falhas ON login_falhas(ip, em);
