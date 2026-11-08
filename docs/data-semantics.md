# Data semantics

Use these rules when interpreting the warehouse. Reconciliation demonstrates agreement with recorded source data; it cannot establish facts the source does not record.

| Concept | Meaning | Safe interpretation |
|---|---|---|
| Recorded sales vs demand | Sales rows have no verified completion/cancellation state or matched return. | Call measures recorded sales; do not claim net sales, fulfilled demand or lost demand. |
| Original vs converted quantity | `sold_quantity` is in its recorded `unit_id`; `stock_unit_qty` exists only for verified identity or approved conversion. | Preserve original values. Unresolved conversion is NULL, never zero. |
| Flow vs balance | Received/issued/delta are flows; opening and closing are recorded balances. | Sum compatible flows; do not sum balances across observations. |
| Observed vs available stock | Recorded closing is not a proven physical, allocatable or available quantity. | Treat it as an observation with its recorded scope and timestamp. |
| Missing vs zero | An absent date means no observation in the export; a recorded zero is a value. | Do not generate zero sales, stock or demand for absent dates. |
| Code vs ID | Product codes and unit labels are business values; numeric product/unit IDs identify OLTP rows. | Join facts to dimensions by numeric IDs; match governed UOM references by exact source code and unit label. |
| Sequence vs time | `dataset_row_number` is validated export order; event time may tie. | Use source sequence for this export's ledger ordering, not generated IDs. |
| Current vs recorded attributes | Product dimension labels are current Type 1 catalog values; facts retain transaction-recorded attributes. | Dimension joins do not reproduce historical catalog versions. |

## Quantity examples

Sales of `2 Box` and `5 Tab` are separate original-unit measures. If a governed approved mapping says 10 Tab per Box and the product's verified stock unit is Tab, the converted quantities are 20 and 5 Tab. If the factor is only a candidate or is otherwise unresolved, the conversion remains NULL. Report conversion coverage with totals so NULL results do not disappear silently. Even stock-unit quantities are product-specific: tablets, bottles and packs from different products are not one common measure.

## Inventory examples

An observed closing of 10 on Monday and 7 on Tuesday represents two balances, not a total of 17. If Tuesday's closing is absent, the model does not carry Monday forward. Within a movement, opening 10 + inbound 5 − outbound 3 = closing 12 is one recorded balance equation. A following opening of 20 starts a discontinuous segment; the difference is diagnostic, not a receipt.

`recorded_delta_qty` is inbound minus outbound based on the recorded quantity columns, independent of movement classification. RETURN direction, UNKNOWN labels, negative quantities/balances and zero-flow rows remain as recorded. No return is linked to a sales line.

## Financial and temporal limits

Fees and percentages retained on sales rows have no fully verified invoice-vs-line allocation contract. Do not derive an invoice total or certified net revenue by summing or reallocating them without further evidence. The source timestamp and export order do not reveal when an old transaction or correction arrived. Historical availability, reservations, stock allocation and physical-count truth cannot be reconstructed from the available observations.

For model-level calculations and column contracts, see the [Intermediate](../transform/dbt/models/intermediate/README.md) and [Marts](../transform/dbt/models/marts/README.md) guides. UOM mapping scope and provenance are described in the [governed seed guide](../transform/dbt/seeds/README.md).
