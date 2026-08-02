import {
  assembleIntakeFrame,
  INTAKE_FRAME_KIND,
  validateIntakeFrame,
} from "./intake-frame.mjs";

const deepFreeze = (value) => {
  if (value !== null && typeof value === "object" && !Object.isFrozen(value)) {
    for (const entry of Object.values(value)) deepFreeze(entry);
    Object.freeze(value);
  }
  return value;
};

const isFrame = (value) =>
  value !== null && typeof value === "object" && value.kind === INTAKE_FRAME_KIND;

const requireFrame = (value) =>
  isFrame(value) ? validateIntakeFrame(value) : assembleIntakeFrame(value);

const registrationLabel = (status) => {
  if (status === "inbox") return "Inbox";
  if (status === "eligible") return "Eligible frame";
  return "Withdrawn frame";
};

export function buildIntakeView(candidate) {
  const frame = requireFrame(candidate);
  const blockerItems = frame.blockers.map(({ code, message, source, subject }) => ({
    code,
    message,
    source,
    subject,
  }));
  const noticeItems = frame.notices.map(({ code, message, source, subject }) => ({
    code,
    message,
    source,
    subject,
  }));
  const reviewItems = frame.ontology_resolutions.flatMap((resolution) =>
    resolution.review_queue_items.map((item) => ({
      authority: item.required_authority_artifact,
      reasons: [...item.reasons],
      review_item_id: item.review_item_id,
    })),
  );
  const sections = [
    {
      id: "blockers",
      items: blockerItems,
      state: blockerItems.length ? "BLOCKED" : "CLEAR",
      title: "Blockers",
      visible: true,
    },
    {
      id: "scope-unknowns",
      items: frame.unknown_scope.map(({ path, source }) => ({ path, source })),
      state: frame.unknown_scope.length ? "VISIBLE_LIMITATIONS" : "CLEAR",
      title: "Scope unknowns",
      visible: true,
    },
    {
      id: "ontology-review",
      items: reviewItems,
      state: reviewItems.length ? "AUTHORITY_REQUIRED" : "CLEAR",
      title: "Ontology review",
      visible: true,
    },
    {
      id: "method-boundaries",
      items: noticeItems,
      state: noticeItems.length ? "VISIBLE_LIMITATIONS" : "CLEAR",
      title: "Method and authority notes",
      visible: true,
    },
  ];
  return deepFreeze({
    export_control: {
      enabled: frame.exportable,
      reason_codes: blockerItems.map(({ code }) => code),
      status: frame.exportable ? "READY" : "BLOCKED",
    },
    heading: registrationLabel(frame.insight_card.registration_status),
    inbox: {
      insight_id: frame.insight_card.insight_id,
      registration_status: frame.insight_card.registration_status,
      statement: frame.insight_card.statement,
      visible: frame.insight_card.registration_status === "inbox",
    },
    kind: "EpistemicFoundryIntakeView",
    sections,
    version: frame.version,
  });
}

const escapeHtml = (value) =>
  String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");

const renderItems = (items, emptyMessage, renderItem) => {
  if (!items.length) return `<p class="intake-empty">${escapeHtml(emptyMessage)}</p>`;
  return `<ol>${items.map((item) => `<li>${renderItem(item)}</li>`).join("")}</ol>`;
};

export function renderIntakePanel(candidate) {
  const view = buildIntakeView(candidate);
  const blockers = view.sections[0];
  const unknowns = view.sections[1];
  const reviews = view.sections[2];
  const notes = view.sections[3];
  const disabled = view.export_control.enabled ? "" : ' disabled aria-disabled="true"';

  return [
    `<main class="intake-panel" data-export-status="${escapeHtml(
      view.export_control.status,
    )}" data-registration-status="${escapeHtml(view.inbox.registration_status)}">`,
    `<header><h1>${escapeHtml(view.heading)}</h1><p>${escapeHtml(view.inbox.statement)}</p></header>`,
    `<section class="intake-blockers" aria-live="assertive" data-state="${escapeHtml(
      blockers.state,
    )}"><h2>Blockers</h2>${renderItems(
      blockers.items,
      "No export blockers.",
      (item) =>
        `<code>${escapeHtml(item.code)}</code> <span>${escapeHtml(item.message)}</span>`,
    )}</section>`,
    `<section class="intake-scope" data-state="${escapeHtml(
      unknowns.state,
    )}"><h2>Scope unknowns</h2>${renderItems(
      unknowns.items,
      "No recorded scope unknowns.",
      (item) => `<code>${escapeHtml(item.path)}</code> <span>${escapeHtml(item.source)}</span>`,
    )}</section>`,
    `<section class="intake-ontology" data-state="${escapeHtml(
      reviews.state,
    )}"><h2>Ontology review</h2>${renderItems(
      reviews.items,
      "No ontology review is queued.",
      (item) =>
        `<code>${escapeHtml(item.review_item_id)}</code> <span>${escapeHtml(
          item.authority,
        )}</span>`,
    )}</section>`,
    `<section class="intake-notes" data-state="${escapeHtml(
      notes.state,
    )}"><h2>Method and authority notes</h2>${renderItems(
      notes.items,
      "No additional method or authority notes.",
      (item) => `<code>${escapeHtml(item.code)}</code> <span>${escapeHtml(item.message)}</span>`,
    )}</section>`,
    `<footer><button type="button" data-action="export-frame"${disabled}>Export frame</button></footer>`,
    "</main>",
  ].join("");
}
