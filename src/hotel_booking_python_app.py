from http import HTTPStatus
from http.cookies import SimpleCookie
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from pathlib import Path
from urllib.parse import parse_qs, urlencode, urlparse
from datetime import date, timedelta
import html

from config import HOST, PORT, SESSION_LIFETIME_MINUTES
from integrations import email_service, payment_gateway
from repository import (
    authenticate_user,
    create_room,
    delete_room,
    get_all_bookings,
    get_booking_by_code,
    get_dashboard_statistics,
    get_member_bookings,
    get_member_profile,
    get_report_summary,
    get_room_by_code,
    list_members,
    list_all_rooms,
    list_rooms,
    register_member,
    reset_password_for_email,
    search_available_rooms,
    update_room,
    update_booking_status,
    update_member_password,
    update_member_profile,
    update_member_status,
)
from services import cancel_booking, create_booking_and_payment
from session_store import SessionStore
from validators import validate_email, validate_guests, validate_required, validate_stay_dates


BASE_DIR = Path(__file__).resolve().parent
PROJECT_DIR = BASE_DIR.parent
INTERFACE_DIR = PROJECT_DIR / "interface"

SESSION_STORE = SessionStore(SESSION_LIFETIME_MINUTES)


def esc(value):
    return html.escape(str(value), quote=True)


def notice(message="", error=False):
    if not message:
        return ""
    kind = "error-message" if error else "success-message"
    return f'<div class="{kind}" role="alert">{esc(message)}</div>'


def message_url(path, message, error=False):
    separator = "&" if "?" in path else "?"
    return path + separator + urlencode({"message": message, "error": "1" if error else "0"})


def money(value):
    return f"${float(value):,.0f}"


def first_value(data, key, default=""):
    value = data.get(key, [default])
    return value[0] if value else default


def clean_query_value(value):
    return str(value or "").replace(" ", "").strip()


def keep_booking_params(params):
    kept = {}
    for key in ["checkin", "checkout", "guests"]:
        raw_value = params.get(key, [""]) if hasattr(params, "get") else ""
        value = raw_value[0] if isinstance(raw_value, list) else raw_value
        value = clean_query_value(value) if key in {"checkin", "checkout", "guests"} else value
        if value:
            kept[key] = value
    return kept


def room_data_from_post(data):
    return {
        "room_id": first_value(data, "room_id").strip(),
        "room_number": first_value(data, "room_number").strip(),
        "room_type": first_value(data, "room_type"),
        "description": first_value(data, "description").strip(),
        "price_per_night": first_value(data, "price_per_night"),
        "area": first_value(data, "area"),
        "bed_type": first_value(data, "bed_type").strip(),
        "max_occupancy": first_value(data, "max_occupancy"),
        "room_status": first_value(data, "room_status"),
    }


def room_by_id(room_id):
    try:
        return get_room_by_code(room_id)
    except Exception:
        return None


def room_missing_page(logged_in=False):
    body = '<section class="view active"><div class="confirmation"><p class="eyebrow">Room</p><h1>Room Not Found</h1><p>The room does not exist or the database is unavailable.</p><a href="/rooms">Back to Rooms</a></div></section>'
    return page("Room Not Found - Lucky Hotel", body, logged_in, "rooms")


def room_can_book(room):
    return bool(room.get("can_book", room.get("status") == "Available"))


def room_availability_label(room):
    return room.get("availability_status") or room.get("status", "Available")


def room_status_text(room):
    return f"Room status: {room.get('status', 'Available')}"


def room_bookability_for_dates(room, params):
    context = keep_booking_params(params)
    if not {"checkin", "checkout", "guests"}.issubset(context):
        return room_can_book(room), room_availability_label(room)

    try:
        guests = int(context["guests"] or 1)
        validate_stay_dates(context["checkin"], context["checkout"])
        dated_rooms = search_available_rooms(context["checkin"], context["checkout"], guests)
    except Exception:
        return False, "Invalid booking dates"

    dated_room = next((item for item in dated_rooms if item["id"] == room["id"]), None)
    if dated_room is None:
        return False, "Not available for selected guests"
    return room_can_book(dated_room), room_availability_label(dated_room)


def available_rooms(params):
    room_type = params.get("type", [""])[0].strip()
    sort_by = params.get("sort", ["price"])[0].strip()
    try:
        guests = validate_guests(clean_query_value(params.get("guests", ["1"])[0]) or "1")
    except ValueError:
        return []

    check_in = clean_query_value(params.get("checkin", [""])[0])
    check_out = clean_query_value(params.get("checkout", [""])[0])
    try:
        if check_in and check_out:
            validate_stay_dates(check_in, check_out)
            rooms = search_available_rooms(check_in, check_out, guests, room_type, sort_by)
            return [room for room in rooms if room_can_book(room)]
        return list_rooms(room_type=room_type, guests=guests, sort_by=sort_by)
    except Exception:
        return []


def button_form(action, label, values=None, ghost=False):
    values = values or {}
    fields = "".join(f'<input type="hidden" name="{esc(key)}" value="{esc(value)}">' for key, value in values.items())
    css = ' class="ghost"' if ghost else ""
    return f'<form class="inline-form" method="get" action="{action}">{fields}<button type="submit"{css}>{label}</button></form>'


def room_card(room, context=None):
    context = context or {}
    room_values = {"id": room["id"], **context}
    can_book = room_can_book(room)
    status_class = "available" if can_book else "blocked"
    select_action = (
        button_form('/select', 'Select Room', room_values, ghost=True)
        if can_book
        else '<span class="disabled-action">Unavailable</span>'
    )
    return f"""
    <article class="room-card">
      <img src="{esc(room['image'])}" alt="{esc(room['type'])} room {esc(room['number'])}">
      <div>
        <p class="eyebrow">{esc(room.get('display_id', room['id']))}</p>
        <h3>{esc(room['type'])} Room {esc(room['number'])}</h3>
        <p>{esc(room['description'])}</p>
        <p class="room-status {status_class}">{esc(room_status_text(room))}</p>
        <div class="room-facts">
          <span>{money(room['price'])} / night</span>
          <span>{room['area']} m2</span>
          <span>{esc(room['bed'])}</span>
          <span>{room['occupancy']} guests</span>
        </div>
        <div class="card-actions">
          {button_form('/room', 'View Detail', room_values)}
          {select_action}
        </div>
      </div>
    </article>
    """


def header(logged_in=False, active="home"):
    member_nav = """
      <a href="/bookings">My Bookings</a>
      <a href="/profile">Profile</a>
      <form class="nav-form" method="post" action="/logout"><button class="logout-link" type="submit">Logout</button></form>
    """
    guest_nav = """
      <a href="/login">Login</a>
      <a class="nav-action" href="/register">Register</a>
    """
    return f"""
    <header class="topbar">
      <a class="brand" href="/">
        <span class="brand-mark">LH</span>
        <span>Lucky Hotel</span>
      </a>
      <nav class="nav" id="mainNav" aria-label="Main navigation">
        <a class="{active == 'home' and 'active' or ''}" href="/">Home</a>
        <a class="{active == 'rooms' and 'active' or ''}" href="/rooms">Rooms</a>
        {member_nav if logged_in else guest_nav}
      </nav>
    </header>
    """


