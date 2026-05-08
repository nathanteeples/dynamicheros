const appState = {
  settings: null,
  services: [],
  jobs: [],
  logs: new Map(),
};

const globalForm = document.getElementById("global-settings-form");
const servicesGrid = document.getElementById("services-grid");
const statusSummary = document.getElementById("status-summary");
const saveButton = document.getElementById("save-button");
const refreshButton = document.getElementById("refresh-button");
const regenerateAllButton = document.getElementById("regenerate-all-button");
const logLineTemplate = document.getElementById("log-line-template");

const globalFields = [
  { key: "tmdb_bearer_token", label: "TMDB bearer token", type: "password" },
  { key: "tmdb_api_key", label: "TMDB v3 API key", type: "password" },
  { key: "default_region", label: "Default region", type: "text" },
  { key: "tmdb_language", label: "TMDB language", type: "text" },
  { key: "pages_per_media_type", label: "Pages per media type", type: "number" },
  { key: "api_cache_ttl_minutes", label: "API cache TTL (minutes)", type: "number" },
  { key: "image_size", label: "TMDB image size", type: "text" },
  { key: "scheduler_poll_seconds", label: "Scheduler poll seconds", type: "number" },
  { key: "max_concurrent_jobs", label: "Max concurrent jobs", type: "number" },
  { key: "failure_retry_minutes", label: "Failure retry minutes", type: "number" },
];

const defaultRenderFields = [
  { key: "output_width", label: "Default output width", type: "number" },
  { key: "output_height", label: "Default output height", type: "number" },
  { key: "loop_duration_seconds", label: "Default loop seconds", type: "number" },
  { key: "fps", label: "Default FPS", type: "number" },
  { key: "card_width", label: "Default card width", type: "number" },
  { key: "gap", label: "Default gap", type: "number" },
  { key: "row_count", label: "Default row count", type: "number" },
  { key: "corner_radius", label: "Default corner radius", type: "number" },
  { key: "rotate_x", label: "Default rotate X", type: "number", step: "0.1" },
  { key: "rotate_y", label: "Default rotate Y", type: "number", step: "0.1" },
  { key: "rotate_z", label: "Default rotate Z", type: "number", step: "0.1" },
  { key: "zoom", label: "Default zoom", type: "number", step: "0.01" },
  { key: "codec", label: "Default codec", type: "select", options: [["vp9", "VP9"], ["vp8", "VP8"]] },
  { key: "quality_preset", label: "Default quality preset", type: "select", options: [["high", "High"], ["balanced", "Balanced"], ["small", "Small"], ["tiny", "Tiny"]] },
  { key: "crf", label: "Default CRF", type: "number" },
  { key: "cpu_used", label: "Default CPU used", type: "number" },
  { key: "max_titles", label: "Default max titles", type: "number" },
  { key: "max_artwork_images", label: "Default max artwork images", type: "number" },
  { key: "minimum_usable_images", label: "Default min usable images", type: "number" },
];

const serviceFields = [
  { key: "enabled", label: "Enabled", type: "checkbox" },
  { key: "provider_id", label: "Provider ID", type: "number" },
  { key: "region", label: "Region", type: "text" },
  {
    key: "content_mode",
    label: "Content mode",
    type: "select",
    options: [["mixed", "Movies + TV"], ["movie", "Movies"], ["tv", "TV"]],
  },
  {
    key: "artwork_mode",
    label: "Artwork mode",
    type: "select",
    options: [["title_cards", "Title cards preferred"], ["clean_backdrops", "Clean backdrops preferred"]],
  },
  { key: "refresh_interval_minutes", label: "Refresh interval (minutes)", type: "number" },
  { key: "output_width", label: "Output width", type: "number" },
  { key: "output_height", label: "Output height", type: "number" },
  { key: "loop_duration_seconds", label: "Loop seconds", type: "number" },
  { key: "fps", label: "FPS", type: "number" },
  { key: "card_width", label: "Card width", type: "number" },
  { key: "gap", label: "Gap", type: "number" },
  { key: "row_count", label: "Rows", type: "number" },
  { key: "corner_radius", label: "Corner radius", type: "number" },
  { key: "rotate_x", label: "Rotate X", type: "number", step: "0.1" },
  { key: "rotate_y", label: "Rotate Y", type: "number", step: "0.1" },
  { key: "rotate_z", label: "Rotate Z", type: "number", step: "0.1" },
  { key: "zoom", label: "Zoom", type: "number", step: "0.01" },
  { key: "skew_x", label: "Skew X", type: "number", step: "0.01" },
  { key: "skew_y", label: "Skew Y", type: "number", step: "0.01" },
  { key: "codec", label: "Codec", type: "select", options: [["vp9", "VP9"], ["vp8", "VP8"]] },
  {
    key: "quality_preset",
    label: "Quality preset",
    type: "select",
    options: [["high", "High"], ["balanced", "Balanced"], ["small", "Small"], ["tiny", "Tiny"]],
  },
  { key: "crf", label: "CRF", type: "number" },
  { key: "cpu_used", label: "CPU used", type: "number" },
  { key: "target_bitrate_kbps", label: "Target bitrate kbps", type: "number" },
  { key: "max_titles", label: "Max titles", type: "number" },
  { key: "max_artwork_images", label: "Max artwork images", type: "number" },
  { key: "minimum_usable_images", label: "Min usable images", type: "number" },
  { key: "seed", label: "Seed", type: "number" },
];

