// Conector REST genérico para a plataforma de gestão do escritório.
import { CAMPOS, soDigitos } from "./clientes.js";

export class PlataformaErro extends Error {}

export function payload(cliente, mapeamento = {}) {
  const out = {};
  for (const campo of CAMPOS) {
    let v = cliente[campo];
    if (!v) continue;
    if (campo === "cpf_cnpj" || campo === "cep") v = soDigitos(v);
    const destino = campo in mapeamento ? mapeamento[campo] : campo;
    if (destino) out[destino] = v;
  }
  return out;
}

export function extrairId(data, caminho = "id") {
  let atual = data;
  for (const p of (caminho || "id").split(".")) {
    if (atual && typeof atual === "object" && p in atual) atual = atual[p];
    else return null;
  }
  return typeof atual === "string" || typeof atual === "number" ? String(atual) : null;
}

export const valorAuth = (prefixo, token) => (String(prefixo).trim() ? `${String(prefixo).trim()} ${token}` : token);

export function configurada(cfg, env) {
  return Boolean(cfg?.ativo && cfg?.base_url && env.PLATAFORMA_TOKEN);
}

export async function enviarCliente(cliente, cfg, env, fetchFn = fetch) {
  if (!configurada(cfg, env)) throw new PlataformaErro("Plataforma não configurada (Configurações > Plataforma e segredo PLATAFORMA_TOKEN).");
  if (!/^https:\/\//.test(cfg.base_url)) throw new PlataformaErro("A URL da plataforma deve usar https://.");
  const base = cfg.base_url.replace(/\/+$/, "");
  const ep = "/" + String(cfg.endpoint_clientes || "/clientes").replace(/^\/+|\/+$/g, "");
  const url = cliente.plataforma_id ? `${base}${ep}/${encodeURIComponent(cliente.plataforma_id)}` : `${base}${ep}`;
  let r;
  try {
    r = await fetchFn(url, {
      method: cliente.plataforma_id ? "PUT" : "POST",
      headers: {
        [cfg.auth_header || "Authorization"]: valorAuth(cfg.auth_prefix ?? "Bearer", env.PLATAFORMA_TOKEN),
        "Content-Type": "application/json", Accept: "application/json",
      },
      body: JSON.stringify(payload(cliente, cfg.mapeamento || {})),
    });
  } catch (e) {
    throw new PlataformaErro(`Falha de conexão com a plataforma: ${e.message}`);
  }
  if (!r.ok) throw new PlataformaErro(`Plataforma respondeu ${r.status}: ${(await r.text()).slice(0, 300)}`);
  if (cliente.plataforma_id) return cliente.plataforma_id;
  const id = extrairId(await r.json().catch(() => ({})), cfg.campo_id_resposta);
  if (!id) throw new PlataformaErro("Cliente enviado, mas a resposta não trouxe um ID.");
  return id;
}
