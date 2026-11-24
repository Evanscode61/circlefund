import math

from rest_framework.settings import api_settings
from rest_framework.throttling import SimpleRateThrottle


class RegistrationThrottle(SimpleRateThrottle):
    """Limit registration attempts per IP within fixed time windows."""

    scope = "registration"

    def get_cache_key(self, request, view) -> str:
        """Build the cache key for the caller's IP address."""
        if api_settings.NUM_PROXIES is not None:
            address = self.get_ident(request)
        else:
            address = request.META.get("REMOTE_ADDR", "")
        return self.cache_format % {"scope": self.scope, "ident": address}

    def allow_request(self, request, view) -> bool:
        """Count the attempt and return whether the request may proceed."""
        if self.rate is None:
            return True
        now = self.timer()
        window = int(now // self.duration)
        key = f"{self.get_cache_key(request, view)}:{window}"
        self.retry_after = math.ceil((window + 1) * self.duration - now)
        self.cache.add(key, 0, timeout=self.duration + 1)
        return self.cache.incr(key) <= self.num_requests

    def wait(self) -> int:
        """Return the seconds until the next window after a rejection."""
        return self.retry_after
