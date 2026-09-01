# -*- coding: utf-8 -*-
"""PHYTO-RECLAIM process and economic model — presentation dashboard.

Run with:  python -m streamlit run app.py

NAMING — read this before using it on stage.
This is a PROCESS SIMULATION MODEL, not a digital twin. A digital twin is a
model synchronised with a physical asset through live data; there is no
physical asset and no field data here. Call it what it is: "a parameterised
process and economic model that reproduces every number in the paper."
That is still a strong claim, and it does not breach the bounded-claim
architecture the paper is built on.
"""
import io

import numpy as np
import plotly.graph_objects as go
import streamlit as st

from phyto_model import (Assumptions, evaluate, breakeven_price, verify,
                         MILLION)

st.set_page_config(page_title="PHYTO-RECLAIM Model", page_icon="💧",
                   layout="wide", initial_sidebar_state="expanded")

NAVY, TEAL, RED, AMBER, GREY = "#17365D", "#1C8C87", "#B3352F", "#C2801F", "#8A949A"
INK, MUTED, RULE, SURFACE = "#15272C", "#5E7076", "#DCE3E5", "#FFFFFF"

# Plotly styling shared by every chart: no gridlines, generous type,
# nothing on screen that is not information.
LAYOUT = dict(
    template="simple_white",
    font=dict(family="Segoe UI, Helvetica, Arial, sans-serif", size=15, color=INK),
    margin=dict(l=8, r=8, t=34, b=8),
    xaxis=dict(showgrid=False, zeroline=False, linecolor=RULE, ticks="outside",
               tickcolor=RULE, tickfont=dict(size=13, color=MUTED)),
    yaxis=dict(showgrid=False, zeroline=False, linecolor=RULE, ticks="outside",
               tickcolor=RULE, tickfont=dict(size=13, color=MUTED)),
    plot_bgcolor="rgba(0,0,0,0)", paper_bgcolor="rgba(0,0,0,0)",
    showlegend=False, hoverlabel=dict(font_size=14),
)
NO_BAR = {"displayModeBar": False, "responsive": True}


