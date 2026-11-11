"use strict";
// Login with the company's identity provider (report 10.11.2026, gap 1): OpenID Connect
// authorization code flow with PKCE for a public web client — no client secret in the browser.
// The second factor (MFA) is run by the identity provider; the API refuses tokens without it.
// The access token is kept in memory only (not in localStorage), so a reload asks to log in
// again; the provider's own session usually makes that one click.
const LOGIN_KEY = "vietbiz-login";
const b64url = (bytes) =>
  btoa(String.fromCharCode(...new Uint8Array(bytes))).replace(/\+/g, "-").replace(/\//g, "_").replace(/=+$/, "");
const randomText = (n = 32) => b64url(crypto.getRandomValues(new Uint8Array(n)));
async function pkceChallenge(verifier) {
  return b64url(await crypto.subtle.digest("SHA-256", new TextEncoder().encode(verifier)));
}
function loginRedirectUri() {
  return location.origin + location.pathname;
}
async function loginSettings(api) {
  const r = await fetch(api + "/auth/config", { credentials: "omit", redirect: "error" });
  if (!r.ok) throw { status: r.status };
  return r.json();
}
async function startLogin() {
  const api = localApi(),
    settings = await loginSettings(api);
  if (settings.mode !== "oidc") throw { messageKey: "loginDemoMode" };
  if (!settings.ready) throw { messageKey: "loginNotReady" };
  const verifier = randomText(48),
    login = { state: randomText(), verifier, api, at: Date.now() };
  try {
    sessionStorage.setItem(LOGIN_KEY, JSON.stringify(login));
  } catch {
    throw { messageKey: "loginFailed" };
  }
  const url = new URL(settings.authorization_endpoint);
  const params = {
    response_type: "code",
    client_id: settings.client_id,
    redirect_uri: loginRedirectUri(),
    scope: settings.scope || "openid",
    state: login.state,
    code_challenge: await pkceChallenge(verifier),
    code_challenge_method: "S256",
    ui_locales: lang,
  };
  if (settings.acr_values) params.acr_values = settings.acr_values;
  for (const [k, v] of Object.entries(params)) url.searchParams.set(k, v);
  location.assign(url.toString());
}
// Back from the provider with ?code=…&state=…: check the state, swap the code for a token.
async function finishLogin() {
  const query = new URLSearchParams(location.search),
    code = query.get("code"),
    returned = query.get("state"),
    failed = query.get("error");
  if (!code && !failed) return false;
  history.replaceState(null, "", loginRedirectUri());
  let login = null;
  try {
    login = JSON.parse(sessionStorage.getItem(LOGIN_KEY) || "null");
    sessionStorage.removeItem(LOGIN_KEY);
  } catch {}
  // A code we did not ask for, or an old one, is never exchanged.
  if (failed || !login || !returned || returned !== login.state || Date.now() - login.at > 10 * 60 * 1000)
    throw { messageKey: failed === "access_denied" ? "loginCancelled" : "loginFailed" };
  const settings = await loginSettings(login.api);
  if (settings.mode !== "oidc" || !settings.ready) throw { messageKey: "loginNotReady" };
  const r = await fetch(settings.token_endpoint, {
    method: "POST",
    credentials: "omit",
    redirect: "error",
    headers: { "Content-Type": "application/x-www-form-urlencoded" },
    body: new URLSearchParams({
      grant_type: "authorization_code",
      code,
      redirect_uri: loginRedirectUri(),
      client_id: settings.client_id,
      code_verifier: login.verifier,
    }),
  });
  const body = r.ok ? await r.json().catch(() => ({})) : {};
  if (!body.access_token || String(body.token_type || "bearer").toLowerCase() !== "bearer")
    throw { messageKey: "loginFailed" };
  $("api").value = login.api;
  state.token = body.access_token;
  state.logoutUrl = settings.end_session_endpoint || "";
  await connectSignedIn();
  return true;
}
async function connectSignedIn() {
  const api = localApi();
  resetContext();
  state.api = api;
  state.user = "";
  state.orgs = [];
  renderOrgOptions();
  const health = await request("/health");
  if (health.auth_mode !== "oidc") throw { messageKey: "loginDemoMode" };
  $("login").hidden = true;
  $("logout").hidden = false;
  await loadCompanies();
  notice(t("loggedIn"));
}
function logout() {
  const url = state.logoutUrl;
  state.token = "";
  state.logoutUrl = "";
  state.orgs = [];
  resetContext();
  renderOrgOptions();
  $("login").hidden = false;
  $("logout").hidden = true;
  notice(t("loggedOut"));
  if (url) {
    const target = new URL(url);
    target.searchParams.set("post_logout_redirect_uri", loginRedirectUri());
    location.assign(target.toString());
  }
}
$("login").onclick = () => run(startLogin, $("login"));
$("logout").onclick = () => logout();
run(finishLogin);
