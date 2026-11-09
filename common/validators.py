# -*- coding: utf-8 -*-
"""
Circlefund input validators.

Two layers:
  - is_valid_*  / normalize_*  : never raise, return True/False or a cleaned value
  - validate_*                 : raise DRF ValidationError, for serializer fields
"""
import datetime
import logging
import re
from decimal import Decimal
from uuid import UUID

from django.core.validators import validate_email as django_validate_email
from django.utils import timezone
from rest_framework.exceptions import ValidationError

lgr = logging.getLogger(__name__)

COUNTRY_CODE = "254"
PHONE_LENGTH = 12  # country code + 9 digits
PHONE_RE = re.compile(r"^\+254[17]\d{8}$")
NATIONAL_ID_RE = re.compile(r"^\d{7,8}$")
NAME_RE = re.compile(r"^[^\W\d_]+(?:[ '\-][^\W\d_]+)*$")
DATE_FORMATS = ["%Y-%m-%d", "%d/%m/%Y", "%d-%m-%Y"]  # day-first, never month-first
MAX_AMOUNT = Decimal("1000000000")
MIN_MEMBER_AGE = 18


# Validate Phone numbers to be used

def normalize_phone_number(phone):
    """Return +254712345678 for 0712345678, 712345678, 254712345678 or +254712345678, else ''."""
    try:
        digits = re.sub(r"[\s()\-]", "", str(phone))
        if digits.startswith("+"):
            digits = digits[1:]
        if digits.startswith(COUNTRY_CODE) and len(digits) == PHONE_LENGTH:
            pass
        elif digits.startswith("0") and len(digits) - 1 + len(COUNTRY_CODE) == PHONE_LENGTH:
            digits = COUNTRY_CODE + digits[1:]
        elif len(digits) + len(COUNTRY_CODE) == PHONE_LENGTH:
            digits = COUNTRY_CODE + digits
        else:
            return ""
        return "+" + digits if digits.isdigit() else ""
    except Exception as e:
        lgr.exception("normalize_phone_number: %s", e)
    return ""


def is_valid_phone_number(phone):
    try:
        return PHONE_RE.match(normalize_phone_number(phone)) is not None
    except Exception as e:
        lgr.exception("is_valid_phone_number: %s", e)
    return False


# Identity

def normalize_email(email):
    try:
        return str(email).strip().lower() if email else ""
    except Exception as e:
        lgr.exception("normalize_email: %s", e)
    return ""


def is_valid_email(email):
    try:
        email = normalize_email(email)
        if not email:
            return False
        django_validate_email(email)
        return True
    except Exception:
        return False


def is_valid_national_id(national_id):
    try:
        return NATIONAL_ID_RE.match(str(national_id).strip()) is not None
    except Exception as e:
        lgr.exception("is_valid_national_id: %s", e)
    return False


def is_valid_name(name, min_length=2, max_length=50):
    """Letters, spaces, hyphens and apostrophes only; length within limits."""
    try:
        name = " ".join(str(name).split())
        return min_length <= len(name) <= max_length and NAME_RE.match(name) is not None
    except Exception as e:
        lgr.exception("is_valid_name: %s", e)
    return False


def is_valid_uuid4(value):
    try:
        return UUID(str(value)).version == 4
    except Exception:
        return False


# ---------------- Money ----------------

def normalize_amount(amount):
    """Return a finite Decimal, or None if it can't be read."""
    try:
        if isinstance(amount, bool):
            return None
        value = amount if isinstance(amount, Decimal) else Decimal(
            str(amount).replace(",", "").replace(" ", "")
        )
        return value if value.is_finite() else None
    except Exception:
        return None


def _within_two_places(value):
    return value.as_tuple().exponent >= -2


def is_valid_amount(amount, allow_zero=False):
    try:
        value = normalize_amount(amount)
        if value is None or value < 0 or value > MAX_AMOUNT:
            return False
        if value == 0 and not allow_zero:
            return False
        return _within_two_places(value)
    except Exception as e:
        lgr.exception("is_valid_amount: %s", e)
    return False


def is_valid_percentage(rate):
    try:
        value = normalize_amount(rate)
        return value is not None and 0 <= value <= 100 and _within_two_places(value)
    except Exception as e:
        lgr.exception("is_valid_percentage: %s", e)
    return False


# ---------------- Dates ----------------

def normalize_date(value):
    """Return a datetime.date, or None."""
    try:
        if isinstance(value, datetime.datetime):
            return value.date()
        if isinstance(value, datetime.date):
            return value
        text = str(value).strip()
        for fmt in DATE_FORMATS:
            try:
                return datetime.datetime.strptime(text, fmt).date()
            except ValueError:
                continue
    except Exception as e:
        lgr.exception("normalize_date: %s", e)
    return None


def is_valid_date(value):
    return normalize_date(value) is not None


def is_not_in_future(value):
    try:
        d = normalize_date(value)
        return d is not None and d <= timezone.localdate()
    except Exception as e:
        lgr.exception("is_not_in_future: %s", e)
    return False


def is_not_in_past(value):
    try:
        d = normalize_date(value)
        return d is not None and d >= timezone.localdate()
    except Exception as e:
        lgr.exception("is_not_in_past: %s", e)
    return False


def is_adult(value, min_age=MIN_MEMBER_AGE):
    try:
        d = normalize_date(value)
        if d is None:
            return False
        today = timezone.localdate()
        age = today.year - d.year - ((today.month, today.day) < (d.month, d.day))
        return age >= min_age
    except Exception as e:
        lgr.exception("is_adult: %s", e)
    return False


# ---------------- DRF validators (raise ValidationError) ----------------
# The raise stays outside any try block so the error is never swallowed.

def validate_phone(value):
    if not is_valid_phone_number(value):
        raise ValidationError("Enter a valid Kenyan phone number, e.g. +254712345678.")


def validate_email(value):
    if not is_valid_email(value):
        raise ValidationError("Enter a valid email address.")


def validate_national_id(value):
    if not is_valid_national_id(value):
        raise ValidationError("National ID must be 7 or 8 digits.")


def validate_person_name(value):
    if not is_valid_name(value):
        raise ValidationError("Use letters, spaces, hyphens or apostrophes (2 to 50 characters).")


def validate_uuid4(value):
    if not is_valid_uuid4(value):
        raise ValidationError("Enter a valid UUID.")


def validate_positive_amount(value):
    if not is_valid_amount(value):
        raise ValidationError("Amount must be greater than zero, with at most 2 decimal places.")


def validate_non_negative_amount(value):
    if not is_valid_amount(value, allow_zero=True):
        raise ValidationError("Amount cannot be negative and can have at most 2 decimal places.")


def validate_percentage(value):
    if not is_valid_percentage(value):
        raise ValidationError("Enter a percentage between 0 and 100.")


def validate_not_in_future(value):
    if not is_not_in_future(value):
        raise ValidationError("Date cannot be in the future.")


def validate_not_in_past(value):
    if not is_not_in_past(value):
        raise ValidationError("Date cannot be in the past.")


def validate_adult(value):
    if not is_adult(value):
        raise ValidationError(f"Must be at least {MIN_MEMBER_AGE} years old.")