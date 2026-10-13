const DATA_URL = "./data/catalog.json";
const PAGE_SIZE = 24;

const state = {
  catalog: null,
  filtered: [],
  page: 1,
  selectedKey: null,
};

const $ = (selector) => document.querySelector(selector);
const elements = {
  body: $("#catalog-body"),
  empty: $("#empty-state"),
  search: $("#search"),
  source: $("#source-filter"),
  freshness: $("#freshness-filter"),
  sort: $("#sort-select"),
  eligible: $("#eligible-only"),
  resultCount: $("#result-count"),
  pageLabel: $("#page-label"),
  prev: $("#prev-page"),
  next: $("#next-page"),
  detailPlaceholder: $("#detail-placeholder"),
  detailContent: $("#detail-content"),
};

function text(value, fallback = "—") {
  return value === null || value === undefined || value === "" ? fallback : String(value);
}

function number(value, digits = 1) {
  if (value === null || value === undefined || value === "") return "—";
  const parsed = Number(value);
  return Number.isFinite(parsed)
    ? parsed.toLocaleString("zh-CN", { maximumFractionDigits: digits, minimumFractionDigits: 0 })
    : "—";
}

function scientific(value, digits = 8) {
  if (value === null || value === undefined || value === "") return "—";
  const parsed = Number(value);
  return Number.isFinite(parsed) ? parsed.toExponential(digits) : "—";
}

function dateText(value, withTime = false) {
  if (!value) return "—";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return text(value);
  return new Intl.DateTimeFormat("zh-CN", {
    timeZone: "UTC", year: "numeric", month: "2-digit", day: "2-digit",
    ...(withTime ? { hour: "2-digit", minute: "2-digit", hour12: false } : {}),
  }).format(date).replaceAll("/", "-");
}

function latestSource(record) {
  return [...record.sources].sort((a, b) => {
    const ta = new Date(a.orbit?.epoch_utc || 0).getTime();
    const tb = new Date(b.orbit?.epoch_utc || 0).getTime();
    return tb - ta;
  })[0];
}

function freshness(source) {
  const epoch = source?.orbit?.epoch_utc;
  if (!epoch) return { key: "unknown", label: "无历元" };
  const days = (Date.now() - new Date(epoch).getTime()) / 86400000;
  if (days <= 7) return { key: "fresh", label: "7 天内" };
  if (days <= 30) return { key: "aging", label: "8–30 天" };
  return { key: "stale", label: "超过 30 天" };
}

function sourceClass(source) { return source === "spacetrack" ? "st" : "bg"; }
function sourceLabel(source) { return source === "spacetrack" ? "Space-Track" : "Bill Gray"; }

function applyFilters() {
  const query = elements.search.value.trim().toLocaleLowerCase("zh-CN");
  const sourceMode = elements.source.value;
  const freshMode = elements.freshness.value;
  const eligibleOnly = elements.eligible.checked;

  state.filtered = state.catalog.records.filter((record) => {
    if (eligibleOnly && !record.eligible) return false;
    const haystack = [record.name, record.norad_cat_id, record.cospar_id, ...(record.aliases || [])]
      .filter(Boolean).join(" ").toLocaleLowerCase("zh-CN");
    if (query && !haystack.includes(query)) return false;

    const sourceNames = new Set(record.sources.map((item) => item.source));
    if (sourceMode === "matched" && sourceNames.size < 2) return false;
    if (sourceMode === "spacetrack" && !sourceNames.has("spacetrack")) return false;
    if (sourceMode === "bill_gray" && !sourceNames.has("bill_gray")) return false;

    if (freshMode !== "all") {
      const keys = record.sources.map((item) => freshness(item).key);
      if (!keys.includes(freshMode)) return false;
    }
    return true;
  });

  const sortMode = elements.sort.value;
  state.filtered.sort((a, b) => {
    const sa = latestSource(a); const sb = latestSource(b);
    if (sortMode === "sma-desc") return (Number(sb?.orbit?.semi_major_axis_km) || -1) - (Number(sa?.orbit?.semi_major_axis_km) || -1);
    if (sortMode === "sma-asc") return (Number(sa?.orbit?.semi_major_axis_km) || Infinity) - (Number(sb?.orbit?.semi_major_axis_km) || Infinity);
    if (sortMode === "epoch-desc") return new Date(sb?.orbit?.epoch_utc || 0) - new Date(sa?.orbit?.epoch_utc || 0);
    if (sortMode === "norad") return (Number(a.norad_cat_id) || Infinity) - (Number(b.norad_cat_id) || Infinity);
    return a.name.localeCompare(b.name, "zh-CN", { numeric: true });
  });

  state.page = 1;
  renderTable();
}

