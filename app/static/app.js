const appState = {
  settings: null,
  draftSettings: null,
  services: [],
  jobs: [],
  logs: new Map(),
  previewBusy: new Set(),
  detailSections: new Set(),
  dirty: false,
  flashTimeout: null,
};

const globalForm = document.getElementById("global-settings-form");
const servicesGrid = document.getElementById("services-grid");
const statusSummary = document.getElementById("status-summary");
const saveButton = document.getElementById("save-button");
const refreshButton = document.getElementById("refresh-button");
const regenerateAllButton = document.getElementById("regenerate-all-button");
const flashMessage = document.getElementById("flash-message");

const selectOptions = {
  pages: [
    [1, "1 page"],
    [2, "2 pages"],
    [4, "4 pages"],
    [6, "6 pages"],
    [8, "8 pages"],
  ],
  imageSizes: [
    ["w780", "w780"],
    ["w1280", "w1280"],
    ["original", "original"],
  ],
  pollSeconds: [
    [30, "30 seconds"],
    [60, "60 seconds"],
    [300, "5 minutes"],
  ],
  maxConcurrent: [
    [1, "1 job"],
    [2, "2 jobs"],
    [3, "3 jobs"],
    [4, "4 jobs"],
  ],
  retryMinutes: [
    [15, "15 minutes"],
    [30, "30 minutes"],
    [60, "1 hour"],
    [180, "3 hours"],
  ],
  codec: [
    ["vp9", "VP9"],
    ["vp8", "VP8"],
  ],
  fps: [
    [24, "24"],
    [30, "30"],
    [60, "60"],
  ],
  refreshIntervals: [
    [360, "6 hours"],
    [720, "12 hours"],
    [1440, "24 hours"],
    [2880, "48 hours"],
    [10080, "7 days"],
  ],
  contentMode: [
    ["mixed", "Movies + TV"],
    ["movie", "Movies only"],
    ["tv", "TV only"],
  ],
  artworkMode: [
    ["title_cards", "Title cards preferred"],
    ["clean_backdrops", "Clean backdrops preferred"],
  ],
  qualityPreset: [
    ["high", "High"],
    ["balanced", "Balanced"],
    ["small", "Small"],
    ["tiny", "Tiny"],
  ],
};

const globalFields = [
  {
    key: "scheduler_enabled",
    type: "checkbox",
    label: "Automatic refresh",
    help: "When off, nothing renders on a schedule. Manual preview and render still work.",
  },
  { key: "tmdb_bearer_token", type: "password", label: "TMDB bearer token" },
  { key: "tmdb_api_key", type: "password", label: "TMDB v3 API key" },
  { key: "default_region", type: "text", label: "Default region" },
  { key: "tmdb_language", type: "text", label: "TMDB language" },
  { key: "pages_per_media_type", type: "select", label: "Pages per media type", options: selectOptions.pages, cast: "number" },
  { key: "image_size", type: "select", label: "TMDB image size", options: selectOptions.imageSizes },
  { key: "scheduler_poll_seconds", type: "select", label: "Poll interval", options: selectOptions.pollSeconds, cast: "number" },
  { key: "max_concurrent_jobs", type: "select", label: "Max concurrent jobs", options: selectOptions.maxConcurrent, cast: "number" },
  { key: "failure_retry_minutes", type: "select", label: "Retry after failure", options: selectOptions.retryMinutes, cast: "number" },
];