st.markdown(f"""
<style>
  .block-container {{padding-top:1.1rem; padding-bottom:2rem; max-width:1500px}}
  header[data-testid="stHeader"] {{background:transparent}}

  .brand {{
    background:{NAVY}; color:#fff; border-radius:6px;
    padding:20px 26px; margin-bottom:18px;
  }}
  .brand h1 {{font-size:30px; font-weight:650; margin:0 0 5px; letter-spacing:-.4px}}
  .brand p  {{font-size:15px; margin:0; opacity:.80; max-width:88ch; line-height:1.5}}
  .brand .eyebrow {{
    font-size:11.5px; letter-spacing:.16em; text-transform:uppercase;
    opacity:.65; margin-bottom:9px;
  }}

  .status {{
    padding:14px 20px; border-radius:6px; font-size:16.5px;
    margin-bottom:16px; line-height:1.45;
  }}
  .status b {{font-weight:650}}
  .pass {{background:#E4F1E7; border-left:5px solid #3B7F4A; color:#1E4A2B}}
  .fail {{background:#F8E4E2; border-left:5px solid {RED}; color:#7A241E}}
  .note {{background:#EAEFF0; border-left:5px solid {MUTED}; color:#3E555B}}

  .kpi {{
    background:{SURFACE}; border:1px solid {RULE}; border-radius:6px;
    padding:16px 18px; height:100%;
  }}
  .kpi .k-label {{
    font-size:11.5px; letter-spacing:.11em; text-transform:uppercase;
    color:{MUTED}; margin-bottom:8px;
  }}
  .kpi .k-value {{
    font-size:34px; font-weight:660; color:{NAVY}; line-height:1.05;
    font-variant-numeric:tabular-nums;
  }}
  .kpi .k-sub {{font-size:13px; color:{MUTED}; margin-top:6px}}
  .kpi .k-up {{color:#3B7F4A; font-weight:600}}
  .kpi .k-dn {{color:{RED}; font-weight:600}}

  /* st.container(border=True) is the only wrapper that can actually contain
     Streamlit widgets - a hand-rolled <div> cannot span separate st calls. */
  div[data-testid="stVerticalBlockBorderWrapper"] {{
    background:{SURFACE}; border-radius:6px; padding:4px 6px;
  }}
  .p-title {{
    font-size:12px; letter-spacing:.11em; text-transform:uppercase;
    color:{MUTED}; margin:2px 0 10px; font-weight:600;
  }}
  .panel {{
    background:{SURFACE}; border:1px solid {RULE}; border-radius:6px;
    padding:16px 20px; margin-bottom:14px;
  }}
  .panel h4 {{
    font-size:12px; letter-spacing:.11em; text-transform:uppercase;
    color:{MUTED}; margin:0 0 12px; font-weight:600;
  }}

  /* derivation chain - values shown as values, never as bar lengths, because
     productivity and NPV share no scale */
  .chain {{display:flex; align-items:stretch; gap:0; flex-wrap:nowrap}}
  .ch-item {{
    flex:1; text-align:center; padding:16px 6px;
    border:1px solid {RULE}; border-radius:6px; background:#FAFBFB;
  }}
  .ch-item.accent {{background:{NAVY}; border-color:{NAVY}}}
  .ch-v {{font-size:24px; font-weight:660; color:{NAVY};
          font-variant-numeric:tabular-nums; line-height:1.1}}
  .ch-item.accent .ch-v {{color:#fff}}
  .ch-item.neg .ch-v {{color:#fff}}
  .ch-item.neg {{background:{RED}; border-color:{RED}}}
  .ch-l {{font-size:12px; color:{MUTED}; margin-top:7px; line-height:1.35}}
  .ch-item.accent .ch-l, .ch-item.neg .ch-l {{color:rgba(255,255,255,.8)}}
  .ch-ar {{
    display:flex; align-items:center; padding:0 9px;
    color:{RULE}; font-size:20px;
  }}

  .stTabs [data-baseweb="tab-list"] {{gap:26px; border-bottom:1px solid {RULE}}}
  .stTabs [data-baseweb="tab"] {{
    font-size:15.5px; font-weight:550; padding:9px 0; color:{MUTED};
  }}
  .stTabs [aria-selected="true"] {{color:{NAVY}}}

  section[data-testid="stSidebar"] {{background:#F4F6F7}}
  section[data-testid="stSidebar"] .stButton button {{
    width:100%; text-align:left; font-size:14px; border-radius:5px;
    border:1px solid {RULE}; background:#fff; padding:7px 12px;
  }}
  section[data-testid="stSidebar"] .stButton button:hover {{
    border-color:{TEAL}; color:{TEAL};
  }}
  div[data-testid="stDataFrame"] {{border:1px solid {RULE}; border-radius:6px}}
</style>
""", unsafe_allow_html=True)


def n(x, d=1):
    """Number with thousands separators; em dash for anything non-finite."""
    if x is None or (isinstance(x, float) and not np.isfinite(x)):
        return "—"
    return f"{x:,.{d}f}"


def panel(title):
    """Bordered card that can genuinely wrap Streamlit widgets."""
    box = st.container(border=True)
    box.markdown(f'<div class="p-title">{title}</div>', unsafe_allow_html=True)
    return box


def kpi(label, value, sub="", delta=None):
    d = ""
    if delta is not None and abs(delta) > 0.5:
        cls = "k-up" if delta > 0 else "k-dn"
        d = f'<span class="{cls}">{"▲" if delta > 0 else "▼"} {n(abs(delta), 0)} M</span> vs base'
    return (f'<div class="kpi"><div class="k-label">{label}</div>'
            f'<div class="k-value">{value}</div>'
            f'<div class="k-sub">{d or sub}</div></div>')


