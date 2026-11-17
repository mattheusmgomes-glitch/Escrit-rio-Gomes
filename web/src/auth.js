// Login por senha única do escritório + cookie de sessão assinado (HMAC-SHA256).

const COOKIE = "sessao";
const DURACAO_S = 12 * 60 * 60;
const enc = new TextEncoder();

const b64url = (buf) => btoa(String.fromCharCode(...new Uint8Array(buf)))
  .replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");

async function chave(segredo) {
  return crypto.subtle.importKey("raw", enc.encode(segredo), { name: "HMAC", hash: "SHA-256" }, false, ["sign"]);
}

async function assinar(valor, segredo) {
  return b64url(await crypto.subtle.sign("HMAC", await chave(segredo), enc.encode(valor)));
}

/** Comparação em tempo constante (compara os HMACs das duas strings). */
async function iguais(a, b, segredo) {
  const [x, y] = await Promise.all([assinar(a, segredo), assinar(b, segredo)]);
  let diff = x.length ^ y.length;
  for (let i = 0; i < Math.min(x.length, y.length); i++) diff |= x.charCodeAt(i) ^ y.charCodeAt(i);
  return diff === 0;
}

function verificarConfig(env) {
  if (!env.APP_PASSWORD || !env.SESSION_SECRET || env.SESSION_SECRET.length < 32)
    throw new Error("Configure os segredos APP_PASSWORD e SESSION_SECRET (mín. 32 caracteres).");
}

export async function senhaCorreta(env, senha) {
  verificarConfig(env);
  return iguais(String(senha ?? ""), env.APP_PASSWORD, env.SESSION_SECRET);
}

export async function criarCookie(env, agora = Date.now()) {
  verificarConfig(env);
  const exp = Math.floor(agora / 1000) + DURACAO_S;
  const valor = `${exp}`;
  const sig = await assinar(valor, env.SESSION_SECRET);
  return `${COOKIE}=${valor}.${sig}; Path=/; HttpOnly; Secure; SameSite=Strict; Max-Age=${DURACAO_S}`;
}

export const cookieSaida = () => `${COOKIE}=; Path=/; HttpOnly; Secure; SameSite=Strict; Max-Age=0`;

export async function autenticado(request, env, agora = Date.now()) {
  verificarConfig(env);
  const cookies = request.headers.get("Cookie") ?? "";
  const m = cookies.match(new RegExp(`(?:^|;\\s*)${COOKIE}=([^;]+)`));
  if (!m) return false;
  const [valor, sig] = m[1].split(".");
  if (!valor || !sig || !(Number(valor) > agora / 1000)) return false;
  return iguais(sig, await assinar(valor, env.SESSION_SECRET), env.SESSION_SECRET);
}