const globalDefaultFields = [
  { key: "output_width", type: "number", label: "Default output width" },
  { key: "output_height", type: "number", label: "Default output height" },
  { key: "fps", type: "select", label: "Default FPS", options: selectOptions.fps, cast: "number" },
  { key: "codec", type: "select", label: "Default codec", options: selectOptions.codec },
  { key: "quality_preset", type: "select", label: "Default quality", options: selectOptions.qualityPreset },
  { key: "cpu_used", type: "number", label: "Default cpu-used" },
  { key: "loop_duration_seconds", type: "slider", label: "Default loop length", min: 20, max: 180, step: 5, unit: "s" },
  { key: "card_width", type: "slider", label: "Default card width", min: 220, max: 520, step: 2, unit: "px" },
  { key: "gap", type: "slider", label: "Default gap", min: 0, max: 40, step: 1, unit: "px" },
  { key: "row_count", type: "slider", label: "Default rows", min: 2, max: 10, step: 1 },
  { key: "corner_radius", type: "slider", label: "Default corner radius", min: 0, max: 32, step: 1, unit: "px" },
  { key: "rotate_z", type: "slider", label: "Default rotate Z", min: -18, max: 18, step: 0.5, unit: "deg" },
  { key: "zoom", type: "slider", label: "Default zoom", min: 0.8, max: 1.3, step: 0.01 },
  { key: "crf", type: "slider", label: "Default CRF", min: 20, max: 45, step: 1 },
];

const serviceToggleFields = [
  {
    key: "enabled",
    type: "checkbox",
    label: "Service enabled",
    help: "Keeps the service active in the dashboard and available for manual render.",
  },
  {
    key: "auto_refresh_enabled",
    type: "checkbox",
    label: "Auto-refresh this service",
    help: "Requires the global scheduler to be on before scheduled regeneration starts.",
  },
];

const serviceControlFields = [
  { key: "provider_id", type: "number", label: "Provider ID" },
  { key: "region", type: "text", label: "Region" },
  { key: "content_mode", type: "select", label: "Content", options: selectOptions.contentMode },
  { key: "artwork_mode", type: "select", label: "Artwork mode", options: selectOptions.artworkMode },
  { key: "refresh_interval_minutes", type: "select", label: "Refresh interval", options: selectOptions.refreshIntervals, cast: "number" },
  { key: "fps", type: "select", label: "FPS", options: selectOptions.fps, cast: "number" },
  { key: "codec", type: "select", label: "Codec", options: selectOptions.codec },
  { key: "quality_preset", type: "select", label: "Quality preset", options: selectOptions.qualityPreset },
];

const serviceSliderFields = [
  { key: "loop_duration_seconds", type: "slider", label: "Loop length", min: 20, max: 180, step: 5, unit: "s" },
  { key: "card_width", type: "slider", label: "Card width", min: 220, max: 520, step: 2, unit: "px" },
  { key: "gap", type: "slider", label: "Gap", min: 0, max: 40, step: 1, unit: "px" },
  { key: "row_count", type: "slider", label: "Rows", min: 2, max: 10, step: 1 },
  { key: "corner_radius", type: "slider", label: "Corner radius", min: 0, max: 32, step: 1, unit: "px" },
  { key: "rotate_z", type: "slider", label: "Rotate Z", min: -18, max: 18, step: 0.5, unit: "deg" },
  { key: "zoom", type: "slider", label: "Zoom", min: 0.8, max: 1.3, step: 0.01 },
  { key: "crf", type: "slider", label: "CRF", min: 20, max: 45, step: 1 },
];

const serviceAdvancedFields = [
  { key: "output_width", type: "number", label: "Output width" },
  { key: "output_height", type: "number", label: "Output height" },
  { key: "rotate_x", type: "number", label: "Rotate X", step: "0.1" },
  { key: "rotate_y", type: "number", label: "Rotate Y", step: "0.1" },
  { key: "skew_x", type: "number", label: "Skew X", step: "0.01" },
  { key: "skew_y", type: "number", label: "Skew Y", step: "0.01" },
  { key: "cpu_used", type: "number", label: "cpu-used" },
  { key: "target_bitrate_kbps", type: "number", label: "Target bitrate kbps" },
  { key: "max_titles", type: "number", label: "Max titles" },
  { key: "max_artwork_images", type: "number", label: "Max artwork images" },
  { key: "minimum_usable_images", type: "number", label: "Minimum usable images" },
  { key: "seed", type: "number", label: "Seed" },
];

