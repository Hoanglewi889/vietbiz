# Czech legal basis for VietBiz document handling

Researched 2026-11-08 by Claude from statute mirrors and professional sources, not the
official e-Sbírka text. Verify each provision on https://www.e-sbirka.gov.cz before it is
shown to customers. This is engineering input, not legal or tax advice.

## What the code may and may not conclude

- VietBiz may check completeness and arithmetic of a tax document and explain it.
- VietBiz must not conclude deductibility, tax payable or a tax regime. Paid, systematic
  tax advice is reserved to tax advisers (zákon č. 523/1992 Sb., § 1–2;
  [dauc.cz](https://www.dauc.cz/predpisy/186/523-1992-sb)). Those calls stay with the
  business's accountant or tax adviser.

## Tax document content — implemented in `services/api/app/tax_document_rules.py`

| Rule | Provision (zákon č. 235/2004 Sb.) | Source |
| --- | --- | --- |
| Mandatory elements a)–l), conditional wording, permitted omissions | § 29 odst. 1–3 | [kurzy.cz § 29](https://www.kurzy.cz/zakony/235-2004-zakon-o-dani-z-pridane-hodnoty-dph/paragraf-29/) |
| Simplified document up to 10 000 Kč; exclusions incl. reverse charge | § 30 odst. 1–2 | [kurzy.cz § 30](https://www.kurzy.cz/zakony/235-2004-zakon-o-dani-z-pridane-hodnoty-dph/paragraf-30/) |
| Elements a simplified document may omit; total required without tax amount | § 30a odst. 1–2 | [kurzy.cz § 30a](https://www.kurzy.cz/zakony/235-2004-zakon-o-dani-z-pridane-hodnoty-dph/paragraf-30a/) |
| Rates 21 % and 12 % since 2024-01-01 (15 %/10 % abolished) | § 47 | [kurzy.cz/dph](https://www.kurzy.cz/dph/) (updated 2026-04-01) |

Simplified-document mandatory set = § 29 odst. 1 minus § 30a odst. 1 (derived; no
statute lists it directly). Arithmetic tolerance (1 unit of currency) is a plausibility
check, not a legal rule. Documents whose supply date (or, when none is stated, issue date) is
before 2024 are reported as outside the rule set. A simplified document stays simplified
when customer details are shown voluntarily; a full document needs the tax base even when
exempt or reverse-charged (§ 29 odst. 3 písm. d) waives only rate and tax).

## Retention — design constraint, not implemented

| Records | Period | Provision | Source |
| --- | --- | --- | --- |
| VAT tax documents | 10 years from end of the tax period of the supply | § 35 zákon 235/2004 | [kurzy.cz § 35](https://www.kurzy.cz/zakony/235-2004-zakon-o-dani-z-pridane-hodnoty-dph/paragraf-35/) |
| Electronic storage allowed with origin/integrity data; in-country or continuous remote access | § 35a zákon 235/2004 | [kurzy.cz § 35a](https://www.kurzy.cz/zakony/235-2004-zakon-o-dani-z-pridane-hodnoty-dph/paragraf-35a/) |
| Financial statements, annual report | 10 years | § 31 zákon 563/1991 | [podnikatel.cz](https://businesscenter.podnikatel.cz/pravo/zakony/ucto/f1397060/) |
| Accounting documents, books, inventories | 5 years; longer for open receivables and pending proceedings | § 31–32 zákon 563/1991 | same |
| Income-tax records | while the assessment period runs: 3 years base, up to 10 | § 148 zákon 280/2009 | [money.cz](https://money.cz/novinky-a-tipy/ucetnictvi-2/archivacni-lhuty-dokladu-z-ucetniho-a-danoveho-hlediska/) (2026-01-16) |
| Payroll records for pension insurance | 45 years | — | same |

Consequence: originals must never be auto-deleted on a single fixed period; minimum 10
years for anything that may be a VAT document. Electronic records must stay convertible to
readable form and protected against unauthorised change (§ 33 zákon 563/1991,
[pracepropravniky.cz](https://www.pracepropravniky.cz/zakony/zakon-o-ucetnictvi-uplne-zneni/paragraf-33/)).
A new accounting act passed first reading on 2026-03-12, planned effective 2028-01-01
([ČTK](https://www.ceskenoviny.cz/zpravy/2798197)); later stages not verified.

## Related obligations outside the current code

- **EET 2.0** from 2027-01-01 for in-person payments (cash, card, QR); signed 2026-09-17;
  EET OFF surcharge 1 400 Kč/month for eligible flat-tax persons, notice by 2027-01-11
  ([Finanční správa](https://financnisprava.gov.cz/cs/financni-sprava/media-a-verejnost/tiskove-zpravy-gfr/tiskove-zpravy-2026/snemovna-schvalila-eet-2-0),
  [vyfakturuj.cz](https://www.vyfakturuj.cz/fakturopedie/eet-2-0-je-schvalena-koho-se-tyka-a-co-se-zmeni-od-roku-2027/)).
  Sbírka number not verified.
- **ISDOC 6.0.2** (2022-03-23), Ministry of the Interior; XSD, Schematron and ISDOC.PDF
  ([MV ČR](https://archiv.mv.gov.cz/isdoc/clanek/aktualni-verze.aspx)). Implemented as
  import of ISDOC embedded in uploaded PDFs (`app/isdoc.py`, CR-2); element names checked
  against [isdoc-invoice-6.0.2.xsd](https://isdoc.cz/6.0.2/xsd/isdoc-invoice-6.0.2.xsd).
  Not yet validated against the official XSD/Schematron in CI (isdoc.cz is not reachable
  from the build sandbox).
- **ViDA**: structured EN 16931 e-invoices for selected intra-EU B2B supplies from 2030-07-01
  ([dauc.cz](https://www.dauc.cz/clanek/497/e-invoicing-bude-povinny-jste-na-rok-2030-pripraveni)).
- **AML** (zákon č. 253/2008 Sb.): external accountants are obliged persons; records 10 years
  ([POHODA](https://portal.pohoda.cz/dane-ucetnictvi-mzdy/ucetnictvi/aml-povinnosti-a-rizika-pro-ucetni/)).
- **GDPR** + zákon č. 110/2019 Sb.: VietBiz is a processor; Art. 28 agreement required
  ([epravo.cz](https://www.epravo.cz/top/clanky/nalezitosti-zpracovatelske-smlouvy-108130.html)).
  Reconcile deletion-on-termination with statutory retention.
