"""Unit tests for app.utils.formatting helpers."""

import pytest

from app.utils.formatting import format_destination, format_us_phone


class TestFormatUsPhone:
    def test_ten_digit_plain(self):
        assert format_us_phone("6083129501") == "(608) 312-9501"

    def test_ten_digit_with_punctuation(self):
        assert format_us_phone("608-312-9501") == "(608) 312-9501"
        assert format_us_phone("(608) 312-9501") == "(608) 312-9501"
        assert format_us_phone("608.312.9501") == "(608) 312-9501"

    def test_eleven_digit_with_us_country_code(self):
        assert format_us_phone("16083129501") == "+1 (608) 312-9501"
        assert format_us_phone("1-608-312-9501") == "+1 (608) 312-9501"

    def test_blank_returns_empty_string(self):
        assert format_us_phone("") == ""
        assert format_us_phone(None) == ""

    def test_unrecognized_format_returns_original(self):
        # 9 digits — not a US format we recognize, return original
        assert format_us_phone("123456789") == "123456789"
        # International (E.164-ish) — return original
        assert format_us_phone("+44 20 7946 0958") == "+44 20 7946 0958"

    def test_letters_in_input_are_stripped_for_match(self):
        # Vanity numbers: digits only matter for length
        assert format_us_phone("(608)EAT-FOOD123") == "(608)EAT-FOOD123"


class TestFormatDestination:
    def test_comma_joined_without_spaces(self):
        assert (
            format_destination("Europe,Switzerland,Alps")
            == "Europe, Switzerland, Alps"
        )

    def test_botswanaand_zimbabwe_pattern(self):
        # The exact bug pattern Steve flagged: comma immediately followed by lowercase
        assert (
            format_destination("Botswana,and Zimbabwe")
            == "Botswana, and Zimbabwe"
        )

    def test_already_spaced_input_idempotent(self):
        assert format_destination("Paris, France") == "Paris, France"
        assert (
            format_destination("Europe, Switzerland, Alps")
            == "Europe, Switzerland, Alps"
        )

    def test_single_destination(self):
        assert format_destination("Greece") == "Greece"

    def test_blank_returns_empty(self):
        assert format_destination("") == ""
        assert format_destination(None) == ""

    def test_extra_whitespace_stripped(self):
        assert format_destination("  Europe ,  Norway  ") == "Europe, Norway"

    def test_trailing_or_empty_segments_dropped(self):
        assert format_destination("Europe,,Norway") == "Europe, Norway"
        assert format_destination("Europe,") == "Europe"
