# Lucky Hotel Booking System

Web application implemented with Python, HTML5/CSS3, and PostgreSQL.

## Run with PowerShell

```powershell
$env:HOTEL_DB_PASSWORD="khoa"
.\.venv\bin\python.exe src\seed_data.py
.\.venv\bin\python.exe src\hotel_booking_python_app.py
```

Open `http://127.0.0.1:4180`.

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
