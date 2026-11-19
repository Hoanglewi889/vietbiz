"use strict";
// Owner money overview (owner request 19.11.2026: the "Tiền của các tiệm" dashboard in the app).
// Reads GET …/reports/overview for every company the user owns (or the one an accountant has
// open), sums them for "all shops", and draws everything with plain SVG. The 2027 plan runs in
// the browser from the last 12 months; its reference values are listed in OV_PLAN with sources.
const OV_PLAN = {
  // ČNB autumn 2026 forecast (published 5.11.2026): CPI 2027 3,2 %.
  inflation: 3.2,
  // OSVČ minimum advances 2027 (government regulation 177/2026 Sb., average wage 51 663 Kč):
  // social 5 281 + health 3 488 Kč a month; flat tax band 1 2027: 9 662 Kč a month.
  insurance: { min: 8769, flat1: 9662, none: 0 },
  // Employer contributions on gross wages: social 24,8 % + health 9 %.
  employer: 0.338,
};
const OV_TEXT = {
  vi: {
    title: "Tiền của tiệm", titleMany: "Tiền của các tiệm", all: "Tất cả tiệm", shop: "Tiệm", month: "Tháng",
    take: "Tháng {month} {who} còn lại {net} Kč, {dir} {pct} so với tháng trước.", takeFirst: "Tháng {month} {who} còn lại {net} Kč.",
    up: "tăng", down: "giảm", whoAll: "các tiệm", in: "Tiền vào", out: "Tiền ra", net: "Còn lại", cash: "Khách trả tiền mặt",
    cashRest: "phần còn lại: thẻ, chuyển khoản", vsPrev: "so với tháng trước", firstMonth: "chưa có tháng trước",
    compare: "So sánh các tiệm — tháng {month}", compareNote: "Mỗi tiệm là một công ty riêng trong VietBiz; ở đây cộng chung.",
    trend: "Tiền vào và tiền ra trong 12 tháng", costs: "Tiền ra tháng {month} gồm những gì", mix: "Khách trả bằng gì",
    mixNote: "Từ 1/1/2027 mọi khoản trả tại quầy — tiền mặt, thẻ, mã QR — phải ghi nhận EET.",
    goods: "Tiền hàng", wages: "Lương", rent: "Thuê mặt bằng", other: "Chi khác", mCash: "Tiền mặt", mCard: "Thẻ", mBank: "Chuyển khoản",
    vat: "Hóa đơn và thuế DPH — tháng {month}",
    vatNote: "Bán tại quầy: khoản thu ghi trong sổ thu chi kèm thuế suất. Hóa đơn xuất và hóa đơn nhập đã duyệt tách theo 21 %, 12 %, 0 %.",
    sales: "Bán ra (có DPH)", purchases: "Hóa đơn nhập (có DPH)", vatDue: "DPH phải nộp", vatOut: "trong đó DPH bán ra", vatIn: "trong đó DPH được khấu trừ",
    vatFormula: "= DPH bán ra − DPH được khấu trừ", notPayer: "Công ty chưa đăng ký là người nộp DPH: không có DPH phải nộp.",
    kind: "Loại", rate: "Thuế suất", base: "Chưa thuế (Kč)", tax: "DPH (Kč)", gross: "Tổng có DPH (Kč)",
    salesRow: "Bán ra", purchasesRow: "Hóa đơn nhập", total: "tổng", unknown: "chưa rõ thuế suất",
    vatChart: "DPH phải nộp mỗi tháng", vatDeadline: "Người nộp DPH theo tháng nộp tờ khai và tiền thuế đến ngày 25 tháng sau. Số chính thức do kế toán lập.",
    unpaid: "Hóa đơn nhà cung cấp chưa trả", unpaidNone: "Không có hóa đơn đã duyệt nào chưa ghi thanh toán.",
    supplier: "Nhà cung cấp", invoices: "Số hóa đơn", amount: "Chưa trả (Kč)", due: "Hạn sớm nhất",
    plan: "Kế hoạch năm 2027 — nếu giá cả, lương, tiền thuê đều tăng",
    planNote: "Lấy 12 tháng gần nhất làm gốc, rồi tăng từng khoản theo mức bạn chọn. Mặc định lạm phát 3,2 % theo dự báo mùa thu 2026 của ČNB.",
    pInfl: "Giá hàng và chi khác tăng (%)", pRev: "Doanh thu tăng (%)", pWage: "Lương tăng (%)", pRent: "Tiền thuê tăng (%)", pBuffer: "Dự phòng chi bất ngờ (% tiền ra)",
    pWagesIncl: "Lương đã gồm bảo hiểm nhân viên?", yes: "Đã gồm", noAdd: "Chưa — cộng 33,8 %",
    pIns: "Bảo hiểm của chủ (tính một lần)", insMin: "Tối thiểu 2027: 8 769 Kč/tháng", insFlat: "Thuế khoán mức 1 2027: 9 662 Kč/tháng", insNone: "Không tính (chủ là s.r.o.)",
    reset: "Về mức mặc định", pBase: "12 tháng qua: còn lại", pBaseSub: "trước bảo hiểm của chủ", pPlan: "2027 dự kiến: còn lại",
    pInsK: "Bảo hiểm của chủ 2027", pInsSub: "cả năm", pAfter: "2027: còn lại sau bảo hiểm", pMonth: "khoảng {n} Kč mỗi tháng",
    pDiff: "{n} Kč so với 12 tháng qua", pNeed: "Để còn lại bằng 12 tháng qua (trước bảo hiểm của chủ), doanh thu năm 2027 cần tăng {pct}.",
    pBars: "Năm 2027 thay đổi bao nhiêu so với 12 tháng qua", dRev: "Doanh thu tăng", dGoods: "Giá hàng", dWages: "Lương", dRent: "Tiền thuê", dOther: "Chi khác", dReserve: "Dự phòng",
    better: "Làm tăng tiền còn lại", worse: "Làm giảm tiền còn lại",
    notes: "Cách tính", note1: "Tiền thực tế theo sổ thu chi (tiền vào, tiền ra), chỉ tiền CZK. Không phải tờ khai thuế.",
    note2: "Còn lại = tiền vào − tiền ra, chưa trừ DPH phải nộp và bảo hiểm của chủ.",
    note3: "Kế hoạch: lạm phát 3,2 % (ČNB, 5/11/2026); bảo hiểm tối thiểu OSVČ 2027 5 281 + 3 488 Kč; thuế khoán mức 1 2027 9 662 Kč; chủ đóng 33,8 % lương gộp cho nhân viên. Chỉ là ước tính — hỏi kế toán trước khi quyết định.",
    skipped: "{n} khoản bằng EUR không tính vào đây.", empty: "Chưa có số liệu. Ghi thu chi trong Sổ thu chi hoặc duyệt hóa đơn để xem tổng quan.",
    failed: "Không tải được số liệu của {name}.",
    capture: "Chụp và lưu hóa đơn",
    captureFor: "Cho công ty {name}: hóa đơn chụp được lưu trong kho chứng từ, kế toán kiểm tra rồi duyệt.",
    captureNote: "Chờ duyệt: {review} · cần sửa: {changes} · đã duyệt: {approved}.",
    capturePhoto: "Chụp hóa đơn nhập", captureRegister: "Ghi tổng quầy hôm nay", captureArchive: "Mở kho hóa đơn",
  },
  cs: {
    title: "Peníze provozovny", titleMany: "Peníze provozoven", all: "Všechny provozovny", shop: "Provozovna", month: "Měsíc",
    take: "V {month} zůstalo {who} {net} Kč, {dir} o {pct} proti minulému měsíci.", takeFirst: "V {month} zůstalo {who} {net} Kč.",
    up: "více", down: "méně", whoAll: "provozovnám", in: "Příjmy", out: "Výdaje", net: "Zůstatek", cash: "Platby v hotovosti",
    cashRest: "zbytek: karta, převod", vsPrev: "proti minulému měsíci", firstMonth: "bez předchozího měsíce",
    compare: "Srovnání provozoven — {month}", compareNote: "Každá provozovna je ve VietBiz samostatná firma; zde sečteno.",
    trend: "Příjmy a výdaje za 12 měsíců", costs: "Z čeho se skládají výdaje {month}", mix: "Jak zákazníci platí",
    mixNote: "Od 1. 1. 2027 se evidují všechny platby na místě — hotovost, karta, QR kód.",
    goods: "Zboží", wages: "Mzdy", rent: "Nájem", other: "Ostatní", mCash: "Hotovost", mCard: "Karta", mBank: "Převod",
    vat: "Faktury a DPH — {month}",
    vatNote: "Tržby na pokladně: příjmy v pokladní knize se sazbou. Vydané a schválené přijaté faktury rozdělené na 21 %, 12 %, 0 %.",
    sales: "Výstup (s DPH)", purchases: "Přijaté faktury (s DPH)", vatDue: "DPH k úhradě", vatOut: "z toho DPH na výstupu", vatIn: "z toho odpočet DPH",
    vatFormula: "= DPH na výstupu − odpočet", notPayer: "Firma není plátcem DPH: žádná DPH k úhradě.",
    kind: "Druh", rate: "Sazba", base: "Základ (Kč)", tax: "DPH (Kč)", gross: "Celkem s DPH (Kč)",
    salesRow: "Výstup", purchasesRow: "Přijaté faktury", total: "celkem", unknown: "sazba neznámá",
    vatChart: "DPH k úhradě po měsících", vatDeadline: "Měsíční plátce podává přiznání a platí daň do 25. dne následujícího měsíce. Oficiální čísla připraví účetní.",
    unpaid: "Nezaplacené faktury dodavatelů", unpaidNone: "Žádná schválená faktura bez zaznamenané platby.",
    supplier: "Dodavatel", invoices: "Faktur", amount: "Nezaplaceno (Kč)", due: "Nejbližší splatnost",
    plan: "Plán na rok 2027 — když porostou ceny, mzdy a nájem",
    planNote: "Základem je posledních 12 měsíců, každá položka roste podle zvolené sazby. Výchozí inflace 3,2 % podle podzimní prognózy ČNB 2026.",
    pInfl: "Ceny zboží a ostatní (%)", pRev: "Růst tržeb (%)", pWage: "Růst mezd (%)", pRent: "Růst nájmu (%)", pBuffer: "Rezerva na nečekané výdaje (% výdajů)",
    pWagesIncl: "Mzdy už obsahují odvody za zaměstnance?", yes: "Ano", noAdd: "Ne — přičíst 33,8 %",
    pIns: "Pojištění majitele (jednou)", insMin: "Minimum 2027: 8 769 Kč/měsíc", insFlat: "Paušální daň 1. pásmo 2027: 9 662 Kč/měsíc", insNone: "Nepočítat (majitel je s.r.o.)",
    reset: "Výchozí hodnoty", pBase: "Posledních 12 měsíců: zůstatek", pBaseSub: "před pojištěním majitele", pPlan: "2027 odhad: zůstatek",
    pInsK: "Pojištění majitele 2027", pInsSub: "za rok", pAfter: "2027: zůstatek po pojištění", pMonth: "asi {n} Kč měsíčně",
    pDiff: "{n} Kč proti posledním 12 měsícům", pNeed: "Aby zůstatek zůstal stejný (před pojištěním majitele), musí tržby 2027 vzrůst o {pct}.",
    pBars: "O kolik se rok 2027 změní proti posledním 12 měsícům", dRev: "Růst tržeb", dGoods: "Ceny zboží", dWages: "Mzdy", dRent: "Nájem", dOther: "Ostatní", dReserve: "Rezerva",
    better: "Zvyšuje zůstatek", worse: "Snižuje zůstatek",
    notes: "Jak se počítá", note1: "Skutečné peníze podle pokladní knihy (příjmy, výdaje), jen v CZK. Nejde o daňové přiznání.",
    note2: "Zůstatek = příjmy − výdaje, bez odečtení DPH k úhradě a pojištění majitele.",
    note3: "Plán: inflace 3,2 % (ČNB, 5. 11. 2026); minimální zálohy OSVČ 2027 5 281 + 3 488 Kč; paušální daň 1. pásmo 2027 9 662 Kč; odvody zaměstnavatele 33,8 % z hrubé mzdy. Jen odhad — před rozhodnutím se poraďte s účetní.",
    skipped: "{n} položek v EUR zde není započteno.", empty: "Zatím žádná data. Zapište příjmy a výdaje v pokladní knize nebo schvalte faktury.",
    failed: "Data firmy {name} se nepodařilo načíst.",
    capture: "Vyfotit a uložit doklady",
    captureFor: "Pro firmu {name}: vyfocené doklady se ukládají do archivu, účetní je zkontroluje a schválí.",
    captureNote: "Ke kontrole: {review} · k opravě: {changes} · schváleno: {approved}.",
    capturePhoto: "Vyfotit přijatou fakturu", captureRegister: "Zapsat dnešní tržbu", captureArchive: "Otevřít archiv dokladů",
  },
};
const ovState = { shops: [], data: {}, failed: [], shop: "", month: "", seen: null, ticket: 0,
  plan: { infl: OV_PLAN.inflation, rev: OV_PLAN.inflation, wage: 5, rent: OV_PLAN.inflation, buffer: 2, wagesIncl: "yes", ins: "min" } };
