// Cadastro de clientes: validação e persistência no D1.

export const CAMPOS = [
  "tipo", "nome", "cpf_cnpj", "rg", "data_nascimento", "estado_civil", "profissao",
  "email", "telefone", "cep", "logradouro", "numero", "complemento", "bairro",
  "cidade", "uf", "area", "origem", "observacoes",
];

export class ValidacaoErro extends Error {}

export const soDigitos = (v) => String(v ?? "").replace(/\D/g, "");

export function cpfValido(cpf) {
  const d = soDigitos(cpf);
  if (d.length !== 11 || /^(\d)\1+$/.test(d)) return false;
  for (const n of [9, 10]) {
    let soma = 0;
    for (let i = 0; i < n; i++) soma += Number(d[i]) * (n + 1 - i);
    if (((soma * 10) % 11) % 10 !== Number(d[n])) return false;
  }
  return true;
}

export function cnpjValido(cnpj) {
  const d = soDigitos(cnpj);
  if (d.length !== 14 || /^(\d)\1+$/.test(d)) return false;
  const p1 = [5, 4, 3, 2, 9, 8, 7, 6, 5, 4, 3, 2];
  const p2 = [6, ...p1];
  for (const [pesos, pos] of [[p1, 12], [p2, 13]]) {
    let soma = 0;
    for (let i = 0; i < pos; i++) soma += Number(d[i]) * pesos[i];
    const resto = soma % 11;
    if ((resto < 2 ? 0 : 11 - resto) !== Number(d[pos])) return false;
  }
  return true;
}

export function formatarDocumento(doc) {
  const d = soDigitos(doc);
  if (d.length === 11) return `${d.slice(0, 3)}.${d.slice(3, 6)}.${d.slice(6, 9)}-${d.slice(9)}`;
  if (d.length === 14) return `${d.slice(0, 2)}.${d.slice(2, 5)}.${d.slice(5, 8)}/${d.slice(8, 12)}-${d.slice(12)}`;
  return doc;
}

export function formatarTelefone(tel) {
  const d = soDigitos(tel);
  if (d.length === 11) return `(${d.slice(0, 2)}) ${d.slice(2, 7)}-${d.slice(7)}`;
  if (d.length === 10) return `(${d.slice(0, 2)}) ${d.slice(2, 6)}-${d.slice(6)}`;
  return tel;
}

/** Valida e normaliza os dados recebidos. Retorna um objeto só com CAMPOS. */
export function normalizar(entrada) {
  const c = {};
  for (const k of CAMPOS) c[k] = String(entrada?.[k] ?? "").trim();
  c.nome = c.nome.replace(/\s+/g, " ");
  c.tipo = c.tipo || "PF";
  if (c.nome.length < 3) throw new ValidacaoErro("Informe o nome completo do cliente.");
  if (!["PF", "PJ"].includes(c.tipo)) throw new ValidacaoErro("Tipo deve ser PF ou PJ.");
  if (c.cpf_cnpj) {
    if (c.tipo === "PF" && !cpfValido(c.cpf_cnpj)) throw new ValidacaoErro("CPF inválido.");
    if (c.tipo === "PJ" && !cnpjValido(c.cpf_cnpj)) throw new ValidacaoErro("CNPJ inválido.");
    c.cpf_cnpj = formatarDocumento(c.cpf_cnpj);
  }
  if (c.email) {
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(c.email)) throw new ValidacaoErro("E-mail inválido.");
    c.email = c.email.toLowerCase();
  }
  if (c.telefone) {
    if (![10, 11].includes(soDigitos(c.telefone).length))
      throw new ValidacaoErro("Telefone deve ter DDD + número (10 ou 11 dígitos).");
    c.telefone = formatarTelefone(c.telefone);
  }
  if (c.cep) {
    const d = soDigitos(c.cep);
    if (d.length !== 8) throw new ValidacaoErro("CEP deve ter 8 dígitos.");
    c.cep = `${d.slice(0, 5)}-${d.slice(5)}`;
  }
  c.uf = c.uf.toUpperCase();
  for (const k of CAMPOS) if (c[k] === "") c[k] = null;
  return c;
}

// ------------------------------------------------------------------ D1

export async function listar(db, busca = "") {
  const t = busca.trim();
  if (!t) return (await db.prepare("SELECT * FROM clientes ORDER BY nome COLLATE NOCASE").all()).results;
  const dig = soDigitos(t);
  return (await db.prepare(
    `SELECT * FROM clientes
     WHERE nome LIKE ?1 OR email LIKE ?1 OR telefone LIKE ?1 OR cidade LIKE ?1
        OR (?2 <> '' AND REPLACE(REPLACE(REPLACE(cpf_cnpj,'.',''),'-',''),'/','') LIKE ?3)
     ORDER BY nome COLLATE NOCASE`,
  ).bind(`%${t}%`, dig, `%${dig}%`).all()).results;
}

export const obter = (db, id) => db.prepare("SELECT * FROM clientes WHERE id = ?").bind(id).first();

export async function salvar(db, dados, id = null) {
  const c = normalizar(dados);
  try {
    if (id) {
      const sets = CAMPOS.map((k) => `${k} = ?`).join(", ");
      const r = await db.prepare(`UPDATE clientes SET ${sets}, atualizado_em = datetime('now') WHERE id = ?`)
        .bind(...CAMPOS.map((k) => c[k]), id).run();
      if (!r.meta.changes) return null;
    } else {
      const r = await db.prepare(
        `INSERT INTO clientes (${CAMPOS.join(", ")}) VALUES (${CAMPOS.map(() => "?").join(", ")})`,
      ).bind(...CAMPOS.map((k) => c[k])).run();
      id = r.meta.last_row_id;
    }
  } catch (e) {
    if (String(e.message).includes("UNIQUE") && String(e.message).includes("cpf_cnpj"))
      throw new ValidacaoErro("Já existe um cliente com este CPF/CNPJ.");
    throw e;
  }
  return obter(db, id);
}

export const excluir = (db, id) => db.prepare("DELETE FROM clientes WHERE id = ?").bind(id).run();

export async function vincularProcesso(db, numero, clienteId) {
  const n = soDigitos(numero);
  await db.batch([
    db.prepare(`INSERT INTO processos_clientes (numero_processo, cliente_id) VALUES (?, ?)
                ON CONFLICT(numero_processo) DO UPDATE SET cliente_id = excluded.cliente_id`).bind(n, clienteId),
    db.prepare("UPDATE intimacoes SET cliente_id = ? WHERE numero_processo = ?").bind(clienteId, n),
  ]);
}
