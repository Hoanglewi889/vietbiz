# Owner decisions — 12.11.2026

Answers the owner gave to the open questions in the overall report (11.11.2026). Codex and Claude
work from these; change them only with a new owner decision.

| Code | Question | Decision | What follows in the code |
| --- | --- | --- | --- |
| D | Merge order of the open PRs | Only the owner merges, in the report's order (#1, #18, then #2 → #26) | Nothing; Claude and Codex never merge |
| A | AI (Claude API) to read invoice photos and translate news | Later, after a DPA and encryption are in place | No AI calls; `draft_with_adapter` stays behind `rights_confirmed`; news is written by people |
| B | Tax reports only as drafts? | Yes — drafts only; the accountant signs | Exports stay marked as drafts for the accountant |
| H | ARES / unreliable VAT payer / insolvency register lookups | Do it — large benefit, small risk (IČO/DIČ leave the app to public state registers) | Next PR after the news change |
| C | Payment gateway | Later; QR Platba is enough for the first stage | Nothing |
| E | Paid e-mail sending service | Later, after real login | Nothing |
| F | Datová schránka with real accounts | After the security stage | Nothing |
| G | News sources | **Changed by the owner:** take news freely from Seznam Zprávy and other Czech outlets, international news and mainstream Vietnamese outlets, and write it again (report proposal was: official sources only) | CR-20: more sources (headline + link only), every item written in the editor's own words, several sources cited; legal news still needs an official link |

## G — what "write it again" may and may not mean

Engineering reading of the rules, to be confirmed by a lawyer before VietBiz News is public:

- Facts and a "denní zpráva" are not protected works (§ 2 odst. 6 zákona č. 121/2000 Sb.).
- Czech press publishers have a right over online use of their articles for 2 years (§ 87b); it
  does not cover hyperlinks, single words or very short extracts.
- Vietnam's Decree 174/2026/NĐ-CP (from 1.7.2026) fines copying or reposting press works without
  permission, including light rewording with "Nguồn: …"; writing independently from several
  sources with citations is the lawful pattern described in Vietnamese press coverage of it.
- So VietBiz keeps only headline + link + date, never the article text or images; the editor
  writes a new Vietnamese title and summary, cites every source with a link, and a reviewer signs
  off. Translating an article sentence by sentence is not "writing again".
- VnExpress's terms forbid commercial copying without written permission; Vietnam+ and Radio
  Prague International mark their feeds ©. Linking and own-words reporting stay within that.
