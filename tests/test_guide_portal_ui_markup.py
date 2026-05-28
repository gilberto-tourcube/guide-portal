from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _read(path: str) -> str:
    return (PROJECT_ROOT / path).read_text(encoding="utf-8")


def test_auth_background_layout_has_contrast_scope():
    auth_layout = _read("templates/layouts/auth.html")
    custom_css = _read("static/css/custom.css")

    assert "auth-bg-content" in auth_layout
    assert ".auth-bg-content .form-note-s2" in custom_css
    assert "linear-gradient(90deg" in custom_css


def test_guide_home_limits_past_trips_and_adds_toggle():
    template = _read("templates/pages/guide_home.html")

    assert "{% if loop.index > 3 %}past-trip-extra d-none{% endif %}" in template
    assert 'id="togglePastTrips"' in template
    assert "More Past Trips" in template
    assert "document.querySelectorAll('.past-trip-extra')" in template


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


def test_departure_page_uses_area_manager_label_for_guides_only():
    template = _read("templates/pages/trip_departure.html")

    assert "Area Manager" in template
    assert "request.session.get('user_role') == 'Vendor'" in template
    assert "{{ departure.trip_contact_label or 'Trip Contact' }}" in template


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


def test_client_emergency_phone_uses_same_display_formatter_as_primary_phone():
    template = _read("templates/pages/client.html")

    assert "{{ client.mobile | format_us_phone }}" in template
    assert "{{ client.emergency_contact_phone | format_us_phone }}" in template
    assert 'href="tel:{{ client.emergency_contact_phone }}"' in template