function deepClone(value) {
  return structuredClone(value);
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function formatDate(value) {
  if (!value) return "Manual only";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Manual only";
  return date.toLocaleString();
}

function formatBytes(value) {
  if (!value) return "0 B";
  const units = ["B", "KB", "MB", "GB"];
  let amount = value;
  let unitIndex = 0;
  while (amount >= 1024 && unitIndex < units.length - 1) {
    amount /= 1024;
    unitIndex += 1;
  }
  return `${amount.toFixed(amount >= 10 || unitIndex === 0 ? 0 : 1)} ${units[unitIndex]}`;
}

function formatProgress(value) {
  return `${Math.round(value || 0)}%`;
}

function formatSliderValue(field, value) {
  const numeric = Number(value ?? 0);
  if (field.unit === "s") return `${numeric}s`;
  if (field.unit === "px") return `${numeric}px`;
  if (field.unit === "deg") return `${numeric.toFixed(1)}deg`;
  if (field.key === "zoom") return `${numeric.toFixed(2)}x`;
  if (field.step && String(field.step).includes(".")) return numeric.toFixed(2).replace(/\.00$/, "");
  return `${numeric}`;
}

function fieldByKey(collection, key) {
  return collection.find((field) => field.key === key) || null;
}

function getDraftService(slug) {
  return appState.draftSettings?.services.find((service) => service.slug === slug) || null;
}

function latestJobForSlug(slug) {
  return appState.jobs.find((job) => job.slug === slug && (job.status === "queued" || job.status === "running")) || null;
}

function mergedServiceView(servicePayload) {
  return {
    ...servicePayload,
    draft: getDraftService(servicePayload.slug) || servicePayload.settings,
    state: servicePayload.state || {},
    job: latestJobForSlug(servicePayload.slug),
  };
}

function automationLabel(serviceView) {
  return serviceView.automation?.automatic_generation_active ? "Auto refresh on" : "Manual only";
}

function renderBadge(serviceView) {
  const status = serviceView.job?.status || serviceView.state.status || "idle";
  if (status === "running") return `<span class="badge warn">Rendering</span>`;
  if (status === "queued") return `<span class="badge warn">Queued</span>`;
  if (status === "failed") return `<span class="badge error">Failed</span>`;
  if (status === "succeeded") return `<span class="badge success">Ready</span>`;
  return `<span class="badge">${escapeHtml(status)}</span>`;
}

function previewStage(serviceView) {
  const previewUpdated = serviceView.state.preview_generated_at;
  const liveUpdated = serviceView.state.last_generated_at;
  const previewCacheBust = previewUpdated ? `?t=${encodeURIComponent(previewUpdated)}` : "";
  const liveCacheBust = liveUpdated ? `?t=${encodeURIComponent(liveUpdated)}` : "";

  if (serviceView.preview_exists) {
    return {
      label: "Draft preview",
      media: `
        <video
          controls
          loop
          muted
          playsinline
          preload="metadata"
          poster="${serviceView.urls.preview_image}${previewCacheBust}"
          src="${serviceView.urls.preview_video}${previewCacheBust}"
        ></video>
      `,
      note: "Preview uses the same server-side compositor and motion timing at a lighter preview size. Render final to publish the stable hosted WebM.",
    };
  }

  if (serviceView.file_exists) {
    return {
      label: "Live asset",
      media: `
        <video
          controls
          loop
          muted
          playsinline
          preload="metadata"
          poster="${serviceView.urls.thumbnail}${liveCacheBust}"
          src="${serviceView.urls.hero}${liveCacheBust}"
        ></video>
      `,
      note: "No draft preview yet. The player above is the exact hosted WebM currently served to downstream apps.",
    };
  }

  return {
    label: "No media yet",
    media: `<div class="media-placeholder">Generate a preview to inspect the composition before you render the full hero file.</div>`,
    note: "Preview first, then save and render when the look feels right.",
  };
}

function renderToggleField(field, value, attrs) {
  return `
    <label class="toggle-card">
      <div class="toggle-copy">
        <strong>${escapeHtml(field.label)}</strong>
        <small>${escapeHtml(field.help || "")}</small>
      </div>
      <input type="checkbox" ${attrs} ${value ? "checked" : ""} />
    </label>
  `;
}

function renderSelectField(field, value, attrs) {
  const options = field.options
    .map(([optionValue, optionLabel]) => {
      const selected = String(value) === String(optionValue) ? "selected" : "";
      return `<option value="${escapeHtml(optionValue)}" ${selected}>${escapeHtml(optionLabel)}</option>`;
    })
    .join("");

  return `
    <label class="control">
      <span class="control-label">${escapeHtml(field.label)}</span>
      <select ${attrs}>${options}</select>
    </label>
  `;
}

function renderTextField(field, value, attrs) {
  const safeValue = value === null || value === undefined ? "" : escapeHtml(value);
  const step = field.step ? `step="${field.step}"` : "";
  return `
    <label class="control">
      <span class="control-label">${escapeHtml(field.label)}</span>
      <input type="${field.type}" value="${safeValue}" ${step} ${attrs} />
    </label>
  `;
}

function renderSliderField(field, value, attrs) {
  const numericValue = Number(value ?? field.min ?? 0);
  return `
    <label class="slider-control">
      <div class="slider-head">
        <span class="control-label">${escapeHtml(field.label)}</span>
        <strong data-slider-output>${escapeHtml(formatSliderValue(field, numericValue))}</strong>
      </div>
      <input
        type="range"
        min="${field.min}"
        max="${field.max}"
        step="${field.step}"
        value="${numericValue}"
        ${attrs}
      />
    </label>
  `;
}

function renderField(field, value, attrs) {
  if (field.type === "checkbox") {
    return renderToggleField(field, value, attrs);
  }
  if (field.type === "select") {
    return renderSelectField(field, value, attrs);
  }
  if (field.type === "slider") {
    return renderSliderField(field, value, attrs);
  }
  return renderTextField(field, value, attrs);
}

function renderGlobalSettings() {
  if (!appState.draftSettings) return;
  const globalSettings = appState.draftSettings.global_settings;
  const defaults = globalSettings.global_defaults;
  const advancedOpen = appState.detailSections.has("global-defaults") ? "open" : "";

  globalForm.innerHTML = `
    ${globalFields
      .map((field) =>
        renderField(
          field,
          globalSettings[field.key],
          `data-target="global" data-field="${field.key}"`,
        ),
      )
      .join("")}
    <details class="details-panel full-span" data-details-id="global-defaults" ${advancedOpen}>
      <summary>Default render settings</summary>
      <div class="details-body">
        <p class="details-copy">These defaults seed each service, but you can override every service independently below.</p>
        <div class="advanced-grid">
          ${globalDefaultFields
            .map((field) =>
              renderField(
                field,
                defaults[field.key],
                `data-target="defaults" data-field="${field.key}"`,
              ),
            )
            .join("")}
        </div>
      </div>
    </details>
  `;
}

function nextRefreshText(serviceView) {
  if (!serviceView.automation?.automatic_generation_active) {
    return "Manual only";
  }
  return formatDate(serviceView.state.next_scheduled_at);
}

function liveAssetLinks(serviceView) {
  if (!serviceView.file_exists) {
    return `<span>Live asset not rendered yet</span>`;
  }
  return `
    <a href="${serviceView.urls.hero}" target="_blank" rel="noreferrer">Open live asset</a>
    <a href="${serviceView.urls.hero}" download>Download WebM</a>
  `;
}

function renderLogSection(slug) {
  const isOpen = appState.detailSections.has(`logs:${slug}`) ? "open" : "";
  const logs = appState.logs.get(slug) || [];
  const logMarkup = logs.length
    ? logs
        .map(
          (entry) => `
            <div class="log-line">
              <span>${escapeHtml(new Date(entry.timestamp).toLocaleString())}</span>
              <span>[${escapeHtml(entry.level)}] ${escapeHtml(entry.message)}</span>
            </div>
          `,
        )
        .join("")
    : `<div class="empty-state">Open this section to load recent logs for this service.</div>`;

  return `
    <details class="details-panel" data-details-id="logs:${slug}" ${isOpen}>
      <summary>Recent logs</summary>
      <div class="details-body">
        <div class="log-list">${logMarkup}</div>
      </div>
    </details>
  `;
}

function renderServiceCard(servicePayload) {
  const serviceView = mergedServiceView(servicePayload);
  const stage = previewStage(serviceView);
  const draft = serviceView.draft;
  const progress = serviceView.job?.progress ?? (serviceView.state.status === "succeeded" ? 100 : 0);
  const progressMessage = serviceView.job?.message || serviceView.state.last_error || "Idle";
  const advancedOpen = appState.detailSections.has(`advanced:${serviceView.slug}`) ? "open" : "";
  const previewBusy = appState.previewBusy.has(serviceView.slug);
  const renderBusy = Boolean(serviceView.job);
  const previewStatus = serviceView.state.preview_status === "succeeded" ? "Preview ready" : "Preview not generated";

  return `
    <article class="service-card" data-service-card="${serviceView.slug}">
      <div class="preview-panel">
        <div class="stage-meta">
          <span class="stage-label">${escapeHtml(stage.label)}</span>
          <div class="asset-links">${liveAssetLinks(serviceView)}</div>
        </div>
        <div class="media-shell">${stage.media}</div>
        <p class="stage-copy">${escapeHtml(stage.note)}</p>
        <div class="action-row">
          <button class="button button-ghost" type="button" data-action="preview" data-slug="${serviceView.slug}" ${previewBusy ? "disabled" : ""}>
            ${previewBusy ? "Generating preview..." : "Preview current settings"}
          </button>
          <button class="button button-primary" type="button" data-action="render" data-slug="${serviceView.slug}" ${renderBusy ? "disabled" : ""}>
            ${renderBusy ? "Rendering..." : "Save + render final"}
          </button>
        </div>
      </div>

      <div class="service-main">
        <div class="service-header">
          <div>
            <h3>${escapeHtml(serviceView.name)}</h3>
            <p class="slug">${escapeHtml(`/heroes/${serviceView.slug}.webm`)}</p>
          </div>
          <div class="badge-row">
            ${renderBadge(serviceView)}
            <span class="badge">${escapeHtml(automationLabel(serviceView))}</span>
            <span class="badge">${escapeHtml(previewStatus)}</span>
          </div>
        </div>

        <div class="meta-grid">
          <div class="meta-item">
            <span class="meta-label">Last render</span>
            <strong>${formatDate(serviceView.state.last_generated_at)}</strong>
          </div>
          <div class="meta-item">
            <span class="meta-label">Next refresh</span>
            <strong>${nextRefreshText(serviceView)}</strong>
          </div>
          <div class="meta-item">
            <span class="meta-label">Live file size</span>
            <strong>${formatBytes(serviceView.state.file_size_bytes)}</strong>
          </div>
          <div class="meta-item">
            <span class="meta-label">Preview file size</span>
            <strong>${formatBytes(serviceView.state.preview_file_size_bytes)}</strong>
          </div>
          <div class="meta-item">
            <span class="meta-label">Live duration</span>
            <strong>${serviceView.state.duration_seconds || draft.loop_duration_seconds}s</strong>
          </div>
          <div class="meta-item">
            <span class="meta-label">Preview duration</span>
            <strong>${serviceView.state.preview_duration_seconds || 0}s</strong>
          </div>
        </div>

        <div>
          <div class="status-line">
            <strong>${formatProgress(progress)}</strong>
            <span class="status-note">${escapeHtml(progressMessage)}</span>
          </div>
          <div class="progress-track">
            <div class="progress-bar" style="width: ${progress}%;"></div>
          </div>
        </div>

        <div>
          <p class="section-title">Service toggles</p>
          <div class="control-grid">
            ${serviceToggleFields
              .map((field) =>
                renderField(
                  field,
                  draft[field.key],
                  `data-target="service" data-service="${serviceView.slug}" data-field="${field.key}"`,
                ),
              )
              .join("")}
          </div>
        </div>

        <div>
          <p class="section-title">Source and cadence</p>
          <div class="control-grid">
            ${serviceControlFields
              .map((field) =>
                renderField(
                  field,
                  draft[field.key],
                  `data-target="service" data-service="${serviceView.slug}" data-field="${field.key}"`,
                ),
              )
              .join("")}
          </div>
        </div>

        <div>
          <p class="section-title">Quick look controls</p>
          <div class="slider-grid">
            ${serviceSliderFields
              .map((field) =>
                renderField(
                  field,
                  draft[field.key],
                  `data-target="service" data-service="${serviceView.slug}" data-field="${field.key}"`,
                ),
              )
              .join("")}
          </div>
        </div>

        <details class="details-panel" data-details-id="advanced:${serviceView.slug}" ${advancedOpen}>
          <summary>Advanced settings</summary>
          <div class="details-body">
            <p class="details-copy">Use these when you want to fine-tune transforms, bitrate, sizing, and artwork pool limits.</p>
            <div class="advanced-grid">
              ${serviceAdvancedFields
                .map((field) =>
                  renderField(
                    field,
                    draft[field.key],
                    `data-target="service" data-service="${serviceView.slug}" data-field="${field.key}"`,
                  ),
                )
                .join("")}
            </div>
          </div>
        </details>

        ${renderLogSection(serviceView.slug)}
      </div>
    </article>
  `;
}

function renderServices() {
  servicesGrid.innerHTML = appState.services.map(renderServiceCard).join("");
}

function renderSummary() {
  const schedulerOn = Boolean(appState.draftSettings?.global_settings.scheduler_enabled);
  const ready = appState.services.filter((service) => service.state?.status === "succeeded").length;
  const previews = appState.services.filter((service) => service.state?.preview_status === "succeeded").length;
  const running = appState.jobs.filter((job) => job.status === "queued" || job.status === "running").length;
  const autoServices = appState.services.filter((service) => service.automation?.automatic_generation_active).length;

  statusSummary.innerHTML = `
    <div class="summary-item">
      <span class="meta-label">Scheduler</span>
      <strong>${schedulerOn ? "On" : "Off"}</strong>
      <span class="status-note">${schedulerOn ? `${autoServices} services auto-refreshing` : "Manual-only by default"}</span>
    </div>
    <div class="summary-item">
      <span class="meta-label">Live renders</span>
      <strong>${ready}</strong>
      <span class="status-note">Stable hosted WebM assets ready</span>
    </div>
    <div class="summary-item">
      <span class="meta-label">Draft previews</span>
      <strong>${previews}</strong>
      <span class="status-note">Current preview clips available</span>
    </div>
    <div class="summary-item">
      <span class="meta-label">Active jobs</span>
      <strong>${running}</strong>
      <span class="status-note">Queued or rendering right now</span>
    </div>
  `;
}

function renderFlash(message = "", tone = "info") {
  if (!message) {
    flashMessage.hidden = true;
    flashMessage.textContent = "";
    flashMessage.className = "flash-message";
    return;
  }
  flashMessage.hidden = false;
  flashMessage.textContent = message;
  flashMessage.className = `flash-message ${tone}`;
}

function setFlash(message, tone = "info", timeout = 4200) {
  renderFlash(message, tone);
  if (appState.flashTimeout) {
    window.clearTimeout(appState.flashTimeout);
  }
  appState.flashTimeout = window.setTimeout(() => {
    renderFlash();
    appState.flashTimeout = null;
  }, timeout);
}

function updateSaveButton() {
  saveButton.textContent = appState.dirty ? "Save changes" : "Save settings";
}

function syncDraftSettings(savedSettings, preserveDraft = true) {
  if (!preserveDraft || !appState.draftSettings) {
    appState.draftSettings = deepClone(savedSettings);
    appState.dirty = false;
    return;
  }

  const draftSlugs = new Set(appState.draftSettings.services.map((service) => service.slug));
  for (const service of savedSettings.services) {
    if (!draftSlugs.has(service.slug)) {
      appState.draftSettings.services.push(deepClone(service));
    }
  }
}

function renderAll() {
  renderGlobalSettings();
  renderServices();
  renderSummary();
  updateSaveButton();
}

function parseElementValue(field, element) {
  if (field.type === "checkbox") {
    return element.checked;
  }
  if (field.type === "number" || field.type === "slider" || field.cast === "number") {
    return element.value === "" ? null : Number(element.value);
  }
  return element.value;
}

function updateSliderDisplay(element, field) {
  const output = element.closest(".slider-control")?.querySelector("[data-slider-output]");
  if (!output) return;
  output.textContent = formatSliderValue(field, Number(element.value));
}

function updateDraftFromElement(element) {
  const target = element.dataset.target;
  const fieldKey = element.dataset.field;
  if (!target || !fieldKey || !appState.draftSettings) {
    return;
  }

  let field = null;
  if (target === "global") {
    field = fieldByKey(globalFields, fieldKey);
    appState.draftSettings.global_settings[fieldKey] = parseElementValue(field, element);
  } else if (target === "defaults") {
    field = fieldByKey(globalDefaultFields, fieldKey);
    appState.draftSettings.global_settings.global_defaults[fieldKey] = parseElementValue(field, element);
  } else if (target === "service") {
    const service = getDraftService(element.dataset.service);
    if (!service) return;
    field =
      fieldByKey(serviceToggleFields, fieldKey) ||
      fieldByKey(serviceControlFields, fieldKey) ||
      fieldByKey(serviceSliderFields, fieldKey) ||
      fieldByKey(serviceAdvancedFields, fieldKey);
    service[fieldKey] = parseElementValue(field, element);
  }

  if (field?.type === "slider") {
    updateSliderDisplay(element, field);
  }

  appState.dirty = true;
  updateSaveButton();
}

async function api(url, options = {}) {
  const response = await fetch(url, {
    headers: { "Content-Type": "application/json" },
    ...options,
  });
  if (!response.ok) {
    const text = await response.text();
    throw new Error(text || `Request failed: ${response.status}`);
  }
  return response.json();
}

async function refreshData({ preserveDraft = true } = {}) {
  const [settingsResult, servicesResult, jobsResult] = await Promise.all([
    api("/api/settings"),
    api("/api/services"),
    api("/api/jobs"),
  ]);

  appState.settings = settingsResult.settings;
  syncDraftSettings(settingsResult.settings, preserveDraft);
  appState.services = servicesResult.services;
  appState.jobs = jobsResult.jobs;
  renderAll();
}

async function saveSettings(quiet = false) {
  if (!appState.draftSettings) return;
  saveButton.disabled = true;
  try {
    const response = await api("/api/settings", {
      method: "PUT",
      body: JSON.stringify(appState.draftSettings),
    });
    appState.settings = response.settings;
    appState.draftSettings = deepClone(response.settings);
    appState.dirty = false;
    await refreshData({ preserveDraft: false });
    if (!quiet) {
      setFlash("Settings saved.", "success");
    }
  } finally {
    saveButton.disabled = false;
    updateSaveButton();
  }
}

async function previewService(slug) {
  const service = getDraftService(slug);
  if (!service || !appState.draftSettings) return;

  appState.previewBusy.add(slug);
  renderServices();
  try {
    const response = await api(`/api/services/${slug}/preview`, {
      method: "POST",
      body: JSON.stringify({
        global_settings: appState.draftSettings.global_settings,
        service,
      }),
    });

    const servicePayload = appState.services.find((entry) => entry.slug === slug);
    if (servicePayload) {
      servicePayload.preview_exists = true;
      servicePayload.preview_thumbnail_exists = true;
      servicePayload.urls.preview_video = response.urls.preview_video;
      servicePayload.urls.preview_image = response.urls.preview_image;
      servicePayload.state = {
        ...(servicePayload.state || {}),
        preview_status: response.preview.status,
        preview_generated_at: response.preview.generated_at,
        preview_last_error: response.preview.last_error,
        preview_seed_used: response.preview.seed_used,
        preview_file_size_bytes: response.preview.file_size_bytes,
        preview_duration_seconds: response.preview.duration_seconds,
        preview_title_count: response.preview.title_count,
        preview_image_count: response.preview.image_count,
      };
    }
    renderServices();
    setFlash(`Preview ready for ${service.name}.`, "success");
  } finally {
    appState.previewBusy.delete(slug);
    renderServices();
  }
}

async function renderService(slug) {
  await saveSettings(true);
  const button = servicesGrid.querySelector(`[data-action="render"][data-slug="${slug}"]`);
  if (button) {
    button.disabled = true;
  }
  try {
    await api(`/api/services/${slug}/regenerate`, { method: "POST" });
    await refreshData({ preserveDraft: false });
    setFlash("Final render queued.", "success");
  } finally {
    if (button) {
      button.disabled = false;
    }
  }
}

async function regenerateAll() {
  regenerateAllButton.disabled = true;
  try {
    await saveSettings(true);
    await api("/api/regenerate-all", { method: "POST" });
    await refreshData({ preserveDraft: false });
    setFlash("Final renders queued for enabled services.", "success");
  } finally {
    regenerateAllButton.disabled = false;
  }
}

async function loadLogs(slug) {
  const response = await api(`/api/logs?slug=${encodeURIComponent(slug)}&limit=12`);
  appState.logs.set(slug, response.logs);
  renderServices();
}

function isUserEditing() {
  const active = document.activeElement;
  if (!(active instanceof HTMLElement)) return false;
  return active.matches("input, select, textarea");
}

document.addEventListener("input", (event) => {
  const target = event.target;
  if (!(target instanceof HTMLInputElement || target instanceof HTMLSelectElement)) return;
  if (!target.dataset.target) return;
  updateDraftFromElement(target);
});

document.addEventListener("change", (event) => {
  const target = event.target;
  if (!(target instanceof HTMLInputElement || target instanceof HTMLSelectElement)) return;
  if (!target.dataset.target) return;
  updateDraftFromElement(target);
});

servicesGrid.addEventListener("click", async (event) => {
  const target = event.target;
  if (!(target instanceof HTMLElement)) return;
  const action = target.dataset.action;
  const slug = target.dataset.slug;
  if (!action || !slug) return;

  try {
    if (action === "preview") {
      await previewService(slug);
    } else if (action === "render") {
      await renderService(slug);
    }
  } catch (error) {
    setFlash(error.message || "Something went wrong.", "error", 6000);
  }
});

document.addEventListener("toggle", async (event) => {
  const target = event.target;
  if (!(target instanceof HTMLDetailsElement)) return;
  const detailId = target.dataset.detailsId;
  if (!detailId) return;

  if (target.open) {
    appState.detailSections.add(detailId);
    if (detailId.startsWith("logs:")) {
      const slug = detailId.split(":")[1];
      if (!appState.logs.has(slug)) {
        try {
          await loadLogs(slug);
        } catch (error) {
          setFlash(error.message || "Unable to load logs.", "error", 6000);
        }
      }
    }
  } else {
    appState.detailSections.delete(detailId);
  }
});

saveButton.addEventListener("click", async () => {
  try {
    await saveSettings(false);
  } catch (error) {
    setFlash(error.message || "Unable to save settings.", "error", 6000);
  }
});

refreshButton.addEventListener("click", async () => {
  try {
    await refreshData({ preserveDraft: true });
    setFlash("Dashboard refreshed.", "info");
  } catch (error) {
    setFlash(error.message || "Unable to refresh dashboard.", "error", 6000);
  }
});

regenerateAllButton.addEventListener("click", async () => {
  try {
    await regenerateAll();
  } catch (error) {
    setFlash(error.message || "Unable to queue renders.", "error", 6000);
  }
});

async function init() {
  await refreshData({ preserveDraft: false });
  window.setInterval(() => {
    if (isUserEditing()) {
      return;
    }
    refreshData({ preserveDraft: true }).catch((error) => {
      console.error(error);
    });
  }, 10000);
}

init().catch((error) => {
  console.error(error);
  setFlash(error.message || "Unable to load the dashboard.", "error", 6000);
});
