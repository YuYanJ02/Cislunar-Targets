import * as THREE from "three";
import { OrbitControls } from "three/addons/controls/OrbitControls.js";
import * as satellite from "satellite.js";
import * as Astronomy from "astronomy-engine";

const CATALOG_URL = "./data/catalog.json";
const MAX_TARGETS = 8;
const AU_KM = 149597870.7;
const EARTH_RADIUS_KM = 6378.137;
const MOON_RADIUS_KM = 1737.4;
const GEO_RADIUS_KM = 42164;
const EARTH_MOON_MU = 0.0121505856;
const TARGET_COLORS = [0x50d5de, 0xf0a35a, 0x73d7a0, 0xb89cff, 0xf0788c, 0xffd166, 0x6fa8ff, 0xd0e36d];

const state = {
  catalog: null,
  selectedKeys: [],
  frame: "teme",
  sourceMode: "auto",
  displayDate: new Date(),
  renderInfo: [],
  labels: [],
  initialFitDone: false,
};

const elements = {
  container: document.querySelector("#scene-container"),
  canvas: document.querySelector("#orbit-canvas"),
  labels: document.querySelector("#scene-labels"),
  message: document.querySelector("#scene-message"),
  search: document.querySelector("#viewer-search"),
  targetList: document.querySelector("#viewer-target-list"),
  selectedTargets: document.querySelector("#selected-targets"),
  selectedCount: document.querySelector("#selected-count"),
  inspector: document.querySelector("#viewer-inspector-content"),
  frame: document.querySelector("#frame-select"),
  source: document.querySelector("#viewer-source-select"),
  time: document.querySelector("#viewer-time"),
  frameReadout: document.querySelector("#frame-readout"),
  timeReadout: document.querySelector("#time-readout"),
  status: document.querySelector("#viewer-status"),
  statusDot: document.querySelector("#viewer-status-dot"),
};

const scene = new THREE.Scene();
const renderer = new THREE.WebGLRenderer({
  canvas: elements.canvas,
  antialias: true,
  logarithmicDepthBuffer: true,
  powerPreference: "high-performance",
});
renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
renderer.outputColorSpace = THREE.SRGBColorSpace;
renderer.toneMapping = THREE.ACESFilmicToneMapping;
renderer.toneMappingExposure = 1.05;

const camera = new THREE.PerspectiveCamera(44, 1, 10, 60000000);
camera.position.set(480000, 310000, 380000);
const controls = new OrbitControls(camera, elements.canvas);
controls.enableDamping = true;
controls.dampingFactor = 0.07;
controls.minDistance = 12000;
controls.maxDistance = 12000000;
controls.target.set(0, 0, 0);

scene.add(new THREE.AmbientLight(0x8db9c9, 0.65));
const sunLight = new THREE.DirectionalLight(0xffffff, 2.1);
sunLight.position.set(2, 1, 1);
scene.add(sunLight);
const worldGroup = new THREE.Group();
scene.add(worldGroup);
addStarField();

const resizeObserver = new ResizeObserver(resizeRenderer);
resizeObserver.observe(elements.container);

function resizeRenderer() {
  const width = Math.max(1, elements.container.clientWidth);
  const height = Math.max(1, elements.container.clientHeight);
  renderer.setSize(width, height, false);
  camera.aspect = width / height;
  camera.updateProjectionMatrix();
}

function addStarField() {
  const random = seededRandom(20261014);
  const positions = new Float32Array(1600 * 3);
  for (let index = 0; index < positions.length; index += 3) {
    const radius = 4500000 + random() * 6000000;
    const z = random() * 2 - 1;
    const angle = random() * Math.PI * 2;
    const radial = Math.sqrt(1 - z * z);
    positions[index] = radius * radial * Math.cos(angle);
    positions[index + 1] = radius * radial * Math.sin(angle);
    positions[index + 2] = radius * z;
  }
  const geometry = new THREE.BufferGeometry();
  geometry.setAttribute("position", new THREE.BufferAttribute(positions, 3));
  const material = new THREE.PointsMaterial({ color: 0xb9d7df, size: 1200, sizeAttenuation: true, transparent: true, opacity: 0.56, depthWrite: false });
  scene.add(new THREE.Points(geometry, material));
}

