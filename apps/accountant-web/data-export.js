"use strict";
// Company data export (GDPR art. 20 / hand-over): the owner downloads one ZIP with every
// record of the company and its original files (GET …/export). Owner only, like the API.
(function () {
  const btn = $("export-data");
  function refresh() {
    btn.hidden = !(state.org && state.role === "owner");
  }
  async function download() {
    const org = state.org,
      blob = await request(base() + "/export", { blob: true });
    if (state.org !== org) return;
    const url = URL.createObjectURL(blob),
      a = document.createElement("a");
    a.href = url;
    a.download = "vietbiz-export-" + org.slice(0, 8) + "-" + pragueToday() + ".zip";
    a.click();
    setTimeout(() => URL.revokeObjectURL(url), 1000);
    notice(t("exportDone"));
  }
  btn.onclick = () => run(download, btn);
  new MutationObserver(refresh).observe($("role-badge"), { childList: true, characterData: true, subtree: true });
  refresh();
})();
