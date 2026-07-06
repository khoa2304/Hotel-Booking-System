from database import get_connection
from security import generate_random_password, hash_password, verify_password


SORT_COLUMNS = {
    "price": "r.price_per_night",
    "area": "r.area",
    "occupancy": "r.max_occupancy",
}

ROOM_IMAGES = {
    "Standard": "https://images.unsplash.com/photo-1611892440504-42a792e24d32?auto=format&fit=crop&w=1000&q=85",
    "Superior": "https://images.unsplash.com/photo-1598928636135-d146006ff4be?auto=format&fit=crop&w=1000&q=85",
    "Deluxe": "https://images.unsplash.com/photo-1590490360182-c33d57733427?auto=format&fit=crop&w=1000&q=85",
    "Suite": "https://images.unsplash.com/photo-1578683010236-d716f9a3f461?auto=format&fit=crop&w=1000&q=85",
}

VALID_ROOM_TYPES = {"Standard", "Superior", "Deluxe", "Suite"}
VALID_ROOM_STATUSES = {"Available", "Occupied", "Cleaning", "Maintenance"}
VALID_BOOKING_STATUSES = {
    "Confirmed",
    "Checked-in",
    "Checked-out",
    "Cancelled",
}


def display_room_code(room: dict) -> str:
    return f"RM-{room['number']}"


def display_booking_code(booking_id: int) -> str:
    return f"BK-{int(booking_id):06d}"


def room_image(room_type: str) -> str:
    return ROOM_IMAGES.get(room_type, ROOM_IMAGES["Standard"])


def decorate_room(room: dict | None) -> dict | None:
    if room is None:
        return None
    room = dict(room)
    room["id"] = str(room["room_id"])
    room["display_id"] = display_room_code(room)
    room["image"] = room_image(room["type"])
    room.setdefault("availability_status", room.get("status", "Available"))
    room.setdefault("can_book", room.get("status") == "Available")
    return room


def parse_room_identifier(identifier: str) -> tuple[str, str]:
    identifier = str(identifier or "").strip()
    if identifier.upper().startswith("RM-"):
        return "room_number", identifier[3:]
    if identifier.isdigit():
        return "room_id", identifier
    return "room_number", identifier


def parse_booking_identifier(identifier: str) -> int:
    identifier = str(identifier or "").strip()
    if identifier.upper().startswith("BK-"):
        identifier = identifier[3:]
    return int(identifier)


def room_select_columns(extra_columns: str = "") -> str:
    return f"""
        r.room_id,
        r.room_number AS number,
        r.room_type AS type,
        r.price_per_night AS price,
        r.area,
        r.bed_type AS bed,
        r.max_occupancy AS occupancy,
        r.status,
        r.description
        {extra_columns}
    """


def list_rooms(room_type: str = "", guests: int = 1, sort_by: str = "price") -> list[dict]:
    order_column = SORT_COLUMNS.get(sort_by, "r.price_per_night")
    conditions = ["r.max_occupancy >= %s"]
    parameters = [guests]

    if room_type:
        conditions.append("r.room_type = %s")
        parameters.append(room_type)

    query = f"""
        SELECT
            {room_select_columns(", r.status AS availability_status, (r.status = 'Available') AS can_book")}
        FROM room r
        WHERE {" AND ".join(conditions)}
        ORDER BY {order_column}
    """

    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(query, parameters)
            return [decorate_room(room) for room in cursor.fetchall()]


def list_all_rooms() -> list[dict]:
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT {room_select_columns()}
                FROM room r
                ORDER BY r.room_id
                """
            )
            return [decorate_room(room) for room in cursor.fetchall()]


def get_room_by_code(room_identifier: str) -> dict | None:
    column, value = parse_room_identifier(room_identifier)
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT {room_select_columns()}
                FROM room r
                WHERE r.{column} = %s
                """,
                (value,),
            )
            return decorate_room(cursor.fetchone())


