"use strict";
// Phone screens for the owner in the mobile app (design "VietBiz App Design": OwnerHome).
// "Hôm nay" shows this month's money, a big capture button, what needs the owner and the latest
// cash book lines; a bottom bar switches between Today, Cash book, Capture, Invoices and Shifts.
// It only reads what the workspace already reads; the accountant keeps the desktop workspace.
const phone = { ticket: 0, data: null };
const PHONE_ROLES = ["owner", "employee"];

function phoneActive() {
  return nativeApp() && Boolean(state.org) && PHONE_ROLES.includes(state.role);
}
function phoneMonth() {
  return pragueToday().slice(0, 7);
}
function phoneApply() {
  const on = phoneActive();
  document.documentElement.classList.toggle("phone-ui", on);
  $("phone-nav").setAttribute("aria-label", t("phoneNav"));
  $("phone-nav").hidden = !on;
  const owner = state.role === "owner";
  for (const id of ["phone-nav-cash", "phone-nav-invoices", "phone-nav-staff"]) $(id).hidden = !owner;
  if (!on) {
    if (!$("home-view").hidden) setTab("tasks");
    return;
  }
  if ($("home-view").hidden && !phone.started) setTab("home");
  phone.started = true;
  phoneMarkNav();
}
function phoneMarkNav() {
  for (const [nav, view] of [["home", "home"], ["cash", "cash"], ["invoices", "invoices"], ["staff", "staff"]]) {
    const on = !$(view + "-view").hidden;
    $("phone-nav-" + nav).classList.toggle("active", on);
    if (on) $("phone-nav-" + nav).setAttribute("aria-current", "page");
    else $("phone-nav-" + nav).removeAttribute("aria-current");
  }
}
// Codex review, PR #30: nothing of one company or person stays on the phone home once the
// context changes; the home shows only data loaded for the current company and role.
function resetPhoneHome() {
  phone.ticket++;
  phone.data = null;
  renderPhoneHome();
}
async function loadPhoneHome() {
  phoneApply();
  if (!phoneActive()) return;
  const ticket = ++phone.ticket,
    org = state.org,
    month = phoneMonth(),
    owner = state.role === "owner";
  const [report, cash, waiting, deadlines] = await Promise.all([
    owner ? request(base() + "/reports/monthly?month=" + month) : null,
    owner ? request(base() + "/cashbook?month=" + month) : null,
    owner ? request(base() + "/tasks?status=WAITING_CLIENT&limit=3") : null,
    owner ? request(base() + "/deadlines?days=14") : null,
  ]);
  if (ticket !== phone.ticket || org !== state.org) return;
  phone.data = { org, role: state.role, month, report, cash, waiting, deadlines };
  renderPhoneHome();
}
function phoneRow(title, detail, colour, go) {
  const row = text("button", "", "phone-todo");
  row.type = "button";
  const dot = text("span", "", "phone-dot " + colour);
  dot.setAttribute("aria-hidden", "true");
  const body = text("span", "", "phone-todo-text");
  body.append(text("strong", title), text("small", detail));
  row.append(dot, body);
  row.onclick = go;
  return row;
}
function renderPhoneHome() {
  const d = phone.data && phone.data.org === state.org && phone.data.role === state.role ? phone.data : null;
  if (!d) {
    for (const id of ["phone-todo", "phone-recent"]) $(id).replaceChildren();
    for (const id of ["phone-left", "phone-in", "phone-out", "phone-money-title"]) $(id).textContent = "";
  }
  $("phone-date").textContent = new Intl.DateTimeFormat(lang === "cs" ? "cs-CZ" : "vi-VN", {
    weekday: "long", day: "numeric", month: "long", timeZone: "Europe/Prague",
  }).format(new Date());
  const org = state.orgs.find((o) => o.id === state.org);
  $("phone-org").textContent = org ? org.name : "";
  const owner = state.role === "owner";
  $("phone-money").hidden = !owner || !d?.report;
  $("phone-todo-section").hidden = !owner;
  $("phone-recent-section").hidden = !owner;
  if (!d || !owner || !d.report) return;
  const totals = d.report.totals.CZK || { income: "0", expense: "0" };
  const monthNo = Number(d.month.slice(5));
  $("phone-money-title").textContent = fill(t("phoneLeftThisMonth"), { month: monthNo });
  $("phone-left").textContent = money(Number(totals.income) - Number(totals.expense), "CZK");
  $("phone-in").textContent = "+" + money(totals.income, "CZK");
  $("phone-out").textContent = "−" + money(totals.expense, "CZK");
  const todo = $("phone-todo");
  todo.replaceChildren();
  const unrecorded = d.report.unrecorded_invoices;
  if (unrecorded.length) {
    const first = unrecorded[0];
    todo.append(phoneRow(fill(t("phoneUnrecorded"), { n: unrecorded.length }),
      [first.supplier_name || first.filename, money(first.total, first.currency)].join(" · "), "bad", () => phoneGo("cash")));
  }
  for (const task of d.waiting?.items || [])
    todo.append(phoneRow(t("phoneAccountantAsks") + " " + task.title, t("phoneAnswerInTask"), "warn", () => {
      setTab("tasks");
      phoneMarkNav();
      run(() => selectTask(task.id));
    }));
  const next = (d.deadlines?.items || [])[0];
  if (next)
    todo.append(phoneRow(deadlineTitle(next.code), fill(t("phoneDue"), { date: shortDate(next.due_date) }), "ok", () => phoneGo("legal")));
  if (!todo.children.length) todo.append(text("p", t("phoneNothingToDo"), "muted"));
  const recent = $("phone-recent");
  recent.replaceChildren();
  const items = (d.cash?.items || []).filter((e) => !e.voided)
    .sort((a, b) => (b.entry_date + b.id).localeCompare(a.entry_date + a.id)).slice(0, 3);
  for (const e of items) {
    const row = text("div", "", "phone-recent-row");
    const label = [e.counterparty || categoryName(e.kind, e.category), COPY[lang].methods[e.method]].filter(Boolean).join(" · ");
    row.append(text("span", label), text("strong", (e.kind === "income" ? "+" : "−") + money(e.amount, e.currency), e.kind));
    recent.append(row);
  }
  if (!items.length) recent.append(text("p", t("phoneNoEntries"), "muted"));
}
function phoneGo(view) {
  setTab(view);
  phoneMarkNav();
  window.scrollTo(0, 0);
  // Codex review, PR #30: coming back to Today reloads it, so payments, entries and answered
  // questions recorded elsewhere show at once.
  if (view === "home") run(loadPhoneHome);
}
// Capture: the phone's camera (or files on Android), then the same upload as the documents view.
function phoneCapture() {
  $("phone-capture-file").value = "";
  $("phone-capture-file").click();
}
$("phone-capture-file").onchange = () => {
  const file = $("phone-capture-file").files[0];
  if (!file) return;
  const files = new DataTransfer();
  files.items.add(file);
  $("upload-file").files = files.files;
  setTab("docs");
  phoneMarkNav();
  $("upload-form").requestSubmit();
};
$("phone-capture").onclick = phoneCapture;
$("phone-nav-capture").onclick = phoneCapture;
$("phone-nav-home").onclick = () => phoneGo("home");
$("phone-nav-cash").onclick = () => phoneGo("cash");
$("phone-nav-invoices").onclick = () => phoneGo("invoices");
$("phone-nav-staff").onclick = () => phoneGo("staff");
new MutationObserver(() => phoneApply()).observe($("role-badge"), { childList: true, characterData: true, subtree: true });
