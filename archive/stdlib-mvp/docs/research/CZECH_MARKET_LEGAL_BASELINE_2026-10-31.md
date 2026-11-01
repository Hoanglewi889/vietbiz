# Czech market/legal research baseline — 2026-10-31

This is research input, **not legal/tax advice**. Validate at implementation and before production release with qualified Czech counsel/accountant. Do not infer ethnic identity from business registries or scrape personal contact details.

## Verified market facts
- Czech Statistical Office: 69,685 Vietnamese citizens resident in Czechia at 2025-12-31, out of 1,131,197 foreign citizens. Source: https://csu.gov.cz/pocet-cizincu-demograficke-udalosti (checked 2026-10-31).
- Czech Ministry of Finance memorandum (2026-06-19) says at least one third of roughly 70,000 Vietnamese-origin residents conduct business or hold a trade licence. This is an indicative statement, **not** validated count of active unique commercial buyers. Source: https://mf.gov.cz/cs/ministerstvo/media/tiskove-zpravy/2026/ministerstvo-financi-podepsalo-memorandum-o-spolup-64357

## Industry segments to validate, not statistical rankings
1. Convenience grocery (potraviny/večerka): cash reconciliation, SKU inventory, expiry dates, POS, supplier invoices.
2. Restaurants/cafes/bistro: recipes, ingredients, shifts, tips, daily cash close, catering.
3. Nail/beauty: bookings, staff commissions, variable services, expenses.
4. Wholesale/import: stock movements, VAT, invoices, customer credit.
5. E-commerce: payment reconciliation, refunds, returns, shipping.
6. Services/construction: quote-to-invoice, project costing, contractors.

## Verified legal starting points (Czech Republic)
- VAT registration turnover: calendar-year threshold CZK 2,000,000 and CZK 2,536,500 have distinct effective dates. Official Financial Administration: https://financnisprava.gov.cz/cs/financni-sprava/novinky/novinky-2025/informace-ke-zmenam-v-platcovstvi-dph-2025
- EET 2.0: Jan 1 2027 planned effective; developer documentation and July 2026 sandbox. Official Financial Administration: https://financnisprava.gov.cz/cs/financni-sprava/media-a-verejnost/tiskove-zpravy-gfr/tiskove-zpravy-2026/financni-sprava-zahajuje-technickou-pripravu-k-eet ; final law no. 180/2026 Sb. must be confirmed for exact current applicability.
- Worktime recordkeeping: section 96 Labour Code obligations include start/end of shifts, overtime, night work and standby; employer remains responsible. https://ppropo.mpsv.cz/VIII9Evidencepracovnidoby
- Food businesses: notification duties under EU Regulation 852/2004 and Czech food law 110/1997; check correct regulator and business type. https://www.szpi.gov.cz/clanek/registrovane-subjekty.aspx

## Research priorities
- Gather Czech Statistical Office CZ-NACE establishment counts and public business-registry totals, not presumed Vietnamese ownership.
- Conduct opt-in interviews with owners and bookkeepers. Get anonymized workflows, top 5 pain points, existing software costs and migration barriers.
- For competitor research, document public URLs, version dates, screenshots used with permission, click paths, tested behavior, and uncertainty. Reverse engineer only legally accessible artifacts, no copy of proprietary code or user data.
- Establish a rules registry: rule_id, jurisdiction, industry, source_url, verified_at, effective_from, applicability, confidence, reviewer_status.
- Schedule source re-check before EET 2.0 release and when government updates appear.
