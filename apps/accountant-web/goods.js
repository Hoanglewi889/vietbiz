"use strict";
// Goods lines on a purchase invoice and the monthly goods-intake report (CR-9).
// Lines are pasted from a spreadsheet or typed (one per row) or come from ISDOC; the server
// computes nets, findings and learned groups. Nothing here reads a photo.
const goods = { doc: "", data: null, ticket: 0, reportTicket: 0, report: null };
const GOODS_COLUMNS = 7;

const linesUrl = (doc) => base() + "/documents/" + encodeURIComponent(doc) + "/lines";
const groupName = (key) => (key ? COPY[lang].goodsGroups[key] || key : t("noGroup"));

// "code; name; quantity; unit; unit price; VAT %; net" — tab (from Excel) or semicolon; net optional.
function parseGoods(textValue) {
  const rows = textValue.split(/\r?\n/).filter((row) => row.trim());
  return rows.map((row, index) => {
    const cells = (row.includes("\t") ? row.split("\t") : row.split(";")).map((c) => c.trim());
    if (cells.length < GOODS_COLUMNS - 1 || cells.length > GOODS_COLUMNS || !cells[1])
      throw { messageKey: "goodsRowInvalid", row: index + 1 };
    const [code, name, quantity, unit, price, vat, net] = cells;
    const rate = (vat || "").replace("%", "").trim();
    return {
      item_code: code || null,
      name,
      quantity: decimal(quantity),
      unit: unit || "ks",
      unit_price: decimal(price),
      vat_rate: rate === "" ? null : rate,
      net: net ? decimal(net) : null,
    };
  });
}
function goodsAsText(lines) {
  return lines
    .map((l) => [l.item_code || "", l.name, l.quantity, l.unit, l.unit_price, l.vat_rate ?? "", l.net].join("\t"))
    .join("\n");
}
async function loadGoodsLines() {
  const x = state.extract;
  if (!x || !FINANCE_ROLES.includes(state.role)) return resetGoodsLines();
  const ticket = ++goods.ticket;
  goods.doc = x.doc;
  $("goods-section").hidden = false;
  const data = await request(linesUrl(x.doc));
  if (ticket !== goods.ticket || state.extract !== x) return;
  goods.data = data;
  $("goods-paste").value = goodsAsText(data.lines);
  renderGoodsLines();
}
function goodsFinding(f) {
  const detail = f.detail || {};
  return fill(COPY[lang].goodsFindings[f.code] || f.code, {
    lines: f.lines.join(", "),
    computed: detail.computed ? money(detail.computed, "CZK") : "",
    stated: detail.stated ? money(detail.stated, "CZK") : "",
    rate: detail.rate ?? "",
    base: detail.invoice_base ? money(detail.invoice_base, "CZK") : "",
    net: detail.lines_net ? money(detail.lines_net, "CZK") : "",
  });
}
function renderGoodsLines() {
  const data = goods.data,
    table = $("goods-table"),
    notes = $("goods-findings");
  table.replaceChildren();
  notes.replaceChildren();
  const hasHeader = !!state.extract?.data;
  $("goods-save").disabled = !hasHeader;
  $("goods-status").textContent = !hasHeader
    ? t("goodsNeedHeader")
    : data?.version
      ? fill(t(data.source === "isdoc" ? "goodsFromIsdoc" : "goodsVersion"), { v: data.version, n: data.lines.length })
      : t("goodsEmpty");
  if (!data || !data.lines.length) return;
  const head = document.createElement("tr");
  for (const key of ["goodsNo", "goodsCode", "goodsName", "goodsQty", "goodsPrice", "goodsVat", "goodsNet", "goodsGroup"])
    head.append(text("th", t(key)));
  table.append(head);
  for (const line of data.lines) {
    const row = document.createElement("tr"),
      select = document.createElement("select");
    select.setAttribute("aria-label", t("goodsGroup") + " · " + line.name);
    select.append(option("", t("noGroup")), ...data.groups.map((g) => option(g, groupName(g))));
    select.value = line.goods_group || "";
    select.onchange = () =>
      run(async () => {
        if (!select.value) return;
        const x = state.extract;
        let saved;
        try {
          saved = await request(linesUrl(goods.doc) + "/" + line.line_no + "/group",
            json("PUT", { goods_group: select.value, expected_version: data.version }));
        } catch (error) {
          // Codex review, PR #14: the set changed meanwhile; show the current lines instead.
          if (error.status === 409 && state.extract === x) {
            await loadGoodsLines();
            throw { messageKey: "goodsConflict" };
          }
          throw error;
        }
        if (state.extract !== x) return;
        goods.data = saved;
        renderGoodsLines();
        notice(saved.also_updated ? fill(t("goodsLearnedMore"), { n: saved.also_updated }) : t("saved"));
      }, select);
    const group = document.createElement("td");
    group.append(select);
    if (line.group_source === "learned") group.append(text("small", " " + t("goodsLearned"), "muted"));
    row.append(
      text("td", String(line.line_no)),
      text("td", line.item_code || "—"),
      text("td", line.name),
      text("td", line.quantity + " " + line.unit),
      text("td", money(line.unit_price, "CZK")),
      text("td", line.vat_rate === null ? "—" : line.vat_rate + " %"),
      text("td", money(line.net, "CZK")),
      group,
    );
    if (data.findings.some((f) => f.lines.includes(line.line_no))) row.className = "flagged";
    table.append(row);
  }
  for (const f of data.findings) notes.append(text("li", goodsFinding(f)));
}
async function saveGoodsLines() {
  const x = state.extract;
  let lines;
  $("goods-error").textContent = "";
  try {
    lines = parseGoods($("goods-paste").value);
  } catch (error) {
    if (error.messageKey !== "goodsRowInvalid") throw error;
    $("goods-error").textContent = fill(t("goodsRowInvalid"), { row: error.row });
    return;
  }
  if (!lines.length) {
    $("goods-error").textContent = t("goodsNoRows");
    return;
  }
  try {
    const data = await request(linesUrl(x.doc), json("PUT", { lines, expected_version: goods.data?.version ?? null }));
    if (state.extract !== x) return;
    goods.data = data;
    renderGoodsLines();
    notice(t("saved"));
    loadGoods(true).catch(() => {});
  } catch (error) {
    if (error.status === 409 && state.extract === x) {
      await loadGoodsLines();
      throw { messageKey: x.data ? "goodsConflict" : "goodsNeedHeader" };
    }
    throw error;
  }
}
function resetGoodsLines() {
  goods.ticket++;
  goods.doc = "";
  goods.data = null;
  $("goods-section").hidden = true;
  $("goods-paste").value = "";
  $("goods-table").replaceChildren();
  $("goods-findings").replaceChildren();
  $("goods-status").textContent = "";
  $("goods-error").textContent = "";
}

