"use strict";
const $ = (id) => document.getElementById(id);
let lang = "vi";
const t = (key) => COPY[lang][key] || key;
const state = {
  api: "",
  user: "",
  org: "",
  role: "",
  epoch: 0,
  selection: 0,
  orgs: [],
  tasks: [],
  docs: [],
  next: null,
  task: null,
  comments: [],
  events: [],
  commentNext: null,
  eventNext: null,
  demo: null,
  extract: null,
  extractTicket: 0,
};
const retries = new Map();
const text = (tag, content, className = "") => {
  const el = document.createElement(tag);
  el.textContent = content;
  el.className = className;
  return el;
};
const option = (value, label) => {
  const el = text("option", label);
  el.value = value;
  return el;
};
const button = (label, fn, cls = "secondary") => {
  const el = text("button", label, cls);
  el.type = "button";
  el.onclick = () => run(fn, el);
  return el;
};
const label = (title, control) => {
  const el = text("label", "");
  el.append(text("span", title), control);
  return el;
};
const timestamp = (value) =>
  new Intl.DateTimeFormat(lang === "cs" ? "cs-CZ" : "vi-VN", {
    dateStyle: "short",
    timeStyle: "short",
    timeZone: "Europe/Prague",
  }).format(new Date(value));
const statusText = (status) => COPY[lang].statuses[status] || status;
function empty(target, title, hint = "", symbol = "◎") {
  const box = text("div", "", "empty");
  box.append(text("span", symbol, "empty-symbol"), text("h3", title));
  if (hint) box.append(text("p", hint));
  target.replaceChildren(box);
}
function notice(message, error = false) {
  $("notice").hidden = !message;
  $("notice").textContent = message;
  $("notice").classList.toggle("error", error);
}
function message(error) {
  return error.messageKey
    ? t(error.messageKey)
    : {
        401: t("unauthenticated"),
        403: t("accessDenied"),
        404: t("notFound"),
        409: t("conflict"),
        413: t("chooseFile"),
        415: t("chooseFile"),
        422: t("validation"),
      }[error.status] || t("failed");
}
async function run(fn, el) {
  if (el) el.disabled = true;
  try {
    await fn();
  } catch (error) {
    if (error.name !== "AbortError") notice(message(error), true);
  } finally {
    if (el && el.isConnected) {
      el.disabled =
        el.id === "upload-button" &&
        !["owner", "employee"].includes(state.role);
    }
  }
}
function localApi() {
  const u = new URL($("api").value);
  if (
    !["localhost", "127.0.0.1", "[::1]"].includes(u.hostname) ||
    !["http:", "https:"].includes(u.protocol) ||
    u.username ||
    u.password ||
    u.search ||
    u.hash ||
    (u.pathname !== "/" && u.pathname !== "")
  )
    throw { messageKey: "localOnly" };
  return u.origin;
}
async function request(path, options = {}) {
  const epoch = state.epoch;
  const r = await fetch(state.api + path, {
    ...options,
    redirect: "error",
    credentials: "omit",
    headers: {
      ...(state.user ? { "X-User": state.user } : {}),
      ...(options.headers || {}),
    },
  });
  if (epoch !== state.epoch)
    throw new DOMException("Stale company response", "AbortError");
  if (!r.ok) throw { status: r.status };
  const result = options.blob ? await r.blob() : await r.json();
  if (epoch !== state.epoch)
    throw new DOMException("Stale company response", "AbortError");
  return result;
}
function json(method, body, key) {
  return {
    method,
    headers: {
      "Content-Type": "application/json",
      ...(key ? { "Idempotency-Key": key } : {}),
    },
    body: JSON.stringify(body),
  };
}
function retryKey(scope, body) {
  const fingerprint = JSON.stringify(body),
    old = retries.get(scope);
  if (old && old.fingerprint === fingerprint) return old.key;
  const key = crypto.randomUUID();
  retries.set(scope, { fingerprint, key });
  return key;
}
const base = () => `/v1/organizations/${encodeURIComponent(state.org)}`;
function resetContext() {
  state.epoch++;
  state.selection++;
  state.org = "";
  state.role = "";
  state.tasks = [];
  state.docs = [];
  state.task = null;
  state.next = null;
  retries.clear();
  $("new-task").disabled = true;
  $("upload-button").disabled = true;
  $("more-tasks").hidden = true;
  $("create-dialog").close();
  closeExtraction();
  $("create-form").reset();
  $("upload-form").reset();
  $("role-badge").textContent = "";
  $("document-list").replaceChildren();
  for (const n of ["active", "waiting", "overdue", "done"])
    $("metric-" + n).textContent = "—";
  empty($("task-list"), t("startTitle"), t("startText"), "↗");
  empty($("detail-panel"), t("chooseTask"), t("detailHint"));
}
function renderOrgOptions(selected = "") {
  const select = $("org");
  select.replaceChildren(option("", t("chooseCompany")));
  state.orgs.forEach((o) => select.append(option(o.id, o.name)));
  select.value = selected;
  select.disabled = !state.orgs.length;
}
async function connect() {
  const api = localApi(),
    uid = $("user").value.trim();
  resetContext();
  state.api = api;
  state.user = uid;
  state.orgs = [];
  renderOrgOptions();
  const health = await request("/health");
  if (health.auth_mode !== "demo") throw { messageKey: "demoOnly" };
  state.orgs = await request("/v1/organizations");
  renderOrgOptions();
  if (!state.orgs.length) {
    notice(t("noCompanies"));
    return;
  }
  const preferred =
    state.orgs.find((o) => o.id === state.demo?.org) || state.orgs[0];
  $("org").value = preferred.id;
  await switchOrg();
  notice(t("connected"));
}
async function switchOrg() {
  const id = $("org").value;
  resetContext();
  if (!id) return;
  const org = state.orgs.find((o) => o.id === id);
  if (!org) return;
  state.org = id;
  state.role = org.role;
  $("role-badge").textContent = t(org.role);
  $("new-task").disabled = !["owner", "accountant"].includes(state.role);
  $("upload-button").disabled = !["owner", "employee"].includes(state.role);
  $("status-filter").value = "";
  $("overdue-filter").checked = false;
  await refresh();
}
async function refresh() {
  if (!state.org) return;
  await Promise.all([loadDocs(), loadTasks(), loadSummary()]);
  if (state.task) await selectTask(state.task.id);
}
async function loadSummary() {
  if (!["owner", "accountant"].includes(state.role)) return;
  const data = await request(base() + "/tasks/summary");
  const counts = data.by_status;
  $("metric-active").textContent = Object.entries(counts)
    .filter(([s]) => !["DONE", "CANCELLED"].includes(s))
    .reduce((n, [, v]) => n + v, 0);
  $("metric-waiting").textContent = counts.WAITING_CLIENT;
  $("metric-overdue").textContent = data.overdue;
  $("metric-done").textContent = counts.DONE;
}
let listRequest = 0;
async function loadTasks(more = false) {
  if (!state.org) return;
  if (!["owner", "accountant"].includes(state.role)) {
    empty($("task-list"), t("noTaskAccess"));
    return;
  }
  const ticket = ++listRequest;
  const q = new URLSearchParams({ limit: "20" });
  if ($("status-filter").value) q.set("status", $("status-filter").value);
  if ($("overdue-filter").checked) q.set("overdue", "true");
  if (more && state.next) q.set("cursor", state.next);
  if (!more) empty($("task-list"), t("loading"));
  try {
    const page = await request(base() + "/tasks?" + q);
    if (ticket !== listRequest) return;
    state.tasks = more ? [...state.tasks, ...page.items] : page.items;
    state.next = page.next_cursor;
    renderTasks();
  } catch (e) {
    if (e.name !== "AbortError" && ticket === listRequest) {
      state.tasks = [];
      $("more-tasks").hidden = true;
      empty($("task-list"), message(e));
    }
    throw e;
  }
}
function renderTasks() {
  const list = $("task-list");
  list.replaceChildren();
  for (const item of state.tasks) {
    const b = button(
      "",
      () => selectTask(item.id),
      "task-item" + (state.task?.id === item.id ? " selected" : ""),
    );
    b.setAttribute("aria-pressed", String(state.task?.id === item.id));
    const top = text("div", "", "task-item-top");
    top.append(
      text("span", statusText(item.status), "badge status-" + item.status),
    );
    if (item.priority === "high")
      top.append(text("span", t("urgent"), "priority"));
    const meta = text("div", "", "task-meta");
    meta.append(
      text(
        "span",
        item.due_date ? `${t("dueDate")}: ${item.due_date}` : t("noDue"),
        item.is_overdue ? "late" : "",
      ),
    );
    if (item.is_overdue) meta.append(text("span", t("overdue"), "late"));
    if (item.document_id) meta.append(text("span", "↳ " + t("documents")));
    b.append(top, text("h3", item.title), meta);
    list.append(b);
  }
  if (!state.tasks.length) empty(list, t("emptyTasks"), t("emptyHint"), "↗");
  $("more-tasks").hidden = !state.next;
}
async function selectTask(id) {
  const ticket = ++state.selection;
  state.task = null;
  empty($("detail-panel"), t("loading"));
  const path = base() + "/tasks/" + encodeURIComponent(id);
  try {
    const [task, comments, events] = await Promise.all([
      request(path),
      request(path + "/comments"),
      request(path + "/events"),
    ]);
    if (ticket !== state.selection) return;
    state.task = task;
    state.comments = comments.items;
    state.events = events.items;
    state.commentNext = comments.next_cursor;
    state.eventNext = events.next_cursor;
    renderTasks();
    renderDetail();
  } catch (e) {
    if (e.name !== "AbortError" && ticket === state.selection)
      empty($("detail-panel"), message(e));
    throw e;
  }
}
async function moreThread(kind) {
  const task = state.task,
    ticket = state.selection;
  if (!task) return;
  const cursor = kind === "comments" ? state.commentNext : state.eventNext;
  const page = await request(
    base() +
      "/tasks/" +
      task.id +
      "/" +
      kind +
      "?cursor=" +
      encodeURIComponent(cursor),
  );
  if (ticket !== state.selection) return;
  state[kind].push(...page.items);
  state[kind === "comments" ? "commentNext" : "eventNext"] = page.next_cursor;
  renderDetail();
}
function renderDetail() {
  const task = state.task;
  if (!task) {
    empty($("detail-panel"), t("chooseTask"), t("detailHint"));
    return;
  }
  const panel = $("detail-panel");
  panel.replaceChildren();
  const top = text("div", "", "detail-top");
  top.append(
    text("span", statusText(task.status), "badge status-" + task.status),
    text("small", `#${task.id.slice(0, 8)}`, "muted"),
  );
  panel.append(
    top,
    text("h2", task.title, "detail-title"),
    text("p", task.description, "detail-body"),
  );
  const meta = text("div", "", "detail-meta");
  meta.append(
    text(
      "span",
      task.due_date ? `${t("dueDate")}: ${task.due_date}` : t("noDue"),
    ),
  );
  if (task.is_overdue) meta.append(text("span", t("overdue"), "inline-error"));
  panel.append(meta);
  if (task.document_id)
    panel.append(
      button(t("original"), () => download(task.document_id), "link-button"),
    );
  if (task.available_transitions.length) {
    const form = text("form", "", "transition-form"),
      select = document.createElement("select"),
      reason = document.createElement("textarea"),
      submit = text("button", t("update"), "primary");
    select.id = "transition-status";
    task.available_transitions.forEach((s) =>
      select.append(option(s, statusText(s))),
    );
    reason.id = "transition-reason";
    reason.maxLength = 2000;
    reason.rows = 2;
    const setRequired = () => {
      reason.required = [
        "WAITING_CLIENT",
        "BLOCKED",
        "REOPENED",
        "CANCELLED",
      ].includes(select.value);
    };
    select.onchange = setRequired;
    setRequired();
    form.append(
      text("strong", t("changeStatus")),
      label(t("nextStatus"), select),
      label(t("reason"), reason),
      submit,
    );
    form.onsubmit = (e) => {
      e.preventDefault();
      run(async () => {
        try {
          await request(
            base() + "/tasks/" + task.id,
            json("PATCH", {
              version: task.version,
              status: select.value,
              reason: reason.value,
            }),
          );
          await Promise.all([loadTasks(), loadSummary()]);
          if (state.task?.id === task.id) await selectTask(task.id);
          notice(t("saved"));
        } catch (error) {
          if (error.status === 409 && state.task?.id === task.id)
            await selectTask(task.id);
          throw error;
        }
      }, submit);
    };
    panel.append(form);
  }
  panel.append(text("h3", t("conversation"), "section-label"));
  if (!state.comments.length) panel.append(text("p", t("noComments"), "muted"));
  for (const item of [...state.comments].reverse()) {
    const comment = text(
      "div",
      "",
      "comment" + (item.visibility === "accountant" ? " internal" : ""),
    );
    comment.append(
      text("p", item.body),
      text(
        "small",
        `${item.visibility === "accountant" ? t("internalNote") : t("clientNote")} · ${timestamp(item.created_at)}`,
      ),
    );
    panel.append(comment);
  }
  if (state.commentNext)
    panel.append(button(t("more"), () => moreThread("comments"), "more"));
  const form = text("form", "", "comment-form"),
    body = document.createElement("textarea"),
    visibility = document.createElement("select"),
    submit = text("button", t("send"), "primary");
  body.id = "reply-body";
  body.rows = 3;
  body.required = true;
  body.maxLength = 4000;
  visibility.id = "reply-visibility";
  visibility.append(option("client", t("clientNote")));
  if (state.role === "accountant")
    visibility.append(option("accountant", t("internalNote")));
  const row = text("div", "", "form-row");
  row.append(label(t("visibility"), visibility), submit);
  form.append(label(t("reply"), body), row);
  form.onsubmit = (e) => {
    e.preventDefault();
    run(async () => {
      const value = { body: body.value, visibility: visibility.value },
        scope = "comment:" + task.id;
      await request(
        base() + "/tasks/" + task.id + "/comments",
        json("POST", value, retryKey(scope, value)),
      );
      retries.delete(scope);
      if (state.task?.id === task.id) await selectTask(task.id);
      notice(t("saved"));
    }, submit);
  };
  panel.append(form, text("h3", t("history"), "section-label"));
  const history = text("ol", "", "history");
  for (const event of state.events) {
    const li = text(
      "li",
      event.from_status
        ? `${statusText(event.from_status)} → ${statusText(event.to_status)}`
        : t("created"),
    );
    li.append(text("small", timestamp(event.created_at)));
    if (event.reason) li.append(text("p", event.reason));
    history.append(li);
  }
  panel.append(history);
  if (state.eventNext)
    panel.append(button(t("more"), () => moreThread("events"), "more"));
}
async function loadDocs() {
  if (!state.org) return;
  state.docs = await request(base() + "/documents");
  renderDocs();
}
function renderDocs() {
  const list = $("document-list");
  list.replaceChildren();
  for (const doc of state.docs) {
    const row = text("div", "", "document"),
      info = text("div", "");
    info.append(
      text("strong", doc.filename),
      text(
        "small",
        (COPY[lang].docStatuses[doc.status] || doc.status) +
          " · " +
          timestamp(doc.created_at),
      ),
    );
    row.append(
      info,
      button(t("original"), () => download(doc.id)),
    );
    if (["owner", "accountant"].includes(state.role)) {
      row.append(button(t("invoiceData"), () => openExtraction(doc.id)));
      row.append(button(t("requestForDoc"), () => openCreate(doc.id)));
      if (doc.status === "needs_review")
        row.append(
          button(
            t("approve"),
            async () => {
              await request(
                base() + "/documents/" + doc.id + "/review",
                json("POST", { decision: "approve" }),
              );
              await loadDocs();
              notice(t("saved"));
            },
            "primary",
          ),
        );
    }
    list.append(row);
  }
  if (!state.docs.length) empty(list, t("noDocuments"));
}
async function download(id) {
  const blob = await request(
      base() + "/documents/" + encodeURIComponent(id) + "/original",
      { blob: true },
    ),
    url = URL.createObjectURL(blob),
    a = document.createElement("a");
  a.href = url;
  a.download = state.docs.find((d) => d.id === id)?.filename || "document";
  a.click();
  setTimeout(() => URL.revokeObjectURL(url), 1000);
}
/* Invoice data (CR-1): original beside manually entered fields and the VAT Act check. */
const FIELD_KEYS = [
  "supplier_name",
  "supplier_vat_id",
  "document_number",
  "subject",
  "issue_date",
  "supply_date",
  "customer_name",
  "customer_vat_id",
];
const OPEN_DOC = ["needs_review", "needs_changes"];
const decimal = (value) => {
  const v = value.replace(/\s/g, "").replace(",", ".");
  return v === "" ? null : v;
};
const extractUrl = (id) =>
  base() + "/documents/" + encodeURIComponent(id) + "/extraction";
