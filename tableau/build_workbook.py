"""Generate the Tableau workbook (TWB XML) for the Supply Chain Shipment Analyzer.

The workbook reads the CSVs that scripts/export_tableau.py writes, so every figure traces back to src/shipiq/metrics.py.
Two dashboards: "Delivery & Freight Overview" and "Freight, Vendors & Mode Shift", in the same warm-paper / teal / amber
look as the Streamlit app. Run:

    python tableau/build_workbook.py --data-dir "C:/Users/<you>/Downloads/scm_tableau"

then open the .twb in Tableau Public or Desktop and save it to Tableau Public.
"""
from __future__ import annotations

import argparse
import uuid
from pathlib import Path
from xml.sax.saxutils import escape

import pandas as pd

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / "tableau" / "data"
OUT = ROOT / "tableau" / "Supply Chain Shipment Analyzer.twb"

TEAL, DEEP, AMBER, RUST, SAND, SLATE = "#0f766e", "#134e4a", "#d97706", "#b45309", "#e7dcc8", "#64748b"
INK, MUTED, PAPER, CARD = "#1c1917", "#57534e", "#faf7f2", "#ffffff"
ROUTE_COLORS = {"Warehouse (RDC)": AMBER, "Direct from vendor": TEAL}
MODE_COLORS = {"Air": RUST, "Air Charter": AMBER, "Truck": TEAL, "Ocean": DEEP, "Not recorded": SLATE}
W, H = 1400, 1000  # dashboard pixels

CAPTIONS = {"saving_musd": "Saving ($M)", "late_rate": "Late rate", "lines": "Line items", "value_musd": "Commodity value ($M)",
            "weight_band": "Shipment size", "year": "Year", "lane": "Lane", "mode": "Mode", "country": "Country", "route": "Route",
            "vendor": "Vendor", "shift_saving_musd": "Mode-shift saving ($M)"}
FORMATS = {"saving_musd": "n#,##0.00", "late_rate": "p0%", "value_musd": "n#,##0.0", "shift_saving_musd": "n#,##0.00"}
REMOTE = {"string": 129, "integer": 20, "real": 5, "date": 133}
DIMENSION_NUMBERS = {"line_id", "year", "band_order"}


def a(v) -> str:
    return escape(str(v), {"'": "&apos;", '"': "&quot;"})


def q(s: str) -> str:
    """Quote a string member for a Tableau formula or bucket."""
    return "&quot;" + a(s) + "&quot;"


