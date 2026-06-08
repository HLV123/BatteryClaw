# BatteryClaw Server — Triển khai Production (HTTPS)

Server bán key (`server/server.py`) chạy HTTP thuần. Khi deploy thật, machine_id
và email KHÔNG nên truyền plaintext (DESIGN-04 / TODO-03). Dưới đây là 2 cách
thêm HTTPS.

## Bắt buộc trước khi deploy

Đặt token admin mạnh (lifespan sẽ chặn nếu yếu — xem NEW-01/BUG-02):
```bash
export BC_ADMIN_TOKEN="$(openssl rand -base64 32)"
```

## Cách 1 — uvicorn với SSL trực tiếp (đơn giản, hợp VPS nhỏ)

```bash
uvicorn server:app --host 0.0.0.0 --port 8443 \
    --ssl-keyfile /etc/letsencrypt/live/your-domain/privkey.pem \
    --ssl-certfile /etc/letsencrypt/live/your-domain/fullchain.pem
```
Lấy cert miễn phí bằng certbot:
```bash
sudo certbot certonly --standalone -d your-domain.com
```

## Cách 2 — nginx reverse proxy (khuyến nghị production)

nginx lo TLS, server chạy HTTP ở localhost. Template `/etc/nginx/sites-available/batteryclaw`:

```nginx
server {
    listen 80;
    server_name your-domain.com;
    # chuyển hết sang HTTPS
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    server_name your-domain.com;

    ssl_certificate     /etc/letsencrypt/live/your-domain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/your-domain.com/privkey.pem;
    ssl_protocols       TLSv1.2 TLSv1.3;

    # giới hạn kích thước upload dataset (khớp giới hạn 5000 dòng phía app)
    client_max_body_size 5m;

    location / {
        proxy_pass         http://127.0.0.1:8000;
        proxy_set_header   Host $host;
        proxy_set_header   X-Real-IP $remote_addr;
        # QUAN TRONG: chuyen IP that de rate_limit() chan dung IP, khong phai 127.0.0.1
        proxy_set_header   X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header   X-Forwarded-Proto $scheme;
    }
}
```

Chạy server sau nginx (chỉ bind localhost):
```bash
export BC_ADMIN_TOKEN="<token-manh>"
uvicorn server:app --host 127.0.0.1 --port 8000
# hoặc nhiều worker:
gunicorn -k uvicorn.workers.UvicornWorker server:app -b 127.0.0.1:8000 -w 2
```

Bật + xin cert:
```bash
sudo ln -s /etc/nginx/sites-available/batteryclaw /etc/nginx/sites-enabled/
sudo certbot --nginx -d your-domain.com
sudo systemctl reload nginx
```

## Lưu ý rate limiting sau proxy

`rate_limit()` dùng `request.client.host`. Sau nginx, IP này là 127.0.0.1 cho mọi
request → rate limit sẽ gộp chung tất cả. Nếu cần chặn theo IP thật, đọc header
`X-Forwarded-For` (nginx đã set ở trên). Khi cần, sửa `rate_limit()`:
```python
ip = request.headers.get("x-forwarded-for", "").split(",")[0].strip() \
     or (request.client.host if request.client else "unknown")
```
(Chỉ tin header này khi server NẰM SAU proxy mình kiểm soát.)
