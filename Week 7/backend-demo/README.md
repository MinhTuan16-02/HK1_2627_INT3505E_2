# Demo Code-First và Design-First — Buổi 7

Demo bám phần ảnh “Hai cách tiếp cận” (trang 6) và ví dụ Product API (trang 7–9) trong tài liệu buổi 7. Hai ứng dụng cùng xử lý sản phẩm, cùng dùng OpenAPI 3.0.3, nhưng nguồn khai báo hợp đồng khác nhau.

Đây là demo tập trung vào hai cách tiếp cận. Dữ liệu lưu RAM, mỗi ứng dụng có kho riêng và hai sản phẩm mẫu; khởi động lại sẽ về dữ liệu ban đầu. Phần SQLAlchemy, migration, Order và Docker thuộc các phần khác của bài giảng, chưa nằm trong demo này.

## Chạy ngay trên máy hiện tại

Đã chuẩn bị `.venv` ở thư mục gốc workspace. Nhấp đúp **start-demo.cmd** trong thư mục này, giữ cửa sổ đó mở khi trình bày.

Hoặc mở PowerShell tại thư mục gốc workspace và chạy:

```powershell
Set-Location '.\Week 7\backend-demo'
& '..\..\.venv\Scripts\python.exe' run.py
```

Mở hai tab:

| Bản | Swagger UI | Hợp đồng OpenAPI |
|---|---|---|
| Code-First | http://127.0.0.1:5001/docs | http://127.0.0.1:5001/openapi.json |
| Design-First | http://127.0.0.1:5002/ui/ | http://127.0.0.1:5002/openapi.json |

Swagger UI dùng JS/CSS từ thư viện đã cài, không cần CDN. Nhấn Ctrl+C tại cửa sổ chạy để dừng cả hai server. Nếu cổng bận, đóng phiên demo cũ rồi chạy lại.

## Kịch bản trình bày khoảng 5 phút

### 1. Nêu ý tưởng (30 giây)

“Em triển khai cùng một Product API theo hai cách. Cả hai đều có hợp đồng OpenAPI và Swagger UI. Điểm khác nhau là em khai báo hợp đồng ở đâu và bắt đầu từ đâu.”

### 2. Code-First (1 phút)

Mở `code_first/app.py`:

1. Chỉ `ProductInput`: `name` bắt buộc, dài 1–100 ký tự; `price` bắt buộc và không âm.
2. Chỉ `@blp.route`, `@blp.arguments` và `@blp.response`: route, kiểm tra đầu vào và mô tả đầu ra được khai báo bằng Python.
3. Mở `http://127.0.0.1:5001/openapi.json`, tìm `/products`. File JSON này được thư viện sinh khi khởi tạo ứng dụng; không có file YAML phải viết tay cho bản Code-First.
4. Mở Swagger UI ở cổng 5001.

“Ở đây Python là nguồn khai báo: resource và schema Python → OpenAPI → Swagger UI. Cách này phù hợp prototype, MVP và nhóm quen Python.”

### 3. Design-First (1 phút)

Mở `design_first/openapi.yaml` trước:

1. Chỉ `paths`, `requestBody`, `responses` và `components/schemas`.
2. Chỉ `operationId: design_first.handlers.create_product`.
3. Mở `design_first/handlers.py`, chỉ đúng hàm `create_product(body)`. Hàm này không có decorator khai báo route hay schema request.
4. Mở `design_first/app.py`, chỉ `app.add_api(...)`: Connexion đọc YAML, đăng ký route, kiểm tra dữ liệu và gọi handler theo `operationId`. `validate_responses=True` bật kiểm tra response theo hợp đồng.

“Ở đây YAML là nguồn khai báo: OpenAPI → route và validation → handler. Các nhóm có thể thống nhất spec trước khi viết backend.”

Connexion 3 có lớp middleware ASGI nên bản này chạy bằng Uvicorn, bên trong vẫn dùng `FlaskApp`. Không dùng riêng `app.app.test_client()` để kiểm tra validation của Connexion vì như vậy sẽ bỏ qua middleware.

### 4. Thử API (1–2 phút)

Thực hiện ở cả hai tab Swagger UI: mở operation → **Try it out** → nhập body nếu có → **Execute**.