def page(title, body, logged_in=False, active="home", extra_css=""):
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{esc(title)}</title>
  <link rel="preconnect" href="https://images.unsplash.com">
  <link rel="stylesheet" href="/hotel-booking-style.css">
  {extra_css}
</head>
<body>
  {header(logged_in, active)}
  <main>{body}</main>
</body>
</html>"""


def home_page(logged_in=False, member_name="Maya Chen"):
    earliest_check_in = date.today().isoformat()
    default_check_out = (date.today() + timedelta(days=1)).isoformat()
    type_cards = ""
    rooms_by_type = {}
    try:
        for room in list_all_rooms():
            rooms_by_type.setdefault(room["type"], room)
    except Exception:
        rooms_by_type = {}
    for room_type, room in rooms_by_type.items():
        type_cards += f"""
        <article class="type-card">
          <img src="{esc(room['image'])}" alt="{room_type} room">
          <div>
            <h3>{room_type}</h3>
            <p>{esc(room['description'])}</p>
            {button_form('/rooms', 'View Rooms', {'type': room_type})}
          </div>
        </article>
        """
    panel = """
      <section class="member-panel">
        <div><p class="eyebrow">Member Access</p><h2>Your account is active</h2><p>Continue booking, check your booking history, or update your profile.</p></div>
        <div class="guest-panel-actions"><a href="/bookings">My Bookings</a><a href="/profile">Profile</a></div>
      </section>
    """ if logged_in else """
      <section class="guest-panel">
        <div><p class="eyebrow">Guest Access</p><h2>Browse rooms without an account</h2><p>Room search, room type browsing, and room details are open to guests. Login or register when you want to reserve a selected room.</p></div>
        <div class="guest-panel-actions"><a href="/login">Login</a><a href="/register">Register</a></div>
      </section>
    """
    hero_actions = f'<div class="member-hero-actions"><span>Welcome back, {esc(member_name)}</span><form class="inline-form" method="get" action="/bookings"><button type="submit">My Bookings</button></form></div>' if logged_in else '<div class="guest-hero-actions"><a href="/login">Login</a><a href="/register">Create Account</a></div>'
    featured_params = {
        "checkin": [earliest_check_in],
        "checkout": [(date.today() + timedelta(days=7)).isoformat()],
        "guests": ["1"],
    }
    # Featured rooms use the next week only to choose cards. The guest still
    # selects their own stay dates after choosing a featured room.
    featured = "".join(room_card(room) for room in available_rooms(featured_params))
    featured = featured or '<p class="empty-state" style="display:block">No rooms are available for the full next seven days.</p>'
    body = f"""
    <section class="view active" id="home">
      <div class="hero">
        <div class="hero-copy">
          <p class="eyebrow">Hotel Room Booking System</p>
          <h1>Lucky Hotel</h1>
          <p>Find a room first, then sign in only when you are ready to complete the booking.</p>
          {hero_actions}
        </div>
      </div>
      <form class="search-panel" method="get" action="/rooms">
        <label><span>Check-in</span><input type="date" name="checkin" min="{earliest_check_in}" required></label>
        <label><span>Check-out</span><input type="date" name="checkout" min="{default_check_out}" required></label>
        <label><span>Guests</span><input type="number" name="guests" min="1" max="6" required></label>
        <button type="submit">Search Rooms</button>
      </form>
      {panel}
      <section class="content-band"><div class="section-heading"><p class="eyebrow">Browse by Room Type</p><h2>Choose the stay that fits</h2></div><div class="type-grid">{type_cards}</div></section>
      <section class="content-band featured"><div class="section-heading"><p class="eyebrow">Featured Rooms</p><h2>Available this week</h2></div><div class="room-grid">{featured}</div></section>
    </section>
    """
    return page("Lucky Hotel Booking", body, logged_in, "home")


def rooms_page(params, logged_in=False):
    search_error = ""
    check_in = clean_query_value(params.get("checkin", [""])[0])
    check_out = clean_query_value(params.get("checkout", [""])[0])
    try:
        validate_guests(clean_query_value(params.get("guests", ["1"])[0]) or "1")
    except (ValueError, TypeError):
        search_error = "Number of guests must be greater than zero."
    if check_in or check_out:
        try:
            if not check_in or not check_out:
                raise ValueError("Both check-in and check-out dates are required.")
            validate_stay_dates(check_in, check_out)
        except (ValueError, TypeError) as error:
            search_error = str(error) or "Invalid stay dates."
    rooms = [] if search_error else available_rooms(params)
    context = keep_booking_params(params)
    cards = "".join(room_card(room, context) for room in rooms) or '<p class="empty-state" style="display:block">No rooms match this search. Try different dates or guest count.</p>'
    sort = params.get("sort", ["price"])[0]
    room_type = params.get("type", [""])[0]
    hidden_context = "".join(f'<input type="hidden" name="{esc(key)}" value="{esc(value)}">' for key, value in context.items())
    body = f"""
    <section class="view active" id="rooms">
      {notice(search_error, True)}
      <div class="page-heading">
        <div><p class="eyebrow">Room List</p><h1>Search Results</h1></div>
        <form class="sort-control" method="get" action="/rooms">
          {hidden_context}
          <label><span>Room type</span><select name="type" onchange="this.form.submit()">
            <option value="" {'selected' if not room_type else ''}>All room types</option>
            <option value="Standard" {'selected' if room_type == 'Standard' else ''}>Standard</option>
            <option value="Superior" {'selected' if room_type == 'Superior' else ''}>Superior</option>
            <option value="Deluxe" {'selected' if room_type == 'Deluxe' else ''}>Deluxe</option>
            <option value="Suite" {'selected' if room_type == 'Suite' else ''}>Suite</option>
          </select></label>
          <label><span>Sort by</span>
          <select name="sort" onchange="this.form.submit()">
            <option value="price" {'selected' if sort == 'price' else ''}>Room price</option>
            <option value="area" {'selected' if sort == 'area' else ''}>Room area</option>
            <option value="occupancy" {'selected' if sort == 'occupancy' else ''}>Maximum occupancy</option>
          </select></label>
        </form>
      </div>
      <div class="room-grid">{cards}</div>
    </section>
    """
    return page("Rooms - Lucky Hotel", body, logged_in, "rooms")


def room_detail_page(room, logged_in=False, context=None):
    context = context or {}
    can_book, _availability_label = room_bookability_for_dates(room, context)
    select_action = (
        button_form('/select', 'Select Room', {'id': room['id'], **context})
        if can_book
        else '<span class="disabled-action">Unavailable for booking</span>'
    )
    body = f"""
    <section class="view active" id="detail">
      <div class="detail-layout">
        <img src="{esc(room['image'])}" alt="{esc(room['type'])} room {esc(room['number'])}">
        <div class="detail-panel">
          <p class="eyebrow">{esc(room['id'])}</p>
          <h1>{esc(room['type'])} Room {esc(room['number'])}</h1>
          <p>{esc(room['description'])}</p>
          <div class="detail-list">
            <div><span>Price per night</span><strong>{money(room['price'])}</strong></div>
            <div><span>Bed type</span><strong>{esc(room['bed'])}</strong></div>
            <div><span>Room status</span><strong>{esc(room['status'])}</strong></div>
            <div><span>Room area</span><strong>{room['area']} m2</strong></div>
            <div><span>Maximum occupancy</span><strong>{room['occupancy']} guests</strong></div>
            <div><span>Room number</span><strong>{esc(room['number'])}</strong></div>
          </div>
          {select_action}
        </div>
      </div>
    </section>
    """
    return page(f"{room['type']} Room", body, logged_in, "rooms")


def login_page(next_url="/bookings", message=""):
    body = f"""
    <section class="view active" id="login">
      <div class="auth-layout">
        <div class="auth-media"></div>
        <form class="form-card" method="post" action="/login">
          <p class="eyebrow">Secure Access</p>
          <h1>Login</h1>
          {notice(message, True)}
          <input type="hidden" name="next" value="{esc(next_url)}">
          <label><span>Email Address</span><input type="email" name="email" autocomplete="email" required></label>
          <label><span>Password</span><input type="password" name="password" autocomplete="current-password" required></label>
          <button type="submit">Login</button>
          <div class="inline-links"><a href="/forgot">Forgot Password</a><a href="/register">Register Account</a></div>
        </form>
      </div>
    </section>
    """
    return page("Login - Lucky Hotel", body, False, "login")


def register_page(message=""):
    fields = """
      <label><span>Full name</span><input name="name" autocomplete="name" required></label>
      <label><span>Date of birth</span><input type="date" name="dob" required></label>
      <label><span>Gender</span><select name="gender" required><option value="" selected disabled>Select gender</option><option>Female</option><option>Male</option><option>Other</option></select></label>
      <label><span>Phone number</span><input name="phone" autocomplete="tel" required></label>
      <label class="wide"><span>Address</span><input name="address" autocomplete="street-address" required></label>
      <label><span>Email address</span><input type="email" name="email" autocomplete="email" required></label>
      <label><span>Password</span><input type="password" name="password" autocomplete="new-password" required></label>
      <label><span>Confirm password</span><input type="password" name="confirm" autocomplete="new-password" required></label>
    """
    body = f'<section class="view active" id="register"><form class="wide-form" method="post" action="/register"><p class="eyebrow">Member Account</p><h1>Register Account</h1>{notice(message, True)}<div class="form-grid">{fields}</div><button type="submit">Register Account</button></form></section>'
    return page("Register - Lucky Hotel", body, False, "register")


def booking_page(room, logged_in, params=None):
    params = params or {}
    earliest_check_in = date.today().isoformat()
    earliest_check_out = (date.today() + timedelta(days=1)).isoformat()
    feedback = notice(params.get("message", [""])[0], params.get("error", [""])[0] == "1")
    has_dates = bool(clean_query_value(params.get("checkin", [""])[0]) and clean_query_value(params.get("checkout", [""])[0]))
    if not has_dates:
        body = f"""
        <section class="view active" id="booking">{feedback}
          <form class="wide-form centered-card" method="get" action="/booking">
            <p class="eyebrow">Complete Booking</p>
            <h1>Select Stay Dates</h1>
            <input type="hidden" name="id" value="{esc(room['id'])}">
            <div class="form-grid">
              <label><span>Room</span><input value="{esc(room['type'])} Room {esc(room['number'])}" readonly></label>
              <label><span>Room status</span><input value="{esc(room['status'])}" readonly></label>
              <label><span>Check-in</span><input type="date" name="checkin" min="{earliest_check_in}" required></label>
              <label><span>Check-out</span><input type="date" name="checkout" min="{earliest_check_out}" required></label>
              <label><span>Guests</span><input type="number" name="guests" min="1" max="{esc(room['occupancy'])}" required></label>
            </div>
            <button type="submit">Check Availability</button>
          </form>
        </section>
        """
        return page("Select Stay Dates - Lucky Hotel", body, logged_in, "rooms")

    check_in = clean_query_value(params.get("checkin", [""])[0])
    check_out = clean_query_value(params.get("checkout", [""])[0])
    try:
        guests = int(clean_query_value(params.get("guests", ["2"])[0]) or 2)
    except ValueError:
        guests = 2
    try:
        check_in_date, check_out_date = validate_stay_dates(check_in, check_out)
        nights = (check_out_date - check_in_date).days
    except Exception as error:
        body = f'<section class="view active"><div class="confirmation"><p class="eyebrow">Invalid Stay Dates</p><h1>Dates Not Accepted</h1>{notice(str(error) or "Check-out must be after check-in.", True)}<a href="/booking?id={esc(room["id"])}">Choose Dates Again</a></div></section>'
        return page("Invalid Stay Dates - Lucky Hotel", body, logged_in, "rooms")
    can_book, _availability_label = room_bookability_for_dates(
        room,
        {"checkin": [check_in], "checkout": [check_out], "guests": [str(guests)]},
    )
    if not can_book:
        body = f"""
        <section class="view active" id="booking">
          <div class="confirmation">
            <p class="eyebrow">Complete Booking</p>
            <h1>Room Not Available</h1>
            <p>{esc(room['type'])} Room {esc(room['number'])} cannot be booked for the selected stay.</p>
            <div class="confirmation-grid">
              <span>Room status</span><strong>{esc(room['status'])}</strong>
              <span>Check-in</span><strong>{esc(check_in)}</strong>
              <span>Check-out</span><strong>{esc(check_out)}</strong>
              <span>Guests</span><strong>{esc(guests)}</strong>
            </div>
            <div class="guest-panel-actions">
              <a href="/rooms?{urlencode({'checkin': check_in, 'checkout': check_out, 'guests': guests})}">Choose Another Room</a>
              <a href="/room?{urlencode({'id': room['id'], 'checkin': check_in, 'checkout': check_out, 'guests': guests})}">Back to Room Detail</a>
            </div>
          </div>
        </section>
        """
        return page("Room Not Available - Lucky Hotel", body, logged_in, "rooms")
    total = room["price"] * nights
    body = f"""
    <section class="view active" id="booking">{feedback}
      <div class="booking-layout">
        <form class="wide-form" method="post" action="/confirmation">
          <p class="eyebrow">Complete Booking</p><h1>Guest Information</h1>
          <input type="hidden" name="room" value="{esc(room['id'])}">
          <input type="hidden" name="checkin" value="{check_in}">
          <input type="hidden" name="checkout" value="{check_out}">
          <input type="hidden" name="guests" value="{guests}">
          <div class="form-grid">
            <label><span>Guest full name</span><input name="guest" autocomplete="name" required></label>
            <label><span>ID card or passport</span><input name="passport" required></label>
            <label><span>Phone number</span><input name="phone" autocomplete="tel" required></label>
          </div>
          <button type="button" id="openPaymentModal">Pay Online</button>
          <div class="modal payment-modal" id="paymentModal" role="dialog" aria-modal="true" aria-labelledby="paymentModalTitle">
            <div class="modal-box payment-modal-box">
              <p class="eyebrow">Online Payment</p>
              <h2 id="paymentModalTitle">Scan QR to Pay</h2>
              <p>Scan the QR code with your banking application, then choose the actual payment result.</p>
              <img class="payment-qr" src="/payment-qr-code.png" alt="VietQR payment code">
              <div class="payment-total"><span>Amount to pay</span><strong>{money(total)}</strong></div>
              <div class="modal-actions payment-actions">
                <button type="submit" name="payment_result" value="success">Payment Successful</button>
                <button class="ghost" type="submit" name="payment_result" value="pending">Not Paid Yet</button>
              </div>
            </div>
          </div>
        </form>
        <aside class="summary-panel">
          <p class="eyebrow">Booking Summary</p><h2>{esc(room['type'])} Room {esc(room['number'])}</h2>
          <div class="summary-row"><span>Check-in</span><strong>{check_in}</strong></div>
          <div class="summary-row"><span>Check-out</span><strong>{check_out}</strong></div>
          <div class="summary-row"><span>Guests</span><strong>{guests}</strong></div>
          <div class="summary-row"><span>Room status</span><strong>{esc(room['status'])}</strong></div>
          <div class="summary-row"><span>Number of nights</span><strong>{nights}</strong></div>
          <div class="summary-row"><span>Price per night</span><strong>{money(room['price'])}</strong></div>
          <div class="summary-row"><span>Total amount</span><strong>{money(total)}</strong></div>
        </aside>
      </div>
    </section>
    <script>
      (() => {{
        const form = document.querySelector('form[action="/confirmation"]');
        const modal = document.getElementById('paymentModal');
        const openButton = document.getElementById('openPaymentModal');
        openButton.addEventListener('click', () => {{
          if (form.reportValidity()) modal.classList.add('show');
        }});
        modal.addEventListener('click', (event) => {{
          if (event.target === modal) modal.classList.remove('show');
        }});
        document.addEventListener('keydown', (event) => {{
          if (event.key === 'Escape') modal.classList.remove('show');
        }});
      }})();
    </script>
    """
    return page("Complete Booking - Lucky Hotel", body, logged_in, "rooms")


def confirmation_page(room, logged_in, booking=None):
    if booking is None:
        raise ValueError("Booking data is required.")
    body = f"""
    <section class="view active" id="confirmation">
      <div class="confirmation"><p class="eyebrow">Payment Successful</p><h1>Booking Created Successfully</h1>
        <div class="confirmation-grid">
          <span>Booking ID</span><strong>{esc(booking['booking_code'])}</strong>
          <span>Member</span><strong>{esc(booking.get('member_name', ''))}</strong>
          <span>Guest full name</span><strong>{esc(booking.get('guest_full_name', ''))}</strong>
          <span>ID card / Passport</span><strong>{esc(booking.get('guest_id_number', ''))}</strong>
          <span>Guest phone</span><strong>{esc(booking.get('guest_phone', ''))}</strong>
          <span>Room</span><strong>{esc(booking['room_type'])} Room {esc(booking['room_number'])}</strong>
          <span>Check-in</span><strong>{esc(booking['check_in_date'])}</strong>
          <span>Check-out</span><strong>{esc(booking['check_out_date'])}</strong>
          <span>Number of nights</span><strong>{esc(booking.get('number_of_nights', ''))}</strong>
          <span>Total amount</span><strong>{money(booking.get('total_amount', 0))}</strong>
          <span>Booking status</span><strong><mark>{esc(booking['booking_status'])}</mark></strong>
          <span>Payment status</span><strong><mark>{esc(booking['payment_status'])}</mark></strong>
        </div>
      </div>
    </section>
    """
    return page("Booking Created - Lucky Hotel", body, logged_in, "bookings")


def payment_message_page(title, heading, message, room_code="", check_in="", check_out="", guests="1"):
    retry_url = "/booking?" + urlencode(
        {
            "id": room_code,
            "checkin": check_in,
            "checkout": check_out,
            "guests": guests,
        }
    )
    body = f"""
    <section class="view active">
      <div class="confirmation">
        <p class="eyebrow">{esc(title)}</p>
        <h1>{esc(heading)}</h1>
        <p>{esc(message)}</p>
        <div class="guest-panel-actions">
          <a href="{retry_url}">Try Payment Again</a>
          <a href="/rooms">Back to Rooms</a>
        </div>
      </div>
    </section>
    """
    return page(f"{heading} - Lucky Hotel", body, True, "rooms")


def profile_page(logged_in, profile=None, message="", error=False):
    profile = profile or {
        "full_name": "",
        "date_of_birth": "",
        "gender": "",
        "phone": "",
        "address": "",
        "email": "",
    }
    gender_options = "".join(
        f'<option {"selected" if profile.get("gender") == gender else ""}>{gender}</option>'
        for gender in ["Female", "Male", "Other"]
    )
    body = f"""
    <section class="view active" id="profile">
      <form class="wide-form" method="post" action="/profile/update"><p class="eyebrow">Member Profile</p><h1>Personal Information</h1>
        {notice(message, error)}
        <div class="form-grid">
          <label><span>Full name</span><input name="full_name" value="{esc(profile.get('full_name', ''))}"></label>
          <label><span>Date of birth</span><input type="date" name="date_of_birth" value="{esc(profile.get('date_of_birth') or '')}"></label>
          <label><span>Gender</span><select name="gender">{gender_options}</select></label>
          <label><span>Phone number</span><input name="phone" value="{esc(profile.get('phone') or '')}"></label>
          <label class="wide"><span>Address</span><input name="address" value="{esc(profile.get('address') or '')}"></label>
          <label><span>Email address</span><input type="email" value="{esc(profile.get('email', ''))}" readonly></label>
          <label><span>New password</span><input type="password" name="password" placeholder="Optional"></label>
        </div><button type="submit">Save Changes</button>
      </form>
    </section>
    """
    return page("Profile - Lucky Hotel", body, logged_in, "profile")


def bookings_page(logged_in, bookings=None, message="", error=False):
    bookings = bookings or []
    rows = ""
    for booking in bookings:
        cancel = ""
        check_in_value = booking.get("check_in_date")
        if isinstance(check_in_value, str):
            try:
                check_in_value = date.fromisoformat(check_in_value)
            except ValueError:
                check_in_value = None
        if booking["booking_status"] == "New" and check_in_value and check_in_value > date.today() + timedelta(days=1):
            cancel = f"""<form class="inline-form" method="post" action="/cancel-booking">
              <input type="hidden" name="booking" value="{esc(booking['booking_code'])}">
              <button class="small ghost" type="submit">Cancel</button>
            </form>"""
        guest_info = f"{esc(booking.get('guest_full_name', ''))}<br><small>{esc(booking.get('guest_id_number', ''))} | {esc(booking.get('guest_phone', ''))}</small>"
        rows += f"<tr><td>{esc(booking['booking_code'])}</td><td>{esc(booking['room_type'])} {esc(booking['room_number'])}</td><td>{guest_info}</td><td>{esc(booking['check_in_date'])}</td><td>{esc(booking['check_out_date'])}</td><td>{money(booking['total_amount']) if not str(booking['total_amount']).startswith('$') else esc(booking['total_amount'])}</td><td><mark>{esc(booking['booking_status'])}</mark></td><td><mark>{esc(booking['payment_status'])}</mark></td><td>{button_form('/confirmation', 'View', {'booking': booking['booking_code']})}{cancel}</td></tr>"
    rows = rows or '<tr><td colspan="9">No bookings found.</td></tr>'
    body = f'<section class="view active" id="bookings"><div class="page-heading"><div><p class="eyebrow">Member Area</p><h1>Booking History</h1></div></div>{notice(message, error)}<div class="table-wrap"><table><thead><tr><th>Booking ID</th><th>Room</th><th>Guest Info</th><th>Check-in</th><th>Check-out</th><th>Total</th><th>Status</th><th>Payment</th><th>Actions</th></tr></thead><tbody>{rows}</tbody></table></div></section>'
    return page("Booking History - Lucky Hotel", body, logged_in, "bookings")


def admin_layout(content, active="dashboard", title="Dashboard"):
    tabs = [("dashboard", "Dashboard", "/admin"), ("rooms", "Manage Rooms", "/admin/rooms"), ("members", "Manage Members", "/admin/members"), ("bookings", "Manage Bookings", "/admin/bookings"), ("reports", "Reports", "/admin/reports")]
    menu = "".join(f'<a class="{active == key and "active" or ""}" href="{url}">{label}</a>' for key, label, url in tabs)
    return f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Lucky Hotel Admin</title><link rel="stylesheet" href="/hotel-booking-style.css"><link rel="stylesheet" href="/admin-dashboard-style.css"></head>
<body class="admin-page"><main class="admin-shell">
<aside class="admin-sidebar"><a class="brand admin-brand" href="/admin"><span class="brand-mark">LH</span><span>Admin</span></a><nav class="admin-menu">{menu}</nav><a class="guest-site-link" href="/">Guest Website</a></aside>
<section class="admin-main"><header class="admin-header"><div><p class="eyebrow">Hotel Room Booking System</p><h1>{esc(title)}</h1></div><form method="post" action="/admin/logout"><button class="ghost" type="submit">Logout</button></form></header>{content}</section>
</main></body></html>"""


