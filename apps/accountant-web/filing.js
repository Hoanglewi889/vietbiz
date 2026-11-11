"use strict";
// Client profiles and the filing calendar (CR-8): what each company files, where, and by when.
// Dates and amounts come from the API; this file only shows them and edits the profile.
const filing = { items: [], missing: [], ticket: 0, profileTicket: 0, profileOrg: "", loadedOrg: "", saving: false,
  profile: null, made: new Set() };
const FILING_DAYS = 45;

function industryName(id) {
  const group = typeof LEGAL !== "undefined" && LEGAL.find((g) => g.id === id);
  return group ? group.icon + " " + group[lang] : t("industryOther");
}
const shortDate = (iso) =>
  new Intl.DateTimeFormat(lang === "cs" ? "cs-CZ" : "vi-VN", {
    day: "numeric",
    month: "numeric",
    year: "numeric",
    timeZone: "UTC",
  }).format(new Date(iso + "T00:00:00Z"));

async function loadDeadlines() {
  const ticket = ++filing.ticket;
  const body = await request("/v1/deadlines?days=" + FILING_DAYS);
  if (ticket !== filing.ticket) return;
  filing.items = body.items;
  filing.missing = body.profiles_missing;
  renderDeadlines();
  renderProfileOrgs();
}
function deadlineTitle(code, language = lang) {
  return COPY[language].deadlines[code] || code;
}
function deadlineRow(item) {
  const row = text("article", "", "deadline-row" + (item.conditional ? " conditional" : "")),
    when = text("div", "", "deadline-date"),
    body = text("div", "");
  when.append(text("strong", shortDate(item.due_date)));
  if (item.moved_from) when.append(text("small", fill(t("movedFrom"), { date: shortDate(item.moved_from) })));
  const meta = [item.name, COPY[lang].offices[item.office], fill(t("forPeriod"), { period: item.period })];
  if (item.conditional) meta.push(t("onlyIfApplies"));
  body.append(text("strong", deadlineTitle(item.code)), document.createElement("br"), text("small", meta.join(" · ")));
  if (item.amount) {
    const amount = text("p", "", "deadline-amount");
    amount.append(
      text("span", fill(t(item.amount.kind === "fixed" ? "fixedAmount" : "minimumAmount"),
        { amount: money(item.amount.value, item.amount.currency) })),
      // "official": read on the authority's own site; otherwise a secondary source to check.
      text("small", " · " + t(item.amount.status === "official" ? "officialFigure" : "checkOfficial") + " "),
    );
    const link = text("a", t("source"));
    link.href = item.amount.source;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    amount.append(link);
    body.append(amount);
  }
  const key = ["deadline", item.organization_id, item.code, item.period].join(":");
  const make = button(filing.made.has(key) ? t("taskCreated") : t("makeTask"), async () => {
    // Bilingual, stable title: the same deadline always maps to the same task.
    const title = (deadlineTitle(item.code, "vi") + " / " + deadlineTitle(item.code, "cs") + " · " + item.period).slice(0, 180);
    await request("/v1/organizations/" + item.organization_id + "/tasks", json("POST", {
      title,
      description: COPY.cs.offices[item.office] + " · " + item.source,
      priority: "normal",
      due_date: item.due_date,
    }, key));
    filing.made.add(key);
    make.textContent = t("taskCreated");
    notice(t("taskCreated"));
  });
  make.disabled = filing.made.has(key);
  row.append(when, body, make);
  return row;
}
function renderDeadlines() {
  if (!$("deadline-list")) return;
  const list = $("deadline-list"),
    missing = $("profiles-missing");
  list.replaceChildren(...filing.items.map(deadlineRow));
  if (!filing.items.length) empty(list, t("noDeadlines"), t("noDeadlinesHint"), "◷");
  missing.replaceChildren();
  missing.hidden = !filing.missing.length;
  if (filing.missing.length) {
    missing.append(text("span", t("profilesMissing") + " "));
    for (const company of filing.missing)
      missing.append(button(company.name, () => openProfile(company.organization_id), "secondary"));
  }
}
function renderProfileOrgs() {
  const sel = $("profile-org"),
    keep = filing.profileOrg;
  sel.replaceChildren(option("", t("chooseCompany")));
  for (const item of portfolio.items) sel.append(option(item.organization_id, item.name));
  sel.value = portfolio.items.some((i) => i.organization_id === keep) ? keep : "";
  renderProfileOptions();
}
function renderProfileOptions() {
  const pick = (id, values, labels) => {
    const sel = $(id),
      value = sel.value;
    sel.replaceChildren(...values.map((v) => option(v, labels(v))));
    if (values.includes(value)) sel.value = value;
  };
  pick("profile-form-legal", ["osvc", "sro"], (v) => COPY[lang].legalForms[v]);
  pick("profile-industry", ["grocery", "bistro", "nails", "hair", "tobacco", "herbal", "drogerie",
    "electronics", "textile", "import", "online", "other"], industryName);
  pick("profile-vat", ["none", "monthly", "quarterly", "identified"], (v) => COPY[lang].vatStatus[v]);
  pick("profile-activity", ["main", "secondary"], (v) => COPY[lang].osvcActivity[v]);
  pick("profile-band", ["", "1", "2", "3"], (v) => (v ? fill(t("flatBand"), { n: v }) : t("noFlatTax")));
  syncProfileForm();
}
function syncProfileForm() {
  const osvc = $("profile-form-legal").value === "osvc";
  $("profile-osvc-fields").hidden = !osvc;
  // § 7a ZDP: the flat-tax regime is closed to VAT payers and identified persons.
  const flatAllowed = osvc && $("profile-vat").value === "none";
  $("profile-band").disabled = !flatAllowed;
  if (!flatAllowed) $("profile-band").value = "";
  // Codex review, PR #13: only the company whose profile is loaded in the form can be saved,
  // never while another company's profile is still loading, after a failed load or mid-save.
  $("profile-save").disabled = filing.saving || !filing.loadedOrg || filing.loadedOrg !== filing.profileOrg;
}
async function openProfile(org) {
  filing.profileOrg = org;
  $("profile-org").value = org;
  const ticket = ++filing.profileTicket;
  filing.profile = null;
  filing.loadedOrg = "";
  $("profile-status").textContent = org ? "…" : "";
  syncProfileForm();
  if (!org) return;
  const body = await request("/v1/organizations/" + org + "/client-profile");
  if (ticket !== filing.profileTicket) return;
  filing.profile = body.profile;
  filing.loadedOrg = org;
  const p = body.profile || { legal_form: "osvc", industry: "grocery", vat_status: "none", has_employees: false,
    osvc_activity: "main", flat_tax_band: null, tax_adviser: false, health_insurer: null };
  $("profile-form-legal").value = p.legal_form;
  $("profile-industry").value = p.industry;
  $("profile-vat").value = p.vat_status;
  $("profile-activity").value = p.osvc_activity || "main";
  $("profile-band").value = p.flat_tax_band ? String(p.flat_tax_band) : "";
  $("profile-employees").checked = p.has_employees;
  $("profile-adviser").checked = p.tax_adviser;
  $("profile-insurer").value = p.health_insurer || "";
  $("profile-status").textContent = body.profile ? fill(t("profileVersion"), { v: body.profile.version }) : t("profileNew");
  syncProfileForm();
  $("profile-form").scrollIntoView({ block: "nearest" });
}
async function saveClientProfile() {
  const org = filing.profileOrg;
  if (!org || filing.loadedOrg !== org) throw { messageKey: "chooseCompanyFirst" };
  const ticket = filing.profileTicket;
  const osvc = $("profile-form-legal").value === "osvc";
  const body = {
    legal_form: $("profile-form-legal").value,
    industry: $("profile-industry").value,
    vat_status: $("profile-vat").value,
    has_employees: $("profile-employees").checked,
    osvc_activity: osvc ? $("profile-activity").value : null,
    flat_tax_band: osvc && $("profile-band").value ? Number($("profile-band").value) : null,
    tax_adviser: $("profile-adviser").checked,
    health_insurer: osvc ? $("profile-insurer").value.trim() || null : null,
    expected_version: filing.profile ? filing.profile.version : null,
  };
  filing.saving = true;
  syncProfileForm();
  try {
    const saved = await request("/v1/organizations/" + org + "/client-profile", json("PUT", body));
    // The form may have moved to another company meanwhile; its state is not this one's.
    if (ticket === filing.profileTicket) {
      filing.profile = saved.profile;
      $("profile-status").textContent = fill(t("profileVersion"), { v: saved.profile.version });
    }
  } catch (error) {
    if (error.status === 409) throw { messageKey: "profileConflict" };
    throw error;
  } finally {
    filing.saving = false;
    syncProfileForm();
  }
  notice(t("profileSaved"));
  await loadPortfolio();
}
// Called from resetPortfolio(): a new identity must never see another's calendar or profiles.
function resetFiling() {
  filing.ticket++;
  filing.profileTicket++;
  filing.items = [];
  filing.missing = [];
  filing.profileOrg = "";
  filing.loadedOrg = "";
  filing.saving = false;
  filing.profile = null;
  filing.made = new Set();
  $("deadline-list").replaceChildren();
  $("profiles-missing").replaceChildren();
  $("profile-status").textContent = "";
  // Codex review, PR #13: the previous identity's client values must not stay in the controls.
  $("profile-form").reset();
  $("profile-org").replaceChildren(option("", t("chooseCompany")));
  syncProfileForm();
}
$("profile-org").onchange = () => run(() => openProfile($("profile-org").value));
$("profile-form-legal").onchange = syncProfileForm;
$("profile-vat").onchange = syncProfileForm;
$("profile-form").onsubmit = (e) => {
  e.preventDefault();
  if (!$("profile-save").disabled) run(saveClientProfile);
};
