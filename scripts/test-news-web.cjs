/* VietBiz News reader: every source of an item is shown as a link (decision G, Codex review PR #27).
   Mocked API, synthetic items only; no server needed. */
const { chromium } = require("playwright");
const path = require("node:path");
const assert = require("node:assert/strict");

const api = "http://news-api.test";
const items = [
  { id: "1", source_id: "vnexpress", source_name: "VnExpress", url: "https://vnexpress.net/a", category: "business",
    vi_title: "Tiêu đề thử nghiệm", vi_summary: "Tóm tắt thử nghiệm do biên tập viên viết.",
    sources: [{ name: "VnExpress", url: "https://vnexpress.net/a" }, { name: "Tuổi Trẻ", url: "https://tuoitre.vn/b" }] },
  // An older API answer without `sources` still shows its one link.
  { id: "2", source_id: "novinky", url: "https://www.novinky.cz/c", category: "law",
    vi_title: "Tin thử nghiệm cũ", vi_summary: "Câu trả lời API cũ không có danh sách nguồn." },
];

(async () => {
  const browser = await chromium.launch({
    executablePath: process.env.CHROMIUM_PATH || undefined,
    args: process.env.CHROMIUM_ARGS ? JSON.parse(process.env.CHROMIUM_ARGS) : [],
  });
  try {
    const page = await browser.newPage();
    const errors = [];
    page.on("pageerror", (e) => errors.push(String(e)));
    await page.route(api + "/v1/news", (r) => r.fulfill({
      contentType: "application/json", headers: { "access-control-allow-origin": "*" }, body: JSON.stringify(items) }));
    const file = "file://" + path.resolve(__dirname, "../apps/news-web/index.html");
    await page.goto(file + "?api=" + encodeURIComponent(api));
    await page.waitForSelector("article");
    const shown = await page.$$eval("article", (as) => as.map((a) => ({
      label: a.querySelector("small").textContent,
      links: [...a.querySelectorAll(".sources a")].map((l) => [l.textContent, l.href, l.rel, l.target]),
    })));
    assert.deepEqual(shown, [
      { label: "Kinh doanh • VnExpress", links: [
        ["VnExpress", "https://vnexpress.net/a", "noopener noreferrer", "_blank"],
        ["Tuổi Trẻ", "https://tuoitre.vn/b", "noopener noreferrer", "_blank"]] },
      { label: "Luật & Thuế • novinky", links: [["novinky", "https://www.novinky.cz/c", "noopener noreferrer", "_blank"]] },
    ]);
    assert.deepEqual(errors, []);
    console.log(JSON.stringify({ status: "passed", checks: 2, suite: "news-web" }));
  } finally {
    await browser.close();
  }
})().catch((error) => { console.error(error); process.exit(1); });
