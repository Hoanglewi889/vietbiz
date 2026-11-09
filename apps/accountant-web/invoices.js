"use strict";
// Issued invoices (CR-5). Uses the shared helpers and state from app.js.
// The server computes every amount; the page never rounds money itself.
const PROFILE_FIELDS = ["legal_name", "address", "ico", "dic", "iban", "register_note"];
const CUSTOMER_FIELDS = [
  "customer_name",
  "customer_address",
  "customer_ico",
  "customer_dic",
  "issue_date",
  "supply_date",
  "due_date",
  "payment_method",
  "note",
];
const inv = { profile: null, items: [], editing: null, ticket: 0, threshold: null };

const addDays = (iso, days) => {
  const d = new Date(iso + "T12:00:00Z");
  d.setUTCDate(d.getUTCDate() + days);
  return d.toISOString().slice(0, 10);
};
const isPayer = () => !!inv.profile?.vat_payer;

function resetInvoices() {
  inv.ticket++;
  inv.profile = null;
  inv.items = [];
  inv.editing = null;
  $("invoices-tab").hidden = true;
  if (!$("invoices-view").hidden) setTab("tasks");
  $("billing-form").reset();
  $("invoice-form").reset();
  $("invoice-form").hidden = true;
  $("invoice-list").replaceChildren();
  $("billing-error").textContent = "";
  inv.threshold = null;
  $("vat-threshold").hidden = true;
  if ($("print-dialog").open) $("print-dialog").close();
}
async function loadInvoices() {
  $("invoices-tab").hidden = !FINANCE_ROLES.includes(state.role);
  if ($("invoices-tab").hidden && !$("invoices-view").hidden) setTab("tasks");
  if (!state.org || $("invoices-tab").hidden) return;
  const ticket = ++inv.ticket;
  const [profile, list, threshold] = await Promise.all([
    request(base() + "/billing-profile"),
    request(base() + "/invoices"),
    request(base() + "/vat-threshold"),
  ]);
  if (ticket !== inv.ticket) return;
  inv.profile = profile.profile;
  inv.items = list.items;
  inv.threshold = threshold;
  renderThreshold();
  fillProfile();
  renderInvoices();
}
function fillProfile() {
  const p = inv.profile || {};
  for (const key of PROFILE_FIELDS) $("b-" + key).value = p[key] || "";
  $("b-vat_payer").checked = !!p.vat_payer;
  $("billing-details").open = !inv.profile;
}
async function saveProfile() {
  $("billing-error").textContent = "";
  const body = { vat_payer: $("b-vat_payer").checked };
  for (const key of PROFILE_FIELDS) body[key] = $("b-" + key).value.trim() || null;
  try {
    const saved = await request(base() + "/billing-profile", json("PUT", body));
    inv.profile = saved.profile;
  } catch (error) {
    if (error.status === 422) $("billing-error").textContent = t("validation");
    throw error;
  }
  $("billing-details").open = false;
  renderInvoiceLines(readInvoiceLines());
  notice(t("saved"));
}

