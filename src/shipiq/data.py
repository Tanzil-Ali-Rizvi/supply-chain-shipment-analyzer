"""Load and clean the USAID SCMS Delivery History dataset into DuckDB tables.

Source: USAID, Supply Chain Management System (SCMS) Delivery History Dataset, release of 29 Sep 2015
(data.usaid.gov dataset a3rc-nmf6, "Supply Chain Shipment Pricing Data"). 10,324 line items of HIV/AIDS
and malaria health commodities shipped to 43 countries, 2006-2015.

Tables
  lines      one row per line item (the grain of the source file)
  shipments  one row per shipment (ASN/DN number). Freight and weight are recorded once per shipment, on one
             of its lines; the other lines say "See ASN-xxx (ID#:yyy)". So freight is analysed per shipment.
"""
from __future__ import annotations

from functools import lru_cache
from pathlib import Path

import duckdb
import numpy as np
import pandas as pd

ROOT = Path(__file__).resolve().parents[2]
RAW = ROOT / "data" / "raw" / "SCMS_Delivery_History_Dataset_20150929.csv"
SOURCE = "USAID SCMS Delivery History Dataset (release 29 Sep 2015)"
PERIOD = "2006-2015"

COLS = {
    "ID": "line_id", "Project Code": "project_code", "PQ #": "pq", "PO / SO #": "po_so", "ASN/DN #": "shipment_id",
    "Country": "country", "Managed By": "managed_by", "Fulfill Via": "fulfill_via", "Vendor INCO Term": "inco_term",
    "Shipment Mode": "mode", "PQ First Sent to Client Date": "pq_sent_raw", "PO Sent to Vendor Date": "po_sent_raw",
    "Scheduled Delivery Date": "scheduled_raw", "Delivered to Client Date": "delivered_raw", "Delivery Recorded Date": "recorded_raw",
    "Product Group": "product_group", "Sub Classification": "sub_class", "Vendor": "vendor", "Item Description": "item",
    "Molecule/Test Type": "molecule", "Brand": "brand", "Dosage": "dosage", "Dosage Form": "dosage_form",
    "Unit of Measure (Per Pack)": "units_per_pack", "Line Item Quantity": "quantity", "Line Item Value": "value_usd",
    "Pack Price": "pack_price", "Unit Price": "unit_price", "Manufacturing Site": "manufacturing_site",
    "First Line Designation": "first_line", "Weight (Kilograms)": "weight_raw", "Freight Cost (USD)": "freight_raw",
    "Line Item Insurance (USD)": "insurance_usd",
}
ROUTES = {"Direct Drop": "Direct from vendor", "From RDC": "From regional warehouse (RDC)"}
MODES = ["Air", "Air Charter", "Truck", "Ocean"]
LATE_DAYS = 0  # a line is late when delivered after its scheduled delivery date


def _date(s: pd.Series, fmt: str) -> pd.Series:
    return pd.to_datetime(s, format=fmt, errors="coerce")


def _freight_status(raw: pd.Series) -> pd.Series:
    num = pd.to_numeric(raw, errors="coerce").notna()
    return np.select(
        [num, raw.str.startswith("See"), raw.str.startswith("Freight Included"), raw.str.startswith("Invoiced Separately")],
        ["priced", "on another line", "included in commodity cost", "invoiced separately"], "not recorded")


def load_lines() -> pd.DataFrame:
    d = pd.read_csv(RAW, encoding="latin1", dtype=str, keep_default_na=False).rename(columns=COLS)
    d["line_id"] = d.line_id.astype(int)
    d["mode"] = d["mode"].replace({"N/A": "Not recorded"})
    d["route"] = d.fulfill_via.map(ROUTES)
    d["scheduled"] = _date(d.scheduled_raw, "%d-%b-%y")
    d["delivered"] = _date(d.delivered_raw, "%d-%b-%y")
    d["recorded"] = _date(d.recorded_raw, "%d-%b-%y")
    d["po_sent"] = _date(d.po_sent_raw, "%m/%d/%Y")
    d["pq_sent"] = _date(d.pq_sent_raw, "%m/%d/%Y")
    for c in ["quantity", "value_usd", "pack_price", "unit_price", "insurance_usd", "units_per_pack"]:
        d[c] = pd.to_numeric(d[c], errors="coerce")
    d["weight_kg"] = pd.to_numeric(d.weight_raw, errors="coerce")
    d["freight_usd"] = pd.to_numeric(d.freight_raw, errors="coerce")
    d["freight_status"] = _freight_status(d.freight_raw)
    d["days_late"] = (d.delivered - d.scheduled).dt.days
    d["late"] = d.days_late > LATE_DAYS
    d["year"] = d.scheduled.dt.year
    d["po_to_delivery_days"] = (d.delivered - d.po_sent).dt.days
    d["po_to_schedule_days"] = (d.scheduled - d.po_sent).dt.days
    d["record_lag_days"] = (d.recorded - d.delivered).dt.days
    keep = ["line_id", "shipment_id", "project_code", "pq", "po_so", "country", "managed_by", "fulfill_via", "route", "inco_term",
            "mode", "product_group", "sub_class", "vendor", "item", "molecule", "brand", "dosage_form", "first_line", "quantity",
            "value_usd", "pack_price", "unit_price", "insurance_usd", "weight_kg", "freight_usd", "freight_status",
            "scheduled", "delivered", "recorded", "po_sent", "pq_sent", "days_late", "late", "year",
            "po_to_delivery_days", "po_to_schedule_days", "record_lag_days"]
    return d[keep]


