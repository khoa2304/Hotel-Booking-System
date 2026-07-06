import json
import smtplib
from email.message import EmailMessage
from urllib.request import Request, urlopen

from config import (
    PAYMENT_GATEWAY_TOKEN,
    PAYMENT_GATEWAY_URL,
    SMTP_FROM,
    SMTP_HOST,
    SMTP_PASSWORD,
    SMTP_PORT,
    SMTP_USE_TLS,
    SMTP_USERNAME,
)


class EmailService:
    def is_configured(self) -> bool:
        return bool(SMTP_HOST and SMTP_FROM)

    def send(self, recipient: str, subject: str, body: str) -> bool:
        if not self.is_configured():
            print(f"Email simulation to {recipient}\nSubject: {subject}\n{body}")
            return False

        message = EmailMessage()
        message["From"] = SMTP_FROM
        message["To"] = recipient
        message["Subject"] = subject
        message.set_content(body)

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=10) as server:
            if SMTP_USE_TLS:
                server.starttls()
            if SMTP_USERNAME:
                server.login(SMTP_USERNAME, SMTP_PASSWORD)
            server.send_message(message)
        return True

    def send_password_reset(self, recipient: str, new_password: str) -> bool:
        return self.send(
            recipient,
            "Lucky Hotel password reset",
            f"Your new temporary password is: {new_password}\nPlease log in and change it immediately.",
        )

    def send_booking_confirmation(self, recipient: str, booking: dict) -> bool:
        return self.send(
            recipient,
            f"Lucky Hotel booking {booking['booking_code']}",
            (
                f"Booking: {booking['booking_code']}\n"
                f"Room: {booking['room_type']} {booking['room_number']}\n"
                f"Check-in: {booking['check_in_date']}\n"
                f"Check-out: {booking['check_out_date']}\n"
                f"Total: {booking['total_amount']}\n"
                f"Status: {booking['booking_status']}\n"
                f"Payment: {booking['payment_status']}"
            ),
        )


class PaymentGateway:
    def is_configured(self) -> bool:
        return bool(PAYMENT_GATEWAY_URL)

    def process(self, amount, reference: str, demo_result: str = "success") -> bool:
        if not self.is_configured():
            return demo_result == "success"

        payload = json.dumps({"amount": str(amount), "reference": reference}).encode("utf-8")
        headers = {"Content-Type": "application/json"}
        if PAYMENT_GATEWAY_TOKEN:
            headers["Authorization"] = f"Bearer {PAYMENT_GATEWAY_TOKEN}"
        request = Request(PAYMENT_GATEWAY_URL, data=payload, headers=headers, method="POST")
        with urlopen(request, timeout=15) as response:
            result = json.loads(response.read().decode("utf-8"))
        return result.get("status") in {"success", "paid", "approved"}


email_service = EmailService()
payment_gateway = PaymentGateway()