# ============================================================ presets
PRESETS = {
    "Base case (paper)":      dict(prod=1.500, avail=90, price=72_000, qc=90,
                                   capex=2054.4, opex=327.3),
    "Phase 1 investment gate": dict(prod=1.125, avail=90, price=72_000, qc=90,
                                    capex=2054.4, opex=327.3),
    "Dynamic-model case":     dict(prod=1.084, avail=90, price=72_000, qc=90,
                                   capex=2054.4, opex=327.3),
    "Productivity 50% short": dict(prod=0.750, avail=90, price=72_000, qc=90,
                                   capex=2054.4, opex=327.3),
    "Offtake floor 55,000/L": dict(prod=1.500, avail=90, price=55_000, qc=90,
                                   capex=2054.4, opex=327.3),
    "Combined downside":      dict(prod=1.200, avail=90, price=57_600, qc=90,
                                   capex=2362.6, opex=392.8),
}

st.sidebar.markdown("### Scenarios")
st.sidebar.caption("One click instead of six slider drags — use these live.")
for name in PRESETS:
    if st.sidebar.button(name, key=f"btn_{name}"):
        for k, v in PRESETS[name].items():
            st.session_state[k] = v
        st.rerun()

st.sidebar.markdown("---")
st.sidebar.markdown("### Assumptions")

prod = st.sidebar.slider("PBR productivity (g/L/day)", 0.400, 1.800, 1.500, 0.005,
                         key="prod", format="%.3f",
                         help="Phase 1 investment gate sits at 1.125 — 75% of design.")
avail = st.sidebar.slider("System availability (%)", 60, 98, 90, 1, key="avail")
price = st.sidebar.slider("Product price (IDR/litre)", 30_000, 95_000, 72_000, 500,
                          key="price")
qc = st.sidebar.slider("QC release factor (%)", 60, 100, 90, 1, key="qc")
# Decimals kept so the base case is genuinely 2,054.4 and 327.3 — rounding these
# moves NPV off the paper's number and the "model = paper" claim collapses.
capex_m = st.sidebar.slider("Installed CAPEX (IDR million)", 1200.0, 2800.0,
                            2054.4, 0.1, key="capex", format="%.1f",
                            help="Paper range 1,586.0–2,054.4 million. "
                                 "Base case uses the upper bound.")
opex_m = st.sidebar.slider("Annual OPEX (IDR million)", 200.0, 550.0, 327.3, 0.1,
                           key="opex", format="%.1f")

with st.sidebar.expander("Advanced (fixed in the paper)"):
    flow = st.number_input("Produced-water flow (m³/day)", 10.0, 200.0, 50.0, 5.0)
    pbr_v = st.number_input("PBR working volume (L)", 1_000.0, 50_000.0,
                            10_000.0, 1_000.0)
    split = st.slider("Biomass allocated to product (%)", 5, 50, 20) / 100
    conc = st.slider("Formulation concentration (% w/v)", 5, 25, 10) / 100
    assim = st.slider("CO₂ assimilation efficiency (%)", 50, 100, 82) / 100
    tariff = st.number_input("Disposal cost avoided (IDR/m³)", 0, 50_000, 12_800, 100)
    disc = st.slider("Discount rate (%)", 5, 20, 10) / 100
    life = st.slider("Project life (years)", 5, 20, 10)

a = Assumptions(
    productivity=prod, availability=avail / 100, product_price=float(price),
    qc_release=qc / 100, capex=capex_m * MILLION, opex=opex_m * MILLION,
    flow=flow, pbr_volume=pbr_v, product_split=split, concentration=conc,
    assimilation=assim, disposal_tariff=float(tariff), discount_rate=disc, life=life,
)
r = evaluate(a)
base = evaluate(Assumptions())

# ============================================================ header
st.markdown(f"""
<div class="brand">
  <div class="eyebrow">Sustainable Innovation Competition 2026 · Team Viraja Gama UGM</div>
  <h1>PHYTO-RECLAIM — process &amp; economic model</h1>
  <p>Every figure on this screen is computed from the assumptions on the left,
     not transcribed from the paper. Move a slider and the investment case moves
     with it.</p>
</div>
""", unsafe_allow_html=True)

at_base = (abs(prod - 1.5) < 1e-6 and avail == 90 and price == 72_000 and qc == 90
           and abs(capex_m - 2054.4) < .05 and abs(opex_m - 327.3) < .05
           and life == 10 and abs(disc - .10) < 1e-6)

