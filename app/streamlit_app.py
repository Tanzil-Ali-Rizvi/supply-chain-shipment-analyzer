"""Supply Chain Shipment Analyzer: Streamlit front end.

Run:  streamlit run app/streamlit_app.py
"""
from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import plotly.graph_objects as go
import streamlit as st

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from shipiq import agent, llm  # noqa: E402
from shipiq import metrics as m  # noqa: E402
from shipiq import tools as t  # noqa: E402
from shipiq.data import ISO3, PERIOD, SOURCE  # noqa: E402

TEAL, DEEP, AMBER, RUST, SAND, SLATE = "#0F766E", "#134E4A", "#D97706", "#B45309", "#E7DCC8", "#64748B"
INK, MUTED, GRID, PAPER = "#1C1917", "#57534E", "#E7E5E4", "#FFFDF8"
ROUTE_COLOR = {"From regional warehouse (RDC)": AMBER, "Direct from vendor": TEAL}
MODE_COLOR = {"Air": RUST, "Air Charter": AMBER, "Truck": TEAL, "Ocean": DEEP, "Not recorded": SLATE}

st.set_page_config(page_title="Supply Chain Shipment Analyzer", page_icon="🚚", layout="wide")
st.markdown(f"""<style>
.block-container {{padding-top: 1.6rem;}}
.hero {{background: linear-gradient(120deg, {DEEP} 0%, {TEAL} 70%, #14B8A6 100%); color: white; padding: 22px 26px; border-radius: 14px; margin-bottom: 14px;}}
.hero h1 {{color: white; font-size: 1.9rem; margin: 0 0 6px 0;}}
.hero p {{color: #E6FFFA; margin: 0; font-size: 0.98rem;}}
.kpi {{background: {PAPER}; border: 1px solid {GRID}; border-left: 5px solid {AMBER}; border-radius: 10px; padding: 12px 14px;}}
.kpi .v {{font-size: 1.6rem; font-weight: 700; color: {INK};}}
.kpi .l {{font-size: 0.8rem; color: {MUTED}; text-transform: uppercase; letter-spacing: .04em;}}
.kpi .s {{font-size: 0.8rem; color: {RUST};}}
</style>""", unsafe_allow_html=True)


@st.cache_data
def load(name: str, *args):
    return getattr(m, name)(*args)


@st.cache_data
def tool(name: str, **kw):
    return getattr(t, name)(**kw)


def style(fig: go.Figure, title: str, y_title: str | None = None, x_title: str | None = None, pct: bool = False,
          height: int = 340, legend: bool = False, money: bool = False, money_x: bool = False) -> go.Figure:
    fig.update_layout(title=dict(text=title, font=dict(size=15, color=INK), x=0, xanchor="left"), height=height,
                      margin=dict(l=10, r=10, t=50, b=10), plot_bgcolor="white", paper_bgcolor="white",
                      font=dict(color=MUTED, size=12), hoverlabel=dict(bgcolor="white"), showlegend=legend,
                      legend=dict(orientation="h", y=-0.2))
    fig.update_xaxes(showgrid=False, linecolor=GRID, title=x_title, tickprefix="$" if money_x else None)
    fig.update_yaxes(gridcolor=GRID, zeroline=False, title=y_title, tickformat=".0%" if pct else None, tickprefix="$" if money else None)
    return fig


def esc(text: str) -> str:
    """Markdown-safe dollar signs (Streamlit reads $...$ as LaTeX)."""
    return text.replace("$", "\\$")


def kpi(col, label: str, value: str, sub: str = "") -> None:
    col.markdown(f'<div class="kpi"><div class="l">{label}</div><div class="v">{value}</div><div class="s">{sub}</div></div>',
                 unsafe_allow_html=True)


n = tool("network_summary")
r = tool("route_comparison")
f = tool("freight_by_mode")

st.markdown(f"""<div class="hero"><h1>Supply Chain Shipment Analyzer</h1>
<p><b>Where does a global health supply chain lose time and money, and what should it fix first?</b> {n['line_items']:,} line items in
{n['shipments']:,} shipments of HIV and malaria medicines and test kits to {n['countries']} countries ({PERIOD}), from the {SOURCE},
with a supply-chain assistant that answers only from governed data.</p></div>""", unsafe_allow_html=True)
c = st.columns(5)
kpi(c[0], "On-time delivery", f"{n['on_time_pct']}%", f"{n['on_time_value_pct']}% by value")
kpi(c[1], "Stock delivered late", f"${n['late_value_musd']}M", f"median {n['median_days_late']} days late")
kpi(c[2], "Warehouse vs direct late", f"{r['warehouse_late_pct']}% vs {r['direct_late_pct']}%", f"{r['like_for_like_odds_ratio']}x odds, like for like")
kpi(c[3], "Air share of freight", f"{n['air_share_of_freight_pct']}%", f"${n['air_usd_per_kg']}/kg vs ${n['ocean_usd_per_kg']}/kg ocean")
kpi(c[4], "Mode-shift saving", f"${n['mode_shift_saving_musd']}M", f"{n['mode_shift_shipments']} heavy air shipments")
st.write("")

