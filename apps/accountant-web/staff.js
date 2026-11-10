"use strict";
// Staff, shifts and tips (CR-12): who worked when, hours, labour cost and tips per week,
// with Labour Code prompts. Only a display name, job, rate and an under-18 flag are kept.
const staffState = { people: [], period: null, ticket: 0 };

function weekBounds(iso) {
  const day = new Date(iso + "T00:00:00Z"),
    monday = new Date(day);
  monday.setUTCDate(day.getUTCDate() - ((day.getUTCDay() + 6) % 7));
  const sunday = new Date(monday);
  sunday.setUTCDate(monday.getUTCDate() + 6);
  return [monday.toISOString().slice(0, 10), sunday.toISOString().slice(0, 10)];
}
async function loadStaff() {
  const ticket = ++staffState.ticket;
  $("staff-tab").hidden = !FINANCE_ROLES.includes(state.role);
  if ($("staff-tab").hidden) {
    if (!$("staff-view").hidden) setTab("tasks");
    return;
  }
  if (!$("staff-week").value) $("staff-week").value = pragueToday();
  if (!$("shift-date").value) $("shift-date").value = pragueToday();
  const [from, to] = weekBounds($("staff-week").value);
  const [people, period] = await Promise.all([
    request(base() + "/staff"),
    request(base() + "/shifts?from=" + from + "&to=" + to),
  ]);
  if (ticket !== staffState.ticket) return;
  staffState.people = people.items;
  staffState.period = period;
  renderStaff();
}
const hoursText = (minutes) => (minutes / 60).toLocaleString(lang === "cs" ? "cs-CZ" : "vi-VN", { maximumFractionDigits: 2 }) + " h";
function findingText(f) {
  return fill(COPY[lang].shiftFindings[f.code] || f.code, {
    hours: hoursText(f.minutes || 0),
    limit: hoursText(f.limit || 0),
    after: hoursText(f.after || 0),
    breakMinutes: f.break_minutes ?? 0,
  });
}
function renderStaff() {
  const people = $("staff-people"),
    pick = $("shift-staff"),
    keep = pick.value;
  people.replaceChildren();
  pick.replaceChildren(option("", t("chooseStaff")));
  for (const p of staffState.people) {
    const row = text("li", "", "staff-person" + (p.active ? "" : " inactive"));
    row.append(
      text("strong", p.display_name),
      text("small", [p.job, p.hourly_rate ? czk(p.hourly_rate) + "/h" : t("noRate"), p.minor ? t("minorShort") : "",
        p.active ? "" : t("inactive")].filter(Boolean).join(" · ")),
      button(t(p.active ? "deactivate" : "activate"), () => run(async () => {
        await request(base() + "/staff/" + encodeURIComponent(p.id), json("PUT", {
          display_name: p.display_name, job: p.job, hourly_rate: p.hourly_rate, minor: p.minor,
          active: !p.active, expected_version: p.version,
        }));
        await loadStaff();
      }), "secondary"),
    );
    people.append(row);
    if (p.active) pick.append(option(p.id, p.display_name));
  }
  if (!staffState.people.length) people.append(text("li", t("noStaff"), "muted"));
  if ([...pick.options].some((o) => o.value === keep)) pick.value = keep;
  const period = staffState.period,
    summary = $("shift-summary"),
    list = $("shift-list");
  summary.replaceChildren();
  list.replaceChildren();
  if (!period) return;
  $("shift-period").textContent = fill(t("shiftPeriod"), { from: czDate(period.from), to: czDate(period.to) });
  for (const s of period.summary) {
    const row = text("tr", "");
    row.append(text("td", s.display_name), text("td", String(s.shifts)), text("td", hoursText(s.minutes)),
      text("td", s.labour_cost ? czk(s.labour_cost) : "—"), text("td", czk(s.tips)),
      text("td", s.findings ? "⚠ " + s.findings : ""));
    summary.append(row);
  }
  const total = text("tr", "", "total");
  total.append(text("td", t("staffTotal")), text("td", ""), text("td", hoursText(period.totals.minutes)),
    text("td", czk(period.totals.labour_cost)), text("td", czk(period.totals.tips)), text("td", ""));
  if (period.summary.length) summary.append(total);
  $("shift-unpriced").textContent = period.totals.unpriced_staff.length
    ? fill(t("unpricedStaff"), { names: period.totals.unpriced_staff.join(", ") }) : "";
  const names = Object.fromEntries(staffState.people.map((p) => [p.id, p.display_name]));
  for (const shift of period.items) {
    const item = text("li", "", "shift-item" + (shift.voided_at ? " voided" : shift.findings.length ? " flagged" : ""));
    item.append(
      text("strong", czDate(shift.work_date) + " · " + (names[shift.staff_id] || "—")),
      text("span", shift.start_time + "–" + shift.end_time + " · " + fill(t("breakShort"), { m: shift.break_minutes }) +
        " · " + hoursText(shift.worked_minutes) + " · tip " + czk(shift.tips)),
    );
    for (const f of shift.findings) {
      const note = text("p", findingText(f) + " ", "shift-finding");
      if (f.source) {
        const link = text("a", t("source"));
        link.href = f.source;
        link.target = "_blank";
        link.rel = "noopener noreferrer";
        note.append(link);
      }
      item.append(note);
    }
    if (shift.voided_at) item.append(text("small", t("voided") + ": " + shift.void_reason));
    else
      item.append(button(t("voidShift"), () => run(async () => {
        await request(base() + "/shifts/" + encodeURIComponent(shift.id) + "/void",
          json("POST", { reason: t("voidShiftReason") }));
        await loadStaff();
      }), "secondary"));
    list.append(item);
  }
  if (!period.items.length) list.append(text("li", t("noShifts"), "muted"));
}
async function addPerson() {
  const name = $("staff-name").value.trim();
  if (!name) throw { messageKey: "staffNeedsName" };
  await request(base() + "/staff", json("POST", {
    display_name: name,
    job: $("staff-job").value.trim() || null,
    hourly_rate: $("staff-rate").value.trim() ? decimal($("staff-rate").value) : null,
    minor: $("staff-minor").checked,
  }));
  $("staff-form").reset();
  notice(t("saved"));
  await loadStaff();
}
async function addShift() {
  if (!$("shift-staff").value) throw { messageKey: "chooseStaffFirst" };
  const body = {
    staff_id: $("shift-staff").value,
    work_date: $("shift-date").value,
    start_time: $("shift-start").value,
    end_time: $("shift-end").value,
    break_minutes: Number($("shift-break").value || 0),
    tips: $("shift-tips").value.trim() ? decimal($("shift-tips").value) : "0",
    note: null,
  };
  // Codex review, PR #17: the same key until it succeeds, so a retry after a lost response
  // returns the first shift instead of recording a second one.
  const scope = "shift:" + state.org;
  await request(base() + "/shifts", json("POST", body, retryKey(scope, body)));
  retries.delete(scope);
  $("staff-week").value = $("shift-date").value;
  $("shift-tips").value = "";
  notice(t("saved"));
  await loadStaff();
}
function resetStaff() {
  staffState.ticket++;
  staffState.people = [];
  staffState.period = null;
  $("staff-tab").hidden = true;
  if (!$("staff-view").hidden) setTab("tasks");
  for (const id of ["staff-people", "shift-summary", "shift-list"]) $(id).replaceChildren();
  $("staff-form").reset();
  $("shift-form").reset();
  $("shift-date").value = pragueToday();
  $("staff-week").value = "";
  $("shift-unpriced").textContent = "";
  $("shift-period").textContent = "";
}
$("staff-tab").onclick = () => setTab("staff");
$("staff-week").onchange = () => run(loadStaff);
$("staff-form").onsubmit = (e) => {
  e.preventDefault();
  run(addPerson, $("staff-add"));
};
$("shift-form").onsubmit = (e) => {
  e.preventDefault();
  run(addShift, $("shift-add"));
};
$("shift-date").value = pragueToday();
