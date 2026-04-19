const initialState = window.CSVAGENT_INITIAL_STATE || {};

const state = {
  folder: initialState.selected_folder || "",
  availableFiles: Array.isArray(initialState.files) ? initialState.files : [],
  openFiles: Array.isArray(initialState.open_files) ? initialState.open_files : [],
  graphConfigurations: initialState.graph_configurations || {},
  defaultPageSize: initialState.default_page_size || 50,
  loadedTables: new Map(),
};

const elements = {};

document.addEventListener("DOMContentLoaded", () => {
  cacheElements();
  bindEvents();
  elements.folderPath.value = state.folder;
  renderFileList();
  updateEmptyState();
  restoreOpenTables();
});

function cacheElements() {
  elements.folderPath = document.getElementById("folder-path");
  elements.loadFolder = document.getElementById("load-folder");
  elements.browseFolder = document.getElementById("browse-folder");
  elements.fileList = document.getElementById("file-list");
  elements.fileCount = document.getElementById("file-count");
  elements.statusMessage = document.getElementById("status-message");
  elements.tablesContainer = document.getElementById("tables-container");
  elements.emptyState = document.getElementById("empty-state");
}

function bindEvents() {
  elements.loadFolder.addEventListener("click", () => {
    handleFolderLoad();
  });

  elements.browseFolder.addEventListener("click", () => {
    handleFolderBrowse();
  });

  elements.folderPath.addEventListener("keydown", (event) => {
    if (event.key === "Enter") {
      handleFolderLoad();
    }
  });

  elements.folderPath.addEventListener("change", () => {
    handleFolderLoad();
  });

  elements.fileList.addEventListener("click", (event) => {
    const trigger = event.target.closest("[data-file-path]");
    if (!trigger) {
      return;
    }

    loadFile(trigger.dataset.filePath);
  });

  elements.tablesContainer.addEventListener("click", (event) => {
    const button = event.target.closest("[data-action]");
    if (!button) {
      return;
    }

    const card = button.closest("[data-file-path]");
    if (!card) {
      return;
    }

    const filePath = card.dataset.filePath;
    const action = button.dataset.action;

    if (action === "close-table") {
      closeTable(filePath);
      return;
    }

    if (action === "previous-page") {
      const table = state.loadedTables.get(filePath);
      if (table) {
        changePage(filePath, table.table.page - 1);
      }
      return;
    }

    if (action === "next-page") {
      const table = state.loadedTables.get(filePath);
      if (table) {
        changePage(filePath, table.table.page + 1);
      }
      return;
    }

    if (action === "generate-graph") {
      generateGraph(filePath);
      return;
    }

    if (action === "save-image") {
      saveGraphImage(filePath);
      return;
    }

    if (action === "save-html") {
      saveGraphHtml(filePath);
    }
  });

  elements.tablesContainer.addEventListener("change", (event) => {
    const select = event.target.closest("[data-field]");
    if (!select) {
      return;
    }

    const card = select.closest("[data-file-path]");
    if (!card) {
      return;
    }

    if (select.dataset.field === "chart-type") {
      updateChartFieldState(card);
    }
  });
}

async function restoreOpenTables() {
  if (!state.openFiles.length) {
    return;
  }

  setStatus("Restoring previously open tables...");

  for (const filePath of state.openFiles) {
    try {
      await loadFile(filePath, { restore: true, quiet: true });
    } catch (error) {
      setStatus(error.message, "error");
    }
  }

  if (state.loadedTables.size > 0) {
    setStatus(`Restored ${state.loadedTables.size} table${state.loadedTables.size === 1 ? "" : "s"}.`, "success");
  }
}

async function handleFolderLoad() {
  const folderPath = elements.folderPath.value.trim();
  if (!folderPath) {
    setStatus("Enter a folder path first.", "error");
    return;
  }

  try {
    const payload = await fetchJson("/api/folder/select", {
      method: "POST",
      body: JSON.stringify({ folder_path: folderPath }),
    });
    updateFolderState(payload);
    setStatus(`Loaded ${payload.files.length} CSV file${payload.files.length === 1 ? "" : "s"}.`, "success");
  } catch (error) {
    setStatus(error.message, "error");
  }
}

