# Source system and lineage

## Operational source

The source system is a pharmacy point-of-sale and inventory application represented by the PostgreSQL `oltp` schema. Its central transaction grains are:

- **Sales:** one `sales_line` per source sales row. Multiple lines may share an invoice number.
- **Inventory:** one `inventory_movement` per source stock-ledger row, product and warehouse. A movement is not assigned a product batch or sales line without source evidence.
- **Reference and header records:** products, manufacturers, drug classes, categories, units, cashiers, warehouses, sales invoices, inventory documents and product batches.

Numeric OLTP identifiers are database identities. They identify rows in that database; they do not represent source order, business codes, or time. `source_dataset` and `source_row_number` identify source rows for the two transaction tables.

The optional CSV bootstrap reconstructs OLTP. The operational DW extracts from the transactional database and does not preprocess or read the original CSVs at runtime. See the [OLTP source model](data-model.md) and the [bootstrap implementation guide](../src/inventory_dw_dss/oltp_ingestion/README.md).

## Export lineage evidence

The supplied export has a validated row sequence for this export vintage. `RowNumber` is retained as `source_row_number` in PostgreSQL and as `dataset_row_number` in ClickHouse Staging and Intermediate. Generated identity keys are separate. Within inventory product–warehouse ledgers, ordering by this source sequence preserves the validated observation order; it is not a general POS-native event sequence or a CDC version.

The 2026-11-08 validation compared source records through six available layers: original and prepared exports, PostgreSQL, ClickHouse raw, Staging and enriched Intermediate. For the scoped `pharmacy_2023_2025` export, it found 804,027 inventory rows and 649,656 sales rows with unique, non-null, gap-free source sequences; payload and identifier comparisons matched at each hop. Inventory continuity had 188 observed gaps across 8,147 product–warehouse ledgers. These are dated validation results for one export, not permanent constraints or proof of physical stock.

The passport fingerprints bind ordered source rows to normalized content. The research provenance for how the workbook's displayed row number became CSV `RowNumber` was supplied separately; the original workbook was unavailable for independent re-extraction. Detailed fingerprint serialization and validator behavior belong to the [validation code guide](../src/inventory_dw_dss/validation/README.md). The immutable passport is retained under [`data/reference`](../data/reference/README.md).

## Source limitations

- Event timestamps do not establish when a late arrival or correction became known. The export has no historical arrival/correction timestamp.
- A generated OLTP identity is not a valid substitute for the validated export sequence.
- Sales lines have no verified sales warehouse, completion/cancellation status or matched stock return.
- Inventory descriptions include unclassified records. `UNKNOWN`, both recorded directions of `RETURN`, negative balances and zero-flow rows are preserved as observed.
- Inventory movements do not provide a verified batch relationship. A shared invoice/document number is not evidence of a line-to-line match.

For analytical meaning and safe use, see [data semantics](data-semantics.md). For schemas and relationship grains, see [data model](data-model.md).

## Export fields and operational mapping

The supplied sales export has 35 fields (649,656 rows); the stock export has 15 fields (804,027 rows). `RowNumber` below is the retained source sequence described above. Examples are representative source values.

### Sales export

