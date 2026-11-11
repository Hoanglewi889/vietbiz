/* Run against a disposable local demo server, never real records. */
const { chromium } = require("playwright");
const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");

(async () => {
  const browser = await chromium.launch({
    headless: true,
    executablePath: process.env.CHROMIUM_PATH || undefined,
    args: process.env.CHROMIUM_ARGS
      ? JSON.parse(process.env.CHROMIUM_ARGS)
      : [],
  });
  const page = await browser.newPage({
    viewport: { width: 1440, height: 1100 },
  });
  const errors = [];
  page.on("pageerror", (e) => errors.push(e.message));
  // Security headers (report 10.11.2026): the workspace must run under its CSP without violations.
  const cspViolations = [];
  page.on("console", (m) => {
    if (m.text().includes("Content Security Policy")) cspViolations.push(m.text());
  });
  const checks = [];
  const webDir = path.join(__dirname, "..", "apps", "accountant-web");
  const globals = ["i18n.js", "app.js", "invoices.js", "legal.js", "portfolio.js", "suppliers.js", "filing.js", "goods.js", "bank.js", "cash-control.js", "staff.js", "quick-create.js", "doc-flag.js", "qty-stepper.js", "range-calendar.js", "login.js"].flatMap((file) =>
    [...fs.readFileSync(path.join(webDir, file), "utf8").matchAll(/^(?:async )?function (\w+)|^(?:const|let) (\w+)/gm)]
      .map((m) => m[1] || m[2]),
  );
  const sharedNames = globals.filter((name, i) => globals.indexOf(name) !== i);
  const check = (name, condition) => {
    assert.ok(condition, name);
    checks.push(name);
  };
  check("Web scripts do not redeclare a global name", sharedNames.length === 0);
  const waitText = async (selector, text) =>
    page.waitForFunction(
      ({ selector, text }) =>
        document.querySelector(selector)?.textContent.includes(text),
      { selector, text },
    );
  const chooseFirst = async () => {
    await page
      .locator(".task-item")
      .filter({ hasText: "Bổ sung thông tin hóa đơn" })
      .click();
    await page.locator("#reply-body").waitFor();
  };
  const transition = async (status, reason = "") => {
    await page.locator("#transition-status").selectOption(status);
    await page.locator("#transition-reason").fill(reason);
    await page.locator(".transition-form button").click();
    await waitText(
      "#detail-panel .badge",
      { IN_REVIEW: "Chờ kế toán duyệt", DONE: "Hoàn tất", REOPENED: "Mở lại" }[
        status
      ],
    );
  };
  try {
    await page.goto(
      process.env.VIETBIZ_UI_URL || "http://127.0.0.1:8000/workspace/",
    );
    await page.locator("#demo").click();
    await waitText("#notice", "Dữ liệu mẫu sẵn sàng");
    // Accountant portfolio (CR-6): every client company, urgent first, one click to open.
    // Let the demo finish loading (three tasks, first one open) before switching views.
    await page.waitForFunction(() => document.querySelectorAll(".task-item").length === 3);
    await page.locator("#portfolio-tab:not([hidden])").waitFor();
    await page.locator("#portfolio-tab").click();
    await page.locator(".portfolio-row").first().waitFor();
    const firstClient = await page.locator(".portfolio-row").first().innerText();
    check(
      "Accountant sees the client portfolio with work counts",
      firstClient.includes("Potraviny Vltava") && firstClient.includes("Chờ duyệt") && firstClient.includes("Quá hạn"),
    );
    // CR-8: a client without a profile is flagged; saving one produces its filing calendar.
    check(
      "Portfolio flags a client without a profile",
      firstClient.includes("Thiếu hồ sơ") && (await page.locator("#profiles-missing").isVisible()),
    );
    await page.locator(".portfolio-row").first().getByRole("button", { name: "Thiếu hồ sơ" }).click();
    await waitText("#profile-status", "Chưa có hồ sơ");
    await page.locator("#profile-form-legal").selectOption("sro");
    await page.locator("#profile-vat").selectOption("monthly");
    await page.locator("#profile-employees").check();
    check(
      "OSVČ-only fields hide for a company and flat tax is closed to VAT payers",
      (await page.locator("#profile-osvc-fields").isHidden()) &&
        (await page.locator("#profile-band").isDisabled()),
    );
    await page.locator("#profile-save").click();
    await waitText("#profile-status", "Phiên bản 1");
    await waitText("#deadline-list", "Kontrolní hlášení (KH)");
    const calendarText = await page.locator("#deadline-list").innerText();
    check(
      "Saved profile produces VAT, control statement and payroll deadlines with the office",
      calendarText.includes("Tờ khai DPH và nộp thuế") &&
        calendarText.includes("Lương: nộp thuế khấu trừ") &&
        calendarText.includes("Finanční úřad") &&
        calendarText.includes("Potraviny Vltava"),
    );
    // Codex review, PR #13: no save while the selected company's profile is still loading.
    let releaseProfile;
    const profileGate = new Promise((resolve) => (releaseProfile = resolve));
    await page.route(/\/client-profile$/, async (route) => {
      if (route.request().method() === "GET") await profileGate;
      await route.continue();
    });
    // Reopening (as when switching straight from one company to another) starts a new load.
    await page.evaluate(() => {
      openProfile(document.querySelector("#profile-org").value);
    });
    check(
      "Saving is blocked while the selected company's profile is still loading",
      await page.locator("#profile-save").isDisabled(),
    );
    releaseProfile();
    await waitText("#profile-status", "Phiên bản 1");
    check("Saving is possible once that profile has loaded", await page.locator("#profile-save").isEnabled());
    await page.unroute(/\/client-profile$/);
    await page.waitForFunction(() => !document.querySelector("#portfolio-list").textContent.includes("Thiếu hồ sơ"));
    check(
      "Portfolio shows the next deadline once the profile exists",
      (await page.locator(".portfolio-row").first().innerText()).includes("Hạn tới:") &&
        (await page.locator("#profiles-missing").isHidden()),
    );
    await page.locator(".portfolio-row").first().getByRole("button", { name: "Mở công ty" }).click();
    await page.waitForFunction(
      () =>
        document.querySelector("#portfolio-view").hidden &&
        document.querySelector("#org").value !== "" &&
        // The demo company has documents to review, so the client opens on its documents.
        !document.querySelector("#docs-view").hidden,
    );
    check(
      "Opening a client switches to its workspace",
      (await page.locator("#org").inputValue()) !== "" &&
        (await page.locator("#docs-view").isVisible()),
    );
    await page.locator("#tasks-tab").click();
    await page.waitForFunction(() => document.querySelectorAll(".task-item").length === 3);
    await chooseFirst();
    check(
      "Sample workflow creates three tasks",
      (await page.locator(".task-item").count()) === 3,
    );
    check(
      "Company summary is loaded",
      (await page.locator("#metric-active").innerText()) === "3",
    );
    check(
      "Internal accountant note is shown to accountant",
      (await page.locator("#detail-panel").innerText()).includes(
        "Ghi chú nội bộ mẫu",
      ),
    );
    const roles = await page
      .locator("#demo-role option")
      .evaluateAll((options) => options.map((o) => o.value));
    await page.locator("#demo-role").selectOption(roles[1]);
    await waitText("#role-badge", "Chủ cửa hàng");
    await chooseFirst();
    check(
      "Owner cannot see accountant-only note",
      !(await page.locator("#detail-panel").innerText()).includes(
        "Ghi chú nội bộ mẫu",
      ),
    );
    await page
      .locator("#reply-body")
      .fill("Đã kiểm tra thông tin mẫu. / Ověřeno.");
    await page.locator(".comment-form button").click();
    await waitText("#detail-panel", "Đã kiểm tra thông tin mẫu.");
    check("Client reply is persisted", true);
    await transition("IN_REVIEW");
    check(
      "Owner cannot mark the task done",
      (await page.locator("#transition-status").count()) === 0,
    );
    await page.locator("#demo-role").selectOption(roles[0]);
    await waitText("#role-badge", "Kế toán");
    await chooseFirst();
    await transition("DONE");
    await waitText("#metric-done", "1");
    check("Accountant completes submitted work", true);
    await transition("REOPENED", "Cần kiểm tra thêm dữ liệu mẫu.");
    check(
      "Reopening preserves the completion history",
      (await page.locator(".history").innerText()).includes(
        "Hoàn tất → Mở lại",
      ),
    );
    await page.locator("#new-task").click();
    const hostile = '<img src=x onerror="window.injected=true">';
    await page.locator("#task-title").fill(hostile);
    await page.locator("#task-description").fill("Synthetic text safety check");
    await page.locator("#create-submit").click();
    await waitText("#detail-panel .detail-title", hostile);
    check(
      "User input is rendered as text",
      await page.evaluate(
        () =>
          !window.injected &&
          document.querySelectorAll("#detail-panel img").length === 0,
      ),
    );
    await page.locator("#language").selectOption("cs");
    check(
      "Czech UI labels are translated",
      (await page.locator("#new-task").innerText()) === "+ Nový požadavek",
    );
    check(
      "Language does not change company context",
      (await page.locator("#org").inputValue()).length > 0,
    );
    await page.locator("#language").selectOption("vi");
    await page.locator("#docs-tab").click();
    check(
      "Related original remains in documents view",
      (await page.locator(".document").count()) === 1,
    );
    const downloadPromise = page.waitForEvent("download");
    await page
      .locator(".document button")
      .filter({ hasText: "Tải bản gốc" })
      .click();
    const download = await downloadPromise;
    check(
      "Authorized original download works",
      download.suggestedFilename() === "sample-only.png",
    );
    // Invoice data (CR-1): original beside the fields and the VAT Act check.
    await page
      .locator(".document button")
      .filter({ hasText: "Dữ liệu hóa đơn" })
      .click();
    await waitText("#check-body", "Thiếu DIČ người bán");
    await page.locator("#extract-preview img").waitFor();
    const checkText = async () => page.locator("#check-body").innerText();
    check(
      "Invoice data shows the original beside the fields",
      (await page.locator("#extract-preview img").count()) === 1,
    );
    check(
      "Seeded receipt is checked as a simplified document",
      (await checkText()).includes("Hóa đơn đơn giản"),
    );
    check(
      "Missing supplier DIČ cites the VAT Act",
      (await checkText()).includes("§ 29 odst. 1 písm. b)"),
    );
    await page.locator("#x-supplier_vat_id").fill("CZ00000001");
    await page.locator("#extract-save").click();
    await waitText("#check-body", "Phiên bản 2");
    check(
      "Correcting the field clears the finding in a new revision",
      (await checkText()).includes("Đủ nội dung bắt buộc"),
    );
    const secondTax = page.locator('#x-lines .vat-line:nth-child(2) [data-key="tax"]');
    await secondTax.fill("170,00");
    await page.locator("#extract-save").click();
    await waitText("#check-body", "Tiền thuế dòng 2 không khớp");
    check(
      "Czech decimal comma is accepted and a wrong tax is flagged",
      (await checkText()).includes("hóa đơn ghi 170.00"),
    );
    await secondTax.fill("168.00");
    await page.locator("#extract-save").click();
    await waitText("#check-body", "Phiên bản 4");
    // CR-9: goods lines pasted from a spreadsheet, checked against the VAT bases, grouped.
    await page.locator("#goods-section:not([hidden])").waitFor();
    await page.locator("#goods-paste").fill("SYN-1;Pivo 0,5 l;24;ks;25,00;21;600,00\nincomplete row");
    await page.locator("#goods-save").click();
    await waitText("#goods-error", "Dòng 2 chưa đủ cột");
    check("A pasted row with missing columns is named before saving", (await page.locator(".goods-table tr").count()) === 0);
    await page.locator("#goods-paste").fill(
      [
        "SYN-1\tSynthetic pivo 0,5 l (24)\t24\tks\t25,00\t21\t600,00",
        "SYN-2\tSynthetic limonáda\t10\tks\t20,00\t21\t",
        "SYN-3\tSynthetic tyčinka (40)\t40\tks\t25,00\t12\t1 000,00",
        "SYN-3\tSynthetic tyčinka (40)\t40\tks\t25,00\t12\t1 000,00",
      ].join("\n"),
    );
    await page.locator("#goods-save").click();
    await waitText("#goods-status", "4 dòng · phiên bản 1");
    const goodsText = await page.locator("#goods-section").innerText();
    check(
      "Goods lines keep quantity, price and VAT, with the net computed when blank",
      (await page.locator(".goods-table tr").count()) === 5 &&
        goodsText.includes("10 ks") &&
        goodsText.includes("200,00"),
    );
    check(
      "Repeated lines are flagged and line totals match the invoice's VAT bases",
      goodsText.includes("Dòng 3, 4 giống hệt nhau") && !goodsText.includes("tổng các dòng"),
    );
    await page.locator(".goods-table tr").nth(1).locator("select").selectOption("beer");
    await waitText("#notice", "Đã lưu");
    check(
      "A goods group is chosen per line",
      (await page.locator(".goods-table tr").nth(1).locator("select").inputValue()) === "beer",
    );
    await page.locator("#language").selectOption("cs");
    check(
      "Invoice check is translated to Czech",
      (await checkText()).includes("Povinné náležitosti úplné"),
    );
    await page.locator("#language").selectOption("vi");
    const dialogTop = () =>
      page.evaluate(() => (document.querySelector("#extract-dialog").scrollTop = 0));
    if (process.env.VIETBIZ_SCREENSHOT_DIR) {
      fs.mkdirSync(process.env.VIETBIZ_SCREENSHOT_DIR, { recursive: true });
      await dialogTop();
      await page.screenshot({
        path: path.join(process.env.VIETBIZ_SCREENSHOT_DIR, "invoice-desktop.png"),
      });
    }
    await page.setViewportSize({ width: 390, height: 844 });
    check(
      "Invoice data dialog fits a 390 px screen",
      await page.evaluate(() => {
        const d = document.querySelector("#extract-dialog");
        return (
          d.scrollWidth <= d.clientWidth + 1 &&
          document.documentElement.scrollWidth <= innerWidth
        );
      }),
    );
    if (process.env.VIETBIZ_SCREENSHOT_DIR) {
      await dialogTop();
      await page.screenshot({
        path: path.join(process.env.VIETBIZ_SCREENSHOT_DIR, "invoice-mobile.png"),
      });
    }
    await page.setViewportSize({ width: 1440, height: 1100 });
    // Unsaved edits must not be dropped by a decision (Codex review, PR #3).
    await page.locator("#x-document_number").fill("DEMO-204-EDITED");
    await page.locator("#extract-approve").click();
    await waitText("#extract-error", "Lưu dữ liệu trước");
    check(
      "Approving with unsaved edits is blocked",
      !(await page.locator("#extract-save").isDisabled()) &&
        (await page.locator("#x-document_number").inputValue()) ===
          "DEMO-204-EDITED",
    );
    await page.locator("#x-document_number").fill("DEMO-204");
    await page.locator("#extract-approve").click();
    await waitText("#extract-error", "Chứng từ đã được quyết định");
    check(
      "Approving from the dialog locks the invoice data",
      await page.locator("#extract-save").isDisabled(),
    );
    await page.keyboard.press("Escape");
    await page.waitForFunction(
      () => !document.querySelector("#extract-dialog").open,
    );
    await page.waitForFunction(
      () => !document.querySelector("#extract-preview img"),
    );
    check(
      "Closing the dialog releases the original preview",
      (await page.locator("#extract-preview img").count()) === 0,
    );
    // ISDOC.PDF: an owner uploads an e-invoice; its VAT data is read without typing.
    await page.locator("#demo-role").selectOption({ label: "Chủ cửa hàng" });
    await page.waitForFunction(
      () => !document.querySelector("#upload-button").disabled,
    );
    await page.locator("#docs-tab").click();
    await page
      .locator("#upload-file")
      .setInputFiles(path.join(__dirname, "fixtures", "synthetic-isdoc.pdf"));
    await page.locator("#upload-button").click();
    await page.waitForFunction(
      () => document.querySelectorAll(".document").length === 2,
    );
    await page
      .locator(".document")
      .filter({ hasText: "synthetic-isdoc.pdf" })
      .getByRole("button", { name: "Dữ liệu hóa đơn" })
      .click();
    await waitText("#x-source", "ISDOC");
    await waitText("#check-body", "Phiên bản 1");
    check(
      "ISDOC data is read from the uploaded PDF",
      (await page.locator("#x-supplier_vat_id").inputValue()) === "CZ00000001" &&
        (await page.locator("#x-lines .vat-line").count()) === 2,
    );
    check(
      "Imported ISDOC data passes the VAT Act check",
      (await page.locator("#check-body").innerText()).includes(
        "Đủ nội dung bắt buộc",
      ),
    );
    if (process.env.VIETBIZ_SCREENSHOT_DIR) {
      await dialogTop();
      await page.screenshot({
        path: path.join(process.env.VIETBIZ_SCREENSHOT_DIR, "isdoc-desktop.png"),
      });
    }
    await page.keyboard.press("Escape");
    await page.waitForFunction(
      () => !document.querySelector("#extract-dialog").open,
    );
    // Digital archive (CR-3): totals, search, categories, duplicate files.
    const docCount = () => page.locator(".document").count();
    await waitText("#archive-summary", "2 chứng từ");
    check(
      "Archive totals the stored invoices",
      (await page.locator("#archive-summary").innerText()).includes("Tổng CZK"),
    );
    await page.locator("#f-q").fill("Synthetic Wholesale");
    await page.waitForFunction(() => document.querySelectorAll(".document").length === 1);
    check("Archive search finds the supplier", (await docCount()) === 1);
    await page.locator(".category-select").first().selectOption("goods");
    await waitText("#notice", "Đã lưu");
    await page.locator("#f-clear").click();
    await page.waitForFunction(() => document.querySelectorAll(".document").length === 2);
    await page.locator("#f-category").selectOption("goods");
    await page.waitForFunction(() => document.querySelectorAll(".document").length === 1);
    await waitText("#category-bars", "Hàng hóa để bán");
    check(
      "Spending is split by supplier and by category",
      (await page.locator("#supplier-panel").isVisible()) &&
        (await page.locator("#supplier-list .supplier-row").count()) >= 1 &&
        (await page.locator("#category-bars").innerText()).includes("Hàng hóa để bán"),
    );
    check(
      "Category filter shows only categorised documents",
      (await page.locator(".document strong").first().innerText()).includes(
        "Synthetic Wholesale",
      ),
    );
    await page.locator("#goods-month").fill("2026-10");
    await waitText("#goods-groups", "Bia");
    const goodsReport = await page.locator("#goods-panel").innerText();
    check(
      "Monthly goods intake shows groups with money and quantity, and the top items",
      goodsReport.includes("24 ks") &&
        goodsReport.includes("Chưa xếp nhóm") &&
        goodsReport.includes("Synthetic tyčinka (40)") &&
        goodsReport.includes("1 hóa đơn có dòng hàng"),
    );
    await page.locator("#f-clear").click();
    await page.waitForFunction(() => document.querySelectorAll(".document").length === 2);
    await page
      .locator("#upload-file")
      .setInputFiles(path.join(__dirname, "fixtures", "synthetic-isdoc.pdf"));
    await page.locator("#upload-button").click();
    await waitText("#notice", "đã được tải lên trước đó");
    check("Identical file upload is refused", (await docCount()) === 2);
    // Codex review, PR #5: a slower, older archive response must not replace a newer one.
    let releaseSlow;
    const slowGate = new Promise((resolve) => (releaseSlow = resolve));
    await page.route(/\/archive\?q=slow/, async (route) => {
      await slowGate;
      await route.continue();
    });
    const slowSent = page.waitForRequest(/\/archive\?q=slow/);
    await page.locator("#f-q").fill("slow");
    await slowSent;
    const fastDone = page.waitForResponse(/\/archive\?q=isdoc/);
    await page.locator("#f-q").fill("isdoc");
    await fastDone;
    await page.waitForFunction(() => document.querySelectorAll(".document").length === 1);
    const slowDone = page.waitForResponse(/\/archive\?q=slow/);
    releaseSlow();
    await slowDone;
    await page.waitForTimeout(100);
    check(
      "An older archive response does not overwrite newer filter results",
      (await docCount()) === 1 &&
        (await page.locator("#f-q").inputValue()) === "isdoc",
    );
    await page.unroute(/\/archive\?q=slow/);
    // Codex review, PR #5: saved invoice data updates the archive row at once.
    await page
      .locator(".document")
      .getByRole("button", { name: "Dữ liệu hóa đơn" })
      .click();
    await waitText("#check-body", "Phiên bản 1");
    await page.locator("#x-document_number").fill("SYN-EDITED-7");
    await page.locator("#extract-save").click();
    await waitText("#check-body", "Phiên bản 2");
    await page.keyboard.press("Escape");
    await waitText("#document-list", "SYN-EDITED-7");
    check(
      "Saving invoice data refreshes the archive row",
      (await page.locator(".document").first().innerText()).includes("SYN-EDITED-7"),
    );
    // Codex review, PR #5: the task document picker ignores archive filters.
    await page.locator("#f-q").fill("no-such-invoice");
    await page.waitForFunction(() => document.querySelectorAll(".document").length === 0);
    await page.locator("#tasks-tab").click();
    await page.locator("#new-task").click();
    check(
      "Task document picker lists every document while a filter is active",
      (await page.locator("#task-document option").count()) === 3,
    );
    await page.keyboard.press("Escape");
    await page.locator("#docs-tab").click();
    await page.locator("#f-clear").click();
    await page.waitForFunction(() => document.querySelectorAll(".document").length === 2);
    await page.setViewportSize({ width: 390, height: 844 });
    check(
      "Archive view fits a 390 px screen",
      await page.evaluate(() => {
        const view = document.querySelector("#docs-view");
        const edge =
          view.getBoundingClientRect().right -
          parseFloat(getComputedStyle(view).paddingRight);
        const inside = [
          ...document.querySelectorAll(
            "#archive-filters input, #archive-filters select, .category-select",
          ),
        ].every((el) => el.getBoundingClientRect().right <= edge + 0.5);
        return inside && document.documentElement.scrollWidth <= innerWidth;
      }),
    );
    if (process.env.VIETBIZ_SCREENSHOT_DIR)
      await page.screenshot({
        path: path.join(process.env.VIETBIZ_SCREENSHOT_DIR, "archive-mobile.png"),
        fullPage: true,
      });
    await page.setViewportSize({ width: 1440, height: 1100 });
    if (process.env.VIETBIZ_SCREENSHOT_DIR)
      await page.screenshot({
        path: path.join(process.env.VIETBIZ_SCREENSHOT_DIR, "archive-desktop.png"),
        fullPage: true,
      });
    // Cashbook and monthly report (CR-4).
    await page.locator("#cash-tab").click();
    await page.locator("#cash-report h3").waitFor();
    check("Cashbook tab opens for the owner", await page.locator("#cash-view").isVisible());
    await page.locator("#c-kind").selectOption("income");
    await page.locator("#c-amount").fill("12 500,50");
    await page.locator("#c-method").selectOption("cash");
    await page.locator("#c-category").selectOption("sales");
    await page.locator("#cash-submit").click();
    await page.waitForFunction(() => document.querySelectorAll(".cash-entry").length === 1);
    check(
      "Income with a Czech decimal comma is recorded and totalled",
      (await page.locator(".cash-entry").first().innerText()).includes("Tiền bán hàng") &&
        (await page.locator(".cash-total").count()) === 3 &&
        (await page.locator(".cash-total.negative").count()) === 0,
    );
    // Codex review, PR #6: the server books it but the answer is lost; a second click must not double it.
    let dropped = 0;
    await page.route(/\/cashbook$/, async (route) => {
      if (route.request().method() !== "POST" || dropped++) return route.continue();
      await route.fetch();
      await route.abort("connectionreset");
    });
    await page.locator("#c-kind").selectOption("expense");
    await page.locator("#c-amount").fill("450");
    await page.locator("#c-counterparty").fill("Synthetic retry");
    await page.locator("#cash-submit").click();
    await page.waitForFunction(() => document.querySelector("#notice").classList.contains("error"));
    await page.locator("#cash-submit").click();
    await page.waitForFunction(() => document.querySelector("#c-amount").value === "");
    await page.unroute(/\/cashbook$/);
    // The list reloads after the form clears; wait for it before counting rows.
    await waitText("#cash-list", "Synthetic retry");
    check(
      "A retried payment after a lost response is booked once",
      (await page.locator(".cash-entry").filter({ hasText: "Synthetic retry" }).count()) === 1,
    );
    await page.locator("#c-kind").selectOption("expense");
    await page.locator("#c-amount").fill("300000");
    await page.locator("#c-method").selectOption("cash");
    await page.locator("#c-category").selectOption("equipment");
    await page.locator("#c-counterparty").fill("Synthetic Auto s.r.o.");
    await page.locator("#cash-submit").click();
    await waitText("#cash-report", "254/2004");
    check(
      "Cash above the legal limit is flagged with the law",
      (await page.locator(".cash-warning").innerText()).includes("§ 4 zákona č. 254/2004 Sb.") &&
        (await page.locator(".cash-total.negative").count()) === 1,
    );
    await page
      .locator(".cash-entry")
      .filter({ hasText: "Synthetic Auto" })
      .getByRole("button", { name: "Hủy khoản" })
      .click();
    await page.locator(".void-form input").fill("Synthetic: wrong amount");
    await page.locator(".void-form button").click();
    await page.waitForFunction(() => !document.querySelector(".cash-warning"));
    check(
      "Voiding keeps the entry visible and removes it from totals",
      (await page.locator(".cash-entry.voided").count()) === 1 &&
        (await page.locator(".cash-entry.voided").innerText()).includes("wrong amount") &&
        (await page.locator(".cash-total.negative").count()) === 0,
    );
    await page.locator("#cash-month").fill("2026-10");
    await page.locator("#cash-month").dispatchEvent("change");
    await waitText("#cash-report", "Hóa đơn đã duyệt nhưng chưa ghi thanh toán");
    await page.locator(".cash-unrecorded button").first().click();
    check(
      "An approved invoice pre-fills its payment",
      (await page.locator("#c-amount").inputValue()) === "3208.00" &&
        (await page.locator("#c-linked").isVisible()),
    );
    await page.locator("#cash-submit").click();
    await page.waitForFunction(() => document.querySelector("#c-linked").hidden);
    await page.locator("#cash-month").fill("2026-10");
    await page.locator("#cash-month").dispatchEvent("change");
    await page.waitForFunction(() => !document.querySelector(".cash-unrecorded"));
    check(
      "A recorded payment leaves the unpaid invoice list",
      (await page.locator(".cash-unrecorded").count()) === 0,
    );
    await page.locator("#language").selectOption("cs");
    check(
      "Cashbook is translated to Czech",
      (await page.locator("#cash-tab").innerText()) === "Příjmy a výdaje" &&
        (await page.locator("#cash-report h3").innerText()).startsWith("Měsíc"),
    );
    await page.locator("#language").selectOption("vi");
    await page.locator("#cash-month").fill(await page.evaluate(() =>
      new Intl.DateTimeFormat("sv-SE", { timeZone: "Europe/Prague" }).format(new Date()).slice(0, 7)));
    await page.locator("#cash-month").dispatchEvent("change");
    await page.waitForFunction(() => document.querySelectorAll(".cash-entry").length >= 2);
    if (process.env.VIETBIZ_SCREENSHOT_DIR)
      await page.screenshot({
        path: path.join(process.env.VIETBIZ_SCREENSHOT_DIR, "cashbook-desktop.png"),
        fullPage: true,
      });
    await page.setViewportSize({ width: 390, height: 844 });
    check(
      "Cashbook fits a 390 px screen",
      await page.evaluate(() => {
        const view = document.querySelector("#cash-view");
        const edge = view.getBoundingClientRect().right -
          parseFloat(getComputedStyle(view).paddingRight);
        return (
          document.documentElement.scrollWidth <= innerWidth &&
          [...view.querySelectorAll("input, select, button, .cash-total, .cash-entry")]
            .every((el) => el.getBoundingClientRect().right <= edge + 1)
        );
      }),
    );
    if (process.env.VIETBIZ_SCREENSHOT_DIR)
      await page.screenshot({
        path: path.join(process.env.VIETBIZ_SCREENSHOT_DIR, "cashbook-mobile.png"),
        fullPage: true,
      });
    await page.setViewportSize({ width: 1440, height: 1100 });
    // Issued invoices (CR-5): seller profile, draft, issue, print, ISDOC.
    await page.locator("#invoices-tab").click();
    await page.locator("#invoice-list .empty").waitFor();
    check(
      "Invoices start by asking for the seller details",
      await page.locator("#billing-details").evaluate((d) => d.open),
    );
    await page.locator("#b-legal_name").fill("Synthetic Bistro s.r.o.");
    await page.locator("#b-address").fill("Ukázková 1, 110 00 Praha 1");
    await page.locator("#b-ico").fill("00000019");
    await page.locator("#b-dic").fill("CZ 000 000 19");
    await page.locator("#b-vat_payer").check();
    await page.locator("#b-iban").fill("CZ65 0800 0000 1920 0014 5399");
    await page.locator("#billing-save").click();
    await page.waitForFunction(() => !document.querySelector("#billing-details").open);
    await page.locator("#new-invoice").click();
    await page.locator("#i-customer_name").fill("Synthetic Customer a.s.");
    await page.locator("#i-customer_address").fill("Vzorová 2, 602 00 Brno");
    await page.locator("#i-customer_dic").fill("CZ00000027");
    const invLine = (n) => page.locator(`#i-lines .invoice-line:nth-child(${n})`);
    await invLine(1).locator('[data-key="description"]').fill("Phở bò");
    await invLine(1).locator('[data-key="quantity"]').fill("3");
    await invLine(1).locator('[data-key="unit_price"]').fill("99,90");
    await page.locator("#i-add-line").click();
    await invLine(2).locator('[data-key="description"]').fill("Catering");
    await invLine(2).locator('[data-key="quantity"]').fill("2");
    await invLine(2).locator('[data-key="unit"]').fill("hod");
    await invLine(2).locator('[data-key="unit_price"]').fill("45,50");
    await invLine(2).locator('[data-key="vat_rate"]').selectOption("12");
    await page.locator("#invoice-save").click();
    await waitText("#i-totals", "464,56");
    check(
      "The server totals the draft with VAT per rate",
      (await page.locator("#i-totals").innerText()).includes("62,94"),
    );
    await page.locator("#invoice-issue").click();
    await page.waitForFunction(() => document.querySelector("#invoice-form").hidden);
    const year = await page.evaluate(() => new Intl.DateTimeFormat("sv-SE", { timeZone: "Europe/Prague" }).format(new Date()).slice(0, 4));
    await waitText("#invoice-list", year + "-0001");
    check(
      "Issuing assigns the first number of the year and freezes the invoice",
      (await page.locator(".invoice-row").count()) === 1 &&
        (await page.locator(".invoice-row").getByRole("button", { name: "Sửa" }).count()) === 0,
    );
    await page.locator(".invoice-row").getByRole("button", { name: "Xem & in" }).click();
    await page.locator("#print-dialog[open]").waitFor();
    await page.locator("#invoice-print .paper-qr img").waitFor();
    check(
      "A bank-paid invoice prints a QR Platba code; a VAT payer sees no threshold tracker",
      (await page.locator("#invoice-print .paper-qr img").getAttribute("src")).startsWith("data:image/svg+xml") &&
        (await page.locator("#vat-threshold").isHidden()),
    );
    // Codex review, PR #15: a late QR for an earlier print view is not added to the current one.
    await page.locator("#close-print").click();
    let releaseQr;
    const qrGate = new Promise((resolve) => (releaseQr = resolve));
    let heldQr = false;
    await page.route(/\/payment-qr$/, async (route) => {
      if (!heldQr) {
        heldQr = true;
        await qrGate;
      }
      await route.continue();
    });
    await page.locator(".invoice-row").getByRole("button", { name: "Xem & in" }).click();
    await page.waitForFunction(() => document.querySelector("#print-dialog").open);
    await page.locator("#close-print").click();
    await page.locator(".invoice-row").getByRole("button", { name: "Xem & in" }).click();
    await page.locator("#invoice-print .paper-qr img").waitFor();
    const lateQr = page.waitForResponse(/\/payment-qr$/);
    releaseQr();
    await lateQr;
    await page.waitForTimeout(200);
    check(
      "A late QR response for an earlier print view is ignored",
      (await page.locator("#invoice-print .paper-qr img").count()) === 1,
    );
    await page.unroute(/\/payment-qr$/);
    const paper = await page.locator("#invoice-print").innerText();
    check(
      "The printable invoice carries the § 29 details in Czech",
      paper.includes("Faktura – daňový doklad č. " + year + "-0001") &&
        paper.includes("DIČ: CZ00000019") &&
        paper.includes("Datum uskutečnění zdanitelného plnění") &&
        paper.includes("Variabilní symbol") &&
        paper.includes("Celkem k úhradě"),
    );
    if (process.env.VIETBIZ_SCREENSHOT_DIR)
      await page.screenshot({
        path: path.join(process.env.VIETBIZ_SCREENSHOT_DIR, "invoice-print.png"),
      });
    await page.locator("#close-print").click();
    const [isdocFile] = await Promise.all([
      page.waitForEvent("download"),
      page.locator(".invoice-row").getByRole("button", { name: "Tải ISDOC" }).click(),
    ]);
    const isdocText = fs.readFileSync(await isdocFile.path(), "utf8");
    check(
      "ISDOC export downloads with VAT data",
      isdocFile.suggestedFilename() === "faktura-" + year + "-0001.isdoc" &&
        isdocText.includes("<VATApplicable>true</VATApplicable>") &&
        isdocText.includes("<PayableAmount>464.56</PayableAmount>"),
    );
    // CR-12: staff, shifts with tips and Labour Code prompts; the daily cash close.
    await page.locator("#staff-tab").click();
    await page.locator("#staff-name").fill("Synthetic Lan");
    await page.locator("#staff-rate").fill("180");
    await page.locator("#staff-add").click();
    await waitText("#staff-people", "Synthetic Lan");
    await page.locator("#staff-name").fill("Synthetic Minh");
    await page.locator("#staff-minor").check();
    await page.locator("#staff-add").click();
    await waitText("#staff-people", "Synthetic Minh");
    await page.locator("#shift-staff").selectOption({ label: "Synthetic Lan" });
    await page.locator("#shift-tips").fill("250");
    await page.locator("#shift-add").click();
    await waitText("#shift-summary", "Synthetic Lan");
    // Codex review, PR #17: a shift whose response is lost is not recorded twice on retry.
    await page.locator("#shift-staff").selectOption({ label: "Synthetic Lan" });
    await page.locator("#shift-date").fill(await page.evaluate(() => pragueToday().slice(0, 8) + "01"));
    let dropShiftResponse = true;
    await page.route(/\/shifts$/, async (route) => {
      if (route.request().method() === "POST" && dropShiftResponse) {
        dropShiftResponse = false;
        await route.fetch();
        await route.abort();
      } else await route.continue();
    });
    await page.locator("#shift-add").click();
    await page.waitForTimeout(300);
    await page.locator("#shift-add").click();
    await page.unroute(/\/shifts$/);
    await page.locator("#staff-week").fill(await page.evaluate(() => pragueToday().slice(0, 8) + "01"));
    await page.locator("#staff-week").dispatchEvent("change");
    await page.waitForFunction(() =>
      document.querySelector("#shift-period").textContent.includes(czDate(weekBounds(pragueToday().slice(0, 8) + "01")[0])) &&
      document.querySelector("#shift-list").textContent.includes("Synthetic Lan"));
    check(
      "A shift retried after a lost response is recorded once",
      (await page.locator(".shift-item").filter({ hasText: "Synthetic Lan" }).count()) === 1,
    );
    await page.locator("#staff-week").fill(await page.evaluate(() => pragueToday()));
    await page.locator("#staff-week").dispatchEvent("change");
    await waitText("#shift-summary", "Synthetic Lan");
    await page.locator("#shift-date").fill(await page.evaluate(() => pragueToday()));
    await page.locator("#shift-staff").selectOption({ label: "Synthetic Minh" });
    await page.locator("#shift-start").fill("09:00");
    await page.locator("#shift-end").fill("14:00");
    await page.locator("#shift-break").fill("0");
    await page.locator("#shift-add").click();
    await waitText("#shift-list", "Synthetic Minh");
    const shiftText = (await page.locator("#staff-view").innerText()).replace(/\s/g, " ");
    check(
      "Shifts sum hours, labour cost and tips per person",
      shiftText.includes("1 440,00") && shiftText.includes("250,00") && shiftText.includes("Chưa có lương giờ nên chưa tính tiền công: Synthetic Minh"),
    );
    check(
      "A person under 18 working 5 hours without a break is flagged",
      (await page.locator(".shift-item.flagged").count()) === 1 && shiftText.includes("sau 4,5 h phải nghỉ ít nhất 30 phút"),
    );
    await page.locator("#cash-tab").click();
    await page.locator("#cash-control:not([hidden])").waitFor();
    await page.locator("#close-opening").fill("2000");
    await page.locator("#close-counted").fill("1900");
    await page.locator("#close-save").click();
    await page.waitForFunction(() => /đếm được 1\s900,00/.test(document.querySelector("#close-result").textContent));
    // Codex review, PR #17: an existing close is found even when the cashbook shows another month.
    await page.locator("#cash-month").fill("2025-01");
    await page.locator("#cash-month").dispatchEvent("change");
    await page.waitForFunction(() => document.querySelector("#cash-report").textContent.includes("2025-01"));
    await page.locator("#close-date").fill(await page.evaluate(() => pragueToday()));
    await page.locator("#close-date").dispatchEvent("change");
    await page.waitForFunction(() => document.querySelector("#close-save").textContent === "Đếm lại" && !document.querySelector("#close-save").disabled);
    check("An existing close outside the shown month opens as a recount", (await page.locator("#close-counted").inputValue()) === "1900.00");
    await page.locator("#cash-month").fill(await page.evaluate(() => pragueToday().slice(0, 7)));
    await page.locator("#cash-month").dispatchEvent("change");
    check(
      "The daily cash close compares the counted till with the cashbook",
      /^(Thiếu|Thừa|Khớp)/.test(await page.locator("#close-result").innerText()) &&
        (await page.locator("#close-save").innerText()) === "Đếm lại" &&
        (await page.locator(".flow-row").count()) === 8,
    );
    // CR-11: a bank statement pays the invoice by its variable symbol; the rest is decided by hand.
    const gpcLine = (hal, code, vs, ref, counter = "19") =>
      "075" + "1234567890".padStart(16, "0") + counter.padStart(16, "0") + ref.padStart(13, "0") +
      String(hal).padStart(12, "0") + code + vs.padStart(10, "0") + "08000308".padEnd(10, "0") + "0".repeat(10) +
      "000000" + "SYNTHETIC".padEnd(20) + "0" + "0203" + "051126";
    const gpcHead = "074" + "1234567890".padStart(16, "0") + "SYNTHETIC UCET".padEnd(20) + "011126" + "0".repeat(14) +
      "+" + "0".repeat(14) + "+" + "0".repeat(14) + "0" + "0".repeat(14) + "0" + "001" + "061126" + " ".repeat(14);
    const statement = [gpcHead, gpcLine(46456, "2", year + "0001", "1"), gpcLine(1500, "1", "", "2", "0"),
      gpcLine(25000, "1", "", "3", "77"), gpcLine(25000, "1", "", "4", "77")].join("\r\n") + "\r\n";
    await page.locator("#bank-tab").click();
    await page.locator("#bank-file").setInputFiles({ name: "vypis.gpc", mimeType: "text/plain", buffer: Buffer.from(statement) });
    await page.locator("#bank-import").click();
    await waitText("#notice", "Đã nhập: 4 giao dịch mới");
    await waitText("#bank-filter-matched", "(1)");
    check(
      "A GPC statement is imported and the invoice payment is matched by its variable symbol",
      (await page.locator("#notice").innerText()).includes("tự khớp 1") &&
        (await page.locator("#bank-filter-matched").innerText()).includes("(1)"),
    );
    check(
      "Two equal payments to the same account within days are flagged",
      (await page.locator(".bank-row .bank-flag").count()) === 2,
    );
    await page.locator("#bank-file").setInputFiles({ name: "vypis.gpc", mimeType: "text/plain", buffer: Buffer.from(statement) });
    await page.locator("#bank-import").click();
    await waitText("#notice", "đã được nhập rồi");
    check("The same statement file is not imported twice", true);
    const feeRow = page.locator(".bank-row").filter({ hasText: "-15,00" });
    await feeRow.getByRole("button", { name: "Không cần chứng từ" }).click();
    await waitText("#bank-filter-ignored", "(1)");
    check("A bank fee is marked as needing no document", (await page.locator(".bank-row").count()) === 2);
    // CR-13: the statement file is kept with its account and period, with monthly coverage.
    await page.locator("#statement-register .statement-row").first().waitFor();
    const register = await page.locator("#statement-register").innerText();
    check(
      "The imported statement is listed with its account and period, ready to download",
      (await page.locator("#statement-register .statement-row").count()) === 1 &&
        register.includes("1234567890") &&
        (await page.locator("#statement-register button").innerText()) === "Tải về" &&
        (await page.locator(".coverage-cell").count()) >= 1 &&
        (await page.locator("#payout-summary").innerText()).includes("Bán bằng thẻ"),
    );
    const [statementDownload] = await Promise.all([
      page.waitForEvent("download"),
      page.locator("#statement-register button").click(),
    ]);
    check("The original statement file downloads unchanged", statementDownload.suggestedFilename() === "vypis.gpc");
    await page.locator("#invoices-tab").click();
    await waitText("#invoice-list", "đã trả");
    check(
      "The issued invoice shows it was paid",
      (await page.locator(".invoice-row").first().innerText()).includes("đã trả"),
    );
    // Codex review, PR #7: deleting a draft (204, no body) must refresh the list, not fail.
    await page.locator("#new-invoice").click();
    await page.locator("#i-customer_name").fill("Synthetic Draft s.r.o.");
    await page.locator("#i-customer_address").fill("Vzorová 3, 602 00 Brno");
    await invLine(1).locator('[data-key="description"]').fill("Synthetic draft line");
    await invLine(1).locator('[data-key="unit_price"]').fill("10");
    await page.locator("#invoice-save").click();
    await page.waitForFunction(() => document.querySelectorAll(".invoice-row").length === 2);
    await page.locator(".invoice-row").filter({ hasText: "Synthetic Draft" }).getByRole("button", { name: "Xóa nháp" }).click();
    await page.waitForFunction(() => document.querySelectorAll(".invoice-row").length === 1);
    check(
      "Deleting a draft refreshes the list and closes its editor",
      (await page.locator("#invoice-form").isHidden()) &&
        !(await page.locator("#notice").evaluate((n) => n.classList.contains("error"))),
    );
    await page.locator("#language").selectOption("cs");
    check(
      "Invoices are translated to Czech",
      (await page.locator("#invoices-tab").innerText()) === "Vydané faktury",
    );
    await page.locator("#language").selectOption("vi");
    await page.locator("#new-invoice").click();
    if (process.env.VIETBIZ_SCREENSHOT_DIR)
      await page.screenshot({
        path: path.join(process.env.VIETBIZ_SCREENSHOT_DIR, "invoices-desktop.png"),
        fullPage: true,
      });
    await page.setViewportSize({ width: 390, height: 844 });
    check(
      "Invoice editor fits a 390 px screen",
      await page.evaluate(() => {
        const view = document.querySelector("#invoices-view");
        const edge = view.getBoundingClientRect().right - parseFloat(getComputedStyle(view).paddingRight);
        return (
          document.documentElement.scrollWidth <= innerWidth &&
          [...view.querySelectorAll("input, select, button")]
            .filter((el) => el.offsetParent)
            .every((el) => el.getBoundingClientRect().right <= edge + 1)
        );
      }),
    );
    if (process.env.VIETBIZ_SCREENSHOT_DIR)
      await page.screenshot({
        path: path.join(process.env.VIETBIZ_SCREENSHOT_DIR, "invoices-mobile.png"),
        fullPage: true,
      });
    await page.locator("#invoice-cancel").click();
    await page.setViewportSize({ width: 1440, height: 1100 });
    // Legal guide per industry (VI/CS, each duty with its source).
    await page.locator("#legal-tab").click();
    await page.locator(".legal-card").first().waitFor();
    const legalLinks = await page.$$eval(".legal-card li", (items) =>
      items.map((li) => {
        const a = li.querySelector("a");
        return a && a.href.startsWith("https://") && a.rel.includes("noopener") && a.target === "_blank";
      }),
    );
    check(
      "Legal guide shows every industry with a source on each duty",
      (await page.locator(".legal-card").count()) === 12 &&
        legalLinks.length >= 43 &&
        legalLinks.every(Boolean),
    );
    // Codex review, PR #8: SZPI supervises restaurants since 2025; the health card was abolished in 2023.
    const bistroText = await page.locator('.legal-card[data-industry="bistro"]').innerText();
    check(
      "Restaurant card names SZPI and the abolished health card",
      bistroText.includes("SZPI kiểm tra quán ăn (từ 1/1/2025)") &&
        bistroText.includes("đã bị bãi bỏ từ 1/7/2023") &&
        !bistroText.includes("Thẻ sức khỏe nhân viên"),
    );
    const cardText = (id) => page.locator(`.legal-card[data-industry="${id}"]`).innerText();
    check(
      "New industry cards cover tobacco stamps, kratom permit, cosmetics, take-back and textile labels",
      (await cardText("tobacco")).includes("tem thuế Séc") &&
        (await cardText("herbal")).includes("12/11/2025") &&
        (await cardText("drogerie")).includes("CPNP") &&
        (await cardText("electronics")).includes("400 m²") &&
        (await cardText("textile")).includes("thành phần sợi") &&
        (await cardText("import")).includes("326 000 Kč"),
    );
    await page.locator(".legal-chip").filter({ hasText: "Nail" }).click();
    check(
      "Industry filter shows the nail salon rules incl. the 2026 KHS change",
      (await page.locator(".legal-card").count()) === 1 &&
        (await page.locator(".legal-card").innerText()).includes("Từ 1/1/2026: chỉ cần báo KHS"),
    );
    await page.locator("#language").selectOption("cs");
    check(
      "Legal guide is translated to Czech",
      (await page.locator(".legal-card h3").innerText()).includes("Nehtové studio") &&
        (await page.locator(".legal-card").innerText()).includes("Od 1. 1. 2026: jen oznámení KHS"),
    );
    await page.locator("#language").selectOption("vi");
    await page.locator(".legal-chip").first().click();
    if (process.env.VIETBIZ_SCREENSHOT_DIR)
      await page.screenshot({
        path: path.join(process.env.VIETBIZ_SCREENSHOT_DIR, "legal-desktop.png"),
        fullPage: true,
      });
    await page.setViewportSize({ width: 390, height: 844 });
    check(
      "Legal guide fits a 390 px screen",
      await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth &&
        [...document.querySelectorAll(".legal-card")].every((c) => c.getBoundingClientRect().right <= innerWidth)),
    );
    if (process.env.VIETBIZ_SCREENSHOT_DIR)
      await page.screenshot({
        path: path.join(process.env.VIETBIZ_SCREENSHOT_DIR, "legal-mobile.png"),
        fullPage: true,
      });
    await page.setViewportSize({ width: 1440, height: 1100 });
    await page.locator("#tasks-tab").click();
    if (process.env.VIETBIZ_SCREENSHOT_DIR) {
      fs.mkdirSync(process.env.VIETBIZ_SCREENSHOT_DIR, { recursive: true });
      await chooseFirst();
      await page.screenshot({
        path: path.join(process.env.VIETBIZ_SCREENSHOT_DIR, "desktop.png"),
        fullPage: true,
      });
    }
    // UI elements #011 #012 #018 #030 (lucianLabs prompts), as the owner of the demo company.
    await page.locator("#demo-role").selectOption({ label: "Chủ cửa hàng" });
    await page.waitForFunction(() => !document.querySelector("#upload-button").disabled);
    await page.locator("#quick-create:not([hidden])").waitFor();
    check(
      "Quick create offers the owner all four actions",
      (await page.locator(".u011-it:not([hidden])").count()) === 4,
    );
    await page.locator(".u011-fab").click();
    check(
      "Quick create opens and names its close action",
      (await page.locator(".u011-fab").getAttribute("aria-expanded")) === "true" &&
        (await page.locator(".u011-fab").getAttribute("aria-label")) === "Đóng menu",
    );
    await page.keyboard.press("Shift+Tab");
    await page.keyboard.press("ArrowRight");
    check(
      "Arrow keys move between the quick actions and wrap around",
      (await page.evaluate(() => document.activeElement.dataset.action)) === "upload",
    );
    await page.keyboard.press("Escape");
    check(
      "Escape closes quick create and returns focus to the button",
      (await page.locator(".u011-fab").getAttribute("aria-expanded")) === "false" &&
        (await page.evaluate(() => document.activeElement.classList.contains("u011-fab"))),
    );
    await page.locator(".u011-fab").click();
    await page.locator('.u011-it[data-action="invoice"]').click();
    await page.locator("#invoice-form:not([hidden])").waitFor();
    await waitText(".u011-note", "Đã mở hoá đơn mới");
    check("The invoice action opens a new issued invoice", await page.locator("#invoices-view").isVisible());
    const qtyLine = page.locator(".invoice-line").first();
    await qtyLine.locator('[data-key="unit_price"]').fill("129");
    await qtyLine.locator(".u018-b.pl").click();
    await qtyLine.locator(".u018-b.pl").click();
    await page.waitForFunction(() => document.querySelector(".u018-total").textContent.replace(/\s/g, "") === "387,00CZK");
    check(
      "The stepper changes the line's own quantity and the amount follows",
      (await qtyLine.locator('[data-key="quantity"]').inputValue()) === "3",
    );
    for (let i = 0; i < 3; i++) await qtyLine.locator(".u018-b.mi").click({ force: true });
    check(
      "The stepper stops at one and shakes instead of going lower",
      (await qtyLine.locator('[data-key="quantity"]').inputValue()) === "1" &&
        (await qtyLine.locator(".u018-step").getAttribute("class")).includes("is-shake") &&
        (await qtyLine.locator(".u018-b.mi").getAttribute("aria-disabled")) === "true",
    );
    await qtyLine.locator('[data-key="quantity"]').fill("2,5");
    await page.waitForFunction(() => document.querySelector(".u018-total").textContent.replace(/\s/g, "") === "322,50CZK");
    check(
      "A decimal quantity can still be typed and is shown as typed",
      (await qtyLine.locator(".u018-raw").innerText()) === "2,5",
    );
    await page.locator("#invoice-cancel").click();
    await page.locator(".u011-fab").click();
    await page.locator('.u011-it[data-action="upload"]').click();
    await page.waitForFunction(() => document.activeElement?.id === "upload-file");
    check("The upload action opens the documents with the file field focused", await page.locator("#docs-view").isVisible());
    await page.locator(".document").first().getByRole("button", { name: "Dữ liệu hóa đơn" }).click();
    await page.locator("#doc-flag:not([hidden])").waitFor();
    const flagsBefore = Number((await page.locator(".u012-num").innerText()).split(" ")[0]);
    await page.locator(".u012-btn").click();
    await page.waitForFunction(
      (n) => document.querySelector(".u012-num").textContent.startsWith(String(n + 1) + " ") &&
        document.querySelector(".u012-btn").getAttribute("aria-pressed") === "true",
      flagsBefore,
    );
    check("The review ribbon marks the document and counts it", true);
    await page.locator("#close-extract").click();
    await page.locator(".document .badge", { hasText: "Cần xem lại" }).first().waitFor();
    await page.locator("#f-flagged").check();
    await page.waitForFunction((n) => document.querySelectorAll(".document").length === n, flagsBefore + 1);
    check("The archive can show only the marked documents", true);
    await page.locator("#f-clear").click();
    await page.waitForFunction(() => !document.querySelector("#f-flagged").checked);
    await page.locator("#range-filter summary").click();
    const days = page.locator(".u030-d:not(:disabled)");
    check("Days after today cannot be picked in the archive range", (await page.locator(".u030-d.off").count()) === (await page.evaluate(() => {
      const [y, m, d] = pragueToday().split("-").map(Number);
      return new Date(Date.UTC(y, m, 0)).getUTCDate() - d;
    })));
    // The previous month always has whole days to pick, whatever today is.
    await page.locator('.u030-nav button[data-step="-1"]').click();
    await page.waitForFunction(() => document.querySelectorAll(".u030-grid").length === 1);
    await days.first().click();
    await days.last().click();
    check(
      "Picking two days fills both ends and enables apply",
      (await page.locator(".u030-ok").getAttribute("aria-disabled")) === "false" &&
        !(await page.locator(".u030-b").getAttribute("class")).includes("ph"),
    );
    await page.locator(".u030-ok").click();
    const [lastFrom, lastTo] = await page.evaluate(() => {
      const [y, m] = pragueToday().split("-").map(Number);
      const first = new Date(Date.UTC(y, m - 2, 1)), last = new Date(Date.UTC(y, m - 1, 0));
      return [first.toISOString().slice(0, 10), last.toISOString().slice(0, 10)];
    });
    check(
      "Applying the range filters the archive by those days",
      (await page.locator("#f-from").inputValue()) === lastFrom &&
        (await page.locator("#f-to").inputValue()) === lastTo &&
        !(await page.locator("#range-clear").isHidden()),
    );
    // Codex review, PR #20: "clear filters" must reload without the applied range.
    const cleared = page.waitForRequest((r) => r.url().includes("/archive"));
    await page.locator("#f-clear").click();
    check(
      "Clearing the filters reloads the archive without the date range",
      !(await cleared).url().includes("date_from") && (await page.locator("#f-from").inputValue()) === "",
    );
    // Codex review, PR #20: the same day twice is a one-day range.
    await page.locator('.u030-nav button[data-step="1"]').click();
    await page.waitForFunction(() => document.querySelectorAll(".u030-grid").length === 1);
    await page.locator(".u030-d.today").click();
    await page.locator(".u030-d.today").click();
    await page.locator(".u030-ok").click();
    const todayIso = await page.evaluate(() => pragueToday());
    check(
      "One day can be chosen by picking it twice",
      (await page.locator("#f-from").inputValue()) === todayIso && (await page.locator("#f-to").inputValue()) === todayIso,
    );
    await page.locator("#range-clear").click();
    check("The range can be cleared again", (await page.locator("#f-from").inputValue()) === "");
    await page.locator("#demo-role").selectOption({ label: "Kế toán" });
    await page.waitForFunction(() => document.querySelector("#role-badge").textContent === "Kế toán");
    check(
      "Quick create follows the role: the accountant cannot upload",
      await page.locator('.u011-it[data-action="upload"]').isHidden(),
    );
    await page.locator("#tasks-tab").click();
    await page.setViewportSize({ width: 390, height: 844 });
    check(
      "Mobile layout has no horizontal overflow",
      await page.evaluate(
        () => document.documentElement.scrollWidth <= innerWidth,
      ),
    );
    await page.locator("#new-task").click();
    check(
      "Mobile task form opens",
      await page.locator("#create-dialog").isVisible(),
    );
    await page.keyboard.press("Escape");
    if (process.env.VIETBIZ_SCREENSHOT_DIR)
      await page.screenshot({
        path: path.join(process.env.VIETBIZ_SCREENSHOT_DIR, "mobile.png"),
        fullPage: true,
      });
    // Clear current company: old content must disappear immediately.
    await page.locator("#org").selectOption("");
    check(
      "Deselecting company clears task details",
      (await page.locator("#reply-body").count()) === 0,
    );
    check("Deselecting company hides quick create", await page.locator("#quick-create").isHidden());
    check(
      "Deselecting company clears financial summary",
      (await page.locator("#metric-active").innerText()) === "—",
    );
    // Codex review, PR #11: a reset context must not keep another identity's client list.
    check(
      "Resetting the context clears and hides the portfolio",
      (await page.locator("#portfolio-tab").isHidden()) &&
        (await page.locator(".portfolio-row").count()) === 0,
    );
    check(
      "Resetting the context clears the filing calendar and profile form",
      (await page.locator(".deadline-row").count()) === 0 &&
        (await page.locator("#profile-status").innerText()) === "" &&
        // Codex review, PR #13: the previous client's values leave the controls too.
        !(await page.locator("#profile-employees").isChecked()) &&
        (await page.locator("#profile-org option").count()) === 1 &&
        (await page.locator("#profile-save").isDisabled()),
    );
    // Report 10.11.2026, gap 1: OIDC login with PKCE against a mocked identity provider.
    const login = await browser.newPage({ viewport: { width: 1280, height: 900 } });
    login.on("pageerror", (e) => errors.push(e.message));
    login.on("console", (m) => {
      if (m.text().includes("Content Security Policy")) cspViolations.push(m.text());
    });
    const workspace = process.env.VIETBIZ_UI_URL || "http://127.0.0.1:8000/workspace/";
    const settings = {
      mode: "oidc", ready: true, client_id: "vietbiz-web", scope: "openid profile",
      authorization_endpoint: "https://id.example/authorize", token_endpoint: "https://id.example/token",
      end_session_endpoint: null, mfa_required: true, acr_values: "mfa",
    };
    let authorizeUrl = null, tokenForm = null, bearer = null;
    await login.route("**/auth/config", (r) => r.fulfill({ json: settings }));
    await login.route("**/health", (r) => r.fulfill({ json: { status: "ok", mode: "test", auth_mode: "oidc" } }));
    await login.route("**/v1/organizations", (r) => {
      bearer = r.request().headers()["authorization"] || null;
      return r.fulfill({ json: [] });
    });
    await login.route("https://id.example/authorize**", (r) => {
      authorizeUrl = new URL(r.request().url());
      const back = new URL(authorizeUrl.searchParams.get("redirect_uri"));
      back.searchParams.set("code", "synthetic-code");
      back.searchParams.set("state", authorizeUrl.searchParams.get("state"));
      return r.fulfill({ status: 302, headers: { location: back.toString() } });
    });
    await login.route("https://id.example/token", (r) => {
      tokenForm = new URLSearchParams(r.request().postData());
      return r.fulfill({
        json: { access_token: "synthetic-access-token", token_type: "Bearer", expires_in: 300 },
        headers: { "Access-Control-Allow-Origin": "*" },
      });
    });
    await login.goto(workspace);
    await login.locator("#login").click();
    await login.waitForFunction(() => document.querySelector("#notice").textContent.includes("Đã đăng nhập"));
    const challenge = await login.evaluate(
      (verifier) => pkceChallenge(verifier),
      tokenForm.get("code_verifier"),
    );
    check(
      "Login sends the user to the provider with PKCE (S256), state and the MFA request",
      authorizeUrl.searchParams.get("code_challenge_method") === "S256" &&
        authorizeUrl.searchParams.get("code_challenge") === challenge &&
        authorizeUrl.searchParams.get("client_id") === "vietbiz-web" &&
        authorizeUrl.searchParams.get("acr_values") === "mfa" &&
        authorizeUrl.searchParams.get("state").length >= 32,
    );
    check(
      "The code is exchanged without a client secret and the API gets the bearer token",
      tokenForm.get("grant_type") === "authorization_code" && tokenForm.get("code") === "synthetic-code" &&
        !tokenForm.has("client_secret") && bearer === "Bearer synthetic-access-token",
    );
    check(
      "After login the code leaves the address bar and the token is not stored in the browser",
      !login.url().includes("code=") &&
        (await login.evaluate(() => JSON.stringify({ ...localStorage, ...sessionStorage }).includes("synthetic-access-token"))) === false,
    );
    await login.locator("#logout").click();
    check("Logout forgets the token", (await login.evaluate(() => state.token)) === "" && (await login.locator("#login").isVisible()));
    // A code that comes back with someone else's state is never exchanged.
    tokenForm = null;
    await login.goto(workspace + "?code=forged&state=not-ours");
    await login.waitForFunction(() => document.querySelector("#notice").textContent.includes("không thành công"));
    check("A returned code with a foreign state is refused", tokenForm === null && !login.url().includes("code="));
    await login.close();
    if (cspViolations.length) console.error("CSP", [...new Set(cspViolations)]);
    check("The workspace runs under its Content-Security-Policy without violations", cspViolations.length === 0);
    check("No browser JavaScript errors", errors.length === 0);
    const report = {
      status: "passed",
      browser: "Chromium",
      browserVersion: await browser.version(),
      checks: checks.length,
      passed: checks,
      errors,
    };
    fs.mkdirSync("quality-evidence", { recursive: true });
    fs.writeFileSync(
      "quality-evidence/sprint10-ui.json",
      JSON.stringify(report, null, 2),
    );
    console.log(JSON.stringify(report, null, 2));
  } finally {
    await browser.close();
  }
})().catch((error) => {
  console.error(error);
  process.exitCode = 1;
});