async function handleFolderBrowse() {
  try {
    const payload = await fetchJson("/api/folder/browse", {
      method: "POST",
      body: JSON.stringify({}),
    });

    if (payload.folder_path) {
      updateFolderState(payload);
      setStatus(`Loaded ${payload.files.length} CSV file${payload.files.length === 1 ? "" : "s"}.`, "success");
      return;
    }
  } catch (error) {
    setStatus(`${error.message} \n폴더 경로를 직접 입력한 뒤 Load Folder 버튼을 눌러주세요.`, "error");
  }
}

function updateFolderState(payload) {
  state.folder = payload.folder_path || "";
  state.availableFiles = Array.isArray(payload.files) ? payload.files : [];
  elements.folderPath.value = state.folder;
  renderFileList();
}

async function loadFile(filePath, options = {}) {
  const { restore = false, quiet = false } = options;

  if (state.loadedTables.has(filePath)) {
    scrollCardIntoView(filePath);
    if (!quiet) {
      setStatus(`${lookupFileName(filePath)} is already open.`);
    }
    return;
  }

  const payload = await fetchJson("/api/files/load", {
    method: "POST",
    body: JSON.stringify({
      file_path: filePath,
      page_size: state.defaultPageSize,
    }),
  });

  const file = payload.file;
  state.loadedTables.set(file.path, file);
  state.openFiles = uniqueValues(
    state.openFiles
      .filter((path) => path !== filePath)
      .concat(file.path)
  );

  renderTableCard(file, payload.graph_configuration);
  renderFileList();
  updateEmptyState();
  scrollCardIntoView(file.path);

  if (payload.graph_configuration) {
    state.graphConfigurations[file.path] = payload.graph_configuration;
    await generateGraph(file.path, { restore: true, quiet: true });
  } else {
    const defaultGraph = getDefaultGraphConfiguration(file, null);
    state.graphConfigurations[file.path] = defaultGraph;
  }

  if (!quiet) {
    setStatus(`${file.name} loaded.`, "success");
  }

  if (restore) {
    return;
  }
}

function renderFileList() {
  elements.fileCount.textContent = String(state.availableFiles.length);

  if (!state.availableFiles.length) {
    elements.fileList.innerHTML = '<div class="empty-files">No CSV files found in the selected folder.</div>';
    return;
  }

  elements.fileList.innerHTML = state.availableFiles
    .map((file) => {
      const loadedClass = state.loadedTables.has(file.path) ? "is-loaded" : "";
      return `
        <button class="file-item ${loadedClass}" type="button" data-file-path="${escapeHtml(file.path)}">
          <span class="file-name">${escapeHtml(file.name)}</span>
          <span class="file-meta">${file.row_count} rows · ${file.column_count} columns · ${escapeHtml(file.file_size_human)}</span>
          <span class="file-path">${escapeHtml(file.path)}</span>
        </button>
      `;
    })
    .join("");
}

