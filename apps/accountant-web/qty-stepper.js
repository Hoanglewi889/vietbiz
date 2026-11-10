// Lucian UX/UI Prompt #018 · MIT License (c) 2026 Seokwoooo · https://lucianlabs.dev/uxui-prompt/#018
"use strict";
// Quantity stepper (#018) under each issued-invoice line. "−" and "+" step the line's own
// quantity field by one, the digits roll like an odometer, and the line amount (quantity ×
// unit price) counts along. The quantity field stays the value that is saved, and it can
// still be typed: a quantity such as 2,5 kg is shown as typed instead of rolling digits.
// The amount is a preview; the invoice totals still come from the server when it is saved.
const QTY_MIN = 1,
  QTY_MAX = 99;
function attachQtyStepper(row) {
  const qty = row.querySelector('[data-key="quantity"]'),
    price = row.querySelector('[data-key="unit_price"]');
  if (!qty || !price) return;
  const rm = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  const root = text("div", "", "ux u018"),
    step = text("div", "", "u018-step"),
    mi = text("button", "", "u018-b mi"),
    pl = text("button", "", "u018-b pl"),
    numBox = text("span", "", "u018-num"),
    sr = text("span", "", "u018-sr"),
    raw = text("span", "", "u018-raw"),
    sum = text("div", "", "u018-sum"),
    sumLabel = text("small", ""),
    total = text("b", "", "u018-total");
  const cols = [text("span", "", "u018-col"), text("span", "", "u018-col")];
  step.setAttribute("role", "group");
  for (const [b, path] of [[mi, "M5 10h10"], [pl, "M10 5v10M5 10h10"]]) {
    b.type = "button";
    b.innerHTML = '<svg viewBox="0 0 20 20" aria-hidden="true"><path d="' + path + '"/></svg>';
  }
  numBox.setAttribute("aria-live", "polite");
  numBox.setAttribute("aria-atomic", "true");
  for (const c of cols) {
    c.setAttribute("aria-hidden", "true");
    for (let d = 0; d < 10; d++) c.append(text("span", String(d)));
    c.style.width = "17px";
  }
  raw.setAttribute("aria-hidden", "true");
  numBox.append(sr, ...cols, raw);
  step.append(mi, numBox, pl);
  sum.append(sumLabel, total);
  root.append(step, sum);
  row.append(root);

  const read = (input) => {
    const v = decimal(input.value);
    return v !== null && /^\d+(\.\d+)?$/.test(v) ? Number(v) : null;
  };
  const show = (n) => String(Math.round(n * 1000) / 1000).replace(".", ",");
  let shown = null,
    raf = 0;
  function countTo(target) {
    cancelAnimationFrame(raf);
    if (target === null) {
      shown = null;
      total.textContent = "—";
      return;
    }
    const from = shown ?? target,
      t0 = performance.now(),
      D = rm ? 1 : 520;
    (function f(now) {
      const x = Math.min(1, (now - t0) / D);
      shown = Math.round((from + (target - from) * (1 - Math.pow(1 - x, 3))) * 100) / 100;
      total.textContent = money(shown, "CZK");
      if (x < 1 && root.isConnected) raf = requestAnimationFrame(f);
    })(t0);
  }
  function relabel() {
    step.setAttribute("aria-label", t("quantity"));
    mi.setAttribute("aria-label", t("qtyMinus"));
    pl.setAttribute("aria-label", t("qtyPlus"));
    sumLabel.textContent = t(isPayer() ? "qtyLineBase" : "qtyLineTotal");
  }
  function render() {
    const q = read(qty),
      p = read(price),
      whole = q !== null && Number.isInteger(q) && q >= QTY_MIN && q <= QTY_MAX;
    const tens = whole ? Math.floor(q / 10) : 0,
      ones = whole ? q % 10 : 0;
    cols[0].hidden = cols[1].hidden = !whole;
    raw.hidden = whole;
    raw.textContent = q === null ? "—" : show(q);
    cols[0].style.transform = "translateY(" + -tens * 34 + "px)";
    cols[0].classList.toggle("is-hide", tens === 0);
    cols[1].style.transform = "translateY(" + -ones * 34 + "px)";
    mi.setAttribute("aria-disabled", String(q === null || q - 1 < QTY_MIN));
    pl.setAttribute("aria-disabled", String(q !== null && q + 1 > QTY_MAX));
    sr.textContent = q === null ? "—" : show(q) + " " + (row.querySelector('[data-key="unit"]')?.value || "");
    countTo(q !== null && p !== null ? Math.round(q * p * 100) / 100 : null);
  }
  function bump(d) {
    const q = read(qty) ?? 0,
      n = Math.round((q + d) * 1000) / 1000;
    if (n < QTY_MIN || n > QTY_MAX) {
      step.classList.remove("is-shake");
      void step.offsetWidth;
      step.classList.add("is-shake");
      return;
    }
    qty.value = show(n);
    qty.dispatchEvent(new Event("input", { bubbles: true }));
  }
  mi.addEventListener("click", () => bump(-1));
  pl.addEventListener("click", () => bump(1));
  step.addEventListener("keydown", (e) => {
    if (e.target !== mi && e.target !== pl) return;
    if (e.key === "ArrowUp" || e.key === "ArrowRight") {
      e.preventDefault();
      bump(1);
    }
    if (e.key === "ArrowDown" || e.key === "ArrowLeft") {
      e.preventDefault();
      bump(-1);
    }
  });
  for (const input of [qty, price, row.querySelector('[data-key="unit"]')])
    input?.addEventListener("input", render);
  root.relabel = relabel;
  relabel();
  render();
}
$("language").addEventListener("change", () => {
  for (const el of document.querySelectorAll(".u018")) el.relabel?.();
});
