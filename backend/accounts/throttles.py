"""Focused login throttles.

The endpoint uses both an address-wide bucket (blocks username spraying) and
an address/account bucket (blocks repeated guessing of one account). Account
names are hashed before becoming cache keys.
"""

import hashlib

from django.conf import settings
from rest_framework.throttling import SimpleRateThrottle


class LoginIpThrottle(SimpleRateThrottle):
    scope = "login_ip"

    def get_rate(self):
        return settings.LOGIN_IP_THROTTLE_RATE

    def get_cache_key(self, request, view):
        ident = self.get_ident(request)
        return self.cache_format % {"scope": self.scope, "ident": ident}


class LoginAccountThrottle(SimpleRateThrottle):
    scope = "login_account"

    def get_rate(self):
        return settings.LOGIN_ACCOUNT_THROTTLE_RATE

    def get_cache_key(self, request, view):
        ident = self.get_ident(request)
        username = str(request.data.get("username", "")).strip().casefold()
        username_digest = hashlib.sha256(username.encode("utf-8")).hexdigest()[:24]
        return self.cache_format % {
            "scope": self.scope,
            "ident": f"{ident}:{username_digest}",
        }