const OV_DEFAULT_PLAN = { ...ovState.plan };

function ovT(key, values) {
  const copy = OV_TEXT[lang === "cs" ? "cs" : "vi"][key] ?? key;
  return values ? fill(copy, values) : copy;
}
const ovN = (v) => Number(v || 0);
const ovKc = (v) => new Intl.NumberFormat("cs-CZ", { maximumFractionDigits: 0 }).format(Math.round(ovN(v)));
const ovPct = (v) => new Intl.NumberFormat(lang === "cs" ? "cs-CZ" : "vi-VN", { maximumFractionDigits: 1, minimumFractionDigits: 1 }).format(Math.abs(v)) + " %";
const ovLabel = (m) => m.slice(5) + "/" + m.slice(0, 4);
const ovShort = (m) => m.slice(5) + "/" + m.slice(2, 4);
const OV_SVG = "http://www.w3.org/2000/svg";

function ovEl(tag, cls, ...children) {
  const el = document.createElement(tag);
  if (cls) el.className = cls;
  for (const c of children) if (c != null) el.append(c);
  return el;
}
function ovSvg(tag, attrs = {}, label) {
  const el = document.createElementNS(OV_SVG, tag);
  for (const [k, v] of Object.entries(attrs)) el.setAttribute(k, v);
  if (label != null) el.textContent = label;
  return el;
}
function ovChart(width, height, label) {
  const svg = ovSvg("svg", { viewBox: `0 0 ${width} ${height}`, width: "100%", role: "img", "aria-label": label, class: "ov-svg" });
  return svg;
}

