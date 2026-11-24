# How Tepidline works

## The question

Not "is there Legionella in this building?" (only a lab can say) but "where does this building's
design and use leave water sitting between 25 and 45 °C for hours, which taps deliver that water,
and what would fix it?" Those are the conditions guidelines warn about, and they can be worked out
from a plan.

## Architecture

```
tepidline/
  physics.py   per-metre pipe properties, the exact warm-hour integral, heat inactivation
  climate.py   air temperature around each pipe through a Sydney summer or winter day
  model.py     reading and checking a plan; labelling every pipe hot, cold or tempered
  sim.py       the week: plug flow of water parcels, mixing valves, standing-water updates
  fixes.py     candidate fixes from the plan, every allowed combination, the cost frontier
  api.py       JSON in, JSON out, for the command line and the web worker
  verify.py    checks against exact answers and a finer model (shown on the method page)
  examples.py  a Sydney family house and an aged-care wing
site/assets/js/
  worker.js    starts Pyodide, writes the package into its file system, answers requests
  engine.js    the page side of the worker: queued requests with progress
  house3d.js   three.js: see-through house, pipes coloured along their length through the day
  planview.js  the plan from above, pipes coloured by warm hours
  check.js, fix.js, home.js, method.js   the four pages
scripts/       build (pages, generated data, vendored files), local server, screenshots
tests/         pytest for the core; Playwright for the site
```

## Key ideas, simply

**1. Water as a queue of parcels.** Each pipe holds a list of parcels from its upstream end to its
downstream end. A parcel has a volume, a temperature, its warm seconds, its heat treatment and its
age. When a tap runs for one step, the volume it draws comes off the end of its pipe; that pipe asks
whatever feeds it (another pipe, the heater, the mains, or a tempering valve) for the same volume,
and so on up the tree. That's exact plug flow: no water is created or lost, and a test checks that
every pipe still holds exactly its volume after a week.

**2. Valves and people mix.** A tempering valve, or a person at a mixer tap, picks the share of hot
water that brings the mix to a target temperature. Tepidline looks at what each side is *about to
deliver* (which may be a slug of cold water still in the hot pipe) and solves for the share, so the
valve behaves thermostatically.

**3. Standing water, in closed form.** Between events the water and the pipe wall share one
temperature that relaxes exponentially towards the air around the pipe, with a time constant of
heat capacity over heat loss (26 minutes for bare 15 mm copper, 51 with lagging). A check against a
finer model, with the lagging split into 12 layers that store heat, agrees within 1 °C.

**4. Warm hours, exactly.** A parcel's warm hours are the integral of a weight over time: 0 outside
25 to 45 °C, 1 across the middle, ramping at the edges. Because the weight is piecewise linear in
temperature and the temperature is an exponential in time, the integral splits at the moments the
curve crosses each corner and each piece has a closed form. So whether a pipe is updated every
minute or every half hour, the answer is the same.

**5. Heat treatment.** Above 45 °C, parcels accumulate inactivation at rates measured by Sanden et
al. (1989), log-linear between 45, 50, 55 and 60 °C. After the equivalent of a hundredfold
reduction, a parcel's warm hours reset.

**6. Every combination of fixes.** Fixes are generated from the plan (only the ones that apply) and
grouped where they're alternatives for the same pipes or room. The planner simulates every allowed
combination (144 for the example house) and keeps the cost frontier: each point beats every cheaper
set. Exhaustive search is affordable because one week takes about 0.15 s natively.

**7. One codebase, two places.** The pages run the same Python package inside Pyodide in a Web
Worker. The build also runs it natively to precompute the examples, so the first view is instant
and a browser test checks the live result matches the build character for character.

## Trade-offs

- **Lumped pipes.** One temperature per parcel, with no heat lost while water moves and no exchange
  between pipes laid together. Cheap, exact in time, and good to about a degree for standing water.
- **A screening metric, not a growth model.** "Warm water" is water that sat over 4 warm hours, and
  showers count most because they make droplets people breathe. It ranks taps and fixes well; it
  says nothing about bacteria counts.
- **Exhaustive search over smart search.** Simple to trust and test, and fast enough for the fixes
  a house or ward needs (tens to hundreds of combinations). A plan with dozens of independent fixes
  would need branch and bound.
- **Pyodide's size.** About 11 MB the first time the model runs, so the pages show precomputed
  results first and only load Python when you change something.

## Interview questions

**Why simulate parcels rather than solve the heat equation along each pipe?** Plug flow is what
happens in a small pipe during a draw, and between draws nothing moves. Parcels make both exact:
transport is bookkeeping and standing water is a closed-form exponential. A 1D advection-diffusion
grid would smear sharp fronts and need tiny time steps.

**How do you know the warm-hour integral is right?** Three ways: a property test against brute-force
numerical integration on hundreds of random curves, edge cases (held in the band, never reaching it,
starting above it), and the method page's check, which reports the largest difference.

**Why did lagging the roof pipes barely help?** Lagging slows heat flow but a lagged 15 mm pipe still
has a time constant under an hour, while the roof stays hot all afternoon. The water still reaches
roof temperature before the evening shower. Lagging can even make things worse for tempered pipes,
by keeping 50 °C water in the band longer. Getting the pipes out of the roof, or keeping them
short, is what works.

**What would you change to handle a hospital?** Recirculating hot water loops (a pump keeps water
moving, so the queue becomes a ring), flushing rosters as schedules, and per-ward occupancy. The
parcel model handles loops with one change: the loop's return feeds its own start.

**How is the site secured when it runs arbitrary user plans?** A plan is data, never code: JSON with
hard limits on size and every field, simulated in WebAssembly in a worker, and rendered with DOM
calls only. A strict CSP and a test that fails on any outside request back that up.

## Extensions

1. Recirculation loops and heat trace, the standard fixes in large buildings.
2. Calibrate each pipe's surroundings from a few logged tap temperatures.
3. A browser editor that lets you draw a plan over a floor plan image.
