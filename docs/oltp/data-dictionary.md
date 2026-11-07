# Báo cáo từ điển dữ liệu

Từ điển này mô tả các cột trong hai tệp CSV hiện có: `sales_raw.csv` (bán hàng) và `stock_raw.csv` (biến động tồn kho). Tên cột được giữ nguyên như trong tệp. Các ví dụ là giá trị thực đã có trong dữ liệu; ID nhân viên/khách hàng đã được ẩn danh.

## `sales_raw.csv`

**Quy mô:** 649.656 bản ghi, 35 cột. Một dòng biểu diễn một mặt hàng bán trên hóa đơn; nhiều dòng có thể thuộc cùng hóa đơn.

| Cột | Ý nghĩa | Ví dụ |
|---|---|---|
| `RowNumber` | Số thứ tự dòng trong tệp xuất | `1` |
| `DateTime` | Thời điểm ghi nhận giao dịch | `02 Jan 2023 07:55:43` |
| `Shift` | Mã ca/ngày gộp ngày, buổi và thu ngân | `20230102-PAGI-Cashier_009` |
| `CashierID` | Mã ẩn danh thu ngân | `Cashier_009` |
| `InvoiceNumber` | Mã hóa đơn bán | `PJ2301020001` |
| `Manufacturer` | Nhà sản xuất/nhãn hãng thuốc | `Bufa Aneka`; `-` |
| `DrugClass` | Phân loại pháp lý của thuốc | `Obat Keras`; `-` |
| `Category` | Nhóm hàng theo hệ thống bán hàng | `Patent`; `OTC`; `Alkes` |
| `DrugCode` | Mã mặt hàng trong danh mục | `SW2106000281` |
| `DrugName` | Tên mặt hàng | `Fasidol Forte Syr 60ml` |
| `BatchAndExpiryDate` | Số lô và hạn dùng được ghép trong một chuỗi | `20229 (ED : 2024-09-01)` |
| `PrescriptionNumber` | Số đơn thuốc nếu được ghi nhận | Thường để trống; `super` |
| `PatientID` | Mã ẩn danh bệnh nhân khi có dữ liệu | `Patient_002` |
| `DoctorID` | Mã ẩn danh bác sĩ nếu được ghi nhận | Trống trong toàn bộ tệp |
| `SalespersonID` | Mã ẩn danh nhân viên bán hàng nếu được ghi nhận | `Salesperson_001` |
| `Quantity` | Số lượng bán của mặt hàng | `1.0`; `10.0` |
| `Unit` | Đơn vị tính của số lượng | `Fls`; `Tab`; `Pcs` |
| `PriceTier` | Bậc giá bán được POS chọn | `Harga Jual 1` |
| `UnitPrice` | Đơn giá mỗi đơn vị tính | `8000` |
| `SalesPromo` | Thông tin chương trình khuyến mại bán hàng | Trống trong toàn bộ tệp |
| `PromoName` | Tên chương trình khuyến mại | Trống trong toàn bộ tệp |
| `DiscountPct` | Tỷ lệ giảm giá ở dòng hàng | `0%`; `5%` |
| `DiscountAmount` | Số tiền giảm tại dòng hàng | `0`; `2000` |
| `ServiceFee` | Phí dịch vụ | `0`; `200` |
| `PackagingFee` | Phí bao bì/đóng gói | `0`; `200` |
| `TaxInvoiceNumber` | Số hóa đơn thuế nếu có | Thường trống; `f` |
| `Subtotal` | Thành tiền trước các điều chỉnh cấp hóa đơn | `8000`; `52000` |
| `InvoiceDiscountPct` | Tỷ lệ chiết khấu ở cấp hóa đơn | `0%` |
| `IsMember` | Trạng thái thành viên trên POS | `Non Member` |
| `PromoDiscountPct` | Tỷ lệ giảm giá khuyến mại | `0%` |
| `TaxAmount` | Thuế được ghi nhận trên dòng/hóa đơn | `0%` |
| `AdditionalFee` | Phí bổ sung | `0` |
| `PaymentType` | Phương thức thanh toán | `TUNAI`; `KARTU`; `KREDIT` |
| `PrintCount` | Số lần in hóa đơn/phiếu | `0`; `1` |
| `TotalPrice` | Tổng tiền cuối cùng được ghi cho dòng bán | `8000`; `52000` |

## `stock_raw.csv`

