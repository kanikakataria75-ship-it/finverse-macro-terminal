// Macro Terrain — the Global Macro Radar as a 3D extruded map.
// Countries are prisms whose height and colour encode the active metric; quakes are pulsing rings
// with light beams, chokepoints are floating status beacons. Drag to orbit, scroll to zoom, double-click to reset.
import * as THREE from "three";
import { EffectComposer } from "three/addons/postprocessing/EffectComposer.js";
import { RenderPass } from "three/addons/postprocessing/RenderPass.js";
import { UnrealBloomPass } from "three/addons/postprocessing/UnrealBloomPass.js";
import { OutputPass } from "three/addons/postprocessing/OutputPass.js";

const W = 20, H = 10.4;          // map footprint in world units
const BASE = 0.05, MAXH = 1.55;  // resting land height, tallest prism
const NEUTRAL = new THREE.Color("#1f2a3a"); // steel-blue land so continents read without data
const TARGET = new THREE.Vector3(0, 0, 0.35);

/** Projected rings via d3's own clipping (handles the antimeridian: Russia, Fiji…). */
function ringsOf(object, path) {
  const rings = [];
  let cur = null;
  path.context({
    beginPath() {}, moveTo(x, y) { cur = [[x, y]]; rings.push(cur); }, lineTo(x, y) { if (cur) cur.push([x, y]); },
    closePath() { cur = null; }, arc() {},
  })(object);
  path.context(null);
  return rings.filter((r) => r.length > 2);
}
function area(r) {
  let a = 0;
  for (let i = 0, j = r.length - 1; i < r.length; j = i++) a += (r[j][0] - r[i][0]) * (r[j][1] + r[i][1]);
  return a / 2;
}
function inside([x, y], r) {
  let c = false;
  for (let i = 0, j = r.length - 1; i < r.length; j = i++) {
    const [xi, yi] = r[i], [xj, yj] = r[j];
    if ((yi > y) !== (yj > y) && x < ((xj - xi) * (y - yi)) / (yj - yi) + xi) c = !c;
  }
  return c;
}
/** Exterior rings share the orientation of the largest ring; the rest are holes. */
function shapesOf(feature, path) {
  const rings = ringsOf(feature, path).map((r) => ({ r, a: area(r) }));
  if (!rings.length) return [];
  const sign = Math.sign(rings.reduce((m, x) => (Math.abs(x.a) > Math.abs(m.a) ? x : m)).a);
  const outers = rings.filter((x) => Math.sign(x.a) === sign && Math.abs(x.a) > 1e-5).map((x) => ({ ring: x.r, holes: [] }));
  rings.filter((x) => Math.sign(x.a) !== sign).forEach((hole) => {
    const o = outers.find((o) => inside(hole.r[0], o.ring));
    if (o) o.holes.push(hole.r);
  });
  return outers.map((o) => {
    const s = new THREE.Shape(o.ring.map(([x, y]) => new THREE.Vector2(x, -y)));
    o.holes.forEach((hr) => s.holes.push(new THREE.Path(hr.map(([x, y]) => new THREE.Vector2(x, -y)))));
    return s;
  });
}
function glowTexture() {
  const c = document.createElement("canvas"); c.width = c.height = 256;
  const g = c.getContext("2d");
  const grd = g.createRadialGradient(128, 128, 0, 128, 128, 128);
  grd.addColorStop(0, "rgba(90,170,255,0.20)"); grd.addColorStop(0.45, "rgba(60,110,200,0.07)"); grd.addColorStop(1, "rgba(0,0,0,0)");
  g.fillStyle = grd; g.fillRect(0, 0, 256, 256);
  return new THREE.CanvasTexture(c);
}