def create_room(data: dict[str, str]) -> None:
    room_type = data["room_type"]
    room_status = data["room_status"]
    if room_type not in VALID_ROOM_TYPES:
        raise ValueError("Invalid room type.")
    if room_status not in VALID_ROOM_STATUSES:
        raise ValueError("Invalid room status.")

    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO room (
                    room_number,
                    room_type,
                    price_per_night,
                    area,
                    bed_type,
                    max_occupancy,
                    status,
                    description
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s)
                """,
                (
                    data["room_number"],
                    room_type,
                    data["price_per_night"],
                    data["area"],
                    data["bed_type"],
                    data["max_occupancy"],
                    room_status,
                    data["description"],
                ),
            )


def update_room(data: dict[str, str]) -> None:
    room_type = data["room_type"]
    room_status = data["room_status"]
    if room_type not in VALID_ROOM_TYPES:
        raise ValueError("Invalid room type.")
    if room_status not in VALID_ROOM_STATUSES:
        raise ValueError("Invalid room status.")

    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE room
                SET room_number = %s,
                    room_type = %s,
                    price_per_night = %s,
                    area = %s,
                    bed_type = %s,
                    max_occupancy = %s,
                    status = %s,
                    description = %s
                WHERE room_id = %s
                """,
                (
                    data["room_number"],
                    room_type,
                    data["price_per_night"],
                    data["area"],
                    data["bed_type"],
                    data["max_occupancy"],
                    room_status,
                    data["description"],
                    data["room_id"],
                ),
            )


def delete_room(room_identifier: str) -> None:
    column, value = parse_room_identifier(room_identifier)
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(f"SELECT room_id FROM room WHERE {column} = %s", (value,))
            room = cursor.fetchone()
            if room is None:
                return
            cursor.execute("SELECT booking_id FROM booking WHERE room_id = %s LIMIT 1", (room["room_id"],))
            if cursor.fetchone() is not None:
                cursor.execute("UPDATE room SET status = 'Maintenance' WHERE room_id = %s", (room["room_id"],))
                return
            cursor.execute("DELETE FROM room WHERE room_id = %s", (room["room_id"],))


def search_available_rooms(
    check_in: str,
    check_out: str,
    guests: int,
    room_type: str = "",
    sort_by: str = "price",
) -> list[dict]:
    order_column = SORT_COLUMNS.get(sort_by, "r.price_per_night")
    overlap_filter = """
        NOT EXISTS (
            SELECT 1
            FROM booking b
            WHERE b.room_id = r.room_id
              AND b.booking_status NOT IN ('Cancelled', 'Checked-out')
              AND b.check_in_date < %s
              AND b.check_out_date > %s
        )
    """
    parameters = [guests, check_out, check_in]
    conditions = [
        "r.status = 'Available'",
        "r.max_occupancy >= %s",
        overlap_filter,
    ]

    if room_type:
        conditions.append("r.room_type = %s")
        parameters.append(room_type)

    query = f"""
        SELECT
            {room_select_columns(f'''
            , 'Available for selected dates' AS availability_status,
            TRUE AS can_book
            ''')}
        FROM room r
        WHERE {" AND ".join(conditions)}
        ORDER BY {order_column}
    """

    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(query, parameters)
            return [decorate_room(room) for room in cursor.fetchall()]


def find_account_by_email(email: str) -> dict | None:
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT account_id, email, password_hash, full_name, phone
                FROM account
                WHERE LOWER(email) = LOWER(%s)
                """,
                (email,),
            )
            return cursor.fetchone()


def authenticate_user(email: str, password: str) -> dict | None:
    account = find_account_by_email(email)
    if account is None or not verify_password(password, account["password_hash"]):
        return None

    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT account_status FROM member WHERE account_id = %s", (account["account_id"],))
            member = cursor.fetchone()
            if member is not None:
                if member["account_status"] == "Locked":
                    return None
                account["role"] = "member"
                account["member_id"] = account["account_id"]
                return account

            cursor.execute("SELECT account_id FROM admin WHERE account_id = %s", (account["account_id"],))
            admin = cursor.fetchone()
            if admin is not None:
                account["role"] = "admin"
                return account

    return None


def register_member(email: str, password: str, full_name: str, phone: str) -> int:
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                INSERT INTO account (email, password_hash, full_name, phone)
                VALUES (%s, %s, %s, %s)
                RETURNING account_id
                """,
                (email, hash_password(password), full_name, phone),
            )
            account_id = cursor.fetchone()["account_id"]
            cursor.execute(
                """
                INSERT INTO member (account_id, account_status)
                VALUES (%s, 'Active')
                """,
                (account_id,),
            )
            return account_id


def get_member_profile(account_id: int) -> dict | None:
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    a.account_id,
                    a.email,
                    a.full_name,
                    a.phone,
                    m.gender,
                    m.date_of_birth,
                    m.address,
                    m.account_status
                FROM account a
                JOIN member m ON m.account_id = a.account_id
                WHERE a.account_id = %s
                """,
                (account_id,),
            )
            profile = cursor.fetchone()
            if profile is not None:
                profile["member_id"] = profile["account_id"]
            return profile


def update_member_profile(account_id: int, data: dict[str, str]) -> None:
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE account
                SET full_name = %s, phone = %s
                WHERE account_id = %s
                """,
                (data["full_name"], data["phone"], account_id),
            )
            cursor.execute(
                """
                UPDATE member
                SET gender = %s,
                    date_of_birth = %s,
                    address = %s
                WHERE account_id = %s
                """,
                (
                    data.get("gender") or None,
                    data.get("date_of_birth") or None,
                    data.get("address") or None,
                    account_id,
                ),
            )


