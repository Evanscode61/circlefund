import math

from django.utils.crypto import salted_hmac
from rest_framework.exceptions import Throttled
from rest_framework.settings import api_settings
from rest_framework.throttling import SimpleRateThrottle


class FixedWindowThrottle(SimpleRateThrottle):
    """Count attempts in a fixed time window using Django's cache."""

    def get_cache_key(self, request, view) -> str:
        """Build the cache key for the caller's IP address."""
        if api_settings.NUM_PROXIES is not None:
            address = self.get_ident(request)
        else:
            address = request.META.get("REMOTE_ADDR", "")
        return self.cache_format % {"scope": self.scope, "ident": address}

    def allow_request(self, request, view) -> bool:
        """Count the attempt and return whether the request may proceed."""
        return self._allow_cache_key(self.get_cache_key(request, view))

    def _allow_cache_key(self, cache_key: str) -> bool:
        if self.rate is None:
            return True
        now = self.timer()
        window = int(now // self.duration)
        key = f"{cache_key}:{window}"
        self.retry_after = math.ceil((window + 1) * self.duration - now)
        self.cache.add(key, 0, timeout=self.duration + 1)
        return self.cache.incr(key) <= self.num_requests

    def wait(self) -> int:
        """Return the seconds until the next window after a rejection."""
        return self.retry_after


class RegistrationThrottle(FixedWindowThrottle):
    scope = "registration"


class LoginThrottle(FixedWindowThrottle):
    scope = "login"


class PasswordRecoveryThrottle(FixedWindowThrottle):
    scope = "password_recovery"


class LoginAccountThrottle(FixedWindowThrottle):
    scope = "login_account"

    def check(self, identifier: str) -> None:
        digest = salted_hmac("accounts.login.throttle", identifier, algorithm="sha256").hexdigest()
        key = self.cache_format % {"scope": self.scope, "ident": digest}
        if not self._allow_cache_key(key):
            raise Throttled(wait=self.wait())
