# -*- coding: utf-8 -*-
"""Dynamic simulation of the PHYTO-RECLAIM photobioreactor.

WHAT THIS SCRIPT DEMONSTRATES

1. The Module III stage-gating claim in the paper — "online sensing, fail-safe
   isolation, and a digital twin decide when to harvest, replace media, or LET
   THE CULTURE RECOVER." Method: apply the same upset to two identical systems,
   one without stage-gating and one with it, then compare the outcome.

2. Why 1.5 g/L/day deserves to be called an *upper design case*. The model
   solves backwards for the maximum specific growth rate that figure demands —
   and it lands at the top of the published range for Chlorella. That gives a
   physics-based reason for the caveat the paper already states, rather than
   mere caution.

MODEL
  Two states: X (biomass, g/L) and S (dissolved nitrogen, mg/L).

    dX/dt = (mu - kd) * X  -  harvest rate
    dS/dt = nutrient dose  -  consumption by growth
    mu    = mu_max * f_light(I_avg) * f_nutrient(S) * f_stress(t)

  Light uses a Beer-Lambert average across the tube diameter, so a denser
  culture shades itself. That is what stops productivity rising indefinitely
  with density.

  Harvesting is via decanter centrifuge with water returned to the reactor
  (Table 4 of the paper: "clarified liquid returns to the reuse tank"), so this
  is biomass harvesting, not chemostat dilution.

  Control runs SAMPLED (hourly by default), mirroring how SCADA actually works.

MODEL LIMITS - say this if a judge probes
  This is a screening model, not calibrated against any field data. Biology
  parameters come from the Chlorella literature range, not from the strain that
  would be used. Its value is in the sensitivity structure, not the absolute
  numbers. Measuring the real mu_max, Ka, and eta_sep is one of the Phase 1
  tasks.

    python pbr_dynamic.py

Outputs pbr_dynamic.png and a numeric summary in the terminal.
"""
import sys
from dataclasses import dataclass, replace

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
from scipy.integrate import solve_ivp

NAVY, TEAL, RED, AMBER, GREY, RULE = (
    "#17365D", "#1C8C87", "#B3352F", "#C2801F", "#8A949A", "#C8CFD2")


def _n(x, d=0):
    if not np.isfinite(x):
        return "-"
    return f"{x:,.{d}f}"


# ============================================================ parameters
@dataclass
class PBRParams:
    # --- reactor (Table 3 of the paper) ---
    volume: float = 10_000.0        # litres working volume
    diameter: float = 0.03          # m, light path across the tube
    Q_harvest: float = 10_000.0     # L/day through the centrifuge
    eta_sep: float = 0.50           # biomass separation efficiency per pass

    # --- biology (Chlorella sp. literature range) ---
    mu_max: float = 2.0             # /day, maximum specific growth rate
    Ki: float = 100.0               # umol/m2/s, light half-saturation
    Ks: float = 5.0                 # mg N/L, nutrient half-saturation
    kd: float = 0.05                # /day, respiration + decay
    Ka: float = 0.08                # m2/g, biomass light absorption coefficient
    Yxs: float = 10.0               # g biomass per g N

    # --- tropical light ---
    I_peak: float = 1800.0          # umol/m2/s at midday
    daylength: float = 12.0         # hours

    # --- nutrients ---
    S_set: float = 60.0             # mg N/L dosing setpoint
    k_dose: float = 8.0             # /day, dosing controller gain

    # --- stage-gating (Module III) ---
    X_set: float = 3.0              # g/L design operating density
    gate_low: float = 0.60          # harvest stops below 60% of setpoint
    gate_high: float = 0.90         # harvest resumes above 90% of setpoint
    control_interval: float = 1.0 / 24   # days; sensor sampled hourly

    # --- culture-loss threshold ---
    # Below this density the culture is effectively unrecoverable: contaminants
    # take over and the reactor must be re-inoculated (weeks, not days). The
    # model does not simulate contamination; this threshold is used as a marker.
    X_critical: float = 0.30        # g/L

    # --- upset: an SOx excursion suppressing growth ---
    upset_start: float = 30.0       # days
    upset_days: float = 2.0         # days
    upset_mu_left: float = 0.15     # fraction of mu remaining during the upset


def irradiance(t, p):
    """Surface irradiance on day t, sinusoidal day-night profile."""
    hour = (t % 1.0) * 24.0
    sunrise = 12.0 - p.daylength / 2
    if hour < sunrise or hour > sunrise + p.daylength:
        return 0.0
    return p.I_peak * np.sin(np.pi * (hour - sunrise) / p.daylength)