function renderTableCard(file, storedGraphConfiguration) {
  const card = document.createElement("section");
  card.className = "table-card";
  card.dataset.filePath = file.path;

  const metadata = file.metadata;
  card.innerHTML = `
    <div class="card-header">
      <div>
        <h3>${escapeHtml(file.name)}</h3>
        <p class="card-path">${escapeHtml(file.path)}</p>
      </div>
      <div class="card-header-actions">
        <button class="button ghost danger" type="button" data-action="close-table">Close</button>
      </div>
    </div>

    <div class="meta-row">
      <span class="meta-pill">${metadata.row_count} rows</span>
      <span class="meta-pill">${metadata.column_count} columns</span>
      <span class="meta-pill">${escapeHtml(metadata.file_size_human)}</span>
    </div>

    <div class="table-toolbar">
      <h3>Table Preview</h3>
      <div class="pagination">
        <button class="button secondary" type="button" data-action="previous-page">Previous</button>
        <span class="pagination-label" data-role="page-label"></span>
        <button class="button secondary" type="button" data-action="next-page">Next</button>
      </div>
    </div>

    <div class="table-scroll" data-role="table-wrapper"></div>

    <div class="graph-panel">
      <div class="graph-controls">
        <div class="field-group">
          <label for="chart-type-${cssSafeId(file.path)}">Chart Type</label>
          <select id="chart-type-${cssSafeId(file.path)}" data-field="chart-type">
            <option value="line">Line</option>
            <option value="bar">Bar</option>
            <option value="scatter">Scatter</option>
            <option value="histogram">Histogram</option>
          </select>
        </div>

        <div class="field-group">
          <label for="x-column-${cssSafeId(file.path)}">X-axis</label>
          <select id="x-column-${cssSafeId(file.path)}" data-field="x-column"></select>
        </div>

        <div class="field-group">
          <label for="y-column-${cssSafeId(file.path)}">Y-axis</label>
          <select id="y-column-${cssSafeId(file.path)}" data-field="y-column"></select>
        </div>

        <div class="graph-actions">
          <button class="button primary" type="button" data-action="generate-graph">Generate Graph</button>
          <button class="button secondary" type="button" data-action="save-image" disabled>Save Image</button>
          <button class="button secondary" type="button" data-action="save-html">Save HTML</button>
        </div>
      </div>

      <p class="graph-hint" data-role="graph-hint">Line, bar, and scatter charts use both selectors. Histogram uses only the X-axis selector.</p>
      <div class="graph-surface is-empty" data-role="graph">Generate a chart to preview it here.</div>
    </div>
  `;

  elements.tablesContainer.appendChild(card);

  renderTablePage(file.path, file.table);

  const graphConfiguration = getDefaultGraphConfiguration(file, storedGraphConfiguration);
  populateColumnSelect(card.querySelector('[data-field="x-column"]'), file.table.columns, {
    allowBlank: false,
    selectedValue: graphConfiguration.x_column,
  });
  populateColumnSelect(card.querySelector('[data-field="y-column"]'), file.table.columns, {
    allowBlank: true,
    blankLabel: "Optional",
    selectedValue: graphConfiguration.y_column,
  });
  card.querySelector('[data-field="chart-type"]').value = graphConfiguration.chart_type;
  updateChartFieldState(card);
}

function renderTablePage(filePath, tableState) {
  const file = state.loadedTables.get(filePath);
  if (!file) {
    return;
  }

  file.table = tableState;

  const card = getCard(filePath);
  if (!card) {
    return;
  }

  card.querySelector('[data-role="table-wrapper"]').innerHTML = renderTableMarkup(tableState);
  card.querySelector('[data-role="page-label"]').textContent =
    `Page ${tableState.page} of ${tableState.total_pages} · ${tableState.total_rows} rows`;

  card.querySelector('[data-action="previous-page"]').disabled = tableState.page <= 1;
  card.querySelector('[data-action="next-page"]').disabled = tableState.page >= tableState.total_pages;
}

function renderTableMarkup(tableState) {
  const columns = tableState.columns.length ? tableState.columns : ["No columns"];
  const header = columns
    .map((column) => `<th>${escapeHtml(column)}</th>`)
    .join("");

  const body = tableState.rows.length
    ? tableState.rows
        .map((row) => {
          const cells = columns
            .map((column) => `<td>${escapeHtml(formatCell(row[column]))}</td>`)
            .join("");
          return `<tr>${cells}</tr>`;
        })
        .join("")
    : `<tr><td class="empty-row" colspan="${Math.max(1, columns.length)}">No rows available on this page.</td></tr>`;

  return `
    <table class="data-table">
      <thead>
        <tr>${header}</tr>
      </thead>
      <tbody>
        ${body}
      </tbody>
    </table>
  `;
}

async function changePage(filePath, page) {
  const table = state.loadedTables.get(filePath);
  if (!table) {
    return;
  }

  if (page < 1 || page > table.table.total_pages) {
    return;
  }

  try {
    const query = new URLSearchParams({
      file_path: filePath,
      page: String(page),
      page_size: String(table.table.page_size),
    });
    const payload = await fetchJson(`/api/files/table?${query.toString()}`);
    renderTablePage(filePath, payload);
  } catch (error) {
    setStatus(error.message, "error");
  }
}

