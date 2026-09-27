// Obsidian Globe — reusable Three.js world with live market/geo overlays.
import * as THREE from "three";
import { EffectComposer } from "three/addons/postprocessing/EffectComposer.js";
import { RenderPass } from "three/addons/postprocessing/RenderPass.js";
import { UnrealBloomPass } from "three/addons/postprocessing/UnrealBloomPass.js";
import { OutputPass } from "three/addons/postprocessing/OutputPass.js";
import { EXCHANGES, session, sunPosition, NUM_ISO } from "../core/world.js";

const DEG = Math.PI / 180;
export function ll2v(lat, lon, r = 1) {
  const phi = (90 - lat) * DEG, th = (lon + 180) * DEG;
  return new THREE.Vector3(-r * Math.sin(phi) * Math.cos(th), r * Math.cos(phi), r * Math.sin(phi) * Math.sin(th));
}

let _atlas;
async function atlas() {
  if (_atlas) return _atlas;
  const topo = await (await fetch("/vendor/data/countries-110m.json")).json();
  const countries = topojson.feature(topo, topo.objects.countries).features;
  // country-id raster: each country painted in a unique colour -> per-dot country lookup
  const W = 2048, H = 1024;
  const cv = document.createElement("canvas"); cv.width = W; cv.height = H;
  const g = cv.getContext("2d", { willReadFrequently: true });
  const proj = d3.geoEquirectangular().translate([W / 2, H / 2]).scale(W / (2 * Math.PI));
  const path = d3.geoPath(proj, g);
  countries.forEach((f, i) => { g.beginPath(); path(f); g.fillStyle = `rgb(${(i + 1) & 255},${((i + 1) >> 8) & 255},7)`; g.fill(); });
  const img = g.getImageData(0, 0, W, H).data;
  _atlas = { countries, W, H, img };
  return _atlas;
}

const DOT_VS = `
  attribute vec3 aColor; attribute float aSize; attribute float aHeat;
  uniform vec3 uSun; uniform float uTime; uniform float uPx;
  varying vec3 vColor; varying float vAlpha;
  void main() {
    vec3 n = normalize(position);
    float day = smoothstep(-0.12, 0.28, dot(n, uSun));
    vec3 dayC = mix(vec3(0.46, 0.55, 0.68), aColor, 0.55);
    vec3 nightC = mix(vec3(0.95, 0.72, 0.36) * 0.62, aColor, 0.35);
    vec3 c = mix(nightC, dayC, day);
    float pulse = aHeat * (0.55 + 0.45 * sin(uTime * 2.4 + position.x * 9.0));
    c = mix(c, vec3(1.0, 0.24, 0.34), clamp(pulse, 0.0, 0.85));
    vColor = c;
    vec4 mv = modelViewMatrix * vec4(position, 1.0);
    vAlpha = mix(0.55, 1.0, day) * smoothstep(-0.35, 0.15, dot(normalize(mat3(modelMatrix) * n), normalize(cameraPosition)));
    gl_PointSize = aSize * uPx * (1.0 + aHeat * 0.7) / -mv.z;
    gl_Position = projectionMatrix * mv;
  }`;
const DOT_FS = `
  varying vec3 vColor; varying float vAlpha;
  void main() {
    vec2 d = gl_PointCoord - 0.5; float r = length(d);
    if (r > 0.5) discard;
    gl_FragColor = vec4(vColor, vAlpha * smoothstep(0.5, 0.2, r));
  }`;
const SPHERE_FS = `
  uniform vec3 uSun; varying vec3 vN; varying vec3 vWN; varying vec3 vV;
  void main() {
    float day = smoothstep(-0.2, 0.35, dot(normalize(vN), uSun));
    vec3 base = mix(vec3(0.010, 0.012, 0.020), vec3(0.028, 0.040, 0.066), day);
    float fres = pow(1.0 - max(dot(normalize(vWN), normalize(vV)), 0.0), 3.0);
    vec3 rim = mix(vec3(0.85, 0.66, 0.32), vec3(0.45, 0.85, 1.0), day) * fres * 0.35;
    gl_FragColor = vec4(base + rim, 1.0);
  }`;
