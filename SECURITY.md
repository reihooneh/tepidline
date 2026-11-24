# Security

Please report a security problem privately to Reihaneh Rahmati (reihaneh26686@gmail.com) rather
than in a public issue. I'll reply within a week.

## Threat model

Tepidline is a static site. Its only input is a building plan (JSON) the visitor chooses, read in
their own browser, and its own settings. There is no server, account or database.

| An attacker could try | What stops it |
|---|---|
| A plan with HTML or script in a name, to run code in the page (XSS) | Nothing from a plan is ever inserted as markup: the page builds every element with `textContent` and SVG attributes set by DOM calls. A strict CSP (`default-src 'none'`, scripts only from the site, no inline code) would block injected script anyway. A browser test loads a plan named `<img src=x onerror=…>` and checks no image appears. |
| A plan that makes Python do something it shouldn't | The plan is parsed with `json.loads`, never `eval` or `pickle`. Python runs in Pyodide, inside the browser's WebAssembly sandbox, in a Web Worker with no access to the page; it has no network or file access beyond its own in-memory files. |
| A plan that hangs or exhausts the browser (denial of service) | Hard limits checked before anything runs: 2 MB of JSON, 200 pipes, 60 outlets, 40 uses per outlet, 50 corners per pipe, 20 tempering valves, 60 rooms, every number finite and within a physical range (lengths 0.1 to 200 m, coordinates within 500 m, uses up to 60 minutes). Pipe loops are refused before simulation. A week's simulation is bounded by those limits, and each pipe holds at most 10 parcels. The largest allowed plan runs in seconds. |
| Deeply nested JSON to crash the parser | Python's recursion limit in the worker is lowered to 400 and a `RecursionError` becomes a plain "couldn't be read" message (tested with 5,000 nested brackets). |
| Tampering with what the check page hands to the fix page | The hand-off lives in this tab's `sessionStorage` and is re-validated on read: only the two example names or an object, and only the known season, roof and scenario values. Anything else is ignored. |
| Supply-chain attacks through dependencies | No runtime dependencies in the Python package. The site self-hosts exact, pinned versions of Pyodide 0.29.4, three.js 0.170.0 and two fonts, copied from the npm lockfile at build time; no CDN, analytics or third-party requests (a browser test fails on any request leaving the site). `npm audit`, `ruff` (including the `S` security rules), `bandit` and `mypy --strict` run in CI. |
| Running the command line on a hostile file | The CLI reads only regular files under 2 MB, through the same validation as the browser. |

## Known limits

- Tepidline screens building designs for warm, stagnant water. It does not measure bacteria and
  must not be used in place of water testing or a water management plan.
- GitHub Pages sets the HTTPS and caching headers; the CSP is delivered as a `<meta>` tag, so
  `frame-ancestors` can't be set and the site could be framed by another page (it has no
  sensitive actions to click-jack).