function renderTable() {
  const totalPages = Math.max(1, Math.ceil(state.filtered.length / PAGE_SIZE));
  state.page = Math.min(state.page, totalPages);
  const start = (state.page - 1) * PAGE_SIZE;
  const rows = state.filtered.slice(start, start + PAGE_SIZE);
  elements.body.replaceChildren(...rows.map(makeRow));
  elements.empty.hidden = rows.length > 0;
  elements.resultCount.textContent = `${state.filtered.length.toLocaleString("zh-CN")} 条`;
  elements.pageLabel.textContent = `第 ${state.page} / ${totalPages} 页`;
  elements.prev.disabled = state.page <= 1;
  elements.next.disabled = state.page >= totalPages;
}

function makeRow(record) {
  const source = latestSource(record);
  const row = document.createElement("tr");
  row.tabIndex = 0;
  row.dataset.key = record.key;
  if (record.key === state.selectedKey) row.classList.add("selected");
  const sourcePills = record.sources.map((item) => `<span class="source-pill ${sourceClass(item.source)}">${sourceLabel(item.source)}</span>`).join("");
  row.innerHTML = `
    <td><span class="target-name">${escapeHtml(record.name)}</span><span class="target-sub">${escapeHtml(record.orbit_regime || "XGEO")} · ${escapeHtml(record.mission_status || "状态未知")}</span></td>
    <td><div class="source-stack">${sourcePills}</div></td>
    <td><span class="numeric">${escapeHtml(text(record.norad_cat_id))}</span><span class="target-sub">${escapeHtml(text(record.cospar_id))}</span></td>
    <td class="numeric">${number(source?.orbit?.semi_major_axis_km, 1)} km</td>
    <td class="numeric">${number(source?.orbit?.period_days, 3)} d</td>
    <td class="epoch-cell">${dateText(source?.orbit?.epoch_utc)}</td>`;
  const activate = () => selectRecord(record.key);
  row.addEventListener("click", activate);
  row.addEventListener("keydown", (event) => { if (event.key === "Enter" || event.key === " ") activate(); });
  return row;
}

function selectRecord(key) {
  state.selectedKey = key;
  const record = state.catalog.records.find((item) => item.key === key);
  if (!record) return;
  document.querySelectorAll("#catalog-body tr").forEach((row) => row.classList.toggle("selected", row.dataset.key === key));
  renderDetail(record);
}

function renderDetail(record) {
  elements.detailPlaceholder.hidden = true;
  elements.detailContent.hidden = false;
  elements.detailContent.replaceChildren();

  const hero = document.createElement("div");
  hero.className = "detail-hero";
  hero.innerHTML = `
    <div class="detail-hero-top"><div><span class="section-kicker">OBJECT RECORD</span><h2>${escapeHtml(record.name)}</h2><p class="detail-id">NORAD ${escapeHtml(text(record.norad_cat_id))} · COSPAR ${escapeHtml(text(record.cospar_id))}</p></div><span class="identity-pill">${escapeHtml(record.identity_status || "unknown")}</span></div>
    <div class="detail-meta"><span class="identity-pill">${escapeHtml(record.orbit_regime || "XGEO")}</span><span class="identity-pill">${escapeHtml(record.object_type || "spacecraft")}</span><span class="identity-pill">${record.eligible ? "符合筛选" : "历史保留"}</span></div>`;

  const body = document.createElement("div");
  body.className = "detail-body";
  if (record.sources.length > 1) body.appendChild(makeComparison(record));
  record.sources
    .slice().sort((a, b) => a.source.localeCompare(b.source))
    .forEach((source) => body.appendChild(makeSourceCard(source)));
  elements.detailContent.append(hero, body);
}