const SPHERE_VS = `
  varying vec3 vN; varying vec3 vWN; varying vec3 vV;
  void main() {
    vN = normalize(position);
    vWN = normalize(mat3(modelMatrix) * normal);
    vec4 wp = modelMatrix * vec4(position, 1.0);
    vV = cameraPosition - wp.xyz;
    gl_Position = projectionMatrix * viewMatrix * wp;
  }`;
const ATMO_FS = `
  varying vec3 vWN; varying vec3 vV; uniform vec3 uColor; uniform float uPow; uniform float uEdge; uniform float uStrength;
  void main() {
    // back-face shell: d runs from 0 at the shell's outer silhouette to -uEdge at the planet's limb
    float d = dot(normalize(vWN), normalize(vV));
    float i = pow(clamp(-d / uEdge, 0.0, 1.0), uPow) * uStrength;
    gl_FragColor = vec4(uColor * i, i);
  }`;
const ARC_VS = `attribute float aT; varying float vT; void main(){ vT = aT; gl_Position = projectionMatrix * modelViewMatrix * vec4(position,1.0); }`;
const ARC_FS = `
  uniform float uTime; uniform float uOff; uniform vec3 uColor; varying float vT;
  void main() {
    float head = fract(uTime * 0.22 + uOff);
    float d = vT - head; if (d > 0.0) d -= 1.0;
    float trail = smoothstep(-0.32, 0.0, d) * step(d, 0.0);
    float base = 0.10;
    gl_FragColor = vec4(uColor, base + trail * 0.95);
  }`;