def average_light(X, I0, p):
    """Beer-Lambert average across the light path; captures self-shading."""
    tau = p.Ka * (X * 1000.0) * p.diameter          # X g/L -> g/m3
    if tau < 1e-9:
        return I0
    return I0 * (1.0 - np.exp(-tau)) / tau


def growth_rate(t, X, S, p):
    I_av = average_light(X, irradiance(t, p), p)
    f_light = I_av / (p.Ki + I_av) if I_av > 0 else 0.0
    f_nutrient = S / (p.Ks + S) if S > 0 else 0.0
    stress = (p.upset_mu_left
              if p.upset_start <= t < p.upset_start + p.upset_days else 1.0)
    return p.mu_max * f_light * f_nutrient * stress


def _derivatives(t, y, p, harvesting):
    X, S = max(y[0], 1e-9), max(y[1], 0.0)
    mu = growth_rate(t, X, S, p)
    harvest = (p.Q_harvest / p.volume) * p.eta_sep * X if harvesting else 0.0
    dX = (mu - p.kd) * X - harvest
    dose = p.k_dose * max(0.0, p.S_set - S)
    dS = dose - mu * X * 1000.0 / p.Yxs
    return [dX, dS]


def run(p, days=90.0, stage_gating=True, X0=3.0, S0=60.0):
    """Sampled integration: control is decided once per `control_interval`."""
    y = [X0, S0]
    harvesting = True
    T, XS, SS, HARV, MU, RATE = [0.0], [X0], [S0], [1.0], [0.0], [0.0]
    isolation_hours = 0.0

    n = int(round(days / p.control_interval))
    for i in range(n):
        t0, t1 = i * p.control_interval, (i + 1) * p.control_interval

        # ---- controller decision, taken from the current sensor reading ----
        if stage_gating:
            if harvesting and y[0] < p.gate_low * p.X_set:
                harvesting = False          # isolate: let the culture recover
            elif not harvesting and y[0] > p.gate_high * p.X_set:
                harvesting = True           # resume harvesting
        else:
            harvesting = True               # no gating: harvest regardless

        sol = solve_ivp(_derivatives, (t0, t1), y, args=(p, harvesting),
                        method="LSODA", rtol=1e-6, atol=1e-9, max_step=0.02)
        y = [max(sol.y[0][-1], 1e-9), max(sol.y[1][-1], 0.0)]

        rate = (p.Q_harvest / p.volume) * p.eta_sep * y[0] if harvesting else 0.0
        if not harvesting:
            isolation_hours += p.control_interval * 24

        T.append(t1); XS.append(y[0]); SS.append(y[1])
        HARV.append(1.0 if harvesting else 0.0)
        MU.append(growth_rate(t1, y[0], y[1], p))
        RATE.append(rate)

    T, XS, RATE = np.array(T), np.array(XS), np.array(RATE)
    harvested_gL = float(np.sum(RATE) * p.control_interval)
    return dict(t=T, X=XS, S=np.array(SS), harvesting=np.array(HARV),
                mu=np.array(MU), rate=RATE,
                cum_kg=np.cumsum(RATE) * p.control_interval * p.volume / 1000.0,
                harvested_gL=harvested_gL,
                harvested_kg=harvested_gL * p.volume / 1000.0,
                isolation_hours=isolation_hours,
                X_min=float(XS.min()),
                culture_lost=bool(XS.min() < p.X_critical))


def steady_productivity(p, after=30.0, days=60.0):
    """True average productivity (g/L/day) once the transient has passed.

    Measured from mass actually harvested, not from instantaneous density — if
    the system has to cycle harvest/isolate, this average is the correct metric.
    """
    r = run(replace(p, upset_start=1e9), days, stage_gating=True)
    sel = r["t"] >= after
    cycling = bool(r["harvesting"][sel].min() < 0.5)
    return float(r["rate"][sel].mean()), cycling, float(r["X"][sel].mean())


def solve_required_mu_max(p, target=1.5, lo=1.0, hi=5.0, iterations=22):
    """Find the mu_max demanded to reach a target productivity."""
    for _ in range(iterations):
        mid = (lo + hi) / 2
        pr, _, _ = steady_productivity(replace(p, mu_max=mid))
        if pr < target:
            lo = mid
        else:
            hi = mid
        if hi - lo < 0.01:
            break
    return (lo + hi) / 2