tabs = st.tabs(["Executive summary", "Delivery & lanes", "Freight & mode shift", "Countries", "Vendors", "Ask the assistant", "Method"])

# ------------------------------------------------------------------ 1 executive summary
with tabs[0]:
    conc = load("late_value_concentration")
    ms = tool("mode_shift_scenario")
    st.subheader("Four findings")
    st.markdown(esc(
        f"1. **${n['late_value_musd']}M of medicines arrived late.** {n['on_time_pct']}% of line items arrived on time, but only "
        f"{n['on_time_value_pct']}% by value; late lines were a median {n['median_days_late']} days late.\n"
        f"2. **The regional warehouse route is the problem.** Warehouse lines were late {r['warehouse_late_pct']}% of the time vs "
        f"{r['direct_late_pct']}% direct; within the same country, year and mode the odds are {r['like_for_like_odds_ratio']}x higher "
        f"(p = {r['like_for_like_p_value']}). It worsened to {r['warehouse_late_pct_2013_2015']}% late in 2013-2015. Warehouse lanes hold "
        f"{conc['warehouse_share']:.0%} of the value delivered late; five lanes hold {conc['top_share']:.0%}.\n"
        f"3. **Air is {n['air_share_of_freight_pct']}% of the freight bill.** ${n['air_usd_per_kg']}/kg against ${n['ocean_usd_per_kg']}/kg "
        f"by ocean. Shipping {ms['eligible_shipments']} heavy air shipments that were planned {ms['min_plan_days']}+ days ahead by sea would "
        f"have saved about ${ms['saving_musd']}M.\n"
        f"4. **Small shipments pay over ten times the rate.** {f['small_shipments']:,} shipments under {f['small_shipments_under_kg']} kg paid a "
        f"median ${f['small_median_usd_per_kg']}/kg (freight = {f['small_freight_share_of_value_pct']}% of their value) vs "
        f"${f['two_tonne_plus_median_usd_per_kg']}/kg for 2 t+. Consolidate."))
    a, b = st.columns(2)
    yr = load("by_year_route")
    fig = go.Figure([go.Scatter(x=g.year, y=g.late_rate, name=k_, mode="lines+markers", line=dict(color=ROUTE_COLOR[k_], width=3))
                     for k_, g in yr.groupby("route")])
    a.plotly_chart(style(fig, "Late rate by year: the warehouse route broke down after 2009", pct=True, legend=True), width="stretch")
    md = load("by_mode")
    md = md[md["mode"] != "Not recorded"]
    fig = go.Figure(go.Bar(x=md["mode"], y=md.freight_per_kg, marker_color=[MODE_COLOR[x] for x in md["mode"]],
                           text=[f"${v:.2f}/kg · {s:.0%} of spend" for v, s in zip(md.freight_per_kg, md.share_of_freight)], textposition="outside"))
    b.plotly_chart(style(fig, "Freight cost per kg by mode", money=True), width="stretch")
    st.info("**Act first:** warehouse service recovery in Mozambique, Nigeria and Zambia; ocean by default for heavy orders placed "
            "180+ days ahead; batch sub-100 kg orders per country. Details in the other tabs and in `docs/findings.md`.")

