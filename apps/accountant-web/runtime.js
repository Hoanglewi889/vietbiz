"use strict";
// Where the workspace runs. In a browser nothing is set and the API must be local (see
// localApi). The mobile app (apps/mobile) adds config.js before this file:
//   window.VIETBIZ_RUNTIME = { native: true, api: "https://…", redirectUri: "cz.vietbiz.app:/oauth/callback" }
// so the app talks to one fixed API and logs in through the system browser (RFC 8252).
const RUNTIME = Object.freeze({ native: false, api: "", redirectUri: "", ...(window.VIETBIZ_RUNTIME || {}) });
const nativeApp = () => Boolean(RUNTIME.native && window.Capacitor?.isNativePlatform?.());
// Plugins are registered by the native side; no bundler is needed to reach them.
const nativePlugin = (name) => window.Capacitor?.Plugins?.[name] || window.Capacitor?.registerPlugin?.(name);
if (RUNTIME.native) document.documentElement.classList.add("native-app");
