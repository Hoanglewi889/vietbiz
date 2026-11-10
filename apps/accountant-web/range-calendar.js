// Lucian UX/UI Prompt #030 · MIT License (c) 2026 Seokwoooo · https://lucianlabs.dev/uxui-prompt/#030
"use strict";
// Date range calendar (#030) for the document archive: pick the first day, move the pointer and
// the band follows, pick the last day and it holds (the same day twice is a one-day range). "Apply" filters the archive by issue date
// (date_from / date_to). Days after today are the disabled ones; months before are open.
// The "flagged only" switch (#012) sits in the same row and is cleared with the filters.
(function () {
  const root = $("range-calendar"),
    bar = $("archive-extra"),
    details = $("range-filter"),
    view = root.querySelector(".u030-view"),
    mEl = root.querySelector(".u030-m"),
    wk = root.querySelector(".u030-wk"),
    pA = root.querySelector(".u030-a"),
    pB = root.querySelector(".u030-b"),
    pills = root.querySelectorAll(".u030-pill"),
    sum = root.querySelector(".u030-sum"),
    ok = root.querySelector(".u030-ok"),
    nav = root.querySelectorAll(".u030-nav button"),
    rm = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const WEEK = { vi: ["T2", "T3", "T4", "T5", "T6", "T7", "CN"], cs: ["Po", "Út", "St", "Čt", "Pá", "So", "Ne"] };
  const today = () => {
    const [y, m, d] = pragueToday().split("-").map(Number);
    return key(y, m - 1, d);
  };
  // A day is the number yyyy·10000 + month(0-11)·100 + day, so days compare as numbers.
  const key = (y, m, d) => y * 10000 + m * 100 + d;
  const parts = (k) => [Math.floor(k / 10000), Math.floor(k / 100) % 100, k % 100];
  const utc = (k) => {
    const [y, m, d] = parts(k);
    return new Date(Date.UTC(y, m, d));
  };
  const fromUtc = (dt) => key(dt.getUTCFullYear(), dt.getUTCMonth(), dt.getUTCDate());
  const iso = (k) => utc(k).toISOString().slice(0, 10);
  const fromIso = (s) => {
    const [y, m, d] = s.split("-").map(Number);
    return key(y, m - 1, d);
  };
  const weekday = (k) => WEEK[lang].at((utc(k).getUTCDay() + 6) % 7);
  const short = (k) => {
    const [y, m, d] = parts(k);
    return d + "." + (m + 1) + "." + y + " (" + weekday(k) + ")";
  };
  const dayMonth = (k) => {
    const [, m, d] = parts(k);
    return d + "." + (m + 1) + ".";
  };
  const fullLabel = (k) =>
    new Intl.DateTimeFormat(lang === "cs" ? "cs-CZ" : "vi-VN", { dateStyle: "full", timeZone: "UTC" }).format(utc(k));
  const monthLabel = (y, m) => {
    const s = new Intl.DateTimeFormat(lang === "cs" ? "cs-CZ" : "vi-VN", {
      month: "long",
      year: "numeric",
      timeZone: "UTC",
    }).format(new Date(Date.UTC(y, m, 1)));
    return s.charAt(0).toUpperCase() + s.slice(1);
  };
  const now = parts(today());
  let cur = { y: now[0], m: now[1] },
    start = null,
    end = null,
    hover = null,
    focusKey = null,
    grid = null,
    flash = 0;

  function build(dir) {
    const TODAY = today(),
      g = text("div", "", "u030-grid");
    g.setAttribute("role", "grid");
    const first = (new Date(Date.UTC(cur.y, cur.m, 1)).getUTCDay() + 6) % 7,
      n = new Date(Date.UTC(cur.y, cur.m + 1, 0)).getUTCDate();
    for (let i = 0; i < 42; i++) {
      const c = text("div", "", "u030-cell");
      c.setAttribute("role", "gridcell");
      const d = i - first + 1;
      if (d >= 1 && d <= n) {
        const k = key(cur.y, cur.m, d),
          b = text("button", String(d), "u030-d");
        b.type = "button";
        b.dataset.k = k;
        b.tabIndex = -1;
        b.setAttribute("aria-label", fullLabel(k));
        if (k > TODAY) {
          b.classList.add("off");
          b.disabled = true;
        }
        if (k === TODAY) b.classList.add("today");
        c.append(b);
      }
      g.append(c);
    }
    const old = grid;
    grid = g;
    if (old && dir && !rm) {
      g.style.transform = "translateX(" + dir * 100 + "%)";
      g.style.opacity = "0";
      view.append(g);
      void g.offsetWidth;
      g.style.transform = "none";
      g.style.opacity = "1";
      old.style.transform = "translateX(" + -dir * 100 + "%)";
      old.style.opacity = "0";
      setTimeout(() => old.remove(), 460);
    } else {
      if (old) old.remove();
      view.replaceChildren(g);
    }
    const s = mEl.lastElementChild,
      ns = text("span", monthLabel(cur.y, cur.m));
    if (dir && !rm && s) {
      ns.style.transform = "translateY(" + dir * 100 + "%)";
      ns.style.opacity = "0";
      mEl.append(ns);
      void ns.offsetWidth;
      ns.style.transform = "none";
      ns.style.opacity = "1";
      s.style.transform = "translateY(" + -dir * 100 + "%)";
      s.style.opacity = "0";
      setTimeout(() => s.remove(), 460);
    } else mEl.replaceChildren(ns);
    nav[1].setAttribute("aria-disabled", String(key(cur.y, cur.m, 1) >= key(now[0], now[1], 1)));
    paint();
    roving();
  }
  function paint() {
    let lo = start,
      hi = end !== null ? end : start !== null && hover !== null ? hover : null;
    if (lo !== null && hi !== null && hi < lo) [lo, hi] = [hi, lo];
    for (const c of grid.children) {
      const b = c.firstChild,
        k = b ? +b.dataset.k : null;
      c.classList.toggle("s", k !== null && k === (hi === null ? start : lo));
      c.classList.toggle("e", k !== null && hi !== null && k === hi);
      c.classList.toggle("in", k !== null && hi !== null && k >= lo && k <= hi);
      if (b) b.setAttribute("aria-selected", String(k === start || k === end));
    }
  }
  function roving() {
    const btns = [...grid.querySelectorAll(".u030-d:not(:disabled)")];
    const target =
      btns.find((b) => +b.dataset.k === focusKey) || btns.find((b) => +b.dataset.k === start) || btns[0];
    btns.forEach((b) => (b.tabIndex = b === target ? 0 : -1));
    return target;
  }
  function summary() {
    pA.textContent = start ? short(start) : t("rangePick");
    pA.classList.toggle("ph", !start);
    pB.textContent = end ? short(end) : t("rangePick");
    pB.classList.toggle("ph", !end);
    pills[0].classList.toggle("on", !start || !!end);
    pills[1].classList.toggle("on", !!start && !end);
    if (start && end) {
      // Documents are counted by day, both ends included.
      const days = Math.round((utc(end) - utc(start)) / 86400000) + 1;
      sum.replaceChildren(
        text("b", fill(t("rangeDays"), { n: days })),
        document.createTextNode(" · " + dayMonth(start) + " – " + dayMonth(end)),
      );
    } else sum.textContent = t(start ? "rangeHintEnd" : "rangeHintStart");
    ok.setAttribute("aria-disabled", String(!(start && end)));
  }
  // What the archive is filtered by now (it may differ from a range still being picked).
  function current() {
    const from = $("f-from").value,
      to = $("f-to").value;
    $("range-current").textContent = from && to ? dayMonth(fromIso(from)) + " – " + dayMonth(fromIso(to)) + to.slice(0, 4) : t("rangeAll");
    $("range-clear").hidden = !(from && to);
  }
  function pick(k) {
    if (start === null || end !== null) {
      start = k;
      end = null;
    } else if (k === start) end = k; // a second click on the first day: that one day
    else {
      end = Math.max(k, start);
      start = Math.min(k, start);
    }
    hover = null;
    focusKey = k;
    paint();
    summary();
    roving();
  }
  view.addEventListener("click", (e) => {
    const b = e.target.closest(".u030-d");
    if (b && !b.disabled) pick(+b.dataset.k);
  });
  view.addEventListener("pointerover", (e) => {
    const b = e.target.closest(".u030-d");
    if (b && !b.disabled && start !== null && end === null) {
      hover = +b.dataset.k;
      paint();
    }
  });
  view.addEventListener("pointerleave", () => {
    if (hover !== null) {
      hover = null;
      paint();
    }
  });
  view.addEventListener("keydown", (e) => {
    const b = e.target.closest(".u030-d");
    if (!b) return;
    const step = { ArrowLeft: -1, ArrowRight: 1, ArrowUp: -7, ArrowDown: 7 }[e.key];
    if (!step) return;
    e.preventDefault();
    const was = +b.dataset.k,
      d = utc(was);
    d.setUTCDate(d.getUTCDate() + step);
    const k = fromUtc(d);
    if (k > today()) return;
    focusKey = k;
    if (start !== null && end === null) {
      hover = focusKey;
      paint();
    }
    if (d.getUTCMonth() !== cur.m) {
      cur = { y: d.getUTCFullYear(), m: d.getUTCMonth() };
      build(k > was ? 1 : -1);
    }
    roving()?.focus();
  });
  nav.forEach((b) =>
    b.addEventListener("click", () => {
      const s = +b.dataset.step,
        d = new Date(Date.UTC(cur.y, cur.m + s, 1));
      if (key(d.getUTCFullYear(), d.getUTCMonth(), 1) > key(now[0], now[1], 1)) return;
      cur = { y: d.getUTCFullYear(), m: d.getUTCMonth() };
      build(s);
    }),
  );
  ok.addEventListener("click", () => {
    if (ok.getAttribute("aria-disabled") === "true") return;
    $("f-from").value = iso(start);
    $("f-to").value = iso(end);
    $("f-month").value = "";
    current();
    ok.textContent = t("rangeApplied");
    clearTimeout(flash);
    flash = setTimeout(() => {
      if (root.isConnected) ok.textContent = t("rangeApply");
    }, 1400);
    refilter();
  });
  $("range-clear").addEventListener("click", () => {
    clear();
    refilter();
  });
  function clear() {
    $("f-from").value = "";
    $("f-to").value = "";
    start = end = hover = null;
    paint();
    summary();
    current();
  }
  // Choosing a month replaces the range; this runs before the month's own change handler.
  $("archive-filters").addEventListener(
    "change",
    (e) => {
      if (e.target.id === "f-month" && e.target.value && $("f-from").value) clear();
    },
    true,
  );
  // Clear now, before f-clear reloads: a hidden input keeps an assigned value through reset().
  $("archive-filters").addEventListener("reset", () => {
    $("f-flagged").checked = false;
    clear();
  });
  new MutationObserver(() => (bar.hidden = $("archive-filters").hidden)).observe($("archive-filters"), {
    attributes: true,
    attributeFilter: ["hidden"],
  });
  function translateRange() {
    wk.replaceChildren(...WEEK[lang].map((w) => text("span", w)));
    nav[0].setAttribute("aria-label", t("rangePrev"));
    nav[1].setAttribute("aria-label", t("rangeNext"));
    build(0);
    summary();
    current();
  }
  $("language").addEventListener("change", translateRange);
  translateRange();
  details.addEventListener("toggle", () => {
    if (details.open) roving();
  });
})();
