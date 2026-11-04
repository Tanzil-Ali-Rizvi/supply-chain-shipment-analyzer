# Findings memo: where the health-commodity supply chain loses time and money

**To:** Head of supply chain operations · **Data:** USAID SCMS Delivery History Dataset, 10,324 line items in 7,030 shipments of HIV and malaria medicines and test kits to 43 countries, scheduled 2006-2015, $1,627.6M of commodities and $68.7M of recorded freight.

## The answer in one paragraph

88.5% of line items arrived on or before their scheduled date, but only 84.1% by value: **$259.0M of medicines and test kits arrived late**, a median 12 days late. The delay is not spread evenly. **Shipments from the regional warehouses (RDCs) run late 17.2% of the time against 5.3% for shipments direct from vendors**, and the gap holds when like is compared with like: within the same country, year and transport mode, warehouse lines had **6.1x the odds** of arriving late (127 groups, 4,836 lines, permutation p = 0.001). Warehouse lanes hold 78% of the value delivered late, and five lanes hold 61%. On cost, **air carries 62.5% of the freight bill at $5.26/kg against $1.85/kg by ocean**, and small shipments pay over ten times the rate of large ones. Two fixes follow: repair warehouse replenishment and dispatch, starting with Mozambique, Nigeria and Zambia; and stop flying heavy orders that were planned months ahead, which would have saved about $1.73M on 140 shipments.

## 1. Delivery: the warehouse route is the problem, and it got worse

| Route | Line items | Commodity value | Late |
|---|---|---|---|
| From regional warehouse (RDC) | 5,404 | $1,085.4M | 17.2% |
| Direct from vendor | 4,920 | $542.2M | 5.3% |

The raw gap could come from where and how the warehouses ship, so I compared only country-year-mode groups that used both routes. The warehouse route stays far worse (odds ratio 6.1, p = 0.001 from 1,000 shuffles of the route label within each group). The trend matters more than the average: the warehouse route was on par with direct shipping until 2009, hit **37.2% late in 2011** (direct: 11.3%), and stayed at **30.0% late across 2013-2015** while direct shipments improved to 3.9%.

**Where to act first**, by value delivered late:

| Lane | Value late | Late rate | Median days late |
|---|---|---|---|
| Mozambique, from RDC | $52.19M | 22.1% | 14 |
| Nigeria, from RDC | $33.24M | 9.3% | 8 |
| Zambia, from RDC | $30.63M | 17.6% | 10 |
| South Africa, direct | $24.79M | 8.2% | 31 |
| Tanzania, from RDC | $17.84M | 18.6% | 19 |

South Africa is the exception: it is served only direct, mostly by truck from local wholesalers who are almost never late (S. Buys 1.5%, Pharmacy Direct 0%). Its late lines are imported orders from Aurobindo (35.4% late) and Cipla (37.7%), mostly by ocean, and they run long (median 31 days), so the fix there is those vendors' import lead times, not the warehouse.

**Vendors** (direct shipments, 20+ line items): Aurobindo Pharma was late on 14.1% of lines with a median 27 days late; Orgenics on 13.0% (median 5 days); Cipla on 13.1% (median 33 days). The local wholesaler S. Buys was late on 1.5%. All direct shipments together: 5.3%.

## 2. Freight: air is most of the bill, and small shipments pay over ten times the rate

| Mode | Priced shipments | Freight | Share | $/kg | Median days PO to delivery |
|---|---|---|---|---|---|
| Air | 4,096 | $43.0M | 62.5% | $5.26 | 99 |
| Truck | 1,162 | $11.9M | 17.3% | $1.59 | 4 |
| Air charter | 423 | $8.9M | 12.9% | $2.73 | 64 |
| Ocean | 282 | $3.6M | 5.2% | $1.85 | 167 |

Size matters as much as mode. **1,016 shipments under 100 kg (16.5% of priced shipments) paid a median $30.6/kg**, and freight was 34.5% of their commodity value; shipments of 2 t or more paid $2.6/kg. Consolidating small orders to the same country is a direct saving.

**Mode-shift scenario.** Ocean takes a median 174 days from purchase order to delivery against 95 by air, so ocean is only an option when the order is placed early. Air shipments of 1,000 kg or more whose purchase order went out at least 180 days before the scheduled delivery: **140 of 4,096 air shipments qualify. They cost $2.39M by air and would have cost about $0.71M at ocean rates, a saving of about $1.73M** (4.0% of all air freight), led by Rwanda ($0.53M), Zimbabwe ($0.32M) and Zambia ($0.26M). The thresholds are adjustable in the app; the estimate uses each country's own ocean rate where it has 5+ ocean shipments and never counts a shipment as cheaper by air.

## 3. Data you should not trust yet

- 832 of 7,030 shipments (11.8%) have no freight cost of their own: 593 have freight included in the commodity price and 239 were invoiced separately. Freight totals here are for priced shipments only.
- 40% of line items carry their freight on another line of the same shipment ("See ASN-..."), so freight must be analysed per shipment, never per line.
- 18.5% of deliveries were recorded in the system after the delivery date, which delays any on-time report built from recorded dates.
- 360 line items have no transport mode, and 328 direct shipments have no purchase-order date (lead time unknown).

## Recommendations

1. **Warehouse service recovery, three countries first.** Mozambique, Nigeria and Zambia warehouse lanes hold $116M of late value. Review replenishment triggers and dispatch lead times against the promised dates; report warehouse on-time weekly by country.
2. **Promise dates that match the route.** Warehouse lines are promised from stock; when the warehouse is short, the order should be re-promised or switched to direct, not left to slip.
3. **Ocean by default for heavy, early orders.** Any order of 1 t or more placed 180+ days before need goes by sea unless an exception is approved.
4. **Consolidate small shipments.** Batch sub-100 kg orders per country per month.
5. **Fix freight capture.** Record freight and weight on every shipment and stamp delivery dates on the day.

## Method and limits

- On-time = delivered on or before the scheduled delivery date in the source; the dataset does not record whether a date was renegotiated.
- Freight is analysed per shipment (ASN/DN number), using shipments with both freight cost and weight recorded.
- The scenario is an estimate on historical rates; it ignores port capacity and the inventory cost of longer transit.
- Observational data: the route comparison controls for country, year and mode but not for every reason an order was sent through the warehouse.
