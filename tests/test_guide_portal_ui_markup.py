from datetime import date
from pathlib import Path

from app.utils.templates import current_year_context


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (PROJECT_ROOT / path).read_text(encoding="utf-8")


def test_auth_background_layout_has_contrast_scope():
    auth_layout = _read("templates/layouts/auth.html")
    custom_css = _read("static/css/custom.css")
    login_template = _read("templates/pages/login.html")
    forgot_password_template = _read("templates/pages/forgot_password.html")

    assert "auth-bg-content" in auth_layout
    assert ".auth-bg-content .form-note-s2" in custom_css
    assert ".auth-bg-content .auth-contrast-link" in custom_css
    assert ".auth-bg-content .form-label-group .auth-contrast-link" in custom_css
    assert "color: #fff !important" in custom_css
    assert "linear-gradient(90deg" in custom_css
    assert "link link-primary link-sm auth-contrast-link" in login_template
    assert "Forgot Password?" in login_template
    assert 'class="auth-contrast-link"' in forgot_password_template
    assert "Back to Login" in forgot_password_template


def test_guide_home_limits_past_trips_and_adds_toggle():
    template = _read("templates/pages/guide_home.html")

    assert "{% if loop.index > 3 %}past-trip-extra d-none{% endif %}" in template
    assert 'id="togglePastTrips"' in template
    assert "More Past Trips" in template
    assert "document.querySelectorAll('.past-trip-extra')" in template


def test_vendor_home_limits_past_trips_and_adds_toggle():
    template = _read("templates/pages/vendor_home.html")

    assert "{% if loop.index > 3 %}past-trip-extra d-none{% endif %}" in template
    assert 'id="togglePastTrips"' in template
    assert "More Past Trips" in template
    assert "document.querySelectorAll('.past-trip-extra')" in template
    assert "vendor.past_trips|length > 3" in template


def test_guide_home_toggle_underline_is_scoped_to_text():
    template = _read("templates/pages/guide_home.html")

    assert "trip-toggle-link" in template
    assert "trip-toggle-text" in template
    assert "text-decoration-underline" not in template
    assert ".trip-toggle-link .icon { text-decoration: none; }" in template


def test_guide_home_uses_area_manager_label_for_trip_contact():
    template = _read("templates/pages/guide_home.html")

    assert '<div class="trip-label">Area Manager</div>' in template
    assert "trip.trip_contact_label if trip.trip_contact_label else 'Trip Contact'" not in template


def test_departure_page_uses_area_manager_label_for_trip_contact():
    template = _read("templates/pages/trip_departure.html")

    assert "Area Manager: {{ departure.trip_contact_name or '-' }}" in template
    assert "{{ departure.trip_contact_label or 'Trip Contact' }}" not in template


def test_departure_page_does_not_render_trip_contact_phone():
    template = _read("templates/pages/trip_departure.html")

    assert "departure.trip_contact_phone" not in template
    assert 'href="tel:{{ departure.trip_contact_phone }}"' not in template


def test_departure_form_tiles_are_whole_card_links_without_edit_icon():
    template = _read("templates/pages/trip_departure.html")
    custom_css = _read("static/css/custom.css")

    assert "portal-form-tile-link" in template
    assert "portal-form-tile-action" in template
    assert 'aria-label="{{ \'Edit\' if is_submitted else \'Complete form\' }} {{ form.form_name }}"' in template
    assert '<em class="icon ni ni-edit"></em>' not in template
    assert ".portal-form-tile-link:focus-visible" in custom_css


def test_vendor_home_uses_area_manager_label_for_trip_contact():
    template = _read("templates/pages/vendor_home.html")

    assert '<div class="trip-label">Area Manager</div>' in template
    assert "trip.trip_contact_label if trip.trip_contact_label else 'Trip Contact'" not in template


def test_vendor_home_toggle_underline_is_scoped_to_text():
    template = _read("templates/pages/vendor_home.html")

    assert "trip-toggle-link" in template
    assert "trip-toggle-text" in template
    assert "text-decoration-underline" not in template
    assert ".trip-toggle-link .icon { text-decoration: none; }" in template
    assert "toggle.setAttribute('aria-expanded'" in template


def test_dashboard_footer_does_not_link_to_missing_help_or_contact_pages():
    template = _read("templates/layouts/dashboard.html")

    assert 'href="/help"' not in template
    assert 'href="/contact"' not in template
    assert ">Help<" not in template
    assert ">Contact<" not in template


def test_dashboard_footer_uses_current_year_context():
    template = _read("templates/layouts/dashboard.html")

    assert "{{ current_year }}" in template
    assert "2024 Tourcube Guide Portal" not in template
    assert current_year_context(None)["current_year"] == date.today().year


def test_client_emergency_phone_uses_same_display_formatter_as_primary_phone():
    template = _read("templates/pages/client.html")

    assert "{{ client.mobile | format_us_phone }}" in template
    assert "{{ client.emergency_contact_phone | format_us_phone }}" in template
    assert 'href="tel:{{ client.emergency_contact_phone }}"' in template