def admin_login_page(message=""):
    return f"""<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1"><title>Lucky Hotel Admin</title><link rel="stylesheet" href="/hotel-booking-style.css"><link rel="stylesheet" href="/admin-dashboard-style.css"></head>
<body class="admin-page"><main class="admin-auth"><section class="admin-login-panel"><div><p class="eyebrow">Administrator Portal</p><h1>Lucky Hotel Admin</h1><p>Manage rooms, members, bookings, statuses, reports, and daily hotel operations from a separate admin website.</p></div>
<form class="form-card" method="post" action="/admin/login"><p class="eyebrow">Admin Login</p><h2>Sign in</h2>{notice(message, True)}<label><span>Email Address</span><input type="email" name="email" autocomplete="email" required></label><label><span>Password</span><input type="password" name="password" autocomplete="current-password" required></label><button type="submit">Login</button></form>
</section></main></body></html>"""


def admin_dashboard(message=""):
    try:
        stats = get_dashboard_statistics()
    except Exception:
        stats = {"total_rooms": 0, "available_rooms": 0, "current_bookings": 0, "registered_members": 0, "total_revenue": 0, "checking_in_today": 0, "checking_out_today": 0, "cleaning_rooms": 0, "maintenance_rooms": 0}
    metrics = f'<div class="metric-grid"><article><span>Total rooms</span><strong>{stats["total_rooms"]}</strong></article><article><span>Available rooms</span><strong>{stats["available_rooms"]}</strong></article><article><span>Current bookings</span><strong>{stats["current_bookings"]}</strong></article><article><span>Registered members</span><strong>{stats["registered_members"]}</strong></article><article><span>Total revenue</span><strong>{money(stats["total_revenue"])}</strong></article></div>'
    content = notice(message) + metrics + f'<div class="admin-split"><section class="admin-panel"><h2>Today</h2><div class="status-list"><span>{stats["checking_in_today"]} rooms checking in</span><span>{stats["checking_out_today"]} rooms checking out</span><span>{stats["cleaning_rooms"]} rooms marked for cleaning</span><span>{stats["maintenance_rooms"]} rooms under maintenance</span></div></section><section class="admin-panel"><h2>Quick Actions</h2><div class="quick-actions"><a class="admin-action-link" href="/admin/rooms">Add Room</a><a class="admin-action-link" href="/admin/bookings">Update Booking</a><a class="admin-action-link" href="/admin/reports">View Revenue</a></div></section></div>'
    return admin_layout(content, "dashboard", "Dashboard")


