# Báo cáo chất lượng dữ liệu theo cột

## Phạm vi và cách đo

| Tệp | Số dòng dữ liệu | Số cột |
|---|---:|---:|
| `sales_raw.csv` | 649.656 | 35 |
| `stock_raw.csv` | 804.027 | 15 |

Báo cáo được tính trực tiếp trên CSV. “Thiếu” ở đây chỉ đếm ô trống sau khi bỏ khoảng trắng; giá trị `-` được thống kê riêng vì là ký tự thực trong tệp. Tỷ lệ làm tròn đến 2 chữ số thập phân. Đây là đánh giá dữ liệu raw, chưa suy diễn `-` thành null và chưa xác nhận đầy đủ quy tắc nghiệp vụ.

## Sales — `sales_raw.csv`

| Cột | Trống | Dấu `-` | Nhận xét chất lượng |
|---|---:|---:|---|
| `RowNumber` | 0 (0%) | 0 | 649.656 giá trị riêng; số thứ tự liên tục theo thứ tự tệp. |
| `DateTime` | 0 (0%) | 0 | 358.788 chuỗi thời gian khác nhau; cần parse định dạng ngày tháng tiếng Anh. |
| `Shift` | 0 (0%) | 0 | 3.277 giá trị khác nhau; là chuỗi ghép ngày/ca/thu ngân chứ không chỉ là ca. |
| `CashierID` | 0 (0%) | 0 | 10 ID; đã ở dạng mã ẩn danh. |
| `InvoiceNumber` | 0 (0%) | 0 | 359.121 hóa đơn; lặp giữa các dòng hàng là bình thường. |
| `Manufacturer` | 0 (0%) | 434.869 (66,94%) | Dấu `-` chiếm đa số; cần coi là giá trị chưa biết/không cung cấp nếu phù hợp nghiệp vụ. |
| `DrugClass` | 0 (0%) | 647.756 (99,71%) | Gần như toàn bộ là `-`; giá trị thông tin rất thấp trong raw. |
| `Category` | 0 (0%) | 109.565 (16,86%) | Có `-`; 10 giá trị phân biệt. Chuẩn hóa nhãn trước khi nhóm. |
| `DrugCode` | 0 (0%) | 0 | 3.149 mã; không rỗng. Kiểm tra tính nhất quán mã-tên nếu dùng làm khóa danh mục. |
| `DrugName` | 0 (0%) | 0 | 3.148 tên; gần tương ứng số mã, nhưng chưa đảm bảo mỗi mã ánh xạ duy nhất một tên. |
| `BatchAndExpiryDate` | 3.183 (0,49%) | 0 | Trường ghép lô và hạn dùng; định dạng chuỗi không đồng nhất có thể cần tách/parse. |
| `PrescriptionNumber` | 649.653 (100,00%) | 0 | Chỉ có 3 ô không trống; gần như không sử dụng được. |
| `PatientID` | 649.478 (99,97%) | 0 | Chỉ 178 ô có dữ liệu; mã ID đã ẩn danh. |
| `DoctorID` | 649.656 (100,00%) | 0 | Hoàn toàn trống. |
| `SalespersonID` | 649.561 (99,99%) | 0 | Chỉ 95 ô có dữ liệu; gần như thiếu toàn bộ. |
| `Quantity` | 0 (0%) | 0 | Có 91 giá trị chuỗi; cần chuyển số và kiểm tra các giá trị thập phân. |
| `Unit` | 0 (0%) | 0 | 20 đơn vị; phải diễn giải Quantity cùng đơn vị. |
| `PriceTier` | 0 (0%) | 0 | 3 nhãn; `Harga Jual 1` chiếm 649.650/649.656 dòng. |
| `UnitPrice` | 0 (0%) | 0 | 703 giá trị dạng chuỗi số; chuyển kiểu số trước phân tích. |
| `SalesPromo` | 649.656 (100,00%) | 0 | Hoàn toàn trống. |
| `PromoName` | 649.656 (100,00%) | 0 | Hoàn toàn trống. |
| `DiscountPct` | 0 (0%) | 0 | 652 chuỗi phần trăm; có dấu phẩy thập phân, ví dụ `2,86%`. |
| `DiscountAmount` | 0 (0%) | 0 | 378 giá trị chuỗi; cần chuyển số. |
| `ServiceFee` | 0 (0%) | 0 | 26 giá trị; 649.293 dòng bằng `0` (99,94%). |
| `PackagingFee` | 0 (0%) | 0 | 77 giá trị; 645.819 dòng bằng `0` (99,41%). |
| `TaxInvoiceNumber` | 649.617 (99,99%) | 0 | Chỉ 39 ô không trống; một số giá trị lẻ như `f`, `+`. Nên rà soát trước khi dùng. |
| `Subtotal` | 0 (0%) | 0 | 1.530 giá trị chuỗi số; cần chuyển kiểu. |
| `InvoiceDiscountPct` | 0 (0%) | 0 | 20 nhãn phần trăm; 649.552 dòng bằng `0%` (99,98%). |
| `IsMember` | 0 (0%) | 0 | Chỉ có `Non Member` (một giá trị duy nhất); không có biến thiên để so sánh thành viên. |
| `PromoDiscountPct` | 0 (0%) | 0 | Chỉ có `0%`; hằng trên toàn bộ tệp. |
| `TaxAmount` | 0 (0%) | 0 | Chỉ có `0%`; hằng trên toàn bộ tệp. |
| `AdditionalFee` | 0 (0%) | 0 | Chỉ có `0`; hằng trên toàn bộ tệp. |
| `PaymentType` | 0 (0%) | 0 | 3 nhãn; `TUNAI` chiếm 639.011 dòng (98,36%). |
| `PrintCount` | 0 (0%) | 0 | 7 giá trị chuỗi số; 559.582 dòng bằng `0` (86,14%). |
| `TotalPrice` | 0 (0%) | 0 | 1.608 giá trị chuỗi số; cần chuyển kiểu và kiểm tra đối chiếu với các cấu phần tiền. |

