"use strict";
// Daily cash close, leakage signals and weekly cash flow (CR-12), inside the cashbook tab.
const cashControl = { data: null, flow: null, ticket: 0, closes: {}, day: null, dayTicket: 0 };

async function loadCashControl() {
  if (!state.org || !FINANCE_ROLES.includes(state.role)) return resetCashControl();
  const ticket = ++cashControl.ticket,
    month = $("cash-month").value || pragueToday().slice(0, 7);
  const [data, flow] = await Promise.all([
    request(base() + "/cash-control?month=" + encodeURIComponent(month)),
    request(base() + "/cash-flow?weeks=8"),
  ]);
  if (ticket !== cashControl.ticket) return;
  cashControl.data = data;
  cashControl.flow = flow;
  cashControl.closes = Object.fromEntries(data.days.filter((d) => d.close).map((d) => [d.date, d.close]));
  $("cash-control").hidden = false;
  if (!$("close-date").value) $("close-date").value = pragueToday();
  renderCashControl();
  await fillCloseForm();
}
// Codex review, PR #17: the form reads the chosen day from the server, whatever month the
// cashbook shows, so an existing close is always recounted with its own version.
async function fillCloseForm() {
  const day = $("close-date").value,
    ticket = ++cashControl.dayTicket;
  cashControl.day = null;
  $("close-save").disabled = true;
  if (!day || !state.org) return;
  const info = await request(base() + "/cash-closes/" + day);
  if (ticket !== cashControl.dayTicket || $("close-date").value !== day) return;
  cashControl.day = info;
  const close = info.close;
  $("close-opening").value = close ? close.opening_float : info.suggested_opening_float || "";
  $("close-counted").value = close ? close.counted_cash : "";
  $("close-note").value = close?.note || "";
  $("close-result").textContent = close ? closeResult(close) : "";
  $("close-save").textContent = t(close ? "recountTill" : "closeTill");
  $("close-save").disabled = false;
}
function closeResult(close) {
  const diff = Number(close.difference);
  return fill(t(diff < 0 ? "closeShort" : diff > 0 ? "closeOver" : "closeExact"), {
    expected: czk(close.expected_cash),
    counted: czk(close.counted_cash),
    diff: czk(Math.abs(diff).toFixed(2)),
  });
}
function renderCashControl() {
  const data = cashControl.data;
  if (!data) return;
  document.querySelectorAll(".leak-warning").forEach((n) => n.remove());
  const summary = $("leak-summary");
  summary.replaceChildren(
    statTile(t("leakShortage"), czk(data.totals.shortage.replace("-", "")), Number(data.totals.shortage) < 0),
    statTile(t("leakSurplus"), czk(data.totals.surplus), false),
    statTile(t("leakClosedDays"), String(data.totals.closed_days), false),
    statTile(t("leakMissingCloses"), String(data.totals.days_without_close.length),
      data.totals.days_without_close.length > 0),
  );
  const missing = $("leak-missing");
  missing.replaceChildren();
  $("leak-missing-hint").hidden = !data.totals.days_without_close.length;
  for (const day of data.totals.days_without_close)
    missing.append(button(czDate(day), () => run(async () => {
      $("close-date").value = day;
      await fillCloseForm();
      $("close-counted").focus();
    }), "secondary"));
  const undoc = $("leak-undocumented");
  undoc.replaceChildren();
  for (const e of data.undocumented_expenses)
    undoc.append(text("li", [czDate(e.entry_date), czk(e.amount), COPY[lang].methods?.[e.method] || e.method,
      e.counterparty || e.description || ""].filter(Boolean).join(" · ")));
  if (!data.undocumented_expenses.length) undoc.append(text("li", t("leakNoUndocumented"), "muted"));
  $("leak-undocumented-title").textContent = fill(t("leakUndocumented"), { from: czk(data.undocumented_from) });
  for (const day of data.days)
    if (day.changed_since_close)
      undoc.before(text("p", fill(t("closeChanged"), { date: czDate(day.date) }), "leak-warning"));
  renderCashFlow();
}
function statTile(label, value, alert) {
  const tile = text("div", "", "leak-tile" + (alert ? " alert" : ""));
  tile.append(text("span", label), text("strong", value));
  return tile;
}
function renderCashFlow() {
  const box = $("cash-flow"),
    weeks = cashControl.flow?.weeks || [];
  box.replaceChildren();
  const top = Math.max(1, ...weeks.map((w) => Math.max(Number(w.in), Number(w.out))));
  for (const w of weeks) {
    const row = text("div", "", "flow-row"),
      bars = text("div", "", "flow-bars"),
      inBar = document.createElement("span"),
      outBar = document.createElement("span");
    inBar.className = "flow-in";
    outBar.className = "flow-out";
    inBar.style.width = (Number(w.in) / top) * 100 + "%";
    outBar.style.width = (Number(w.out) / top) * 100 + "%";
    bars.append(inBar, outBar);
    row.append(
      text("span", fill(t("weekOf"), { date: czDate(w.week_start) }), "flow-week"),
      bars,
      text("span", (Number(w.net) >= 0 ? "+" : "") + czk(w.net), "flow-net" + (Number(w.net) < 0 ? " negative" : "")),
    );
    row.title = fill(t("flowDetail"), { in: czk(w.in), out: czk(w.out), source: COPY[lang].bankSources[w.bank_source] });
    box.append(row);
  }
}
async function saveClose() {
  const day = $("close-date").value,
    loaded = cashControl.day;
  if (!day || !$("close-counted").value.trim()) throw { messageKey: "closeNeedsCount" };
  if (!loaded || loaded.date !== day) throw { messageKey: "closeConflict" };
  const existing = loaded.close;
  let saved;
  try {
    saved = await request(base() + "/cash-closes/" + day, json("PUT", {
      opening_float: decimal($("close-opening").value || "0"),
      counted_cash: decimal($("close-counted").value),
      note: $("close-note").value.trim() || null,
      expected_version: existing ? existing.version : null,
    }));
  } catch (error) {
    if (error.status === 409) {
      await fillCloseForm();
      throw { messageKey: "closeConflict" };
    }
    throw error;
  }
  notice(closeResult(saved));
  await loadCashControl();
}
function resetCashControl() {
  cashControl.ticket++;
  cashControl.data = null;
  cashControl.flow = null;
  cashControl.closes = {};
  cashControl.day = null;
  cashControl.dayTicket++;
  $("cash-control").hidden = true;
  $("close-form").reset();
  $("close-result").textContent = "";
  for (const id of ["leak-summary", "leak-missing", "leak-undocumented", "cash-flow"]) $(id).replaceChildren();
  document.querySelectorAll(".leak-warning").forEach((n) => n.remove());
}
$("close-date").onchange = () => run(fillCloseForm);
$("close-form").onsubmit = (e) => {
  e.preventDefault();
  // run() re-enables the button afterwards; the form decides again once the day is reloaded.
  if (!$("close-save").disabled) run(saveClose);
};