function makeComparison(record) {
  const st = record.sources.find((item) => item.source === "spacetrack");
  const bg = record.sources.find((item) => item.source === "bill_gray");
  const card = document.createElement("section");
  card.className = "comparison-card";
  const sma = delta(st?.orbit?.semi_major_axis_km, bg?.orbit?.semi_major_axis_km);
  const period = delta(st?.orbit?.period_days, bg?.orbit?.period_days, 86400);
  const epochHours = st?.orbit?.epoch_utc && bg?.orbit?.epoch_utc
    ? Math.abs(new Date(st.orbit.epoch_utc) - new Date(bg.orbit.epoch_utc)) / 3600000 : null;
  card.innerHTML = `<h3>源间差异摘要</h3><div class="delta-grid">
    <div><span>|Δ 半长轴|</span><strong>${sma === null ? "—" : `${number(sma, 1)} km`}</strong></div>
    <div><span>|Δ 周期|</span><strong>${period === null ? "—" : `${number(period, 1)} s`}</strong></div>
    <div><span>|Δ 历元|</span><strong>${epochHours === null ? "—" : `${number(epochHours, 1)} h`}</strong></div>
  </div>`;
  return card;
}

function delta(a, b, factor = 1) {
  const x = Number(a); const y = Number(b);
  return Number.isFinite(x) && Number.isFinite(y) ? Math.abs(x - y) * factor : null;
}

function makeSourceCard(source) {
  const template = $("#source-card-template");
  const card = template.content.firstElementChild.cloneNode(true);
  const sourceBadge = card.querySelector(".source-badge");
  sourceBadge.textContent = sourceLabel(source.source);
  sourceBadge.classList.add(sourceClass(source.source));
  const fresh = freshness(source);
  const freshBadge = card.querySelector(".freshness-badge");
  freshBadge.textContent = fresh.label;
  freshBadge.classList.add(fresh.key);

  const orbit = source.orbit || {};
  const fieldGroups = [
    ["平均轨道根数", [
      ["历元 UTC", text(orbit.epoch_utc)],
      ["半长轴 a / km", number(orbit.semi_major_axis_km, 3)],
      ["偏心率 e", number(orbit.eccentricity, 8)],
      ["倾角 i / deg", number(orbit.inclination_deg, 6)],
      ["升交点赤经 Ω / deg", number(orbit.raan_deg, 6)],
      ["近地点幅角 ω / deg", number(orbit.arg_pericenter_deg, 6)],
      ["平近点角 M / deg", number(orbit.mean_anomaly_deg, 6)],
      ["平均运动 n / rev·day⁻¹", number(orbit.mean_motion_rev_day, 10)],
      ["周期 / day", number(orbit.period_days, 8)],
    ]],
    ["传播与目录参数", [
      ["平均运动一阶导数", scientific(orbit.mean_motion_dot)],
      ["平均运动二阶导数", scientific(orbit.mean_motion_ddot)],
      ["BSTAR", scientific(orbit.bstar)],
      ["近地点高度 / km", number(orbit.perigee_altitude_km, 3)],
      ["远地点高度 / km", number(orbit.apogee_altitude_km, 3)],
      ["历元圈次", text(orbit.rev_at_epoch)],
      ["元素集编号", text(orbit.element_set_no)],
      ["历表类型", text(orbit.ephemeris_type)],
      ["GP ID", text(orbit.gp_id)],
    ]],
    ["OMM 坐标与生成信息", [
      ["中心天体", text(orbit.center_name)],
      ["参考系", text(orbit.ref_frame)],
      ["时间系统", text(orbit.time_system)],
      ["平均根数理论", text(orbit.mean_element_theory)],
      ["CCSDS OMM 版本", text(orbit.ccsds_omm_version)],
      ["产品生成时间", text(orbit.creation_date_utc)],
      ["发布机构", text(orbit.originator)],
    ]],
  ];
  const grid = card.querySelector(".orbit-grid");
  fieldGroups.forEach(([title, fields]) => {
    const heading = document.createElement("h3");
    heading.className = "orbit-section-title";
    heading.textContent = title;
    grid.appendChild(heading);
    fields.forEach(([label, value]) => {
      const field = document.createElement("div"); field.className = "orbit-field";
      field.innerHTML = `<span>${escapeHtml(label)}</span><strong title="${escapeHtml(value)}">${escapeHtml(value)}</strong>`;
      grid.appendChild(field);
    });
  });
  const raw = [orbit.tle_line0, orbit.tle_line1, orbit.tle_line2].filter(Boolean).join("\n") || "当前快照未保存原始根数。下次 API 更新后可补充。";
  card.querySelector("pre").textContent = `${raw}\n\n验证时间: ${text(source.last_verified_utc)}\n文件/版本: ${text(source.bill_gray_file || source.source_commit)}`;
  const link = card.querySelector(".source-url");
  if (source.source_url) link.href = source.source_url; else link.remove();
  return card;
}

