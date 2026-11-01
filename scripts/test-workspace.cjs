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
