// Talks to the Python model in its worker. Requests queue up; each can report progress.
let worker = null;
let nextId = 1;
const pending = new Map();

function start() {
  if (worker) return;
  worker = new Worker(new URL('./worker.js', import.meta.url), { type: 'module' });
  worker.onmessage = (e) => {
    const msg = e.data;
    const p = pending.get(msg.id);
    if (!p) return;
    if ('progress' in msg && !('ok' in msg)) {
      p.onProgress?.(msg.progress);
      return;
    }
    pending.delete(msg.id);
    if (msg.ok) p.resolve(msg);
    else p.reject(new Error(msg.error || 'Something went wrong in the model.'));
  };
  worker.onerror = () => {
    for (const p of pending.values()) p.reject(new Error('The model could not start in this browser.'));
    pending.clear();
  };
}

/** Sends one request ({ op, plan, settings, ... }) to the model. */
export function call(request, onProgress) {
  start();
  const id = nextId++;
  return new Promise((resolve, reject) => {
    pending.set(id, { resolve, reject, onProgress });
    worker.postMessage({ id, request: JSON.stringify(request) });
  });
}

/** Starts Python loading early, so the first real request is quicker. */
export function warm() {
  start();
}
