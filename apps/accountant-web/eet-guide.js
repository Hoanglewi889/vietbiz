"use strict";
// EET 2.0, step by step (owner request 18.11.2026: "chỉ dẫn và làm theo quy trình để dễ hiểu
// nhất cho người dùng"). One step open at a time, in plain words, with the official link for it;
// the company's progress is kept by the API (GET/PUT …/eet-readiness) so owner and accountant see
// the same ticks. Without a company the guide still reads, only nothing is saved.
// Dates checked 18.11.2026 against the Financial Administration / Ministry of Finance.
const EET_CHECKED = "2026-11-18";
const EET_LINKS = {
  web: "https://eet.gov.cz/",
  mojeDane: "https://mojedane.gov.cz/",
  faq: "https://app.fs.gov.cz/dotazy-verejnosti/Content/UserFiles/Attachments/4265-O-EET2.0_DOTAZY.pdf",
};
const EET_UI = {
  vi: {
    title: "EET 2.0 — làm từng bước",
    intro: "Từ 1/1/2027 mọi khoản khách trả trực tiếp tại cửa hàng (tiền mặt, thẻ, mã QR, voucher) phải được ghi nhận và gửi cho cơ quan thuế. Làm lần lượt từng bước dưới đây, xong bước nào bấm “Đã xong” bước đó.",
    daysLeft: "Còn {n} ngày đến 1/1/2027.",
    started: "EET 2.0 đã bắt đầu từ 1/1/2027.",
    progress: "Đã xong {done}/{all} bước",
    doneMark: "Đã xong",
    undo: "Làm lại bước này",
    doneBy: "Đánh dấu bởi {who}, {when}",
    now: "Bước hiện tại",
    later: "Làm sau",
    noCompany: "Chọn công ty để lưu tiến độ. Bạn vẫn có thể đọc hướng dẫn.",
    readOnly: "Chỉ chủ và kế toán đánh dấu được các bước.",
    allDone: "Xong hết! Công ty đã sẵn sàng cho EET 2.0. Giữ chứng chỉ an toàn và ghi nhận mọi khoản trả trực tiếp.",
    notNeeded: "EET không áp dụng cho công ty này: chỉ nhận chuyển khoản / thanh toán online. Nếu sau này bắt đầu nhận tiền mặt, thẻ hay QR tại chỗ, chọn lại ở bước 1.",
    eetOff: "Đã chọn EET OFF: không ghi nhận từng khoản, nhưng trả thêm 1 400 Kč mỗi tháng vào thuế khoán. Chỉ dành cho thuế khoán mức 1 với thu nhập đến 1 triệu Kč/năm — bàn với kế toán và kiểm tra điều kiện trên eet.gov.cz.",
    change: "Chọn lại",
    official: "Nguồn chính thức",
    checked: "Thông tin kiểm tra ngày {date}. Đây là hướng dẫn, không phải tư vấn thuế.",
  },
  cs: {
    title: "EET 2.0 — krok za krokem",
    intro: "Od 1. 1. 2027 se evidují všechny platby přijaté přímo na místě (hotovost, karta, QR kód, stravenky). Projděte kroky postupně a hotový krok označte „Hotovo“.",
    daysLeft: "Do 1. 1. 2027 zbývá {n} dní.",
    started: "EET 2.0 běží od 1. 1. 2027.",
    progress: "Hotovo {done}/{all} kroků",
    doneMark: "Hotovo",
    undo: "Vrátit krok",
    doneBy: "Označil(a) {who}, {when}",
    now: "Aktuální krok",
    later: "Později",
    noCompany: "Vyberte firmu, aby se postup uložil. Návod si můžete přečíst i tak.",
    readOnly: "Kroky může označovat jen majitel a účetní.",
    allDone: "Hotovo! Firma je na EET 2.0 připravená. Certifikát chraňte a evidujte každou platbu na místě.",
    notNeeded: "EET se této firmy netýká: přijímá jen převody / online platby. Pokud začnete brát hotovost, kartu či QR na místě, změňte volbu v kroku 1.",
    eetOff: "Zvolen režim EET OFF: tržby se neevidují, ale k paušální dani se platí navíc 1 400 Kč měsíčně. Jen pro 1. pásmo paušální daně s příjmy do 1 mil. Kč ročně — proberte s účetní a ověřte podmínky na eet.gov.cz.",
    change: "Změnit volbu",
    official: "Oficiální zdroj",
    checked: "Ověřeno {date}. Jde o návod, ne o daňové poradenství.",
  },
};
// [step, title vi, title cs, why vi, why cs, how vi[], how cs[], links]
const EET_STEPS = [
  ["applies",
    "EET có áp dụng cho bạn không?", "Týká se vás EET?",
    "Áp dụng khi khách trả tiền trực tiếp tại chỗ: tiền mặt, thẻ, mã QR, voucher. Không áp dụng nếu bạn chỉ gửi hóa đơn và nhận chuyển khoản hoặc thanh toán online.",
    "Týká se plateb přijatých přímo na místě: hotovost, karta, QR kód, stravenky. Netýká se vás, pokud jen fakturujete a berete převody či online platby.",
    ["Tiệm nail, quán ăn, cửa hàng, quầy chợ: thường là CÓ.",
      "Thuế khoán (paušál) mức 1, thu nhập đến 1 triệu Kč/năm: có thể chọn EET OFF — trả thêm 1 400 Kč/tháng thay vì ghi nhận.",
      "Một số trường hợp được miễn (ví dụ người ZTP/P không có nhân viên, máy bán hàng tự động) — xem eet.gov.cz."],
    ["Nehtové studio, bistro, obchod, stánek: obvykle ANO.",
      "Paušální daň 1. pásma s příjmy do 1 mil. Kč ročně: lze zvolit EET OFF — 1 400 Kč měsíčně navíc místo evidence.",
      "Některé případy jsou vyňaty (např. ZTP/P bez zaměstnanců, prodejní automaty) — viz eet.gov.cz."],
    [["eet.gov.cz", EET_LINKS.web]]],
  ["dis",
    "Mở hộp thư thuế DIS+ trên MOJE daně", "Otevřete DIS+ na portálu MOJE daně",
    "Mọi việc đăng ký EET làm trong hộp thư thuế DIS+ trên cổng MOJE daně, miễn phí. Mở được từ 1/11/2026.",
    "Vše k EET se vyřizuje v Daňové informační schránce plus (DIS+) na portálu MOJE daně, zdarma. Otevřeno od 1. 11. 2026.",
    ["Đăng nhập bằng danh tính điện tử: Bankovní identita (qua ngân hàng), eObčanka hoặc Mobilní klíč eGovernmentu.",
      "Chưa từng dùng DIS+? Làm theo hướng dẫn kích hoạt trên eet.gov.cz.",
      "Kế toán có thể giúp nếu có giấy ủy quyền."],
    ["Přihlaste se elektronickou identitou: Bankovní identita, eObčanka nebo Mobilní klíč eGovernmentu.",
      "DIS+ jste ještě nepoužívali? Postup aktivace je na eet.gov.cz.",
      "S plnou mocí může pomoci účetní."],
    [["MOJE daně", EET_LINKS.mojeDane], ["eet.gov.cz", EET_LINKS.web]]],
  ["units",
    "Khai báo điểm bán (evidenční jednotka)", "Oznamte evidenční jednotky",
    "Mỗi nơi bạn nhận tiền của khách là một “điểm bán”: một tiệm, một quầy, một xe bán hàng.",
    "Evidenční jednotka je každé místo, kde přijímáte platby: provozovna, stánek, pojízdná prodejna.",
    ["Trong DIS+ mở mục “Elektronická evidence tržeb”.",
      "Thêm từng tiệm / quầy với địa chỉ của nó.",
      "Bán lưu động không có chỗ cố định: thường khai theo địa chỉ trụ sở."],
    ["V DIS+ otevřete sekci „Elektronická evidence tržeb“.",
      "Přidejte každou provozovnu / stánek s adresou.",
      "Prodej bez stálého místa: obvykle se uvádí sídlo."],
    [["Hỏi đáp chính thức (PDF)", EET_LINKS.faq]]],
  ["certificate",
    "Tạo chứng chỉ thu ngân (pokladní certifikát)", "Vygenerujte pokladní certifikát",
    "Chứng chỉ giúp máy tính tiền hoặc app gửi dữ liệu an toàn cho cơ quan thuế. Tạo miễn phí trong DIS+.",
    "Certifikát zajišťuje bezpečné odesílání tržeb finanční správě. Vygenerujete ho zdarma v DIS+.",
    ["Trong DIS+, mục “Elektronická evidence tržeb”, tạo chứng chỉ cho điểm bán.",
      "Cài chứng chỉ vào máy tính tiền, hoặc dùng cho app MOJE EET.",
      "Giữ kín như mật khẩu. Không gửi qua chat, không đưa vào VietBiz."],
    ["V DIS+ v sekci „Elektronická evidence tržeb“ vytvořte certifikát.",
      "Nahrajte ho do pokladny, nebo použijte v aplikaci MOJE EET.",
      "Chraňte ho jako heslo. Neposílejte ho chatem a nenahrávejte do VietBiz."],
    [["MOJE daně", EET_LINKS.mojeDane]]],
  ["tool",
    "Chọn cách ghi nhận: máy tính tiền hoặc app MOJE EET", "Zvolte pokladnu nebo aplikaci MOJE EET",
    "Nhà nước có app MOJE EET miễn phí cho cơ sở nhỏ, chạy trên điện thoại / máy tính bảng, từ 1/12/2026. Không bắt buộc dùng, có thể dùng máy tính tiền thương mại.",
    "Stát nabízí pro malé podnikatele bezplatnou aplikaci MOJE EET na telefon / tablet, od 1. 12. 2026. Je dobrovolná, lze použít i komerční pokladnu.",
    ["Đã có máy tính tiền: hỏi nhà cung cấp máy đã sẵn sàng cho EET 2.0 chưa.",
      "Tiệm nhỏ, ít giao dịch: thử app MOJE EET (cần chứng chỉ ở bước 4).",
      "Không bắt buộc in bill, trừ khi khách yêu cầu."],
    ["Máte pokladnu: ověřte u dodavatele připravenost na EET 2.0.",
      "Malá provozovna: vyzkoušejte MOJE EET (potřebuje certifikát z kroku 4).",
      "Účtenku tisknout nemusíte, jen když o ni zákazník požádá."],
    [["eet.gov.cz", EET_LINKS.web]]],
  ["pilot",
    "Tháng 1/2027: chạy thử, sau đó chính thức", "Leden 2027: zkušební provoz, pak ostrý",
    "Từ 1/1/2027 ghi nhận mọi khoản trả trực tiếp. Tháng 1 là tháng thử: cơ quan thuế chưa phạt, để bạn sửa lỗi kỹ thuật. Sau đó vi phạm có thể bị phạt tới 500 000 Kč.",
    "Od 1. 1. 2027 evidujte každou platbu na místě. Leden je zkušební: finanční správa nebude sankcionovat, abyste odladili techniku. Potom hrozí pokuta až 500 000 Kč.",
    ["Ngày đầu: thử vài giao dịch thật và kiểm tra đã gửi được.",
      "Dạy nhân viên đứng quầy cách ghi nhận.",
      "Có lỗi trong tháng 1: báo nhà cung cấp máy / kế toán ngay."],
    ["První den vyzkoušejte několik skutečných plateb a ověřte odeslání.",
      "Proškolte obsluhu u pokladny.",
      "Chyba v lednu: hned dodavatel pokladny / účetní."],
    [["eet.gov.cz", EET_LINKS.web]]],
];
const eetGuide = { data: null, seen: null, ticket: 0 };