// Editor
function renderPaymentOptions() {
  const sel = $("i-payment_method"),
    chosen = sel.value;
  sel.replaceChildren(
    ...["bank", "cash", "card"].map((m) => option(m, COPY[lang].methods[m])),
  );
  sel.value = chosen || "bank";
}
function invoiceLine(line = {}) {
  const row = text("div", "", "invoice-line");
  const field = (key, title, attrs = {}) => {
    const input = document.createElement("input");
    input.dataset.key = key;
    input.autocomplete = "off";
    Object.assign(input, attrs, { value: line[key] ?? attrs.value ?? "" });
    return label(title, input);
  };
  const rate = document.createElement("select");
  rate.dataset.key = "vat_rate";
  rate.append(option("21", "21 %"), option("12", "12 %"));
  rate.value = line.vat_rate || "21";
  const rateLabel = label(t("rate"), rate);
  rateLabel.classList.add("vat-only");
  rateLabel.hidden = !isPayer();
  const remove = text("button", "×", "icon-button");
  remove.type = "button";
  remove.setAttribute("aria-label", t("removeLine"));
  remove.onclick = () => {
    row.remove();
    if (!$("i-lines").children.length) $("i-lines").append(invoiceLine());
  };
  row.append(
    field("description", t("subject"), { maxLength: 200 }),
    field("quantity", t("quantity"), { inputMode: "decimal", value: "1" }),
    field("unit", t("unit"), { maxLength: 10, value: "ks" }),
    field("unit_price", isPayer() ? t("unitPrice") : t("unitPricePlain"), {
      inputMode: "decimal",
    }),
    rateLabel,
    remove,
  );
  row.querySelector('[data-key="description"]').parentElement.classList.add("grow");
  return row;
}
function renderInvoiceLines(lines) {
  $("i-lines").replaceChildren(...(lines.length ? lines : [{}]).map(invoiceLine));
}
function readInvoiceLines() {
  return [...$("i-lines").querySelectorAll(".invoice-line")].map((row) => {
    const get = (key) => row.querySelector(`[data-key="${key}"]`).value.trim();
    return {
      description: get("description"),
      quantity: decimal(get("quantity")) || "",
      unit: get("unit") || "ks",
      unit_price: decimal(get("unit_price")) || "",
      vat_rate: isPayer() ? get("vat_rate") : null,
    };
  });
}
function readInvoice() {
  const body = {};
  for (const key of CUSTOMER_FIELDS) body[key] = $("i-" + key).value.trim() || null;
  body.payment_method = body.payment_method || "bank";
  body.lines = readInvoiceLines();
  return body;
}
function openInvoiceEditor(invoice = null) {
  inv.editing = invoice;
  $("invoice-error").textContent = "";
  renderPaymentOptions();
  const today = pragueToday(),
    c = invoice?.content || {
      issue_date: today,
      supply_date: today,
      due_date: addDays(today, 14),
      payment_method: "bank",
    };
  for (const key of CUSTOMER_FIELDS) $("i-" + key).value = c[key] || "";
  renderInvoiceLines(c.lines || []);
  renderEditorTotals();
  $("invoice-form").hidden = false;
  $("i-customer_name").focus();
}
function closeInvoiceEditor() {
  inv.editing = null;
  $("invoice-form").reset();
  $("invoice-form").hidden = true;
}
function totalsBlock(totals) {
  const box = text("div", "");
  const rows = totals.vat_payer
    ? totals.rates.map((r) => [
        `${t("base")} ${r.rate} % · ${t("tax")}`,
        money(r.base, "CZK") + " · " + money(r.tax, "CZK"),
      ])
    : [];
  rows.push([t("total"), money(totals.total, "CZK")]);
  const list = document.createElement("dl");
  for (const [k, v] of rows) list.append(text("dt", k), text("dd", v));
  box.append(list);
  return box;
}
function renderEditorTotals() {
  const box = $("i-totals");
  box.replaceChildren();
  if (inv.editing) box.append(totalsBlock(inv.editing.totals));
}
async function saveInvoice() {
  $("invoice-error").textContent = "";
  const body = readInvoice();
  try {
    if (inv.editing) {
      inv.editing = await request(
        base() + "/invoices/" + encodeURIComponent(inv.editing.id),
        json("PUT", { ...body, version: inv.editing.version }),
      );
    } else {
      const scope = "invoice:" + state.org;
      inv.editing = await request(
        base() + "/invoices",
        json("POST", body, retryKey(scope, body)),
      );
      retries.delete(scope);
    }
  } catch (error) {
    $("invoice-error").textContent = message(error);
    throw error;
  }
  renderEditorTotals();
  await loadInvoices();
  return inv.editing;
}
const ISSUE_ERRORS = {
  billing_profile_missing: "profileMissing",
  vat_status_changed: "vatChanged",
  tax_document_incomplete: "invoiceIncomplete",
};
async function issueInvoice(invoice) {
  try {
    const issued = await request(
      base() + "/invoices/" + encodeURIComponent(invoice.id) + "/issue",
      { method: "POST" },
    );
    closeInvoiceEditor();
    await loadInvoices();
    const late = issued.totals.findings?.some((f) => f.code === "issued_after_15_days");
    notice(fill(t("invoiceIssued"), { number: issued.number }) + (late ? " — " + t("lateIssue") : ""));
    return issued;
  } catch (error) {
    const key = ISSUE_ERRORS[error.detail?.code];
    if (key) {
      $("invoice-error").textContent = t(key);
      if (key === "profileMissing") $("billing-details").open = true;
      error = { ...error, messageKey: key };
    }
    throw error;
  }
}

