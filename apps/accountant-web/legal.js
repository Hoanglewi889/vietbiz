"use strict";
// "Pháp lý theo ngành" — key legal duties per industry, VI/CS, each with its source.
// Reference information checked on LEGAL_CHECKED; it is not legal or tax advice.
// When a rule changes, edit the item and the date; tests require a https source per item.
const LEGAL_CHECKED = "2026-11-09";
const LAW = {
  vat: "https://financnisprava.gov.cz/cs/financni-sprava/novinky/novinky-2025/informace-ke-zmenam-v-platcovstvi-dph-2025",
  eet: "https://www.epravo.cz/top/aktualne/eet-20-je-na-svete-od-ledna-2027-budou-podnikatele-evidovat-i-platby-kartou-a-qr-kodem-121639.html",
  eetGov: "https://eet.gov.cz/",
  cash: "https://www.dauc.cz/predpisy/128/254-2004-sb",
  vatAct: "https://www.zakonyprolidi.cz/cs/2004-235",
  trade: "https://www.zakonyprolidi.cz/cs/1991-455",
  spirits: "https://www.businessinfo.cz/navody/obsahove-naplne-zivnosti-koncesovanych/",
  tobacco: "https://www.szpi.gov.cz/soubor/tabakove-vyroby-povinnosti-hospodarskych-subjektu.aspx",
  addictive: "https://www.zakonyprolidi.cz/cs/2017-65",
  food: "https://www.zakonyprolidi.cz/cs/1997-110",
  prices: "https://www.zakonyprolidi.cz/cs/1990-526",
  restaurant: "https://www.businessinfo.cz/navody/hostinska-cinnost/",
  hygiene: "https://eur-lex.europa.eu/legal-content/CS/TXT/?uri=CELEX:32004R0852",
  szpiCatering: "https://www.szpi.gov.cz/en/article/press-release-of-the-ministry-of-agriculture-and-cafia-minister-vyborny-unifying-supervision-and-transferring-inspection-competencies-to-cafia-eliminates-previously-often-illogical-division-of-responsibilities.aspx",
  foodCard: "https://dostupnyadvokat.cz/blog/potravinarsky-prukaz",
  allergens: "https://eur-lex.europa.eu/legal-content/CS/TXT/?uri=CELEX:32011R1169",
  health: "https://www.zakonyprolidi.cz/cs/2000-258",
  nails: "https://www.businessinfo.cz/navody/pedikura-manikura-2/",
  hair: "https://www.businessinfo.cz/navody/holicstvi-kadernictvi/",
  bodyCare2026: "https://mzd.gov.cz/?p=219179",
  bodyCareTemplate: "https://khsova.cz/docs/01_obcanum/files/zs/PROVOZN%C3%8D_%C5%98%C3%81D_-_VZOR_Holi%C4%8Dstv%C3%AD_kade%C5%99nictv%C3%AD.pdf",
  civil: "https://www.zakonyprolidi.cz/cs/2012-89",
  cookies: "https://www.zakonyprolidi.cz/cs/2005-127",
  gdpr: "https://eur-lex.europa.eu/legal-content/CS/TXT/?uri=CELEX:32016R0679",
  oss: "https://vat-one-stop-shop.ec.europa.eu/",
};
// Each item: [vi title, cs title, vi text, cs text, legal basis, source url]
const LEGAL = [
  {
    id: "all",
    icon: "§",
    vi: "Mọi ngành",
    cs: "Všechny obory",
    items: [
      ["Đăng ký DPH theo doanh thu", "Registrace k DPH podle obratu",
        "Doanh thu năm dương lịch vượt 2 000 000 Kč → thành người nộp DPH từ 1/1 năm sau. Vượt 2 536 500 Kč → thành người nộp DPH ngay từ ngày hôm sau.",
        "Obrat za kalendářní rok nad 2 000 000 Kč → plátcem od 1. ledna následujícího roku. Nad 2 536 500 Kč → plátcem už ode dne následujícího po překročení.",
        "zákon č. 235/2004 Sb., o DPH (od 1. 1. 2025)", LAW.vat],
      ["EET 2.0 từ 1/1/2027", "EET 2.0 od 1. 1. 2027",
        "Phải ghi nhận mọi khoản thanh toán trực tiếp tại cửa hàng: tiền mặt, thẻ, mã QR, voucher. Chuyển khoản và cổng thanh toán online không thuộc diện này. Chứng chỉ lấy trên MOJE daně từ 1/11/2026. Không bắt buộc in bill, trừ khi khách yêu cầu. Một số trường hợp được miễn — kiểm tra trên eet.gov.cz.",
        "Evidují se všechny platby přijaté osobně na provozovně: hotovost, karta, QR kód, stravenky. Bezhotovostní platby na dálku (převod, platební brána) ne. Certifikát na MOJE daně od 1. 11. 2026. Účtenka jen na žádost zákazníka. Výjimky ověřte na eet.gov.cz.",
        "zákon o evidenci tržeb (EET 2.0), schválen 2026, účinnost 1. 1. 2027", LAW.eet],
      ["Hạn mức tiền mặt 270 000 Kč", "Limit hotovosti 270 000 Kč",
        "Cùng một người trả – người nhận, trong một ngày: tổng thanh toán trên 270 000 Kč phải chuyển khoản. Tab Thu chi tự cảnh báo.",
        "Mezi stejným plátcem a příjemcem během jednoho dne: platby nad 270 000 Kč jen bezhotovostně. Záložka Příjmy a výdaje upozorní.",
        "§ 4 zákona č. 254/2004 Sb.", LAW.cash],
      ["Lưu chứng từ thuế 10 năm", "Archivace daňových dokladů 10 let",
        "Hóa đơn, chứng từ thuế phải giữ 10 năm kể từ cuối kỳ tính thuế có giao dịch. Kho chứng từ số trong VietBiz không có nút xóa.",
        "Daňové doklady uchovávejte 10 let od konce zdaňovacího období, ve kterém se plnění uskutečnilo. Digitální archiv ve VietBiz doklady nemaže.",
        "§ 35 zákona č. 235/2004 Sb.", LAW.vatAct],
    ],
  },
  {
    id: "grocery",
    icon: "🛒",
    vi: "Potraviny (cửa hàng thực phẩm)",
    cs: "Potraviny (prodejna)",
    items: [
      ["Giấy phép kinh doanh", "Živnostenské oprávnění",
        "Bán lẻ thực phẩm là živnost tự do (volná živnost) „Výroba, obchod a služby neuvedené v přílohách 1 až 3“.",
        "Maloobchod s potravinami spadá do volné živnosti „Výroba, obchod a služby neuvedené v přílohách 1 až 3“.",
        "zákon č. 455/1991 Sb., živnostenský zákon", LAW.trade],
      ["Rượu mạnh cần koncese", "Lihoviny jen s koncesí",
        "Bán rượu mạnh (lihoviny) cần živnost koncese „Prodej kvasného lihu, konzumního lihu a lihovin“. Bia và rượu vang không cần koncese này.",
        "Prodej lihovin vyžaduje koncesi „Prodej kvasného lihu, konzumního lihu a lihovin“. Pivo a víno ji nevyžadují.",
        "příloha č. 3 zákona č. 455/1991 Sb.", LAW.spirits],
      ["Thuốc lá", "Tabákové výrobky",
        "Chỉ bán nguyên bao còn tem thuế, không bán dưới giá in trên tem. Để riêng khỏi hàng khác. Treo biển cấm bán cho người dưới 18 tuổi: tiếng Séc, chữ in hoa đen trên nền trắng, cao ít nhất 2 cm. Người bán phải từ 18 tuổi trở lên.",
        "Jen celé balení s neporušenou tabákovou nálepkou, ne pod cenou z nálepky. Odděleně od ostatního zboží. Viditelný zákaz prodeje osobám mladším 18 let: česky, černá velká písmena na bílém, min. 2 cm. Prodávající starší 18 let.",
        "zákon č. 353/2003 Sb.; zákon č. 65/2017 Sb.", LAW.tobacco],
      ["Không bán rượu, thuốc cho người dưới 18 tuổi", "Alkohol a tabák ne osobám pod 18 let",
        "Nếu nghi ngờ tuổi, yêu cầu khách xuất trình giấy tờ.",
        "V případě pochybností požadujte doklad totožnosti.",
        "zákon č. 65/2017 Sb.", LAW.addictive],
      ["Thực phẩm & ghi nhãn", "Potraviny a označování",
        "SZPI kiểm tra: hạn sử dụng, nhãn tiếng Séc, bảo quản đúng nhiệt độ. Giá bán phải niêm yết rõ.",
        "Dozor SZPI: data použitelnosti, české označení, teploty skladování. Ceny musí být zřetelně označeny.",
        "zákon č. 110/1997 Sb.; zákon č. 526/1990 Sb.", LAW.food],
    ],
  },
  {
    id: "bistro",
    icon: "🍜",
    vi: "Quán ăn, bistro",
    cs: "Bistro, restaurace",
    items: [
      ["Hostinská činnost — živnost nghề", "Hostinská činnost — řemeslná živnost",
        "Cần chứng minh trình độ chuyên môn (bằng cấp, kinh nghiệm), hoặc cử người phụ trách có trình độ (odpovědný zástupce).",
        "Je třeba doložit odbornou způsobilost, nebo ustanovit odpovědného zástupce.",
        "příloha č. 1 zákona č. 455/1991 Sb.", LAW.restaurant],
      ["Vệ sinh an toàn thực phẩm (HACCP)", "Hygiena potravin (HACCP)",
        "Phải có quy trình kiểm soát mối nguy theo nguyên tắc HACCP: nhiệt độ, nguồn gốc nguyên liệu, vệ sinh.",
        "Postupy založené na zásadách HACCP (teploty, původ surovin, sanitace).",
        "nařízení (ES) č. 852/2004, čl. 5", LAW.hygiene],
      ["SZPI kiểm tra quán ăn (từ 1/1/2025)", "Dozor SZPI nad stravováním (od 1. 1. 2025)",
        "Quán ăn, bistro mở cho khách vãng lai do SZPI kiểm tra, không còn là KHS. Khi mở, thay đổi hoặc đóng quán phải báo cho SZPI.",
        "Veřejně přístupné restaurace a bistra kontroluje SZPI místo KHS. Zahájení, změnu a ukončení činnosti oznamujete SZPI.",
        "převod dozoru na SZPI od 1. 1. 2025", LAW.szpiCatering],
      ["Không cần thẻ sức khỏe nữa — vẫn phải khám sức khỏe", "Zdravotní průkaz zrušen — prohlídky zůstávají",
        "Thẻ sức khỏe (zdravotní průkaz) đã bị bãi bỏ từ 1/7/2023. Chủ quán vẫn phải đưa nhân viên đi khám sức khỏe khi nhận việc (pracovnělékařská prohlídka) và lưu giấy xác nhận. Người chế biến thức ăn phải được hướng dẫn về vệ sinh.",
        "Zdravotní průkaz byl zrušen k 1. 7. 2023. Zaměstnavatel dál zajišťuje pracovnělékařské prohlídky a uchovává doklad; pracovníci s potravinami musí být poučeni o hygieně.",
        "novela zákona č. 258/2000 Sb. (od 1. 7. 2023); nařízení (ES) č. 852/2004, příloha II kap. XII", LAW.foodCard],
      ["14 chất gây dị ứng", "14 alergenů",
        "Phải thông báo cho khách món nào chứa chất gây dị ứng (gluten, đậu phộng, đậu nành, hải sản…), ví dụ ghi số dị ứng trên thực đơn.",
        "Zákazník musí být informován o alergenech v pokrmech (lepek, arašídy, sója, korýši…), např. čísly v jídelním lístku.",
        "nařízení (EU) č. 1169/2011, příloha II", LAW.allergens],
      ["Cấm hút thuốc trong quán", "Zákaz kouření v provozovně",
        "Không hút thuốc trong không gian quán. Không bán rượu cho người dưới 18 tuổi.",
        "Ve vnitřních prostorách se nekouří; alkohol ne osobám mladším 18 let.",
        "zákon č. 65/2017 Sb.", LAW.addictive],
    ],
  },
  {
    id: "nails",
    icon: "💅",
    vi: "Nail (manikúra, pedikúra)",
    cs: "Nehtové studio (manikúra, pedikúra)",
    items: [
      ["Pedikúra, manikúra — živnost nghề", "Pedikúra, manikúra — řemeslná živnost",
        "Cần chứng minh trình độ chuyên môn (chứng chỉ nghề, kinh nghiệm), hoặc cử người phụ trách có trình độ.",
        "Je třeba doložit odbornou způsobilost, nebo ustanovit odpovědného zástupce.",
        "příloha č. 1 zákona č. 455/1991 Sb.", LAW.nails],
      ["Từ 1/1/2026: chỉ cần báo KHS", "Od 1. 1. 2026: jen oznámení KHS",
        "Không còn phải nộp nội quy hoạt động (provozní řád) để KHS duyệt. Thay vào đó, báo bằng văn bản cho KHS ngày bắt đầu, phạm vi, địa điểm, các thay đổi và ngày ngừng hoạt động. Vẫn phải có provozní řád, làm đúng theo nó và trình khi bị kiểm tra.",
        "Provozní řád se již nepředkládá ke schválení. KHS se písemně oznamuje zahájení, rozsah, místo, podstatné změny a ukončení činnosti. Provozní řád musíte mít, dodržovat a předložit při kontrole.",
        "novela zákona č. 258/2000 Sb., účinná od 1. 1. 2026", LAW.bodyCare2026],
      ["Vệ sinh dụng cụ", "Hygiena nástrojů",
        "Sau mỗi khách: làm sạch, rửa, khử trùng dụng cụ. Đồ dùng một lần không được dùng lại. Không làm trên da bị bệnh, sẹo hay nốt ruồi.",
        "Po každém zákazníkovi očistit, umýt a dezinfikovat nástroje; jednorázové pomůcky znovu nepoužívat; nepracovat na nemocné kůži, jizvách a znaménkách.",
        "§ 19, 20 a 22 zákona č. 258/2000 Sb.", LAW.bodyCareTemplate],
    ],
  },
  {
    id: "hair",
    icon: "✂️",
    vi: "Cắt tóc (kadeřnictví)",
    cs: "Kadeřnictví, holičství",
    items: [
      ["Holičství, kadeřnictví — živnost nghề", "Holičství, kadeřnictví — řemeslná živnost",
        "Cần chứng minh trình độ chuyên môn (bằng nghề, kinh nghiệm), hoặc cử người phụ trách có trình độ.",
        "Je třeba doložit odbornou způsobilost, nebo ustanovit odpovědného zástupce.",
        "příloha č. 1 zákona č. 455/1991 Sb.", LAW.hair],
      ["Từ 1/1/2026: chỉ cần báo KHS", "Od 1. 1. 2026: jen oznámení KHS",
        "Quy định giống tiệm nail: báo KHS bằng văn bản, vẫn phải có provozní řád và làm đúng theo nó.",
        "Stejně jako u nehtových služeb: písemné oznámení KHS; provozní řád mít a dodržovat.",
        "novela zákona č. 258/2000 Sb., účinná od 1. 1. 2026", LAW.bodyCare2026],
      ["Vệ sinh & sức khỏe nhân viên", "Hygiena a zdravotní způsobilost",
        "Thay khăn cho từng khách, khử trùng dụng cụ. Nhân viên phải đủ sức khỏe và có hiểu biết về vệ sinh.",
        "Prádlo pro každého zákazníka čisté, nástroje dezinfikovat; pracovníci zdravotně způsobilí a se znalostmi hygieny.",
        "§ 19 a 20 zákona č. 258/2000 Sb.", LAW.bodyCareTemplate],
    ],
  },
  {
    id: "online",
    icon: "🛍️",
    vi: "Bán hàng online",
    cs: "Online prodej",
    items: [
      ["Khách được trả hàng trong 14 ngày", "Odstoupení do 14 dnů",
        "Khách cá nhân được trả hàng không cần lý do trong 14 ngày kể từ khi nhận hàng. Phải báo trước cho khách quyền này.",
        "Spotřebitel může odstoupit bez udání důvodu do 14 dnů od převzetí zboží; musí o tom být předem poučen.",
        "§ 1829 zákona č. 89/2012 Sb.", LAW.civil],
      ["Thông tin trước khi bán", "Informace před uzavřením smlouvy",
        "Ghi rõ tên, IČO, địa chỉ, giá cuối cùng đã gồm thuế và phí giao hàng, điều kiện mua bán (obchodní podmínky).",
        "Uveďte totožnost, IČO, adresu, konečnou cenu včetně daní a dopravy a obchodní podmínky.",
        "§ 1820 zákona č. 89/2012 Sb.", LAW.civil],
      ["Cookies & dữ liệu cá nhân", "Cookies a osobní údaje",
        "Cookie quảng cáo hay thống kê chỉ được dùng khi khách đồng ý trước. Dữ liệu khách hàng xử lý theo GDPR.",
        "Analytické a marketingové cookies jen s předchozím souhlasem; osobní údaje podle GDPR.",
        "§ 89 odst. 3 zákona č. 127/2005 Sb.; nařízení (EU) 2016/679", LAW.cookies],
      ["EET 2.0 & thanh toán online", "EET 2.0 a platby online",
        "Thanh toán qua cổng thanh toán hoặc chuyển khoản không phải ghi EET. Nhận tiền trực tiếp khi giao hàng tại chỗ thì phải ghi.",
        "Platby přes bránu nebo převodem se do EET neevidují; platby přijaté osobně ano.",
        "zákon o evidenci tržeb (EET 2.0)", LAW.eet],
      ["Bán cho khách cá nhân ở nước EU khác", "Prodej spotřebitelům v jiných státech EU",
        "Nếu tổng doanh thu bán cho khách cá nhân ở các nước EU khác vượt 10 000 EUR/năm, DPH tính theo nước của khách. Có thể khai qua hệ thống OSS.",
        "Nad 10 000 EUR ročně prodejů spotřebitelům do jiných států EU se DPH řídí státem zákazníka; lze přiznat přes OSS.",
        "zákon č. 235/2004 Sb.; režim OSS", LAW.oss],
    ],
  },
];
const legal = { filter: "all-industries" };