| Lần thử | Request | Kết quả |
|---|---|---|
| 1 | `GET /products` | 200, danh sách sản phẩm mẫu |
| 2 | `POST /products` với body hợp lệ bên dưới | 201, có ID mới |
| 3 | `GET /products/{product_id}` với ID vừa tạo | 200, sản phẩm vừa tạo |
| 4 | `POST /products` với giá âm | Code-First: 422; Design-First: 400 |
| 5 | `DELETE /products/{product_id}` | 204, không có body |
| 6 | `GET` lại ID đã xóa | 404 |

Body hợp lệ:

```json
{"name": "Man hinh demo", "price": 2500000}
```

Body sai:

```json
{"name": "Gia sai", "price": -1}
```

“Cả hai đều từ chối giá âm trước khi lưu. 422 và 400 ở đây là mặc định của hai thư viện được chọn; đây không phải quy tắc bắt buộc của Code-First hay Design-First.”

### 5. Chứng minh nguồn hợp đồng bằng một thay đổi nhỏ (tùy thời gian)

- Code-First: đổi `validate.Length(min=1, max=100)` thành `min=5` tại `ProductInput.name` trong Python.
- Design-First: đổi `minLength: 1` thành `minLength: 5` **cả ở ProductInput.name và Product.name** trong YAML để request/response nhất quán.
- Dừng rồi chạy lại demo, tải lại Swagger UI. Gửi `{"name":"ABC","price":100}` sẽ bị từ chối. Khôi phục `min=1` / `minLength: 1` và khởi động lại sau khi trình bày.

“Bên Code-First em sửa schema Python; bên Design-First em sửa hợp đồng YAML. Thay đổi hợp đồng cần được phản ánh nhất quán ở xử lý và dữ liệu liên quan.”

## Chạy demo tự động bằng HTTP

Giữ server đang chạy, mở PowerShell thứ hai tại thư mục này:

```powershell
& '..\..\.venv\Scripts\python.exe' demo_requests.py
```

Script gửi request thật tới hai cổng, in HTTP status và JSON, kiểm tra kết quả rồi xóa sản phẩm mà script vừa tạo. Kết thúc thành công sẽ in `PASS`.

## Kiểm thử

```powershell
& '..\..\.venv\Scripts\python.exe' -m pytest -q
```

Bộ kiểm thử bao phủ vòng đời sản phẩm, các body sai, JSON lỗi, hợp đồng OpenAPI, tài nguyên Swagger UI và kho dữ liệu độc lập. Mỗi fixture dùng ứng dụng mới nên không làm thay đổi dữ liệu của server demo.

## Cài đặt trên máy khác

Yêu cầu Python 3.10+ (đã kiểm thử bằng Python 3.13). Mở PowerShell tại thư mục chứa README này:

```powershell
python -m venv .venv
& '.\.venv\Scripts\python.exe' -m pip install -r requirements.txt
& '.\.venv\Scripts\python.exe' run.py
```

Không cần activate môi trường. `start-demo.cmd` dùng môi trường ở gốc workspace của máy hiện tại; trên máy khác dùng các lệnh trực tiếp ở trên.

## Những câu thầy có thể hỏi

- **Cả hai có OpenAPI không?** Có. Khác nhau ở nguồn khai báo và quy trình xây dựng hợp đồng.
- **Design-First có tự viết logic nghiệp vụ không?** Không. Connexion ánh xạ route và kiểm tra theo spec; lập trình viên vẫn viết handler.
- **Code-First có validation không?** Có. Marshmallow kiểm tra đầu vào; Flask-Smorest dùng schema để sinh tài liệu và serialize đầu ra. Serialize đầu ra không đồng nghĩa với kiểm tra response theo JSON Schema như tùy chọn Connexion trong demo.
- **Swagger UI là backend không?** Swagger UI là giao diện đọc hợp đồng và gửi request thử; backend là hai ứng dụng đang chạy.
- **Lựa chọn nào tốt hơn?** Tùy bối cảnh: nhóm nhỏ cần thử nhanh có thể chọn Code-First; nhiều nhóm/consumer cần thống nhất hợp đồng trước có thể chọn Design-First.

## Tài liệu chính thức đã đối chiếu

- [Flask-Smorest Quickstart](https://flask-smorest.readthedocs.io/en/latest/quickstart.html)
- [Flask-Smorest OpenAPI](https://flask-smorest.readthedocs.io/en/latest/openapi.html)
- [Connexion Quickstart](https://connexion.readthedocs.io/en/stable/quickstart.html)
- [Connexion Validation](https://connexion.readthedocs.io/en/stable/validation.html)