if r["gate_passed"]:
    st.markdown(
        f'<div class="status pass"><b>Phase 1 investment gate cleared.</b> '
        f'Productivity {n(prod, 3)} g/L/day is at or above 1.125 — 75% of the '
        f'1.5 design case.</div>', unsafe_allow_html=True)
else:
    st.markdown(
        f'<div class="status fail"><b>Phase 1 investment gate not cleared.</b> '
        f'Productivity {n(prod, 3)} g/L/day is below 1.125. The paper states the '
        f'response is redesign or termination — not a wider scope.</div>',
        unsafe_allow_html=True)

if at_base:
    ok = (abs(r["npv"] / MILLION - 1150) < 1 and abs(r["irr"] * 100 - 21.9) < .05)
    st.markdown(
        f'<div class="status note">Sitting on the <b>paper base case</b> — '
        f'{"the figures below match Table 13." if ok else "figures do NOT match Table 13; check the advanced assumptions."}'
        f'</div>', unsafe_allow_html=True)

c1, c2, c3, c4 = st.columns(4)
c1.markdown(kpi("Net present value", f"{n(r['npv'] / MILLION, 0)}",
                "IDR million · 10 yr · 10% discount",
                None if at_base else (r["npv"] - base["npv"]) / MILLION),
            unsafe_allow_html=True)
c2.markdown(kpi("Internal rate of return",
                f"{n(r['irr'] * 100)}%" if np.isfinite(r["irr"]) else "negative",
                "same conservative basis"), unsafe_allow_html=True)
c3.markdown(kpi("Simple payback",
                f"{n(r['payback'])}" if np.isfinite(r["payback"]) else "—",
                "years to recover installed CAPEX"), unsafe_allow_html=True)
c4.markdown(kpi("Net annual benefit", f"{n(r['net_benefit'] / MILLION)}",
                "IDR million per year"), unsafe_allow_html=True)

st.write("")
t1, t2, t3, t4 = st.tabs(["Overview", "Mass balance", "Economics",
                          "Sensitivity & validation"])

# ============================================================ overview
with t1:
    st.markdown('<div class="panel"><h4>Where every number comes from</h4>',
                unsafe_allow_html=True)
    steps = [
        (n(prod, 3), "PBR productivity<br>g/L/day", ""),
        (n(r["biomass"], 2), "Algal biomass<br>t dry/year", ""),
        (n(r["saleable"] / 1000, 1), "QC-released product<br>thousand L/year", ""),
        (n(r["total_benefit"] / MILLION, 0), "Annual benefit<br>IDR million", ""),
        (n(r["npv"] / MILLION, 0), "Net present value<br>IDR million",
         "accent" if r["npv"] >= 0 else "neg"),
    ]
    chain = '<div class="chain">'
    for i, (val, lab, cls) in enumerate(steps):
        if i:
            chain += '<div class="ch-ar">&#8594;</div>'
        chain += (f'<div class="ch-item {cls}"><div class="ch-v">{val}</div>'
                  f'<div class="ch-l">{lab}</div></div>')
    chain += '</div>'
    st.markdown(chain, unsafe_allow_html=True)
    st.markdown(f'<p style="font-size:13.5px;color:{MUTED};margin:14px 0 0">'
                f'One root assumption drives all four downstream figures. That is '
                f'deliberate: anchoring biomass, product and carbon to a single '
                f'number means an error anywhere shows up everywhere, instead of '
                f'two estimates quietly drifting apart.</p></div>',
                unsafe_allow_html=True)

    o1, o2 = st.columns(2)
    with o1:
        box = panel("Physical output per year")
        rows = [("Produced water treated", f"{n(r['water_treated'], 0)} m³"),
                ("Water recovered", f"{n(r['water_recovered'], 0)} m³"),
                ("Gross algal CO₂ uptake", f"{n(r['co2_gross'], 2)} tCO₂"),
                ("QC-released product", f"{n(r['saleable'], 0)} L"),
                ("Biochar", f"{n(r['biochar'], 2)} t")]
        html = '<table style="width:100%;border-collapse:collapse;font-size:15px">'
        for k, v in rows:
            html += (f'<tr><td style="padding:9px 0;color:{MUTED}">{k}</td>'
                     f'<td style="padding:9px 0;text-align:right;font-weight:600;'
                     f'font-variant-numeric:tabular-nums">{v}</td></tr>')
        box.markdown(html + "</table>", unsafe_allow_html=True)

    with o2:
        box = panel("Deliberately booked at zero")
        box.markdown(
            f'<div style="font-size:15px;line-height:1.65;color:{INK}">'
            f'<b>Carbon credit revenue: IDR 0.</b><br>'
            f'<span style="color:{MUTED}">No approved methodology, no MRV, no '
            f'additionality and no permanence demonstrated — so the base case '
            f'books nothing. The investment case has to stand without it, and '
            f'it does.</span><br><br>'
            f'<b>Gross uptake {n(r["co2_gross"], 2)} tCO₂/year is not '
            f'sequestration.</b><br>'
            f'<span style="color:{MUTED}">Carbon in the liquid product is '
            f'temporary utilisation. Only the tested stable fraction of '
            f'algal-derived biochar could ever back a durable storage claim.'
            f'</span></div>', unsafe_allow_html=True)

    st.info("**If a judge asks about 1.5 g/L/day:** it is an upper design case "
            "taken from optimised-PBR literature, not demonstrated on this "
            "produced water with this flue gas. Drag the slider down and show "
            "the consequence — do not defend the number.")

