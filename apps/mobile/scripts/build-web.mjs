// Copies the accountant-web workspace into www/ for Capacitor and adds what the app needs:
//   config.js   window.VIETBIZ_RUNTIME = { native, api, redirectUri } (read by runtime.js)
//   a Content-Security-Policy <meta> (the web view gets no HTTP headers for bundled files)
//   viewport-fit=cover so the layout can respect the notch (env(safe-area-inset-*))
// Settings come from the environment:
//   VIETBIZ_API_URL       the API the app talks to, https (required)
//   VIETBIZ_OIDC_ORIGIN   the identity provider's origin (token endpoint), https (required)
//   VIETBIZ_APP_SCHEME    the app's URL scheme for the login redirect (default: the appId)
import { cpSync, mkdirSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const here = dirname(fileURLToPath(import.meta.url));
const root = join(here, "..");
const source = join(root, "..", "accountant-web");
const out = join(root, "www");

export function settings(env = process.env) {
  const config = JSON.parse(readFileSync(join(root, "capacitor.config.json"), "utf8"));
  const https = (name) => {
    const value = env[name];
    if (!value) throw new Error(`${name} is required (https URL)`);
    const url = new URL(value);
    if (url.protocol !== "https:") throw new Error(`${name} must be https`);
    return url.origin;
  };
  const scheme = env.VIETBIZ_APP_SCHEME || config.appId;
  if (!/^[a-z][a-z0-9.+-]*\.[a-z0-9.+-]+$/.test(scheme)) throw new Error("VIETBIZ_APP_SCHEME must be a reverse-domain scheme");
  return { api: https("VIETBIZ_API_URL"), idp: https("VIETBIZ_OIDC_ORIGIN"), redirectUri: `${scheme}:/oauth/callback` };
}

export function csp({ api, idp }) {
  return [
    "default-src 'self'",
    "script-src 'self'",
    "style-src 'self'",
    "img-src 'self' data: blob:",
    "frame-src blob:",
    "font-src 'self'",
    `connect-src 'self' ${api} ${idp}`,
    "base-uri 'none'",
    "object-src 'none'",
    "form-action 'self'",
  ].join("; ");
}

export function page(html, s) {
  const head = [
    `<meta http-equiv="Content-Security-Policy" content="${csp(s)}" />`,
    `<script src="config.js" defer></script>`,
  ].join("\n    ");
  let result = html.replace('content="width=device-width,initial-scale=1"', 'content="width=device-width,initial-scale=1,viewport-fit=cover"');
  if (result === html) throw new Error("viewport meta not found");
  const marker = '    <script src="runtime.js" defer></script>';
  if (!result.includes(marker)) throw new Error("runtime.js script not found");
  return result.replace(marker, "    " + head + "\n" + marker);
}

export function build(env = process.env) {
  const s = settings(env);
  rmSync(out, { recursive: true, force: true });
  mkdirSync(out, { recursive: true });
  cpSync(source, out, { recursive: true });
  writeFileSync(
    join(out, "config.js"),
    `"use strict";\nwindow.VIETBIZ_RUNTIME = ${JSON.stringify({ native: true, api: s.api, redirectUri: s.redirectUri })};\n`,
  );
  const index = join(out, "index.html");
  writeFileSync(index, page(readFileSync(index, "utf8"), s));
  return s;
}

if (process.argv[1] === fileURLToPath(import.meta.url)) {
  const s = build();
  console.log(`www/ ready: API ${s.api}, login back to ${s.redirectUri}`);
}
