"use strict";
// Partner check (decision H): ARES, register of bankrupts and VAT register by IČO, optionally
// with the bank account about to be paid. Owner / accountant, like the API. A register that did
// not answer is shown as such, never as "all clear".
const partnerCheck = { result: null, ticket: 0, seen: null };

function resetPartnerCheck() {
  partnerCheck.ticket++;
  partnerCheck.result = null;
  $("partner-result").replaceChildren();
}
function refreshPartnerCheck() {
  const allowed = Boolean(state.org) && ["owner", "accountant"].includes(state.role);
  $("partner-check").hidden = !allowed;
  // The role badge is also rewritten when the language changes: keep the result then.
  const seen = state.org + "|" + state.role;
  if (seen !== partnerCheck.seen) resetPartnerCheck();
  partnerCheck.seen = seen;
}
function partnerLine(label, value, cls = "") {
  const row = text("p", "", "partner-line " + cls);
  row.append(text("strong", label + ": "), document.createTextNode(value));
  return row;
}
function partnerLink(label, href) {
  const a = text("a", label);
  a.href = href;
  a.target = "_blank";
  a.rel = "noopener noreferrer";
  return a;
}
function renderPartnerCheck() {
  const r = partnerCheck.result,
    out = $("partner-result");
  out.replaceChildren();
  if (!r) return;
  const company = r.company,
    vat = r.vat,
    ins = r.insolvency;
  if (r.warnings.length) {
    const list = text("ul", "", "partner-warnings");
    r.warnings.forEach((code) => list.append(text("li", t("partnerWarn_" + code))));
    out.append(list);
  } else out.append(text("p", t("partnerNoWarnings"), "partner-ok"));
  if (company.status === "ok") {
    out.append(text("h4", company.name || r.ico));
    out.append(partnerLine("IČO", r.ico + (company.dic ? " · DIČ " + company.dic : "")));
    if (company.address) out.append(partnerLine(t("partnerAddress"), company.address));
  }
  const vatText = {
    ok: vat.unreliable ? t("partnerVatUnreliable") : t("partnerVatReliable"),
    not_registered: t("partnerVatNone"),
    not_found: t("partnerVatNotFound"),
    unavailable: t("partnerUnavailable"),
  }[vat.status];
  out.append(partnerLine(t("partnerVat"), vatText, vat.unreliable ? "bad" : ""));
  if (vat.status === "ok" && vat.published_accounts.length)
    out.append(partnerLine(t("partnerAccounts"), vat.published_accounts.map((a) => a.account).join(", ")));
  if (r.account)
    out.append(
      partnerLine(
        t("partnerAccount"),
        r.account.account + " — " + t(r.account.published === null ? "partnerUnavailable" : r.account.published ? "partnerAccountPublished" : "partnerAccountNotPublished"),
        r.account.published === false ? "bad" : "",
      ),
    );
  const insText =
    ins.status === "unavailable" ? t("partnerUnavailable") : ins.listed ? t("partnerInsolvencyListed") : ins.status === "ok" ? t("partnerInsolvencyNone") : "—";
  out.append(partnerLine(t("partnerInsolvency"), insText, ins.listed ? "bad" : ""));
  for (const p of ins.proceedings || []) {
    const row = text("p", "", "partner-line small");
    row.append(document.createTextNode([p.case, p.date].filter(Boolean).join(" · ") + " "));
    if (p.url) row.append(partnerLink("ISIR", p.url));
    out.append(row);
  }
  const sources = text("p", fill(t("partnerCheckedAt"), { time: timestamp(r.checked_at) }) + " · ", "muted small");
  if (company.url) sources.append(partnerLink("ARES", company.url));
  if (vat.url) sources.append(document.createTextNode(" · "), partnerLink(t("partnerVatRegister"), vat.url));
  out.append(sources);
}
async function checkPartner() {
  const ico = $("partner-ico").value.replace(/\s+/g, ""),
    account = $("partner-account").value.trim();
  if (!/^\d{8}$/.test(ico)) throw Object.assign(Error("Invalid IČO"), { messageKey: "partnerInvalidIco" });
  const ticket = ++partnerCheck.ticket,
    org = state.org;
  const query = account ? "?account=" + encodeURIComponent(account) : "";
  const result = await request(base() + "/registry-check/" + ico + query);
  if (ticket !== partnerCheck.ticket || org !== state.org) return;
  partnerCheck.result = result;
  renderPartnerCheck();
}
$("partner-form").onsubmit = (e) => {
  e.preventDefault();
  run(checkPartner, $("partner-submit"));
};
new MutationObserver(refreshPartnerCheck).observe($("role-badge"), { childList: true, characterData: true, subtree: true });
refreshPartnerCheck();