def update_member_password(account_id: int, password: str) -> None:
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE account
                SET password_hash = %s
                WHERE account_id = %s
                """,
                (hash_password(password), account_id),
            )


def reset_password_for_email(email: str, notifier=None) -> str | None:
    account = find_account_by_email(email)
    if account is None:
        return None

    new_password = generate_random_password()
    if notifier is not None:
        notifier(email, new_password)
    update_member_password(account["account_id"], new_password)
    return new_password


def get_member_bookings(account_id: int) -> list[dict]:
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    b.booking_id,
                    b.guest_full_name,
                    b.guest_id_card AS guest_id_number,
                    b.guest_phone,
                    r.room_type,
                    r.room_number,
                    b.check_in_date,
                    b.check_out_date,
                    b.number_of_nights,
                    b.total_amount,
                    b.booking_status,
                    p.payment_status
                FROM booking b
                JOIN room r ON b.room_id = r.room_id
                JOIN payment p ON p.booking_id = b.booking_id
                WHERE b.account_id = %s
                ORDER BY b.created_at DESC
                """,
                (account_id,),
            )
            bookings = []
            for booking in cursor.fetchall():
                booking["booking_code"] = display_booking_code(booking["booking_id"])
                bookings.append(booking)
            return bookings


def get_booking_by_code(booking_identifier: str, account_id: int | None = None) -> dict | None:
    booking_id = parse_booking_identifier(booking_identifier)
    parameters = [booking_id]
    account_filter = ""
    if account_id is not None:
        account_filter = "AND b.account_id = %s"
        parameters.append(account_id)

    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT
                    b.booking_id,
                    a.full_name AS member_name,
                    a.email AS member_email,
                    b.guest_full_name,
                    b.guest_id_card AS guest_id_number,
                    b.guest_phone,
                    r.room_id,
                    r.room_number,
                    r.room_type,
                    b.check_in_date,
                    b.check_out_date,
                    b.number_of_guests,
                    b.number_of_nights,
                    b.total_amount,
                    b.booking_status,
                    p.payment_status
                FROM booking b
                JOIN account a ON b.account_id = a.account_id
                JOIN room r ON b.room_id = r.room_id
                JOIN payment p ON p.booking_id = b.booking_id
                WHERE b.booking_id = %s
                {account_filter}
                """,
                parameters,
            )
            booking = cursor.fetchone()
            if booking is not None:
                booking["booking_code"] = display_booking_code(booking["booking_id"])
                booking["room_code"] = str(booking["room_id"])
            return booking


def get_all_bookings() -> list[dict]:
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                SELECT
                    b.booking_id,
                    a.full_name AS member,
                    r.room_type || ' ' || r.room_number AS room,
                    b.check_in_date || ' - ' || b.check_out_date AS dates,
                    b.total_amount AS total,
                    b.booking_status AS status,
                    p.payment_status AS payment
                FROM booking b
                JOIN account a ON b.account_id = a.account_id
                JOIN room r ON b.room_id = r.room_id
                JOIN payment p ON p.booking_id = b.booking_id
                ORDER BY b.created_at DESC
                """
            )
            bookings = []
            for booking in cursor.fetchall():
                booking["booking_code"] = display_booking_code(booking["booking_id"])
                bookings.append(booking)
            return bookings


def update_booking_status(booking_identifier: str, status: str) -> None:
    if status not in VALID_BOOKING_STATUSES:
        raise ValueError("Invalid booking status.")

    booking_id = parse_booking_identifier(booking_identifier)
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT booking_status FROM booking WHERE booking_id = %s FOR UPDATE",
                (booking_id,),
            )
            booking = cursor.fetchone()
            if booking is None:
                raise ValueError("Booking not found.")
            allowed_transitions = {
                "New": {"Confirmed", "Cancelled"},
                "Confirmed": {"Checked-in", "Cancelled"},
                "Checked-in": {"Checked-out"},
                "Checked-out": set(),
                "Cancelled": set(),
            }
            if status not in allowed_transitions[booking["booking_status"]]:
                raise ValueError("Invalid booking status transition.")
            cursor.execute(
                """
                UPDATE booking
                SET booking_status = %s
                WHERE booking_id = %s
                """,
                (status, booking_id),
            )
            if status == "Cancelled":
                cursor.execute(
                    """
                    UPDATE payment
                    SET payment_status = 'Refund Pending'
                    WHERE booking_id = %s
                      AND payment_status = 'Paid'
                    """,
                    (booking_id,),
                )


