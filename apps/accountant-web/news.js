"use strict";
// News in the app (owner request 19.–21.11.2026): Czech law news, notices and rules for
// Vietnamese businesses, filtered by trade (grocery, bistro, nails, hair). Items are the ones the
// editor wrote in Vietnamese and a reviewer published (GET /v1/news); each keeps its sources and,
// for law, the official link. A law item or notice can be added to today's tasks.
const NEWS_TEXT = {
  vi: {
    title: "Luật & tin cho tiệm bạn", note: "Biên tập viên viết lại bằng tiếng Việt từ nguồn đã ghi; tin luật kèm văn bản chính thức.",
    mine: "Cho tiệm bạn", all: "Tất cả", law: "Luật mới", notice: "Thông báo", business: "Kinh doanh", general: "Chung", events: "Sự kiện",
    grocery: "Potraviny", bistro: "Quán ăn", nails: "Nail", hair: "Cắt tóc", everyone: "Mọi ngành",
    sources: "Nguồn", official: "Văn bản chính thức", addTask: "Thêm vào việc", added: "Đã thêm vào việc ✓",
    empty: "Chưa có tin nào cho mục này.", failed: "Không tải được tin tức.", affects: "Ảnh hưởng đến tiệm bạn",
    taskFrom: "Từ tin tức",
  },
  cs: {
    title: "Zákony a zprávy pro vaši provozovnu", note: "Redakce píše vietnamsky z uvedených zdrojů; zprávy o zákonech s oficiálním odkazem.",
    mine: "Pro vás", all: "Vše", law: "Nové zákony", notice: "Oznámení", business: "Podnikání", general: "Obecné", events: "Akce",
    grocery: "Potraviny", bistro: "Bistro", nails: "Nehty", hair: "Kadeřnictví", everyone: "Všechny obory",
    sources: "Zdroj", official: "Oficiální text", addTask: "Přidat do úkolů", added: "Přidáno do úkolů ✓",
    empty: "Pro tento výběr zatím nejsou zprávy.", failed: "Zprávy se nepodařilo načíst.", affects: "Týká se vaší provozovny",
    taskFrom: "Ze zpráv",
  },
};
const NEWS_FILTERS = [
  ["mine", {}], ["all", {}], ["law", { category: "law" }], ["notice", { category: "notice" }],
  ["grocery", { industry: "grocery" }], ["bistro", { industry: "bistro" }], ["nails", { industry: "nails" }], ["hair", { industry: "hair" }],
];
const newsState = { items: [], filter: "mine", industry: null, seen: null, ticket: 0, added: new Set(), failed: false };

function newsT(key) {
  return NEWS_TEXT[lang === "cs" ? "cs" : "vi"][key] ?? key;
}
function newsEl(tag, cls, ...children) {
  const el = document.createElement(tag);
  if (cls) el.className = cls;
  for (const c of children) if (c != null) el.append(c);
  return el;
}
function newsLink(label, href) {
  const a = newsEl("a", "", label + " ↗");
  a.href = href;
  a.target = "_blank";
  a.rel = "noopener noreferrer";
  return a;
}

// The company's trade, from its client profile (owner and accountant can read it).
async function newsIndustry() {
  if (!state.org || !FINANCE_ROLES.includes(state.role)) return null;
  try {
    const body = await request("/v1/organizations/" + encodeURIComponent(state.org) + "/client-profile");
    return body.profile ? body.profile.industry : null;
  } catch (error) {
    return null;
  }
}
async function loadNews() {
  if ($("news-view").hidden) return;
  const ticket = ++newsState.ticket;
  if (newsState.industry === null) newsState.industry = (await newsIndustry()) || "";
  if (newsState.filter === "mine" && !newsState.industry) newsState.filter = "all";
  const [, params] = NEWS_FILTERS.find(([key]) => key === newsState.filter);
  const query = new URLSearchParams({ limit: "30", ...params });
  if (newsState.filter === "mine") query.set("industry", newsState.industry);
  try {
    const items = await request("/v1/news?" + query);
    if (ticket !== newsState.ticket) return;
    newsState.items = items;
    newsState.failed = false;
  } catch (error) {
    if (ticket !== newsState.ticket) return;
    newsState.items = [];
    newsState.failed = true;
  }
  renderNews();
}

