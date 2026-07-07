from dataclasses import dataclass
from datetime import date, datetime, timedelta
from decimal import Decimal


ROOM_TYPES = {"Standard", "Superior", "Deluxe", "Suite"}
ROOM_STATUSES = {"Available", "Occupied", "Cleaning", "Maintenance"}
BOOKING_STATUSES = {"New", "Confirmed", "Checked-in", "Checked-out", "Cancelled"}
PAYMENT_STATUSES = {"Paid", "Refund Pending"}


@dataclass
class Account:
    account_id: int
    email: str
    password_hash: str
    full_name: str
    phone: str = ""

    def login(self, password: str) -> bool:
        from security import verify_password

        return verify_password(password, self.password_hash)

    def logout(self) -> None:
        return None

    def resetPassword(self, new_password: str) -> str:
        from security import hash_password

        self.password_hash = hash_password(new_password)
        return self.password_hash


@dataclass
class Member(Account):
    date_of_birth: date | None = None
    gender: str = ""
    address: str = ""
    account_status: str = "Active"

    def can_login(self) -> bool:
        return self.account_status == "Active"

    @classmethod
    def register(cls, email: str, password: str, full_name: str, phone: str) -> int:
        from repository import register_member

        return register_member(email, password, full_name, phone)

    def updateProfile(self, data: dict[str, str]) -> None:
        from repository import update_member_profile

        update_member_profile(self.account_id, data)

    def viewBookingHistory(self) -> list[dict]:
        from repository import get_member_bookings

        return get_member_bookings(self.account_id)

    def cancelBooking(self, booking_code: str) -> None:
        from services import cancel_booking

        cancel_booking(self.account_id, booking_code)


@dataclass
class Admin(Account):
    def manageRoom(self, action: str, room_data: dict[str, str]) -> None:
        from repository import create_room, delete_room, update_room

        actions = {"add": create_room, "update": update_room}
        if action == "delete":
            delete_room(room_data["id"])
            return
        if action not in actions:
            raise ValueError("Invalid room management action.")
        actions[action](room_data)

    def manageUser(self, account_id: int, status: str) -> None:
        from repository import update_member_status

        update_member_status(account_id, status)

    def manageBooking(self, booking_code: str, status: str) -> None:
        from repository import update_booking_status

        update_booking_status(booking_code, status)

    def viewReport(self) -> dict:
        from repository import get_report_summary

        return get_report_summary()


@dataclass
class Room:
    room_id: int
    room_number: str
    room_type: str
    price_per_night: Decimal
    area: float
    bed_type: str
    max_occupancy: int
    status: str
    description: str = ""

    def __post_init__(self) -> None:
        self.price_per_night = Decimal(str(self.price_per_night))
        if self.room_type not in ROOM_TYPES:
            raise ValueError("Invalid room type.")
        if self.status not in ROOM_STATUSES:
            raise ValueError("Invalid room status.")
        if self.price_per_night <= 0 or self.area <= 0 or self.max_occupancy <= 0:
            raise ValueError("Room price, area, and occupancy must be positive.")

    def check_availability(self, number_of_guests: int) -> bool:
        return self.status == "Available" and 0 < number_of_guests <= self.max_occupancy

    def viewDetails(self) -> dict:
        return {
            "roomID": self.room_id,
            "roomNumber": self.room_number,
            "roomType": self.room_type,
            "pricePerNight": self.price_per_night,
            "area": self.area,
            "bedType": self.bed_type,
            "maxOccupancy": self.max_occupancy,
            "status": self.status,
            "description": self.description,
        }

    def checkAvailability(self, number_of_guests: int) -> bool:
        return self.check_availability(number_of_guests)

    def update_status(self, status: str) -> None:
        if status not in ROOM_STATUSES:
            raise ValueError("Invalid room status.")
        self.status = status

    def updateStatus(self, status: str) -> None:
        self.update_status(status)

    def updateRoomInfo(self, **changes) -> None:
        editable = {"room_number", "room_type", "price_per_night", "area", "bed_type", "max_occupancy", "description"}
        if not set(changes).issubset(editable):
            raise ValueError("Invalid room field.")
        for field, value in changes.items():
            setattr(self, field, value)
        self.__post_init__()


@dataclass
class Booking:
    booking_id: int
    account_id: int
    room_id: int
    guest_full_name: str
    guest_id_card: str
    guest_phone: str
    check_in_date: date
    check_out_date: date
    number_of_guests: int
    price_per_night: Decimal
    booking_status: str = "New"
    created_at: datetime | None = None

    def __post_init__(self) -> None:
        self.price_per_night = Decimal(str(self.price_per_night))
        if self.check_out_date <= self.check_in_date:
            raise ValueError("Check-out date must be after check-in date.")
        if self.number_of_guests <= 0:
            raise ValueError("Number of guests must be greater than zero.")
        if self.booking_status not in BOOKING_STATUSES:
            raise ValueError("Invalid booking status.")

    @property
    def number_of_nights(self) -> int:
        return (self.check_out_date - self.check_in_date).days

    def calculate_total_amount(self) -> Decimal:
        return self.price_per_night * self.number_of_nights

    def createBooking(self) -> dict:
        return self.viewBookingDetails()

    def can_cancel(self, today: date | None = None) -> bool:
        today = today or date.today()
        return self.booking_status == "New" and self.check_in_date > today + timedelta(days=1)

    def cancelBooking(self, today: date | None = None) -> None:
        if not self.can_cancel(today):
            raise ValueError("Booking cannot be cancelled.")
        self.booking_status = "Cancelled"

    def calculateTotalAmount(self) -> Decimal:
        return self.calculate_total_amount()

    def viewBookingDetails(self) -> dict:
        return {
            "bookingID": self.booking_id,
            "accountID": self.account_id,
            "roomID": self.room_id,
            "guestFullName": self.guest_full_name,
            "guestIDCard": self.guest_id_card,
            "guestPhone": self.guest_phone,
            "checkInDate": self.check_in_date,
            "checkOutDate": self.check_out_date,
            "numberOfGuests": self.number_of_guests,
            "numberOfNights": self.number_of_nights,
            "totalAmount": self.calculate_total_amount(),
            "bookingStatus": self.booking_status,
            "createdAt": self.created_at,
        }

    def updateBookingStatus(self, status: str) -> None:
        if status not in BOOKING_STATUSES:
            raise ValueError("Invalid booking status.")
        self.booking_status = status


@dataclass
class Payment:
    payment_id: int
    booking_id: int
    amount: Decimal
    payment_status: str = "Paid"
    payment_date: datetime | None = None

    def __post_init__(self) -> None:
        self.amount = Decimal(str(self.amount))
        if self.amount < 0:
            raise ValueError("Payment amount cannot be negative.")
        if self.payment_status not in PAYMENT_STATUSES:
            raise ValueError("Invalid payment status.")

    def request_refund(self) -> None:
        if self.payment_status == "Paid":
            self.payment_status = "Refund Pending"

    def processPayment(self, successful: bool = True) -> bool:
        if not successful:
            return False
        self.payment_status = "Paid"
        self.payment_date = self.payment_date or datetime.now()
        return True

    def updatePaymentStatus(self, status: str) -> None:
        if status not in PAYMENT_STATUSES:
            raise ValueError("Invalid payment status.")
        self.payment_status = status

    def viewPaymentDetails(self) -> dict:
        return {
            "paymentID": self.payment_id,
            "bookingID": self.booking_id,
            "paymentStatus": self.payment_status,
            "amount": self.amount,
            "paymentDate": self.payment_date,
        }