async function closeTable(filePath) {
  const fileName = lookupFileName(filePath);

  try {
    await fetchJson("/api/files/close", {
      method: "POST",
      body: JSON.stringify({ file_path: filePath }),
    });
  } catch (error) {
    setStatus(error.message, "error");
    return;
  }

  const card = getCard(filePath);
  if (card) {
    card.remove();
  }

  state.loadedTables.delete(filePath);
  state.openFiles = state.openFiles.filter((path) => path !== filePath);
  renderFileList();
  updateEmptyState();
  setStatus(`${fileName} closed.`);
}

async function generateGraph(filePath, options = {}) {
  const { quiet = false } = options;
  const card = getCard(filePath);
  if (!card) {
    return;
  }

  try {
    const payload = collectGraphPayload(filePath, card);
    const response = await fetchJson("/api/graphs/generate", {
      method: "POST",
      body: JSON.stringify(payload),
    });

    state.graphConfigurations[filePath] = response.graph_configuration;
    const graphSurface = card.querySelector('[data-role="graph"]');
    graphSurface.classList.remove("is-empty");

    await Plotly.react(graphSurface, response.figure.data, response.figure.layout, {
      responsive: true,
      displaylogo: false,
    });

    card.querySelector('[data-action="save-image"]').disabled = false;
    card.querySelector('[data-action="save-html"]').disabled = false;

    if (!quiet) {
      setStatus(`${lookupFileName(filePath)} chart generated.`, "success");
    }
  } catch (error) {
    setStatus(error.message, "error");
  }
}

