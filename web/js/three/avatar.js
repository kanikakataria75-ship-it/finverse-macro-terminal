// VEDA — a human form assembled from neon dust. Three.js points + bloom, lip-synced to her voice.
// Geometry: "Infinite, 3D Head Scan" by Lee Perry-Smith, CC BY 3.0 (via the three.js examples).
import * as THREE from "three";
import { GLTFLoader } from "three/addons/loaders/GLTFLoader.js";
import { MeshSurfaceSampler } from "three/addons/math/MeshSurfaceSampler.js";
import { EffectComposer } from "three/addons/postprocessing/EffectComposer.js";
import { RenderPass } from "three/addons/postprocessing/RenderPass.js";
import { UnrealBloomPass } from "three/addons/postprocessing/UnrealBloomPass.js";
import { OutputPass } from "three/addons/postprocessing/OutputPass.js";

const VS = `
  attribute vec3 aStart; attribute vec3 aNormal; attribute float aRand;
  attribute float aJaw; attribute float aLip; attribute float aEye; attribute float aFade;
  uniform float uForm; uniform float uTime; uniform float uAmp; uniform float uListen; uniform float uThink;
  uniform float uPx; uniform float uScan;
  varying vec3 vColor; varying float vAlpha;
  void main() {
    // staggered assembly: each grain arrives on its own schedule
    float f = smoothstep(aRand * 0.42, aRand * 0.42 + 0.58, uForm);
    // dust nebula (slow swirl + drift)
    vec3 s = aStart;
    float a = uTime * (0.05 + aRand * 0.1) + aRand * 6.2831;
    s.xz = mat2(cos(a), -sin(a), sin(a), cos(a)) * s.xz;
    s.y += sin(uTime * 0.35 + aRand * 40.0) * 0.6;
    // body with a hinged jaw (hinge near the ears), opened by the voice amplitude
    vec3 t = position;
    vec3 hinge = vec3(0.0, 0.45, -0.25);
    float ang = aJaw * uAmp * 0.3;
    vec3 r = t - hinge;
    r = vec3(r.x, r.y * cos(ang) - r.z * sin(ang), r.y * sin(ang) + r.z * cos(ang));
    t = hinge + r;
    t.y += aLip * uAmp * 0.07;
    // living surface: breathing shimmer, listening ripples, speaking push
    float ripple = sin(dot(position, vec3(0.6, 1.0, 0.3)) * 3.0 - uTime * 7.0);
    t += aNormal * (sin(uTime * 2.4 + aRand * 50.0) * 0.012 + ripple * uListen * 0.05 + uAmp * aRand * 0.03);
    vec3 p = mix(s, t, f);
    // thinking: a sliver of grains leaves the body and orbits the head like streaming data
    float halo = step(0.93, aRand) * uThink;
    float oa = uTime * (1.2 + aRand) + aRand * 80.0;
    vec3 orbit = vec3(cos(oa) * 3.3, 1.4 + sin(oa * 1.7 + aRand * 9.0) * 1.1, sin(oa) * 3.3);
    p = mix(p, orbit, halo);
    vec4 mv = modelViewMatrix * vec4(p, 1.0);
    gl_PointSize = (1.0 + aRand * 1.5) * (1.0 + aEye * 0.9) * (1.0 + uAmp * 0.2 * f) * uPx / -mv.z;
    gl_Position = projectionMatrix * mv;
    // hologram lighting: rim glow + soft key light sculpt the face so features read
    // rim uses a smoothed, head-shaped normal so only the silhouette glows (fine normals would
    // outline every protrusion — lips, chin, eye sockets — like a mask); the key light keeps the
    // fine normals for soft shading of nose, brow and lips
    vec3 radial = normalize((position - vec3(0.0, 1.2, 0.3)) / vec3(1.0, 1.3, 1.1));
    float headW = smoothstep(-1.4, -0.9, position.y);
    vec3 nvs = normalize(normalMatrix * normalize(mix(aNormal, radial, 0.8 * headW)));
    float rim = pow(1.0 - abs(nvs.z), 2.4);
    vec3 nv = normalize(normalMatrix * aNormal);
    float key = max(dot(nv, normalize(vec3(-0.5, 0.45, 0.72))), 0.0);
    // features (brow, nose, lips, cheekbones) are where the true surface departs from the head's curve
    float feature = clamp(1.0 - dot(normalize(aNormal), radial), 0.0, 1.0) * headW;
    float shade = mix(1.0, 0.12 + 0.66 * key + 0.8 * rim + 0.6 * feature, f);
    // neon palette: violet crown -> ice-cyan face, sparse gold sparks, warm glinting eyes
    vec3 cyan = vec3(0.3, 0.88, 1.0), violet = vec3(0.58, 0.45, 1.0), gold = vec3(1.0, 0.8, 0.46);
    vec3 col = mix(cyan, violet, clamp((position.y - 0.8) / 3.2, 0.0, 1.0) * 0.75 + smoothstep(0.7, 1.0, aRand) * 0.25);
    col = mix(col, gold, step(0.965, aRand) * 0.85);
    col *= shade * (0.78 + 0.22 * sin(uTime * 3.0 + aRand * 120.0));
    float scan = smoothstep(0.35, 0.0, abs(position.y - uScan)) * f;
    col += vec3(0.45, 0.85, 1.0) * scan * 0.35;
    float dm = length(position - vec3(0.0, -0.05, 2.25));
    col += vec3(1.0, 0.85, 0.62) * uAmp * (0.5 + 0.5 * sin(dm * 7.0 - uTime * 16.0)) * smoothstep(1.7, 0.0, dm) * 0.32;
    col = mix(col, vec3(1.0, 0.9, 0.72) * 1.9, aEye * (0.8 + 0.2 * max(uAmp, uListen)));
    col *= 0.9 + uAmp * 0.2 + uListen * 0.15;
    vColor = col;
    vAlpha = mix(0.16, 0.62, f) * mix(1.0, aFade, f) * (0.45 + 0.55 * aRand) + halo * 0.4;
  }`;