// Which companies the overview covers: all the owner's, or the one company an accountant has open.
function ovShops() {
  if (state.role === "owner") return state.orgs.filter((o) => o.role === "owner");
  return state.orgs.filter((o) => o.id === state.org);
}
async function loadOverview() {
  const ticket = ++ovState.ticket;
  $("overview-tab").hidden = !FINANCE_ROLES.includes(state.role);
  if ($("overview-tab").hidden) {
    if (!$("overview-view").hidden) setTab("tasks");
    return;
  }
  if ($("overview-view").hidden) return; // loaded when opened
  const shops = ovShops(), data = {}, failed = [];
  await Promise.all(shops.map(async (o) => {
    try {
      data[o.id] = await request("/v1/organizations/" + encodeURIComponent(o.id) + "/reports/overview?months=12");
    } catch (error) {
      failed.push(o.name);
    }
  }));
  if (ticket !== ovState.ticket) return;
  ovState.shops = shops.filter((o) => data[o.id]);
  ovState.data = data;
  ovState.failed = failed;
  if (!ovState.shops.some((o) => o.id === ovState.shop)) ovState.shop = ovState.shops.length > 1 ? "" : ovState.shops[0]?.id || "";
  renderOverview();
}
function resetOverview() {
  ovState.ticket++;
  ovState.shops = [];
  ovState.data = {};
  ovState.shop = "";
  ovState.month = "";
  if ($("overview-root")) $("overview-root").replaceChildren();
}