| Source field | Business meaning | Example |
|---|---|---|
| `RowNumber` | Export row sequence | `1` |
| `DateTime` | Recorded sales event time | `02 Jan 2023 07:55:43` |
| `Shift` | Combined shift date, period and cashier code | `20230102-PAGI-Cashier_009` |
| `CashierID` | Pseudonymous cashier code | `Cashier_009` |
| `InvoiceNumber` | Sales invoice code | `PJ2301020001` |
| `Manufacturer` | Recorded manufacturer/brand label | `Bufa Aneka`; `-` |
| `DrugClass` | Recorded regulatory drug class | `Obat Keras`; `-` |
| `Category` | POS merchandise category | `Patent`; `OTC`; `Alkes` |
| `DrugCode` | Product catalog code | `SW2106000281` |
| `DrugName` | Recorded product name | `Fasidol Forte Syr 60ml` |
| `BatchAndExpiryDate` | Combined batch and expiry label | `20229 (ED : 2024-09-01)` |
| `PrescriptionNumber` | Recorded prescription reference | blank; `super` |
| `PatientID` | Pseudonymous patient code | `Patient_002` |
| `DoctorID` | Prescriber code | blank in the supplied export |
| `SalespersonID` | Pseudonymous salesperson code | `Salesperson_001` |
| `Quantity` | Recorded sold quantity | `1.0`; `10.0` |
| `Unit` | Unit for the sold quantity | `Fls`; `Tab`; `Pcs` |
| `PriceTier` | POS price tier | `Harga Jual 1` |
| `UnitPrice` | Recorded price per source unit | `8000` |
| `SalesPromo` | Sales-promotion indicator/details | blank in the supplied export |
| `PromoName` | Promotion name | blank in the supplied export |
| `DiscountPct` | Recorded discount percentage | `0%`; `5%` |
| `DiscountAmount` | Recorded discount amount | `0`; `2000` |
| `ServiceFee` | Recorded service fee | `0`; `200` |
| `PackagingFee` | Recorded packaging fee | `0`; `200` |
| `TaxInvoiceNumber` | Tax invoice reference | blank; `f` |
| `Subtotal` | Recorded pre-adjustment line amount | `8000`; `52000` |
| `InvoiceDiscountPct` | Recorded invoice-discount percentage | `0%` |
| `IsMember` | POS membership label | `Non Member` |
| `PromoDiscountPct` | Recorded promotion-discount percentage | `0%` |
| `TaxAmount` | Source field containing a recorded percentage | `0%` |
| `AdditionalFee` | Recorded additional fee | `0` |
| `PaymentType` | Recorded payment method | `TUNAI`; `KARTU`; `KREDIT` |
| `PrintCount` | Receipt/ invoice print count | `0`; `1` |
| `TotalPrice` | Final amount recorded on this source row | `8000`; `52000` |

### Stock export

| Source field | Business meaning | Example |
|---|---|---|
| `RowNumber` | Export row sequence | `1` |
| `DateTime` | Recorded inventory event time | `02 Jan 2023 07:55:43` |
| `Warehouse` | Inventory location | `Apotek`; `Gudang Obat 1` |
| `DrugCode` | Product catalog code | `SW2106000281` |
| `DrugName` | Recorded product name | `Fasidol Forte Syr 60ml` |
| `DocumentNumber` | Referenced inventory document code | `PJ2301020001` |
| `TransactionDescription` | Source description of the recorded event | `Penjualan dengan No Faktur :PJ2301020001`; `mutasi` |
| `InitialStock` | Recorded quantity before the movement | `17 Fls` |
| `StockIn` | Recorded inbound quantity | `0 Fls` |
| `StockOut` | Recorded outbound quantity | `1 Fls` |
| `RemainingStock` | Recorded quantity after the movement | `16 Fls` |
| `DrugClass` | Recorded regulatory drug class | `Obat Keras`; `-` |
| `Category` | POS merchandise category | `Patent`; `OTC`; `Alkes` |
| `DrugType` | POS product-management type | `NON KONSINYASI`; `KONSINYASI` |
| `Status` | POS product status | `Aktif` |

Source percentage, quantity and amount fields may be text-formatted: percentages include `%` and may use a decimal comma; quantity strings combine numeric value and unit and may use a dot as a thousands separator. A literal `-` is a source marker, not an empty CSV value. OLTP converts only known missing markers and preserves source transaction text needed for lineage. `DoctorID`, `SalesPromo` and `PromoName` are empty in this export. `PrescriptionNumber`, `PatientID`, `SalespersonID` and `TaxInvoiceNumber` are intentionally not mapped to the current OLTP schema; their existence in the original export does not create a DW analytical relationship.

## Observed source grouping variation

In this export, 223 invoice codes occur at multiple event times, 222 at multiple shift/cashier values and 5 at multiple payment types. Invoice discount percentage and print count are consistent per invoice code in this snapshot, but remain on sales lines. The observed variation is why a sales invoice header is only a source-code grouping, not a place to assign one presumed common event time, cashier, payment type or fee total.

Inventory has 404,180 distinct document codes; 179,466 occur at multiple times, 8,528 at multiple warehouses, 901 at multiple descriptions and 1,550 at multiple product types. A document number therefore does not identify one inferred event-time/location context. These statistics describe the supplied export vintage and do not constrain future source data.