# ============================================================ mass balance
with t2:
    st.caption("Every output descends from one root assumption: PBR productivity.")
    m1, m2 = st.columns(2)

    def block(col, title, rows):
        with col:
            st.markdown(f'<div class="panel"><h4>{title}</h4>', unsafe_allow_html=True)
            html = '<table style="width:100%;border-collapse:collapse;font-size:14.5px">'
            for name, val, how in rows:
                html += (f'<tr><td style="padding:8px 12px 8px 0">{name}'
                         f'<br><span style="color:{MUTED};font-size:12px">{how}</span></td>'
                         f'<td style="text-align:right;font-weight:600;white-space:nowrap;'
                         f'font-variant-numeric:tabular-nums">{val}</td></tr>')
            st.markdown(html + "</table></div>", unsafe_allow_html=True)

    block(m1, "Water", [
        ("On-stream days", f"{n(r['on_stream_days'])} d", f"365 × {avail}% availability"),
        ("Produced water treated", f"{n(r['water_treated'], 0)} m³/yr",
         f"{n(flow, 0)} m³/day × on-stream days"),
        ("Water recovered", f"{n(r['water_recovered'], 0)} m³/yr",
         "× 96% after evapotranspiration"),
    ])
    block(m1, "Carbon", [
        ("Algal biomass", f"{n(r['biomass'], 4)} t dry/yr",
         f"{n(prod, 3)} g/L/day × {n(pbr_v, 0)} L × on-stream days"),
        ("Gross CO₂ uptake", f"{n(r['co2_gross'], 2)} tCO₂/yr", "× 50% carbon × 44/12"),
        ("CO₂ delivered to PBR", f"{n(r['co2_delivered'], 2)} tCO₂/yr",
         f"÷ {n(assim * 100, 0)}% assimilation"),
        ("Uptake per m³ water", f"{n(r['co2_specific'], 2)} kgCO₂/m³",
         "gross uptake ÷ water treated"),
    ])
    block(m2, "Product", [
        ("Allocated to product", f"{n(r['allocated'], 4)} t dry/yr",
         f"biomass × {n(split * 100, 0)}%"),
        ("Gross formulated volume", f"{n(r['gross_volume'], 0)} L/yr",
         f"÷ {n(conc * 100, 0)}% w/v concentration"),
        ("QC-released product", f"{n(r['saleable'], 0)} L/yr",
         f"× {qc}% QC release"),
    ])
    block(m2, "Pyrolysis", [
        ("Residual algae", f"{n(r['residual_algae'], 3)} t dry/yr",
         f"biomass × {n((1 - split) * 100, 0)}%"),
        ("Total pyrolysis feed", f"{n(r['pyrolysis_feed'], 2)} t dry/yr",
         "+ 1.40 t wetland biomass"),
        ("Biochar", f"{n(r['biochar'], 2)} t/yr", "feed × 30%"),
        ("Bio-oil / syngas", f"{n(r['biooil'], 2)} / {n(r['syngas'], 2)} t/yr",
         "feed × 35% each"),
    ])

