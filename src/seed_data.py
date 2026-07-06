from database import get_connection
from security import hash_password


def create_member() -> None:
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT account_id FROM account WHERE LOWER(email) = LOWER(%s)",
                ("member@example.com",),
            )
            existing = cursor.fetchone()
            if existing is not None:
                cursor.execute(
                    """
                    UPDATE account
                    SET password_hash = %s, full_name = %s, phone = %s
                    WHERE account_id = %s
                    """,
                    (hash_password("password123"), "Maya Chen", "+1 555 0148", existing["account_id"]),
                )
                cursor.execute(
                    "UPDATE member SET account_status = 'Active' WHERE account_id = %s",
                    (existing["account_id"],),
                )
                return

            cursor.execute(
                """
                INSERT INTO account (email, password_hash, full_name, phone)
                VALUES (%s, %s, %s, %s)
                RETURNING account_id
                """,
                (
                    "member@example.com",
                    hash_password("password123"),
                    "Maya Chen",
                    "+1 555 0148",
                ),
            )
            account_id = cursor.fetchone()["account_id"]
            cursor.execute(
                """
                INSERT INTO member (account_id, date_of_birth, gender, address, account_status)
                VALUES (%s, %s, %s, %s, 'Active')
                """,
                (account_id, "1995-04-15", "Female", "212 Bay Street"),
            )


def create_admin() -> None:
    with get_connection() as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                "SELECT account_id FROM account WHERE LOWER(email) = LOWER(%s)",
                ("admin@harborview.test",),
            )
            existing = cursor.fetchone()
            if existing is not None:
                cursor.execute(
                    "UPDATE account SET password_hash = %s WHERE account_id = %s",
                    (hash_password("admin123"), existing["account_id"]),
                )
                return

            cursor.execute(
                """
                INSERT INTO account (email, password_hash, full_name, phone)
                VALUES (%s, %s, %s, %s)
                RETURNING account_id
                """,
                (
                    "admin@harborview.test",
                    hash_password("admin123"),
                    "Hotel Administrator",
                    "+1 555 0100",
                ),
            )
            account_id = cursor.fetchone()["account_id"]
            cursor.execute("INSERT INTO admin (account_id) VALUES (%s)", (account_id,))


if __name__ == "__main__":
    create_member()
    create_admin()
    print("Sample accounts created successfully.")
