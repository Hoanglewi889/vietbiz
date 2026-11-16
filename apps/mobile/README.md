# VietBiz mobile (iOS / Android)

The `apps/accountant-web` workspace in a Capacitor 8 shell. Login: OIDC + PKCE in the system
browser, back through `cz.vietbiz.app:/oauth/callback`; the token stays in memory.

```bash
npm ci
export VIETBIZ_API_URL=https://api-test.example VIETBIZ_OIDC_ORIGIN=https://id.example
npm test            # bundle checks
npm run sync        # build www/ + cap sync
npx cap open android   # or: npx cap open ios (macOS)
npm run assets      # regenerate icons and splash screens
```

Store steps, signing and what is still missing before a public release:
`docs/mobile/STORE_RELEASE.md`; listing texts: `docs/mobile/STORE_LISTING.md`.
