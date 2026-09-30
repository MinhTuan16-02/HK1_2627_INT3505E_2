Bài 1:
curl http://localhost:5000/orders
{
  "data": [
    {
      "customer_name": "Nguyen Van A",
      "id": "ord_01",
      "status": "pending",
      "total": 150.0
    }
  ],
  "total": 1
}


curl http://localhost:5000/orders/ord_01
{
  "customer_name": "Nguyen Van A",
  "id": "ord_01",
  "status": "pending",
  "total": 150.0
}


curl -i -X POST http://localhost:5000/orders \
  -H "Content-Type: application/json" \
  -d '{"id": "ord_02", "customer_name": "Tran Van B", "total": 220.5}'
HTTP/1.1 201 CREATED
Server: Werkzeug/3.1.8 Python/3.14.3
Content-Type: application/json
Location: /orders/ord_02

{
  "customer_name": "Tran Van B",
  "id": "ord_02",
  "status": "pending",
  "total": 220.5
}

Bài 3:
curl -i http://localhost:5000/books/1
HTTP/1.1 200 OK
Content-Type: application/json
ETag: "7f5b6223786fad4ae56765f6d8fd6ba0"
Cache-Control: public, max-age=60

{
  "author": "Robert Martin",
  "id": 1,
  "price": 30.0,
  "title": "Clean Code"
}


curl -i -H 'If-None-Match: "7f5b6223786fad4ae56765f6d8fd6ba0"' http://localhost:5000/books/1
HTTP/1.1 304 NOT MODIFIED
ETag: "7f5b6223786fad4ae56765f6d8fd6ba0"