function formatDate(value) {
  if (!value) return "Not yet";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "Not yet";
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

function createField(namePrefix, field, value) {
  const wrapper = document.createElement("label");
  wrapper.className = "form-field";

  const text = document.createElement("span");
  text.textContent = field.label;
  wrapper.appendChild(text);

  let input;
  if (field.type === "select") {
    input = document.createElement("select");
    for (const [optionValue, optionLabel] of field.options) {
      const option = document.createElement("option");
      option.value = optionValue;
      option.textContent = optionLabel;
      if (String(value) === optionValue) {
        option.selected = true;
      }
      input.appendChild(option);
    }
  } else {
    input = document.createElement("input");
    input.type = field.type === "checkbox" ? "checkbox" : field.type;
    if (field.step) {
      input.step = field.step;
    }
    if (field.type === "checkbox") {
      input.checked = Boolean(value);
    } else if (value !== null && value !== undefined) {
      input.value = String(value);
    } else {
      input.value = "";
    }
  }

  input.name = `${namePrefix}.${field.key}`;
  input.dataset.fieldKey = field.key;
  wrapper.appendChild(input);
  return wrapper;
}

function renderGlobalSettings() {
  const settings = appState.settings;
  if (!settings) return;

  globalForm.innerHTML = "";
  const { global_settings: globalSettings } = settings;

  for (const field of globalFields) {
    globalForm.appendChild(createField("global", field, globalSettings[field.key]));
  }

  for (const field of defaultRenderFields) {
    globalForm.appendChild(
      createField("defaults", field, globalSettings.global_defaults[field.key]),
    );
  }
}

function badgeForState(service) {
  const state = service.state;
  if (!state) return `<span class="badge warn">Awaiting first generation</span>`;
  if (state.status === "running") return `<span class="badge warn">Rendering</span>`;
  if (state.status === "queued") return `<span class="badge warn">Queued</span>`;
  if (state.status === "failed") return `<span class="badge error">Failed</span>`;
  if (state.status === "succeeded") return `<span class="badge success">Ready</span>`;
  return `<span class="badge">${state.status}</span>`;
}

function latestJobForSlug(slug) {
  return appState.jobs.find((job) => job.slug === slug) || null;
}

function previewMarkup(service) {
  const heroUrl = service.urls.hero;
  const thumbUrl = service.urls.thumbnail;
  const cacheBust = service.state?.last_generated_at
    ? `?t=${encodeURIComponent(service.state.last_generated_at)}`
    : "";

  if (!service.file_exists) {
    return `<div class="video-placeholder">No WebM generated yet</div>`;
  }

  return `
    <video
      controls
      loop
      muted
      playsinline
      preload="metadata"
      poster="${thumbUrl}${cacheBust}"
      src="${heroUrl}${cacheBust}"
    ></video>
  `;
}

function metaValue(service, key) {
  return service.state?.[key] ?? null;
}

function serviceCard(service) {
  const state = service.state || {};
  const job = latestJobForSlug(service.slug);
  const progress = job?.progress ?? (state.status === "succeeded" ? 100 : 0);
  const progressMessage = job?.message || state.last_error || "Idle";

  return `
    <article class="service-card" data-service-card="${service.slug}">
      <div>
        <div class="video-shell">${previewMarkup(service)}</div>
        <div class="service-actions" style="margin-top: 16px;">
          <button class="service-button" type="button" data-action="regenerate" data-slug="${service.slug}">Regenerate</button>
          <a class="link-button" href="${service.urls.hero}" target="_blank" rel="noreferrer">Open URL</a>
          <a class="link-button" href="${service.urls.hero}" download>Download</a>
          <button class="service-button" type="button" data-action="logs" data-slug="${service.slug}">Show logs</button>
        </div>
        <div class="logs-container" id="logs-${service.slug}" hidden>
          <div class="logs-panel" id="logs-panel-${service.slug}"></div>
        </div>
      </div>

      <div>
        <div class="service-topline">
          <div>
            <h3 class="service-name">${service.name}</h3>
            <p class="slug-text">/heroes/${service.slug}.webm</p>
          </div>
          <div class="service-badges">
            ${badgeForState(service)}
            <span class="badge">${service.settings.provider_id} / ${service.settings.region}</span>
            <span class="badge">${service.settings.codec.toUpperCase()} CRF ${service.settings.crf}</span>
          </div>
        </div>

        <div class="meta-grid" style="margin-top: 18px;">
          <div class="meta-item"><small>Last generated</small><strong>${formatDate(metaValue(service, "last_generated_at"))}</strong></div>
          <div class="meta-item"><small>Next refresh</small><strong>${formatDate(metaValue(service, "next_scheduled_at"))}</strong></div>
          <div class="meta-item"><small>File size</small><strong>${formatBytes(metaValue(service, "file_size_bytes"))}</strong></div>
          <div class="meta-item"><small>Duration</small><strong>${metaValue(service, "duration_seconds") || service.settings.loop_duration_seconds}s</strong></div>
          <div class="meta-item"><small>Titles considered</small><strong>${metaValue(service, "title_count") || 0}</strong></div>
          <div class="meta-item"><small>Images used</small><strong>${metaValue(service, "image_count") || 0}</strong></div>
          <div class="meta-item"><small>Status</small><strong>${state.status || "idle"}</strong></div>
          <div class="meta-item"><small>Seed</small><strong>${metaValue(service, "seed_used") || service.settings.seed || "auto"}</strong></div>
        </div>

        <div style="margin-top: 18px;">
          <div class="service-topline">
            <div>
              <p class="panel-label">Job progress</p>
              <strong>${formatProgress(progress)}</strong>
            </div>
            <div class="panel-note">${progressMessage}</div>
          </div>
          <div class="progress-track">
            <div class="progress-bar" style="width: ${progress}%;"></div>
          </div>
        </div>

        <div class="service-settings" style="margin-top: 20px;">
          ${serviceFields.map((field) => createServiceFieldMarkup(service.slug, field, service.settings[field.key])).join("")}
        </div>
      </div>
    </article>
  `;
}

function createServiceFieldMarkup(slug, field, value) {
  if (field.type === "checkbox") {
    return `
      <label class="form-field">
        <span>${field.label}</span>
        <input type="checkbox" data-service="${slug}" data-field="${field.key}" ${value ? "checked" : ""} />
      </label>
    `;
  }

  if (field.type === "select") {
    const options = field.options
      .map(
        ([optionValue, optionLabel]) =>
          `<option value="${optionValue}" ${String(value) === optionValue ? "selected" : ""}>${optionLabel}</option>`,
      )
      .join("");
    return `
      <label class="form-field">
        <span>${field.label}</span>
        <select data-service="${slug}" data-field="${field.key}">${options}</select>
      </label>
    `;
  }

  const step = field.step ? `step="${field.step}"` : "";
  const safeValue = value === null || value === undefined ? "" : String(value);
  return `
    <label class="form-field">
      <span>${field.label}</span>
      <input type="${field.type}" ${step} value="${safeValue}" data-service="${slug}" data-field="${field.key}" />
    </label>
  `;
}

function renderServices() {
  servicesGrid.innerHTML = appState.services.map(serviceCard).join("");
}

function renderSummary() {
  const ready = appState.services.filter((service) => service.state?.status === "succeeded").length;
  const running = appState.services.filter((service) => service.state?.status === "running").length;
  const failed = appState.services.filter((service) => service.state?.status === "failed").length;
  const enabled = appState.settings?.services.filter((service) => service.enabled).length ?? 0;

  statusSummary.innerHTML = `
    <div class="status-chip">${enabled} enabled services</div>
    <div class="status-chip">${ready} ready loops</div>
    <div class="status-chip">${running} active jobs</div>
    <div class="status-chip">${failed} services with errors</div>
  `;
}

function typedValue(field, input) {
  if (field.type === "checkbox") return input.checked;
  if (field.type === "number") {
    if (input.value === "") return null;
    return Number(input.value);
  }
  return input.value;
}

function collectSettingsPayload() {
  const settings = structuredClone(appState.settings);
  const globalSettings = settings.global_settings;

  for (const field of globalFields) {
    const input = globalForm.querySelector(`[name="global.${field.key}"]`);
    globalSettings[field.key] = typedValue(field, input);
  }

  for (const field of defaultRenderFields) {
    const input = globalForm.querySelector(`[name="defaults.${field.key}"]`);
    globalSettings.global_defaults[field.key] = typedValue(field, input);
  }

  settings.services = settings.services.map((service) => {
    const updated = { ...service };
    for (const field of serviceFields) {
      const input = servicesGrid.querySelector(
        `[data-service="${service.slug}"][data-field="${field.key}"]`,
      );
      updated[field.key] = typedValue(field, input);
    }
    return updated;
  });

  return settings;
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

async function loadLogs(slug) {
  const data = await api(`/api/logs?slug=${encodeURIComponent(slug)}&limit=12`);
  appState.logs.set(slug, data.logs);
  renderLogs(slug);
}

function renderLogs(slug) {
  const container = document.getElementById(`logs-${slug}`);
  const panel = document.getElementById(`logs-panel-${slug}`);
  const logs = appState.logs.get(slug) || [];

  panel.innerHTML = "";
  if (!logs.length) {
    panel.innerHTML = `<div class="log-line"><span class="log-message">No logs recorded yet.</span></div>`;
  } else {
    for (const entry of logs) {
      const fragment = logLineTemplate.content.cloneNode(true);
      fragment.querySelector(".log-time").textContent = new Date(entry.timestamp).toLocaleString();
      fragment.querySelector(".log-message").textContent = `[${entry.level}] ${entry.message}`;
      panel.appendChild(fragment);
    }
  }
  container.hidden = false;
}

async function refreshData() {
  const [settingsResult, servicesResult, jobsResult] = await Promise.all([
    api("/api/settings"),
    api("/api/services"),
    api("/api/jobs"),
  ]);

  appState.settings = settingsResult.settings;
  appState.services = servicesResult.services;
  appState.jobs = jobsResult.jobs;

  renderGlobalSettings();
  renderServices();
  renderSummary();
}

function isUserEditing() {
  const active = document.activeElement;
  if (!(active instanceof HTMLElement)) return false;
  return globalForm.contains(active) || servicesGrid.contains(active);
}

async function saveSettings() {
  saveButton.disabled = true;
  saveButton.textContent = "Saving...";
  try {
    const payload = collectSettingsPayload();
    const response = await api("/api/settings", {
      method: "PUT",
      body: JSON.stringify(payload),
    });
    appState.settings = response.settings;
    await refreshData();
  } finally {
    saveButton.disabled = false;
    saveButton.textContent = "Save settings";
  }
}

async function regenerateService(slug) {
  const button = servicesGrid.querySelector(`[data-action="regenerate"][data-slug="${slug}"]`);
  if (button) {
    button.disabled = true;
    button.textContent = "Queued...";
  }
  try {
    await api(`/api/services/${slug}/regenerate`, { method: "POST" });
    await refreshData();
  } finally {
    if (button) {
      button.disabled = false;
      button.textContent = "Regenerate";
    }
  }
}

async function regenerateAll() {
  regenerateAllButton.disabled = true;
  regenerateAllButton.textContent = "Queueing...";
  try {
    await api("/api/regenerate-all", { method: "POST" });
    await refreshData();
  } finally {
    regenerateAllButton.disabled = false;
    regenerateAllButton.textContent = "Regenerate all";
  }
}

servicesGrid.addEventListener("click", async (event) => {
  const target = event.target;
  if (!(target instanceof HTMLElement)) return;

  if (target.dataset.action === "regenerate" && target.dataset.slug) {
    await regenerateService(target.dataset.slug);
    return;
  }

  if (target.dataset.action === "logs" && target.dataset.slug) {
    await loadLogs(target.dataset.slug);
  }
});

saveButton.addEventListener("click", saveSettings);
refreshButton.addEventListener("click", refreshData);
regenerateAllButton.addEventListener("click", regenerateAll);

async function init() {
  await refreshData();
  window.setInterval(() => {
    if (isUserEditing()) {
      return;
    }
    refreshData().catch((error) => console.error(error));
  }, 10000);
}

init().catch((error) => console.error(error));
