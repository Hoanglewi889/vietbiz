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
  const checks = [];
  const check = (name, condition) => {
    assert.ok(condition, name);
    checks.push(name);
  };
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
    await page.locator("#tasks-tab").click();
    if (process.env.VIETBIZ_SCREENSHOT_DIR) {
      fs.mkdirSync(process.env.VIETBIZ_SCREENSHOT_DIR, { recursive: true });
      await chooseFirst();
      await page.screenshot({
        path: path.join(process.env.VIETBIZ_SCREENSHOT_DIR, "desktop.png"),
        fullPage: true,
      });
    }
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
    check(
      "Deselecting company clears financial summary",
      (await page.locator("#metric-active").innerText()) === "—",
    );
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
