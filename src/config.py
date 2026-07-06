import os


HOST = os.getenv("HOTEL_HOST", "127.0.0.1")
PORT = int(os.getenv("HOTEL_PORT", "4180"))

DB_CONFIG = {
    "host": os.getenv("HOTEL_DB_HOST", "localhost"),
    "port": int(os.getenv("HOTEL_DB_PORT", "5432")),
    "dbname": os.getenv("HOTEL_DB_NAME", "hotel_booking"),
    "user": os.getenv("HOTEL_DB_USER", "postgres"),
    "password": os.getenv("HOTEL_DB_PASSWORD", "MAT_KHAU_POSTGRES"),
}

SESSION_LIFETIME_MINUTES = int(os.getenv("HOTEL_SESSION_MINUTES", "60"))

SMTP_HOST = os.getenv("HOTEL_SMTP_HOST", "")
SMTP_PORT = int(os.getenv("HOTEL_SMTP_PORT", "587"))
SMTP_USERNAME = os.getenv("HOTEL_SMTP_USERNAME", "")
SMTP_PASSWORD = os.getenv("HOTEL_SMTP_PASSWORD", "")
SMTP_FROM = os.getenv("HOTEL_SMTP_FROM", SMTP_USERNAME)
SMTP_USE_TLS = os.getenv("HOTEL_SMTP_USE_TLS", "true").lower() == "true"

PAYMENT_GATEWAY_URL = os.getenv("HOTEL_PAYMENT_GATEWAY_URL", "")
PAYMENT_GATEWAY_TOKEN = os.getenv("HOTEL_PAYMENT_GATEWAY_TOKEN", "")
