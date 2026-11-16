// node --test: the app bundle gets a fixed https API, its own redirect and a strict CSP.
import { test } from "node:test";
import assert from "node:assert/strict";
import { existsSync, readFileSync } from "node:fs";
import { join, dirname } from "node:path";
import { fileURLToPath } from "node:url";
import { build, csp, settings } from "./build-web.mjs";

const www = join(dirname(fileURLToPath(import.meta.url)), "..", "www");
const env = { VIETBIZ_API_URL: "https://api.vietbiz.example/", VIETBIZ_OIDC_ORIGIN: "https://id.vietbiz.example/oauth/v2" };

test("settings need https and keep only the origins", () => {
  assert.deepEqual(settings(env), {
    api: "https://api.vietbiz.example", idp: "https://id.vietbiz.example", redirectUri: "cz.vietbiz.app:/oauth/callback",
  });
  assert.throws(() => settings({ ...env, VIETBIZ_API_URL: "http://api.vietbiz.example" }), /https/);
  assert.throws(() => settings({ VIETBIZ_OIDC_ORIGIN: env.VIETBIZ_OIDC_ORIGIN }), /VIETBIZ_API_URL is required/);
  assert.throws(() => settings({ ...env, VIETBIZ_APP_SCHEME: "https" }), /reverse-domain/);
});

test("the bundle has config.js, the CSP and the safe-area viewport", () => {
  build(env);
  const html = readFileSync(join(www, "index.html"), "utf8");
  const config = readFileSync(join(www, "config.js"), "utf8");
  assert.match(config, /"native":true/);
  assert.match(config, /"api":"https:\/\/api.vietbiz.example"/);
  assert.match(config, /"redirectUri":"cz.vietbiz.app:\/oauth\/callback"/);
  assert.ok(html.includes(`content="${csp(settings(env))}"`));
  assert.ok(html.indexOf('src="config.js"') < html.indexOf('src="runtime.js"'), "config.js before runtime.js");
  assert.ok(html.includes("viewport-fit=cover"));
  assert.ok(!csp(settings(env)).includes("unsafe-inline"));
  assert.ok(existsSync(join(www, "login.js")) && existsSync(join(www, "partner-check.js")));
});