# ------------------------------------------------------------------ datasources
class DS:
    def __init__(self, key: str, caption: str, csv: str, data_dir: str, dates=(), geo: str | None = None):
        self.key, self.caption, self.csv, self.data_dir, self.geo = key, caption, csv, data_dir, geo
        self.name = f"federated.{key}"
        self.conn = f"hyper.{key}"
        self.obj = f"{csv}_{uuid.uuid5(uuid.NAMESPACE_URL, csv).hex.upper()}"
        df = pd.read_csv(DATA / csv, nrows=2000)
        self.cols = []
        for c, t in df.dtypes.items():
            dt = "date" if c in dates else "integer" if pd.api.types.is_integer_dtype(t) else "real" if pd.api.types.is_float_dtype(t) else "string"
            self.cols.append((c, dt))
        self.dtype = dict(self.cols)
        self.calcs: dict[str, tuple[str, str, str, str]] = {}  # id -> (caption, datatype, formula, format)

    def calc(self, cid: str, caption: str, formula: str, fmt: str = "", datatype: str = "real") -> str:
        self.calcs[cid] = (caption, datatype, formula, fmt)
        return cid

    def role(self, c: str) -> tuple[str, str]:
        dt = self.dtype[c]
        if dt in ("integer", "real") and c not in DIMENSION_NUMBERS:
            return "measure", "quantitative"
        if c == "year":
            return "dimension", "ordinal"
        return "dimension", "nominal"

    def column_decl(self, c: str) -> str:
        if c in self.calcs:
            cap, dt, f, fmt = self.calcs[c]
            fa = f" default-format='{a(fmt)}'" if fmt else ""
            return (f"<column caption='{a(cap)}' datatype='{dt}'{fa} name='[{c}]' role='measure' type='quantitative'>"
                    f"<calculation class='tableau' formula='{a(f)}' /></column>")
        role, typ = self.role(c)
        sem = " semantic-role='[Country].[Name]'" if c == self.geo else ""
        cap = CAPTIONS.get(c, c.replace("_", " ").capitalize())
        fa = f" default-format='{a(FORMATS[c])}'" if c in FORMATS else ""
        return f"<column caption='{a(cap)}' datatype='{self.dtype[c]}'{fa} name='[{c}]' role='{role}'{sem} type='{typ}' />"

    def xml(self, palettes: dict[str, dict[str, str]]) -> str:
        hyper = self.csv.replace(".csv", ".hyper")
        rel = f"<relation connection='{self.conn}' name='Extract' table='[Extract].[Extract]' type='table' />"
        recs = []
        for i, (c, dt) in enumerate(self.cols):
            agg = "Sum" if dt in ("integer", "real") else "Year" if dt == "date" else "Count"
            recs.append(f"<metadata-record class='column'><remote-name>{a(c)}</remote-name><remote-type>{REMOTE[dt]}</remote-type>"
                        f"<local-name>[{a(c)}]</local-name><parent-name>[Extract]</parent-name><remote-alias>{a(c)}</remote-alias>"
                        f"<ordinal>{i}</ordinal><local-type>{dt}</local-type><aggregation>{agg}</aggregation>"
                        + "<contains-null>true</contains-null>"
                        + ("<collation flag='0' name='LEN_RUS' />" if dt == "string" else "")
                        + f"<object-id>[{self.obj}]</object-id></metadata-record>")
        decl = "".join(self.column_decl(c) for c, _ in self.cols) + "".join(self.column_decl(c) for c in self.calcs)
        style = ""
        rules = [(f, m) for f, m in palettes.items() if f in self.dtype]
        if rules:
            enc = "".join(f"<encoding attr='color' field='[none:{f}:nk]' type='palette'>"
                          + "".join(f"<map to='{c}'><bucket>{q(v)}</bucket></map>" for v, c in m.items()) + "</encoding>" for f, m in rules)
            style = f"<style><style-rule element='mark'>{enc}</style-rule></style>"
        return (f"<datasource caption='{a(self.caption)}' inline='true' name='{self.name}' version='18.1'>"
                f"<connection class='federated'><named-connections><named-connection caption='{a(self.caption)}' name='{self.conn}'>"
                f"<connection authentication='auth-none' author-locale='en_US' class='hyper' dbname='{a(self.data_dir + '/' + hyper)}' "
                f"default-settings='yes' sslmode='' username='tableau_internal_user' />"
                f"</named-connection></named-connections>{rel}<metadata-records>{''.join(recs)}</metadata-records></connection>"
                f"<aliases enabled='yes' />{decl}"
                f"<column caption='{a(self.csv)}' datatype='table' name='[__tableau_internal_object_id__].[{self.obj}]' role='measure' type='quantitative' />"
                f"<layout dim-ordering='alphabetic' measure-ordering='alphabetic' show-structure='true' />{style}"
                f"<semantic-values><semantic-value key='[Country].[Name]' value='&quot;United States&quot;' /></semantic-values>"
                f"<object-graph><objects><object caption='{a(self.csv)}' id='{self.obj}'><properties context=''>{rel}</properties></object></objects></object-graph>"
                f"</datasource>")


