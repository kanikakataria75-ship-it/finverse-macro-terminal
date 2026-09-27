// FINVERSE — cinematic boot sequence (Three.js particles + bloom), driven by real feed health.
import * as THREE from "three";
import { EffectComposer } from "three/addons/postprocessing/EffectComposer.js";
import { RenderPass } from "three/addons/postprocessing/RenderPass.js";
import { UnrealBloomPass } from "three/addons/postprocessing/UnrealBloomPass.js";
import { OutputPass } from "three/addons/postprocessing/OutputPass.js";
import { h } from "../core/util.js";

const VS = `
  attribute vec3 aStart; attribute vec3 aSphere; attribute vec3 aText; attribute float aRand;
  uniform float uA; uniform float uB; uniform float uC; uniform float uTime; uniform float uPx;
  varying vec3 vColor; varying float vAlpha;
  mat2 rot(float a){ float c=cos(a), s=sin(a); return mat2(c,-s,s,c); }
  float ease(float t){ return t<0.5 ? 4.0*t*t*t : 1.0 - pow(-2.0*t+2.0, 3.0)/2.0; }
  void main() {
    float a = ease(clamp(uA * 1.35 - aRand * 0.35, 0.0, 1.0));
    float b = ease(clamp(uB * 1.4 - (1.0 - aRand) * 0.4, 0.0, 1.0));
    vec3 p0 = aStart; p0.xz = rot(uTime * (0.25 + aRand * 0.5)) * p0.xz;
    vec3 p1 = aSphere; p1.xz = rot(uTime * 0.35) * p1.xz;
    p1 += normalize(aSphere) * sin(uTime * 2.0 + aRand * 40.0) * 0.025;
    vec3 p2 = aText + vec3(sin(uTime * 1.3 + aRand * 30.0), cos(uTime * 1.1 + aRand * 20.0), 0.0) * 0.012;
    vec3 p = mix(mix(p0, p1, a), p2, b);
    p += normalize(p + vec3(0.001)) * uC * (1.5 + aRand * 9.0);
    p.z += uC * uC * 6.0 * aRand;
    vec3 gold = vec3(1.0, 0.8, 0.46), ice = vec3(0.48, 0.88, 1.0), white = vec3(1.0, 0.97, 0.9);
    vec3 cSphere = mix(gold, ice, step(0.62, aRand));
    vec3 cText = mix(ice, gold, smoothstep(-3.2, 3.2, aText.x)) * (0.85 + 0.3 * aRand);
    vColor = mix(mix(cSphere * 0.9, cSphere, a), cText, b);
    // letters pack ~16k additive points into a small area: dim and shrink them as they land
    vAlpha = (0.35 + 0.65 * max(a, b)) * (1.0 - uC * 0.6) * mix(0.85, 0.44, b);
    vec4 mv = modelViewMatrix * vec4(p, 1.0);
    gl_PointSize = (1.3 + aRand * 2.2) * mix(1.0, 0.7, b) * uPx / -mv.z;
    gl_Position = projectionMatrix * mv;
  }`;
const FS = `
  varying vec3 vColor; varying float vAlpha;
  void main() {
    float r = length(gl_PointCoord - 0.5);
    if (r > 0.5) discard;
    gl_FragColor = vec4(vColor, vAlpha * smoothstep(0.5, 0.0, r));
  }`;

function sampleText(text, count) {
  const cv = document.createElement("canvas");
  const W = 1600, H = 360;
  cv.width = W; cv.height = H;
  const g = cv.getContext("2d", { willReadFrequently: true });
  g.fillStyle = "#fff";
  g.textAlign = "center"; g.textBaseline = "middle";
  g.font = "300 200px Unbounded, Manrope, sans-serif";
  if ("letterSpacing" in g) g.letterSpacing = "38px";
  g.fillText(text, W / 2 + 19, H / 2);
  const data = g.getImageData(0, 0, W, H).data;
  const pts = [];
  for (let y = 0; y < H; y += 3) for (let x = 0; x < W; x += 3) if (data[(y * W + x) * 4 + 3] > 128) pts.push([x, y]);
  const out = new Float32Array(count * 3);
  const scale = 7.6 / W;
  for (let i = 0; i < count; i++) {
    const p = pts[(i * 7919) % pts.length] || [W / 2, H / 2];
    out[i * 3] = (p[0] - W / 2) * scale + (Math.random() - 0.5) * 0.012;
    out[i * 3 + 1] = -(p[1] - H / 2) * scale + (Math.random() - 0.5) * 0.012;
    out[i * 3 + 2] = (Math.random() - 0.5) * 0.08;
  }
  return out;
}