// Months of one shop, or all shops summed month by month.
function ovSeries(shopId) {
  const ids = shopId ? [shopId] : ovState.shops.map((o) => o.id);
  const months = ovState.data[ids[0]]?.months.map((m) => m.month) || [];
  return months.map((month, i) => {
    const rows = ids.map((id) => ovState.data[id].months[i]);
    const sum = (f) => rows.reduce((n, r) => n + ovN(f(r)), 0);
    const rate = (side, r, key) => sum((x) => x[side][r][key]);
    const out = {
      month,
      cash: sum((r) => r.income.cash), card: sum((r) => r.income.card), bankIn: sum((r) => r.income.bank),
      revenue: sum((r) => r.income.total), goods: sum((r) => r.expense.goods), wages: sum((r) => r.expense.wages),
      rent: sum((r) => r.expense.rent), other: sum((r) => r.expense.other), expenses: sum((r) => r.expense.total),
      vatOut: sum((r) => r.vat_out), vatIn: sum((r) => r.vat_in),
      vatDue: rows.some((r) => r.vat_due != null) ? sum((r) => r.vat_due) : null,
      salesUnknown: sum((r) => r.sales_unknown), purchasesUnknown: sum((r) => r.purchases_unknown),
      sales: {}, purchases: {},
    };
    for (const r of ["21", "12", "0"]) {
      out.sales[r] = { base: rate("sales", r, "base"), tax: rate("sales", r, "tax"), gross: rate("sales", r, "gross") };
      out.purchases[r] = { base: rate("purchases", r, "base"), tax: rate("purchases", r, "tax"), gross: rate("purchases", r, "gross") };
    }
    out.net = out.revenue - out.expenses;
    out.cashShare = out.revenue ? (100 * out.cash) / out.revenue : null;
    return out;
  });
}
const ovChange = (now, before) => (before ? (100 * (now - before)) / Math.abs(before) : null);

function renderOverview() {
  const root = $("overview-root");
  if (!root) return;
  root.replaceChildren();
  if (!ovState.shops.length) {
    if (ovState.failed.length) root.append(ovEl("p", "ov-note", ovT("failed", { name: ovState.failed.join(", ") })));
    return;
  }
  const series = ovSeries(ovState.shop);
  // Drawn at the width they get, so text stays at its real size (root padding 18, card 17).
  // Measured on the view, not the root: an empty root is not displayed and has no width.
  const view = root.parentElement, pad = getComputedStyle(view);
  const rootW = view.clientWidth - parseFloat(pad.paddingLeft) - parseFloat(pad.paddingRight) || 640;
  const full = Math.max(260, rootW - 70);
  const half = rootW - 36 >= 616 ? Math.floor((rootW - 52) / 2) - 34 : full;
  const months = series.map((s) => s.month);
  if (!months.includes(ovState.month)) ovState.month = months[months.length - 1];
  const i = months.indexOf(ovState.month), cur = series[i], prev = series[i - 1];
  const shopName = ovState.shop ? ovState.shops.find((o) => o.id === ovState.shop).name : ovT("all");
  const many = ovState.shops.length > 1;

  // Header: pickers, title, one sentence, four numbers.
  const hero = ovEl("header", "ov-hero");
  const pickers = ovEl("div", "ov-pickers");
  if (many) {
    const shopSel = ovEl("select", "ov-select");
    shopSel.id = "ov-shop";
    shopSel.setAttribute("aria-label", ovT("shop"));
    shopSel.append(option("", ovT("all")), ...ovState.shops.map((o) => option(o.id, o.name)));
    shopSel.value = ovState.shop;
    shopSel.onchange = () => { ovState.shop = shopSel.value; renderOverview(); };
    pickers.append(ovEl("label", "ov-pick", ovT("shop") + " ", shopSel));
  }
  const monthSel = ovEl("select", "ov-select");
  monthSel.id = "ov-month";
  monthSel.setAttribute("aria-label", ovT("month"));
  monthSel.append(...[...months].reverse().map((m) => option(m, ovLabel(m))));
  monthSel.value = ovState.month;
  monthSel.onchange = () => { ovState.month = monthSel.value; renderOverview(); };
  pickers.append(ovEl("label", "ov-pick", ovT("month") + " ", monthSel));
  hero.append(pickers, ovEl("h2", "ov-title", many ? ovT("titleMany") : ovT("title")), ovEl("p", "ov-shop", shopName));
  const netChange = prev ? ovChange(cur.net, prev.net) : null;
  const who = ovState.shop ? shopName : many ? ovT("whoAll") : shopName;
  const take = ovEl("p", "ov-take");
  take.id = "ov-take";
  take.textContent = netChange == null
    ? ovT("takeFirst", { month: ovLabel(cur.month), who, net: ovKc(cur.net) })
    : ovT("take", { month: ovLabel(cur.month), who, net: ovKc(cur.net), dir: netChange >= 0 ? ovT("up") : ovT("down"), pct: ovPct(netChange) });
  hero.append(take);
  const kpis = ovEl("div", "ov-kpis");
  const kpi = (id, label, value, change, goodUp, sub) => {
    const box = ovEl("div", "ov-kpi", ovEl("span", "ov-kpi-label", label), ovEl("strong", "ov-kpi-value", value));
    box.id = id;
    if (change !== undefined) {
      const ch = change == null ? ovEl("span", "ov-kpi-sub", prev ? "—" : ovT("firstMonth"))
        : ovEl("span", "ov-kpi-sub " + ((goodUp ? change >= 0 : change <= 0) ? "good" : "bad"), (change >= 0 ? "▲ " : "▼ ") + ovPct(change) + " " + ovT("vsPrev"));
      box.append(ch);
    } else if (sub) box.append(ovEl("span", "ov-kpi-sub", sub));
    return box;
  };
  kpis.append(
    kpi("ov-in", ovT("in"), ovKc(cur.revenue), prev ? ovChange(cur.revenue, prev.revenue) : null, true),
    kpi("ov-out", ovT("out"), ovKc(cur.expenses), prev ? ovChange(cur.expenses, prev.expenses) : null, false),
    kpi("ov-net", ovT("net"), ovKc(cur.net), netChange, true),
    kpi("ov-cash", ovT("cash"), cur.cashShare == null ? "—" : ovPct(cur.cashShare), undefined, true, ovT("cashRest")),
  );
  hero.append(kpis);
  root.append(hero);
  if (!series.some((s) => s.revenue || s.expenses || s.vatOut || s.vatIn)) root.append(ovEl("p", "ov-note", ovT("empty")));
  if (ovState.failed.length) root.append(ovEl("p", "ov-note", ovT("failed", { name: ovState.failed.join(", ") })));

  root.append(ovCapture());
  if (many) root.append(ovCompare(i, full));
  root.append(ovCard("ov-trend-card", ovT("trend"), null, ovLegend([["in", ovT("in")], ["out", ovT("out")]]), ovTrend(series, i, full)));
  const grid = ovEl("div", "ov-grid");
  grid.append(
    ovCard("ov-costs-card", ovT("costs", { month: ovLabel(cur.month) }), null, ovBars([
      [ovT("goods"), cur.goods], [ovT("wages"), cur.wages], [ovT("rent"), cur.rent], [ovT("other"), cur.other],
    ], "out", half)),
    ovCard("ov-mix-card", ovT("mix"), ovT("mixNote"), ovLegend([["in", ovT("mCash")], ["soft", ovT("mCard")], ["line", ovT("mBank")]]), ovMix(series, i, half)),
  );
  root.append(grid, ovVat(series, i, full), ovUnpaid(), ovPlanCard(series, full));
  const notes = ovEl("details", "ov-notes", ovEl("summary", "", ovT("notes")));
  const list = ovEl("ul", "");
  for (const k of ["note1", "note2", "note3"]) list.append(ovEl("li", "", ovT(k)));
  const eur = ovState.shops.reduce((n, o) => n + (ovState.data[o.id].skipped?.currency || 0), 0);
  if (eur) list.append(ovEl("li", "", ovT("skipped", { n: eur })));
  notes.append(list);
  root.append(notes);
}

