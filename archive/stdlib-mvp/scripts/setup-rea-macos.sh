#!/usr/bin/env bash
set -euo pipefail
# Run on user's Mac only. Review external packages and configuration changes before approval.
command -v node >/dev/null || { echo 'Node.js not found. Install Node 24 LTS (with nvm) first.'; exit 1; }
command -v npm >/dev/null || { echo 'npm not found.'; exit 1; }
node - <<'JS'
const [major,minor,patch]=process.versions.node.split('.').map(Number);
const ok=(major===22&&(minor>23||(minor===23&&patch>=4)))||(major===24&&(minor>22||(minor===22&&patch>=1)))||(major===26&&(minor>12||(minor===12&&patch>=1)));
if(!ok){console.error('REA needs Node 22.23.4+, 24.22.1+, or 26.12.1+. Found '+process.version);process.exit(1)}
JS
printf '\nREA installation for Claude Code and Codex (interactive, requires approval).\n'
printf 'Source: https://github.com/morluto/rea\n\n'
npx rea-agents@latest setup
printf '\nChecking REA health...\n'
npx rea-agents@latest doctor
printf '\nRestart Claude Code and Codex after successful setup.\n'