# ------------------------------------------------------------------ 2 delivery & lanes
with tabs[1]:
    st.subheader("Where deliveries run late")
    w = load("worklist", 15)
    a, b = st.columns([3, 2])
    fig = go.Figure(go.Bar(y=w.country + " · " + w.route.str.replace("From regional warehouse (RDC)", "warehouse").str.replace("Direct from vendor", "direct"),
                           x=w.late_value_usd / 1e6, orientation="h", marker_color=[ROUTE_COLOR[x] for x in w.route],
                           text=[f"{x:.0%} late" for x in w.late_rate], textposition="outside"))
    fig.update_yaxes(autorange="reversed")
    fig.update_xaxes(range=[0, w.late_value_usd.max() / 1e6 * 1.15])
    a.plotly_chart(style(fig, "Lanes ranked by commodity value delivered late ($M)", height=520, money_x=True), width="stretch")
    rt = load("by_route")
    fig = go.Figure(go.Bar(x=rt.route, y=rt.late_rate, marker_color=[ROUTE_COLOR[x] for x in rt.route], text=[f"{x:.1%}" for x in rt.late_rate],
                           textposition="outside"))
    b.plotly_chart(style(fig, "Late rate by route", pct=True), width="stretch")
    b.markdown(f"**Like for like.** {r['like_for_like_lines']:,} lines in {r['like_for_like_groups']} country-year-mode groups that used both "
               f"routes: odds ratio **{r['like_for_like_odds_ratio']}**, permutation p = {r['like_for_like_p_value']}. The gap is not explained "
               f"by where or how the warehouses ship.")
    st.dataframe(w.assign(late_value_musd=(w.late_value_usd / 1e6).round(2), late_rate=(w.late_rate * 100).round(1))
                 [["country", "route", "lines", "late_lines", "late_rate", "late_value_musd", "median_days_late"]],
                 hide_index=True, width="stretch",
                 column_config={"late_rate": st.column_config.NumberColumn("late %"), "late_value_musd": st.column_config.NumberColumn("late value $M")})

# ------------------------------------------------------------------ 3 freight & mode shift
with tabs[2]:
    st.subheader("What freight costs, and what a mode shift would save")
    a, b = st.columns(2)
    wb = load("by_weight_band")
    fig = go.Figure(go.Bar(x=wb.band, y=wb.median_usd_per_kg, marker_color=[RUST, AMBER, SAND, TEAL, DEEP],
                           text=[f"${v:.2f}/kg · {s:,} shipments" for v, s in zip(wb.median_usd_per_kg, wb.shipments)], textposition="outside"))
    a.plotly_chart(style(fig, "Median freight $/kg by shipment size", money=True), width="stretch")
    mall = load("by_mode")
    fig = go.Figure(go.Pie(labels=mall["mode"], values=mall.freight_usd, hole=0.55, sort=False,
                           marker=dict(colors=[MODE_COLOR[x] for x in mall["mode"]]), textinfo="label+percent"))
    b.plotly_chart(style(fig, f"Freight spend by mode (${n['freight_musd']}M on priced shipments)"), width="stretch")
    st.markdown("#### Mode-shift scenario")
    st.caption("Air shipments heavy enough and planned far enough ahead to have gone by sea, re-costed at ocean rates "
               "(the country's own median ocean $/kg where it has 5+ ocean shipments, else the overall median).")
    s1, s2 = st.columns(2)
    kg = s1.slider("Minimum shipment weight (kg)", 250, 10000, m.SHIFT_MIN_KG, 250)
    days = s2.slider("Minimum days from purchase order to scheduled delivery", 60, 300, m.SHIFT_MIN_PLAN_DAYS, 10)
    sc = tool("mode_shift_scenario", min_kg=kg, min_plan_days=days)
    c = st.columns(4)
    kpi(c[0], "Eligible air shipments", f"{sc['eligible_shipments']}", f"of {sc['air_shipments']:,} air shipments")
    kpi(c[1], "Their air freight", f"${sc['eligible_air_freight_musd']}M")
    kpi(c[2], "At ocean rates", f"${sc['ocean_cost_musd']}M", f"median ${sc['ocean_median_usd_per_kg']}/kg")
    kpi(c[3], "Estimated saving", f"${sc['saving_musd']}M", f"{sc['saving_share_of_air_freight_pct']}% of all air freight")
    st.caption(esc(f"Ocean takes a median {sc['ocean_median_po_to_delivery_days']} days from PO to delivery vs {sc['air_median_po_to_delivery_days']} by air; "
               "the estimate ignores port capacity and the inventory cost of a longer transit."))
    if sc["top_countries"]:
        st.dataframe(pd.DataFrame(sc["top_countries"]), hide_index=True, width="stretch")

# ------------------------------------------------------------------ 4 countries
with tabs[3]:
    st.subheader("Countries")
    bc = load("by_country")
    bc["iso3"] = bc.country.map(ISO3)
    fig = go.Figure(go.Choropleth(locations=bc.iso3, z=bc.late_rate * 100, text=bc.country, colorscale=[[0, "#F0FDFA"], [0.5, AMBER], [1, RUST]],
                                  marker_line_color="white", colorbar=dict(title="% late"),
                                  hovertemplate="%{text}<br>%{z:.1f}% of lines late<extra></extra>"))
    fig.update_geos(showframe=False, showcoastlines=False, projection_type="natural earth", bgcolor="white", landcolor="#F5F5F4", showland=True)
    st.plotly_chart(style(fig, "Share of line items delivered late, by destination country", height=430), width="stretch")
    choice = st.selectbox("Country brief", list(bc.country), index=list(bc.country).index("Mozambique"))
    st.markdown(esc(agent.country_brief(choice)))

