// 3D US Treasury yield-curve surface: maturity × time × yield.
import * as THREE from "three";

function label(text, color = "#a3abba", size = 42) {
  const c = document.createElement("canvas"); c.width = 256; c.height = 64;
  const g = c.getContext("2d");
  g.font = `700 ${size}px JetBrains Mono, monospace`; g.fillStyle = color; g.textAlign = "center"; g.textBaseline = "middle";
  g.fillText(text, 128, 32);
  const sp = new THREE.Sprite(new THREE.SpriteMaterial({ map: new THREE.CanvasTexture(c), transparent: true, depthWrite: false }));
  sp.scale.set(0.5, 0.125, 1);
  return sp;
}

export class CurveSurface {
  constructor(canvas) {
    this.canvas = canvas;
    this.renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.scene = new THREE.Scene();
    this.camera = new THREE.PerspectiveCamera(36, 1, 0.1, 50);
    this.group = new THREE.Group();
    this.scene.add(this.group);
    this.scene.add(new THREE.AmbientLight(0xffffff, 0.35));
    const dl = new THREE.DirectionalLight(0xfff1d6, 1.4); dl.position.set(2, 4, 3); this.scene.add(dl);
    const dl2 = new THREE.DirectionalLight(0x7fe3ff, 0.6); dl2.position.set(-3, 2, -2); this.scene.add(dl2);
    this.rot = { x: 0.55, y: -0.7, vy: 0.0015 };
    let drag = false, lx = 0, ly = 0;
    canvas.addEventListener("pointerdown", (e) => { drag = true; lx = e.clientX; ly = e.clientY; canvas.setPointerCapture(e.pointerId); });
    canvas.addEventListener("pointerup", () => (drag = false));
    canvas.addEventListener("pointermove", (e) => {
      if (!drag) return;
      this.rot.y += (e.clientX - lx) * 0.008; this.rot.x = Math.max(0.1, Math.min(1.3, this.rot.x + (e.clientY - ly) * 0.006));
      lx = e.clientX; ly = e.clientY; this.rot.vy = 0;
    });
    this._ro = new ResizeObserver(() => this.resize()); this._ro.observe(canvas);
    this.resize();
  }

  setData({ tenors, rows }) {
    this.group.clear();
    if (!rows || rows.length < 5) return;
    const codes = tenors.map((t) => t.code).filter((c) => rows[rows.length - 1][c] != null);
    const nx = codes.length, nz = rows.length;
    let lo = Infinity, hi = -Infinity;
    rows.forEach((r) => codes.forEach((c) => { if (r[c] != null) { lo = Math.min(lo, r[c]); hi = Math.max(hi, r[c]); } }));
    const W = 2.4, D = 2.0, H = 1.0;
    const X = (i) => (i / (nx - 1) - 0.5) * W, Z = (j) => (j / (nz - 1) - 0.5) * D, Y = (v) => ((v - lo) / (hi - lo || 1)) * H;
    const geo = new THREE.PlaneGeometry(1, 1, nx - 1, nz - 1);
    const pos = geo.attributes.position, colors = [];
    const cLo = new THREE.Color(0x163a5c), cMid = new THREE.Color(0x7fe3ff), cHi = new THREE.Color(0xf4ddaa), cTop = new THREE.Color(0xff5773);
    for (let j = 0; j < nz; j++) for (let i = 0; i < nx; i++) {
      const k = j * nx + i;
      let v = rows[j][codes[i]];
      if (v == null) v = rows[Math.max(0, j - 1)][codes[i]] ?? lo;
      pos.setXYZ(k, X(i), Y(v), Z(j));
      const t = (v - lo) / (hi - lo || 1);
      const c = t < 0.4 ? cLo.clone().lerp(cMid, t / 0.4) : t < 0.8 ? cMid.clone().lerp(cHi, (t - 0.4) / 0.4) : cHi.clone().lerp(cTop, (t - 0.8) / 0.2);
      colors.push(c.r, c.g, c.b);
    }
    geo.setAttribute("color", new THREE.Float32BufferAttribute(colors, 3));
    geo.computeVertexNormals();
    this.group.add(new THREE.Mesh(geo, new THREE.MeshStandardMaterial({ vertexColors: true, side: THREE.DoubleSide, roughness: 0.45, metalness: 0.25, transparent: true, opacity: 0.92 })));
    this.group.add(new THREE.LineSegments(new THREE.WireframeGeometry(geo), new THREE.LineBasicMaterial({ color: 0xffffff, transparent: true, opacity: 0.07 })));
    // today's curve highlighted
    const today = codes.map((c, i) => new THREE.Vector3(X(i), Y(rows[nz - 1][c]) + 0.01, Z(nz - 1)));
    this.group.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(today), new THREE.LineBasicMaterial({ color: 0xf4ddaa })));
    // floor grid + labels
    const grid = new THREE.GridHelper(2.6, 13, 0x2a3140, 0x161b24); grid.position.y = -0.01; this.group.add(grid);
    codes.forEach((c, i) => { if (i % 2 === 0 || i === nx - 1) { const l = label(c); l.position.set(X(i), -0.08, D / 2 + 0.16); this.group.add(l); } });
    const l1 = label(rows[0].d.slice(2), "#626b7c", 34); l1.position.set(W / 2 + 0.35, -0.05, -D / 2); this.group.add(l1);
    const l2 = label("TODAY", "#d9b56d", 34); l2.position.set(W / 2 + 0.35, -0.05, D / 2); this.group.add(l2);
    const lh = label(`${hi.toFixed(2)}%`, "#f4ddaa", 36); lh.position.set(-W / 2 - 0.3, H, -D / 2); this.group.add(lh);
    const ll = label(`${lo.toFixed(2)}%`, "#7fe3ff", 36); ll.position.set(-W / 2 - 0.3, 0, -D / 2); this.group.add(ll);
    this.group.position.y = -0.35;
  }

  resize() {
    const w = this.canvas.clientWidth, h = this.canvas.clientHeight;
    if (!w || !h) return;
    this.renderer.setSize(w, h, false);
    this.camera.aspect = w / h; this.camera.updateProjectionMatrix();
  }
  start() {
    if (this.running) return; this.running = true;
    const loop = () => {
      if (!this.running) return;
      this._raf = requestAnimationFrame(loop);
      this.rot.y += this.rot.vy;
      const r = 4.1;
      this.camera.position.set(Math.sin(this.rot.y) * Math.cos(this.rot.x) * r, Math.sin(this.rot.x) * r, Math.cos(this.rot.y) * Math.cos(this.rot.x) * r);
      this.camera.lookAt(0, 0, 0);
      this.renderer.render(this.scene, this.camera);
    };
    loop();
  }
  stop() { this.running = false; cancelAnimationFrame(this._raf); }
}
