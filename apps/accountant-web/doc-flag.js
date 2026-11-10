// Lucian UX/UI Prompt #012 · MIT License (c) 2026 Seokwoooo · https://lucianlabs.dev/uxui-prompt/#012
"use strict";
// Review ribbon (#012) in the document dialog: the owner or the accountant marks a document
// "to look at again". The number beside it is how many documents of the company are marked.
// The mark is stored on the server (PUT …/documents/{id}/flag), so the whole team sees it.
(function () {
  const root = $("doc-flag"),
    btn = root.querySelector(".u012-btn"),
    num = root.querySelector(".u012-num"),
    roll = root.querySelector(".u012-roll"),
    dialog = $("extract-dialog"),
    rm = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  // One gradient id per page; the dialog exists once, but keep the original's unique id.
  const gid = "u012-g-" + Math.random().toString(36).slice(2, 7);
  root.querySelector("linearGradient").id = gid;
  root.querySelector(".u012-in").style.fill = "url(#" + gid + ")";
  const flag = { doc: null, on: false, count: 0, ticket: 0, busy: false };
  let timer = 0;
  function fitRoll(on) {
    roll.style.width = roll.children[on ? 1 : 0].offsetWidth + "px";
  }
  function paint() {
    root.classList.toggle("is-on", flag.on);
    btn.setAttribute("aria-pressed", String(flag.on));
    btn.setAttribute("aria-label", t(flag.on ? "flagUnset" : "flagSet"));
    num.textContent = fill(t("flagCount"), { n: flag.count });
    fitRoll(flag.on);
  }
  const url = (doc) => base() + "/documents/" + encodeURIComponent(doc) + "/flag";
  async function load() {
    const x = state.extract;
    root.hidden = true;
    if (!dialog.open || !x || !FINANCE_ROLES.includes(state.role)) return;
    const ticket = ++flag.ticket,
      body = await request(url(x.doc));
    if (ticket !== flag.ticket || state.extract !== x) return;
    Object.assign(flag, { doc: x.doc, on: body.flagged, count: body.flagged_count });
    root.classList.remove("is-burst");
    root.hidden = false;
    paint();
  }
  btn.addEventListener("click", () =>
    run(async () => {
      if (flag.busy || !flag.doc) return;
      const on = !flag.on,
        ticket = ++flag.ticket,
        doc = flag.doc;
      flag.busy = true;
      // Show the change at once, as the original does; the server answer then sets the count.
      flag.on = on;
      flag.count += on ? 1 : -1;
      paint();
      root.classList.remove("is-burst");
      clearTimeout(timer);
      if (on && !rm) {
        void root.offsetWidth;
        root.classList.add("is-burst");
        timer = setTimeout(() => root.classList.remove("is-burst"), 900);
      }
      try {
        const body = await request(url(doc), json("PUT", { flagged: on }));
        if (ticket === flag.ticket && flag.doc === doc) {
          Object.assign(flag, { on: body.flagged, count: body.flagged_count });
          paint();
        }
        if (FINANCE_ROLES.includes(state.role)) loadDocs().catch(() => {});
      } catch (error) {
        if (ticket === flag.ticket && flag.doc === doc) await load().catch(() => {});
        throw error;
      } finally {
        flag.busy = false;
      }
    }, btn),
  );
  new MutationObserver(() => {
    if (dialog.open) run(load);
    else {
      flag.ticket++;
      flag.doc = null;
      root.hidden = true;
    }
  }).observe(dialog, { attributes: true, attributeFilter: ["open"] });
  $("language").addEventListener("change", () => {
    if (!root.hidden) paint();
  });
})();
