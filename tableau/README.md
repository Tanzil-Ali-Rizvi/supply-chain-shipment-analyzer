# Tableau dashboard

Live: [Supply Chain Shipment Analyzer on Tableau Public](https://public.tableau.com/app/profile/tanzil.ali.rizvi/viz/SupplyChainShipmentAnalyzerv4/DeliveryFreightOverview)

Two dashboards built on governed extracts: **Delivery & Freight Overview** and **Freight, Vendors & Mode Shift**.

| File | What it is |
|---|---|
| `build_workbook.py` | Generates `Supply Chain Shipment Analyzer.twb` (datasources, calculated fields, 13 worksheets, 2 dashboards). Validated against Tableau's workbook XSD. |
| `make_extracts.py` | Writes each `data/*.csv` as a Hyper extract (Tableau Public requires extracts). |
| `data/*.csv` | Written by `scripts/export_tableau.py` from `src/shipiq/metrics.py`; six headline numbers are reconciled before writing. |

Rebuild:

```bash
python scripts/export_tableau.py
pip install tableauhyperapi && python tableau/make_extracts.py
python tableau/build_workbook.py --data-dir "C:/path/to/folder/with/extracts"
```

Copy the `.hyper` files and the `.twb` to that folder, open the `.twb` in Tableau Public or Desktop, and save to Tableau Public.

**Tableau calculated fields** (they reproduce the Python KPIs):

| Field | Formula |
|---|---|
| On-time rate | `1 - SUM([late]) / SUM([lines])` |
| Late rate | `SUM([late]) / SUM([lines])` |
| Value delivered late ($M) | `SUM([late_value_usd]) / 1000000` |
| Warehouse late rate | `SUM(IF [route] = 'Warehouse (RDC)' THEN [late] END) / SUM(IF [route] = 'Warehouse (RDC)' THEN [lines] END)` |
| Freight $ per kg | `SUM([freight_usd]) / SUM([weight_kg])` |
| Air share of freight | `SUM(IF [mode] = 'Air' THEN [freight_usd] END) / SUM([freight_usd])` |
| Median freight $ per kg | `MEDIAN([freight_usd] / [weight_kg])` |