function seededRandom(seed) {
  let value = seed >>> 0;
  return () => {
    value = (1664525 * value + 1013904223) >>> 0;
    return value / 4294967296;
  };
}

function moonState(date) {
  const value = Astronomy.GeoMoonState(date);
  return {
    position: new THREE.Vector3(value.x, value.y, value.z).multiplyScalar(AU_KM),
    velocity: new THREE.Vector3(value.vx, value.vy, value.vz).multiplyScalar(AU_KM / 86400),
  };
}

function frameTransform(moon) {
  if (state.frame === "teme") return (vector) => vector.clone();
  const xAxis = moon.position.clone().normalize();
  const zAxis = new THREE.Vector3().crossVectors(moon.position, moon.velocity).normalize();
  const yAxis = new THREE.Vector3().crossVectors(zAxis, xAxis).normalize();
  return (vector) => new THREE.Vector3(vector.dot(xAxis), vector.dot(yAxis), vector.dot(zAxis));
}

function clearWorld() {
  state.labels.forEach(({ element }) => element.remove());
  state.labels = [];
  while (worldGroup.children.length) {
    const child = worldGroup.children.pop();
    child.traverse((object) => {
      object.geometry?.dispose?.();
      if (Array.isArray(object.material)) object.material.forEach((material) => material.dispose?.());
      else object.material?.dispose?.();
    });
  }
}

function addReferenceScene(moon, transform) {
  const earth = new THREE.Mesh(
    new THREE.SphereGeometry(EARTH_RADIUS_KM, 48, 32),
    new THREE.MeshPhongMaterial({ color: 0x245f78, emissive: 0x071d28, specular: 0x4f8fa2, shininess: 24 })
  );
  worldGroup.add(earth);
  addLabel("地球", earth, "reference");

  const atmosphere = new THREE.Mesh(
    new THREE.SphereGeometry(EARTH_RADIUS_KM * 1.045, 48, 32),
    new THREE.MeshBasicMaterial({ color: 0x50d5de, transparent: true, opacity: 0.09, side: THREE.BackSide, depthWrite: false })
  );
  worldGroup.add(atmosphere);

  const moonMesh = new THREE.Mesh(
    new THREE.SphereGeometry(MOON_RADIUS_KM, 36, 24),
    new THREE.MeshPhongMaterial({ color: 0xa4aaad, emissive: 0x17191a, shininess: 3 })
  );
  moonMesh.position.copy(transform(moon.position));
  worldGroup.add(moonMesh);
  addLabel("月球", moonMesh, "reference");

  const geoPoints = [];
  for (let index = 0; index <= 256; index += 1) {
    const angle = index / 256 * Math.PI * 2;
    geoPoints.push(transform(new THREE.Vector3(GEO_RADIUS_KM * Math.cos(angle), GEO_RADIUS_KM * Math.sin(angle), 0)));
  }
  const geoLine = new THREE.Line(
    new THREE.BufferGeometry().setFromPoints(geoPoints),
    new THREE.LineBasicMaterial({ color: 0x73d7a0, transparent: true, opacity: 0.56 })
  );
  worldGroup.add(geoLine);

  const moonDistance = moon.position.length();
  const lagrangeOffset = Math.cbrt(EARTH_MOON_MU / 3);
  const xAxis = moon.position.clone().normalize();
  const l1 = transform(xAxis.clone().multiplyScalar(moonDistance * (1 - lagrangeOffset)));
  const l2 = transform(xAxis.clone().multiplyScalar(moonDistance * (1 + lagrangeOffset)));
  addReferenceMarker("L1", l1, 0xf0a35a);
  addReferenceMarker("L2", l2, 0xf0a35a);

  const axes = new THREE.AxesHelper(Math.max(90000, moonDistance * 0.28));
  axes.material.transparent = true;
  axes.material.opacity = 0.38;
  worldGroup.add(axes);
}