# ============================================================ economics
with t3:
    e1, e2 = st.columns([1, 1.1])

    with e1:
        box = panel("Annual economic build-up")
        pr = r["product_revenue"] / MILLION
        dp = r["disposal_avoided"] / MILLION
        ox = a.opex / MILLION
        nb = r["net_benefit"] / MILLION
        wf = go.Figure(go.Waterfall(
            orientation="v",
            measure=["relative", "relative", "relative", "total"],
            x=["Product value", "Disposal avoided", "OPEX", "Net benefit"],
            y=[pr, dp, -ox, 0],
            text=[n(pr), n(dp), f"−{n(ox)}", n(nb)],
            textposition="outside", textfont=dict(size=15),
            increasing=dict(marker_color=TEAL), decreasing=dict(marker_color=RED),
            totals=dict(marker_color=NAVY),
            connector=dict(line=dict(color=GREY, dash="dot", width=1))))
        wf.update_layout(**LAYOUT, height=360)
        wf.update_yaxes(title="IDR million per year", visible=True)
        box.plotly_chart(wf, use_container_width=True, config=NO_BAR)

    with e2:
        box = panel("Cumulative discounted cash flow")
        cum = r["cumulative"] / MILLION
        cf = go.Figure()
        cf.add_hline(y=0, line=dict(color=INK, width=1))
        cf.add_trace(go.Scatter(
            x=list(range(a.life + 1)), y=cum, mode="lines+markers",
            line=dict(color=NAVY, width=2.6),
            marker=dict(size=8, color="white", line=dict(color=NAVY, width=2)),
            fill="tozeroy",
            fillcolor="rgba(28,140,135,.13)" if cum[-1] >= 0 else "rgba(179,53,47,.12)"))
        cf.update_layout(**LAYOUT, height=360)
        cf.update_xaxes(title="Year")
        cf.update_yaxes(title="IDR million (discounted)")
        box.plotly_chart(cf, use_container_width=True, config=NO_BAR)

    h1, h2, h3 = st.columns(3)
    h1.markdown(kpi("Breakeven price", f"{n(breakeven_price(a), 0)}",
                    f"IDR/L at NPV 0, {n(disc*100,0)}% discount"), unsafe_allow_html=True)
    h2.markdown(kpi("Price for a 12% hurdle",
                    f"{n(breakeven_price(a, hurdle=0.12), 0)}", "IDR/L"),
                unsafe_allow_html=True)
    h3.markdown(kpi("Recommended contract floor", "55,000",
                    "IDR/L — the number to have ready"), unsafe_allow_html=True)

    st.warning("**Never breach this rule:** product value means **either** an "
               "arm's-length sale to an external buyer **or** avoided "
               "procurement. Never both — that is double counting. Say it "
               "before a judge asks.")

    st.markdown("##### Figure 5 for the paper")
    st.caption("Figure 5 is missing from the submitted PDF — only its caption "
               "renders. This builds it from the assumptions currently set.")
    try:
        from figure5 import build_figure5
        fig = build_figure5(a)
        buf = io.BytesIO()
        fig.savefig(buf, format="png", dpi=300, bbox_inches="tight",
                    facecolor="white")
        st.image(buf.getvalue(), use_container_width=True)
        st.download_button("Download Figure 5 (PNG, 300 dpi)", buf.getvalue(),
                           "figure5.png", "image/png")
    except Exception as exc:
        st.error(f"Could not build the figure: {exc}")