export async function playIntro(root, { health, sound, onDone }) {
  const canvas = h("canvas.stage");
  const log = h("div.boot-log");
  const title = h("div.intro-title", h("div.t1", "Macro Intelligence Terminal"), h("div.t2", "Obsidian Edition · v4.0"));
  const bar = h("i");
  const flash = h("div.flashout");
  const skip = h("button.intro-skip", "SKIP  ·  ESC");
  const pct = h("b", "0%");
  root.append(canvas, h("div.intro-hud",
    h("div.intro-corner.tl", "FINVERSE SYSTEMS", h("br"), "SECURE MARKET LINK"),
    h("div.intro-corner.tr", "CORE ", pct, h("br"), new Date().toUTCString().slice(0, 22).toUpperCase()),
    log, title, h("div.intro-progress", bar), flash, skip));

  try { await Promise.race([document.fonts.load("300 200px Unbounded"), new Promise((r) => setTimeout(r, 1200))]); } catch { /* fallback font */ }

  const renderer = new THREE.WebGLRenderer({ canvas, antialias: true, powerPreference: "high-performance" });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(45, 1, 0.1, 200);
  camera.position.set(0, 0, 9);
  const N = window.innerWidth < 900 ? 9000 : 16000;
  const start = new Float32Array(N * 3), sphere = new Float32Array(N * 3), rand = new Float32Array(N);
  const golden = Math.PI * (3 - Math.sqrt(5));
  for (let i = 0; i < N; i++) {
    const r = 5 + Math.random() * 11, a = Math.random() * Math.PI * 2;
    start[i * 3] = Math.cos(a) * r; start[i * 3 + 1] = (Math.random() - 0.5) * 2.2 * (r / 8); start[i * 3 + 2] = Math.sin(a) * r - 4;
    const y = 1 - (i / (N - 1)) * 2, rr = Math.sqrt(1 - y * y), th = golden * i;
    sphere[i * 3] = Math.cos(th) * rr * 2.05; sphere[i * 3 + 1] = y * 2.05; sphere[i * 3 + 2] = Math.sin(th) * rr * 2.05;
    rand[i] = Math.random();
  }
  const geo = new THREE.BufferGeometry();
  geo.setAttribute("position", new THREE.BufferAttribute(new Float32Array(N * 3), 3));
  geo.setAttribute("aStart", new THREE.BufferAttribute(start, 3));
  geo.setAttribute("aSphere", new THREE.BufferAttribute(sphere, 3));
  geo.setAttribute("aText", new THREE.BufferAttribute(sampleText("FINVERSE", N), 3));
  geo.setAttribute("aRand", new THREE.BufferAttribute(rand, 1));
  const U = { uA: { value: 0 }, uB: { value: 0 }, uC: { value: 0 }, uTime: { value: 0 }, uPx: { value: 300 } };
  const pts = new THREE.Points(geo, new THREE.ShaderMaterial({ vertexShader: VS, fragmentShader: FS, uniforms: U, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending }));
  pts.frustumCulled = false;
  scene.add(pts);
  // orbital rings
  const rings = [];
  [[2.55, 0xd9b56d, 1.15, 0.2], [2.9, 0x7fe3ff, -0.5, 0.9], [3.35, 0xd9b56d, 0.35, -0.6]].forEach(([r, c, tx, tz]) => {
    const m = new THREE.Mesh(new THREE.TorusGeometry(r, 0.004, 8, 220), new THREE.MeshBasicMaterial({ color: c, transparent: true, opacity: 0, blending: THREE.AdditiveBlending }));
    m.rotation.set(tx, 0, tz); scene.add(m); rings.push(m);
  });
  const composer = new EffectComposer(renderer);
  composer.addPass(new RenderPass(scene, camera));
  const bloom = new UnrealBloomPass(new THREE.Vector2(512, 512), 0.9, 0.55, 0.05);
  composer.addPass(bloom);
  composer.addPass(new OutputPass());
  const resize = () => {
    const w = window.innerWidth, hh = window.innerHeight;
    renderer.setSize(w, hh, false); composer.setSize(w, hh); bloom.resolution.set(w, hh);
    camera.aspect = w / hh;
    camera.position.z = w / hh < 1.2 ? 12.5 : 9;
    camera.updateProjectionMatrix();
    U.uPx.value = hh * 0.0105 * Math.min(window.devicePixelRatio, 2);
  };
  resize();
  window.addEventListener("resize", resize);

  // boot log from real feed health
  const feeds = (health && health.feeds) || [];
  const lines = [
    { k: "SYS", t: "Obsidian core · WebGL2 renderer", s: "ok", m: "READY" },
    ...feeds.map((f) => ({ k: "LINK", t: `${f.label} · ${f.source}`, s: f.status === "booting" ? "warn" : f.status, m: f.status === "idle" ? "STANDBY" : f.status === "ok" ? "ONLINE" : f.status.toUpperCase() })),
    { k: "SEC", t: "Local-only gateway · same-origin policy", s: "ok", m: "SEALED" },
  ];
  let li = 0;
  const addLine = () => {
    if (li >= lines.length) return;
    const L = lines[li++];
    const ts = (performance.now() / 1000).toFixed(2).padStart(6, "0");
    log.append(h("div.l", h("span.k", L.k), h("span", `[${ts}]`), h("span", L.t), h("span.s", { class: L.s }, L.m)));
    while (log.children.length > 9) log.firstChild.remove();
  };

  let done = false, t0 = performance.now(), raf;
  const finish = () => {
    if (done) return; done = true;
    cancelAnimationFrame(raf);
    window.removeEventListener("resize", resize);
    window.removeEventListener("keydown", onKey);
    onDone();
    setTimeout(() => { renderer.dispose(); geo.dispose(); root.replaceChildren(); }, 1200);
  };
  const onKey = (e) => { if (e.key === "Escape") { skipTo(); } };
  const skipTo = () => { t0 = performance.now() - 7200 * 1; };
  skip.addEventListener("click", skipTo);
  window.addEventListener("keydown", onKey);
  sound.boot();

  const ease = (x) => (x < 0.5 ? 4 * x * x * x : 1 - Math.pow(-2 * x + 2, 3) / 2);
  const seg = (t, a, b) => Math.min(1, Math.max(0, (t - a) / (b - a)));
  let revealed = false, whooshed = false, nextLog = 0.35;
  const loop = () => {
    raf = requestAnimationFrame(loop);
    const t = (performance.now() - t0) / 1000;
    U.uTime.value = t;
    U.uA.value = seg(t, 0.1, 2.6);
    U.uB.value = seg(t, 3.5, 5.3);
    U.uC.value = ease(seg(t, 7.1, 8.1));
    const ringA = seg(t, 1.6, 2.6) * (1 - seg(t, 3.4, 4.2));
    rings.forEach((r, i) => { r.material.opacity = ringA * (0.55 - i * 0.1); r.rotation.y += 0.004 + i * 0.002; r.rotation.x += 0.0015; });
    camera.position.x = Math.sin(t * 0.3) * 0.25;
    camera.position.y = Math.cos(t * 0.25) * 0.15;
    if (t > 7.1) camera.position.z -= 0.08;
    camera.lookAt(0, 0, 0);
    bloom.strength = 0.7 - seg(t, 3.5, 5.2) * 0.12 + U.uC.value * 1.1;
    if (t > nextLog && t < 6.6) { addLine(); nextLog += 6.0 / Math.max(8, lines.length); }
    const prog = Math.min(1, t / 7.4);
    bar.style.width = `${prog * 100}%`;
    pct.textContent = `${Math.round(prog * 100)}%`;
    if (t > 5.0 && !revealed) { revealed = true; title.classList.add("on"); sound.reveal(); }
    if (t > 7.0 && !whooshed) { whooshed = true; title.classList.remove("on"); sound.whoosh(); }
    flash.style.opacity = seg(t, 7.55, 8.05) * 0.9;
    composer.render();
    if (t > 8.1) finish();
  };
  loop();
}