# ------------------------------------------------------------------ worksheets
def inst(ds: DS, col: str, agg: str = "none") -> str:
    """Column-instance name: [none:country:nk], [sum:value_usd:qk], [usr:Calc:qk], [med:x:qk], [yr:date:ok]..."""
    if col in ds.calcs:
        return f"[usr:{col}:qk]"
    role, typ = ds.role(col)
    if agg == "none":
        return f"[none:{col}:{'ok' if typ == 'ordinal' else 'nk' if role == 'dimension' else 'qk'}]"
    return f"[{agg}:{col}:qk]"


DERIV = {"none": "None", "sum": "Sum", "avg": "Avg", "med": "Median", "min": "Min", "usr": "User", "cnt": "Count"}


class Sheet:
    def __init__(self, name: str, ds: DS, title: str | None = None):
        self.name, self.ds, self.title = name, ds, title
        self.used: dict[str, tuple[str, str]] = {}  # instance -> (column, derivation)
        self.rows = self.cols = ""
        self.mark = "Automatic"
        self.enc: list[str] = []
        self.filters: list[str] = []
        self.sorts: list[str] = []
        self.label: str | None = None
        self.show_labels = False
        self.extra_style: list[str] = []
        self.palette: tuple[str, dict[str, str]] | None = None  # (column, value -> colour)
        self.mark_color: str | None = None

    def f(self, col: str, agg: str = "none") -> str:
        if col in self.ds.calcs:
            agg = "usr"
        i = inst(self.ds, col, agg)
        self.used[i] = (col, DERIV[agg])
        return f"[{self.ds.name}].{i}"

    def raw(self, field: str) -> str:
        return f"[{self.ds.name}].[{field}]"

    def _palette_rule(self) -> str:
        if not self.palette:
            return ""
        col, m = self.palette
        ref = self.f(col)
        maps = "".join(f"<map to='{c}'><bucket>{q(v)}</bucket></map>" for v, c in m.items())
        return f"<style-rule element='mark'><encoding attr='color' field='{a(ref)}' type='palette'>{maps}</encoding></style-rule>"

    def xml(self) -> str:
        ds = self.ds
        self._palette_rule()  # registers the palette field as used
        cols = sorted({c for c, _ in self.used.values()})
        deps = "".join(ds.column_decl(c) for c in cols)
        for i, (c, d) in sorted(self.used.items()):
            role, typ = (("measure", "quantitative") if c in ds.calcs else ds.role(c))
            t = "quantitative" if d not in ("None",) or typ == "quantitative" else typ
            deps += f"<column-instance column='[{c}]' derivation='{d}' name='{i}' pivot='key' type='{t}' />"
        title = ""
        if self.title:
            title = (f"<layout-options><title><formatted-text><run bold='true' fontcolor='{INK}' fontname='Tableau Medium' fontsize='12'>"
                     f"{a(self.title)}</run></formatted-text></title></layout-options>")
        filt = "".join(self.filters)
        srt = "".join(self.sorts)
        label = ""
        if self.label is not None:
            label = f"<customized-label><formatted-text>{self.label}</formatted-text></customized-label>"
        fmts = ""
        if self.show_labels or self.label is not None:
            fmts += "<format attr='mark-labels-show' value='true' /><format attr='mark-labels-cull' value='true' />"
        if self.mark_color:
            fmts += f"<format attr='mark-color' value='{self.mark_color}' />"
        pane_style = f"<style><style-rule element='mark'>{fmts}</style-rule></style>" if fmts else ""
        enc = f"<encodings>{''.join(self.enc)}</encodings>" if self.enc else ""
        ws_style = ("<style><style-rule element='table'><format attr='background-color' value='#ffffff' /></style-rule>"
                    "<style-rule element='worksheet'><format attr='font-family' value='Tableau Book' /><format attr='color' value='#57534e' /></style-rule>"
                    + "".join(self.extra_style) + self._palette_rule() + "</style>")
        return (f"<worksheet name='{a(self.name)}'>{title}<table><view><datasources><datasource caption='{a(ds.caption)}' name='{ds.name}' />"
                f"</datasources><datasource-dependencies datasource='{ds.name}'>{deps}</datasource-dependencies>{filt}{srt}"
                f"<aggregation value='true' /></view>{ws_style}<panes><pane selection-relaxation-option='selection-relaxation-allow'>"
                f"<view><breakdown value='auto' /></view><mark class='{self.mark}' />{enc}{label}{pane_style}</pane></panes>"
                f"<rows>{a(self.rows)}</rows><cols>{a(self.cols)}</cols></table>"
                f"<simple-id uuid='{{{str(uuid.uuid5(uuid.NAMESPACE_DNS, self.name)).upper()}}}' /></worksheet>")


