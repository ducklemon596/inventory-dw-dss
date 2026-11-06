# Daily Retail Pharmacy Sales and Stock Dataset from Indonesia (2023–2025)

This repository accompanies the Data in Brief article of the same title. It contains retrospective
sales-transaction and stock-movement records from a single privately-owned retail pharmacy in
Indonesia, covering 2 January 2023 – 31 December 2025, in both **Raw** and **Processed** form.

## Repository structure

```
.
├── README.md
├── raw_dataset/
│   ├── sales_raw.csv          (649,656 rows × 35 columns)
│   └── stock_raw.csv          (804,027 rows × 15 columns)
├── processed_dataset/
│   ├── sales_processed.csv    (627,389 rows × 35 columns)
│   ├── stock_processed.csv    (775,560 rows × 21 columns)
│   └── EDA Notebook/
│       ├── EDA_Analysis.ipynb
│       ├── 01_Sales_Temporal_Trends.png
│       ├── 02_Sales_Data_Composition.png
│       ├── 03_Stock_Movements.png
│       └── 04_Temporal_Patterns.png
└── processing script/
    ├── generate_raw.py
    └── generate_processed.py
```

`generate_raw.py` produces the Raw CSVs from the original Excel exports (header-row removal, PII
anonymization, column-header translation to English). `generate_processed.py` produces the
Processed CSVs from the Raw CSVs (category filtering, datetime/quantity parsing, value cleaning).

## Reproducing the dataset

Requirements: Python 3 (developed and tested with Python 3.13) with `pandas` and `openpyxl`
(`pip install pandas openpyxl`).

Both scripts work with the folder layout shown above and can be started from any working
directory. `--root` is the dataset folder, i.e. the folder that contains `raw_dataset/`,
`processed_dataset/` and `processing script/`. If `--root` is left out, the parent folder of
`processing script/` is used, so for the layout above no option is needed at all.

**1. Processed dataset, from the published Raw CSVs** (no additional files needed):

```
python "processing script/generate_processed.py" --root "path/to/dataset"
```

This reads `raw_dataset/sales_raw.csv` and `raw_dataset/stock_raw.csv` and writes
`processed_dataset/sales_processed.csv` and `processed_dataset/stock_processed.csv`.

**2. Raw dataset, from the original Excel exports.** The original exports (`Sales 2023-2025.xlsx`
and `Stock 2023-2025.xlsx`) contain personal information and are therefore **not** part of this
dataset, so this step can only be reproduced by whoever holds them:

```
python "processing script/generate_raw.py" --root "path/to/dataset"
```

The two Excel files are expected inside the dataset folder. If they are stored elsewhere, point to
each file with its own option (`--sales` and `--stock`, also accepted as `--sales-input` and
`--stock-input`):

```
python "processing script/generate_raw.py" --root "path/to/dataset" --sales "path/to/Sales 2023-2025.xlsx" --stock "path/to/Stock 2023-2025.xlsx"
```

The script writes `raw_dataset/sales_raw.csv` and
`raw_dataset/stock_raw.csv`, plus the private file `_PRIVATE_anonymization_map.csv` (see the PII
section below), which must not be shared.

## Raw vs. Processed — what's different

Both versions now have **English column headers**. The difference between them is **not**
language, it's cleanliness:

- **Raw**: column headers translated, but *values* are exactly as exported from the POS system (apart
  from the anonymization of personal names, see the PII section) —
  free text, Indonesian-formatted numbers (comma decimal, dot thousands separator), combined
  fields not yet split, inconsistent spelling in free-text fields.
- **Processed**: values parsed, cleaned, and standardized — datetimes split into components,
  numeric fields converted to proper numeric types, free-text transaction descriptions
  normalized into a fixed set of categories, non-pharmaceutical product categories excluded.

A handful of Raw columns keep a distinct name from their Processed counterpart specifically
*because* their values aren't cleaned yet — e.g. Raw's `PriceTier` still holds text like
`"Harga Jual 1"` where Processed's `PriceTier` holds the integer `1`. Where a Raw field is later
split into multiple Processed columns (or vice versa), the Raw column uses a distinct name
(`DateTime`, `BatchAndExpiryDate`, `TransactionDescription`) rather than reusing one of the
Processed names, so it's never ambiguous which version of a file you're looking at.

## Column translation reference — Sales

**Indonesian → English (Raw column names)**

| Indonesian | English | | Indonesian | English |
|---|---|---|---|---|
| No | RowNumber | | No. Faktur Pajak | TaxInvoiceNumber |
| Tanggal | DateTime | | Subtotal | Subtotal |
| Shift | Shift | | Diskon Faktur | InvoiceDiscountPct |
| Kasir | CashierID | | Promo Member | IsMember |
| No. Faktur | InvoiceNumber | | Diskon Promo | PromoDiscountPct |
| Pabrik | Manufacturer | | Pajak Faktur | TaxAmount |
| Golongan | DrugClass | | Biaya | AdditionalFee |
| Kategori | Category | | Jenis | PaymentType |
| Kode Obat | DrugCode | | Jumlah Cetak | PrintCount |
| Nama Obat | DrugName | | Total | TotalPrice |
| No. Batch & ED | BatchAndExpiryDate | | No. Resep | PrescriptionNumber |
| Jumlah | Quantity | | Nama Pasien | PatientID |
| Satuan | Unit | | Nama Dokter | DoctorID |
| Harga Jual | PriceTier | | Sales | SalespersonID |
| Harga | UnitPrice | | Promo Penjualan | SalesPromo |
| Diskon | DiscountPct | | Nama Promo | PromoName |
| Nominal Diskon | DiscountAmount | | | |
| Tuslah | ServiceFee | | | |
| Embalase | PackagingFee | | | |