function ovCard(id, title, note, ...body) {
  const card = ovEl("section", "ov-card", ovEl("h3", "", title));
  card.id = id;
  if (note) card.append(ovEl("p", "ov-note", note));
  card.append(...body.filter(Boolean));
  return card;
}
function ovLegend(items) {
  const ul = ovEl("ul", "ov-legend");
  for (const [cls, label] of items) ul.append(ovEl("li", "", ovEl("span", "ov-sw " + cls), label));
  return ul;
}

// Capture and archive: the three things an owner does with paper — photograph a supplier invoice,
// book the day's register total with its VAT rate, open the archive — plus what waits for review.
function ovCapture() {
  // Codex review, PR #33: the actions work on one company. With a shop chosen that is it (the
  // workspace switches to it first); with all shops it is the company open in the workspace.
  const target = ovState.shop || state.org;
  const name = (state.orgs.find((o) => o.id === target) || {}).name || "";
  const docs = target === state.org ? state.docs || [] : null;
  const count = (status) => docs.filter((d) => d.status === status).length;
  const card = ovCard("ov-capture-card", ovT("capture"),
    ovT("captureFor", { name }) + (docs ? " " + ovT("captureNote", { review: count("needs_review"), changes: count("needs_changes"), approved: count("approved") }) : ""));
  const row = ovEl("div", "ov-actions");
  const action = (id, label, go) => {
    const b = ovEl("button", "ov-action", label);
    b.type = "button";
    b.id = id;
    b.onclick = () => run(async () => {
      if (target !== state.org) {
        $("org").value = target;
        await switchOrg();
      }
      go();
    }, b);
    return b;
  };
  const photo = action("ov-photo", ovT("capturePhoto"), () => {
    if (typeof phoneCapture === "function" && typeof phoneActive === "function" && phoneActive()) return phoneCapture();
    setTab("docs");
    $("upload-file").click();
  });
  photo.hidden = (ovState.shops.find((o) => o.id === target) || { role: state.role }).role !== "owner";
  row.append(
    photo,
    action("ov-register", ovT("captureRegister"), () => {
      setTab("cash");
      // A fresh, unlinked entry: a pending supplier payment must not travel with the sale.
      state.cashDoc = null;
      $("c-linked").hidden = true;
      $("c-kind").value = "income";
      $("c-kind").onchange();
      $("c-category").value = "sales";
      $("c-date").value = pragueToday();
      $("c-amount").focus();
    }),
    action("ov-archive", ovT("captureArchive"), () => setTab("docs")),
  );
  card.append(row);
  return card;
}

function ovCompare(i, W) {
  const rows = ovState.shops.map((o) => ({ name: o.name, ...ovSeries(o.id)[i] })).sort((a, b) => b.revenue - a.revenue);
  const barH = 14, gap = 4, groupH = 3 * (barH + gap) + 28;
  const svg = ovChart(W, rows.length * groupH, ovT("compare", { month: ovLabel(ovState.month) }));
  const max = Math.max(1, ...rows.map((r) => r.revenue), ...rows.map((r) => r.expenses));
  const sx = (v) => (Math.max(0, v) / max) * (W - 90);
  rows.forEach((r, k) => {
    const y0 = k * groupH;
    svg.append(ovSvg("text", { x: 0, y: y0 + 14, class: "ov-strong" }, r.name));
    [["revenue", "in"], ["expenses", "out"], ["net", "net"]].forEach(([key, cls], j) => {
      const y = y0 + 22 + j * (barH + gap);
      svg.append(ovSvg("rect", { x: 0, y, width: Math.max(1, sx(r[key])), height: barH, rx: 4, class: "ov-fill-" + cls }));
      svg.append(ovSvg("text", { x: sx(r[key]) + 6, y: y + 11 }, ovKc(r[key])));
    });
  });
  return ovCard("ov-compare-card", ovT("compare", { month: ovLabel(ovState.month) }), ovT("compareNote"),
    ovLegend([["in", ovT("in")], ["out", ovT("out")], ["net", ovT("net")]]), svg);
}

