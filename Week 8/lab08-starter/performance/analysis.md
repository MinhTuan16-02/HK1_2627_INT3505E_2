# Phân tích hiệu năng Books API (Lab 4)

## 1. Bảng tổng hợp kết quả đo từ 3 kịch bản

| Kịch bản | Số User | Ramp-up | Thời gian | Tổng Requests | RPS | p50 (ms) | p95 (ms) | p99 (ms) | Tỷ lệ lỗi (%) |
| :--- | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: | :---: |
| **A (Baseline)** | 10 | 2/s | 30s | 142 | 4.81 | 7 | 18 | 20 | 0.70% (1/142) |
| **B (Load test)** | 50 | 5/s | 60s | 1400 | 23.46 | 6 | 18 | 26 | 0.29% (4/1400) |
| **C (Spike test)** | 200 | 50/s | 30s | 2867 | 96.64 | 7 | 67 | 110 | 0.10% (3/2867) |

---

## 2. Trả lời các câu hỏi phân tích

### Câu 1: Trong 3 kịch bản, kịch bản nào có p95 cao nhất? Vì sao?
* **Kết quả:** **Kịch bản C (Spike test - 200 users)** có độ trễ `p95` cao nhất với **67 ms** (gấp hơn 3,7 lần so với mức **18 ms** của Kịch bản A và B).
* **Nguyên nhân:** Ở mức tải nhẹ và trung bình (10–50 users), server xử lý dư sức nên `p95` giữ nguyên ở mức 18 ms. Khi tăng đột biến lên 200 users với tốc độ 50 users/giây, lượng request đồng thời đạt gần 97 RPS khiến các luồng xử lý của Flask development server (giới hạn bởi Python GIL) và thao tác ghi vào file SQLite (`POST /books` có `p95 = 67 ms`, `max = 227 ms`) bị nghẽn hàng đợi, kéo độ trễ ở nhóm 5% request chậm nhất tăng lên.

### Câu 2: Có endpoint nào fail rate tăng theo số user? Đoán nguyên nhân dựa trên code.
* **Thực tế đo được:** Tất cả các lỗi ghi nhận trong cả 3 kịch bản (1 lỗi ở A, 4 lỗi ở B, 3 lỗi ở C) đều chỉ xuất hiện ở duy nhất endpoint **`GET /books?year`** với thông báo `Simulated HTTP 500 (client-side)`. Các endpoint còn lại (`GET /books`, `GET /books/{id}`, `POST /books`) đều có tỷ lệ lỗi **0%**.
* **Nguyên nhân dựa trên code:** Trong file `performance/locustfile.py`, task `search_by_year` được chủ động lập trình để đánh dấu thất bại ngẫu nhiên với xác suất 1% (`random.random() < 0.01`). Vì đây là biến cố ngẫu nhiên theo xác suất độc lập trên từng request (không phải lỗi quá tải hệ thống), nên tỷ lệ lỗi của endpoint này dao động quanh ngưỡng kỳ vọng 1% (4.00% trên 25 reqs ở A, 1.94% trên 206 reqs ở B, 0.75% trên 399 reqs ở C) chứ không tăng tuyến tính theo số lượng user.

### Câu 3: Nếu production cần SLO p95 < 300ms, kịch bản nào đạt? Đề xuất baseline cho CI gate.
* **Đánh giá SLO (`p95 < 300ms`):** Cả 3 kịch bản đều đạt yêu cầu SLO `p95 < 300ms` khi chạy kiểm thử cục bộ (A: `18 ms`, B: `18 ms`, C: `67 ms`).
* **Đề xuất baseline cho CI gate:** Nên chọn cấu hình tương đương **Kịch bản A (10–20 users, ramp-up 2–5/s, chạy trong 30s)** làm bài kiểm tra tự động (smoke load test) trên CI pipeline. Mức tải này chạy nhanh (30 giây), đủ để phát hiện sớm các lỗi suy giảm hiệu năng (như query chậm hoặc khóa DB) với ngưỡng chặn `p95 < 300ms` và `error rate <= 2%` (trừ hao sai số của 1% lỗi giả lập trên mẫu nhỏ) mà không làm chậm quá trình merge code.

### Câu hỏi bonus: Nếu connection pool giới hạn 5 khi 200 user truy cập đồng thời thì điều gì xảy ra? Cách xác nhận bằng Locust?
* **Hiện tượng:** Khi 200 user gửi request cùng lúc nhưng pool chỉ cấp tối đa 5 kết nối tới database, 195 request còn lại buộc phải xếp hàng chờ giải phóng kết nối. Thời gian chờ đợi này làm `p95` và `p99` tăng vọt; nếu thời gian chờ vượt quá `pool_timeout`, SQLAlchemy sẽ ném ngoại lệ `TimeoutError: QueuePool limit of size 5 overflow 0 reached` và trả về lỗi HTTP `500`.
* **Cách xác nhận bằng Locust:** Cấu hình `SQLALCHEMY_ENGINE_OPTIONS = {"pool_size": 5, "max_overflow": 0, "pool_timeout": 2}` trong `app.py`, khởi động lại server và chạy lại **Kịch bản C (200 users)** bằng Locust. Sau đó mở bảng **Failures Statistics** trong báo cáo HTML để xác nhận tỷ lệ lỗi `500` tăng đột biến kèm thông báo timeout từ `QueuePool`.