function renderNews() {
  const root = $("news-root");
  if (!root) return;
  root.replaceChildren(newsEl("h2", "news-title", newsT("title")), newsEl("p", "news-note", newsT("note")));
  const chips = newsEl("div", "news-chips");
  chips.setAttribute("role", "group");
  chips.setAttribute("aria-label", newsT("title"));
  for (const [key] of NEWS_FILTERS) {
    if (key === "mine" && !newsState.industry) continue;
    const b = newsEl("button", "news-chip", newsT(key));
    b.type = "button";
    b.dataset.filter = key;
    b.setAttribute("aria-pressed", String(newsState.filter === key));
    b.onclick = () => {
      newsState.filter = key;
      run(loadNews);
    };
    chips.append(b);
  }
  root.append(chips);
  if (newsState.failed) return root.append(newsEl("p", "news-empty", newsT("failed")));
  if (!newsState.items.length) return root.append(newsEl("p", "news-empty", newsT("empty")));
  const list = newsEl("ul", "news-list");
  newsState.items.forEach((item, index) => list.append(newsCard(item, index === 0)));
  root.append(list);
}

function newsCard(item, featured) {
  const li = newsEl("li", "news-card" + (featured ? " featured" : ""));
  li.dataset.id = item.id;
  const tags = newsEl("div", "news-tags");
  tags.append(newsEl("span", "news-tag cat-" + item.category, newsT(item.category)));
  const trades = item.industries || [];
  if (trades.length) for (const t of trades) tags.append(newsEl("span", "news-tag", newsT(t)));
  else tags.append(newsEl("span", "news-tag", newsT("everyone")));
  if (newsState.industry && trades.includes(newsState.industry)) tags.append(newsEl("span", "news-tag mine", newsT("affects")));
  // Feeds give RSS or ISO dates; show the day only, as people write it.
  const when = new Date(item.published_at || "");
  if (!Number.isNaN(when.getTime()))
    tags.append(newsEl("span", "news-date", new Intl.DateTimeFormat(lang === "cs" ? "cs-CZ" : "vi-VN", { day: "numeric", month: "numeric", year: "numeric", timeZone: "Europe/Prague" }).format(when)));
  li.append(tags, newsEl(featured ? "h3" : "h4", "news-head", item.vi_title), newsEl("p", "news-summary", item.vi_summary));
  const foot = newsEl("div", "news-foot");
  const refs = newsEl("p", "news-sources", newsT("sources") + ": ");
  (item.sources || []).forEach((s, i) => {
    if (i) refs.append(" · ");
    refs.append(newsLink(s.name, s.url));
  });
  foot.append(refs);
  if (item.authority_url) foot.append(newsEl("p", "news-official", newsLink(newsT("official"), item.authority_url)));
  if (state.org && (item.category === "law" || item.category === "notice")) {
    const done = newsState.added.has(state.org + "|" + item.id);
    const b = newsEl("button", "news-task", done ? newsT("added") : newsT("addTask"));
    b.type = "button";
    b.disabled = done;
    b.onclick = () => run(async () => {
      const org = state.org;
      const description = newsT("taskFrom") + ": " + item.vi_summary + "\n" + (item.authority_url || item.url);
      await request("/v1/organizations/" + encodeURIComponent(org) + "/tasks",
        json("POST", { title: item.vi_title.slice(0, 180), description: description.slice(0, 4000) }, crypto.randomUUID()));
      newsState.added.add(org + "|" + item.id);
      if (state.org === org) renderNews();
    }, b);
    foot.append(b);
  }
  li.append(foot);
  return li;
}

function refreshNews() {
  const seen = state.org + "|" + state.role;
  if (seen !== newsState.seen) {
    newsState.seen = seen;
    newsState.industry = null; // the trade belongs to the company
    newsState.ticket++;
    if (!$("news-view").hidden) run(loadNews);
    return;
  }
  renderNews(); // language change: same items, new labels
}
new MutationObserver(refreshNews).observe($("role-badge"), { childList: true, characterData: true, subtree: true });
$("news-tab").onclick = () => {
  setTab("news");
  run(loadNews);
};
$("phone-nav-news").onclick = () => {
  phoneGo("news");
  run(loadNews);
};