# ------------------------------------------------------------------ 5 vendors
with tabs[4]:
    st.subheader(f"Direct-ship vendor scorecard ({m.MIN_VENDOR_LINES}+ line items)")
    v = load("vendor_scorecard")
    short = v.vendor.str.replace(r"[,()]", "", regex=True).str.split().apply(lambda w_: " ".join(w_[:2]) if len(w_[0]) <= 3 else w_[0]).str.title()
    show = (v.lines >= 150) | (v.late_rate >= 0.1)
    fig = go.Figure(go.Scatter(x=v.lines, y=v.late_rate, mode="markers+text", text=short.where(show, ""), hovertext=v.vendor,
                               hovertemplate="%{hovertext}<br>%{x} lines · %{y:.1%} late<extra></extra>", textposition="top center",
                               marker=dict(size=(v.value_usd / v.value_usd.max() * 40 + 8), color=v.late_rate, colorscale=[[0, TEAL], [1, RUST]],
                                           line=dict(color="white", width=1))))
    st.plotly_chart(style(fig, "Volume vs late rate (bubble = commodity value)", y_title="late rate", x_title="direct line items", pct=True, height=420),
                    width="stretch")
    st.dataframe(v.assign(late_rate=(v.late_rate * 100).round(1), value_musd=(v.value_usd / 1e6).round(1))
                 [["vendor", "lines", "value_musd", "late_rate", "late_lines", "median_days_late", "countries", "median_po_to_delivery_days"]],
                 hide_index=True, width="stretch")

# ------------------------------------------------------------------ 6 assistant
with tabs[5]:
    st.subheader("Ask the supply-chain assistant")
    st.caption(("LLM mode: the model picks tools; a grounding check rejects any number not returned by a tool." if llm.enabled() else
                "Offline mode: a deterministic planner picks the tool; answers are templated from tool results.") +
               " Every answer shows the tool calls and the facts it used.")
    examples = ["How did the supply chain perform overall?", "Is the warehouse route slower than direct shipping?", "Where should we act first?",
                "How is Zambia doing?", "What if air shipments over 2 t planned 150 days ahead went by sea?", "How does Aurobindo perform?"]
    pick = st.radio("Try one", examples, horizontal=False, index=None)
    question = st.chat_input("Ask about delivery, freight, countries or vendors") or pick
    if question:
        ans = agent.ask(question)
        with st.chat_message("user"):
            st.write(question)
        with st.chat_message("assistant"):
            st.markdown(esc(ans.text))
            st.caption(f"mode: {ans.mode} · grounded: {ans.grounded}")
            with st.expander("Tool calls and facts"):
                st.json({"calls": ans.calls, "results": ans.results})

# ------------------------------------------------------------------ 7 method
with tabs[6]:
    dq = load("data_quality")
    st.subheader("Method and data quality")
    st.markdown(f"""
- **Source:** {SOURCE}, published by USAID on data.usaid.gov (dataset a3rc-nmf6, *Supply Chain Shipment Pricing Data*). 33 columns,
  {n['line_items']:,} line items, {n['shipments']:,} shipments (ASN/DN numbers).
- **On time** = delivered on or before the scheduled delivery date. **Freight** is analysed per shipment: it is recorded on one line and the
  others point to it ("See ASN-..."); {dq['lines_without_own_freight']:.0%} of lines carry no freight of their own.
- **Route effect:** Mantel-Haenszel odds ratio within country × year × mode groups that used both routes, with a 1,000-shuffle permutation test.
- **Data you should not trust yet:** {dq['freight_in_commodity_cost'] + dq['freight_invoiced_separately']:,} of {dq['shipments']:,} shipments
  ({dq['unpriced_share']:.1%}) have no freight cost of their own; {dq['recorded_late_share']:.1%} of deliveries were recorded after the
  delivery date; {int(dq['mode_not_recorded'])} lines have no transport mode.
- **Definitions:** `docs/kpi_definitions.md`. **Memo:** `docs/findings.md`. **Evals:** `evals/results.md`.
""")