# ============================================================ sensitivity
with t4:
    box = panel("Which variable actually decides the outcome")
    box.caption("Each variable is moved ±20% from its current slider position "
               "while the others are held. Bar length is its influence on NPV.")

    fields = [("PBR productivity", "productivity", a.productivity),
              ("Product price", "product_price", a.product_price),
              ("Availability", "availability", a.availability),
              ("QC release factor", "qc_release", a.qc_release),
              ("OPEX", "opex", a.opex),
              ("CAPEX", "capex", a.capex)]
    rows = []
    for label, field, value in fields:
        down = evaluate(Assumptions(**{**a.__dict__, field: value * 0.80}))["npv"] / MILLION
        up = evaluate(Assumptions(**{**a.__dict__, field: value * 1.20}))["npv"] / MILLION
        rows.append((label, down, up, abs(up - down)))
    rows.sort(key=lambda x: x[3])
    here = r["npv"] / MILLION

    tor = go.Figure()
    tor.add_trace(go.Bar(y=[x[0] for x in rows], x=[x[1] - here for x in rows],
                         base=here, orientation="h", name="−20%",
                         marker_color=RED, opacity=.85,
                         hovertemplate="%{y}: %{x:,.0f} M<extra>−20%</extra>"))
    tor.add_trace(go.Bar(y=[x[0] for x in rows], x=[x[2] - here for x in rows],
                         base=here, orientation="h", name="+20%",
                         marker_color=TEAL, opacity=.85,
                         hovertemplate="%{y}: %{x:,.0f} M<extra>+20%</extra>"))
    tor.add_vline(x=here, line=dict(color=NAVY, width=1.6, dash="dash"))
    tor.add_vline(x=0, line=dict(color=INK, width=1))
    tor.update_layout(**{**LAYOUT, "showlegend": True}, height=380,
                      barmode="overlay",
                      legend=dict(orientation="h", y=1.14, x=0,
                                  font=dict(size=13)))
    tor.update_xaxes(title="NPV (IDR million)")
    box.plotly_chart(tor, use_container_width=True, config=NO_BAR)

    st.success(f"**At the current settings the deciding variable is "
               f"{rows[-1][0]}.** If a judge asks what your biggest risk is, "
               f"name the top two from this chart — not a long list.")

    box = panel("This model reproduces Table 14 of the paper")
    box.caption("All ten scenarios are recomputed by the model and compared with "
               "the published figures. This is the evidence that model and "
               "paper are one thing, not two separate calculations.")
    checks = verify()
    table = [{
        "Scenario": h["scenario"],
        "Net model (M)": round(h["net_model"], 1),
        "Net paper (M)": h["net_paper"],
        "NPV model (M)": round(h["npv_model"]),
        "NPV paper (M)": h["npv_paper"],
        "IRR model": f"{h['irr_model']:.1f}%" if np.isfinite(h["irr_model"]) else "<0%",
        "IRR paper": f"{h['irr_paper']:.1f}%" if h["irr_paper"] else "<0%",
        "Match": "✔" if h["match"] else "✘",
    } for h in checks]
    box.dataframe(table, use_container_width=True, hide_index=True)

    if all(h["match"] for h in checks):
        st.success("**All ten scenarios match.** Differences are below IDR 1 "
                   "million on both net benefit and NPV — the remainder is "
                   "rounding in the paper.")
    else:
        st.error("A scenario does not match — check the advanced assumptions.")

    st.markdown(
        f"""<div class="panel"><h4>Call this tool what it is</h4>
        <p style="font-size:15px;line-height:1.6;margin:0">
        This is a <b>parameterised process and economic model</b>, not a
        <i>digital twin</i>. A digital twin is synchronised with a physical
        asset through live data — there is no physical asset and no field data
        here. Calling it a digital twin would breach the bounded-claim
        architecture that is the paper's main strength, and the judges from
        Pertamina Hulu Energi know the difference.<br><br>
        What you can say: <i>“This model reproduces every number in Tables 13
        and 14 of the paper from its underlying assumptions, so any
        ‘what if’ question can be answered here, live.”</i></p></div>""",
        unsafe_allow_html=True)