function addReferenceMarker(name, position, color) {
  const mesh = new THREE.Mesh(
    new THREE.SphereGeometry(1350, 18, 12),
    new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.92 })
  );
  mesh.position.copy(position);
  worldGroup.add(mesh);
  addLabel(name, mesh, "reference");
}

function addLabel(text, object, className = "") {
  const element = document.createElement("span");
  element.className = `scene-label ${className}`.trim();
  element.textContent = text;
  elements.labels.appendChild(element);
  state.labels.push({ element, object });
}

function sourceFor(record) {
  let candidates = (record.sources || []).filter((source) => source.orbit?.epoch_utc);
  if (state.sourceMode !== "auto") candidates = candidates.filter((source) => source.source === state.sourceMode);
  return candidates.sort((a, b) => new Date(b.orbit.epoch_utc) - new Date(a.orbit.epoch_utc))[0] || null;
}

function makeSatrec(record, source) {
  const orbit = source.orbit || {};
  try {
    if (orbit.tle_line1 && orbit.tle_line2) {
      return satellite.twoline2satrec(orbit.tle_line1, orbit.tle_line2);
    }
    if (typeof satellite.json2satrec !== "function") return null;
    return satellite.json2satrec({
      OBJECT_NAME: record.name,
      OBJECT_ID: record.cospar_id || "",
      EPOCH: orbit.epoch_utc,
      MEAN_MOTION: Number(orbit.mean_motion_rev_day),
      ECCENTRICITY: Number(orbit.eccentricity),
      INCLINATION: Number(orbit.inclination_deg),
      RA_OF_ASC_NODE: Number(orbit.raan_deg),
      ARG_OF_PERICENTER: Number(orbit.arg_pericenter_deg),
      MEAN_ANOMALY: Number(orbit.mean_anomaly_deg),
      EPHEMERIS_TYPE: Number(orbit.ephemeris_type || 0),
      CLASSIFICATION_TYPE: "U",
      NORAD_CAT_ID: Number(record.norad_cat_id || source.catalog_id || 0),
      ELEMENT_SET_NO: Number(orbit.element_set_no || 0),
      REV_AT_EPOCH: Number(orbit.rev_at_epoch || 0),
      BSTAR: Number(orbit.bstar || 0),
      MEAN_MOTION_DOT: Number(orbit.mean_motion_dot || 0),
      MEAN_MOTION_DDOT: Number(orbit.mean_motion_ddot || 0),
    });
  } catch (error) {
    console.warn("Unable to build SGP4 record", record.key, error);
    return null;
  }
}

function propagatedPosition(record, source, satrec, date) {
  if (satrec) {
    try {
      const result = satellite.propagate(satrec, date);
      const value = result?.position;
      if (value && [value.x, value.y, value.z].every(Number.isFinite)) {
        return { position: new THREE.Vector3(value.x, value.y, value.z), method: "SGP4" };
      }
    } catch (error) {
      console.warn("SGP4 propagation failed", record.key, error);
    }
  }
  const position = keplerPosition(source.orbit || {}, date);
  return position ? { position, method: "二体回退" } : null;
}

