Lucky Hotel Booking System

Web application implemented with Python, HTML5/CSS3, and PostgreSQL.

## Run with PowerShell

```powershell
$env:HOTEL_DB_PASSWORD="khoa"
.\.venv\bin\python.exe src\seed_data.py
.\.venv\bin\python.exe src\hotel_booking_python_app.py
```

Open `http://127.0.0.1:4180`.

## External email and payment services

Without external credentials, email and payment run in demo mode. To use real services, set:

```powershell
$env:HOTEL_SMTP_HOST="smtp.example.com"
$env:HOTEL_SMTP_PORT="587"
$env:HOTEL_SMTP_USERNAME="account@example.com"
$env:HOTEL_SMTP_PASSWORD="app-password"
$env:HOTEL_SMTP_FROM="account@example.com"
$env:HOTEL_PAYMENT_GATEWAY_URL="https://gateway.example.com/payments"
$env:HOTEL_PAYMENT_GATEWAY_TOKEN="gateway-token"
```

The payment endpoint must accept JSON containing `amount` and `reference`, then return a JSON `status` of `success`, `paid`, or `approved`.

## Run tests

```powershell
.\.venv\bin\python.exe -m unittest discover -s tests -p "test_*.py"
.\.venv\bin\python.exe tests\test_database.py
```

## Run with Docker

```powershell
docker compose -f docker\docker-compose.yml up --build
docker compose -f docker\docker-compose.yml exec web python src\seed_data.py
```

Open `http://127.0.0.1:4180`. Stop with `docker compose -f docker\docker-compose.yml down`.

Sample accounts are created by `seed_data.py`:

- Member: `member@example.com` / `password123`
- Admin: `admin@harborview.test` / `admin123`
EADME.md…]()
