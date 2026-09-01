# -*- coding: utf-8 -*-
"""PHYTO-RECLAIM process and economic model.

This file is deliberately separated from any user interface so it can be
audited on its own. Every formula and default value is taken directly from the
Stage 2 paper:

  Table 4   annual mass balance
  Table 5   carbon accounting derivation
  Table 11  capital expenditure
  Table 12  operating expenditure
  Table 13  revenue model and investment metrics
  Table 14  sensitivity analysis

Run `python phyto_model.py` to verify that this model reproduces all ten
scenarios of Table 14.
"""
from dataclasses import dataclass

import numpy as np
import numpy_financial as npf

MILLION = 1_000_000
BILLION = 1_000_000_000


@dataclass
class Assumptions:
    """All model inputs. The first six are the dashboard sliders."""

    # --- variables tested for sensitivity ---
    productivity: float = 1.5           # g dry biomass / L / day
    availability: float = 0.90          # fraction of time the unit runs
    product_price: float = 72_000.0     # IDR per litre
    qc_release: float = 0.90            # fraction of batches passing QC
    capex: float = 2054.4 * MILLION     # IDR, upper installed CAPEX
    opex: float = 327.3 * MILLION       # IDR per year

    # --- fixed assumptions from the paper ---
    flow: float = 50.0                  # m3/day nameplate capacity
    pbr_volume: float = 10_000.0        # litres working volume
    product_split: float = 0.20         # biomass fraction sent to formulation
    concentration: float = 0.10         # 10% w/v -> 0.10 kg dry per litre
    carbon_fraction: float = 0.50       # carbon fraction of dry biomass
    assimilation: float = 0.82          # CO2 assimilation efficiency in the PBR
    water_recovery: float = 0.96        # fraction of water recovered
    wetland_biomass: float = 1.40       # t dry/year from wetland harvest
    biochar_yield: float = 0.30         # pyrolysis feed fraction -> biochar
    biooil_yield: float = 0.35          # pyrolysis feed fraction -> bio-oil
    disposal_tariff: float = 12_800.0   # IDR/m3 disposal cost avoided
    discount_rate: float = 0.10         # DCF discount rate
    life: int = 10                      # project life, years
    productivity_gate: float = 1.125    # g/L/day, Phase 1 investment gate


def evaluate(a: Assumptions) -> dict:
    """Run the full chain, from productivity through to IRR."""

    # ---------- water balance ----------
    on_stream_days = 365 * a.availability
    water_treated = a.flow * on_stream_days                    # m3/year
    water_recovered = water_treated * a.water_recovery

    # ---------- algal biomass ----------
    # g/L/day x L x days -> grams, divided by 1e6 to give tonnes
    biomass = a.productivity * a.pbr_volume * on_stream_days / 1e6   # t dry/yr

    # ---------- carbon branch ----------
    co2_gross = biomass * a.carbon_fraction * (44 / 12)        # tCO2/year
    co2_delivered = co2_gross / a.assimilation
    co2_specific = co2_gross * 1000 / water_treated if water_treated else 0.0

    # ---------- product branch ----------
    allocated = biomass * a.product_split                      # t dry/year
    gross_volume = allocated * 1000 / a.concentration          # litres/year
    saleable = gross_volume * a.qc_release                     # litres/year

    # ---------- pyrolysis branch ----------
    residual_algae = biomass * (1 - a.product_split)
    pyrolysis_feed = residual_algae + a.wetland_biomass
    biochar = pyrolysis_feed * a.biochar_yield
    biooil = pyrolysis_feed * a.biooil_yield
    syngas = pyrolysis_feed * (1 - a.biochar_yield - a.biooil_yield)

    # ---------- annual economics ----------
    product_revenue = saleable * a.product_price
    disposal_avoided = water_treated * a.disposal_tariff
    total_benefit = product_revenue + disposal_avoided
    net_benefit = total_benefit - a.opex

    # ---------- investment metrics ----------
    # The first benefit only arrives at the end of year 1, so discounting starts
    # at t=1. (numpy_financial.npv treats the first element as t=0 with no
    # discount, which overstates NPV — hence the explicit sum below.)
    discounted = [net_benefit / (1 + a.discount_rate) ** t
                  for t in range(1, a.life + 1)]
    npv = sum(discounted) - a.capex

    cash_flows = [-a.capex] + [net_benefit] * a.life
    try:
        irr = npf.irr(cash_flows)
    except Exception:
        irr = float("nan")
    if irr is None or not np.isfinite(irr):
        irr = float("nan")
    payback = a.capex / net_benefit if net_benefit > 0 else float("inf")

    return {
        "water_treated": water_treated,
        "water_recovered": water_recovered,
        "on_stream_days": on_stream_days,
        "biomass": biomass,
        "co2_gross": co2_gross,
        "co2_delivered": co2_delivered,
        "co2_specific": co2_specific,
        "allocated": allocated,
        "gross_volume": gross_volume,
        "saleable": saleable,
        "residual_algae": residual_algae,
        "pyrolysis_feed": pyrolysis_feed,
        "biochar": biochar,
        "biooil": biooil,
        "syngas": syngas,
        "product_revenue": product_revenue,
        "disposal_avoided": disposal_avoided,
        "total_benefit": total_benefit,
        "net_benefit": net_benefit,
        "npv": npv,
        "irr": irr,
        "payback": payback,
        "cumulative": np.cumsum([-a.capex] + discounted),
        "gate_passed": a.productivity >= a.productivity_gate,
    }


