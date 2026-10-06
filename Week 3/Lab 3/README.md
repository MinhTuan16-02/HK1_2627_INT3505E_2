# Lab 3: Cursor Pagination cho `GET /orders`
# Chức năng

Endpoint `GET /orders` hỗ trợ:
- Phân trang bằng `cursor` Base64, có `next_cursor` và `has_more`.
- Lọc theo `status`, `customer_id`.
- Sắp xếp bằng `sort`, ví dụ `sort=-total`.
- Chọn trường cần trả về bằng `fields`, ví dụ `fields=id,total`.
- `limit` dùng để giới hạn số đơn hàng mỗi trang, mặc định là 5.
- Cursor sai định dạng sẽ trả về `400 Bad Request`.

Ví dụ:

```http
GET /orders?status=paid&limit=5&sort=-total
```