export class MacroMap3D {
  constructor(container, { onHover, onClick } = {}) {
    this.el = container; this.onHover = onHover; this.onClick = onClick;
    this.canvas = document.createElement("canvas"); this.canvas.className = "stage";
    this.labelsEl = document.createElement("div"); this.labelsEl.className = "m3-labels";
    container.append(this.canvas, this.labelsEl);
    const r = (this.renderer = new THREE.WebGLRenderer({ canvas: this.canvas, antialias: true, alpha: true, powerPreference: "high-performance" }));
    r.setPixelRatio(Math.min(devicePixelRatio, 2));
    r.shadowMap.enabled = true; r.shadowMap.type = THREE.PCFSoftShadowMap;
    r.toneMapping = THREE.ACESFilmicToneMapping; r.toneMappingExposure = 1.15;
    this.scene = new THREE.Scene();
    this.camera = new THREE.PerspectiveCamera(30, 1, 0.1, 200);
    this.view = { az: 0, pol: 0.84, r: 19, tAz: 0, tPol: 0.84, zoom: 1 };  // distance = auto-fit × zoom
    this.clock = new THREE.Clock();
    this.countries = []; this.labels = []; this.pulses = [];
    this._lights();
    this.overlay = new THREE.Group(); this.scene.add(this.overlay);
    this.composer = new EffectComposer(r);
    this.composer.addPass(new RenderPass(this.scene, this.camera));
    this.bloom = new UnrealBloomPass(new THREE.Vector2(512, 512), 0.55, 0.45, 0.62);
    this.composer.addPass(this.bloom);
    this.composer.addPass(new OutputPass());
    this._interact();
    this._ro = new ResizeObserver(() => this.resize()); this._ro.observe(container);
    this.resize();
    this.ready = this._build();
  }

  _lights() {
    const s = this.scene;
    s.add(new THREE.HemisphereLight(0xaee8ff, 0x04060a, 0.65));
    const key = new THREE.DirectionalLight(0xfff0dc, 1.45);
    key.position.set(-8, 14, 7); key.castShadow = true;
    key.shadow.mapSize.set(2048, 2048);
    Object.assign(key.shadow.camera, { left: -13, right: 13, top: 9, bottom: -9, near: 1, far: 45 });
    key.shadow.bias = -0.0006;
    s.add(key);
    const rim = new THREE.DirectionalLight(0x7a8cff, 0.5); rim.position.set(7, 6, -11); s.add(rim);
    // stage: dark floor that catches the shadows + a soft pool of light under the map
    const floor = new THREE.Mesh(new THREE.PlaneGeometry(60, 40), new THREE.MeshStandardMaterial({ color: 0x05070b, roughness: 0.95, metalness: 0 }));
    floor.rotation.x = -Math.PI / 2; floor.position.y = -0.002; floor.receiveShadow = true; s.add(floor);
    const pool = new THREE.Mesh(new THREE.PlaneGeometry(30, 18), new THREE.MeshBasicMaterial({ map: glowTexture(), transparent: true, depthWrite: false, blending: THREE.AdditiveBlending }));
    pool.rotation.x = -Math.PI / 2; pool.position.y = 0.001; s.add(pool);
  }