function eetText(key, values) {
  const copy = EET_UI[lang === "cs" ? "cs" : "vi"][key];
  return values ? fill(copy, values) : copy;
}
function eetCanEdit() {
  return Boolean(state.org) && ["owner", "accountant"].includes(state.role);
}
function eetLink(label, href) {
  const a = text("a", label);
  a.href = href;
  a.target = "_blank";
  a.rel = "noopener noreferrer";
  return a;
}
function eetButton(label, onClick, cls = "secondary") {
  const b = text("button", label, cls);
  b.type = "button";
  b.onclick = () => run(onClick, b);
  return b;
}
async function eetSave(step, body) {
  const org = state.org;
  const answer = await request(base() + "/eet-readiness/" + step, json("PUT", body));
  if (state.org !== org) return;
  eetGuide.data = answer;
  renderEetGuide();
}
async function loadEetGuide() {
  const ticket = ++eetGuide.ticket;
  if (!state.org) return renderEetGuide();
  try {
    const answer = await request(base() + "/eet-readiness");
    if (ticket === eetGuide.ticket) eetGuide.data = answer;
  } catch (error) {
    if (ticket === eetGuide.ticket) eetGuide.data = null;
  }
  if (ticket === eetGuide.ticket) renderEetGuide();
}
function refreshEetGuide() {
  const seen = state.org + "|" + state.role;
  if (seen === eetGuide.seen) return renderEetGuide();
  eetGuide.seen = seen;
  eetGuide.data = null;
  loadEetGuide();
}
function renderEetGuide() {
  const box = $("eet-guide");
  if (!box) return;
  const vi = lang !== "cs",
    data = eetGuide.data,
    edit = eetCanEdit() && Boolean(data),
    status = {};
  if (data) for (const s of data.steps) status[s.step] = s;
  box.replaceChildren();
  box.append(text("h3", eetText("title")), text("p", eetText("intro"), "eet-intro"));
  const left = Math.ceil((Date.UTC(2027, 0, 1) - Date.parse(pragueToday() + "T00:00:00Z")) / 86400000);
  box.append(text("p", left > 0 ? eetText("daysLeft", { n: left }) : eetText("started"), "eet-countdown"));
  const choice = data ? data.choice : null,
    skipRest = choice === "no" || choice === "eet_off",
    shown = skipRest ? EET_STEPS.slice(0, 1) : EET_STEPS,
    done = shown.filter(([id]) => status[id] && status[id].done).length;
  if (data) {
    const bar = text("div", "", "eet-progress");
    bar.setAttribute("role", "progressbar");
    bar.setAttribute("aria-valuemin", "0");
    bar.setAttribute("aria-valuemax", String(shown.length));
    bar.setAttribute("aria-valuenow", String(done));
    const fillBar = text("span", "");
    fillBar.style.width = Math.round((100 * done) / shown.length) + "%";
    bar.append(fillBar);
    box.append(bar, text("p", eetText("progress", { done, all: shown.length }), "eet-progress-label"));
  }
  if (!state.org) box.append(text("p", eetText("noCompany"), "eet-note"));
  else if (data && !eetCanEdit()) box.append(text("p", eetText("readOnly"), "eet-note"));
  // The current step is the first one not done; with no company the first step is open.
  const current = shown.find(([id]) => !(status[id] && status[id].done));
  const list = text("ol", "", "eet-steps");
  shown.forEach(([id, tVi, tCs, wVi, wCs, hVi, hCs, links], index) => {
    const s = status[id],
      isDone = Boolean(s && s.done),
      isNow = current && current[0] === id,
      li = text("li", "", "eet-step" + (isDone ? " done" : isNow ? " now" : ""));
    li.dataset.step = id;
    const head = text("div", "", "eet-step-head");
    head.append(text("span", isDone ? "✓" : String(index + 1), "eet-num"), text("strong", vi ? tVi : tCs));
    head.append(text("span", isDone ? eetText("doneMark") : isNow ? eetText("now") : eetText("later"), "eet-badge"));
    li.append(head);
    if (isDone && s.done_by)
      li.append(text("p", eetText("doneBy", { who: s.done_by, when: s.done_at.slice(0, 10).split("-").reverse().join(". ") }), "eet-meta"));
    // Open the current step fully; done and later steps keep one line so the page stays short.
    const details = text("details", "", "eet-body");
    details.open = Boolean(isNow);
    details.append(text("summary", vi ? wVi : wCs));
    const how = text("ul", "");
    (vi ? hVi : hCs).forEach((line) => how.append(text("li", line)));
    details.append(how);
    const refs = text("p", eetText("official") + ": ", "eet-links");
    links.forEach(([label, href], i) => {
      if (i) refs.append(document.createTextNode(" · "));
      refs.append(eetLink(label, href));
    });
    details.append(refs);
    li.append(details);
    if (edit) {
      const actions = text("div", "", "eet-actions");
      if (id === "applies" && !isDone) {
        actions.append(
          eetButton(vi ? "Có, tôi nhận tiền tại chỗ" : "Ano, beru platby na místě", () => eetSave(id, { done: true, choice: "yes" }), "primary"),
          eetButton(vi ? "Không, chỉ chuyển khoản / online" : "Ne, jen převody / online", () => eetSave(id, { done: true, choice: "no" })),
          eetButton("EET OFF", () => eetSave(id, { done: true, choice: "eet_off" })),
        );
      } else if (isDone) actions.append(eetButton(id === "applies" ? eetText("change") : eetText("undo"), () => eetSave(id, { done: false }), "link-button"));
      else if (isNow) actions.append(eetButton(eetText("doneMark") + " ✓", () => eetSave(id, { done: true }), "primary"));
      li.append(actions);
    }
    list.append(li);
  });
  box.append(list);
  if (choice === "no") box.append(text("p", eetText("notNeeded"), "eet-result"));
  else if (choice === "eet_off") box.append(text("p", eetText("eetOff"), "eet-result"));
  else if (data && data.remaining.length === 0) box.append(text("p", eetText("allDone"), "eet-result ok"));
  box.append(text("p", eetText("checked", { date: EET_CHECKED.split("-").reverse().join(". ") }), "muted small"));
}
new MutationObserver(refreshEetGuide).observe($("role-badge"), { childList: true, characterData: true, subtree: true });
$("legal-tab").addEventListener("click", loadEetGuide);
refreshEetGuide();