export class Globe {
  constructor(canvas, opts = {}) {
    this.canvas = canvas;
    this.opts = { autoRotate: true, bloom: true, dots: 30000, labels: null, onHover: null, zoom: 3.25, offsetX: 0, ...opts };
    this.renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true, powerPreference: "high-performance" });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.renderer.setClearColor(0x000000, 0);
    this.scene = new THREE.Scene();
    this.camera = new THREE.PerspectiveCamera(38, 1, 0.1, 100);
    this.camera.position.set(0, 0.18, this.opts.zoom);
    this.world = new THREE.Group();
    this.scene.add(this.world);
    this.clock = new THREE.Clock();
    this.rot = { x: 0.32, y: -1.9, vx: 0, vy: 0.0009, dragging: false };
    this.markers = [];
    this.rings = [];
    this.running = false;
    this.data = {};
    this._build();
    this._interact();
    this.resize();
    this._ro = new ResizeObserver(() => this.resize());
    this._ro.observe(canvas);
  }

  _build() {
    const sun = sunPosition();
    this.uSun = { value: ll2v(sun.lat, sun.lon).normalize() };
    // base sphere
    const sphere = new THREE.Mesh(new THREE.SphereGeometry(0.995, 96, 96),
      new THREE.ShaderMaterial({ vertexShader: SPHERE_VS, fragmentShader: SPHERE_FS, uniforms: { uSun: this.uSun } }));
    this.world.add(sphere);
    // atmosphere (outer glow)
    const atmoMat = (color, radius, pow, strength) => new THREE.ShaderMaterial({
      vertexShader: SPHERE_VS, fragmentShader: ATMO_FS, blending: THREE.AdditiveBlending, side: THREE.BackSide, transparent: true, depthWrite: false,
      uniforms: { uColor: { value: new THREE.Color(color) }, uPow: { value: pow }, uStrength: { value: strength }, uEdge: { value: Math.sqrt(1 - 1 / (radius * radius)) } },
    });
    this.scene.add(new THREE.Mesh(new THREE.SphereGeometry(1.14, 64, 64), atmoMat(0x5fb8ff, 1.14, 2.4, 0.75)));
    this.scene.add(new THREE.Mesh(new THREE.SphereGeometry(1.32, 64, 64), atmoMat(0xd9b56d, 1.32, 3.2, 0.22)));
    // lat/lon hairlines
    const lineMat = new THREE.LineBasicMaterial({ color: 0x7fe3ff, transparent: true, opacity: 0.05 });
    for (let lat = -60; lat <= 60; lat += 30) {
      const pts = []; for (let lon = -180; lon <= 180; lon += 4) pts.push(ll2v(lat, lon, 1.001));
      this.world.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(pts), lineMat));
    }
    // starfield
    const sg = new THREE.BufferGeometry(), sp = [];
    for (let i = 0; i < 1600; i++) { const v = new THREE.Vector3().randomDirection().multiplyScalar(18 + Math.random() * 30); sp.push(v.x, v.y, v.z); }
    sg.setAttribute("position", new THREE.Float32BufferAttribute(sp, 3));
    this.stars = new THREE.Points(sg, new THREE.PointsMaterial({ color: 0xc4d4ff, size: 0.045, transparent: true, opacity: 0.55, depthWrite: false }));
    this.scene.add(this.stars);
    this._buildDots();
    this._buildExchanges();
    this._buildArcs();
    if (this.opts.bloom) {
      this.composer = new EffectComposer(this.renderer);
      this.composer.addPass(new RenderPass(this.scene, this.camera));
      this.bloom = new UnrealBloomPass(new THREE.Vector2(512, 512), 0.55, 0.5, 0.22);
      this.composer.addPass(this.bloom);
      this.composer.addPass(new OutputPass());
    }
  }

  async _buildDots() {
    const { countries, W, H, img } = await atlas();
    this.countries = countries;
    const N = this.opts.dots, pos = [], col = [], size = [], heat = [], cid = [];
    const golden = Math.PI * (3 - Math.sqrt(5));
    for (let i = 0; i < N; i++) {
      const y = 1 - (i / (N - 1)) * 2, r = Math.sqrt(1 - y * y), th = golden * i;
      const x = Math.cos(th) * r, z = Math.sin(th) * r;
      const lat = Math.asin(y) / DEG;
      const lon = Math.atan2(z, -x) / DEG - 180; // exact inverse of ll2v
      const lonN = ((((lon + 180) % 360) + 360) % 360) - 180;
      const px = Math.floor(((lonN + 180) / 360) * W), py = Math.floor(((90 - lat) / 180) * H);
      const k = (py * W + px) * 4;
      if (img[k + 2] !== 7) continue;
      const idx = img[k] + (img[k + 1] << 8) - 1;
      pos.push(x * 1.003, y * 1.003, z * 1.003);
      col.push(0.82, 0.87, 0.95);
      size.push(1.35 + Math.random() * 0.35);
      heat.push(0);
      cid.push(idx);
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.Float32BufferAttribute(pos, 3));
    g.setAttribute("aColor", new THREE.Float32BufferAttribute(col, 3));
    g.setAttribute("aSize", new THREE.Float32BufferAttribute(size, 1));
    g.setAttribute("aHeat", new THREE.Float32BufferAttribute(heat, 1));
    this.dotCountry = cid;
    this.uPx = { value: 1 };
    this.uTime = this.uTime || { value: 0 };
    this.dots = new THREE.Points(g, new THREE.ShaderMaterial({
      vertexShader: DOT_VS, fragmentShader: DOT_FS, transparent: true, depthWrite: false,
      uniforms: { uSun: this.uSun, uTime: this.uTime, uPx: this.uPx },
    }));
    this.world.add(this.dots);
    this.resize();
    if (this.data.geo) this.setGeo(this.data.geo);
  }

  _buildExchanges() {
    this.uTime = this.uTime || { value: 0 };
    const beamGeo = new THREE.CylinderGeometry(0.0025, 0.0025, 1, 6, 1, true).translate(0, 0.5, 0);
    const headGeo = new THREE.SphereGeometry(0.011, 12, 12);
    for (const ex of EXCHANGES) {
      const g = new THREE.Group();
      const p = ll2v(ex.lat, ex.lon, 1.0);
      g.position.copy(p);
      g.quaternion.setFromUnitVectors(new THREE.Vector3(0, 1, 0), p.clone().normalize());
      const beam = new THREE.Mesh(beamGeo, new THREE.MeshBasicMaterial({ color: 0xd9b56d, transparent: true, opacity: 0.8, depthWrite: false, blending: THREE.AdditiveBlending }));
      const head = new THREE.Mesh(headGeo, new THREE.MeshBasicMaterial({ color: 0xf4ddaa }));
      head.userData = { kind: "exchange", ex };
      g.add(beam, head);
      this.world.add(g);
      this.markers.push({ ex, g, beam, head });
    }
  }

  _buildArcs() {
    const pairs = [["NYSE", "LSE"], ["LSE", "NSE"], ["NSE", "SGX"], ["SGX", "HKEX"], ["HKEX", "TSE"], ["TSE", "NYSE"], ["NYSE", "B3"],
      ["LSE", "DFM"], ["DFM", "NSE"], ["HKEX", "ASX"], ["XETRA", "NSE"], ["SSE", "SGX"], ["LSE", "JSE"], ["NYSE", "TSX"]];
    const by = Object.fromEntries(EXCHANGES.map((e) => [e.id, e]));
    this.arcs = [];
    pairs.forEach(([a, b], i) => {
      const A = ll2v(by[a].lat, by[a].lon, 1.005), B = ll2v(by[b].lat, by[b].lon, 1.005);
      const mid = A.clone().add(B).multiplyScalar(0.5);
      const lift = 1 + A.distanceTo(B) * 0.38;
      mid.normalize().multiplyScalar(lift);
      const curve = new THREE.QuadraticBezierCurve3(A, mid, B);
      const pts = curve.getPoints(90);
      const g = new THREE.BufferGeometry().setFromPoints(pts);
      g.setAttribute("aT", new THREE.Float32BufferAttribute(pts.map((_, k) => k / (pts.length - 1)), 1));
      const m = new THREE.ShaderMaterial({
        vertexShader: ARC_VS, fragmentShader: ARC_FS, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending,
        uniforms: { uTime: this.uTime, uOff: { value: i * 0.137 }, uColor: { value: new THREE.Color(i % 3 === 0 ? 0x7fe3ff : 0xd9b56d) } },
      });
      const line = new THREE.Line(g, m);
      this.world.add(line);
      this.arcs.push(line);
    });
  }

  // ------------------------------------------------------------------ data
  setGeo(geo) {
    this.data.geo = geo;
    if (!this.dots || !this.countries) return;
    const conflict = geo.conflict || {};
    const heatByIdx = new Map();
    this.countries.forEach((f, i) => {
      const iso = NUM_ISO[+f.id];
      const sc = iso && conflict[iso] ? conflict[iso].score : 0;
      if (sc >= 45) heatByIdx.set(i, Math.min(1, (sc - 45) / 45));
    });
    const heat = this.dots.geometry.attributes.aHeat;
    for (let k = 0; k < this.dotCountry.length; k++) heat.array[k] = heatByIdx.get(this.dotCountry[k]) || 0;
    heat.needsUpdate = true;
    // rings: quakes + chokepoints
    this.rings.forEach((r) => this.world.remove(r.mesh));
    this.rings = [];
    const ring = (lat, lon, color, scale, speed, kind, info) => {
      const m = new THREE.Mesh(new THREE.RingGeometry(0.018, 0.022, 48),
        new THREE.MeshBasicMaterial({ color, transparent: true, opacity: 0.9, side: THREE.DoubleSide, depthWrite: false, blending: THREE.AdditiveBlending }));
      const p = ll2v(lat, lon, 1.006);
      m.position.copy(p);
      m.lookAt(p.clone().multiplyScalar(2));
      m.userData = { kind, info };
      this.world.add(m);
      this.rings.push({ mesh: m, scale, speed, phase: Math.random() });
    };
    (geo.quakes || []).filter((q) => q.mag >= 5.2).slice(0, 30).forEach((q) => ring(q.lat, q.lon, 0xffb648, 1 + (q.mag - 5) * 0.8, 0.5, "quake", q));
    (geo.chokepoints || []).forEach((c) => {
      const col = c.status === "CRITICAL" ? 0xff3b5c : c.status === "ELEVATED" ? 0xffb648 : 0x7fe3ff;
      ring(c.lat, c.lon, col, c.status === "NORMAL" ? 0.7 : 1.4, c.status === "NORMAL" ? 0.25 : 0.7, "choke", c);
    });
  }

  setQuotes(quotes) { this.data.quotes = quotes; }

  // ------------------------------------------------------------ interaction
  _interact() {
    const c = this.canvas;
    let lx = 0, ly = 0, idle = 0;
    this.ray = new THREE.Raycaster();
    this.mouse = new THREE.Vector2(9, 9);
    c.addEventListener("pointerdown", (e) => { this.rot.dragging = true; lx = e.clientX; ly = e.clientY; c.setPointerCapture(e.pointerId); });
    c.addEventListener("pointerup", () => { this.rot.dragging = false; idle = performance.now(); });
    c.addEventListener("pointermove", (e) => {
      const r = c.getBoundingClientRect();
      this.mouse.set(((e.clientX - r.left) / r.width) * 2 - 1, -((e.clientY - r.top) / r.height) * 2 + 1);
      this._mouseEvt = e;
      if (!this.rot.dragging) return;
      const dx = e.clientX - lx, dy = e.clientY - ly; lx = e.clientX; ly = e.clientY;
      this.rot.vy = dx * 0.0045; this.rot.vx = dy * 0.0035;
    });
    c.addEventListener("pointerleave", () => { this.mouse.set(9, 9); this.opts.onHover && this.opts.onHover(null); });
    c.addEventListener("wheel", (e) => {
      e.preventDefault();
      this.camera.position.z = Math.max(1.9, Math.min(7, this.camera.position.z + e.deltaY * 0.0015));
    }, { passive: false });
    this._idle = () => performance.now() - idle > 2500;
  }

  focus(lat, lon) {
    this.rot.targetY = -(lon + 90) * DEG;
    this.rot.targetX = lat * DEG * 0.85;
  }

  resize() {
    const w = this.canvas.clientWidth, h = this.canvas.clientHeight;
    if (!w || !h) return;
    this.renderer.setSize(w, h, false);
    this.camera.aspect = w / h;
    this.camera.setViewOffset(w, h, -w * this.opts.offsetX, 0, w, h);
    this.camera.updateProjectionMatrix();
    if (this.composer) { this.composer.setSize(w, h); this.bloom.resolution.set(w, h); }
    if (this.uPx) this.uPx.value = h * 0.0058 * Math.min(window.devicePixelRatio, 2);
  }

  start() { if (this.running) return; this.running = true; this.clock.getDelta(); const loop = () => { if (!this.running) return; this._raf = requestAnimationFrame(loop); this.frame(); }; loop(); }
  stop() { this.running = false; cancelAnimationFrame(this._raf); }

  frame() {
    const dt = Math.min(0.05, this.clock.getDelta()), t = this.clock.elapsedTime;
    this.uTime.value = t;
    // rotation with inertia + gentle auto-rotate
    if (this.rot.targetY != null) {
      this.rot.y += (this.rot.targetY - this.rot.y) * 0.06; this.rot.x += (this.rot.targetX - this.rot.x) * 0.06;
      if (Math.abs(this.rot.targetY - this.rot.y) < 0.002) this.rot.targetY = this.rot.targetX = null;
    } else {
      if (!this.rot.dragging) { this.rot.vx *= 0.94; this.rot.vy *= 0.95; if (this.opts.autoRotate && this._idle()) this.rot.vy += (0.0011 - this.rot.vy) * 0.02; }
      this.rot.y += this.rot.vy; this.rot.x = Math.max(-1.1, Math.min(1.1, this.rot.x + this.rot.vx));
    }
    this.world.rotation.set(this.rot.x, this.rot.y, 0);
    this.stars.rotation.y += dt * 0.004;
    if ((t | 0) % 30 === 0) { const s = sunPosition(); this.uSun.value.copy(ll2v(s.lat, s.lon).normalize()); }
    // exchange beacons
    const now = new Date();
    for (const m of this.markers) {
      const st = session(m.ex, now);
      m.open = st.open;
      const hgt = st.open ? 0.085 + 0.012 * Math.sin(t * 3 + m.ex.lon) : 0.03;
      m.beam.scale.y += (hgt - m.beam.scale.y) * 0.1;
      m.head.position.y = m.beam.scale.y;
      m.beam.material.color.setHex(st.open ? 0xd9b56d : 0x3b4a66);
      m.head.material.color.setHex(st.open ? 0xfff0c8 : 0x6f86a8);
      m.beam.material.opacity = st.open ? 0.9 : 0.45;
    }
    for (const r of this.rings) {
      const k = (t * r.speed + r.phase) % 1;
      r.mesh.scale.setScalar(0.4 + k * 2.6 * r.scale);
      r.mesh.material.opacity = (1 - k) * 0.9;
    }
    this._labels();
    this._hover();
    if (this.composer) this.composer.render(); else this.renderer.render(this.scene, this.camera);
  }

  _labels() {
    const el = this.opts.labels;
    if (!el) return;
    if (!this._labelEls) {
      this._labelEls = this.markers.map((m) => {
        const d = document.createElement("div"); d.className = "glabel";
        const n = document.createElement("span"); n.textContent = m.ex.id;
        const p = document.createElement("span"); p.className = "p";
        d.append(n, p); el.append(d); return { d, p };
      });
    }
    const w = this.canvas.clientWidth, h = this.canvas.clientHeight, v = new THREE.Vector3(), camDir = this.camera.position.clone().normalize();
    this.markers.forEach((m, i) => {
      const L = this._labelEls[i];
      m.head.getWorldPosition(v);
      const facing = v.clone().normalize().dot(camDir);
      v.project(this.camera);
      L.d.style.opacity = facing > 0.25 ? Math.min(1, (facing - 0.25) * 3) : 0;
      L.d.style.left = `${(v.x * 0.5 + 0.5) * w}px`;
      L.d.style.top = `${(-v.y * 0.5 + 0.5) * h}px`;
      L.d.classList.toggle("open", !!m.open);
      const q = this.data.quotes && m.ex.idx && this.data.quotes[m.ex.idx];
      const txt = q && q.pct != null ? `${q.pct > 0 ? "+" : ""}${q.pct.toFixed(2)}%` : "";
      if (L.p.textContent !== txt) { L.p.textContent = txt; L.p.style.color = q && q.pct < 0 ? "#ff5773" : "#2fe3a3"; }
    });
  }

  _hover() {
    if (!this.opts.onHover || this.mouse.x > 5) return;
    this.ray.setFromCamera(this.mouse, this.camera);
    const targets = [...this.markers.map((m) => m.head), ...this.rings.map((r) => r.mesh)];
    const hit = this.ray.intersectObjects(targets, false)[0];
    const key = hit ? hit.object.uuid : null;
    if (key !== this._hoverKey || hit) { this._hoverKey = key; this.opts.onHover(hit ? hit.object.userData : null, this._mouseEvt); }
  }

  dispose() { this.stop(); this._ro.disconnect(); this.renderer.dispose(); }
}