def kpi_sheet(name: str, ds: DS, label: str, measures: list, tmpl: str, sub: str) -> Sheet:
    """A KPI tile: a small caption, one big number (or two), a one-line context."""
    s = Sheet(name, ds)
    s.mark = "Text"
    refs = [s.f(*mz) if isinstance(mz, tuple) else s.f(mz) for mz in measures]
    for r in refs:
        s.enc.append(f"<text column='{a(r)}' />")
    big = tmpl
    for k_, r in enumerate(refs):
        big = big.replace(f"{{{k_}}}", f"&lt;{a(r)}&gt;")
    s.label = (f"<run fontcolor='{MUTED}' fontsize='9'>{a(label.upper())}</run><run>Æ&#10;</run>"
               f"<run bold='true' fontcolor='{INK}' fontsize='20'>{big}</run><run>Æ&#10;</run>"
               f"<run fontcolor='{RUST}' fontsize='9'>{a(sub)}</run>")
    return s


def cat_filter(s: Sheet, col: str, members: list[str], exclude: bool = False) -> None:
    lvl = s.f(col)
    short = "[" + lvl.split("].[", 1)[1]
    inner = "".join(f"<groupfilter function='member' level='{a(short)}' member='{q(m)}' />" for m in members)
    if exclude:
        g = (f"<groupfilter function='except' user:ui-domain='database' user:ui-enumeration='exclusive' user:ui-marker='enumerate'>"
             f"<groupfilter function='level-members' level='{a(short)}' />"
             + (inner if len(members) == 1 else f"<groupfilter function='union'>{inner}</groupfilter>") + "</groupfilter>")
    else:
        g = (inner.replace("<groupfilter function='member'", "<groupfilter function='member' user:ui-domain='database' user:ui-enumeration='inclusive' "
                           "user:ui-marker='enumerate'", 1) if len(members) == 1 else
             f"<groupfilter function='union' user:ui-domain='database' user:ui-enumeration='inclusive' user:ui-marker='enumerate'>{inner}</groupfilter>")
    s.filters.append(f"<filter class='categorical' column='{a(lvl)}'>{g}</filter>")


def computed_sort(s: Sheet, dim: str, measure_ref: str, direction: str = "DESC") -> None:
    s.sorts.append(f"<sort class='computed' column='{a(dim)}' direction='{direction}' using='{a(measure_ref)}' />")


# ------------------------------------------------------------------ dashboards
_zid = [100]


def zid() -> int:
    _zid[0] += 1
    return _zid[0]


def px(x, y, w, h) -> str:
    return f"h='{round(h / H * 100000)}' w='{round(w / W * 100000)}' x='{round(x / W * 100000)}' y='{round(y / H * 100000)}'"


def zstyle(bg: str = CARD, border: str = "#e7e5e4", margin: int = 6) -> str:
    return (f"<zone-style><format attr='border-color' value='{border}' /><format attr='border-style' value='solid' />"
            f"<format attr='border-width' value='1' /><format attr='margin' value='{margin}' />"
            f"<format attr='background-color' value='{bg}' /></zone-style>")


