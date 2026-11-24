// Runs the Tepidline Python package in Pyodide, off the main thread. Messages in: { id, request }
// where request is JSON text for tepidline.api.call; out: { id, progress } while it works, then
// { id, ok, ... } with the result. Pyodide and the package are served from this site.
import { loadPyodide } from '../pyodide/pyodide.mjs';
import { PY_FILES } from './data/pyfiles.js';

let api = null;

async function load() {
  const py = await loadPyodide({
    indexURL: new URL('../pyodide/', import.meta.url).href,
    packages: [],
    stdout: () => {},
    stderr: () => {},
  });
  py.FS.mkdirTree('/home/pyodide/tepidline');
  for (const name of PY_FILES) {
    const r = await fetch(new URL(`../py/tepidline/${name}`, import.meta.url));
    if (!r.ok) throw new Error('missing model file');
    py.FS.writeFile(`/home/pyodide/tepidline/${name}`, await r.text());
  }
  py.runPython('import sys\nsys.path.insert(0, "/home/pyodide")\nsys.setrecursionlimit(400)');
  api = py.pyimport('tepidline.api');
}
const ready = load();

onmessage = async (e) => {
  const { id, request } = e.data || {};
  try {
    await ready;
  } catch {
    postMessage({ id, ok: false, error: 'Python could not start in this browser.' });
    return;
  }
  if (typeof request !== 'string') {
    postMessage({ id, ok: false, error: 'bad request' });
    return;
  }
  let last = 0;
  const progress = (i, n) => {
    const now = Date.now();
    if (now - last > 120 || i === n) {
      last = now;
      postMessage({ id, progress: i / n });
    }
  };
  try {
    const text = api.call(request, progress);
    postMessage({ id, ...JSON.parse(text) });
  } catch {
    postMessage({ id, ok: false, error: 'The model stopped unexpectedly.' });
  }
};
