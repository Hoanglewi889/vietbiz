# GDPR drafts for VietBiz — for review by a Czech lawyer

DRAFT, written by Claude on 2026-11-11 as engineering input, not legal advice. Nothing here
may be shown to customers or signed before a lawyer qualified in Czech data-protection law
has reviewed it. Places marked **[…]** need facts only the owner has (company name, address,
hosting provider). Regulation: GDPR (EU 2016/679); Czech implementing act: zákon
č. 110/2019 Sb.; supervisory authority: Úřad pro ochranu osobních údajů (ÚOOÚ,
https://uoou.gov.cz).

## 1. Who is who (to confirm with the lawyer)

| Party | Role for the data in VietBiz | Why |
| --- | --- | --- |
| The business (OSVČ or s.r.o.) using VietBiz | Controller (správce) of its customers', suppliers' and staff's data | It decides why the data is kept (its accounting, invoicing, staff) |
| The accounting firm working in VietBiz | Processor for the business, or a separate controller for its own legal duties — **lawyer to decide** | Depends on the accounting contract |
| **[VietBiz operator]** | Processor (zpracovatel) for each business | Hosts and processes on the business's instructions; needs a DPA (§ 3) |
| Hosting provider, identity provider (OIDC) | Sub-processors | Listed in the DPA annex; EU locations planned |

## 2. Record of processing (čl. 30) — VietBiz as processor

| Data | Data subjects | Purpose | Legal basis of the controller | Where in VietBiz |
| --- | --- | --- | --- | --- |
| Names, IČO/DIČ (an OSVČ's DIČ may contain the rodné číslo), addresses, bank accounts on received and issued invoices | Customers, suppliers | Bookkeeping, invoicing, VAT | čl. 6(1)(c) legal obligation (accounting, VAT); 6(1)(b) contract | `documents`, `document_extractions`, `issued_invoices`, originals (sealed) |
| Bank movements: counterparty names and accounts, amounts, messages | Counterparties | Payment matching, bookkeeping | 6(1)(c) | `bank_transactions`, statement files (sealed) |
| Staff: display name, job, hourly rate (optional), "minor" flag, shifts, tips | Employees | Shift and cash control | 6(1)(b) employment contract; 6(1)(c) working-time records | `staff_members`, `shifts` |
| Users: display name, role, identity hash, actions | Owner, staff, accountants | Access control, audit trail | 6(1)(b), 6(1)(f) security | `users`, `memberships`, `audit_events` |

No special categories (čl. 9) are requested. Transfers outside the EU: none planned —
**[confirm hosting and identity provider locations]**. Security measures (čl. 32):
`docs/SECURITY_HARDENING.md`.

## 3. Retention (proposal — the controller decides; lawyer to confirm)

| Data | Keep at least | Source | Proposal after that |
| --- | --- | --- | --- |
| Accounting records (účetní záznamy) | 5 years after the end of the accounting period | § 31 zákona č. 563/1991 Sb. | Delete or hand back on request |
| Tax documents for VAT | 10 years after the end of the taxable period | § 35 zákona č. 235/2004 Sb. | Delete or hand back on request |
| Payroll records for pension insurance | 30 years (older sources) — one 2026 source says 45 years; **verify** | § 35a zákona č. 582/1991 Sb. | Not held by VietBiz today (no payroll module) |
| Shift records (evidence pracovní doby) | **verify** with the lawyer | zákoník práce | — |
| Audit log | Proposal: 2 years | Security (6(1)(f)) | Delete |
| User accounts | Until the account is closed | — | Remove within 30 days, keep audit entries |

## 4. Rights of data subjects — how VietBiz supports the controller

| Right | In VietBiz today |
| --- | --- |
| Access, portability (čl. 15, 20) | Owner export: `GET /v1/organizations/{org}/export` → ZIP with every record and the decrypted originals (CR-18) |
| Rectification (čl. 16) | Records are edited in the app (profiles, staff, extraction corrections) |
| Erasure (čl. 17) | Limited while a legal retention period runs (§ 3); a deletion function after retention is **not built yet** |
| Breach notification (čl. 33) | Processor tells the controller without undue delay; controller tells ÚOOÚ within 72 hours where required |

## 5. DPA (čl. 28 odst. 3) — clauses the contract must contain

1. Subject-matter, duration, nature and purpose of processing; types of personal data and
   categories of data subjects (copy § 2).
2. Processing only on documented instructions of the controller.
3. Confidentiality of everyone with access.
4. Security measures under čl. 32 (annex: `docs/SECURITY_HARDENING.md`).
5. Sub-processors only with the controller's authorisation; list in an annex; same duties
   passed down.
6. Help with data-subject requests (export, rectification).
7. Help with čl. 32–36 (security, breach notification, impact assessment).
8. At the end: delete or return all data (the export in § 4), unless law requires storage.
9. Information and audits to show compliance.

## 6. Privacy notice — short drafts for the app

**Tiếng Việt (nháp):** VietBiz giúp doanh nghiệp của bạn lưu chứng từ, hoá đơn, sao kê ngân
hàng và ca làm việc. Doanh nghiệp của bạn quyết định dữ liệu nào được lưu và vì sao;
**[đơn vị vận hành VietBiz]** chỉ xử lý dữ liệu theo chỉ dẫn của doanh nghiệp. Dữ liệu được
lưu trong EU, file gốc được mã hoá. Chứng từ kế toán được giữ ít nhất 5 năm, chứng từ thuế
DPH ít nhất 10 năm theo luật Séc. Chủ doanh nghiệp có thể tải toàn bộ dữ liệu bất cứ lúc
nào. Bạn có quyền xem, sửa, yêu cầu xoá (trong giới hạn luật lưu trữ) và khiếu nại tới ÚOOÚ
(uoou.gov.cz). Liên hệ: **[email]**.

**Česky (návrh):** VietBiz pomáhá vaší firmě uchovávat doklady, faktury, bankovní výpisy a
směny. O tom, jaká data se ukládají a proč, rozhoduje vaše firma; **[provozovatel VietBiz]**
je zpracovává jen podle jejích pokynů. Data jsou uložena v EU, originály jsou šifrované.
Účetní záznamy se uchovávají nejméně 5 let, daňové doklady k DPH nejméně 10 let podle
českých zákonů. Majitel firmy si může kdykoli stáhnout všechna data. Máte právo na přístup,
opravu, výmaz (v mezích zákonných lhůt) a stížnost u ÚOOÚ (uoou.gov.cz). Kontakt: **[e-mail]**.