def text_zone(x, y, w, h, runs: str, bg: str = PAPER, border: str = PAPER) -> str:
    return (f"<zone floating='true' {px(x, y, w, h)} id='{zid()}' type-v2='text'><formatted-text>{runs}</formatted-text>"
            f"{zstyle(bg, border, 10)}</zone>")


def sheet_zone(name: str, x, y, w, h, title: bool = True) -> str:
    return f"<zone floating='true' {px(x, y, w, h)} id='{zid()}' name='{a(name)}' show-title='{str(title).lower()}'>{zstyle()}</zone>"


def dashboard(name: str, zones: list[str]) -> str:
    return (f"<dashboard name='{a(name)}'><style><style-rule element='table'><format attr='background-color' value='{PAPER}' /></style-rule></style>"
            f"<size maxheight='{H}' maxwidth='{W}' minheight='{H}' minwidth='{W}' sizing-mode='fixed' />"
            f"<datasources /><zones><zone h='100000' id='{zid()}' type-v2='layout-basic' w='100000' x='0' y='0'>{''.join(zones)}</zone></zones>"
            f"<simple-id uuid='{{{str(uuid.uuid5(uuid.NAMESPACE_DNS, name)).upper()}}}' /></dashboard>")


def viewpoint(s: Sheet) -> str:
    """Fit every sheet to its dashboard box, except maps (fitting a map drops the background map)."""
    zoom = "" if s.mark == "Multipolygon" else "<zoom type='entire-view' />"
    return f"<viewpoint name='{a(s.name)}'>{zoom}</viewpoint>" if zoom else f"<viewpoint name='{a(s.name)}' />"


def br() -> str:
    return "<run>Æ&#10;</run>"


def run(text: str, size: int = 10, color: str = INK, bold: bool = False) -> str:
    return f"<run{' bold=' + chr(39) + 'true' + chr(39) if bold else ''} fontcolor='{color}' fontsize='{size}'>{a(text)}</run>"