function renderSummary() {
  const records = state.catalog.records;
  const countSource = (name) => records.filter((record) => record.sources.some((source) => source.source === name)).length;
  $("#metric-total").textContent = records.length.toLocaleString("zh-CN");
  $("#metric-st").textContent = countSource("spacetrack").toLocaleString("zh-CN");
  $("#metric-bg").textContent = countSource("bill_gray").toLocaleString("zh-CN");
  $("#metric-matched").textContent = records.filter((record) => new Set(record.sources.map((source) => source.source)).size > 1).length.toLocaleString("zh-CN");
  $("#generated-at").textContent = `目录生成时间：${dateText(state.catalog.generated_at_utc, true)} UTC`;
}

function exportData(format) {
  const timestamp = new Date().toISOString().slice(0, 10);
  if (format === "json") {
    download(`cislunar-catalog-${timestamp}.json`, JSON.stringify({ ...state.catalog, records: state.filtered }, null, 2), "application/json");
    return;
  }
  const headers = ["name", "norad_cat_id", "cospar_id", "sources", "orbit_regime", "mission_status", "latest_epoch_utc", "semi_major_axis_km", "period_days"];
  const lines = [headers.join(",")];
  state.filtered.forEach((record) => {
    const source = latestSource(record);
    const row = [record.name, record.norad_cat_id, record.cospar_id, record.sources.map((item) => item.source).join("|"), record.orbit_regime, record.mission_status, source?.orbit?.epoch_utc, source?.orbit?.semi_major_axis_km, source?.orbit?.period_days];
    lines.push(row.map(csvCell).join(","));
  });
  download(`cislunar-catalog-${timestamp}.csv`, `\uFEFF${lines.join("\n")}`, "text/csv;charset=utf-8");
}

function csvCell(value) { const raw = value ?? ""; return `"${String(raw).replaceAll('"', '""')}"`; }
function download(name, content, type) { const url = URL.createObjectURL(new Blob([content], { type })); const a = document.createElement("a"); a.href = url; a.download = name; a.click(); URL.revokeObjectURL(url); }
function escapeHtml(value) { const node = document.createElement("span"); node.textContent = text(value, ""); return node.innerHTML; }

function bindEvents() {
  [elements.search, elements.source, elements.freshness, elements.sort, elements.eligible].forEach((input) => input.addEventListener(input === elements.search ? "input" : "change", applyFilters));
  elements.prev.addEventListener("click", () => { if (state.page > 1) { state.page--; renderTable(); } });
  elements.next.addEventListener("click", () => { const pages = Math.ceil(state.filtered.length / PAGE_SIZE); if (state.page < pages) { state.page++; renderTable(); } });
  $("#export-csv").addEventListener("click", () => exportData("csv"));
  $("#export-json").addEventListener("click", () => exportData("json"));
  document.addEventListener("keydown", (event) => { if (event.key === "/" && document.activeElement !== elements.search) { event.preventDefault(); elements.search.focus(); } });
}

async function init() {
  bindEvents();
  try {
    const response = await fetch(DATA_URL, { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    state.catalog = await response.json();
    renderSummary();
    applyFilters();
    $("#load-status").textContent = `目录已加载 · ${dateText(state.catalog.generated_at_utc, true)} UTC`;
    $("#load-status-dot").classList.add("ready");
  } catch (error) {
    console.error(error);
    $("#load-status").textContent = "目录读取失败";
    $("#load-status-dot").classList.add("error");
    elements.empty.hidden = false;
    elements.empty.querySelector("h3").textContent = "无法读取目录数据";
    elements.empty.querySelector("p").textContent = "请通过本地 HTTP 服务打开页面，并检查 public/data/catalog.json。";
  }
}

init();
