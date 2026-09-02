# PHYTO-RECLAIM — model, figures and bench rig

Everything here derives from the Stage 2 paper. Nothing is retyped: the numbers
are computed, so if an assumption changes the outputs change with it.

| File | What it is |
|---|---|
| `phyto_model.py` | The calculation engine. No user interface, so it can be audited on its own. |
| `app.py` | Presentation dashboard. This is the thing you drive on stage. |
| `figure5.py` | Rebuilds Figure 5, which is missing from the submitted PDF. 300 dpi, ready for Word. |
| `pbr_dynamic.py` | Dynamic photobioreactor simulation. Proves the Module III stage-gating claim. |
| `rig/` | ESP32 + Node-RED bench rig. See `rig/RIG.md`. |
| `viz3d/` | 3D model of the reference unit, generated in Blender from the paper's dimensions. |

---

## How to run

Always go through `python -m`. Do not call `pip` or `streamlit` directly — the
PATH on this laptop still points at an old Python installation that was deleted,
so the launcher stubs are broken.

**1. Prove the model is right** (run this once, first):

    python phyto_model.py

You should see `ALL MATCH`. That means the model reproduces all ten scenarios of
Table 14 — net benefit, NPV and IRR — to within IDR 1 million.

**2. Rebuild Figure 5:**

    python figure5.py

Outputs `figure5.png` (300 dpi, for Word) and `figure5.pdf` (vector, for
enlarging without pixelation).

**3. Run the dashboard:**

    python -m streamlit run app.py

Open `http://localhost:8501`. Press `Ctrl+C` in the terminal to stop it.

**4. Run the dynamic PBR simulation:**

    python pbr_dynamic.py

Takes about a minute. Outputs `pbr_dynamic.png` plus three blocks of numbers in
the terminal.

**5. Bench rig:** see `rig/RIG.md`. It can be built today using the simulator,
without waiting for sensors to arrive.

---

## Using the dashboard on stage

The sidebar has six **one-click scenarios**. Use those, not the sliders — you
cannot drag six sliders while talking.

Open the **Sensitivity & validation** tab first and leave it up for a moment.
That establishes credibility: the model is the paper, not a separate
calculation.

Then, when a judge asks *"what if the productivity is not achieved?"* — do not
answer with a sentence. Click **Productivity 50% short** and let them watch NPV
fall to −812 million and the gate banner turn red. That is a demonstration, not
a claim, and it is what the 20% evidence criterion asks for.

Run it locally. Do not depend on venue internet.

---

## Two things that must not be got wrong

### Call the tools what they are

`app.py` is a **parameterised process and economic model**. `pbr_dynamic.py` is
a **screening simulation**. Neither is a *digital twin*.

A digital twin is synchronised with a physical asset through live data. There is
no physical asset and no field data in either script. The judges from Pertamina
Hulu Energi know the difference, and misusing the term would breach exactly the
bounded-claim architecture that is the paper's main strength.

Only the bench rig in `rig/` earns the phrase — and then only as a
**bench-scale digital twin**.

### The dynamic model's finding about 1.5 g/L/day

`pbr_dynamic.py` solves backwards for the growth rate the design figure demands:

- reaching **1.5 g/L/day requires mu_max ≈ 2.40/day**
- even the Phase 1 gate of **1.125 g/L/day requires mu_max ≈ 2.04/day**
- the published Chlorella range is typically **1.2–2.0/day** under optimal
  conditions

This *supports* the "upper design case" caveat the paper already states, and
gives it a physics-based reason instead of mere caution. But it must never be
presented as "our simulation proves 1.5 is achievable" — it shows the opposite.
If in doubt, use it only to answer a question, do not raise it yourself.

---

## Technical notes

- NPV is computed by explicit summation, not `numpy_financial.npv`, because that
  function treats the first element as year 0 with no discount. The first
  benefit only arrives at the end of year 1. Used naively it overstates NPV by
  IDR 321 million and the figures stop matching the paper.
- The CAPEX and OPEX sliders deliberately carry decimals (2,054.4 and 327.3).
  Rounded to 2,054 and 327 the NPV comes out at 1,153 instead of 1,150.
- Figure 5 panel (b) shows a **discounted breakeven of 5.3 years**, while the
  paper quotes a **simple payback of 3.0–3.9 years**. Both are correct and
  different: simple payback ignores discounting. Have that answer ready if a
  judge compares the two.
- Charts and figures are drawn without gridlines. Values are labelled directly
  instead, so nothing on screen is decoration.

---

## 3D model of the reference unit