// CR-10: turnover against the VAT registration thresholds, for a business that is not a payer.
function renderThreshold() {
  const box = $("vat-threshold"),
    data = inv.threshold;
  box.hidden = !data || !data.applies;
  if (box.hidden) return;
  box.className = "vat-threshold " + data.status;
  const bar = text("div", "", "threshold-bar"),
    fillEl = document.createElement("span");
  fillEl.style.width = Math.min(100, Math.round(Number(data.share) * 100)) + "%";
  bar.append(fillEl);
  const link = text("a", t("source"));
  link.href = data.source;
  link.target = "_blank";
  link.rel = "noopener noreferrer";
  const note = text("small", fill(t("vatThresholdNote"), {
    invoiced: czk(data.invoiced),
    counter: czk(data.cash_and_card_sales),
    bank: czk(data.bank_income_not_added),
  }) + " ");
  note.append(link);
  box.replaceChildren(
    text("strong", fill(t("vatThresholdLine"), { year: data.year, estimate: czk(data.estimate) })),
    text("span", COPY[lang].vatThresholdStatus[data.status], "threshold-status"),
    bar,
    note,
  );
}
function translateInvoices() {
  renderPaymentOptions();
  renderThreshold();
  if (!$("invoice-form").hidden) renderInvoiceLines(readInvoiceLines());
  renderEditorTotals();
  if (state.org) renderInvoices();
}

// List
function renderInvoices() {
  const list = $("invoice-list");
  list.replaceChildren();
  for (const item of inv.items) {
    const row = text("div", "", "invoice-row"),
      info = text("div", ""),
      c = item.content;
    info.append(
      text("strong", (item.number || t("draft")) + " · " + c.customer_name),
      text(
        "small",
        [c.issue_date, t(item.status === "issued" ? "issued" : "draft")].join(" · "),
      ),
    );
    row.append(info, text("span", money(item.totals.total, "CZK"), "cash-amount"));
    if (item.status === "draft") {
      row.append(
        button(t("editDraft"), () => openInvoiceEditor(item)),
        button(t("issueInvoice"), () => issueInvoice(item), "primary"),
        button(t("deleteDraft"), async () => {
          await request(base() + "/invoices/" + encodeURIComponent(item.id), {
            method: "DELETE",
          });
          if (inv.editing?.id === item.id) closeInvoiceEditor();
          await loadInvoices();
        }),
      );
    } else {
      row.append(
        button(t("printInvoice"), () => showPrint(item)),
        button(t("downloadIsdoc"), () => downloadIsdoc(item)),
      );
    }
    list.append(row);
  }
  if (!inv.items.length) empty(list, t("noInvoices"));
}
async function downloadIsdoc(item) {
  const blob = await request(
    base() + "/invoices/" + encodeURIComponent(item.id) + "/isdoc",
    { blob: true },
  );
  const a = document.createElement("a");
  a.href = URL.createObjectURL(blob);
  a.download = "faktura-" + item.number + ".isdoc";
  a.click();
  setTimeout(() => URL.revokeObjectURL(a.href), 1000);
}

// Printable invoice: always Czech, the language of the customer and the tax office.
const czk = (v) =>
  new Intl.NumberFormat("cs-CZ", { style: "currency", currency: "CZK" }).format(Number(v));