def option_tags(options, selected):
    return "".join(f'<option value="{esc(option)}" {"selected" if option == selected else ""}>{esc(option)}</option>' for option in options)


def room_admin_form(room=None):
    room = room or {
        "id": "",
        "display_id": "",
        "number": "",
        "type": "Standard",
        "price": "120",
        "area": "24",
        "bed": "Queen bed",
        "occupancy": "2",
        "status": "Available",
        "description": "",
    }
    action = "/admin/room-update" if room.get("id") else "/admin/room-add"
    button = "Update Room" if room.get("id") else "Add Room"
    id_field = (
        f'<label><span>Room ID</span><input value="{esc(room.get("display_id", room["id"]))}" readonly>'
        f'<input type="hidden" name="room_id" value="{esc(room["id"])}"></label>'
        if room.get("id")
        else ""
    )
    return f"""
    <form class="wide-form admin-room-form" method="post" action="{action}">
      <div class="form-grid">
        {id_field}
        <label><span>Room number</span><input name="room_number" value="{esc(room['number'])}" required></label>
        <label><span>Type</span><select name="room_type">{option_tags(["Standard", "Superior", "Deluxe", "Suite"], room['type'])}</select></label>
        <label><span>Status</span><select name="room_status">{option_tags(["Available", "Occupied", "Cleaning", "Maintenance"], room['status'])}</select></label>
        <label><span>Price per night</span><input type="number" name="price_per_night" min="1" value="{esc(room['price'])}" required></label>
        <label><span>Area</span><input type="number" name="area" min="1" value="{esc(room['area'])}" required></label>
        <label><span>Bed type</span><input name="bed_type" value="{esc(room['bed'])}" required></label>
        <label><span>Max occupancy</span><input type="number" name="max_occupancy" min="1" value="{esc(room['occupancy'])}" required></label>
        <label class="wide"><span>Description</span><input name="description" value="{esc(room['description'])}" required></label>
      </div>
      <button type="submit">{button}</button>
    </form>
    """


