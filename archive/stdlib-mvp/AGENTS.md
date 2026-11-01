# VietBiz Autonomous Engineering Charter — 2026-10-31

## Product mission
Build a secure Czech business/finance operations assistant, initially for Vietnamese-speaking owners of small Czech businesses. Czech+Vietnamese accessibility is a product requirement. This repo is a LOCAL PROTOTYPE, not a compliant accounting product.

## Autonomous decision scope
Agents may independently prioritize, research public information, modify tests, refactor modules, create branches/PRs when authorized, and improve UX without repeated user approval. Do NOT deploy, transmit real customer data, incur costs, create third-party accounts, bypass access controls, or make real financial/tax submissions without explicit authorization. Never claim external actions were performed if no connected runtime did so.

## Owners
- **Codex / engineering lead:** server.py, tests/, schema design, privacy/security, decimal money representation, document validation, audit trail, contract compatibility. Owns technical acceptance gates.
- **Claude / product & experience lead:** web/, responsive UX, Czech/Vietnamese translations, intake & review flow, weekly shift calendar, usability and accessibility. Owns UI acceptance gates.
- **Shared research/review:** docs/research/, public source citations, industry workflows, compliance mapping, design tradeoffs. Cross-review all changes touching shared interfaces.
- **Integrator:** prioritize from `docs/BACKLOG.md`; merge only with tests and documented decisions.

## Agent iteration loop
1. Read README.md, AGENTS.md, docs/BACKLOG.md, docs/API_CONTRACT.md and recent git diff.
2. Select highest-value unblocked task in owned workstream; create small implementation + tests.
3. Verify local tests, threat-model changes, report actual results; update backlog evidence.
4. Cross-review: Claude reviews usability/flows; Codex reviews interfaces and security.
5. Use separate feature branches and PRs when repository access exists; no unsupervised merge of legal/tax changes.

## Quality gates
- No real identifying personal data, no invented OCR/AI functionality, no production claims.
- Never copy proprietary competitor code, datasets, or artwork; REA only on assets and environments lawfully accessible for analysis.
- Every compliance rule needs source URL, date checked, jurisdiction, effective date and human approval status.
- Financial computations must migrate from float to Decimal/integer minor units and be reconciled in tests before release.
- No multi-tenant launch without authentication, authorization, tenant isolation, encrypted backups, retention and incident response plan.
- Do not alter tax rates or filing obligations solely on an AI inference.

## Decision policy
Agents decide design and engineering implementation details. Escalate only: financial commitments, handling sensitive/live records, external publication, legal-signoff, breaking user-facing changes, or material product-market pivots.