function ovTrend(series, sel, W) {
  const H = 220, L = 46, R = 10, T = 12, B = 24;
  const svg = ovChart(W, H, ovT("trend"));
  const max = Math.max(1, ...series.map((s) => Math.max(s.revenue, s.expenses))) * 1.08;
  const x = (k) => L + (series.length > 1 ? (k * (W - L - R)) / (series.length - 1) : (W - L - R) / 2);
  const y = (v) => T + (1 - v / max) * (H - T - B);
  for (let t = 0; t <= 4; t++) {
    const v = (max * t) / 4;
    svg.append(ovSvg("line", { x1: L, x2: W - R, y1: y(v), y2: y(v), class: "ov-grid" }));
    svg.append(ovSvg("text", { x: L - 6, y: y(v) + 4, "text-anchor": "end" }, Math.round(v / 1000) + "k"));
  }
  svg.append(ovSvg("rect", { x: x(sel) - 12, y: T, width: 24, height: H - T - B, rx: 6, class: "ov-band" }));
  series.forEach((s, k) => {
    const step = W < 480 ? 3 : 2;
    if (k % step === (series.length - 1) % step) svg.append(ovSvg("text", { x: x(k), y: H - 6, "text-anchor": "middle" }, ovShort(s.month)));
  });
  for (const [key, cls] of [["revenue", "in"], ["expenses", "out"]]) {
    svg.append(ovSvg("polyline", { points: series.map((s, k) => `${x(k)},${y(s[key])}`).join(" "), class: "ov-line-" + cls }));
    series.forEach((s, k) => {
      const dot = ovSvg("circle", { cx: x(k), cy: y(s[key]), r: k === sel ? 5 : 3, class: "ov-fill-" + cls });
      dot.append(ovSvg("title", {}, `${ovLabel(s.month)} · ${key === "revenue" ? ovT("in") : ovT("out")}: ${ovKc(s[key])} Kč`));
      svg.append(dot);
    });
  }
  return svg;
}

function ovBars(parts, cls, W) {
  const rows = parts.filter(([, v]) => v).sort((a, b) => b[1] - a[1]);
  if (!rows.length) return ovEl("p", "ov-note", "—");
  const rowH = 34, labelW = 110, valueW = 80;
  const svg = ovChart(W, rows.length * rowH + 4, rows.map(([l, v]) => `${l} ${ovKc(v)} Kč`).join(", "));
  const max = Math.max(...rows.map(([, v]) => v));
  rows.forEach(([label, v], k) => {
    const w = Math.max(1, (v / max) * (W - labelW - valueW)), y = k * rowH + 6;
    svg.append(ovSvg("text", { x: 0, y: y + 14 }, label));
    svg.append(ovSvg("rect", { x: labelW, y, width: w, height: 18, rx: 5, class: "ov-fill-" + cls }));
    svg.append(ovSvg("text", { x: labelW + w + 6, y: y + 14 }, ovKc(v)));
  });
  return svg;
}

function ovMix(series, sel, W) {
  const H = 180, T = 20, B = 22;
  const svg = ovChart(W, H, ovT("mix"));
  const bw = (W / series.length) * 0.7;
  series.forEach((s, k) => {
    const x = (k * W) / series.length + (W / series.length - bw) / 2, total = s.revenue || 1;
    let y = H - B;
    for (const [key, cls] of [["cash", "in"], ["card", "soft"], ["bankIn", "line"]]) {
      const h = s.revenue ? ((H - T - B) * s[key]) / total : 0;
      y -= h;
      svg.append(ovSvg("rect", { x, y, width: bw, height: Math.max(0, h), class: "ov-fill-" + cls + (k === sel ? "" : " ov-dim") }));
    }
    if (k % 3 === (series.length - 1) % 3) svg.append(ovSvg("text", { x: x + bw / 2, y: H - 6, "text-anchor": "middle" }, ovShort(s.month)));
  });
  const cur = series[sel];
  if (cur.cashShare != null) {
    const x = (sel * W) / series.length + W / series.length / 2;
    svg.append(ovSvg("text", { x, y: 13, "text-anchor": "middle", class: "ov-strong" }, ovPct(cur.cashShare)));
  }
  return svg;
}