const FS = `
  varying vec3 vColor; varying float vAlpha;
  void main() {
    float r = length(gl_PointCoord - 0.5);
    if (r > 0.5) discard;
    gl_FragColor = vec4(vColor, vAlpha * smoothstep(0.5, 0.05, r));
  }`;
const DUST_VS = `
  attribute float aRand; uniform float uTime; uniform float uPx; varying float vA;
  void main() {
    vec3 p = position;
    p.y = mod(p.y + uTime * (0.05 + aRand * 0.12) + 6.0, 12.0) - 6.0;
    p.x += sin(uTime * 0.3 + aRand * 30.0) * 0.3;
    vec4 mv = modelViewMatrix * vec4(p, 1.0);
    gl_PointSize = (0.6 + aRand * 1.2) * uPx / -mv.z;
    gl_Position = projectionMatrix * mv;
    vA = 0.15 + aRand * 0.35;
  }`;
const DUST_FS = `
  varying float vA;
  void main() { float r = length(gl_PointCoord - 0.5); if (r > 0.5) discard; gl_FragColor = vec4(0.55, 0.85, 1.0, vA * smoothstep(0.5, 0.0, r)); }`;

const ss = (e0, e1, x) => { const t = Math.min(1, Math.max(0, (x - e0) / (e1 - e0))); return t * t * (3 - 2 * t); };

