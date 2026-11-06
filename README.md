# Inventory DW DSS

PostgreSQL OLTP cho dữ liệu bán hàng và biến động tồn kho nhà thuốc. Triển khai dùng **một container** PostgreSQL 17 và một named volume của Docker Compose. Python loader dùng thư viện chuẩn và `psql` trong container, không yêu cầu PostgreSQL client trên máy host.

## Nạp toàn bộ dữ liệu

Yêu cầu: Docker Engine đang chạy, Docker Compose và `uv`. Tài khoản chạy lệnh cần truy cập được Docker daemon.

```bash
uv run inventory-dw-dss load
```

Lệnh tự khởi động database, áp dụng [schema SQL](sql/001_schema.sql), COPY toàn bộ `data/sales_raw.csv` và `data/stock_raw.csv` vào staging, rồi thực hiện [SQL chuyển đổi](sql/002_load.sql). Kết quả được ghi tại `reports/load_summary.json`.

Loader dùng cấu hình Docker tạm để tránh phụ thuộc credential helper trên máy. Image PostgreSQL là public. Database không mở cổng ra host; mật khẩu trong Compose chỉ phục vụ môi trường local.

## Cấu trúc dữ liệu

- `staging.sales_raw`, `staging.stock_raw`: giữ đủ 35/15 cột raw dưới dạng text, bao gồm các trường ít dữ liệu. COPY mặc định biểu diễn ô CSV trống không quote thành SQL NULL; đây không phải bản sao byte của file nguồn.
- `oltp.product`: danh mục mã sản phẩm dùng chung.
- `oltp.unit`, `oltp.warehouse`, `oltp.cashier`: đơn vị, kho và thu ngân.
- `oltp.sales_invoice`, `oltp.sales_line`: mã hóa đơn và các dòng hàng bán, với FK tới sản phẩm/đơn vị/thu ngân.
- `oltp.inventory_document`, `oltp.inventory_movement`: chứng từ và từng biến động tồn kho. Giữ riêng đơn vị của cả bốn lượng tồn để không giả định chúng luôn giống nhau.

Tên sản phẩm, nhà sản xuất và nhóm hàng được giữ tại dòng giao dịch để bảo toàn giá trị lịch sử; chưa chọn một giá trị danh mục khi cùng mã có nhiều cách mô tả. Các thuộc tính ca, thời điểm, thanh toán và chiết khấu giữ tại dòng bán cho tới khi xác nhận chúng thống nhất trong từng hóa đơn. Batch giữ dạng chuỗi gốc, chưa gán batch cho stock. Chưa suy diễn quan hệ trực tiếp giữa dòng bán và dòng kho.

Số lượng sales dùng dấu chấm thập phân. Số tồn kho tách khỏi đơn vị, bỏ dấu chấm hàng nghìn và đổi dấu phẩy thập phân. Tỷ lệ `%` được lưu theo thang 0–100, không phải 0–1. `TaxAmount` được chuyển thành `tax_pct` vì dữ liệu nguồn là chuỗi phần trăm. Dấu `-` trong các trường phân loại chuyển thành NULL ở OLTP và còn nguyên trong staging. Thời gian dùng `timestamp without time zone` vì nguồn không cung cấp múi giờ.

## Chạy lại và truy vấn

Một lần nạp nằm trong một transaction, có khóa để tránh hai loader chạy đồng thời. Lỗi parse, ràng buộc hoặc lệch số dòng làm rollback. Chạy lại cùng hai file sẽ làm mới staging và bỏ qua các dòng OLTP đã có theo `source_row_number`; không nhân đôi dữ liệu. Cơ chế này dành cho bộ file cố định hiện tại, không cập nhật dòng nguồn đã sửa và không hỗ trợ tái sử dụng RowNumber cho bộ file khác.

```bash
docker compose -p inventory-dw-dss exec db psql -U inventory -d inventory
```

```sql
SELECT count(*) FROM oltp.sales_line;
SELECT count(*) FROM oltp.inventory_movement;
SELECT initial_stock, stock_in, stock_out, remaining_stock
FROM oltp.inventory_movement LIMIT 5;
```

Container có các PK, UNIQUE và FK phục vụ toàn vẹn OLTP; chưa có index phục vụ benchmark hay star schema. Loader đối chiếu số dòng staging với fact giao dịch OLTP trước khi commit; chưa xác nhận các công thức tổng tiền và cân đối tồn kho.

Dừng container, giữ dữ liệu:

```bash
docker compose -p inventory-dw-dss stop
```

## Báo cáo dữ liệu

- [Từ điển dữ liệu và ví dụ](data/data_dictionary_report.md)
- [Chất lượng dữ liệu theo cột](data/data_quality_report.md)
