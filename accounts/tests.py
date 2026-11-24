from unittest.mock import patch

from django.conf import settings
from django.core.cache import cache
from django.test import override_settings
from django.urls import reverse
from rest_framework import status
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

from .models import User
from .ratelimit import LoginAccountThrottle, LoginThrottle, RegistrationThrottle


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


@override_settings(CACHES={"default": {"BACKEND": "django.core.cache.backends.locmem.LocMemCache"}})
class LoginTests(APITestCase):
    def setUp(self) -> None:
        cache.clear()
        self.addCleanup(cache.clear)
        self.url = reverse("user-login")
        self.token_url = reverse("token_obtain_pair")
        self.password = " A-strong-Password42! "
        self.user = User.objects.create_user(
            username="evans", first_name="Evans", last_name="Kiprotich",
            email="evans@example.com", phone="+254712345678", password=self.password,
            is_email_verified=True,
        )

    def test_email_login_returns_tokens_and_public_user_fields(self) -> None:
        response = self.client.post(self.url, {
            "email": " EVANS@EXAMPLE.COM ", "password": self.password,
            "first_name": "Client-supplied name", "email_verified": False,
        }, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(set(response.data), {"access", "refresh", "user"})
        self.assertEqual(response.data["user"], {
            "id": str(self.user.pk),
            "first_name": "Evans",
            "last_name": "Kiprotich",
            "email": "evans@example.com",
            "email_verified": True,
        })
        self.assertEqual(AccessToken(response.data["access"])["user_id"], str(self.user.pk))
        self.assertEqual(RefreshToken(response.data["refresh"])["user_id"], str(self.user.pk))
        self.assertIn("no-store", response["Cache-Control"])

    def test_unverified_active_account_can_log_in(self) -> None:
        self.user.is_email_verified = False
        self.user.save(update_fields=["is_email_verified"])
        response = self.client.post(self.url, {
            "email": self.user.email, "password": self.password,
        }, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK)
        self.assertFalse(response.data["user"]["email_verified"])

    def test_login_requires_email_and_password(self) -> None:
        response = self.client.post(self.url, {
            "username": self.user.username,
        }, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertEqual(set(response.data["errors"]), {"email", "password"})

        response = self.client.post(self.url, {
            "email": "invalid", "password": self.password,
        }, format="json")
        self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
        self.assertIn("email", response.data["errors"])

    def test_credential_failures_have_the_same_response(self) -> None:
        unknown = self.client.post(self.url, {
            "email": "missing@example.com", "password": self.password,
        }, format="json")
        wrong_password = self.client.post(self.url, {
            "email": self.user.email, "password": self.password.strip(),
        }, format="json")
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        inactive = self.client.post(self.url, {
            "email": self.user.email, "password": self.password,
        }, format="json")
        legacy = self.client.post(self.token_url, {
            "username": self.user.username, "password": self.password,
        }, format="json")
        for response in (unknown, wrong_password, inactive, legacy):
            self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED, response.data)
            self.assertEqual(response.data, unknown.data)
            self.assertEqual(response.data["message"], "Invalid email or password.")
            self.assertIn("WWW-Authenticate", response)

    def test_disabled_account_cannot_refresh(self) -> None:
        login = self.client.post(self.url, {
            "email": self.user.email, "password": self.password,
        }, format="json")
        self.assertEqual(login.status_code, status.HTTP_200_OK, login.data)
        self.user.is_active = False
        self.user.save(update_fields=["is_active"])
        refresh = self.client.post(reverse("token_refresh"), {
            "refresh": login.data["refresh"],
        }, format="json")
        self.assertEqual(refresh.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertNotIn("access", refresh.data)

    def test_legacy_token_login_keeps_its_response_shape(self) -> None:
        response = self.client.post(self.token_url, {
            "username": self.user.username, "password": self.password,
        }, format="json")
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        self.assertEqual(set(response.data), {"access", "refresh"})
        self.assertIn("no-store", response["Cache-Control"])

    def test_ip_limit_is_shared_between_login_routes(self) -> None:
        with (
            patch.object(LoginThrottle, "get_rate", return_value="2/min"),
            patch.object(LoginThrottle, "timer", return_value=4000),
        ):
            for url in (self.url, self.token_url):
                response = self.client.post(url, {}, format="json")
                self.assertEqual(response.status_code, status.HTTP_400_BAD_REQUEST)
            response = self.client.post(self.url, {}, format="json")
        self.assertEqual(response.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertGreater(int(response["Retry-After"]), 0)

    def test_account_limit_is_shared_by_email_username_and_ip(self) -> None:
        with (
            patch.object(LoginAccountThrottle, "get_rate", return_value="2/min"),
            patch.object(LoginAccountThrottle, "timer", return_value=4000),
        ):
            email_attempt = self.client.post(self.url, {
                "email": "EVANS@example.com", "password": "wrong",
            }, format="json", REMOTE_ADDR="198.51.100.1")
            username_attempt = self.client.post(self.token_url, {
                "username": self.user.username, "password": "wrong",
            }, format="json", REMOTE_ADDR="198.51.100.2")
            throttled = self.client.post(self.url, {
                "email": self.user.email, "password": self.password,
            }, format="json", REMOTE_ADDR="198.51.100.3")
        self.assertEqual(email_attempt.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(username_attempt.status_code, status.HTTP_401_UNAUTHORIZED)
        self.assertEqual(throttled.status_code, status.HTTP_429_TOO_MANY_REQUESTS)
        self.assertGreater(int(throttled["Retry-After"]), 0)