def table_page(kind, params=None):
    params = params or {}
    message = str(params.get("message", [""])[0]).strip()
    is_error = clean_query_value(params.get("error", [""])[0]) == "1"
    feedback = notice(message, is_error)
    if kind == "rooms":
        try:
            rooms = list_all_rooms()
        except Exception:
            rooms = []
        edit_code = params.get("edit", [""])[0]
        edit_room = next((room for room in rooms if room["id"] == edit_code), None)
        rows = ""
        for r in rooms:
            edit_link = f'<a class="small" href="/admin/rooms?edit={esc(r["id"])}">Edit</a>'
            delete_form = f"""<form class="inline-form" method="post" action="/admin/room-delete">
              <input type="hidden" name="room_id" value="{esc(r['id'])}">
              <button class="small ghost" type="submit">Delete</button>
            </form>"""
            rows += f"<tr><td>{esc(r.get('display_id', r['id']))}</td><td>{esc(r['number'])}</td><td>{esc(r['type'])}</td><td>{money(r['price'])}</td><td>{esc(r['bed'])}</td><td>{r['occupancy']}</td><td>{esc(r['status'])}</td><td>{edit_link}{delete_form}</td></tr>"
        head = "<tr><th>Room ID</th><th>Number</th><th>Type</th><th>Price</th><th>Bed</th><th>Max</th><th>Status</th><th>Actions</th></tr>"
        form_title = "Edit Room" if edit_room else "Add Room"
        cancel_link = '<a class="guest-site-link" href="/admin/rooms">Cancel Edit</a>' if edit_room else ""
        content = f"{feedback}<section class='admin-panel'><h2>{form_title}</h2>{room_admin_form(edit_room)}{cancel_link}</section><div class='table-wrap'><table><thead>{head}</thead><tbody>{rows}</tbody></table></div>"
        return admin_layout(content, "rooms", "Manage Rooms")
    if kind == "members":
        search = params.get("search", [""])[0]
        try:
            members = list_members(search)
        except Exception:
            members = []
        rows = ""
        for m in members:
            next_status = "Locked" if m["status"] == "Active" else "Active"
            label = "Lock" if m["status"] == "Active" else "Unlock"
            action = f"""<form class="inline-form" method="post" action="/admin/member-status">
              <input type="hidden" name="member_id" value="{esc(m['id'])}">
              <input type="hidden" name="status" value="{next_status}">
              <button class="small" type="submit">{label}</button>
            </form>"""
            rows += f"<tr><td>{esc(m['id'])}</td><td>{esc(m['name'])}</td><td>{esc(m['email'])}</td><td>{esc(m['phone'])}</td><td><mark>{esc(m['status'])}</mark></td><td>{action}</td></tr>"
        head = "<tr><th>Member ID</th><th>Full name</th><th>Email</th><th>Phone</th><th>Status</th><th>Action</th></tr>"
        search_form = f"""
        <form class="admin-filter-form" method="get" action="/admin/members">
          <label><span>Search member</span><input name="search" value="{esc(search)}" placeholder="Name, email, or phone"></label>
          <button type="submit">Search</button>
          <a class="guest-site-link" href="/admin/members">Clear</a>
        </form>
        """
        return admin_layout(f"{feedback}{search_form}<div class='table-wrap'><table><thead>{head}</thead><tbody>{rows}</tbody></table></div>", "members", "Manage Members")
    try:
        bookings = get_all_bookings()
    except Exception:
        bookings = []
    status_options = ["Confirmed", "Checked-in", "Checked-out", "Cancelled"]
    rows = ""
    for b in bookings:
        booking_code = b.get("booking_code", b.get("id", ""))
        options = "".join(f'<option value="{status}" {"selected" if b["status"] == status else ""}>{status}</option>' for status in status_options)
        action = f"""<form class="inline-form" method="post" action="/admin/booking-status">
          <input type="hidden" name="booking" value="{esc(booking_code)}">
          <select class="status-select" name="status">{options}</select>
          <button class="small" type="submit">Update</button>
        </form>"""
        rows += f"<tr><td>{esc(booking_code)}</td><td>{esc(b['member'])}</td><td>{esc(b['room'])}</td><td>{esc(b['dates'])}</td><td>{esc(b['status'])}</td><td><mark>{esc(b['payment'])}</mark></td><td>{action}</td></tr>"
    head = "<tr><th>Booking ID</th><th>Member</th><th>Room</th><th>Dates</th><th>Status</th><th>Payment</th><th>Action</th></tr>"
    return admin_layout(f"{feedback}<div class='table-wrap'><table><thead>{head}</thead><tbody>{rows}</tbody></table></div>", "bookings", "Manage Bookings")