function keplerPosition(orbit, date, overrideMeanAnomaly = null) {
  const requiredFields = [
    "eccentricity",
    "inclination_deg",
    "raan_deg",
    "arg_pericenter_deg",
    "mean_anomaly_deg",
  ];
  if (requiredFields.some((field) => orbit[field] === null || orbit[field] === undefined || orbit[field] === "")) return null;
  const eccentricity = Number(orbit.eccentricity);
  const inclination = radians(orbit.inclination_deg);
  const raan = radians(orbit.raan_deg);
  const argPericenter = radians(orbit.arg_pericenter_deg);
  const meanMotion = Number(orbit.mean_motion_rev_day);
  const epoch = new Date(orbit.epoch_utc);
  let semiMajor = Number(orbit.semi_major_axis_km);
  if (!Number.isFinite(semiMajor) && Number.isFinite(meanMotion) && meanMotion > 0) {
    const angularRate = meanMotion * Math.PI * 2 / 86400;
    semiMajor = Math.cbrt(398600.4418 / (angularRate * angularRate));
  }
  if (![eccentricity, inclination, raan, argPericenter, semiMajor].every(Number.isFinite) || eccentricity < 0 || eccentricity >= 1) return null;
  const elapsedDays = Number.isNaN(epoch.getTime()) ? 0 : (date - epoch) / 86400000;
  const baseMeanAnomaly = radians(orbit.mean_anomaly_deg || 0);
  const meanAnomaly = overrideMeanAnomaly ?? baseMeanAnomaly + (Number.isFinite(meanMotion) ? meanMotion * Math.PI * 2 * elapsedDays : 0);
  let eccentricAnomaly = normalizeAngle(meanAnomaly);
  for (let iteration = 0; iteration < 12; iteration += 1) {
    eccentricAnomaly -= (eccentricAnomaly - eccentricity * Math.sin(eccentricAnomaly) - normalizeAngle(meanAnomaly)) / (1 - eccentricity * Math.cos(eccentricAnomaly));
  }
  const xOrbital = semiMajor * (Math.cos(eccentricAnomaly) - eccentricity);
  const yOrbital = semiMajor * Math.sqrt(1 - eccentricity * eccentricity) * Math.sin(eccentricAnomaly);
  return rotatePerifocal(new THREE.Vector3(xOrbital, yOrbital, 0), raan, inclination, argPericenter);
}

function rotatePerifocal(vector, raan, inclination, argPericenter) {
  vector.applyAxisAngle(new THREE.Vector3(0, 0, 1), argPericenter);
  vector.applyAxisAngle(new THREE.Vector3(1, 0, 0), inclination);
  vector.applyAxisAngle(new THREE.Vector3(0, 0, 1), raan);
  return vector;
}

function sampleOrbit(record, source, satrec) {
  const orbit = source.orbit || {};
  const epoch = new Date(orbit.epoch_utc);
  const periodDays = Number(orbit.period_days) || (Number(orbit.mean_motion_rev_day) > 0 ? 1 / Number(orbit.mean_motion_rev_day) : null);
  const points = [];
  let method = "SGP4";
  if (satrec && !Number.isNaN(epoch.getTime()) && Number.isFinite(periodDays)) {
    for (let index = 0; index <= 240; index += 1) {
      const date = new Date(epoch.getTime() + periodDays * 86400000 * index / 240);
      const result = propagatedPosition(record, source, satrec, date);
      if (!result || result.method !== "SGP4") {
        points.length = 0;
        break;
      }
      points.push(result.position);
    }
  }
  if (!points.length) {
    method = "二体回退";
    for (let index = 0; index <= 240; index += 1) {
      const point = keplerPosition(orbit, epoch, Math.PI * 2 * index / 240);
      if (point) points.push(point);
    }
  }
  return { points, method };
}

function addTargetOrbit(record, source, color, transform) {
  const satrec = makeSatrec(record, source);
  const sampled = sampleOrbit(record, source, satrec);
  const current = propagatedPosition(record, source, satrec, state.displayDate);
  if (!sampled.points.length || !current) return null;

  const points = sampled.points.map(transform);
  const line = new THREE.Line(
    new THREE.BufferGeometry().setFromPoints(points),
    new THREE.LineBasicMaterial({ color, transparent: true, opacity: 0.88 })
  );
  worldGroup.add(line);

  const marker = new THREE.Mesh(
    new THREE.SphereGeometry(1150, 18, 12),
    new THREE.MeshBasicMaterial({ color })
  );
  const transformedPosition = transform(current.position);
  marker.position.copy(transformedPosition);
  worldGroup.add(marker);
  addLabel(record.name, marker);

  return {
    record,
    source,
    color,
    method: current.method === "SGP4" && sampled.method === "SGP4" ? "SGP4" : "二体回退",
    position: transformedPosition,
    geocentricDistance: current.position.length(),
  };
}

