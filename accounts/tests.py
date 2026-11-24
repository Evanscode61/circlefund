from unittest.mock import patch

from django.conf import settings
from django.core.cache import cache
from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase

from .models import User
from .ratelimit import RegistrationThrottle


@override_settings(CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}})
class RegistrationTests(APITestCase):
    def setUp(self) -> None:
        cache.clear()
        self.addCleanup(cache.clear)
        self.url = reverse("user-register")
        self.payload = {
            "first_name": "  Alice  ",
            "last_name": "  Kamau ",
            "email": " Alice@Example.COM ",
            "phone_number": "+376 312 345",
            "password": " A-strong-Password42! ",
            "password_confirmation": " A-strong-Password42! ",
        }

    def test_registration_and_email_login(self) -> None:
        response = self.client.post(self.url, self.payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_201_CREATED, response.data)
        user = User.objects.get(email="alice@example.com")
        self.assertEqual((user.first_name, user.last_name), ("Alice", "Kamau"))
        self.assertEqual(user.phone, "+376312345")
        self.assertNotEqual(user.password, self.payload["password"])
        self.assertTrue(user.check_password(self.payload["password"]))
        self.assertTrue(user.is_active)
        self.assertFalse(user.is_email_verified or user.is_phone_verified)
        self.assertFalse(user.is_staff or user.is_superuser or user.is_platform_admin)
        self.assertNotIn("password", response.data["data"])
        self.assertNotIn("password_confirmation", response.data["data"])

        response = self.client.post(reverse("token_obtain_pair"), {
            "email": "ALICE@example.com", "password": self.payload["password"],
        }, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertIn("access", response.data)

        response = self.client.post(reverse("token_obtain_pair"), {
            "username": user.username, "password": self.payload["password"],
        }, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

    def test_inactive_account_still_reserves_email(self) -> None:
        User.objects.create_user(
            username="inactive", email="alice@example.com", phone="+254712345678", is_active=False,
        )
        response = self.client.post(self.url, self.payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("email", response.data["errors"])
        self.assertEqual(User.objects.count(), 1)

    def test_duplicate_phone_in_a_different_format_is_rejected(self) -> None:
        User.objects.create_user(
            username="existing", email="other@example.com", phone="+376312345",
        )
        response = self.client.post(self.url, self.payload, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("phone_number", response.data["errors"])

    def test_invalid_fields_and_password_policy(self) -> None:
        response = self.client.post(self.url, {
            **self.payload, "first_name": "  ", "last_name": "a" * 151,
            "email": "invalid", "phone_number": "0712345678",
        }, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(set(response.data["errors"]), {"first_name", "last_name", "email", "phone_number"})

        response = self.client.post(self.url, {
            **self.payload, "password_confirmation": "different",
        }, format="json")
        self.assertIn("password_confirmation", response.data["errors"])

        response = self.client.post(self.url, {
            **self.payload, "password": "12345678", "password_confirmation": "12345678",
        }, format="json")
        self.assertIn("password", response.data["errors"])
        self.assertFalse(User.objects.exists())

    def test_backend_controlled_fields_are_rejected(self) -> None:
        backend_fields = {
            "is_staff": True, "is_superuser": True, "is_active": False,
            "is_platform_admin": True, "is_email_verified": True, "role": "Owner",
        }
        response = self.client.post(self.url, {**self.payload, **backend_fields}, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(set(response.data["errors"]), set(backend_fields))
        self.assertFalse(User.objects.exists())

    @override_settings(REST_FRAMEWORK={**settings.REST_FRAMEWORK, "NUM_PROXIES": None})
    def test_rate_limits_failed_attempts_even_if_forwarded_header_changes(self) -> None:
        with (
            patch.object(RegistrationThrottle, "get_rate", return_value="2/hour"),
            patch.object(RegistrationThrottle, "timer", return_value=4000),
        ):
            for address in ("198.51.100.1", "198.51.100.2"):
                response = self.client.post(self.url, {}, format="json", HTTP_X_FORWARDED_FOR=address)
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            response = self.client.post(
                self.url, {}, format="json", HTTP_X_FORWARDED_FOR="198.51.100.3",
            )
        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertGreater(int(response["Retry-After"]), 0)