def reports_page():
    try:
        report = get_report_summary()
    except Exception:
        report = {"total_bookings": 0, "revenue": 0, "occupancy": 0, "status_counts": []}
    status_lines = "".join(
        f"<span>{esc(item['booking_status'])}: {item['count']} bookings</span>"
        for item in report["status_counts"]
    ) or "<span>No booking status data yet</span>"
    maximum = max((item["count"] for item in report["status_counts"]), default=1)
    bars = "".join(
        f'<div class="report-bar"><span style="height:{max(8, round(item["count"] / maximum * 100))}%"></span><small>{esc(item["booking_status"])} ({item["count"]})</small></div>'
        for item in report["status_counts"]
    ) or '<p>No booking data yet.</p>'
    chart = f'<section class="admin-panel"><h2>Booking Status Distribution</h2><div class="chart">{bars}</div></section>'
    summary = f'<section class="admin-panel"><h2>Summary</h2><div class="status-list"><span>Total bookings: {report["total_bookings"]}</span><span>Total revenue: {money(report["revenue"])}</span><span>Room occupancy: {report["occupancy"]}%</span>{status_lines}</div></section>'
    return admin_layout(f'<div class="admin-split">{chart}{summary}</div>', "reports", "Reports")


class HotelHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urlparse(self.path)
        params = parse_qs(parsed.query)
        path = parsed.path
        if path in {"/hotel-booking-style.css", "/admin-dashboard-style.css", "/payment-qr-code.png"}:
            self.serve_static(path[1:])
            return
        session = self.session()
        logged_in = session.get("role") == "member"
        if path == "/":
            member_name = session.get("full_name", "Maya Chen")
            if logged_in:
                try:
                    profile = get_member_profile(session.get("account_id"))
                    if profile and profile.get("full_name"):
                        member_name = profile["full_name"]
                        session["full_name"] = member_name
                except Exception:
                    pass
            self.send_html(home_page(logged_in, member_name))
        elif path == "/rooms":
            self.send_html(rooms_page(params, logged_in))
        elif path == "/room":
            room = room_by_id(params.get("id", [""])[0])
            self.send_html(room_detail_page(room, logged_in, keep_booking_params(params)) if room else room_missing_page(logged_in))
        elif path == "/select":
            room_id = params.get("id", ["RM-403"])[0]
            booking_params = keep_booking_params(params)
            booking_params["id"] = room_id
            booking_url = "/booking?" + urlencode(booking_params)
            if logged_in:
                self.redirect(booking_url)
            else:
                self.redirect("/login?" + urlencode({"next": booking_url}))
        elif path == "/login":
            self.send_html(login_page(params.get("next", ["/bookings"])[0]))
        elif path == "/register":
            self.send_html(register_page())
        elif path == "/forgot":
            self.send_html(page("Forgot Password", '<section class="view active"><form class="form-card centered-card" method="post" action="/forgot"><p class="eyebrow">Account Recovery</p><h1>Forgot Password</h1><label><span>Registered email address</span><input type="email" name="email" placeholder="name@example.com"></label><button type="submit">Submit</button><a href="/login">Back to Login</a></form></section>'))
        elif path == "/booking":
            if not logged_in:
                self.redirect("/login?" + urlencode({"next": self.path}))
            else:
                room = room_by_id(params.get("id", [""])[0])
                self.send_html(booking_page(room, logged_in, params) if room else room_missing_page(logged_in))
        elif path == "/confirmation":
            if not logged_in:
                self.redirect("/login?" + urlencode({"next": self.path}))
                return
            booking_code = params.get("booking", [""])[0]
            booking = None
            if booking_code:
                try:
                    booking = get_booking_by_code(booking_code, session.get("member_id"))
                except Exception:
                    booking = None
            if booking is None:
                self.send_html(payment_message_page("Booking", "Booking Not Found", "This booking does not exist or does not belong to your account."))
                return
            room = room_by_id(booking["room_code"])
            self.send_html(confirmation_page(room, logged_in, booking) if room else room_missing_page(logged_in))
        elif path == "/profile":
            def send_profile():
                profile = None
                try:
                    profile = get_member_profile(session.get("account_id"))
                except Exception:
                    pass
                self.send_html(profile_page(logged_in, profile, params.get("message", [""])[0], params.get("error", [""])[0] == "1"))
            self.guard_member(logged_in, send_profile)
        elif path == "/bookings":
            def send_bookings():
                bookings = None
                try:
                    bookings = get_member_bookings(session.get("member_id"))
                except Exception:
                    pass
                self.send_html(bookings_page(logged_in, bookings, params.get("message", [""])[0], params.get("error", [""])[0] == "1"))
            self.guard_member(logged_in, send_bookings)
        elif path == "/admin/login":
            self.send_html(admin_login_page(params.get("message", [""])[0]))
        elif path == "/admin":
            self.guard_admin(lambda: self.send_html(admin_dashboard(params.get("message", [""])[0])))
        elif path == "/admin/rooms":
            self.guard_admin(lambda: self.send_html(table_page("rooms", params)))
        elif path == "/admin/members":
            self.guard_admin(lambda: self.send_html(table_page("members", params)))
        elif path == "/admin/bookings":
            self.guard_admin(lambda: self.send_html(table_page("bookings", params)))
        elif path == "/admin/reports":
            self.guard_admin(lambda: self.send_html(reports_page()))
        else:
            self.send_error(HTTPStatus.NOT_FOUND)

    def do_POST(self):
        parsed = urlparse(self.path)
        data = self.post_data()
        if parsed.path == "/login":
            account = authenticate_user(first_value(data, "email"), first_value(data, "password"))
            if account is None or account.get("role") != "member":
                self.send_html(login_page(first_value(data, "next", "/bookings"), "Invalid email or password, or the account is locked."))
                return
            session = self.session(create=True, reset=True)
            session["role"] = "member"
            session["account_id"] = account["account_id"]
            session["member_id"] = account["member_id"]
            session["full_name"] = account["full_name"]
            self.redirect(message_url(first_value(data, "next", "/bookings"), "Login successful."))
        elif parsed.path == "/register":
            email = first_value(data, "email")
            password = first_value(data, "password")
            confirm = first_value(data, "confirm")
            required = {key: first_value(data, key) for key in ["name", "dob", "gender", "address", "phone", "email", "password"]}
            errors = validate_required(required, list(required))
            if not validate_email(email):
                errors.append("A valid email address is required.")
            if password != confirm:
                errors.append("Password confirmation does not match.")
            if password and len(password) < 8:
                errors.append("Password must contain at least 8 characters.")
            if errors:
                self.send_html(register_page(" ".join(errors)))
                return
            try:
                member_id = register_member(email, password, first_value(data, "name"), first_value(data, "phone"))
                account = authenticate_user(email, password)
                if account:
                    update_member_profile(
                        account["account_id"],
                        {
                            "full_name": first_value(data, "name"),
                            "phone": first_value(data, "phone"),
                            "date_of_birth": first_value(data, "dob"),
                            "gender": first_value(data, "gender"),
                            "address": first_value(data, "address"),
                        },
                    )
            except Exception:
                self.send_html(register_page("Registration failed. The email may already be registered."))
                return
            session = self.session(create=True, reset=True)
            session["role"] = "member"
            session["account_id"] = account["account_id"] if account else None
            session["member_id"] = member_id
            session["full_name"] = first_value(data, "name")
            self.redirect("/profile")
        elif parsed.path == "/logout":
            self.destroy_session()
            self.redirect("/")
        elif parsed.path == "/forgot":
            email = first_value(data, "email")
            try:
                reset_password_for_email(email, email_service.send_password_reset)
            except Exception:
                body = '<section class="view active"><div class="confirmation"><p class="eyebrow">Account Recovery</p><h1>Email Could Not Be Sent</h1><p>Your password was not changed. Check the email configuration and try again.</p><a href="/forgot">Try Again</a></div></section>'
                self.send_html(page("Password Reset Error - Lucky Hotel", body))
                return
            body = '<section class="view active"><div class="confirmation"><p class="eyebrow">Account Recovery</p><h1>Password Reset Sent</h1><p>If the email exists, a new password was generated and sent to the registered email address.</p><a href="/login">Back to Login</a></div></section>'
            self.send_html(page("Password Reset - Lucky Hotel", body))
        elif parsed.path == "/profile/update":
            session = self.session()
            if session.get("role") != "member":
                self.redirect("/login")
                return
            profile_data = {
                "full_name": first_value(data, "full_name"),
                "phone": first_value(data, "phone"),
                "date_of_birth": first_value(data, "date_of_birth"),
                "gender": first_value(data, "gender"),
                "address": first_value(data, "address"),
            }
            errors = validate_required(profile_data, ["full_name", "phone", "date_of_birth", "gender", "address"])
            if errors:
                self.redirect(message_url("/profile", " ".join(errors), True))
                return
            try:
                update_member_profile(session["account_id"], profile_data)
            except Exception:
                self.redirect(message_url("/profile", "Profile could not be updated.", True))
                return
            new_password = first_value(data, "password")
            if new_password:
                try:
                    update_member_password(session["account_id"], new_password)
                except ValueError as error:
                    self.redirect(message_url("/profile", str(error), True))
                    return
            session["full_name"] = first_value(data, "full_name")
            self.redirect(message_url("/profile", "Profile updated successfully."))
        elif parsed.path == "/confirmation":
            session = self.session()
            if session.get("role") != "member":
                self.redirect("/login?" + urlencode({"next": "/bookings"}))
                return
            room_code = first_value(data, "room", "")
            check_in = clean_query_value(first_value(data, "checkin", ""))
            check_out = clean_query_value(first_value(data, "checkout", ""))
            guests = clean_query_value(first_value(data, "guests", "1"))
            demo_result = first_value(data, "payment_result", "pending")
            try:
                guest_data = {
                    "guest": first_value(data, "guest"),
                    "passport": first_value(data, "passport"),
                    "phone": first_value(data, "phone"),
                }
                required_errors = validate_required(guest_data, list(guest_data))
                if required_errors:
                    raise ValueError(" ".join(required_errors))
                guest_count = validate_guests(guests)
                if demo_result != "success":
                    self.send_html(
                        payment_message_page(
                            "Payment Pending",
                            "Booking Not Created",
                            "Payment has not been confirmed. No Booking or Payment record was created.",
                            room_code,
                            check_in,
                            check_out,
                            guests,
                        )
                    )
                    return
                booking_code = create_booking_and_payment(
                    member_id=session["member_id"],
                    room_code=room_code,
                    guest_full_name=first_value(data, "guest"),
                    guest_id_number=first_value(data, "passport"),
                    guest_phone=first_value(data, "phone"),
                    check_in_text=check_in,
                    check_out_text=check_out,
                    number_of_guests=guest_count,
                    payment_processor=lambda amount: payment_gateway.process(amount, room_code, demo_result),
                )
            except Exception as error:
                self.send_html(
                    payment_message_page(
                        "Booking Error",
                        "Booking Not Created",
                        str(error) or "The room could not be booked. Please try another date or room.",
                        room_code,
                        check_in,
                        check_out,
                        guests,
                    )
                )
                return
            booking = get_booking_by_code(booking_code, session["member_id"])
            if booking:
                try:
                    email_service.send_booking_confirmation(booking["member_email"], booking)
                except Exception as error:
                    print(f"Booking {booking_code} was created, but confirmation email failed: {error}")
            self.redirect("/confirmation?" + urlencode({"booking": booking_code}))
        elif parsed.path == "/cancel-booking":
            session = self.session()
            if session.get("role") != "member":
                self.redirect("/login")
                return
            try:
                cancel_booking(session["member_id"], first_value(data, "booking"))
            except Exception as error:
                self.redirect(message_url("/bookings", str(error) or "Booking could not be cancelled.", True))
                return
            self.redirect(message_url("/bookings", "Booking cancelled. Refund is pending."))
        elif parsed.path == "/admin/login":
            account = authenticate_user(first_value(data, "email"), first_value(data, "password"))
            if account is None or account.get("role") != "admin":
                self.send_html(admin_login_page("Invalid administrator email or password."))
                return
            session = self.session(create=True, reset=True)
            session["role"] = "admin"
            session["account_id"] = account["account_id"]
            self.redirect(message_url("/admin", "Administrator login successful."))
        elif parsed.path == "/admin/logout":
            self.destroy_session()
            self.redirect("/admin/login")
        elif parsed.path == "/admin/member-status":
            if self.session().get("role") != "admin":
                self.redirect("/admin/login")
                return
            try:
                update_member_status(int(first_value(data, "member_id")), first_value(data, "status"))
            except Exception as error:
                self.redirect(message_url("/admin/members", str(error) or "Member status could not be updated.", True))
                return
            self.redirect(message_url("/admin/members", "Member status updated."))
        elif parsed.path == "/admin/booking-status":
            if self.session().get("role") != "admin":
                self.redirect("/admin/login")
                return
            try:
                update_booking_status(first_value(data, "booking"), first_value(data, "status"))
            except Exception as error:
                self.redirect(message_url("/admin/bookings", str(error) or "Booking status could not be updated.", True))
                return
            self.redirect(message_url("/admin/bookings", "Booking status updated."))
        elif parsed.path == "/admin/room-add":
            if self.session().get("role") != "admin":
                self.redirect("/admin/login")
                return
            try:
                create_room(room_data_from_post(data))
            except Exception as error:
                self.redirect(message_url("/admin/rooms", str(error) or "Room could not be added.", True))
                return
            self.redirect(message_url("/admin/rooms", "Room added successfully."))
        elif parsed.path == "/admin/room-update":
            if self.session().get("role") != "admin":
                self.redirect("/admin/login")
                return
            try:
                update_room(room_data_from_post(data))
            except Exception as error:
                self.redirect(message_url("/admin/rooms", str(error) or "Room could not be updated.", True))
                return
            self.redirect(message_url("/admin/rooms", "Room updated successfully."))
        elif parsed.path == "/admin/room-delete":
            if self.session().get("role") != "admin":
                self.redirect("/admin/login")
                return
            try:
                delete_room(first_value(data, "room_id"))
            except Exception as error:
                self.redirect(message_url("/admin/rooms", str(error) or "Room could not be deleted.", True))
                return
            self.redirect(message_url("/admin/rooms", "Room deleted or moved to Maintenance when booking history exists."))
        else:
            self.send_error(HTTPStatus.NOT_FOUND)

    def post_data(self):
        length = int(self.headers.get("Content-Length", "0"))
        return parse_qs(self.rfile.read(length).decode("utf-8")) if length else {}

    def session_id(self):
        cookie = SimpleCookie(self.headers.get("Cookie"))
        return cookie.get("hotel_session").value if cookie.get("hotel_session") else ""

    def session(self, create=False, reset=False):
        sid = self.session_id()
        if not reset:
            existing = SESSION_STORE.get(sid)
            if existing is not None:
                return existing
        if not create:
            if sid:
                self.pending_cookie = ""
            return {}
        if sid:
            SESSION_STORE.destroy(sid)
        sid, session = SESSION_STORE.create()
        self.pending_cookie = sid
        return session

    def destroy_session(self):
        sid = self.session_id()
        SESSION_STORE.destroy(sid)
        self.pending_cookie = ""

    def guard_member(self, logged_in, callback):
        if logged_in:
            callback()
        else:
            self.redirect("/login?" + urlencode({"next": self.path}))

    def guard_admin(self, callback):
        if self.session().get("role") == "admin":
            callback()
        else:
            self.redirect("/admin/login")

    def send_html(self, body):
        data = body.encode("utf-8")
        self.send_response(HTTPStatus.OK)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        if hasattr(self, "pending_cookie"):
            self.send_header("Set-Cookie", f"hotel_session={self.pending_cookie}; Path=/; HttpOnly; SameSite=Lax")
        self.end_headers()
        self.wfile.write(data)

    def redirect(self, location):
        self.send_response(HTTPStatus.SEE_OTHER)
        self.send_header("Location", location)
        if hasattr(self, "pending_cookie"):
            self.send_header("Set-Cookie", f"hotel_session={self.pending_cookie}; Path=/; HttpOnly; SameSite=Lax")
        self.end_headers()

    def serve_static(self, filename):
        path = INTERFACE_DIR / filename
        if not path.exists():
            self.send_error(HTTPStatus.NOT_FOUND)
            return
        data = path.read_bytes()
        self.send_response(HTTPStatus.OK)
        content_type = "image/png" if path.suffix.lower() == ".png" else "text/css; charset=utf-8"
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)


if __name__ == "__main__":
    print(f"Python hotel app running at http://{HOST}:{PORT}")
    ThreadingHTTPServer((HOST, PORT), HotelHandler).serve_forever()
