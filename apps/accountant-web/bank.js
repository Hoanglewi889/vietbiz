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
  if (!$("payout-month").value) $("payout-month").value = pragueToday().slice(0, 7);
  const [body, register, cover, payouts] = await Promise.all([
    request(base() + "/bank/transactions"),
    request(base() + "/bank/imports"),
    request(base() + "/bank/coverage?months=12"),
    request(base() + "/bank/card-payouts?month=" + encodeURIComponent($("payout-month").value)),
  ]);
  if (ticket !== bankState.ticket) return;
  bankState.items = body.items;
  bankState.counts = body.counts;
  bankState.register = register;
  bankState.cover = cover;
  bankState.payouts = payouts;
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
    // CR-13: say what a movement without a document is (a card payout, a bank fee …).
    const purpose = document.createElement("select");
    purpose.setAttribute("aria-label", t("bankPurpose"));
    const purposes = Number(tx.amount) > 0 ? ["card_payout", "own_transfer", "other"]
      : ["bank_fee", "tax_or_insurance", "salary", "own_transfer", "other"];
    purpose.append(...purposes.map((p) => option(p, COPY[lang].bankPurposes[p])));
    actions.append(purpose, button(t("bankNoDocument"), () => bankDecide(tx, "ignore", {
      note: COPY[lang].bankPurposes[purpose.value], purpose: purpose.value,
    }), "secondary"));
  } else {
    side.append(text("small", tx.status === "matched"
      ? fill(t(tx.matched_by === "auto" ? "bankMatchedAuto" : "bankMatchedManual"), { what: tx.invoice_number || t("bankDocument") })
      : t("bankIgnored") + (tx.purpose ? " · " + COPY[lang].bankPurposes[tx.purpose] : "")));
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
  renderRegister();
}
// CR-13: statement register per account — files, periods, balances, gaps, monthly coverage.
function renderRegister() {
  const reg = bankState.register,
    box = $("statement-register"),
    grid = $("statement-coverage"),
    warn = $("statement-breaks");
  box.replaceChildren();
  grid.replaceChildren();
  warn.replaceChildren();
  if (!reg) return;
  for (const item of reg.items) {
    const row = text("li", "", "statement-row");
    row.append(
      text("strong", (item.account || t("bankUnknownAccount")) + (item.statement_no ? " · č. " + item.statement_no : "")),
      text("span", [item.period_from && item.period_to ? czDate(item.period_from) + " – " + czDate(item.period_to) : "",
        item.opening_balance !== null ? czk(item.opening_balance) + " → " + czk(item.closing_balance) : "",
        fill(t("bankRows"), { n: item.rows })].filter(Boolean).join(" · ")),
      button(t("download"), () => run(() => downloadStatement(item)), "secondary"),
    );
    box.append(row);
  }
  if (!reg.items.length) box.append(text("li", t("bankEmpty"), "muted"));
  for (const b of reg.breaks)
    warn.append(text("li", b.kind === "gap"
      ? fill(t("statementGap"), { account: b.account || "—", from: czDate(b.missing_from), to: czDate(b.missing_to) })
      : fill(t("statementBalanceBreak"), { account: b.account || "—", closing: czk(b.closing), opening: czk(b.opening) })));
  for (const account of bankState.cover?.accounts || []) {
    const line = text("div", "", "coverage-row");
    line.append(text("strong", account.account || t("bankUnknownAccount")));
    for (const m of account.months) {
      const cell = text("span", m.month.slice(5) + "/" + m.month.slice(2, 4), "coverage-cell " + m.state);
      cell.title = COPY[lang].coverageStates[m.state] + (m.missing_days ? " · " + fill(t("missingDays"), { n: m.missing_days }) : "");
      line.append(cell);
    }
    grid.append(line);
  }
  const p = bankState.payouts;
  if (p)
    $("payout-summary").textContent = fill(t("payoutSummary"), {
      sales: czk(p.card_sales), payouts: czk(p.payouts), diff: czk(p.difference),
      share: p.difference_share === null ? "—" : (Number(p.difference_share) * 100).toFixed(2).replace(".", ",") + " %",
    });
}
async function downloadStatement(item) {
  const blob = await request(base() + "/bank/imports/" + encodeURIComponent(item.id) + "/file", { blob: true }),
    url = URL.createObjectURL(blob),
    a = document.createElement("a");
  a.href = url;
  a.download = item.filename || "statement";
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
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
  bankState.register = null;
  bankState.cover = null;
  bankState.payouts = null;
  $("payout-month").value = "";
  $("payout-summary").textContent = "";
  $("bank-tab").hidden = true;
  if (!$("bank-view").hidden) setTab("tasks");
  $("bank-list").replaceChildren();
  for (const id of ["statement-register", "statement-coverage", "statement-breaks"]) $(id).replaceChildren();
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
$("payout-month").onchange = () => run(loadBank);
