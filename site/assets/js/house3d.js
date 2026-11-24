// The building in 3D: walls and ceiling see-through, the roof tinted by the air in the roof space,
// and every pipe coloured along its length by the temperature of the water standing in it, through
// a day. Drag to turn. three.js is self-hosted.
import * as THREE from '../vendor/three.module.min.js';
import { tempRGB, reducedMotion } from './common.js';

export function hasWebGL() {
  try {
    const c = document.createElement('canvas');
    return !!(c.getContext('webgl2') || c.getContext('webgl'));
  } catch {
    return false;
  }
}

const DAY = 86400;

export function createHouse(container, { onTime } = {}) {
  const renderer = new THREE.WebGLRenderer({ antialias: true });
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.outputColorSpace = THREE.SRGBColorSpace;
  container.prepend(renderer.domElement);
  renderer.domElement.setAttribute('aria-hidden', 'true');
  renderer.domElement.style.touchAction = 'pan-y';
  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(38, 1, 0.1, 400);
  const hemi = new THREE.HemisphereLight(0xdfeff2, 0x1a2629, 1.4);
  scene.add(hemi);
  const sun = new THREE.DirectionalLight(0xfff1dd, 1.2);
  scene.add(sun);
  const world = new THREE.Group();
  scene.add(world);

  let pipes = [];
  let roofMats = [];
  let data = null, time = 8 * 3600, playing = !reducedMotion(), raf = 0, last = 0;
  let theta = 0.7, phi = 0.62, dist = 30, centre = new THREE.Vector3();
  let dragging = null;

  function clear() {
    for (const obj of [...world.children]) {
      world.remove(obj);
      obj.traverse((o) => {
        o.geometry?.dispose();
        if (o.material) (Array.isArray(o.material) ? o.material : [o.material]).forEach((m) => m.dispose());
      });
    }
    pipes = [];
    roofMats = [];
  }

  function build(building) {
    clear();
    const [sx, sz, wallH] = building.size;
    centre = new THREE.Vector3(sx / 2, 1.0, sz / 2);
    dist = Math.max(sx, sz) * 1.45 + 6;
    const ground = new THREE.Mesh(new THREE.CircleGeometry(Math.max(sx, sz) * 1.6, 64), new THREE.MeshStandardMaterial({ color: 0x18241f, roughness: 1 }));
    ground.rotation.x = -Math.PI / 2;
    ground.position.set(sx / 2, -0.62, sz / 2);
    world.add(ground);
    const floor = new THREE.Mesh(new THREE.BoxGeometry(sx, 0.06, sz), new THREE.MeshStandardMaterial({ color: 0x9aa7a6, transparent: true, opacity: 0.16, depthWrite: false }));
    floor.position.set(sx / 2, -0.03, sz / 2);
    world.add(floor);
    const wallMat = new THREE.MeshStandardMaterial({ color: 0xd8e2e0, transparent: true, opacity: 0.07, side: THREE.DoubleSide, depthWrite: false });
    const edgeMat = new THREE.LineBasicMaterial({ color: 0x5d7276, transparent: true, opacity: 0.55 });
    for (const r of building.rooms) {
      const [a, b, c, d] = r.box;
      const w = Math.abs(c - a), dd = Math.abs(d - b);
      const box = new THREE.BoxGeometry(w, wallH, dd);
      const mesh = new THREE.Mesh(box, wallMat);
      mesh.position.set((a + c) / 2, wallH / 2, (b + d) / 2);
      world.add(mesh);
      const edges = new THREE.LineSegments(new THREE.EdgesGeometry(box), edgeMat);
      edges.position.copy(mesh.position);
      world.add(edges);
    }
    // A gable roof along the longer side, tinted by the roof-space air.
    const ridgeAlongX = sx >= sz;
    const o = 0.5; // eave overhang
    const rise = (ridgeAlongX ? sz : sx) * 0.22;
    const y0 = wallH, y1 = wallH + rise;
    const P = ridgeAlongX
      ? { a: [-o, y0, -o], b: [sx + o, y0, -o], c: [sx + o, y1, sz / 2], d: [-o, y1, sz / 2], e: [sx + o, y0, sz + o], f: [-o, y0, sz + o] }
      : { a: [-o, y0, -o], b: [-o, y0, sz + o], c: [sx / 2, y1, sz + o], d: [sx / 2, y1, -o], e: [sx + o, y0, sz + o], f: [sx + o, y0, -o] };
    const faces = [[P.a, P.b, P.c, P.d], [P.d, P.c, P.e, P.f]];
    for (const q of faces) {
      const geo = new THREE.BufferGeometry();
      geo.setAttribute('position', new THREE.Float32BufferAttribute([...q[0], ...q[1], ...q[2], ...q[0], ...q[2], ...q[3]], 3));
      geo.computeVertexNormals();
      const mat = new THREE.MeshStandardMaterial({ color: 0x4a5558, transparent: true, opacity: 0.2, side: THREE.DoubleSide, depthWrite: false });
      roofMats.push(mat);
      world.add(new THREE.Mesh(geo, mat));
      const outline = new THREE.LineLoop(new THREE.BufferGeometry().setFromPoints(q.map((v) => new THREE.Vector3(...v))), edgeMat);
      world.add(outline);
    }
    // Heater, meter and tempering valves.
    const heater = new THREE.Mesh(new THREE.CylinderGeometry(0.32, 0.32, 1.5, 24), new THREE.MeshStandardMaterial({ color: 0xc8cfd0, roughness: 0.4, metalness: 0.3 }));
    heater.position.set(building.heater[0], 0.75, building.heater[2]);
    world.add(heater);
    const meter = new THREE.Mesh(new THREE.BoxGeometry(0.3, 0.3, 0.3), new THREE.MeshStandardMaterial({ color: 0x3b7fc4 }));
    meter.position.set(building.meter[0], 0.15, building.meter[2]);
    world.add(meter);
    for (const t of building.tmvs) {
      const v = new THREE.Mesh(new THREE.SphereGeometry(0.13, 16, 12), new THREE.MeshStandardMaterial({ color: 0x7fd6e8, emissive: 0x15434c }));
      v.position.set(...t.at);
      world.add(v);
    }
    for (const o of Object.values(building.outlets)) {
      const head = new THREE.Mesh(new THREE.SphereGeometry(o.kind === 'shower' ? 0.14 : 0.1, 16, 12), new THREE.MeshStandardMaterial({ color: 0xeaf2f1, roughness: 0.3, metalness: 0.5 }));
      head.position.set(o.at[0], o.at[1] + (o.kind === 'shower' ? 0.9 : 0), o.at[2]);
      world.add(head);
    }
    // Pipes, with colours we can change per vertex along their length.
    const lagMat = new THREE.MeshStandardMaterial({ color: 0x7c8a8d, transparent: true, opacity: 0.25, depthWrite: false });
    for (const [pid, p] of Object.entries(building.pipes)) {
      const path = new THREE.CurvePath();
      for (let i = 0; i < p.points.length - 1; i++) {
        const a = new THREE.Vector3(...p.points[i]), b = new THREE.Vector3(...p.points[i + 1]);
        if (a.distanceTo(b) > 1e-4) path.add(new THREE.LineCurve3(a, b));
      }
      if (!path.curves.length) continue;
      const radius = p.dn >= 20 ? 0.06 : 0.045;
      const segs = Math.max(4, Math.min(48, Math.round(p.length * 4)));
      const geo = new THREE.TubeGeometry(path, segs, radius, 6, false);
      const count = geo.attributes.position.count;
      const colors = new Float32Array(count * 3);
      geo.setAttribute('color', new THREE.BufferAttribute(colors, 3));
      const mat = new THREE.MeshStandardMaterial({ vertexColors: true, roughness: 0.45, metalness: 0.25, emissive: 0x111111 });
      const mesh = new THREE.Mesh(geo, mat);
      world.add(mesh);
      // TubeGeometry lays out (segs + 1) rings of (radial + 1) vertices: ring i sits at u = i / segs.
      const ring = count / (segs + 1);
      pipes.push({ pid, geo, colors, segs, ring });
      if (p.insulation > 0) {
        const lag = new THREE.Mesh(new THREE.TubeGeometry(path, segs, radius * 2.1, 8, false), lagMat);
        world.add(lag);
      }
    }
    place();
  }

  const tmp = new THREE.Color();
  function colourAt(s) {
    if (!data) return;
    const snap = data.snapshots;
    const ts = snap.t;
    // ticks run from the first sample to the end of the day; before the first, use the last (yesterday's midnight)
    let i = 0;
    while (i < ts.length - 1 && ts[i + 1] <= s) i++;
    let a = i, b = Math.min(i + 1, ts.length - 1), f = 0;
    if (s < ts[0]) {
      a = ts.length - 1; b = 0; f = s / ts[0];
    } else if (b !== a) {
      f = (s - ts[a]) / (ts[b] - ts[a]);
    }
    for (const p of pipes) {
      const A = snap.pipes[p.pid][a], B = snap.pipes[p.pid][b];
      if (!A || !B) continue;
      const n = A.length;
      for (let k = 0; k <= p.segs; k++) {
        const x = (k / p.segs) * n - 0.5;
        const j = Math.max(0, Math.min(n - 1, Math.floor(x)));
        const j2 = Math.min(n - 1, j + 1);
        const g = Math.max(0, Math.min(1, x - j));
        const ta = A[j] + (A[j2] - A[j]) * g, tb = B[j] + (B[j2] - B[j]) * g;
        const [r, gg, bb] = tempRGB(ta + (tb - ta) * f);
        tmp.setRGB(r / 255, gg / 255, bb / 255, THREE.SRGBColorSpace);
        for (let v = 0; v < p.ring; v++) {
          const idx = (k * p.ring + v) * 3;
          p.colors[idx] = tmp.r; p.colors[idx + 1] = tmp.g; p.colors[idx + 2] = tmp.b;
        }
      }
      p.geo.attributes.color.needsUpdate = true;
    }
    const air = snap.air.roof;
    const roofT = air[a] + (air[b] - air[a]) * f;
    const [r, g, bb] = tempRGB(roofT);
    for (const m of roofMats) {
      m.color.setRGB(r / 255, g / 255, bb / 255, THREE.SRGBColorSpace);
      m.opacity = 0.12 + Math.max(0, Math.min(1, (roofT - 22) / 25)) * 0.22;
    }
    const h = s / 3600;
    const day = Math.max(0, Math.sin(Math.PI * (h - 6) / 13));
    sun.intensity = 0.25 + 1.2 * day;
    sun.position.set(centre.x + Math.cos(Math.PI * (h - 6) / 13) * 40, 5 + day * 35, centre.z - 15);
    hemi.intensity = 0.8 + 0.8 * day;
    renderer.setClearColor(new THREE.Color().setRGB(0.04 + 0.08 * day, 0.06 + 0.1 * day, 0.07 + 0.12 * day, THREE.SRGBColorSpace));
    onTime?.(s, roofT);
  }

  function place() {
    camera.position.set(centre.x + Math.sin(theta) * Math.cos(phi) * dist, centre.y + Math.sin(phi) * dist, centre.z + Math.cos(theta) * Math.cos(phi) * dist);
    camera.lookAt(centre);
  }
  const canvas = renderer.domElement;
  canvas.addEventListener('pointerdown', (e) => { dragging = { x: e.clientX, y: e.clientY, theta, phi, id: e.pointerId }; });
  canvas.addEventListener('pointermove', (e) => {
    if (!dragging || e.pointerId !== dragging.id) return;
    theta = dragging.theta - (e.clientX - dragging.x) * 0.006;
    phi = Math.max(0.15, Math.min(1.35, dragging.phi + (e.clientY - dragging.y) * 0.004));
    place();
    kick();
  });
  const end = () => { dragging = null; };
  canvas.addEventListener('pointerup', end);
  canvas.addEventListener('pointercancel', end);
  canvas.addEventListener('pointerleave', end);

  function resize() {
    const w = container.clientWidth, h = container.clientHeight;
    if (!w || !h) return;
    renderer.setSize(w, h, false);
    camera.aspect = w / h;
    camera.updateProjectionMatrix();
    kick();
  }
  new ResizeObserver(resize).observe(container);
  let visible = true;
  new IntersectionObserver((entries) => {
    visible = entries[0].isIntersecting;
    if (visible) kick();
  }).observe(container);

  function frame(now) {
    raf = 0;
    const dt = last ? Math.min(0.05, (now - last) / 1000) : 0;
    last = now;
    if (data && playing) {
      time = (time + dt * DAY / 30) % DAY; // a day in 30 seconds
      colourAt(time);
      if (!dragging) {
        theta += dt * 0.04;
        place();
      }
    }
    renderer.render(scene, camera);
    if (visible && playing) raf = requestAnimationFrame(frame);
    else last = 0;
  }
  function kick() {
    if (!raf) raf = requestAnimationFrame(frame);
  }
  resize();
  return {
    set(building, result) {
      data = result;
      build(building);
      colourAt(time);
      kick();
    },
    setTime(s) {
      time = s;
      colourAt(s);
      kick();
    },
    play(on) {
      playing = on && !reducedMotion();
      kick();
      return playing;
    },
    get playing() { return playing; },
    get time() { return time; },
  };
}