function rebuildScene({ fit = false } = {}) {
  if (!state.catalog) return;
  clearWorld();
  const moon = moonState(state.displayDate);
  const transform = frameTransform(moon);
  addReferenceScene(moon, transform);
  state.renderInfo = [];

  state.selectedKeys.forEach((key, index) => {
    const record = state.catalog.records.find((item) => item.key === key);
    const source = record ? sourceFor(record) : null;
    if (!record || !source) return;
    const info = addTargetOrbit(record, source, TARGET_COLORS[index % TARGET_COLORS.length], transform);
    if (info) state.renderInfo.push(info);
  });

  elements.frameReadout.textContent = state.frame === "teme" ? "TEME 地心惯性系" : "地心—月球旋转系";
  elements.timeReadout.textContent = `${state.displayDate.toISOString().replace(".000Z", "Z")}`;
  elements.message.hidden = state.renderInfo.length > 0;
  if (!state.renderInfo.length) elements.message.textContent = state.selectedKeys.length ? "所选来源缺少可传播轨道根数，请切换来源。" : "从左侧选择目标以绘制轨道。";
  renderInspector();
  if (fit || !state.initialFitDone) {
    fitCamera();
    state.initialFitDone = true;
  }
}

function fitCamera() {
  const box = new THREE.Box3().setFromObject(worldGroup);
  if (box.isEmpty()) return;
  const center = box.getCenter(new THREE.Vector3());
  const size = box.getSize(new THREE.Vector3());
  const largest = Math.max(size.x, size.y, size.z, 120000);
  const distance = Math.min(9500000, Math.max(160000, largest / (2 * Math.tan(THREE.MathUtils.degToRad(camera.fov / 2))) * 1.35));
  controls.target.copy(center);
  camera.position.copy(center).add(new THREE.Vector3(0.82, 0.58, 0.72).normalize().multiplyScalar(distance));
  controls.update();
}

function renderInspector() {
  elements.inspector.replaceChildren();
  if (!state.renderInfo.length) {
    elements.inspector.innerHTML = `<div class="inspector-empty"><strong>尚无可显示轨道</strong><span>选择目标或切换数据来源。</span></div>`;
    return;
  }
  state.renderInfo.forEach((info) => {
    const orbit = info.source.orbit || {};
    const epoch = new Date(orbit.epoch_utc);
    const ageDays = Number.isNaN(epoch.getTime()) ? null : Math.abs(state.displayDate - epoch) / 86400000;
    const card = document.createElement("article");
    card.className = "inspector-card";
    card.style.setProperty("--target-color", `#${info.color.toString(16).padStart(6, "0")}`);
    card.innerHTML = `
      <div class="inspector-card-head">
        <div><h3>${escapeHtml(info.record.name)}</h3><p>NORAD ${escapeHtml(text(info.record.norad_cat_id))} · ${escapeHtml(text(info.record.cospar_id))}</p></div>
        <span class="inspector-source">${sourceLabel(info.source.source)}</span>
      </div>
      <div class="inspector-grid">
        <div><span>根数历元</span><strong title="${escapeHtml(text(orbit.epoch_utc))}">${escapeHtml(shortDate(orbit.epoch_utc))}</strong></div>
        <div><span>传播方法</span><strong>${info.method}</strong></div>
        <div><span>半长轴 / km</span><strong>${formatNumber(orbit.semi_major_axis_km, 1)}</strong></div>
        <div><span>偏心率</span><strong>${formatNumber(orbit.eccentricity, 7)}</strong></div>
        <div><span>倾角 / deg</span><strong>${formatNumber(orbit.inclination_deg, 4)}</strong></div>
        <div><span>当前位置距离 / km</span><strong>${formatNumber(info.geocentricDistance, 0)}</strong></div>
        <div><span>周期 / day</span><strong>${formatNumber(orbit.period_days, 4)}</strong></div>
        <div><span>历元时差 / day</span><strong>${ageDays === null ? "—" : formatNumber(ageDays, 2)}</strong></div>
      </div>
      ${info.method !== "SGP4" ? `<div class="propagation-note">SGP4 无法生成完整轨道，当前使用归一化平均根数进行二体几何回退。</div>` : ""}`;
    elements.inspector.appendChild(card);
  });
}