`viz3d/build_3d.py` builds the whole plant in Blender **procedurally, from the
dimensions in the paper**, then renders it. Nothing is modelled by hand, so the
model is dimensionally faithful rather than an artist's impression — it answers
"does this actually fit on 725 m2", which is the first thing an operator asks.

    blender --background --python build_3d.py     # or the full path to blender.exe
    python annotate_3d.py

Add `-- --no-render` to rebuild the model without waiting on the renders.

### Opening it in Blender

The build also writes `viz3d/phyto_reclaim.blend` (2.7 MB). Just double-click
it, or File -> Open. Everything is already set up:

- **Units are metres.** Blender's measure tool (press N, Item tab, or the ruler
  in the toolbar) reports real dimensions, so you can check any distance live if
  a judge asks.
- **Four named cameras**: `aerial`, `plan`, `ground`, `process`. Numpad 0 looks
  through the active one. To switch, click a camera in the outliner, then
  Ctrl+Numpad 0.
- **Objects are grouped into collections**: Site, Wetland Tier 1, Wetland Tier 2,
  Process equipment, Piping, Planting, Cameras and lights. Click the eye icon in
  the outliner to hide Planting if you want to see the basins and pipework
  underneath.
- Orbit with middle mouse, pan with Shift + middle mouse, zoom with the wheel.

To change a dimension, edit the constants at the top of `build_3d.py` and re-run
the build - do not move geometry by hand, or the model stops matching the paper.

Outputs land in `viz3d/renders/`:

| File | View |
|---|---|
| `aerial_labelled.png` | Three-quarter view with leader-line callouts. Use this one. |
| `aerial.png` | The same view, unlabelled. |
| `plan.png` | Orthographic top-down plan. |
| `process.png` | Close view of the 150 m2 process area. |
| `ground.png` | Eye level, from the access road. |

The layout resolves to exactly 725.0 m2: a 7.77 m process strip, then Tier 1 at
17.88 m wide (345 m2), then Tier 2 at 11.92 m wide (230 m2), all 19.3 m deep.
Change a number in the dimensions block and the geometry follows.

### Two things it deliberately gets right

**No open water.** The paper specifies a subsurface-flow wetland, so the water
table sits inside the 0.60 m media bed and the visible surface is gravel.
Drawing open water would depict a free-water-surface wetland — a different
design with a different footprint and its own odour and mosquito problems. A
judge who knows constructed wetlands would spot that immediately.

**It is a visualisation, not a twin.** The model is not connected to anything and
carries no live state. It shows what the unit would look like at the sizes
claimed. Same naming discipline as everywhere else in this repo.

---

## Sharing the dashboard — QR codes and links

`make_qr.py` builds a labelled QR for any URL:

    python make_qr.py                                 # this laptop's LAN address
    python make_qr.py https://your-app.streamlit.app  # a real public URL

### Three options, and what each actually does

**1. LAN address (`http://192.168.x.x:8501`) — same room only.**
This is a private address. It resolves only on the same WiFi as this laptop,
the laptop must be running the app at that moment, DHCP can hand out a
different number next time you connect, and many venue networks block
device-to-device traffic outright. Fine as a same-room fallback. Useless as a
permanent link, and never print it on a poster.

**2. Streamlit Community Cloud — the real answer for "anywhere".**
Free, public HTTPS URL, permanent, and it keeps running when your laptop is
closed. `requirements.txt` in this folder is already correct for it.

  1. Push this folder to a GitHub repository.
  2. Go to share.streamlit.io and sign in with GitHub.
  3. New app -> pick the repo -> main file `app.py` -> Deploy.
  4. You get something like `https://phyto-reclaim.streamlit.app`.
  5. Re-run `python make_qr.py <that URL>` and print that QR instead.

**3. Tunnel (ngrok, cloudflared) — middle ground.**
Gives a public URL that forwards to your laptop. Still needs your laptop
running and online, and on the free tier the URL changes every restart. Useful
for a quick share, not for a printed poster.

### Do not use a QR for the live demo

Whichever option you choose, drive the demo from `localhost` on your own screen.
A QR asks the judges to depend on venue WiFi at the exact moment you need
everything to work. Use the QR afterwards, so they can revisit it — that is
what it is good for.

### One thing to check before you publish

The competition rules require submitted work to be original and unpublished. A
publicly reachable dashboard is almost certainly not "publication" in the sense
the rules mean, but it is your call to make, not an assumption to drift into.
If in doubt, keep it local until after judging, or ask the committee at
sic.spejava@gmail.com.