const czDate = (iso) => iso.split("-").reverse().join(". ").replace(/^0/, "").replace(". 0", ". ");
const PAY_CS = { bank: "Převodem", cash: "Hotově", card: "Kartou" };
function partyBlock(title, lines) {
  const box = text("section", "", "paper-party");
  box.append(text("h3", title));
  for (const line of lines.filter(Boolean)) box.append(text("p", line));
  return box;
}
function showPrint(item) {
  const s = item.supplier,
    c = item.content,
    totals = item.totals,
    payer = totals.vat_payer,
    paper = $("invoice-print");
  paper.replaceChildren();
  const head = text("header", "", "paper-head");
  head.append(
    text("h1", (payer ? "Faktura – daňový doklad č. " : "Faktura č. ") + item.number),
  );
  const parties = text("div", "", "paper-parties");
  parties.append(
    partyBlock("Dodavatel", [
      s.legal_name,
      s.address,
      "IČO: " + s.ico,
      payer ? "DIČ: " + s.dic : "Není plátce DPH.",
      s.register_note,
    ]),
    partyBlock("Odběratel", [
      c.customer_name,
      c.customer_address,
      c.customer_ico && "IČO: " + c.customer_ico,
      c.customer_dic && "DIČ: " + c.customer_dic,
    ]),
  );
  const facts = document.createElement("dl");
  facts.className = "paper-facts";
  for (const [k, v] of [
    ["Datum vystavení", czDate(c.issue_date)],
    [payer ? "Datum uskutečnění zdanitelného plnění" : "Datum plnění", czDate(c.supply_date)],
    ["Datum splatnosti", czDate(c.due_date)],
    ["Způsob platby", PAY_CS[c.payment_method]],
    s.iban && c.payment_method === "bank" ? ["Bankovní účet (IBAN)", s.iban] : null,
    ["Variabilní symbol", item.variable_symbol],
  ].filter(Boolean))
    facts.append(text("dt", k), text("dd", v));
  const table = document.createElement("table");
  const headers = ["Popis", "Množství", payer ? "Cena/jedn. bez DPH" : "Cena/jedn.", ...(payer ? ["Sazba"] : []), payer ? "Základ" : "Celkem"];
  const thead = document.createElement("tr");
  headers.forEach((h) => thead.append(text("th", h)));
  table.append(thead);
  for (const line of totals.lines) {
    const tr = document.createElement("tr");
    [
      line.description,
      line.quantity.replace(".", ",") + " " + line.unit,
      czk(line.unit_price),
      ...(payer ? [line.vat_rate + " %"] : []),
      czk(line.net),
    ].forEach((v) => tr.append(text("td", v)));
    table.append(tr);
  }
  paper.append(head, parties, facts, table);
  if (payer) {
    const recap = document.createElement("table");
    recap.className = "paper-recap";
    const tr = document.createElement("tr");
    ["Sazba DPH", "Základ daně", "Výše DPH"].forEach((h) => tr.append(text("th", h)));
    recap.append(tr);
    for (const r of totals.rates) {
      const row = document.createElement("tr");
      [r.rate + " %", czk(r.base), czk(r.tax)].forEach((v) => row.append(text("td", v)));
      recap.append(row);
    }
    paper.append(recap);
  }
  paper.append(text("p", "Celkem k úhradě: " + czk(totals.total), "paper-total"));
  if (c.note) paper.append(text("p", c.note, "paper-note"));
  $("print-dialog").showModal();
  // CR-10: QR Platba for a bank transfer to the supplier's IBAN (server builds the SPAYD code).
  if (item.status === "issued" && c.payment_method === "bank" && s.iban) {
    const ticket = inv.ticket;
    request(base() + "/invoices/" + encodeURIComponent(item.id) + "/payment-qr")
      .then((qr) => {
        if (ticket !== inv.ticket || !$("print-dialog").open) return;
        const figure = text("figure", "", "paper-qr"),
          img = document.createElement("img");
        img.src = qr.image;
        img.alt = "QR Platba " + item.number;
        figure.append(img, text("figcaption", "QR Platba"));
        paper.append(figure);
      })
      .catch(() => {});
  }
}

$("invoices-tab").onclick = () => setTab("invoices");
$("new-invoice").onclick = () => openInvoiceEditor();
$("invoice-cancel").onclick = closeInvoiceEditor;
$("i-add-line").onclick = () => $("i-lines").append(invoiceLine());
$("billing-form").onsubmit = (e) => {
  e.preventDefault();
  run(saveProfile, $("billing-save"));
};
$("invoice-form").onsubmit = (e) => {
  e.preventDefault();
  run(saveInvoice, $("invoice-save"));
};
$("invoice-issue").onclick = () =>
  run(async () => issueInvoice(await saveInvoice()), $("invoice-issue"));
$("close-print").onclick = () => $("print-dialog").close();
$("print-now").onclick = () => window.print();