function renderTargetList() {
  if (!state.catalog) return;
  const query = elements.search.value.trim().toLocaleLowerCase("zh-CN");
  const records = state.catalog.records
    .filter((record) => record.eligible !== false)
    .filter((record) => (record.sources || []).some((source) => source.orbit?.epoch_utc))
    .filter((record) => {
      if (!query) return true;
      return [record.name, record.norad_cat_id, record.cospar_id, ...(record.aliases || [])]
        .filter(Boolean).join(" ").toLocaleLowerCase("zh-CN").includes(query);
    })
    .slice(0, 120);

  elements.targetList.replaceChildren(...records.map((record) => {
    const selected = state.selectedKeys.includes(record.key);
    const button = document.createElement("button");
    button.type = "button";
    button.className = "viewer-target-row";
    button.disabled = !selected && state.selectedKeys.length >= MAX_TARGETS;
    button.innerHTML = `<span><strong>${escapeHtml(record.name)}</strong><small>NORAD ${escapeHtml(text(record.norad_cat_id))} · ${escapeHtml(text(record.cospar_id))}</small></span><span class="add-mark">${selected ? "✓" : "+"}</span>`;
    button.addEventListener("click", () => selected ? removeTarget(record.key) : addTarget(record.key));
    return button;
  }));
  renderSelectedTargets();
}

function renderSelectedTargets() {
  elements.selectedTargets.replaceChildren();
  state.selectedKeys.forEach((key, index) => {
    const record = state.catalog.records.find((item) => item.key === key);
    if (!record) return;
    const chip = document.createElement("span");
    chip.className = "selected-target-chip";
    chip.style.borderColor = `#${TARGET_COLORS[index % TARGET_COLORS.length].toString(16).padStart(6, "0")}66`;
    chip.innerHTML = `<span>${escapeHtml(record.name)}</span><button type="button" aria-label="移除 ${escapeHtml(record.name)}">×</button>`;
    chip.querySelector("button").addEventListener("click", () => removeTarget(key));
    elements.selectedTargets.appendChild(chip);
  });
  elements.selectedCount.textContent = `${state.selectedKeys.length} / ${MAX_TARGETS}`;
}

function addTarget(key) {
  if (state.selectedKeys.includes(key) || state.selectedKeys.length >= MAX_TARGETS) return;
  state.selectedKeys.push(key);
  renderTargetList();
  rebuildScene({ fit: true });
}

function removeTarget(key) {
  state.selectedKeys = state.selectedKeys.filter((item) => item !== key);
  renderTargetList();
  rebuildScene({ fit: true });
}

function setDefaultTargets() {
  const preferredNames = ["DRO-A", "DRO-B"];
  state.selectedKeys = preferredNames
    .map((name) => state.catalog.records.find((record) => record.name.toLocaleLowerCase() === name.toLocaleLowerCase())?.key)
    .filter(Boolean);
  if (!state.selectedKeys.length) {
    state.selectedKeys = state.catalog.records.filter((record) => record.eligible !== false).slice(0, 2).map((record) => record.key);
  }
}