def idr_per_kg_dry(split=0.20, concentration=0.10, qc=0.90, price=72_000.0):
    """Value of one kg of dry biomass through the paper's product route.

    1 kg dry x 20% allocation = 0.2 kg -> at 10% w/v that is 2 L
    -> x 90% QC release = 1.8 L -> x IDR 72,000/L = IDR 129,600
    The remaining 80% goes to pyrolysis, which the base case books at zero.
    """
    return split / concentration * qc * price


# ============================================================ figure
def build_figure(no_gate, gated, sweep, p, days, mu_required):
    fig = plt.figure(figsize=(11.8, 10.4))
    gs = fig.add_gridspec(4, 2, height_ratios=[1.25, 1.0, 0.42, 1.0],
                          hspace=0.58, wspace=0.26)

    def tidy(ax):
        ax.spines[["top", "right"]].set_visible(False)
        ax.spines[["left", "bottom"]].set_color(RULE)
        ax.tick_params(colors=GREY, labelsize=8.5, length=3)

    u0, u1 = p.upset_start, p.upset_start + p.upset_days

    # --- (a) culture density ---
    ax = fig.add_subplot(gs[0, :]); tidy(ax)
    ax.axvspan(u0, u1, color=RED, alpha=0.13, zorder=1)
    ax.text((u0 + u1) / 2, p.X_set * 1.26,
            f"SOx excursion\n{_n(p.upset_days)} days", ha="center",
            fontsize=8.5, color=RED, fontweight="bold", zorder=6)
    isolated = gated["harvesting"] < 0.5
    if isolated.any():
        ax.fill_between(gated["t"], 0, p.X_set * 1.5, where=isolated,
                        color=TEAL, alpha=0.10, zorder=1)
    for value, colour, text, side, va in (
            (p.X_set, GREY, "setpoint 3.0 g/L", "left", "bottom"),
            (p.gate_low * p.X_set, AMBER, "isolation threshold 1.8 g/L", "left", "top"),
            (p.X_critical, RED, "culture-loss threshold 0.3 g/L", "right", "bottom")):
        ax.axhline(value, color=colour, lw=1.0,
                   ls=":" if colour == GREY else "--", zorder=2)
        if side == "left":
            ax.text(days * 0.004, value, " " + text, fontsize=8, color=colour,
                    va=va, ha="left", zorder=6)
        else:
            ax.text(days * 0.996, value, text + " ", fontsize=8, color=colour,
                    va=va, ha="right", zorder=6)
    ax.plot(no_gate["t"], no_gate["X"], color=RED, lw=1.9, zorder=4,
            label="Without stage-gating — harvesting continues")
    ax.plot(gated["t"], gated["X"], color=TEAL, lw=2.1, zorder=5,
            label="With stage-gating — harvesting paused")
    ax.set_ylim(0, p.X_set * 1.62); ax.set_xlim(0, days)
    ax.set_ylabel("Biomass X (g/L)", fontsize=9.5)
    ax.set_xlabel("Day", fontsize=9.5)
    ax.legend(fontsize=8.8, loc="upper right", framealpha=0.95)
    ax.set_title("(a) Culture response to an identical upset", fontsize=10.5,
                 color=NAVY, fontweight="bold", pad=8)

    # --- (b) cumulative harvest ---
    ax = fig.add_subplot(gs[1, 0]); tidy(ax)
    ax.plot(no_gate["t"], no_gate["cum_kg"], color=RED, lw=2.0,
            label="without gating")
    ax.plot(gated["t"], gated["cum_kg"], color=TEAL, lw=2.0,
            label="with gating")
    ax.fill_between(gated["t"], no_gate["cum_kg"], gated["cum_kg"],
                    color=TEAL, alpha=0.18, lw=0)
    ax.axvspan(u0, u1, color=RED, alpha=0.13)
    gap = gated["cum_kg"][-1] - no_gate["cum_kg"][-1]
    ax.annotate(f"+{_n(gap, 1)} kg", xy=(days, gated["cum_kg"][-1]),
                xytext=(days * 0.60, gated["cum_kg"][-1] * 0.70),
                fontsize=9, color=TEAL, fontweight="bold",
                arrowprops=dict(arrowstyle="->", color=TEAL, lw=1.1))
    ax.set_xlim(0, days)
    ax.set_ylabel("Biomass harvested (kg dry)", fontsize=9.5)
    ax.set_xlabel("Day", fontsize=9.5)
    ax.legend(fontsize=8.8, loc="upper left")
    ax.set_title("(b) Cumulative harvest over 90 days", fontsize=10.5,
                 color=NAVY, fontweight="bold", pad=8)

    # --- (c) diurnal cycle ---
    ax = fig.add_subplot(gs[1, 1]); tidy(ax)
    sel = gated["t"] <= 5
    ax.plot(gated["t"][sel], gated["mu"][sel], color=NAVY, lw=1.5)
    ax.axhline(p.kd, color=RED, lw=1.0, ls="--")
    ax.text(5, p.kd, " respiration ", fontsize=8, color=RED,
            va="bottom", ha="right")
    ax.set_xlim(0, 5)
    ax.set_ylabel("mu (per day)", fontsize=9.5)
    ax.set_xlabel("Day (first five)", fontsize=9.5)
    ax.set_title("(c) The underlying day-night cycle", fontsize=10.5,
                 color=NAVY, fontweight="bold", pad=8)

    # --- (d) gating decisions ---
    ax = fig.add_subplot(gs[2, :]); tidy(ax)
    ax.fill_between(gated["t"], 0, gated["harvesting"], step="post",
                    color=TEAL, alpha=0.75, lw=0)
    ax.axvspan(u0, u1, color=RED, alpha=0.13)
    ax.set_ylim(-0.08, 1.25); ax.set_xlim(0, days)
    ax.set_yticks([0, 1]); ax.set_yticklabels(["ISOLATE", "HARVEST"], fontsize=8.5)
    ax.set_xlabel("Day", fontsize=9.5)
    ax.set_title("(d) Stage-gating decisions — this is what Module III does",
                 fontsize=10.5, color=NAVY, fontweight="bold", pad=8)

    # --- (e) severity sweep: lowest density ---
    d, xmin_n, xmin_g, kg_n, kg_g = sweep
    ax = fig.add_subplot(gs[3, 0]); tidy(ax)
    ax.axhline(p.X_critical, color=RED, lw=1.2, ls="--")
    ax.text(d[-1], p.X_critical, " culture-loss threshold ", fontsize=8,
            color=RED, va="bottom", ha="right")
    floor = max(min(xmin_n.min(), xmin_g.min()) * 0.6, 1e-3)
    ax.fill_between(d, floor, p.X_critical, color=RED, alpha=0.09)
    ax.plot(d, xmin_n, color=RED, lw=2.0, marker="o", ms=4.5,
            label="without gating")
    ax.plot(d, xmin_g, color=TEAL, lw=2.0, marker="o", ms=4.5,
            label="with gating")
    ax.set_yscale("log")
    ax.set_ylim(floor, max(xmin_g.max(), xmin_n.max()) * 1.8)
    ax.set_xlabel("Upset duration (days)", fontsize=9.5)
    ax.set_ylabel("Lowest density reached (g/L, log)", fontsize=9.5)
    ax.legend(fontsize=8.8, loc="lower left")
    ax.set_title("(e) How large an upset the system survives", fontsize=10.5,
                 color=NAVY, fontweight="bold", pad=8)

    # --- (f) severity sweep: harvest ---
    ax = fig.add_subplot(gs[3, 1]); tidy(ax)
    ax.plot(d, kg_n, color=RED, lw=2.0, marker="o", ms=4.5,
            label="without gating")
    ax.plot(d, kg_g, color=TEAL, lw=2.0, marker="o", ms=4.5,
            label="with gating")
    ax.fill_between(d, kg_n, kg_g, color=TEAL, alpha=0.14)
    ax.set_xlabel("Upset duration (days)", fontsize=9.5)
    ax.set_ylabel("90-day harvest (kg dry)", fontsize=9.5)
    ax.legend(fontsize=8.8, loc="lower left")
    ax.set_title("(f) Biomass saved by stage-gating", fontsize=10.5,
                 color=NAVY, fontweight="bold", pad=8)

    fig.suptitle("PHYTO-RECLAIM photobioreactor dynamic simulation — "
                 "90 days, the length of the Phase 1 pilot",
                 fontsize=13, color=NAVY, fontweight="bold", y=0.995)
    fig.text(0.5, 0.004,
             f"Screening model, not calibrated against field data. Biology "
             f"parameters from the Chlorella literature range  ·  "
             f"mu_max {_n(p.mu_max, 1)}/day  ·  Ka {_n(p.Ka, 2)} m2/g  ·  "
             f"eta_sep {_n(p.eta_sep * 100)}%  ·  reaching 1.5 g/L/day demands "
             f"mu_max ~ {_n(mu_required, 2)}/day",
             ha="center", fontsize=8.2, color=GREY, style="italic")
    return fig