function renderLegal() {
  const vi = lang === "vi",
    chips = $("legal-filters"),
    grid = $("legal-grid");
  chips.replaceChildren();
  const chip = (id, title) => {
    const b = text("button", title, "legal-chip" + (legal.filter === id ? " active" : ""));
    b.type = "button";
    b.setAttribute("aria-pressed", String(legal.filter === id));
    b.onclick = () => {
      legal.filter = id;
      renderLegal();
    };
    return b;
  };
  chips.append(chip("all-industries", t("allIndustries")), ...LEGAL.map((g) => chip(g.id, g.icon + " " + g[lang])));
  grid.replaceChildren();
  for (const group of LEGAL) {
    if (legal.filter !== "all-industries" && legal.filter !== group.id) continue;
    const card = text("section", "", "legal-card");
    card.dataset.industry = group.id;
    card.append(text("h3", group.icon + " " + group[lang]));
    const list = text("ul", "");
    for (const [tVi, tCs, xVi, xCs, basis, url] of group.items) {
      const li = text("li", "");
      const link = text("a", t("legalSource"));
      link.href = url;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      const meta = text("small", basis + " · ");
      meta.append(link);
      li.append(text("strong", vi ? tVi : tCs), text("p", vi ? xVi : xCs), meta);
      list.append(li);
    }
    card.append(list);
    grid.append(card);
  }
  $("legal-checked").textContent = fill(t("legalChecked"), {
    date: LEGAL_CHECKED.split("-").reverse().join(". "),
  });
}
$("legal-tab").onclick = () => setTab("legal");
renderLegal();