**Where Raw and Processed differ** (everything not listed here keeps the same name and same values)

| Raw column | Becomes in Processed |
|---|---|
| DateTime | Split into `Date`, `Year`, `Month`, `Day`, `DayOfWeek`, `Time`, `Hour` |
| Shift | Trimmed to `ShiftPeriod` (`PAGI` or `SORE`, upper-cased; the pharmacy has no night shift) |
| BatchAndExpiryDate | Split into `BatchNumber`, `ExpiryDate` |
| PriceTier | Text label (`"Harga Jual 1"`) → integer `1`/`2`/`3` |
| DiscountPct, InvoiceDiscountPct, PromoDiscountPct, TaxAmount | `"8%"` string → float `8.0` |
| IsMember | Member-type text → binary `0`/`1` (constant `0` here: see note below) |

**Constant columns kept as exported.** Four Sales columns hold a single value in every row:
`IsMember` (always `Non Member`, i.e. `0` after processing, because the pharmacy did not use the POS
membership feature), `TaxAmount` (always `0%`, because tax is accounted for outside this report),
`PromoDiscountPct` (always `0%`) and `AdditionalFee` (always `0`). Likewise, `Status` in the Stock
tables is always `Aktif`. They are retained so that the schema matches the POS export.

**Dropped in Processed** (zero or near-zero fill rate; `PatientID` also on PII grounds)

`PrescriptionNumber`, `PatientID`, `DoctorID`, `SalespersonID`, `SalesPromo`, `PromoName`, `TaxInvoiceNumber`

## Column translation reference — Stock

**Indonesian → English (Raw column names)**

| Indonesian | English |
|---|---|
| No. | RowNumber |
| Tanggal | DateTime |
| Gudang | Warehouse |
| Kode Obat | DrugCode |
| Nama Obat | DrugName |
| No. Bukti | DocumentNumber |
| Keterangan | TransactionDescription |
| Stok Awal | InitialStock |
| Masuk | StockIn |
| Keluar | StockOut |
| Sisa Stok | RemainingStock |
| Golongan | DrugClass |
| Kategori | Category |
| Jenis Obat | DrugType |
| Status | Status |

**Where Raw and Processed differ** (everything not listed here keeps the same name and same values)

| Raw column | Becomes in Processed |
|---|---|
| DateTime | Split into `Date`, `Year`, `Month`, `Day`, `DayOfWeek`, `Time`, `Hour` |
| TransactionDescription | Free text normalized into `TransactionType`: Penjualan, Mutasi, Stokopname, Import Stokopname, Import Data Obat, Tambah Master Obat, Retur, Test Entry, or `Pembelian (SupplierName)` (purchases keep the supplier name in parentheses; 133 distinct values). Over 70 spelling variants of "Mutasi" were merged into the single value `Mutasi`. |
| InitialStock, StockIn, StockOut, RemainingStock | `"17 Fls"` string → integer quantity (negative stock levels such as `"-10 Tab"` are kept), with the unit split into its own `Unit` column |

**Dropped in Processed**

`Warehouse`. In the Raw file it only tags the storage location a movement was booked in at the same
pharmacy: `Apotek` (the sales floor, 742,242 rows) or `Gudang Obat 1` (a storage room upstairs, 61,785
rows, from July 2023). It is not needed for pharmacy-level demand or inventory analysis, so it is not
carried into the Processed file; **stock levels in `stock_processed.csv` therefore combine both locations.**
Use `stock_raw.csv` if the split by location is needed.

## Days without records
The sales file has no records on 8 calendar days: 1 January 2023, 2024 and 2025; Eid al-Fitr
(22 April 2023, 10 April 2024, 31 March 2025); and 9–10 October 2025 (pharmacy closed for a
staff event). The stock file has no records on the first six of these dates only.

## Personally identifiable information (PII)

The following columns contained PII in the original export and were anonymized to sequential ID
codes (e.g. `Cashier_001`, `Patient_001`) before this dataset was compiled: cashier names, patient
names, doctor names, and salesperson names. In the Stock export, the POS also writes the customer's
name into the free-text `TransactionDescription` of some sales (`...,Pasien :<name>`); these names
are replaced by the same `Patient_xxx` ID that the person has in the Sales file. The mapping between original names and anonymized
IDs is kept in a private file (`_PRIVATE_anonymization_map.csv`) that is **not** included in this
public repository.

## Category exclusions

Three non-pharmaceutical product categories present in the original POS export — Alkes (medical
equipment), Baby (baby products), and Minuman (beverages) — fall outside the scope of this
dataset and are excluded from the Processed version. They remain present in the Raw version.

## Citation

Please cite the accompanying Data in Brief article when using this dataset. See the article for
full authorship, funding, and ethics information.