def breakeven_price(a: Assumptions, target_npv: float = 0.0,
                    hurdle: float | None = None) -> float:
    """Minimum product price (IDR/L) for NPV to reach a target at a given rate.

    Used to derive the IDR 50,900/L (10% hurdle) and IDR 54,200/L (12% hurdle)
    figures quoted in the paper.
    """
    r = a.discount_rate if hurdle is None else hurdle
    annuity = sum(1 / (1 + r) ** t for t in range(1, a.life + 1))
    base = evaluate(a)
    if base["saleable"] <= 0:
        return float("nan")
    required_net = (target_npv + a.capex) / annuity
    required_revenue = required_net - base["disposal_avoided"] + a.opex
    return required_revenue / base["saleable"]


# ---------------------------------------------------------------- verification

#: The ten rows of Table 14. Used to prove this model reproduces the published
#: numbers rather than being a separate calculation that merely looks similar.
SCENARIOS = [
    ("Base case",                    dict(),                                     521.5,  3.9,  1150,  21.9),
    ("Product price IDR 45,000/L",   dict(product_price=45_000),                 282.0,  7.3,  -321,   6.2),
    ("Product price IDR 55,000/L",   dict(product_price=55_000),                 370.7,  5.5,   224,  12.5),
    ("PBR productivity 1.125 g/L/d", dict(productivity=1.125),                   361.9,  5.7,   169,  11.9),
    ("PBR productivity 0.75 g/L/d",  dict(productivity=0.75),                    202.2, 10.2,  -812,  None),
    ("Availability 80%",             dict(availability=0.80),                    427.2,  4.8,   571,  16.1),
    ("QC release 80%",               dict(qc_release=0.80),                      450.6,  4.6,   714,  17.6),
    ("OPEX +20%",                    dict(opex=327.3 * 1.20 * MILLION),          456.1,  4.5,   748,  17.9),
    ("CAPEX +15%",                   dict(capex=2054.4 * 1.15 * MILLION),        521.5,  4.5,   842,  17.8),
    ("Combined downside",            dict(capex=2054.4 * 1.15 * MILLION,
                                          opex=327.3 * 1.20 * MILLION,
                                          product_price=72_000 * 0.80,
                                          productivity=1.5 * 0.80),              226.2, 10.4,  -973,  None),
]


def verify(tolerance_million: float = 1.0) -> list[dict]:
    """Recompute every Table 14 scenario and compare against the paper."""
    rows = []
    for name, overrides, p_net, p_payback, p_npv, p_irr in SCENARIOS:
        r = evaluate(Assumptions(**overrides))
        net = r["net_benefit"] / MILLION
        npv = r["npv"] / MILLION
        irr = r["irr"] * 100 if np.isfinite(r["irr"]) else float("nan")
        rows.append({
            "scenario": name,
            "net_model": net, "net_paper": p_net,
            "npv_model": npv, "npv_paper": p_npv,
            "irr_model": irr, "irr_paper": p_irr,
            "payback_model": r["payback"], "payback_paper": p_payback,
            "match": abs(net - p_net) <= tolerance_million
                     and abs(npv - p_npv) <= tolerance_million,
        })
    return rows


if __name__ == "__main__":
    import sys
    sys.stdout.reconfigure(encoding="utf-8")

    print("Model verification against Table 14 of the paper")
    print("=" * 78)
    print(f"{'Scenario':<32}{'Net benefit (M)':>20}{'NPV (M)':>18}{'':>8}")
    print(f"{'':<32}{'model':>10}{'paper':>10}{'model':>9}{'paper':>9}")
    print("-" * 78)
    all_match = True
    for h in verify():
        flag = "OK" if h["match"] else "DIFF"
        all_match &= h["match"]
        print(f"{h['scenario']:<32}"
              f"{h['net_model']:>10.1f}{h['net_paper']:>10.1f}"
              f"{h['npv_model']:>9.0f}{h['npv_paper']:>9.0f}"
              f"{flag:>8}")
    print("-" * 78)
    print("ALL MATCH" if all_match else "MISMATCH FOUND - check the assumptions")

    a = Assumptions()
    print()
    print(f"Breakeven price at 10% NPV : IDR {breakeven_price(a):,.0f}/L")
    print(f"Price to clear a 12% hurdle: IDR {breakeven_price(a, hurdle=0.12):,.0f}/L")
