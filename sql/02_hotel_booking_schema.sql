CREATE TABLE IF NOT EXISTS account (
    account_id BIGSERIAL PRIMARY KEY,
    email VARCHAR(100) NOT NULL UNIQUE,
    password_hash VARCHAR(255) NOT NULL,
    full_name VARCHAR(50) NOT NULL,
    phone VARCHAR(20)
);

CREATE TABLE IF NOT EXISTS member (
    account_id BIGINT PRIMARY KEY,
    gender VARCHAR(20),
    date_of_birth DATE,
    address VARCHAR(200),
    account_status VARCHAR(20) NOT NULL DEFAULT 'Active',

    FOREIGN KEY (account_id)
        REFERENCES account(account_id)
        ON DELETE CASCADE,

    CHECK (account_status IN ('Active', 'Locked'))
);

CREATE TABLE IF NOT EXISTS admin (
    account_id BIGINT PRIMARY KEY,

    FOREIGN KEY (account_id)
        REFERENCES account(account_id)
        ON DELETE CASCADE
);

CREATE TABLE IF NOT EXISTS room (
    room_id BIGSERIAL PRIMARY KEY,
    room_number VARCHAR(20) NOT NULL UNIQUE,
    room_type VARCHAR(20) NOT NULL,
    price_per_night NUMERIC(10, 2) NOT NULL,
    area DOUBLE PRECISION NOT NULL,
    bed_type VARCHAR(50) NOT NULL,
    max_occupancy INTEGER NOT NULL,
    status VARCHAR(20) NOT NULL DEFAULT 'Available',
    description TEXT,

    CHECK (room_type IN ('Standard', 'Superior', 'Deluxe', 'Suite')),
    CHECK (status IN ('Available', 'Occupied', 'Cleaning', 'Maintenance')),
    CHECK (price_per_night > 0),
    CHECK (area > 0),
    CHECK (max_occupancy > 0)
);

CREATE TABLE IF NOT EXISTS booking (
    booking_id BIGSERIAL PRIMARY KEY,
    account_id BIGINT NOT NULL,
    room_id BIGINT NOT NULL,
    guest_id_card VARCHAR(50) NOT NULL,
    guest_full_name VARCHAR(100) NOT NULL,
    guest_phone VARCHAR(20) NOT NULL,
    check_in_date DATE NOT NULL,
    check_out_date DATE NOT NULL,
    number_of_guests INTEGER NOT NULL,
    number_of_nights INTEGER NOT NULL,
    total_amount NUMERIC(10, 2) NOT NULL,
    booking_status VARCHAR(20) NOT NULL DEFAULT 'New',
    created_at TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (account_id)
        REFERENCES member(account_id)
        ON DELETE RESTRICT,

    FOREIGN KEY (room_id)
        REFERENCES room(room_id)
        ON DELETE RESTRICT,

    CHECK (check_out_date > check_in_date),
    CHECK (number_of_guests > 0),
    CHECK (number_of_nights > 0),
    CHECK (total_amount >= 0),
    CHECK (booking_status IN ('New', 'Confirmed', 'Checked-in', 'Checked-out', 'Cancelled'))
);

CREATE TABLE IF NOT EXISTS payment (
    payment_id BIGSERIAL PRIMARY KEY,
    booking_id BIGINT NOT NULL UNIQUE,
    payment_status VARCHAR(20) NOT NULL DEFAULT 'Paid',
    amount NUMERIC(10, 2) NOT NULL,
    payment_date TIMESTAMP NOT NULL DEFAULT CURRENT_TIMESTAMP,

    FOREIGN KEY (booking_id)
        REFERENCES booking(booking_id)
        ON DELETE CASCADE,

    CHECK (payment_status IN ('Paid', 'Refund Pending')),
    CHECK (amount >= 0)
);

CREATE INDEX IF NOT EXISTS idx_booking_room_dates
    ON booking(room_id, check_in_date, check_out_date);

CREATE INDEX IF NOT EXISTS idx_booking_account
    ON booking(account_id);

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
VALUES
    (
        '211',
        'Standard',
        110,
        24,
        'Queen bed',
        2,
        'Available',
        'A bright room for short city stays with a work desk, rainfall shower, and quiet courtyard view.'
    ),
    (
        '305',
        'Superior',
        145,
        31,
        'King bed',
        3,
        'Available',
        'A larger room with a lounge chair, breakfast nook, and generous storage for longer stays.'
    ),
    (
        '403',
        'Deluxe',
        180,
        38,
        'King bed',
        3,
        'Available',
        'A refined room with harbor-facing windows, premium linens, and a marble bathroom.'
    ),
    (
        '610',
        'Suite',
        295,
        58,
        'King bed and sofa bed',
        5,
        'Available',
        'A separate bedroom and living room suite for families, special occasions, and extended stays.'
    ),
    (
        '118',
        'Standard',
        95,
        22,
        'Twin beds',
        2,
        'Cleaning',
        'A compact twin room with practical storage and easy lobby access.'
    ),
    (
        '512',
        'Deluxe',
        210,
        42,
        'Two queen beds',
        4,
        'Available',
        'A spacious double queen room for small groups with a wide city view.'
    )
ON CONFLICT (room_number) DO NOTHING;
