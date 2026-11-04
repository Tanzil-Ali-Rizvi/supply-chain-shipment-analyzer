# KPI definitions

All figures come from `src/shipiq/metrics.py`; the app, the memo, the Tableau extract and the assistant read the same functions.

| KPI | Definition | Grain |
|---|---|---|
| On-time delivery (OTD) | Line items delivered on or before the scheduled delivery date ÷ all line items | Line item |
| OTD by value | Commodity value of on-time line items ÷ all commodity value | Line item |
| Value delivered late | Sum of line item value where delivered date > scheduled date | Line item |
| Days late | Delivered date − scheduled date, for late lines (median reported) | Line item |
| Route | "Direct from vendor" (Direct Drop) or "From regional warehouse (RDC)" | Line item |
| Like-for-like route effect | Mantel-Haenszel odds ratio of lateness, warehouse vs direct, pooled over country × year × mode groups that used both routes; p-value from 1,000 shuffles of the route label within each group (seed 7) | Line item |
| Lane | Country × route | Line item |
| Freight $/kg | Shipment freight cost ÷ shipment weight; shipments with both recorded ("priced") | Shipment (ASN/DN) |
| Freight share of value | Shipment freight cost ÷ commodity value of the shipment | Shipment |
| Lead time | Delivered date − PO sent to vendor date (direct shipments only; warehouse lines have no PO) | Shipment |
| Planning window | Scheduled delivery date − PO sent to vendor date | Shipment |
| Mode-shift saving | For air shipments ≥ min kg with planning window ≥ min days: air freight − weight × ocean $/kg (country median with 5+ ocean shipments, else overall median), floored at 0 per shipment | Shipment |
| Vendor scorecard | Direct-shipment line items per vendor, vendors with 20+ lines | Line item |

**Why shipment grain for freight.** Freight and weight are entered once per shipment, on one line; the other lines say "See ASN-xxx (ID#:yyy)". All 2,445 such references resolve to a line in the same shipment, and no shipment has more than one priced line.