async function saveGraphHtml(filePath) {
  const card = getCard(filePath);
  if (!card) {
    return;
  }

  try {
    const payload = collectGraphPayload(filePath, card);
    const response = await fetch("/api/graphs/export-html", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    if (!response.ok) {
      const data = await response.json();
      throw new Error(data.error || "Unable to export graph HTML.");
    }

    const blob = await response.blob();
    const filename = parseDownloadFilename(response.headers.get("Content-Disposition"))
      || `${slugify(lookupFileName(filePath)) || "chart"}.html`;
    downloadBlob(blob, filename);
    setStatus(`${lookupFileName(filePath)} HTML export saved.`, "success");
  } catch (error) {
    setStatus(error.message, "error");
  }
}

function saveGraphImage(filePath) {
  const card = getCard(filePath);
  if (!card) {
    return;
  }

  const graphSurface = card.querySelector('[data-role="graph"]');
  if (!graphSurface || graphSurface.classList.contains("is-empty")) {
    setStatus("Generate a graph before saving an image.", "error");
    return;
  }

  Plotly.downloadImage(graphSurface, {
    format: "png",
    filename: slugify(lookupFileName(filePath)) || "csvagent-chart",
    height: 700,
    width: 1200,
  });

  setStatus(`${lookupFileName(filePath)} image export started.`, "success");
}

function collectGraphPayload(filePath, card) {
  const chartType = card.querySelector('[data-field="chart-type"]').value;
  const xColumn = emptyToNull(card.querySelector('[data-field="x-column"]').value);
  const yColumn = emptyToNull(card.querySelector('[data-field="y-column"]').value);

  return {
    file_path: filePath,
    chart_type: chartType,
    x_column: xColumn,
    y_column: chartType === "histogram" ? null : yColumn,
  };
}

function updateChartFieldState(card) {
  const chartType = card.querySelector('[data-field="chart-type"]').value;
  const yColumn = card.querySelector('[data-field="y-column"]');
  const hint = card.querySelector('[data-role="graph-hint"]');

  if (chartType === "histogram") {
    yColumn.disabled = true;
    hint.textContent = "Histogram uses only the X-axis selector.";
    return;
  }

  yColumn.disabled = false;
  hint.textContent = "Line, bar, and scatter charts use both selectors.";
}

function populateColumnSelect(select, columns, options = {}) {
  const {
    allowBlank = false,
    blankLabel = "Select",
    selectedValue = "",
  } = options;

  const optionMarkup = [];
  if (allowBlank) {
    optionMarkup.push(`<option value="">${escapeHtml(blankLabel)}</option>`);
  }

  for (const column of columns) {
    optionMarkup.push(
      `<option value="${escapeHtml(column)}">${escapeHtml(column)}</option>`
    );
  }

  select.innerHTML = optionMarkup.join("");

  if (selectedValue && columns.includes(selectedValue)) {
    select.value = selectedValue;
    return;
  }

  if (allowBlank) {
    select.value = "";
    return;
  }

  if (columns.length) {
    select.value = columns[0];
  }
}

function getDefaultGraphConfiguration(file, storedConfiguration) {
  const columns = file.table.columns || [];
  const fallback = {
    chart_type: "line",
    x_column: columns[0] || "",
    y_column: columns[1] || columns[0] || "",
  };

  if (!storedConfiguration) {
    return fallback;
  }

  const chartType = ["line", "bar", "scatter", "histogram"].includes(storedConfiguration.chart_type)
    ? storedConfiguration.chart_type
    : fallback.chart_type;

  const configuration = {
    chart_type: chartType,
    x_column: columns.includes(storedConfiguration.x_column) ? storedConfiguration.x_column : fallback.x_column,
    y_column: columns.includes(storedConfiguration.y_column) ? storedConfiguration.y_column : fallback.y_column,
  };

  if (configuration.chart_type === "histogram") {
    if (!configuration.x_column && configuration.y_column) {
      configuration.x_column = configuration.y_column;
    }
    configuration.y_column = "";
  }

  return configuration;
}

function updateEmptyState() {
  elements.emptyState.classList.toggle("is-hidden", state.loadedTables.size > 0);
}

function getCard(filePath) {
  return elements.tablesContainer.querySelector(`[data-file-path="${cssEscape(filePath)}"]`);
}

function lookupFileName(filePath) {
  const loaded = state.loadedTables.get(filePath);
  if (loaded) {
    return loaded.name;
  }

  const available = state.availableFiles.find((file) => file.path === filePath);
  return available ? available.name : filePath.split("/").pop() || filePath;
}

function setStatus(message, type = "info") {
  elements.statusMessage.textContent = message || "";
  elements.statusMessage.className = "status-message";

  if (type === "error") {
    elements.statusMessage.classList.add("is-error");
  }

  if (type === "success") {
    elements.statusMessage.classList.add("is-success");
  }
}

async function fetchJson(url, options = {}) {
  const response = await fetch(url, {
    headers: {
      "Content-Type": "application/json",
      ...(options.headers || {}),
    },
    ...options,
  });

  let data = {};
  const contentType = response.headers.get("Content-Type") || "";

  if (contentType.includes("application/json")) {
    data = await response.json();
  } else {
    const text = await response.text();
    data = { error: text || "Request failed." };
  }

  if (!response.ok) {
    throw new Error(data.error || "Request failed.");
  }

  return data;
}

function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function parseDownloadFilename(contentDisposition) {
  if (!contentDisposition) {
    return "";
  }

  const match = contentDisposition.match(/filename="?([^"]+)"?/i);
  return match ? match[1] : "";
}

function scrollCardIntoView(filePath) {
  const card = getCard(filePath);
  if (card) {
    card.scrollIntoView({ behavior: "smooth", block: "start" });
  }
}

function uniqueValues(values) {
  return Array.from(new Set(values));
}

function formatCell(value) {
  if (value === null || value === undefined) {
    return "";
  }
  return String(value);
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#39;");
}

function slugify(value) {
  return String(value)
    .toLowerCase()
    .replace(/[^a-z0-9._-]+/g, "-")
    .replace(/^-+|-+$/g, "");
}

function emptyToNull(value) {
  return value ? value : null;
}

function cssSafeId(value) {
  return slugify(value) || "csvagent";
}

function cssEscape(value) {
  if (window.CSS && typeof window.CSS.escape === "function") {
    return window.CSS.escape(value);
  }

  return String(value).replace(/["\\]/g, "\\$&");
}
