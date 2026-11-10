// Lucian UX/UI Prompt #011 · MIT License (c) 2026 Seokwoooo · https://lucianlabs.dev/uxui-prompt/#011
"use strict";
// Quick create (#011): the "+" turns into a close button and four create actions fan out.
// Each action opens the existing form for it (it does not create anything by itself):
// upload a document, a new issued invoice, import a bank statement, record a shift.
// An action shows only when the signed-in role can already reach that form.
(function () {
  const root = $("quick-create"),
    spacer = $("quick-create-spacer"),
    fab = root.querySelector(".u011-fab"),
    items = [...root.querySelectorAll(".u011-it")],
    note = root.querySelector(".u011-note"),
    noteT = note.querySelector("span"),
    rm = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  let timer = 0;
  const ACTIONS = {
    upload: {
      tab: "docs-tab",
      ready: () => ["owner", "employee"].includes(state.role),
      go: () => $("upload-file").focus(),
      done: "quickUploadDone",
    },
    invoice: { tab: "invoices-tab", go: () => $("new-invoice").click(), done: "quickInvoiceDone" },
    statement: { tab: "bank-tab", go: () => $("bank-file").focus(), done: "quickStatementDone" },
    shift: { tab: "staff-tab", go: () => $("shift-staff").focus(), done: "quickShiftDone" },
  };
  const available = (it) => {
    const a = ACTIONS[it.dataset.action];
    return !!state.org && !$(a.tab).hidden && (!a.ready || a.ready());
  };
  const shown = () => items.filter((it) => !it.hidden);
  function setOpen(v) {
    root.classList.toggle("is-open", v);
    fab.setAttribute("aria-expanded", String(v));
    fab.setAttribute("aria-label", t(v ? "quickClose" : "quickOpen"));
    items.forEach((it) => (it.tabIndex = v && !it.hidden ? 0 : -1));
    if (v) note.classList.remove("is-on");
  }
  // Which actions this role can use right now; no action at all hides the button.
  function refresh() {
    items.forEach((it) => (it.hidden = !available(it)));
    const any = shown().length > 0;
    root.hidden = !any;
    spacer.hidden = !any;
    if (!any && root.classList.contains("is-open")) setOpen(false);
    else setOpen(root.classList.contains("is-open"));
  }
  setOpen(false);
  refresh();
  fab.addEventListener("click", () => {
    refresh();
    setOpen(!root.classList.contains("is-open"));
  });
  items.forEach((it) => {
    it.addEventListener("click", () => {
      it.classList.remove("is-picked");
      void it.offsetWidth;
      it.classList.add("is-picked");
      clearTimeout(timer);
      timer = setTimeout(() => {
        if (!root.isConnected) return;
        setOpen(false);
        const a = ACTIONS[it.dataset.action];
        if (!available(it)) return refresh();
        $(a.tab).click();
        a.go();
        noteT.textContent = t(a.done);
        note.classList.add("is-on");
        timer = setTimeout(() => {
          if (root.isConnected) note.classList.remove("is-on");
        }, 1800);
      }, rm ? 0 : 260);
    });
    it.addEventListener("keydown", (e) => {
      const d =
        e.key === "ArrowRight" || e.key === "ArrowDown" ? 1 : e.key === "ArrowLeft" || e.key === "ArrowUp" ? -1 : 0;
      if (!d) return;
      e.preventDefault();
      const list = shown(),
        i = list.indexOf(it);
      list.at((i + d + list.length) % list.length).focus();
    });
  });
  root.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && root.classList.contains("is-open")) {
      e.preventDefault();
      setOpen(false);
      fab.focus();
    }
  });
  document.addEventListener("pointerdown", (e) => {
    if (root.isConnected && root.classList.contains("is-open") && !root.contains(e.target)) setOpen(false);
  });
  // Roles and companies change without a page load: follow the tabs and the role badge.
  const watch = new MutationObserver(refresh);
  watch.observe(document.querySelector(".workspace-tabs"), { attributes: true, subtree: true, attributeFilter: ["hidden"] });
  watch.observe($("role-badge"), { childList: true, characterData: true, subtree: true });
  $("language").addEventListener("change", () => setOpen(root.classList.contains("is-open")));
})();