# ------------------------------------------------------------------ build
def build(data_dir: str) -> str:
    k = pd.read_csv(DATA / "kpis.csv").iloc[0]
    L = DS("lines01", "Line items", "lines.csv", data_dir, dates=("scheduled_date",), geo="country")
    S = DS("shipments01", "Priced shipments", "shipments.csv", data_dir)
    K = DS("kpis01", "Governed KPIs", "kpis.csv", data_dir)
    V = DS("vendors01", "Vendor scorecard", "vendors.csv", data_dir)
    M = DS("modeshift01", "Mode-shift scenario", "mode_shift.csv", data_dir)

    L.calc("Calc_on_time", "On-time rate", "1 - SUM([late]) / SUM([lines])", "p0.0%")
    L.calc("Calc_late_rate", "Late rate", "SUM([late]) / SUM([lines])", "p0.0%")
    L.calc("Calc_value_late", "Value delivered late ($M)", "SUM([late_value_usd]) / 1000000", "n#,##0.0")
    for cid, cap, route in [("Calc_wh_late", "Warehouse late rate", "Warehouse (RDC)"), ("Calc_direct_late", "Direct late rate", "Direct from vendor")]:
        L.calc(cid, cap, f"SUM(IF [route] = '{route}' THEN [late] END) / SUM(IF [route] = '{route}' THEN [lines] END)", "p0.0%")
    L.calc("Calc_value_total", "Commodity value ($M)", "SUM([value_usd]) / 1000000", "n#,##0.0")
    S.calc("Calc_usd_kg", "Freight $ per kg", "SUM([freight_usd]) / SUM([weight_kg])", "c\"$\"#,##0.00")
    S.calc("Calc_air_share", "Air share of freight", "SUM(IF [mode] = 'Air' THEN [freight_usd] END) / SUM([freight_usd])", "p0.0%")
    S.calc("Calc_median_kg", "Median freight $ per kg", "MEDIAN([freight_usd] / [weight_kg])", "c\"$\"#,##0.00")
    S.calc("Calc_freight_m", "Freight ($M)", "SUM([freight_usd]) / 1000000", "n#,##0.0")

    sheets: list[Sheet] = []
    # KPI tiles
    s1 = kpi_sheet("KPI On-time", L, "On-time delivery", ["Calc_on_time"], "{0}", f"{k.net_on_time_value_pct}% by value")
    s2 = kpi_sheet("KPI Value late", L, "Stock delivered late", ["Calc_value_late"], "${0}M", f"median {int(k.net_median_days_late)} days late")
    s3 = kpi_sheet("KPI Warehouse vs direct", L, "Late: warehouse vs direct", ["Calc_wh_late", "Calc_direct_late"], "{0} vs {1}",
                   f"{k.route_like_for_like_odds_ratio}x odds, like for like (p = {k.route_like_for_like_p_value})")
    s4 = kpi_sheet("KPI Air share", S, "Air share of freight", ["Calc_air_share"], "{0}", f"${k.net_air_usd_per_kg}/kg vs ${k.net_ocean_usd_per_kg}/kg ocean")
    s5 = kpi_sheet("KPI Mode shift", K, "Mode-shift saving", [("shift_saving_musd", "sum")], "${0}M",
                   f"{int(k.shift_eligible_shipments)} heavy air shipments by sea")
    sheets += [s1, s2, s3, s4, s5]

    # late rate by year and route
    t = Sheet("Late rate by year", L, "Late rate by year: warehouse (orange) vs direct (blue)")
    t.mark = "Line"
    t.cols = t.f("year")
    t.rows = t.f("Calc_late_rate")
    t.enc.append(f"<color column='{a(t.f('route'))}' />")
    t.palette = ("route", ROUTE_COLORS)
    sheets.append(t)

    # lanes
    ln = Sheet("Lanes by value late", L, "Top 12 lanes by commodity value delivered late ($M)")
    ln.mark = "Bar"
    ln.rows = ln.f("lane")
    ln.cols = ln.f("Calc_value_late")
    ln.enc += [f"<color column='{a(ln.f('route'))}' />", f"<text column='{a(ln.f('Calc_late_rate'))}' />"]
    ln.label = f"<run fontcolor='{MUTED}' fontsize='8'>&lt;{a(ln.f('Calc_late_rate'))}&gt; late</run>"
    ln.palette = ("route", ROUTE_COLORS)
    cat_filter(ln, "top_lane", ["Top 12"])
    computed_sort(ln, ln.f("lane"), ln.f("Calc_value_late"))
    sheets.append(ln)

    # map
    mp = Sheet("Late rate by country", L, "Share of line items delivered late, by destination country")
    mp.mark = "Multipolygon"
    mp.rows = mp.raw("Latitude (generated)")
    mp.cols = mp.raw("Longitude (generated)")
    mp.enc += [f"<color column='{a(mp.f('Calc_late_rate'))}' />", f"<lod column='{a(mp.f('country'))}' />"]
    sheets.append(mp)

    # freight by mode
    fm = Sheet("Freight cost by mode", S, "Freight cost per kg by mode (bar label = freight spend)")
    fm.mark = "Bar"
    fm.rows = fm.f("mode")
    fm.cols = fm.f("Calc_usd_kg")
    fm.enc += [f"<color column='{a(fm.f('mode'))}' />", f"<text column='{a(fm.f('Calc_freight_m'))}' />"]
    fm.label = f"<run fontcolor='{MUTED}' fontsize='8'>$&lt;{a(fm.f('Calc_freight_m'))}&gt;M</run>"
    fm.palette = ("mode", MODE_COLORS)
    cat_filter(fm, "mode", ["Not recorded"], exclude=True)
    computed_sort(fm, fm.f("mode"), fm.f("Calc_usd_kg"))
    sheets.append(fm)

    # cost per kg by size band
    sb = Sheet("Cost per kg by size", S, "Median freight $/kg by shipment size: small orders pay over 10x the rate")
    sb.mark = "Bar"
    sb.cols = sb.f("weight_band")
    sb.rows = sb.f("Calc_median_kg")
    sb.enc += [f"<color column='{a(sb.f('weight_band'))}' />", f"<text column='{a(sb.f('Calc_median_kg'))}' />"]
    sb.show_labels = True
    sb.palette = ("weight_band", dict(zip(["Under 100 kg", "100-500 kg", "500 kg-2 t", "2-10 t", "Over 10 t"], [RUST, AMBER, SAND, TEAL, DEEP])))
    computed_sort(sb, sb.f("weight_band"), sb.f("band_order", "min"), "ASC")
    sheets.append(sb)

    # vendors
    vs = Sheet("Vendor scorecard", V, "Direct-ship vendors: volume vs late rate (bubble = commodity value)")
    vs.mark = "Circle"
    vs.cols = vs.f("lines", "sum")
    vs.rows = vs.f("late_rate", "avg")
    vs.mark_color = TEAL
    vs.enc += [f"<size column='{a(vs.f('value_musd', 'sum'))}' />",
               f"<lod column='{a(vs.f('vendor'))}' />", f"<text column='{a(vs.f('vendor'))}' />"]
    vs.show_labels = True
    sheets.append(vs)

    # mode shift by country
    msh = Sheet("Mode-shift saving by country", M, f"Mode-shift saving by country ($M): air shipments of {int(k.shift_min_kg):,}+ kg planned "
                f"{int(k.shift_min_plan_days)}+ days ahead, re-costed at ocean rates")
    msh.mark = "Bar"
    msh.rows = msh.f("country")
    msh.cols = msh.f("saving_musd", "sum")
    msh.enc += [f"<text column='{a(msh.f('saving_musd', 'sum'))}' />"]
    msh.show_labels = True
    msh.mark_color = TEAL
    computed_sort(msh, msh.f("country"), msh.f("saving_musd", "sum"))
    sheets.append(msh)

    # ---------------- dashboard 1
    head = (run("Supply Chain Shipment Analyzer", 17, "#ffffff", True) + br()
            + run("Where does a global health supply chain lose time and money, and what should it fix first? "
                  f"{int(k.net_line_items):,} line items to {int(k.net_countries)} countries, 2006-2015 (USAID SCMS data).", 10, "#e6fffa"))
    z1 = [text_zone(16, 10, W - 32, 94, head, DEEP, DEEP)]
    kw = (W - 32 - 4 * 10) / 5
    for i, s in enumerate([s1, s2, s3, s4, s5]):
        z1.append(sheet_zone(s.name, 16 + i * (kw + 10), 112, kw, 104, title=False))
    z1 += [sheet_zone(t.name, 16, 226, 680, 324), sheet_zone(ln.name, 704, 226, 680, 324),
           sheet_zone(mp.name, 16, 558, 680, 326), sheet_zone(fm.name, 704, 558, 680, 326)]
    foot = (run("What this solves. ", 10, INK, True)
            + run(f"${k.net_late_value_musd}M of medicines arrived late, and the regional-warehouse route is late {k.route_warehouse_late_pct}% of the "
                  f"time vs {k.route_direct_late_pct}% direct ({k.route_like_for_like_odds_ratio}x odds in the same country, year and mode). "
                  "Act first on warehouse dispatch in Mozambique, Nigeria and Zambia; ship heavy orders placed 180+ days ahead by sea; batch "
                  "sub-100 kg orders. Questions answered: how reliable is delivery, which route and lanes lose the most stock, what freight "
                  "costs by mode and size, and what a mode shift would save.", 9, MUTED))
    z1.append(text_zone(16, 892, W - 32, 96, foot, CARD, "#e7e5e4"))
    d1 = dashboard("Delivery & Freight Overview", z1)

    # ---------------- dashboard 2
    head2 = (run("Freight, Vendors & Mode Shift", 17, "#ffffff", True) + br()
             + run(f"Air is {k.net_air_share_of_freight_pct}% of the ${k.net_freight_musd}M freight bill; shipping "
                   f"{int(k.shift_eligible_shipments)} heavy, early-planned air orders by sea saves about ${k.shift_saving_musd}M.", 10, "#e6fffa"))
    z2 = [text_zone(16, 10, W - 32, 94, head2, DEEP, DEEP),
          sheet_zone(sb.name, 16, 114, 680, 380), sheet_zone(msh.name, 704, 114, 680, 380),
          sheet_zone(vs.name, 16, 502, W - 32, 390)]
    foot2 = (run("How to read it. ", 10, INK, True)
             + run("Freight is analysed per shipment (it is recorded once per ASN/DN). Vendor scorecard covers direct shipments from vendors with "
                   "20+ line items. Every number comes from the governed Python metrics in the GitHub repo "
                   "(Tanzil-Ali-Rizvi/supply-chain-shipment-analyzer), and the extract reconciles to them.", 9, MUTED))
    z2.append(text_zone(16, 900, W - 32, 88, foot2, CARD, "#e7e5e4"))
    d2 = dashboard("Freight, Vendors & Mode Shift", z2)

    palettes = {"route": ROUTE_COLORS, "mode": MODE_COLORS}
    cards = ("<cards><edge name='left'><strip size='160'><card type='pages' /><card type='filters' /><card type='marks' /></strip></edge>"
             "<edge name='top'><strip size='2147483647'><card type='columns' /></strip><strip size='2147483647'><card type='rows' /></strip>"
             "<strip size='31'><card type='title' /></strip></edge></cards>")
    windows = "".join(f"<window class='worksheet' hidden='true' maximized='true' name='{a(s.name)}'>{cards}"
                      f"<simple-id uuid='{{{str(uuid.uuid5(uuid.NAMESPACE_X500, s.name)).upper()}}}' /></window>"
                      for s in sheets)
    for dn, ss in [("Delivery & Freight Overview", [s1, s2, s3, s4, s5, t, ln, mp, fm]), ("Freight, Vendors & Mode Shift", [sb, msh, vs])]:
        windows += (f"<window class='dashboard' maximized='true' name='{a(dn)}'><viewpoints>"
                    + "".join(viewpoint(s) for s in ss) + "</viewpoints><active id='-1' />"
                    f"<simple-id uuid='{{{str(uuid.uuid5(uuid.NAMESPACE_OID, dn)).upper()}}}' /></window>")
    return ("<?xml version='1.0' encoding='utf-8' ?>\n"
            "<workbook original-version='18.1' source-build='2025.2.0 (20252.25.0610.1520)' source-platform='win' version='18.1' "
            "xmlns:user='http://www.tableausoftware.com/xml/user'>"
            "<document-format-change-manifest><AnimationOnByDefault /><MarkAnimation /><ObjectModelEncapsulateLegacy />"
            "<ObjectModelTableType /><SchemaViewerObjectModel /><SheetIdentifierTracking /><WindowsPersistSimpleIdentifiers />"
            "</document-format-change-manifest><preferences />"
            f"<datasources>{''.join(d.xml(palettes) for d in [L, S, K, V, M])}</datasources>"
            f"<worksheets>{''.join(s.xml() for s in sheets)}</worksheets>"
            f"<dashboards>{d1}{d2}</dashboards>"
            f"<windows source-height='30'>{windows}</windows></workbook>\n")


def main() -> None:
    p = argparse.ArgumentParser()
    p.add_argument("--data-dir", default=str(DATA).replace("\\", "/"), help="folder holding the CSVs on the machine that opens the workbook")
    p.add_argument("--out", default=str(OUT))
    args = p.parse_args()
    Path(args.out).write_text(build(args.data_dir), encoding="utf-8")
    print("wrote", args.out)


if __name__ == "__main__":
    main()