## Stock — `stock_raw.csv`

| Cột | Trống | Dấu `-` | Nhận xét chất lượng |
|---|---:|---:|---|
| `RowNumber` | 0 (0%) | 0 | 804.027 giá trị riêng; số thứ tự liên tục theo thứ tự tệp. |
| `DateTime` | 0 (0%) | 0 | 763.505 chuỗi thời gian khác nhau; cần parse định dạng ngày tháng tiếng Anh. |
| `Warehouse` | 0 (0%) | 0 | 2 địa điểm; `Apotek` 742.242 dòng (92,31%), `Gudang Obat 1` 61.785 dòng. |
| `DrugCode` | 0 (0%) | 0 | 4.366 mã khác nhau; không rỗng. |
| `DrugName` | 0 (0%) | 0 | 4.366 tên khác nhau; số lượng khác nhau trùng với mã, nên kiểm tra ánh xạ mã-tên. |
| `DocumentNumber` | 0 (0%) | 0 | 404.180 giá trị; số chứng từ được lặp trên nhiều dòng là có thể xảy ra. |
| `TransactionDescription` | 0 (0%) | 0 | 395.129 chuỗi khác nhau; mô tả tự do có nhiều cách viết/viết tắt, cần phân loại chuẩn hóa. |
| `InitialStock` | 0 (0%) | 0 | 15.693 chuỗi; số lượng và đơn vị ghép chung, có phân cách hàng nghìn. |
| `StockIn` | 0 (0%) | 0 | 880 chuỗi; số lượng và đơn vị ghép chung, đa số là 0. |
| `StockOut` | 0 (0%) | 0 | 1.126 chuỗi; số lượng và đơn vị ghép chung. |
| `RemainingStock` | 0 (0%) | 0 | 15.679 chuỗi; cần tách số/đơn vị và đối chiếu với tồn đầu, nhập, xuất. |
| `DrugClass` | 0 (0%) | 801.669 (99,71%) | Gần như toàn bộ là `-`; giá trị thông tin rất thấp trong raw. |
| `Category` | 0 (0%) | 139.498 (17,35%) | Có `-`; cần xem dấu gạch như giá trị thiếu khi phân tích nhóm. |
| `DrugType` | 0 (0%) | 0 | 2 nhãn; `NON KONSINYASI` chiếm 798.785 dòng (99,35%). |
| `Status` | 0 (0%) | 0 | Chỉ có `Aktif`; cột hằng, không phân biệt bản ghi trong snapshot này. |

## Kết luận và điểm cần xử lý

- Không có ô trống trong các cột stock; các trường thiếu thông tin được biểu diễn bằng `-` ở `DrugClass` và `Category`.
- Các cột trống hoàn toàn trong sales là `DoctorID`, `SalesPromo`, `PromoName`; `PrescriptionNumber` gần như hoàn toàn trống. Các cột `PatientID`, `SalespersonID`, `TaxInvoiceNumber` cũng có tỷ lệ thiếu trên 99,9%.
- Nhiều cột sales mang tính hằng: `IsMember`, `PromoDiscountPct`, `TaxAmount`, `AdditionalFee`; `Status` trong stock cũng chỉ có một giá trị. Chúng ít hữu ích cho mô hình phân tích hiện tại.
- Trường thời gian, tỷ lệ, tiền tệ, số lượng tồn kho chưa ở dạng số/ngày chuẩn. Cần parse theo định dạng cụ thể, giữ đơn vị đo và xử lý dấu phẩy/dấu chấm có chủ đích.
- `TransactionDescription` và một số phân loại là văn bản gốc; chuẩn hóa nên giữ lại giá trị raw để có thể truy nguyên.
- Các phép kiểm tra tiếp theo nên bao gồm: tính duy nhất/ánh xạ mã thuốc-tên, quy tắc tổng tiền, cân đối tồn đầu + nhập - xuất = tồn cuối, phạm vi giá trị số và kiểm tra ngày hợp lệ. Báo cáo này chưa tự khẳng định các ràng buộc đó đã đạt.