# ============================================================ main
if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    p = PBRParams()
    DAYS = 90.0

    print("PHYTO-RECLAIM photobioreactor dynamic simulation")
    print("=" * 74)

    # ---------- 1. what the paper's design figure actually demands ----------
    prod, cycling, X_mean = steady_productivity(p)
    mu_required = solve_required_mu_max(p, target=1.5)
    mu_gate = solve_required_mu_max(p, target=1.125)

    print("\n[1] What the paper's design figure actually demands")
    print("-" * 74)
    print(f"With literature parameters (mu_max {_n(p.mu_max, 1)}/day):")
    print(f"  mean density        : {_n(X_mean, 2)} g/L")
    print(f"  productivity        : {_n(prod, 3)} g/L/day"
          f"{'  (must cycle harvest/isolate)' if cycling else ''}")
    print(f"To reach 1.500 g/L/day       -> demands mu_max ~ {_n(mu_required, 2)}/day")
    print(f"To reach the 1.125 gate      -> demands mu_max ~ {_n(mu_gate, 2)}/day")
    print("  The Chlorella literature range is typically 1.2-2.0/day under")
    print("  optimal conditions. So the 1.5 design figure demands a growth rate")
    print("  at the top of that range, before accounting for SOx stress. That is")
    print("  a physics-based reason for the 'upper design case' caveat the paper")
    print("  already states.")

    # ---------- 2. the value of stage-gating ----------
    no_gate = run(p, DAYS, stage_gating=False)
    gated = run(p, DAYS, stage_gating=True)
    unit_value = idr_per_kg_dry()
    gap = gated["harvested_kg"] - no_gate["harvested_kg"]

    print(f"\n[2] Value of stage-gating under a {_n(p.upset_days)}-day upset")
    print("-" * 74)
    print(f"{'':30}{'without gating':>16}{'with gating':>16}")
    print(f"{'90-day harvest (kg dry)':30}{_n(no_gate['harvested_kg'], 1):>16}"
          f"{_n(gated['harvested_kg'], 1):>16}")
    print(f"{'Lowest density (g/L)':30}{_n(no_gate['X_min'], 3):>16}"
          f"{_n(gated['X_min'], 3):>16}")
    print(f"{'Culture lost?':30}{('YES' if no_gate['culture_lost'] else 'no'):>16}"
          f"{('YES' if gated['culture_lost'] else 'no'):>16}")
    print(f"Harvest difference : {_n(gap, 1)} kg "
          f"({_n(gap / max(no_gate['harvested_kg'], 1e-9) * 100, 1)}%) "
          f"= IDR {_n(gap * unit_value, 0)} per event")
    print(f"Total isolation time : {_n(gated['isolation_hours'], 1)} hours")

    # ---------- 3. upset severity sweep ----------
    print("\n[3] Upset severity sweep")
    print("-" * 74)
    durations = np.arange(0, 9, 1.0)
    xmin_n, xmin_g, kg_n, kg_g = [], [], [], []
    safe_limit = None
    for d in durations:
        pd_ = replace(p, upset_days=float(d))
        a_ = run(pd_, DAYS, stage_gating=False)
        b_ = run(pd_, DAYS, stage_gating=True)
        xmin_n.append(a_["X_min"]); xmin_g.append(b_["X_min"])
        kg_n.append(a_["harvested_kg"]); kg_g.append(b_["harvested_kg"])
        if safe_limit is None and a_["culture_lost"]:
            safe_limit = d
        print(f"  upset {_n(d)} days : X_min without {_n(a_['X_min'], 3):>6} / "
              f"with {_n(b_['X_min'], 3):>6}  |  harvest "
              f"{_n(a_['harvested_kg'], 0):>4} / {_n(b_['harvested_kg'], 0):>4} kg")

    if safe_limit is not None:
        print(f"\n  Without stage-gating, an upset of {_n(safe_limit)} days or longer")
        print(f"  drops the culture below the critical threshold. With stage-gating")
        print(f"  the culture holds at {_n(min(xmin_g), 2)} g/L even at the longest")
        print(f"  upset tested.")
    else:
        print(f"\n  Over the range tested both systems stay above the critical")
        print(f"  threshold. The difference is lost biomass: up to "
              f"{_n(max(np.array(kg_g) - np.array(kg_n)), 0)} kg at the longest upset.")

    sweep = (durations, np.array(xmin_n), np.array(xmin_g),
             np.array(kg_n), np.array(kg_g))
    fig = build_figure(no_gate, gated, sweep, p, DAYS, mu_required)
    fig.savefig("pbr_dynamic.png", dpi=200, bbox_inches="tight", facecolor="white")
    print("\nSaved: pbr_dynamic.png")
