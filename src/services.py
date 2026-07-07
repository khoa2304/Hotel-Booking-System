from datetime import date, timedelta

from database import get_connection
from models import Booking, Room
from repository import display_booking_code, parse_booking_identifier, parse_room_identifier
from validators import validate_stay_dates


def create_booking_and_payment(
    member_id: int,
    room_code: str,
    guest_full_name: str,
    guest_id_number: str,
    guest_phone: str,
    check_in_text: str,
    check_out_text: str,
    number_of_guests: int,
    payment_processor=None,
) -> str:
    check_in, check_out = validate_stay_dates(check_in_text, check_out_text)

    with get_connection() as connection:
        with connection.cursor() as cursor:
            room_column, room_value = parse_room_identifier(room_code)
            cursor.execute(
                f"""
                SELECT room_id, room_number, room_type, price_per_night, area,
                       bed_type, max_occupancy, status, description
                FROM room
                WHERE {room_column} = %s
                FOR UPDATE
                """,
                (room_value,),
            )
            room = cursor.fetchone()

            if room is None:
                raise ValueError("Room not found.")
            room_model = Room(
                room_id=room["room_id"],
                room_number=room["room_number"],
                room_type=room["room_type"],
                price_per_night=room["price_per_night"],
                area=room["area"],
                bed_type=room["bed_type"],
                max_occupancy=room["max_occupancy"],
                status=room["status"],
                description=room["description"] or "",
            )
            if not room_model.check_availability(number_of_guests):
                raise ValueError("Room is unavailable or does not fit the guest count.")

            cursor.execute(
                """
                SELECT booking_id
                FROM booking
                WHERE room_id = %s
                  AND booking_status NOT IN ('Cancelled', 'Checked-out')
                  AND check_in_date < %s
                  AND check_out_date > %s
                """,
                (room["room_id"], check_out, check_in),
            )
            if cursor.fetchone() is not None:
                raise ValueError("Room already booked.")

            booking_model = Booking(
                booking_id=0,
                account_id=member_id,
                room_id=room["room_id"],
                guest_full_name=guest_full_name,
                guest_id_card=guest_id_number,
                guest_phone=guest_phone,
                check_in_date=check_in,
                check_out_date=check_out,
                number_of_guests=number_of_guests,
                price_per_night=room["price_per_night"],
            )
            number_of_nights = booking_model.number_of_nights
            total_amount = booking_model.calculate_total_amount()

            if payment_processor is not None and not payment_processor(total_amount):
                raise ValueError("Online payment was declined. No booking was created.")

            cursor.execute(
                """
                INSERT INTO booking (
                    account_id,
                    room_id,
                    guest_full_name,
                    guest_id_card,
                    guest_phone,
                    check_in_date,
                    check_out_date,
                    number_of_guests,
                    number_of_nights,
                    total_amount,
                    booking_status
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, 'New')
                RETURNING booking_id
                """,
                (
                    member_id,
                    room["room_id"],
                    guest_full_name,
                    guest_id_number,
                    guest_phone,
                    check_in,
                    check_out,
                    number_of_guests,
                    number_of_nights,
                    total_amount,
                ),
            )
            booking_id = cursor.fetchone()["booking_id"]

            cursor.execute(
                """
                INSERT INTO payment (booking_id, amount, payment_status)
                VALUES (%s, %s, 'Paid')
                """,
                (booking_id, total_amount),
            )

    return display_booking_code(booking_id)


def cancel_booking(member_id: int, booking_code: str) -> None:
    booking_id = parse_booking_identifier(booking_code)
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT booking_id, check_in_date, booking_status
                FROM booking
                WHERE booking_id = %s
                  AND account_id = %s
                FOR UPDATE
                """,
                (booking_id, member_id),
            )
            booking = cursor.fetchone()

            if booking is None:
                raise ValueError("Booking not found.")
            if booking["booking_status"] != "New":
                raise ValueError("Only New bookings can be cancelled.")

            check_in = booking["check_in_date"]
            if isinstance(check_in, str):
                check_in = date.fromisoformat(check_in)
            if check_in <= date.today() + timedelta(days=1):
                raise ValueError("Booking can only be cancelled at least 24 hours before check-in.")

            cursor.execute(
                """
                UPDATE booking
                SET booking_status = 'Cancelled'
                WHERE booking_id = %s
                """,
                (booking["booking_id"],),
            )
            cursor.execute(
                """
                UPDATE payment
                SET payment_status = 'Refund Pending'
                WHERE booking_id = %s
                  AND payment_status = 'Paid'
                """,
                (booking["booking_id"],),
            )