  async _build() {
    const topo = await (await fetch("/vendor/data/countries-110m.json")).json();
    const feats = topojson.feature(topo, topo.objects.countries).features.filter((f) => f.geometry && f.id !== "010"); // no Antarctica
    this.proj = d3.geoNaturalEarth1().fitExtent([[-W / 2, -H / 2], [W / 2, H / 2]], { type: "Sphere" });
    const path = d3.geoPath(this.proj);
    const land = (this.land = new THREE.Group());
    land.rotation.x = -Math.PI / 2; // shapes are drawn in XY; extrusion (+Z) becomes height (+Y)
    this.scene.add(land);
    const lineLoop = (ring, z, mat) => new THREE.LineLoop(new THREE.BufferGeometry().setFromPoints(ring.map(([x, y]) => new THREE.Vector3(x, -y, z))), mat);
    const grat = new THREE.LineBasicMaterial({ color: 0x7fe3ff, transparent: true, opacity: 0.05 });
    ringsOf(d3.geoGraticule10(), path).forEach((r) => land.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(r.map(([x, y]) => new THREE.Vector3(x, -y, 0.003))), grat)));
    const rimMat = new THREE.LineBasicMaterial({ color: 0x9fe9ff, transparent: true, opacity: 0.2 });
    ringsOf({ type: "Sphere" }, path).forEach((r) => land.add(lineLoop(r, 0.003, rimMat)));
    for (const f of feats) {
      const shapes = shapesOf(f, path);
      if (!shapes.length) continue;
      const geo = new THREE.ExtrudeGeometry(shapes, { depth: 1, bevelEnabled: false, curveSegments: 1 });
      const top = new THREE.MeshStandardMaterial({ color: NEUTRAL.clone(), roughness: 0.38, metalness: 0.3, emissive: new THREE.Color(0) });
      const side = new THREE.MeshStandardMaterial({ color: NEUTRAL.clone().multiplyScalar(0.5), roughness: 0.75, metalness: 0.15 });
      const mesh = new THREE.Mesh(geo, [top, side]);
      mesh.castShadow = mesh.receiveShadow = true;
      mesh.scale.z = BASE;
      const edge = new THREE.LineBasicMaterial({ color: 0xbfefff, transparent: true, opacity: 0.18 });
      shapes.forEach((s) => mesh.add(new THREE.LineLoop(new THREE.BufferGeometry().setFromPoints(s.getPoints().map((p) => new THREE.Vector3(p.x, p.y, 1.002))), edge)));
      const [cx, cy] = path.centroid(f);
      mesh.userData = { id: +f.id, name: f.properties.name, cx, cy, h: BASE, th: BASE, lift: 0, start: 0,
        tcol: NEUTRAL.clone(), temis: new THREE.Color(0), top, side, edge, edgeBase: 0.18 };
      land.add(mesh);
      this.countries.push(mesh);
    }
    this.byId = new Map(this.countries.map((m) => [m.userData.id, m]));
    if (this._pendingData) this.setData(...this._pendingData);
    if (this._pendingOverlays) this.setOverlays(this._pendingOverlays);
  }

  /** data: Map<numericId, {color, h (0..1) | null}> · labels: [{id, text, tone}] */
  setData(data, labels = []) {
    if (!this.byId) { this._pendingData = [data, labels]; return; }
    const now = this.clock.elapsedTime;
    for (const m of this.countries) {
      const u = m.userData, d = data.get(u.id);
      const has = d && d.h != null;
      u.th = has ? BASE + Math.max(0.02, d.h) * MAXH : BASE;
      u.tcol.set(has ? d.color : NEUTRAL);
      u.temis.copy(u.tcol).multiplyScalar(has ? 0.1 + 0.45 * d.h : 0);
      u.start = now + ((u.cx + W / 2) / W) * 0.7; // west→east wave
    }
    this.labels.forEach((l) => l.el.remove());
    this.labels = labels.map((l) => {
      const m = this.byId.get(l.id);
      if (!m) return null;
      const el = document.createElement("div");
      el.className = "m3-label";
      const n = document.createElement("span"); n.textContent = (l.text || m.userData.name).toUpperCase();
      const v = document.createElement("b"); v.textContent = l.value || ""; v.className = l.tone || "";
      el.append(n, v);
      this.labelsEl.append(el);
      return { el, m };
    }).filter(Boolean);
  }

  setOverlays({ quakes = [], chokepoints = [] } = {}) {
    if (!this.proj) { this._pendingOverlays = { quakes, chokepoints }; return; }
    this.overlay.clear(); this.pulses = [];
    const at = (lon, lat) => { const p = this.proj([lon, lat]); return p ? new THREE.Vector3(p[0], 0, p[1]) : null; };
    const ringGeo = new THREE.RingGeometry(0.1, 0.13, 48);
    for (const q of quakes) {
      const p = at(q.lon, q.lat); if (!p) continue;
      const col = q.mag >= 6.5 ? 0xff5773 : 0xffb648;
      const ring = new THREE.Mesh(ringGeo, new THREE.MeshBasicMaterial({ color: col, transparent: true, side: THREE.DoubleSide, depthWrite: false, blending: THREE.AdditiveBlending }));
      ring.rotation.x = -Math.PI / 2; ring.position.copy(p).setY(0.03);
      ring.userData = { kind: "quake", info: q, speed: 0.55, scale: 1 + (q.mag - 5) * 0.7, phase: Math.random() };
      const beam = new THREE.Mesh(new THREE.CylinderGeometry(0.014, 0.014, 1, 6).translate(0, 0.5, 0),
        new THREE.MeshBasicMaterial({ color: col, transparent: true, opacity: 0.75, depthWrite: false, blending: THREE.AdditiveBlending }));
      beam.position.copy(p); beam.scale.y = 0.25 + (q.mag - 4.5) * 0.45;
      beam.userData = { kind: "quake", info: q };
      this.overlay.add(ring, beam); this.pulses.push(ring);
    }
    const gem = new THREE.OctahedronGeometry(0.11);
    for (const c of chokepoints) {
      const p = at(c.lon, c.lat); if (!p) continue;
      const col = c.status === "CRITICAL" ? 0xff3b5c : c.status === "ELEVATED" ? 0xffb648 : 0x7fe3ff;
      const g = new THREE.Mesh(gem, new THREE.MeshBasicMaterial({ color: col }));
      g.position.copy(p).setY(1.2);
      g.userData = { kind: "choke", info: c, bob: Math.random() * 6 };
      const stem = new THREE.Line(new THREE.BufferGeometry().setFromPoints([p.clone().setY(0.02), p.clone().setY(1.15)]),
        new THREE.LineBasicMaterial({ color: col, transparent: true, opacity: 0.35 }));
      this.overlay.add(g, stem);
      if (c.status !== "NORMAL") {
        const ring = new THREE.Mesh(ringGeo, new THREE.MeshBasicMaterial({ color: col, transparent: true, side: THREE.DoubleSide, depthWrite: false, blending: THREE.AdditiveBlending }));
        ring.rotation.x = -Math.PI / 2; ring.position.copy(p).setY(0.04);
        ring.userData = { kind: "choke", info: c, speed: 0.8, scale: 1.8, phase: Math.random() };
        this.overlay.add(ring); this.pulses.push(ring);
      }
    }
  }

  // ------------------------------------------------------------ interaction
  _interact() {
    const c = this.canvas;
    let drag = null, idleAt = 0;
    this.pointer = new THREE.Vector2(9, 9);
    this.ray = new THREE.Raycaster();
    c.addEventListener("pointerdown", (e) => { drag = { x: e.clientX, y: e.clientY, moved: 0 }; c.setPointerCapture(e.pointerId); });
    c.addEventListener("pointerup", (e) => {
      if (drag && drag.moved < 4 && this.hover && this.onClick) this.onClick(this.hover.userData);
      drag = null; idleAt = performance.now();
    });
    c.addEventListener("pointermove", (e) => {
      const rect = c.getBoundingClientRect();
      this.pointer.set(((e.clientX - rect.left) / rect.width) * 2 - 1, -((e.clientY - rect.top) / rect.height) * 2 + 1);
      this._evt = e;
      if (!drag) return;
      const dx = e.clientX - drag.x, dy = e.clientY - drag.y;
      drag.moved += Math.abs(dx) + Math.abs(dy); drag.x = e.clientX; drag.y = e.clientY;
      this.view.tAz = Math.max(-0.75, Math.min(0.75, this.view.tAz - dx * 0.004));
      this.view.tPol = Math.max(0.3, Math.min(1.2, this.view.tPol - dy * 0.004));
      idleAt = performance.now();
    });
    c.addEventListener("pointerleave", () => { this.pointer.set(9, 9); this._setHover(null); });
    c.addEventListener("wheel", (e) => { e.preventDefault(); this.view.zoom = Math.max(0.5, Math.min(1.5, this.view.zoom * (1 + e.deltaY * 0.0009))); idleAt = performance.now(); }, { passive: false });
    c.addEventListener("dblclick", () => Object.assign(this.view, { tAz: 0, tPol: 0.84, zoom: 1 }));
    this._idle = () => performance.now() - idleAt > 6000;
  }
  _setHover(obj) {
    if (obj === this.hover) return;
    if (this.hover?.userData.edge) { this.hover.userData.lift = 0; this.hover.userData.edge.opacity = this.hover.userData.edgeBase; }
    this.hover = obj;
    if (obj?.userData.edge) { obj.userData.lift = 0.16; obj.userData.edge.opacity = 0.9; }
    this.canvas.style.cursor = obj ? "pointer" : "grab";
    if (this.onHover) this.onHover(obj ? obj.userData : null, this._evt);
  }

  resize() {
    const w = this.el.clientWidth, h = this.el.clientHeight;
    if (!w || !h) return;
    this.renderer.setSize(w, h, false);
    this.composer.setSize(w, h);
    this.bloom.resolution.set(w, h);
    this.camera.aspect = w / h;
    // fit the whole map on narrow panels
    // keep the whole map (20 units wide, tilted) in frame whatever the panel's shape
    this.fitR = Math.max(21, 25.5 * (1.75 / Math.min(1.75, w / h)));
    this.camera.updateProjectionMatrix();
  }
  start() {
    if (this.running) return;
    this.running = true; this.clock.getDelta();
    const loop = () => { if (!this.running) return; this._raf = requestAnimationFrame(loop); this.frame(); };
    loop();
  }
  stop() { this.running = false; cancelAnimationFrame(this._raf); }

  frame() {
    const dt = Math.min(0.05, this.clock.getDelta()), t = this.clock.elapsedTime, v = this.view;
    if (this._idle()) v.tAz = Math.sin(t * 0.11) * 0.14;
    const k = Math.min(1, dt * 4);
    v.az += (v.tAz - v.az) * k; v.pol += (v.tPol - v.pol) * k; v.r += ((this.fitR || 24) * v.zoom - v.r) * k;
    this.camera.position.set(TARGET.x + v.r * Math.sin(v.pol) * Math.sin(v.az), TARGET.y + v.r * Math.cos(v.pol), TARGET.z + v.r * Math.sin(v.pol) * Math.cos(v.az));
    this.camera.lookAt(TARGET);
    const kk = Math.min(1, dt * 5);
    for (const m of this.countries) {
      const u = m.userData;
      if (t < u.start) continue;
      u.h += (u.th + u.lift - u.h) * kk;
      m.scale.z = u.h;
      u.top.color.lerp(u.tcol, kk);
      u.top.emissive.lerp(u.temis, kk);
      u.side.color.copy(u.top.color).multiplyScalar(0.42);
    }
    for (const p of this.pulses) {
      const d = p.userData, ph = (t * d.speed + d.phase) % 1;
      p.scale.setScalar(0.5 + ph * 3 * d.scale);
      p.material.opacity = (1 - ph) * 0.9;
    }
    for (const o of this.overlay.children) if (o.userData.bob != null) { o.position.y = 1.2 + Math.sin(t * 1.6 + o.userData.bob) * 0.06; o.rotation.y += dt * 1.2; }
    this._pick();
    this._labels();
    this.composer.render();
  }
  _pick() {
    if (this.pointer.x > 5) return;
    this.ray.setFromCamera(this.pointer, this.camera);
    const hit = this.ray.intersectObjects([...this.overlay.children.filter((o) => o.userData.kind), ...this.countries], false)[0];
    const obj = hit ? hit.object : null;
    if (obj?.userData.kind) { if (this.hover !== obj) { this._setHover(null); this.hover = obj; this.canvas.style.cursor = "pointer"; if (this.onHover) this.onHover(obj.userData, this._evt); } return; }
    this._setHover(obj);
  }
  _labels() {
    const w = this.el.clientWidth, h = this.el.clientHeight, v = new THREE.Vector3();
    for (const l of this.labels) {
      const u = l.m.userData;
      v.set(u.cx, u.h + 0.08, u.cy).project(this.camera);
      l.el.style.transform = `translate(${(v.x * 0.5 + 0.5) * w}px, ${(-v.y * 0.5 + 0.5) * h}px) translate(-50%, -100%)`;
    }
  }
  dispose() { this.stop(); this._ro.disconnect(); this.renderer.dispose(); }
}
