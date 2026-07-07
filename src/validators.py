from datetime import date
import re


EMAIL_PATTERN = re.compile(r"^[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}$")


def validate_required(data: dict[str, str], required_fields: list[str]) -> list[str]:
    errors = []
    for field in required_fields:
        if not data.get(field, "").strip():
            errors.append(f"{field} is required.")
    return errors


def validate_email(email: str) -> bool:
    return bool(EMAIL_PATTERN.fullmatch(email.strip()))


def validate_stay_dates(check_in_text: str, check_out_text: str) -> tuple[date, date]:
    check_in = date.fromisoformat(check_in_text)
    check_out = date.fromisoformat(check_out_text)
    if check_in < date.today():
        raise ValueError("Check-in date cannot be in the past.")
    if check_out <= check_in:
        raise ValueError("Check-out date must be after check-in date.")
    return check_in, check_out


def validate_guests(guests_text: str) -> int:
    guests = int(guests_text)
    if guests <= 0:
        raise ValueError("Number of guests must be greater than zero.")
    return guests