// Monthly goods intake: groups (money and quantity), suppliers, most bought items.
async function loadGoods(finance) {
  const ticket = ++goods.reportTicket;
  if (!state.org || !finance) return resetGoods();
  if (!$("goods-month").value) $("goods-month").value = pragueToday().slice(0, 7);
  const report = await request(base() + "/goods?month=" + encodeURIComponent($("goods-month").value));
  if (ticket !== goods.reportTicket) return;
  goods.report = report;
  renderGoods();
}
function renderGoods() {
  const report = goods.report;
  if (!report) return;
  $("goods-panel").hidden = false;
  const bars = $("goods-groups"),
    items = $("goods-items");
  bars.replaceChildren();
  items.replaceChildren();
  const czk = (totals) => Number(totals.CZK || 0);
  const top = Math.max(1, ...report.groups.map((g) => czk(g.totals)));
  for (const group of report.groups) {
    const quantity = Object.entries(group.quantity).map(([unit, n]) => n + " " + unit).join(" · ");
    const amounts = Object.entries(group.totals).map(([cur, v]) => money(v, cur)).join(" · ");
    bars.append(supplierRow(groupName(group.group), fill(t("goodsLines"), { n: group.lines, qty: quantity }),
      amounts, czk(group.totals) / top, !group.group));
  }
  if (!report.groups.length) bars.append(text("p", t("goodsNoData"), "muted small"));
  for (const item of report.top_items.slice(0, 8)) {
    const quantity = Object.entries(item.quantity).map(([unit, n]) => n + " " + unit).join(" · ");
    items.append(supplierRow(item.name, [item.code, groupName(item.group), quantity].filter(Boolean).join(" · "),
      Object.entries(item.totals).map(([cur, v]) => money(v, cur)).join(" · "), czk(item.totals) / Math.max(1, czk(report.top_items[0].totals))));
  }
  $("goods-summary").textContent = fill(t("goodsSummary"), { docs: report.documents, n: report.uncategorised_lines });
}
function resetGoods() {
  goods.reportTicket++;
  goods.report = null;
  $("goods-panel").hidden = true;
  $("goods-groups").replaceChildren();
  $("goods-items").replaceChildren();
  $("goods-summary").textContent = "";
  $("goods-month").value = "";
}
$("goods-form").onsubmit = (e) => {
  e.preventDefault();
  run(saveGoodsLines, $("goods-save"));
};
$("goods-month").onchange = () => run(() => loadGoods(FINANCE_ROLES.includes(state.role)));
