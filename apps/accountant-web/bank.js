"use strict";
// Bank statements and payment matching (CR-11): import a GPC/CSV statement, see what was paid,
// match the rest by hand. Nothing here talks to a bank; the file is read by the server.
const bankState = { items: [], counts: {}, filter: "unmatched", ticket: 0 };

async function loadBank() {
  const ticket = ++bankState.ticket;
  $("bank-tab").hidden = !FINANCE_ROLES.includes(state.role);
  if ($("bank-tab").hidden) {
    if (!$("bank-view").hidden) setTab("tasks");
    return;
  }
  const body = await request(base() + "/bank/transactions");
  if (ticket !== bankState.ticket) return;
  bankState.items = body.items;
  bankState.counts = body.counts;
  renderBank();
}
function bankAmount(value, currency) {
  return (Number(value) > 0 ? "+" : "") + money(value, currency);
}
function bankAction(tx, verb, body) {
  return request(base() + "/bank/transactions/" + encodeURIComponent(tx.id) + "/" + verb,
    json("POST", { expected_version: tx.version, ...body }));
}
async function bankDecide(tx, verb, body) {
  try {
    await bankAction(tx, verb, body);
  } catch (error) {
    if (error.status === 409) {
      await loadBank();
      throw { messageKey: "bankConflict" };
    }
    throw error;
  }
  notice(t("saved"));
  await Promise.all([loadBank(), invoicesReady() ? loadInvoices() : null]);
}
function bankRow(tx) {
  const row = text("article", "", "bank-row " + tx.status + (Number(tx.amount) > 0 ? " in" : " out")),
    info = text("div", "");
  const who = [tx.counter_name, tx.counter_account].filter(Boolean).join(" · ") || t("bankNoCounterparty");
  info.append(
    text("strong", who),
    document.createElement("br"),
    text("small", [shortBankDate(tx.booked_on), tx.vs ? "VS " + tx.vs : "", tx.message].filter(Boolean).join(" · ")),
  );
  if (tx.possible_duplicate_of.length)
    info.append(text("p", t("bankPossibleDuplicate"), "bank-flag"));
  const side = text("div", "", "bank-side");
  side.append(text("strong", bankAmount(tx.amount, tx.currency), "bank-amount"));
  const actions = text("div", "", "bank-actions");
  if (tx.status === "unmatched") {
    for (const s of tx.suggestions) {
      const label = s.issued_invoice_id
        ? fill(t("bankMatchInvoice"), { number: s.number, remaining: money(s.remaining, "CZK") })
        : fill(t("bankMatchDocument"), { supplier: s.supplier || "—", number: s.number || "—" });
      actions.append(button(label, () => bankDecide(tx, "match",
        s.issued_invoice_id ? { issued_invoice_id: s.issued_invoice_id } : { document_id: s.document_id }), "secondary"));
    }
    actions.append(button(t("bankNoDocument"), () => bankDecide(tx, "ignore", { note: t("bankNoDocumentNote") }), "secondary"));
  } else {
    side.append(text("small", tx.status === "matched"
      ? fill(t(tx.matched_by === "auto" ? "bankMatchedAuto" : "bankMatchedManual"), { what: tx.invoice_number || t("bankDocument") })
      : t("bankIgnored")));
    actions.append(button(t("bankUndo"), () => bankDecide(tx, "unmatch", {}), "secondary"));
  }
  row.append(info, side, actions);
  return row;
}
function shortBankDate(iso) {
  return new Intl.DateTimeFormat(lang === "cs" ? "cs-CZ" : "vi-VN", { timeZone: "UTC" }).format(new Date(iso + "T00:00:00Z"));
}
function renderBank() {
  const list = $("bank-list");
  list.replaceChildren();
  for (const key of ["unmatched", "matched", "ignored"]) {
    const chip = $("bank-filter-" + key);
    chip.textContent = COPY[lang].bankFilters[key] + " (" + (bankState.counts[key] || 0) + ")";
    chip.classList.toggle("active", bankState.filter === key);
    chip.setAttribute("aria-pressed", String(bankState.filter === key));
  }
  const shown = bankState.items.filter((tx) => tx.status === bankState.filter);
  list.append(...shown.map(bankRow));
  if (!shown.length) empty(list, t(bankState.items.length ? "bankNothingHere" : "bankEmpty"), t("bankEmptyHint"), "⇄");
}
async function importStatement() {
  const file = $("bank-file").files[0];
  if (!file) throw { messageKey: "chooseFile" };
  const form = new FormData();
  form.append("file", file);
  let result;
  try {
    result = await request(base() + "/bank/imports", { method: "POST", body: form });
  } catch (error) {
    if (error.status === 409) throw { messageKey: "bankAlreadyImported" };
    if (error.status === 422) throw { messageKey: "bankUnreadable" };
    throw error;
  }
  $("bank-file").value = "";
  notice(fill(t("bankImported"), { added: result.added, known: result.already_known, matched: result.auto_matched }));
  await Promise.all([loadBank(), invoicesReady() ? loadInvoices() : null]);
}
function resetBank() {
  bankState.ticket++;
  bankState.items = [];
  bankState.counts = {};
  bankState.filter = "unmatched";
  $("bank-tab").hidden = true;
  if (!$("bank-view").hidden) setTab("tasks");
  $("bank-list").replaceChildren();
  $("bank-file").value = "";
}
$("bank-tab").onclick = () => setTab("bank");
$("bank-form").onsubmit = (e) => {
  e.preventDefault();
  run(importStatement, $("bank-import"));
};
for (const key of ["unmatched", "matched", "ignored"])
  $("bank-filter-" + key).onclick = () => {
    bankState.filter = key;
    renderBank();
  };