function ovVat(series, i, W) {
  const cur = series[i];
  const payer = ovState.shop ? ovState.data[ovState.shop].vat_payer : ovState.shops.some((o) => ovState.data[o.id].vat_payer);
  const sum = (side, key) => ["21", "12", "0"].reduce((n, r) => n + cur[side][r][key], 0);
  const kpis = ovEl("div", "ov-kpis ov-vat-kpis");
  const k = (id, label, value, sub) => { const b = ovEl("div", "ov-kpi", ovEl("span", "ov-kpi-label", label), ovEl("strong", "ov-kpi-value", value), ovEl("span", "ov-kpi-sub", sub)); b.id = id; return b; };
  kpis.append(
    k("ov-vat-sales", ovT("sales"), ovKc(sum("sales", "gross") + cur.salesUnknown), ovT("vatOut") + " " + ovKc(cur.vatOut) + " Kč"),
    k("ov-vat-purchases", ovT("purchases"), ovKc(sum("purchases", "gross") + cur.purchasesUnknown), ovT("vatIn") + " " + ovKc(cur.vatIn) + " Kč"),
    k("ov-vat-due", ovT("vatDue"), payer && cur.vatDue != null ? ovKc(cur.vatDue) : "—", payer ? ovT("vatFormula") : ovT("notPayer")),
  );
  const table = ovEl("table", "ov-table");
  table.id = "ov-vat-table";
  const head = ovEl("tr", "");
  for (const [label, cls] of [[ovT("kind"), ""], [ovT("rate"), "num"], [ovT("base"), "num"], [ovT("tax"), "num"], [ovT("gross"), "num"]]) head.append(ovEl("th", cls, label));
  table.append(ovEl("thead", "", head));
  const body = ovEl("tbody", "");
  const row = (kind, rate, v, total) => {
    const tr = ovEl("tr", total ? "ov-total" : "");
    for (const [txt, cls] of [[kind, ""], [rate, "num"], [v.base == null ? "—" : ovKc(v.base), "num"], [v.tax == null ? "—" : ovKc(v.tax), "num"], [ovKc(v.gross), "num"]]) tr.append(ovEl("td", cls, txt));
    body.append(tr);
  };
  for (const [side, label, unknown] of [["sales", ovT("salesRow"), cur.salesUnknown], ["purchases", ovT("purchasesRow"), cur.purchasesUnknown]]) {
    for (const r of ["21", "12", "0"]) if (cur[side][r].gross) row(label, r + " %", cur[side][r]);
    if (unknown) row(label + " — " + ovT("unknown"), "", { base: null, tax: null, gross: unknown });
    row(label + " — " + ovT("total"), "", { base: sum(side, "base"), tax: sum(side, "tax"), gross: sum(side, "gross") + unknown }, true);
  }
  table.append(body);
  const wrap = ovEl("div", "ov-table-wrap", table);
  const chart = payer ? ovVatChart(series, i, W) : null;
  return ovCard("ov-vat-card", ovT("vat", { month: ovLabel(cur.month) }), ovT("vatNote"), kpis, wrap,
    payer ? ovEl("h4", "", ovT("vatChart")) : null, chart, ovEl("p", "ov-note", ovT("vatDeadline")));
}
function ovVatChart(series, sel, W) {
  const H = 170, T = 20, B = 22;
  const svg = ovChart(W, H, ovT("vatChart"));
  const vals = series.map((s) => s.vatDue || 0), max = Math.max(1, ...vals.map(Math.abs)), min = Math.min(0, ...vals);
  const y = (v) => T + ((max - v) / (max - min || 1)) * (H - T - B);
  const bw = (W / series.length) * 0.65;
  series.forEach((s, k) => {
    const x = (k * W) / series.length + (W / series.length - bw) / 2, v = s.vatDue || 0;
    svg.append(ovSvg("rect", { x, y: Math.min(y(v), y(0)), width: bw, height: Math.max(1, Math.abs(y(v) - y(0))), rx: 3, class: "ov-fill-gold" + (k === sel ? "" : " ov-dim") }));
    if (k === sel) svg.append(ovSvg("text", { x: x + bw / 2, y: Math.min(y(v), y(0)) - 5, "text-anchor": "middle", class: "ov-strong" }, ovKc(v)));
    const step = W < 480 ? 3 : 2;
    if (k % step === (series.length - 1) % step) svg.append(ovSvg("text", { x: x + bw / 2, y: H - 6, "text-anchor": "middle" }, ovShort(s.month)));
  });
  return svg;
}

function ovUnpaid() {
  const ids = ovState.shop ? [ovState.shop] : ovState.shops.map((o) => o.id);
  const groups = new Map();
  for (const id of ids) for (const u of ovState.data[id].unpaid) {
    const name = (ovState.shops.length > 1 && !ovState.shop ? ovState.shops.find((o) => o.id === id).name + " · " : "") + u.supplier_name;
    const g = groups.get(name) || { name, count: 0, total: 0, due: null };
    g.count++;
    g.total += ovN(u.total);
    if (u.due_date && (!g.due || u.due_date < g.due)) g.due = u.due_date;
    groups.set(name, g);
  }
  const rows = [...groups.values()].sort((a, b) => b.total - a.total);
  if (!rows.length) return ovCard("ov-unpaid-card", ovT("unpaid"), ovT("unpaidNone"));
  const total = rows.reduce((n, r) => n + r.total, 0);
  const table = ovEl("table", "ov-table");
  table.id = "ov-unpaid-table";
  const head = ovEl("tr", "");
  for (const [label, cls] of [[ovT("supplier"), ""], [ovT("invoices"), "num"], [ovT("amount"), "num"], [ovT("due"), ""]]) head.append(ovEl("th", cls, label));
  const body = ovEl("tbody", "");
  const today = pragueToday();
  for (const r of rows) {
    const tr = ovEl("tr", "");
    for (const [txt, cls] of [[r.name, ""], [String(r.count), "num"], [ovKc(r.total), "num"], [r.due ? r.due.slice(8) + "/" + r.due.slice(5, 7) : "—", r.due && r.due <= today ? "ov-late" : ""]]) tr.append(ovEl("td", cls, txt));
    body.append(tr);
  }
  table.append(ovEl("thead", "", head), body);
  const card = ovCard("ov-unpaid-card", ovT("unpaid"), null, ovEl("p", "ov-unpaid-total", ovKc(total) + " Kč"), ovEl("div", "ov-table-wrap", table));
  return card;
}

