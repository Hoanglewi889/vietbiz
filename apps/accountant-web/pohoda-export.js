"use strict";
// POHODA hand-over: the month in the cash book view (issued + approved received invoices) as a
// Stormware XML data pack for the accountant's POHODA (GET …/exports/pohoda?month=). Owner and
// accountant, like the API.
(function () {
  const btn = $("pohoda-export");
  function refresh() {
    btn.hidden = !(state.org && FINANCE_ROLES.includes(state.role));
  }
  // Codex review, PR #31: invoices left out of the pack are always reported, by reason.
  function leftOut(reasons) {
    const n = (r) => reasons.filter((x) => x === r).length;
    return [
      n("currency") ? fill(t("pohodaSkippedCurrency"), { n: n("currency") }) : "",
      n("amounts") ? fill(t("pohodaSkippedAmounts"), { n: n("amounts") }) : "",
    ].filter(Boolean).join(" ");
  }
  async function download() {
    const org = state.org,
      month = $("cash-month").value || pragueToday().slice(0, 7);
    let answer;
    try {
      answer = await request(base() + "/exports/pohoda?month=" + encodeURIComponent(month), { blob: true, withHeaders: true });
    } catch (error) {
      if (error && error.status === 404) throw { messageKey: "pohodaNothing" };
      if (error && error.status === 422 && error.detail && Array.isArray(error.detail.skipped)) {
        if (state.org === org) notice(t("pohodaAllSkipped") + " " + leftOut(error.detail.skipped.map((s) => s.reason)), true);
        return;
      }
      throw error;
    }
    if (state.org !== org) return;
    const url = URL.createObjectURL(answer.body),
      a = document.createElement("a");
    a.href = url;
    a.download = "vietbiz-pohoda-" + month + ".xml";
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    const skipped = (answer.headers.get("X-VietBiz-Skipped") || "").split(",").filter(Boolean).map((x) => x.split(":")[1]);
    const done = fill(t("pohodaDone"), {
      month, issued: answer.headers.get("X-VietBiz-Issued") || "0", received: answer.headers.get("X-VietBiz-Received") || "0",
    });
    if (skipped.length) notice(done + " " + t("pohodaSkippedIntro") + " " + leftOut(skipped), true);
    else notice(done);
  }
  btn.onclick = () => run(download, btn);
  new MutationObserver(refresh).observe($("role-badge"), { childList: true, characterData: true, subtree: true });
  refresh();
})();