function latestSelectedEpoch() {
  const epochs = state.selectedKeys
    .map((key) => state.catalog.records.find((record) => record.key === key))
    .map((record) => record && sourceFor(record)?.orbit?.epoch_utc)
    .filter(Boolean)
    .map((value) => new Date(value))
    .filter((date) => !Number.isNaN(date.getTime()));
  return epochs.sort((a, b) => b - a)[0] || new Date();
}

function bindEvents() {
  elements.search.addEventListener("input", renderTargetList);
  elements.frame.addEventListener("change", () => {
    state.frame = elements.frame.value;
    rebuildScene({ fit: true });
  });
  elements.source.addEventListener("change", () => {
    state.sourceMode = elements.source.value;
    rebuildScene();
  });
  elements.time.addEventListener("change", () => {
    const date = parseUtcInput(elements.time.value);
    if (!date) return;
    state.displayDate = date;
    rebuildScene();
  });
  document.querySelector("#use-now").addEventListener("click", () => setDisplayDate(new Date()));
  document.querySelector("#use-epoch").addEventListener("click", () => setDisplayDate(latestSelectedEpoch()));
  document.querySelector("#fit-view").addEventListener("click", fitCamera);
}

function setDisplayDate(date) {
  state.displayDate = date;
  elements.time.value = utcInputValue(date);
  rebuildScene();
}

function utcInputValue(date) {
  return date.toISOString().slice(0, 19);
}

function parseUtcInput(value) {
  if (!value) return null;
  const date = new Date(`${value}Z`);
  return Number.isNaN(date.getTime()) ? null : date;
}

function updateLabels() {
  const width = elements.container.clientWidth;
  const height = elements.container.clientHeight;
  const vector = new THREE.Vector3();
  state.labels.forEach(({ element, object }) => {
    object.getWorldPosition(vector);
    vector.project(camera);
    const visible = vector.z > -1 && vector.z < 1 && Math.abs(vector.x) < 1.15 && Math.abs(vector.y) < 1.15;
    element.hidden = !visible;
    if (visible) {
      element.style.left = `${(vector.x * 0.5 + 0.5) * width}px`;
      element.style.top = `${(-vector.y * 0.5 + 0.5) * height}px`;
    }
  });
}

function animate() {
  controls.update();
  updateLabels();
  renderer.render(scene, camera);
}
renderer.setAnimationLoop(animate);

async function init() {
  bindEvents();
  elements.time.value = utcInputValue(state.displayDate);
  resizeRenderer();
  try {
    const response = await fetch(CATALOG_URL, { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    state.catalog = await response.json();
    setDefaultTargets();
    renderTargetList();
    rebuildScene({ fit: true });
    elements.status.textContent = `三维场景已就绪 · ${state.catalog.records.length.toLocaleString("zh-CN")} 个目标`;
    elements.statusDot.classList.add("ready");
  } catch (error) {
    console.error(error);
    elements.message.hidden = false;
    elements.message.textContent = "目标目录读取失败，请刷新页面后重试。";
    elements.status.textContent = "三维场景初始化失败";
    elements.statusDot.classList.add("error");
  }
}

function radians(value) { return Number(value) * Math.PI / 180; }
function normalizeAngle(value) { const result = value % (Math.PI * 2); return result < 0 ? result + Math.PI * 2 : result; }
function sourceLabel(value) { return value === "spacetrack" ? "Space-Track" : "Bill Gray"; }
function text(value, fallback = "—") { return value === null || value === undefined || value === "" ? fallback : String(value); }
function shortDate(value) { const date = new Date(value); return Number.isNaN(date.getTime()) ? text(value) : date.toISOString().replace(".000Z", "Z"); }
function formatNumber(value, digits = 1) { const parsed = Number(value); return Number.isFinite(parsed) ? parsed.toLocaleString("zh-CN", { maximumFractionDigits: digits }) : "—"; }
function escapeHtml(value) { const node = document.createElement("span"); node.textContent = text(value, ""); return node.innerHTML; }

init();