def list_members(search: str = "") -> list[dict]:
    parameters = []
    where = ""
    if search:
        like = f"%{search}%"
        parameters = [like, like, like]
        where = """
            WHERE LOWER(a.full_name) LIKE LOWER(%s)
               OR LOWER(a.email) LIKE LOWER(%s)
               OR a.phone LIKE %s
        """

    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                f"""
                SELECT
                    m.account_id AS id,
                    a.full_name AS name,
                    a.email,
                    a.phone,
                    m.account_status AS status
                FROM member m
                JOIN account a ON m.account_id = a.account_id
                {where}
                ORDER BY m.account_id
                """,
                parameters,
            )
            return list(cursor.fetchall())


def update_member_status(account_id: int, status: str) -> None:
    if status not in {"Active", "Locked"}:
        raise ValueError("Invalid member status.")

    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE member
                SET account_status = %s
                WHERE account_id = %s
                """,
                (status, account_id),
            )


def get_dashboard_statistics() -> dict:
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) AS total_rooms FROM room")
            total_rooms = cursor.fetchone()["total_rooms"]
            cursor.execute("SELECT COUNT(*) AS available_rooms FROM room WHERE status = 'Available'")
            available_rooms = cursor.fetchone()["available_rooms"]
            cursor.execute(
                """
                SELECT COUNT(*) AS current_bookings
                FROM booking
                WHERE booking_status NOT IN ('Cancelled', 'Checked-out')
                  AND check_out_date > CURRENT_DATE
                """
            )
            current_bookings = cursor.fetchone()["current_bookings"]
            cursor.execute("SELECT COUNT(*) AS registered_members FROM member")
            registered_members = cursor.fetchone()["registered_members"]
            cursor.execute("SELECT COALESCE(SUM(amount), 0) AS total_revenue FROM payment WHERE payment_status = 'Paid'")
            total_revenue = cursor.fetchone()["total_revenue"]
            cursor.execute("SELECT COUNT(*) AS count FROM booking WHERE check_in_date = CURRENT_DATE AND booking_status <> 'Cancelled'")
            checking_in_today = cursor.fetchone()["count"]
            cursor.execute("SELECT COUNT(*) AS count FROM booking WHERE check_out_date = CURRENT_DATE AND booking_status <> 'Cancelled'")
            checking_out_today = cursor.fetchone()["count"]
            cursor.execute("SELECT COUNT(*) AS count FROM room WHERE status = 'Cleaning'")
            cleaning_rooms = cursor.fetchone()["count"]
            cursor.execute("SELECT COUNT(*) AS count FROM room WHERE status = 'Maintenance'")
            maintenance_rooms = cursor.fetchone()["count"]

    return {
        "total_rooms": total_rooms,
        "available_rooms": available_rooms,
        "current_bookings": current_bookings,
        "registered_members": registered_members,
        "total_revenue": total_revenue,
        "checking_in_today": checking_in_today,
        "checking_out_today": checking_out_today,
        "cleaning_rooms": cleaning_rooms,
        "maintenance_rooms": maintenance_rooms,
    }


def get_report_summary() -> dict:
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute("SELECT COUNT(*) AS total_bookings FROM booking")
            total_bookings = cursor.fetchone()["total_bookings"]
            cursor.execute("SELECT COALESCE(SUM(amount), 0) AS revenue FROM payment WHERE payment_status = 'Paid'")
            revenue = cursor.fetchone()["revenue"]
            cursor.execute("SELECT COUNT(*) AS total_rooms FROM room")
            total_rooms = cursor.fetchone()["total_rooms"]
            cursor.execute(
                """
                SELECT COUNT(DISTINCT room_id) AS occupied_rooms
                FROM booking
                WHERE booking_status NOT IN ('Cancelled', 'Checked-out')
                  AND check_in_date <= CURRENT_DATE
                  AND check_out_date > CURRENT_DATE
                """
            )
            occupied_rooms = cursor.fetchone()["occupied_rooms"]
            cursor.execute(
                """
                SELECT booking_status, COUNT(*) AS count
                FROM booking
                GROUP BY booking_status
                ORDER BY booking_status
                """
            )
            status_counts = cursor.fetchall()

    occupancy = 0
    if total_rooms:
        occupancy = round((occupied_rooms / total_rooms) * 100)

    return {
        "total_bookings": total_bookings,
        "revenue": revenue,
        "occupancy": occupancy,
        "status_counts": status_counts,
    }
