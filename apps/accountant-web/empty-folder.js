// Lucian UX/UI Prompt #088 · MIT License (c) 2026 Seokwoooo · https://lucianlabs.dev/uxui-prompt/#088
"use strict";
// Empty task list (#088). When a company has no tasks yet (no filter set) and the role may
// create tasks, the list shows a floating folder and three templates from the accountant's
// month: collect this month's documents, reconcile the bank statement, complete the client
// profile. Choosing one creates that task through the normal API (with an Idempotency-Key);
// a sheet flies into the folder, the folder swallows it and the list opens on the new task.
// When the list becomes empty again, the folder drops back in.
const starter = { busy: false, seen: new Set() };
const STARTER_TEMPLATES = [
  {
    label: "starterDocs",
    task: "starterDocsTask",
    color: "#3D8BFF",
    icon: '<path d="M4 1.8h5.4L12.4 5v9.2H4z"/><path d="M9.4 1.8V5h3"/>',
  },
  {
    label: "starterBank",
    task: "starterBankTask",
    color: "#10B981",
    icon: '<rect x="2.6" y="2.6" width="10.8" height="10.8" rx="2.4"/><path d="M5.4 6.2h5.2M5.4 9.4h3.4"/>',
  },
  {
    label: "starterProfile",
    task: "starterProfileTask",
    color: "#FF8A3D",
    icon: '<path d="M2 4.2l4-1.8 4 1.8 4-1.8v9.4l-4 1.8-4-1.8-4 1.8z"/><path d="M6 2.4v9.4M10 4.2v9.4"/>',
  },
];
const STARTER_ART =
  '<div class="u088-fl"><svg viewBox="0 0 168 128">' +
  '<path d="M16 26a10 10 0 0 1 10-10h34a8 8 0 0 1 6 2.6l8 8.4h68a10 10 0 0 1 10 10v66a10 10 0 0 1-10 10H26a10 10 0 0 1-10-10z" fill="#0B9B70"/>' +
  '<g class="u088-pp a"><rect x="30" y="26" width="92" height="72" rx="6" fill="#EEF1F7"/><path d="M42 40h48M42 50h62M42 60h36" stroke="#C9D1DF" stroke-width="3" stroke-linecap="round"/></g>' +
  '<g class="u088-pp b"><rect x="50" y="32" width="90" height="68" rx="6" fill="#fff"/><path d="M62 46h52M62 56h64M62 66h30" stroke="#D3DAE6" stroke-width="3" stroke-linecap="round"/></g>' +
  '<g class="u088-front"><path d="M10 50a10 10 0 0 1 10-10h128a10 10 0 0 1 10 10.8l-5 52a10 10 0 0 1-10 9.2H25a10 10 0 0 1-10-9.2z" fill="#16C08C"/><path d="M22 47h124" stroke="#fff" stroke-opacity=".35" stroke-width="2" stroke-linecap="round"/><rect x="66" y="72" width="36" height="8" rx="4" fill="#fff" fill-opacity=".38"/></g>' +
  '</svg></div><span class="u088-sh"></span>';

