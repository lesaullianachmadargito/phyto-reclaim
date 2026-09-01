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
