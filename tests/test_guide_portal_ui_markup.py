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


def test_error_page_buttons_are_tenant_aware():
    error_template = _read("templates/pages/error.html")

    # Return Home links straight to the tenant login. The old `/?{{ query }}`
    # re-rendered the error page when the failing request lacked tenant query
    # params, so the button appeared to "do nothing" (DEVCUR-1708 / 1707).
    # Values are urlencoded so `&`/`#` cannot tamper with the target.
    assert (
        'href="/auth/login?company_code={{ company_code|urlencode }}&mode={{ mode|urlencode }}"'
        in error_template
    )
    # Go Back falls back to the tenant login when there is no history entry to
    # return to (direct navigation / redirect), instead of a no-op history.back().
    # The URL is carried in a data- attribute (not interpolated into a JS string
    # literal) to avoid XSS in the onclick JS context.
    assert "window.history.length > 1" in error_template
    assert "window.location.assign(this.dataset.loginUrl)" in error_template
    assert (
        'data-login-url="/auth/login?company_code={{ company_code|urlencode }}&mode={{ mode|urlencode }}"'
        in error_template
    )


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


def test_guide_home_forms_badge_distinguishes_empty_from_complete():
    """Both trip lists must render the same four-state badge, driven by forms_badge.

    The old markup branched on `forms_due_count == 0` and therefore rendered
    "Complete" both for a trip whose forms were all returned and for a trip that
    never had a form at all.
    """
    template = _read("templates/pages/guide_home.html")

    assert "{% macro forms_badge(trip" in template
    for state in ("due", "pending", "complete", "empty"):
        assert f'trip.forms_badge == "{state}"' in template
    assert "No Forms" in template
    assert 'Form{{ "" if trip.forms_incomplete_count == 1 else "s" }} Pending' in template
    # The macro is used by BOTH the future and the past trip cards.
    assert template.count("{{ forms_badge(trip") == 2
    # The old "zero due means complete" branch must be gone.
    assert "trip.forms_due_count == 0" not in template


def test_guide_home_renders_every_forms_badge_state():
    """Render the real template so the macro is exercised, not just grepped.

    Both trip lists go through the same macro, so this also proves the future and
    past cards can no longer drift apart.
    """
    import re

    from jinja2 import ChoiceLoader, DictLoader, Environment, FileSystemLoader

    env = Environment(
        loader=ChoiceLoader(
            [
                # Stub layout: this test is about the card markup, not the shell.
                DictLoader({"layouts/dashboard.html": "{% block page_content %}{% endblock %}"}),
                FileSystemLoader(str(PROJECT_ROOT / "templates")),
            ]
        )
    )

    def card(name, badge, due=0, incomplete=0):
        return dict(
            trip_departure_id=1, trip_id=1, tour_name=name, dates="August 30-31, 2026",
            thumbnail_image=None, group_size=4, trip_contact_name="AM", trip_leaders="TL",
            departure_docs_count=None, forms_badge=badge,
            forms_due_count=due, forms_incomplete_count=incomplete,
        )

    html = env.get_template("pages/guide_home.html").render(
        guide=dict(
            future_trips=[card("Due", "due", due=2), card("Pending", "pending", incomplete=1)],
            past_trips=[card("Complete", "complete"), card("Empty", "empty"), card("Unknown", None)],
        )
    )

    rendered = []
    for chunk in re.split(r'class="card trip-card', html)[1:]:
        badges = re.findall(r'<span class="badge (bg-outline-\w+)[^"]*"[^>]*>(.*?)</span>', chunk, re.S)
        rendered.append([(cls, re.sub(r"\s+", " ", re.sub("<[^>]+>", "", text)).strip()) for cls, text in badges])

    assert rendered == [
        [("bg-outline-danger", "2 Forms Due")],
        [("bg-outline-warning", "1 Form Pending")],
        [("bg-outline-success", "Complete")],
        [("bg-outline-gray", "No Forms")],  # neutral, not a warning
        [],  # unknown state renders no badge at all
    ]


def test_departure_page_uses_area_manager_label_for_trip_contact():
    template = _read("templates/pages/trip_departure.html")

    assert "Area Manager: {{ departure.trip_contact_name or '-' }}" in template
    assert "{{ departure.trip_contact_label or 'Trip Contact' }}" not in template


def test_departure_page_does_not_render_trip_contact_phone():
    template = _read("templates/pages/trip_departure.html")

    assert "departure.trip_contact_phone" not in template
    assert 'href="tel:{{ departure.trip_contact_phone }}"' not in template


def test_departure_page_has_save_offline_helper_text():
    """DEVCUR-1695: helper text under the Save offline button, gated to when it shows."""
    template = _read("templates/pages/trip_departure.html")

    assert (
        "Save all documents to this device for offline access during your trip."
        in template
    )
    # The helper text only renders when the Save offline button is active.
    helper_index = template.index("Save all documents to this device")
    gate_index = template.rindex("{% if save_offline_active %}", 0, helper_index)
    assert gate_index != -1


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


def test_client_trip_count_uses_tenant_neutral_copy():
    template = _read("templates/pages/client.html")

    assert "Past Trips" in template
    assert "Past WT Trips" not in template