// Called by renderTasks with the list and the number of tasks shown; true when it drew.
function renderTaskStarter(list, count) {
  if (count) {
    starter.seen.add(state.org);
    return false;
  }
  if ($("status-filter").value || $("overdue-filter").checked || $("new-task").disabled) return false;
  const root = text("div", "", "ux u088"),
    art = text("div", "", "u088-art"),
    tpl = text("div", "", "u088-tpl"),
    fly = text("span", "", "u088-fly");
  art.setAttribute("aria-hidden", "true");
  art.innerHTML = STARTER_ART;
  fly.setAttribute("aria-hidden", "true");
  tpl.setAttribute("role", "group");
  tpl.setAttribute("aria-label", t("starterGroup"));
  for (const [k, item] of STARTER_TEMPLATES.entries()) {
    const b = text("button", "");
    b.type = "button";
    const icon = text("i", "");
    icon.style.setProperty("--c", item.color);
    icon.setAttribute("aria-hidden", "true");
    icon.innerHTML = '<svg viewBox="0 0 16 16">' + item.icon + "</svg>";
    b.append(icon, document.createTextNode(t(item.label)));
    b.onclick = () => run(() => startFromTemplate(k, b, root, art, fly));
    tpl.append(b);
  }
  root.append(art, text("p", t("starterTitle"), "u088-t"), text("p", t("starterHint"), "u088-s"), tpl, fly);
  list.replaceChildren(root);
  // Back to empty after there were tasks: the folder drops in again.
  if (starter.seen.delete(state.org)) {
    art.classList.add("drop");
    setTimeout(() => art.classList.remove("drop"), 900);
  }
  return true;
}
function starterMonth() {
  const [y, m] = pragueToday().split("-");
  return m + "/" + y;
}
// The sheet flies from the button into the folder, the folder swallows it (760 ms + 1180 ms
// as in the original). Resolves when the swallow is done.
function starterFlight(from, root, art, fly, color) {
  const rr = root.getBoundingClientRect(),
    s = root.offsetWidth / rr.width,
    fr = from.getBoundingClientRect(),
    ar = art.getBoundingClientRect();
  const x0 = (fr.left + fr.width / 2 - rr.left) * s,
    y0 = (fr.top + fr.height / 2 - rr.top) * s;
  const x1 = (ar.left + ar.width / 2 - rr.left) * s,
    y1 = (ar.top + ar.height * 0.3 - rr.top) * s;
  const dx = x1 - x0,
    dy = y1 - y0;
  fly.style.setProperty("--c", color);
  fly.style.left = x0 - 13 + "px";
  fly.style.top = y0 - 16 + "px";
  art.classList.add("eat");
  fly.animate(
    [
      { transform: "translate(0,0) rotate(-10deg) scale(.5)", opacity: 0 },
      { transform: `translate(${dx * 0.45}px,${dy * 0.45 - 70}px) rotate(12deg) scale(1.1)`, opacity: 1, offset: 0.45 },
      { transform: `translate(${dx}px,${dy}px) rotate(0deg) scale(.8)`, opacity: 1, offset: 0.82 },
      { transform: `translate(${dx}px,${dy + 26}px) rotate(0deg) scale(.6)`, opacity: 0 },
    ],
    { duration: 760, easing: "cubic-bezier(.45,0,.25,1)" },
  );
  return new Promise((done) => {
    setTimeout(() => {
      art.classList.remove("eat");
      art.classList.add("gulp");
    }, 700);
    setTimeout(() => {
      art.classList.remove("gulp");
      done();
    }, 1180);
  });
}
async function startFromTemplate(k, from, root, art, fly) {
  if (starter.busy) return;
  const item = STARTER_TEMPLATES[k],
    org = state.org,
    body = {
      title: fill(t(item.task), { month: starterMonth() }),
      description: "",
      document_id: null,
      priority: "normal",
      due_date: null,
    },
    scope = "starter:" + org + ":" + k,
    buttons = [...root.querySelectorAll(".u088-tpl button")];
  starter.busy = true;
  buttons.forEach((b) => b.setAttribute("aria-disabled", "true"));
  const rm = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  try {
    const [task] = await Promise.all([
      request(base() + "/tasks", json("POST", body, retryKey(scope, body))),
      rm ? null : starterFlight(from, root, art, fly, item.color),
    ]);
    retries.delete(scope);
    if (state.org !== org) return;
    await Promise.all([loadTasks(), loadSummary()]);
    await selectTask(task.id);
    notice(fill(t("starterCreated"), { title: task.title }));
  } catch (error) {
    art.classList.remove("eat", "gulp");
    throw error;
  } finally {
    starter.busy = false;
    buttons.forEach((b) => b.removeAttribute("aria-disabled"));
  }
}
