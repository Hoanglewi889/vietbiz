"use strict";
// POHODA hand-over: the month in the cash book view (issued + approved received invoices) as a
// Stormware XML data pack for the accountant's POHODA (GET …/exports/pohoda?month=). Owner and
// accountant, like the API.
(function () {
  const btn = $("pohoda-export");
  function refresh() {
    btn.hidden = !(state.org && FINANCE_ROLES.includes(state.role));
  }
  async function download() {
    const org = state.org,
      month = $("cash-month").value || pragueToday().slice(0, 7);
    let blob;
    try {
      blob = await request(base() + "/exports/pohoda?month=" + encodeURIComponent(month), { blob: true });
    } catch (error) {
      if (error && error.status === 404) throw { messageKey: "pohodaNothing" };
      throw error;
    }
    if (state.org !== org) return;
    const url = URL.createObjectURL(blob),
      a = document.createElement("a");
    a.href = url;
    a.download = "vietbiz-pohoda-" + month + ".xml";
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    notice(fill(t("pohodaDone"), { month }));
  }
  btn.onclick = () => run(download, btn);
  new MutationObserver(refresh).observe($("role-badge"), { childList: true, characterData: true, subtree: true });
  refresh();
})();