def build_shipments(lines: pd.DataFrame) -> pd.DataFrame:
    g = lines.groupby("shipment_id", sort=False)
    s = g.agg(country=("country", "first"), route=("route", "first"), fulfill_via=("fulfill_via", "first"),
              mode=("mode", "first"), vendor=("vendor", "first"), inco_term=("inco_term", "first"),
              lines=("line_id", "size"), value_usd=("value_usd", "sum"), weight_kg=("weight_kg", "sum"),
              freight_usd=("freight_usd", "sum"), priced_lines=("freight_usd", "count"), weighed_lines=("weight_kg", "count"),
              scheduled=("scheduled", "max"), delivered=("delivered", "max"), po_sent=("po_sent", "min"),
              late_lines=("late", "sum"), product_group=("product_group", "first")).reset_index()
    anchor = lines.sort_values("freight_usd", na_position="last").drop_duplicates("shipment_id").set_index("shipment_id").freight_status
    s["freight_status"] = s.shipment_id.map(anchor)
    s.loc[s.priced_lines == 0, "freight_usd"] = np.nan
    s.loc[s.weighed_lines == 0, "weight_kg"] = np.nan
    s["late"] = s.late_lines > 0
    s["days_late"] = (s.delivered - s.scheduled).dt.days
    s["year"] = s.scheduled.dt.year
    s["po_to_delivery_days"] = (s.delivered - s.po_sent).dt.days
    s["po_to_schedule_days"] = (s.scheduled - s.po_sent).dt.days
    ok = (s.freight_usd > 0) & (s.weight_kg > 0)
    s["usd_per_kg"] = np.where(ok, s.freight_usd / s.weight_kg, np.nan)
    s["freight_pct_value"] = np.where((s.freight_usd > 0) & (s.value_usd > 0), s.freight_usd / s.value_usd, np.nan)
    return s.drop(columns=["priced_lines", "weighed_lines"])


@lru_cache(maxsize=1)
def con() -> duckdb.DuckDBPyConnection:
    c = duckdb.connect()
    lines = load_lines()
    shipments = build_shipments(lines)
    c.register("_lines", lines)
    c.register("_shipments", shipments)
    c.execute("CREATE TABLE lines AS SELECT * FROM _lines")
    c.execute("CREATE TABLE shipments AS SELECT * FROM _shipments")
    return c


def q(sql: str, params: list | None = None) -> pd.DataFrame:
    return con().execute(sql, params or []).df()

ISO3 = {"Afghanistan": "AFG", "Angola": "AGO", "Belize": "BLZ", "Benin": "BEN", "Botswana": "BWA", "Burkina Faso": "BFA", "Burundi": "BDI",
        "Cameroon": "CMR", "Congo, DRC": "COD", "Côte d'Ivoire": "CIV", "Dominican Republic": "DOM", "Ethiopia": "ETH", "Ghana": "GHA",
        "Guatemala": "GTM", "Guinea": "GIN", "Guyana": "GUY", "Haiti": "HTI", "Kazakhstan": "KAZ", "Kenya": "KEN", "Kyrgyzstan": "KGZ",
        "Lebanon": "LBN", "Lesotho": "LSO", "Liberia": "LBR", "Libya": "LBY", "Malawi": "MWI", "Mali": "MLI", "Mozambique": "MOZ",
        "Namibia": "NAM", "Nigeria": "NGA", "Pakistan": "PAK", "Rwanda": "RWA", "Senegal": "SEN", "Sierra Leone": "SLE",
        "South Africa": "ZAF", "South Sudan": "SSD", "Sudan": "SDN", "Swaziland": "SWZ", "Tanzania": "TZA", "Togo": "TGO",
        "Uganda": "UGA", "Vietnam": "VNM", "Zambia": "ZMB", "Zimbabwe": "ZWE"}