function format(template, detail = {}) {
  return template.replace(/\{(\w+)\}/g, (_, key) =>
    key === "line" ? String((detail.line ?? 0) + 1) : String(detail[key] ?? ""),
  );
}
function lineRow(line = {}) {
  const row = text("div", "", "vat-line");
  for (const [key, title] of [
    ["rate", "rate"],
    ["base", "base"],
    ["tax", "tax"],
  ]) {
    const input = document.createElement("input");
    input.inputMode = "decimal";
    input.autocomplete = "off";
    input.dataset.key = key;
    input.value = line[key] ?? "";
    input.disabled = !!state.extract?.locked;
    row.append(label(t(title), input));
  }
  const remove = text("button", "×", "icon-button remove-line");
  remove.type = "button";
  remove.setAttribute("aria-label", t("removeLine"));
  remove.disabled = !!state.extract?.locked;
  remove.onclick = () => {
    row.remove();
    syncLines();
  };
  row.append(remove);
  return row;
}
function syncLines() {
  $("x-add-line").disabled =
    !!state.extract?.locked || $("x-lines").children.length >= 10;
}
function readLines() {
  return [...$("x-lines").children].map((row) => {
    const value = (key) => row.querySelector(`[data-key="${key}"]`).value;
    return { rate: value("rate"), base: value("base"), tax: value("tax") };
  });
}
function renderLines(lines) {
  $("x-lines").replaceChildren(...lines.map(lineRow));
  syncLines();
}
function fillForm(fields = {}) {
  for (const key of FIELD_KEYS) $("x-" + key).value = fields[key] ?? "";
  $("x-total").value = fields.total ?? "";
  $("x-currency").value = fields.currency || "CZK";
  $("x-exempt").checked = !!fields.exempt;
  $("x-reverse_charge").checked = !!fields.reverse_charge;
  renderLines(fields.lines?.length ? fields.lines : [{}]);
}
function readForm() {
  const fields = {};
  for (const key of FIELD_KEYS) fields[key] = $("x-" + key).value.trim() || null;
  fields.total = decimal($("x-total").value);
  fields.currency = $("x-currency").value;
  fields.exempt = $("x-exempt").checked;
  fields.reverse_charge = $("x-reverse_charge").checked;
  fields.lines = readLines()
    .map((line) => ({
      rate: decimal(line.rate),
      base: decimal(line.base),
      tax: decimal(line.tax),
    }))
    .filter((line) => line.rate || line.base || line.tax);
  return fields;
}
function renderCheck() {
  const body = $("check-body"),
    data = state.extract?.data;
  body.replaceChildren();
  if (!data) {
    body.append(text("p", t("noDataYet"), "muted"));
    return;
  }
  const check = data.check,
    meta = text("div", "", "check-meta");
  meta.append(
    text("span", COPY[lang].kinds[check.kind] || check.kind, "badge neutral"),
    text(
      "span",
      t(check.complete ? "checkComplete" : "checkIncomplete"),
      "badge " + (check.complete ? "ok" : "warn"),
    ),
    text(
      "small",
      t("revision") + " " + data.version + " · " + timestamp(data.updated_at),
      "muted",
    ),
  );
  body.append(meta);
  if (!check.findings.length) return;
  const list = text("ul", "", "findings");
  for (const f of check.findings) {
    const item = text("li", "", f.severity);
    item.append(
      text("strong", COPY[lang].severities[f.severity] || f.severity),
      text("span", format(COPY[lang].findings[f.code] || f.code, f.detail)),
      text("small", f.basis),
    );
    list.append(item);
  }
  body.append(list);
}
function renderExtractionState() {
  const x = state.extract,
    doc = state.docs.find((d) => d.id === x.doc);
  x.locked = !doc || !OPEN_DOC.includes(doc.status);
  $("extract-file").textContent = doc
    ? doc.filename + " · " + (COPY[lang].docStatuses[doc.status] || doc.status)
    : "";
  $("extract-form")
    .querySelectorAll("input, select")
    .forEach((el) => (el.disabled = x.locked));
  $("extract-save").disabled = x.locked;
  const decide = !!doc && doc.status === "needs_review";
  $("extract-approve").hidden = !decide;
  $("extract-request-changes").hidden = !decide;
  $("extract-error").textContent = x.locked ? t("dataLocked") : "";
  const imported = x.data?.source === "isdoc";
  $("x-source").textContent = t(imported ? "isdocSourceNotice" : "manualEntryNotice");
  $("x-source").classList.toggle("imported", imported);
  renderLines(readLines());
  renderCheck();
}
async function showPreview(id) {
  const x = state.extract,
    doc = state.docs.find((d) => d.id === id),
    box = $("extract-preview");
  box.replaceChildren(text("p", "…", "muted"));
  const blob = await request(
    base() + "/documents/" + encodeURIComponent(id) + "/original",
    { blob: true },
  );
  if (state.extract !== x) return;
  x.url = URL.createObjectURL(blob);
  let view;
  if (doc?.mime === "application/pdf") {
    view = document.createElement("iframe");
    view.title = t("originalPreview") + " · " + doc.filename;
  } else if (doc?.mime?.startsWith("image/")) {
    view = document.createElement("img");
    view.alt = t("originalPreview") + " · " + doc.filename;
  }
  if (!view) {
    box.replaceChildren(text("p", t("noPreview"), "muted"));
    return;
  }
  view.src = x.url;
  box.replaceChildren(view);
}
async function loadExtraction() {
  const x = state.extract;
  try {
    x.data = await request(extractUrl(x.doc));
  } catch (error) {
    if (error.status !== 404) throw error;
    x.data = null;
  }
  if (state.extract !== x) return;
  fillForm(x.data?.fields);
  x.saved = JSON.stringify(readForm());
  renderExtractionState();
}
const unsavedEdits = (x) => x.saved !== JSON.stringify(readForm());
async function openExtraction(id) {
  closeExtraction();
  const x = (state.extract = {
    doc: id,
    data: null,
    url: "",
    locked: false,
    ticket: ++state.extractTicket,
  });
  fillForm();
  x.saved = JSON.stringify(readForm());
  renderExtractionState();
  $("extract-dialog").showModal();
  $("x-supplier_name").focus();
  await Promise.all([showPreview(id), loadExtraction()]);
  if (state.extract === x) $("x-supplier_name").focus();
}
function closeExtraction() {
  const x = state.extract;
  state.extract = null;
  if (x?.url) URL.revokeObjectURL(x.url);
  $("extract-preview").replaceChildren();
  if ($("extract-dialog").open) $("extract-dialog").close();
}
async function saveExtraction() {
  const x = state.extract;
  $("extract-error").textContent = "";
  try {
    const data = await request(
      extractUrl(x.doc),
      json("PUT", {
        version: x.data?.version ?? 0,
        source: "manual",
        fields: readForm(),
      }),
    );
    if (state.extract !== x) return;
    x.data = data;
    fillForm(data.fields);
    x.saved = JSON.stringify(readForm());
    renderExtractionState();
    notice(t("saved"));
  } catch (error) {
    if (error.status === 409 && state.extract === x) {
      await loadDocs();
      await loadExtraction();
      $("extract-error").textContent = t("dataConflict");
      return;
    }
    if (state.extract === x) $("extract-error").textContent = message(error);
    throw error;
  }
}
async function decideFromExtraction(decision) {
  const x = state.extract;
  // A decision locks the data, so unsaved edits would be lost silently.
  if (unsavedEdits(x)) {
    $("extract-error").textContent = t("saveBeforeDecision");
    return;
  }
  try {
    await request(
      base() + "/documents/" + encodeURIComponent(x.doc) + "/review",
      json("POST", { decision }),
    );
  } finally {
    await loadDocs();
    if (state.extract === x) renderExtractionState();
  }
  notice(t("saved"));
}
function openCreate(doc = "") {
  if (!state.org) throw { messageKey: "chooseCompanyFirst" };
  const sel = $("task-document");
  sel.replaceChildren(option("", t("noDocument")));
  state.docs.forEach((d) => sel.append(option(d.id, d.filename)));
  sel.value = doc;
  $("create-error").textContent = "";
  $("create-dialog").showModal();
  $("task-title").focus();
}
function translate() {
  document.documentElement.lang = lang;
  document
    .querySelectorAll("[data-i18n]")
    .forEach((el) => (el.textContent = t(el.dataset.i18n)));
  const filter = $("status-filter"),
    value = filter.value;
  filter.replaceChildren(option("", t("allStatuses")));
  Object.keys(COPY[lang].statuses).forEach((s) =>
    filter.append(option(s, statusText(s))),
  );
  filter.value = value;
  renderOrgOptions(state.org);
  if (state.role) $("role-badge").textContent = t(state.role);
  if (state.demo) renderDemoRoles();
  if (state.org) {
    renderTasks();
    renderDocs();
  } else empty($("task-list"), t("startTitle"), t("startText"), "↗");
  renderDetail();
  if (state.extract) renderExtractionState();
}
function renderDemoRoles() {
  const sel = $("demo-role");
  sel.replaceChildren(
    option(state.demo.accountant, t("accountant")),
    option(state.demo.owner, t("owner")),
  );
  sel.value = state.user;
  $("demo-role-label").hidden = false;
}
function setTab(which) {
  for (const name of ["tasks", "docs"]) {
    $(name + "-view").hidden = name !== which;
    $(name + "-tab").classList.toggle("active", name === which);
    $(name + "-tab").setAttribute("aria-pressed", String(name === which));
  }
}
async function seedDemo() {
  state.api = localApi();
  state.epoch++;
  const health = await request("/health");
  if (health.auth_mode !== "demo") throw { messageKey: "demoOnly" };
  if (state.demo && state.demo.api === state.api) {
    $("user").value = state.demo.accountant;
    await connect();
    return;
  }
  resetContext();
  state.user = "";
  state.orgs = [];
  renderOrgOptions();
  const owner = (
      await request("/dev/users?display_name=Demo%20owner", { method: "POST" })
    ).id,
    accountant = (
      await request("/dev/users?display_name=Demo%20accountant", {
        method: "POST",
      })
    ).id;
  state.user = owner;
  const org = (
    await request(
      "/v1/organizations",
      json("POST", { name: "Potraviny Vltava · DEMO" }),
    )
  ).id;
  state.org = org;
  const invitation = (
    await request(
      base() + "/members",
      json("POST", { user_id: accountant, role: "accountant" }),
    )
  ).id;
  state.user = accountant;
  await request("/v1/invitations/" + invitation + "/accept", {
    method: "POST",
  });
  state.user = owner;
  const form = new FormData();
  form.append(
    "file",
    new Blob(
      [
        Uint8Array.from(
          atob(
            "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+j6l8AAAAASUVORK5CYII=",
          ),
          (c) => c.charCodeAt(0),
        ),
      ],
      { type: "image/png" },
    ),
    "sample-only.png",
  );
  const doc = (
    await request(base() + "/documents", { method: "POST", body: form })
  ).id;
  await request(
    base() + "/documents/" + doc + "/extraction",
    json("PUT", {
      version: 0,
      source: "manual",
      fields: {
        supplier_name: "Velkoobchod Ukázka s.r.o. · DEMO",
        supplier_vat_id: null,
        document_number: "DEMO-204",
        subject: "Potraviny a drogerie (dữ liệu mẫu / ukázka)",
        issue_date: "2026-10-30",
        currency: "CZK",
        total: "3208.00",
        lines: [
          { rate: "12", base: "2000.00", tax: "240.00" },
          { rate: "21", base: "800.00", tax: "168.00" },
        ],
      },
    }),
  );
  state.user = accountant;
  const date = new Date(),
    due = new Intl.DateTimeFormat("en-CA", {
      timeZone: "Europe/Prague",
    }).format(date);
  date.setDate(date.getDate() - 1);
  const yesterday = new Intl.DateTimeFormat("en-CA", {
    timeZone: "Europe/Prague",
  }).format(date);
  const samples = [
    {
      title: "Bổ sung thông tin hóa đơn / Doplnit fakturu",
      description:
        "Dữ liệu giả lập. Vui lòng xác nhận mục đích mua hàng.\nUkázková data. Doplňte účel nákupu.",
      document_id: doc,
      priority: "high",
      due_date: yesterday,
    },
    {
      title: "Đối chiếu chứng từ tháng / Kontrola dokladů",
      description:
        "Kiểm tra chứng từ đã gửi trong tháng.\nZkontrolujte doklady odeslané za tento měsíc.",
      due_date: due,
    },
    {
      title: "Xác nhận thông tin cửa hàng / Údaje provozovny",
      description:
        "Kiểm tra tên cửa hàng trong hồ sơ mẫu.\nOvěřte název provozovny v ukázkovém záznamu.",
    },
  ];
  let first;
  for (const sample of samples) {
    const task = await request(
      base() + "/tasks",
      json("POST", sample, crypto.randomUUID()),
    );
    if (!first) {
      first = task;
      await request(
        base() + "/tasks/" + task.id,
        json("PATCH", {
          version: task.version,
          status: "WAITING_CLIENT",
          reason:
            "Cần cửa hàng bổ sung mục đích mua hàng. / Klient doplní účel nákupu.",
        }),
      );
      await request(
        base() + "/tasks/" + task.id + "/comments",
        json(
          "POST",
          {
            body: "Ghi chú nội bộ mẫu / Interní ukázková poznámka",
            visibility: "accountant",
          },
          crypto.randomUUID(),
        ),
      );
    }
  }
  state.demo = { api: state.api, org, owner, accountant };
  $("user").value = accountant;
  renderDemoRoles();
  await connect();
  await selectTask(first.id);
  notice(t("demoReady"));
}
$("connect-form").onsubmit = (e) => {
  e.preventDefault();
  run(connect, e.submitter);
};
$("org").onchange = () => run(switchOrg);
$("demo").onclick = () => run(seedDemo, $("demo"));
$("demo-role").onchange = () => {
  $("user").value = $("demo-role").value;
  run(connect);
};
$("language").onchange = () => {
  lang = $("language").value;
  translate();
};
$("status-filter").onchange = () => run(() => loadTasks());
$("overdue-filter").onchange = () => run(() => loadTasks());
$("refresh").onclick = () => run(refresh, $("refresh"));
$("more-tasks").onclick = () => run(() => loadTasks(true), $("more-tasks"));
$("new-task").onclick = () => openCreate();
$("close-dialog").onclick = () => $("create-dialog").close();
$("create-form").onsubmit = (e) => {
  e.preventDefault();
  const el = e.submitter;
  run(async () => {
    const body = {
      title: $("task-title").value,
      description: $("task-description").value,
      document_id: $("task-document").value || null,
      priority: $("task-priority").value,
      due_date: $("task-due").value || null,
    };
    try {
      const task = await request(
        base() + "/tasks",
        json("POST", body, retryKey("create", body)),
      );
      retries.delete("create");
      $("create-dialog").close();
      $("create-form").reset();
      $("status-filter").value = "";
      $("overdue-filter").checked = false;
      setTab("tasks");
      await Promise.all([loadTasks(), loadSummary()]);
      await selectTask(task.id);
      notice(t("created"));
    } catch (error) {
      $("create-error").textContent = message(error);
      throw error;
    }
  }, el);
};
$("upload-form").onsubmit = (e) => {
  e.preventDefault();
  run(async () => {
    const form = new FormData();
    form.append("file", $("upload-file").files[0]);
    await request(base() + "/documents", { method: "POST", body: form });
    $("upload-form").reset();
    await loadDocs();
    notice(t("saved"));
  }, e.submitter);
};
$("close-extract").onclick = () => closeExtraction();
$("extract-dialog").addEventListener("close", () => {
  if (state.extract) closeExtraction();
});
$("x-add-line").onclick = () => {
  $("x-lines").append(lineRow());
  syncLines();
};
$("extract-form").onsubmit = (e) => {
  e.preventDefault();
  run(saveExtraction, $("extract-save"));
};
$("extract-approve").onclick = () =>
  run(() => decideFromExtraction("approve"), $("extract-approve"));
$("extract-request-changes").onclick = () =>
  run(
    () => decideFromExtraction("request_changes"),
    $("extract-request-changes"),
  );
$("tasks-tab").onclick = () => setTab("tasks");
$("docs-tab").onclick = () => setTab("docs");
if (
  ["localhost", "127.0.0.1", "[::1]"].includes(location.hostname) &&
  location.port !== "3000"
)
  $("api").value = location.origin;
translate();