// The 2027 plan, worked out in the browser from the last 12 months of the chosen shop(s).
function ovPlan(series) {
  const p = ovState.plan, last = series.slice(-12);
  const b = ["revenue", "goods", "wages", "rent", "other"].reduce((o, k) => ({ ...o, [k]: last.reduce((n, s) => n + s[k], 0) }), {});
  const baseNet = b.revenue - b.goods - b.wages - b.rent - b.other;
  const plan = { revenue: b.revenue * (1 + p.rev / 100), goods: b.goods * (1 + p.infl / 100), other: b.other * (1 + p.infl / 100),
    rent: b.rent * (1 + p.rent / 100), wages: b.wages * (1 + p.wage / 100) * (1 + (p.wagesIncl === "no" ? OV_PLAN.employer : 0)) };
  const before = plan.goods + plan.other + plan.rent + plan.wages, reserve = (before * p.buffer) / 100;
  const net = plan.revenue - before - reserve, ins = 12 * (OV_PLAN.insurance[p.ins] ?? 0);
  return { baseNet, net, ins, after: net - ins, need: b.revenue ? ovChange(before + reserve + baseNet, b.revenue) : null,
    deltas: [["dRev", plan.revenue - b.revenue], ["dGoods", b.goods - plan.goods], ["dWages", b.wages - plan.wages],
      ["dRent", b.rent - plan.rent], ["dOther", b.other - plan.other], ["dReserve", -reserve]] };
}
function ovPlanCard(series, W) {
  const card = ovCard("ov-plan-card", ovT("plan"), ovT("planNote"));
  const inputs = ovEl("div", "ov-plan-inputs");
  const num = (key, label, min, max, step) => {
    const input = ovEl("input", "");
    Object.assign(input, { type: "number", min, max, step, value: ovState.plan[key] });
    input.id = "ov-plan-" + key;
    input.onchange = () => {
      if (input.value === "" || !input.validity.valid) return;
      ovState.plan[key] = Number(input.value);
      renderOverview();
    };
    return ovEl("label", "ov-in", label, input);
  };
  const sel = (key, label, opts) => {
    const s = ovEl("select", "ov-select");
    s.id = "ov-plan-" + key;
    s.append(...opts.map(([v, l]) => option(v, l)));
    s.value = ovState.plan[key];
    s.onchange = () => { ovState.plan[key] = s.value; renderOverview(); };
    return ovEl("label", "ov-in", label, s);
  };
  const reset = ovEl("button", "ov-reset", ovT("reset"));
  reset.type = "button";
  reset.onclick = () => { ovState.plan = { ...OV_DEFAULT_PLAN }; renderOverview(); };
  inputs.append(num("infl", ovT("pInfl"), 0, 30, 0.1), num("rev", ovT("pRev"), -30, 30, 0.1), num("wage", ovT("pWage"), 0, 50, 0.5),
    num("rent", ovT("pRent"), 0, 50, 0.1), num("buffer", ovT("pBuffer"), 0, 30, 0.5),
    sel("wagesIncl", ovT("pWagesIncl"), [["yes", ovT("yes")], ["no", ovT("noAdd")]]),
    sel("ins", ovT("pIns"), [["min", ovT("insMin")], ["flat1", ovT("insFlat")], ["none", ovT("insNone")]]), reset);
  const r = ovPlan(series), diff = r.net - r.baseNet;
  const kpis = ovEl("div", "ov-kpis ov-plan-kpis");
  const k = (id, label, value, sub, cls = "") => { const b = ovEl("div", "ov-kpi", ovEl("span", "ov-kpi-label", label), ovEl("strong", "ov-kpi-value", value), ovEl("span", "ov-kpi-sub " + cls, sub)); b.id = id; return b; };
  kpis.append(
    k("ov-plan-base", ovT("pBase"), ovKc(r.baseNet), ovT("pBaseSub")),
    k("ov-plan-net", ovT("pPlan"), ovKc(r.net), ovT("pDiff", { n: (diff >= 0 ? "+" : "−") + ovKc(Math.abs(diff)) }), diff >= 0 ? "good" : "bad"),
    k("ov-plan-ins", ovT("pInsK"), ovKc(r.ins), ovT("pInsSub")),
    k("ov-plan-after", ovT("pAfter"), ovKc(r.after), ovT("pMonth", { n: ovKc(r.after / 12) }), r.after >= 0 ? "good" : "bad"),
  );
  const need = ovEl("p", "ov-need", r.need == null ? "" : ovT("pNeed", { pct: (r.need < 0 ? "−" : "") + ovPct(r.need) }));
  need.id = "ov-plan-need";
  // Two-sided bars: right makes the money left grow, left makes it shrink.
  const rowH = 30, labelW = W < 480 ? 92 : 120, valueW = W < 480 ? 66 : 84;
  const svg = ovChart(W, r.deltas.length * rowH + 4, ovT("pBars"));
  const span = Math.max(1, ...r.deltas.map(([, v]) => Math.abs(v))), half = (W - labelW - 2 * valueW) / 2, mid = labelW + valueW + half;
  svg.append(ovSvg("line", { x1: mid, x2: mid, y1: 0, y2: r.deltas.length * rowH, class: "ov-grid" }));
  r.deltas.forEach(([key, v], j) => {
    const w = (Math.abs(v) / span) * half, y = j * rowH + 5;
    svg.append(ovSvg("text", { x: 0, y: y + 13 }, ovT(key)));
    svg.append(ovSvg("rect", { x: v >= 0 ? mid : mid - w, y, width: Math.max(1, w), height: 18, rx: 4, class: v >= 0 ? "ov-fill-in" : "ov-fill-out" }));
    svg.append(ovSvg("text", { x: v >= 0 ? mid + w + 6 : mid - w - 6, y: y + 13, "text-anchor": v >= 0 ? "start" : "end" }, (v >= 0 ? "+" : "−") + ovKc(Math.abs(v))));
  });
  card.append(inputs, kpis, need, ovEl("h4", "", ovT("pBars")), ovLegend([["in", ovT("better")], ["out", ovT("worse")]]), svg);
  return card;
}

function refreshOverview() {
  const seen = state.org + "|" + state.role;
  if (seen !== ovState.seen) {
    ovState.seen = seen;
    resetOverview();
    $("overview-tab").hidden = !FINANCE_ROLES.includes(state.role);
    if (!$("overview-view").hidden) run(loadOverview);
    return;
  }
  renderOverview(); // language change: same data, new words
}
new MutationObserver(refreshOverview).observe($("role-badge"), { childList: true, characterData: true, subtree: true });
let ovResize = 0;
window.addEventListener("resize", () => {
  clearTimeout(ovResize);
  ovResize = setTimeout(() => { if (!$("overview-view").hidden) renderOverview(); }, 150);
});
$("overview-tab").onclick = () => {
  setTab("overview");
  run(loadOverview);
};
// Phone home: the money card opens the overview.
$("phone-overview").onclick = () => {
  phoneGo("overview");
  run(loadOverview);
};
