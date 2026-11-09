"use strict";
// Spending by supplier and by category after scanning (owner / accountant).
const suppliers = { data: null, ticket: 0 };

function resetSuppliers() {
  suppliers.ticket++;
  suppliers.data = null;
  $("supplier-panel").hidden = true;
  $("supplier-list").replaceChildren();
  $("category-bars").replaceChildren();
}
async function loadSuppliers(finance) {
  const ticket = ++suppliers.ticket;
  if (!state.org || !finance) {
    resetSuppliers();
    return;
  }
  const data = await request(base() + "/suppliers");
  if (ticket !== suppliers.ticket) return;
  suppliers.data = data;
  renderSuppliers();
}
function supplierRow(title, meta, amount, share, muted = false) {
  const row = text("div", "", "supplier-row"),
    bar = text("div", "", "supplier-bar" + (muted ? " muted" : "")),
    fillEl = document.createElement("span");
  fillEl.style.width = Math.max(2, Math.round(share * 100)) + "%";
  bar.append(fillEl);
  const head = text("div", "");
  head.append(text("strong", title), document.createElement("br"), text("small", meta));
  row.append(head, text("strong", amount), bar);
  return row;
}
function renderSuppliers() {
  const data = suppliers.data;
  if (!data) return;
  $("supplier-panel").hidden = false;
  const list = $("supplier-list"),
    bars = $("category-bars");
  list.replaceChildren();
  bars.replaceChildren();
  const czk = (item) => Number(item.totals.CZK?.total || 0);
  const top = Math.max(1, ...data.items.map(czk));
  for (const item of data.items.slice(0, 8)) {
    const category = item.category ? COPY[lang].categories[item.category] : t("noCategory");
    const amounts = Object.entries(item.totals)
      .map(([cur, v]) => money(v.total, cur))
      .join(" · ");
    list.append(
      supplierRow(
        item.name || item.vat_id,
        [category, fill(t("supplierDocs"), { n: item.documents, date: item.last_date })].join(" · "),
        amounts,
        czk(item) / top,
      ),
    );
  }
  if (!data.items.length) list.append(text("p", t("noSupplierData"), "muted small"));
  // One block per currency; amounts in different currencies are never added together.
  const currencies = Object.entries(data.by_category);
  for (const [currency, totals] of currencies) {
    const cats = Object.entries(totals);
    const catTop = Math.max(1, ...cats.map(([, v]) => Number(v)));
    if (currencies.length > 1) bars.append(text("small", currency, "muted"));
    for (const [key, value] of cats)
      bars.append(
        supplierRow(
          key === "none" ? t("noCategory") : COPY[lang].categories[key] || key,
          "",
          money(value, currency),
          Number(value) / catTop,
          key === "none",
        ),
      );
  }
  if (data.uncategorised_documents)
    bars.append(text("p", fill(t("uncategorisedDocs"), { n: data.uncategorised_documents }), "muted small"));
}