**Quy mô:** 804.027 bản ghi, 15 cột. Một dòng biểu diễn một sự kiện biến động tồn kho cho một mặt hàng tại một địa điểm.

| Cột | Ý nghĩa | Ví dụ |
|---|---|---|
| `RowNumber` | Số thứ tự dòng trong tệp xuất | `1` |
| `DateTime` | Thời điểm ghi nhận biến động tồn kho | `02 Jan 2023 07:55:43` |
| `Warehouse` | Địa điểm/kho nơi giao dịch được ghi nhận | `Apotek`; `Gudang Obat 1` |
| `DrugCode` | Mã mặt hàng trong danh mục | `SW2106000281` |
| `DrugName` | Tên mặt hàng | `Fasidol Forte Syr 60ml` |
| `DocumentNumber` | Số chứng từ liên quan đến biến động | `PJ2301020001` |
| `TransactionDescription` | Mô tả gốc về loại nghiệp vụ hoặc giao dịch | `Penjualan dengan No Faktur :PJ2301020001`; `mutasi` |
| `InitialStock` | Tồn trước khi áp dụng biến động | `17 Fls` |
| `StockIn` | Số lượng nhập vào trong giao dịch | `0 Fls` |
| `StockOut` | Số lượng xuất ra trong giao dịch | `1 Fls` |
| `RemainingStock` | Tồn sau giao dịch | `16 Fls` |
| `DrugClass` | Phân loại pháp lý của thuốc | `Obat Keras`; `-` |
| `Category` | Nhóm hàng theo hệ thống bán hàng | `Patent`; `OTC`; `Alkes` |
| `DrugType` | Loại quản lý hàng, ví dụ hàng ký gửi | `NON KONSINYASI`; `KONSINYASI` |
| `Status` | Trạng thái mặt hàng trên hệ thống | `Aktif` |

## Lưu ý đọc dữ liệu

- Các số tiền trong CSV là chuỗi ký tự, hiện ví dụ dùng số nguyên như `8000`; cần chuyển kiểu trước khi tính toán.
- Phần trăm trong sales được lưu dưới dạng chuỗi có ký hiệu `%`; một số giá trị dùng dấu phẩy thập phân, ví dụ `2,86%`.
- Các trường tồn kho ghép số lượng và đơn vị trong cùng chuỗi, ví dụ `17 Fls`, `199.271 Pcs`.
- `-` là giá trị được xuất ra như một dấu gạch, không phải ô rỗng. Cần quyết định riêng khi làm sạch liệu nó có đại diện cho “không rõ/không áp dụng” hay không.
- Các tên nghiệp vụ trong `TransactionDescription`, phân loại và đơn vị dùng nhãn gốc của hệ thống POS; có thể có cách viết không đồng nhất.
- Tệp sales có nhiều dòng cho một hóa đơn. Không xem `InvoiceNumber` là khóa duy nhất của từng dòng hàng.


## Phạm vi ánh xạ vào OLTP

- Sales ánh xạ 28/35 cột; stock ánh xạ đầy đủ 15/15 cột. Mã sản phẩm, hóa đơn, chứng từ, thu ngân, kho và đơn vị truy xuất qua FK; các thuộc tính giao dịch lưu trên line/movement.
- Không đưa `PrescriptionNumber`, `PatientID`, `SalespersonID`, `TaxInvoiceNumber` vào OLTP theo quyết định cuối cùng. Các giá trị vẫn được giữ trong raw/processed và staging lịch sử; DW không đọc staging thay cho OLTP.
- `DoctorID`, `SalesPromo`, `PromoName` toàn bộ trống trong nguồn hiện có và chưa được ánh xạ. Không tạo thực thể nghiệp vụ từ cột trống.
- `DateTime` trở thành timestamp; các phần ngày/giờ tính lại được. `BatchAndExpiryDate` được giữ raw và tách sang product_batch. Bốn trường stock tách thành quantity và FK đơn vị. Tỷ lệ lưu numeric 0–100; `TaxAmount` nguồn là phần trăm nên ánh xạ `tax_pct`.
- Tên/hãng/nhóm/category trên dòng giữ snapshot; product có tên và FK danh mục. Dấu `-` trong hãng/phân loại trở thành NULL. Không tự quy đổi đơn vị, khẳng định công thức tiền hoặc suy diễn batch cho stock.

[Schema và ERD](schema.md) · [Luồng ingestion](ingestion.md). Dữ liệu gốc nằm trong `data/raw/`.
