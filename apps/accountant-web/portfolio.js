"use strict";
// Accountant portfolio (CR-6): every company the user keeps books for, urgent work first.
const portfolio = { items: [], ticket: 0, asOf: "" };

async function loadPortfolio() {
  const ticket = ++portfolio.ticket;
  const body = await request("/v1/portfolio");
  if (ticket !== portfolio.ticket) return;
  portfolio.items = body.items;
  portfolio.asOf = body.as_of_date;
  // Shown to anyone who keeps the books for at least one company, or owns several.
  const accountantSomewhere = body.items.some((i) => i.role === "accountant");
  $("portfolio-tab").hidden = !(accountantSomewhere || body.items.length > 1);
  if ($("portfolio-tab").hidden && !$("portfolio-view").hidden) setTab("tasks");
  renderPortfolio();
  if (typeof loadDeadlines === "function") await loadDeadlines();
}
function portfolioStat(label, value, alert = false) {
  return text(
    "span",
    label + ": " + value,
    "portfolio-stat" + (value ? (alert ? " alert" : "") : " zero"),
  );
}
function replyDuration(minutes) {
  if (minutes < 60) return minutes + " min";
  if (minutes < 48 * 60) return Math.round(minutes / 60) + " h";
  return Math.round(minutes / 1440) + (lang === "cs" ? " d" : " ngày");
}
function renderPortfolio() {
  const list = $("portfolio-list");
  list.replaceChildren();
  for (const item of portfolio.items) {
    const row = text("article", "", "portfolio-row " + item.attention),
      head = text("div", "");
    head.append(
      text("h3", item.name),
      text(
        "small",
        [
          COPY[lang].attention[item.attention],
          t(item.role),
          item.last_activity_at
            ? fill(t("lastActivity"), { when: timestamp(item.last_activity_at) })
            : "",
        ]
          .filter(Boolean)
          .join(" · "),
      ),
    );
    const stats = text("div", "", "portfolio-stats");
    stats.append(
      portfolioStat(t("overdueTasks"), item.overdue_tasks, true),
      portfolioStat(t("toReview"), item.documents_to_review),
      portfolioStat(t("returnedDocs"), item.documents_returned),
      portfolioStat(t("unpaidApproved"), item.approved_without_payment),
      portfolioStat(t("waitingClient"), item.waiting_on_client),
      portfolioStat(t("openTasks"), item.open_tasks),
    );
    if (item.next_deadline)
      stats.append(text("span", fill(t("nextDeadline"), {
        date: shortDate(item.next_deadline.due_date),
        what: deadlineTitle(item.next_deadline.code),
      }), "portfolio-stat deadline"));
    if (item.unanswered_messages)
      stats.append(text("span", fill(t("unansweredMessages"), {
        n: item.unanswered_messages,
        since: timestamp(item.oldest_unanswered_at),
      }), "portfolio-stat alert"));
    if (item.median_reply_minutes !== null && item.median_reply_minutes !== undefined)
      stats.append(text("span", fill(t("medianReply"), { m: replyDuration(item.median_reply_minutes) }), "portfolio-stat"));
    if (item.vat_threshold && item.vat_threshold !== "ok")
      stats.append(text("span", t("vatThresholdShort") + ": " + COPY[lang].vatThresholdStatus[item.vat_threshold],
        "portfolio-stat" + (item.vat_threshold === "watch" ? "" : " alert")));
    if (item.profile_missing)
      stats.append(button(t("profileMissing"), () => openProfile(item.organization_id), "portfolio-stat alert"));
    const open = button(t("openCompany"), async () => {
      $("org").value = item.organization_id;
      await switchOrg();
      setTab(item.documents_to_review || item.documents_returned ? "docs" : "tasks");
    }, item.attention === "high" ? "primary" : "secondary");
    row.append(head, open, stats);
    list.append(row);
  }
  if (!portfolio.items.length) empty(list, t("noPortfolio"));
  if (typeof renderDeadlines === "function") {
    renderDeadlines();
    renderProfileOptions();
  }
}
// Called from resetContext(): a new identity or company must never see the old portfolio.
function resetPortfolio() {
  portfolio.ticket++;
  portfolio.items = [];
  $("portfolio-tab").hidden = true;
  if (!$("portfolio-view").hidden) setTab("tasks");
  $("portfolio-list").replaceChildren();
  if (typeof resetFiling === "function") resetFiling();
}
$("portfolio-tab").onclick = () => setTab("portfolio");