export class VedaAvatar {
  constructor(canvas) {
    this.canvas = canvas;
    this.renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true, powerPreference: "high-performance" });
    this.renderer.setPixelRatio(Math.min(devicePixelRatio, 2));
    this.renderer.setClearColor(0x000000, 0);
    this.scene = new THREE.Scene();
    this.camera = new THREE.PerspectiveCamera(30, 1, 0.1, 100);
    this.camera.position.set(0, 0.12, 7.4);
    this.group = new THREE.Group();
    this.group.scale.setScalar(0.3);
    this.scene.add(this.group);
    this.U = { uForm: { value: 0 }, uTime: { value: 0 }, uAmp: { value: 0 }, uListen: { value: 0 }, uThink: { value: 0 }, uPx: { value: 8 }, uScan: { value: 0 } };
    this.goal = { form: 0, think: 0 };
    this.amp = 0; this.listen = 0;
    this.mouse = { x: 0, y: 0 };
    this.clock = new THREE.Clock();
    this.composer = new EffectComposer(this.renderer);
    this.composer.addPass(new RenderPass(this.scene, this.camera));
    this.bloom = new UnrealBloomPass(new THREE.Vector2(512, 512), 0.62, 0.55, 0.12);
    this.composer.addPass(this.bloom);
    this.composer.addPass(new OutputPass());
    this._dust();
    this.ready = this._load();
    this._ro = new ResizeObserver(() => this.resize());
    this._ro.observe(canvas);
    window.addEventListener("pointermove", (e) => { this.mouse.x = e.clientX / innerWidth - 0.5; this.mouse.y = e.clientY / innerHeight - 0.5; });
    this.resize();
  }

  _dust() {
    const n = 1400, pos = new Float32Array(n * 3), rnd = new Float32Array(n);
    for (let i = 0; i < n; i++) { pos[i * 3] = (Math.random() - 0.5) * 16; pos[i * 3 + 1] = (Math.random() - 0.5) * 12; pos[i * 3 + 2] = -Math.random() * 8 + 1.5; rnd[i] = Math.random(); }
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.BufferAttribute(pos, 3));
    g.setAttribute("aRand", new THREE.BufferAttribute(rnd, 1));
    const m = new THREE.ShaderMaterial({ vertexShader: DUST_VS, fragmentShader: DUST_FS, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending, uniforms: { uTime: this.U.uTime, uPx: this.U.uPx } });
    const pts = new THREE.Points(g, m); pts.frustumCulled = false;
    this.scene.add(pts);
  }

  async _load() {
    const gltf = await new GLTFLoader().loadAsync("/vendor/models/LeePerrySmith.glb");
    let mesh = null;
    gltf.scene.traverse((o) => { if (o.isMesh && !mesh) mesh = o; });
    const sampler = new MeshSurfaceSampler(mesh).build();
    const want = innerWidth < 900 ? 15000 : 26000;
    const A = { pos: new Float32Array(want * 3), start: new Float32Array(want * 3), nrm: new Float32Array(want * 3),
      rnd: new Float32Array(want), jaw: new Float32Array(want), lip: new Float32Array(want), eye: new Float32Array(want), fade: new Float32Array(want) };
    // pass 1: oversample the surface and record the front-most depth per (x,y) cell. The scan has an
    // internal seam wall around the mouth patch; grains hidden behind the face surface would glow
    // through additive blending as a rectangular "mask", so they are dropped in pass 2.
    const M = want * 3, raw = new Float32Array(M * 6), frontZ = new Map(), CELL = 0.06;
    const cellKey = (x, y) => Math.floor((x + 5) / CELL) * 100000 + Math.floor((y + 5) / CELL);
    const v = new THREE.Vector3(), vn = new THREE.Vector3();
    for (let i = 0; i < M; i++) {
      sampler.sample(v, vn);
      raw.set([v.x, v.y, v.z, vn.x, vn.y, vn.z], i * 6);
      const key = cellKey(v.x, v.y);
      if (v.z > (frontZ.get(key) ?? -99)) frontZ.set(key, v.z);
    }
    const p = new THREE.Vector3(), n = new THREE.Vector3();
    let k = 0, i = 0;
    while (k < want && i < M) {
      p.set(raw[i * 6], raw[i * 6 + 1], raw[i * 6 + 2]);
      n.set(raw[i * 6 + 3], raw[i * 6 + 4], raw[i * 6 + 5]);
      i++;
      if (p.z > 0.5 && p.z < frontZ.get(cellKey(p.x, p.y)) - 0.12) continue; // internal wall, not skin
      // density: the face gets most grains, the back of the head fewer, shoulders sparse
      const keep = p.y > -1.3 ? 0.42 + 0.58 * ss(0.0, 1.8, p.z) : p.y > -2.2 ? 0.38 : 0.24;
      if (Math.random() > keep) continue;
      A.pos.set([p.x, p.y, p.z], k * 3);
      A.nrm.set([n.x, n.y, n.z], k * 3);
      A.rnd[k] = Math.random();
      const front = ss(0.4, 1.4, p.z);
      // landmarks measured from the scan: lip seam y≈0, chin y≈-0.9, eyes y≈1.7 x≈±0.52
      A.jaw[k] = front * ss(0.06, -0.14, p.y) * (1 - ss(-1.05, -1.5, p.y)) * (1 - ss(1.2, 1.7, Math.abs(p.x)));
      A.lip[k] = p.y > 0.02 && p.y < 0.42 && Math.abs(p.x) < 0.9 ? ss(1.9, 2.2, p.z) : 0;
      A.eye[k] = Math.hypot(Math.abs(p.x) - 0.5, (p.y - 1.7) * 1.4) < 0.14 && p.z > 1.88 ? 1 : 0;
      A.fade[k] = ss(-3.95, -2.2, p.y);
      // dust origin: a wide shell around the figure, some rising from below
      const d = new THREE.Vector3().randomDirection().multiplyScalar(9 + Math.random() * 9);
      if (Math.random() < 0.3) d.y = -8 - Math.random() * 6;
      A.start.set([d.x, d.y, d.z], k * 3);
      k++;
    }
    const g = new THREE.BufferGeometry();
    g.setAttribute("position", new THREE.BufferAttribute(A.pos.subarray(0, k * 3), 3));
    g.setAttribute("aStart", new THREE.BufferAttribute(A.start.subarray(0, k * 3), 3));
    g.setAttribute("aNormal", new THREE.BufferAttribute(A.nrm.subarray(0, k * 3), 3));
    g.setAttribute("aRand", new THREE.BufferAttribute(A.rnd.subarray(0, k), 1));
    g.setAttribute("aJaw", new THREE.BufferAttribute(A.jaw.subarray(0, k), 1));
    g.setAttribute("aLip", new THREE.BufferAttribute(A.lip.subarray(0, k), 1));
    g.setAttribute("aEye", new THREE.BufferAttribute(A.eye.subarray(0, k), 1));
    g.setAttribute("aFade", new THREE.BufferAttribute(A.fade.subarray(0, k), 1));
    this.points = new THREE.Points(g, new THREE.ShaderMaterial({ vertexShader: VS, fragmentShader: FS, uniforms: this.U, transparent: true, depthWrite: false, blending: THREE.AdditiveBlending }));
    this.points.frustumCulled = false;
    this.group.add(this.points);
    this.count = k;
  }

  // ------------------------------------------------------------ controls
  form() { this.goal.form = 1; }
  dissolve() { this.goal.form = 0; this.goal.think = 0; }
  think(on) { this.goal.think = on ? 1 : 0; }
  setAmp(v) { this.amp = v; }
  setListen(v) { this.listen = v; }
  get formed() { return this.U.uForm.value > 0.95; }
  get gone() { return this.U.uForm.value < 0.02 && this.goal.form === 0; }

  resize() {
    const w = this.canvas.clientWidth, h = this.canvas.clientHeight;
    if (!w || !h) return;
    this.renderer.setSize(w, h, false);
    this.composer.setSize(w, h);
    this.bloom.resolution.set(w, h);
    this.camera.aspect = w / h;
    this.camera.position.z = w / h < 0.9 ? 10.5 : 7.4;
    this.camera.updateProjectionMatrix();
    this.U.uPx.value = h * 0.0095 * Math.min(devicePixelRatio, 2);
  }
  start() {
    if (this.running) return;
    this.running = true;
    this.clock.getDelta();
    const loop = () => { if (!this.running) return; this._raf = requestAnimationFrame(loop); this.frame(); };
    loop();
  }
  stop() { this.running = false; cancelAnimationFrame(this._raf); }

  frame() {
    const dt = Math.min(0.05, this.clock.getDelta()), t = (this.U.uTime.value += dt);
    const U = this.U;
    const formRate = this.goal.form > U.uForm.value ? 0.55 : 0.8;   // assemble ~2s, dissolve faster
    U.uForm.value += Math.sign(this.goal.form - U.uForm.value) * Math.min(Math.abs(this.goal.form - U.uForm.value), dt * formRate);
    U.uThink.value += (this.goal.think - U.uThink.value) * Math.min(1, dt * 3);
    U.uAmp.value += (this.amp - U.uAmp.value) * Math.min(1, dt * (this.amp > U.uAmp.value ? 28 : 12)); // fast attack, softer release
    U.uListen.value += (this.listen - U.uListen.value) * Math.min(1, dt * 8);
    U.uScan.value = ((t * 1.1) % 10) - 4.5;
    // idle life: slow sway, glance toward the cursor, nod a little when talking
    const g = this.group;
    g.rotation.y += ((Math.sin(t * 0.33) * 0.16 + this.mouse.x * 0.45) - g.rotation.y) * Math.min(1, dt * 2);
    g.rotation.x += ((Math.sin(t * 0.27) * 0.04 + this.mouse.y * 0.18 - U.uAmp.value * 0.03) - g.rotation.x) * Math.min(1, dt * 2);
    g.position.y = Math.sin(t * 0.8) * 0.02;
    this.composer.render();
  }

  dispose() { this.stop(); this._ro.disconnect(); this.renderer.dispose(); }
}
