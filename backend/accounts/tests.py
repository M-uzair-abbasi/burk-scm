from django.core.cache import cache
from django.test import TestCase, override_settings
from rest_framework.test import APIClient

from .models import User
from .throttles import LoginAccountThrottle, LoginIpThrottle


@override_settings(
    LOGIN_IP_THROTTLE_RATE="100/min",
    LOGIN_ACCOUNT_THROTTLE_RATE="2/min",
)
class LoginAccountThrottleTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()
        self.user = User.objects.create_user(
            username="login-user",
            password="correct-password",
        )

    def tearDown(self):
        cache.clear()

    def test_repeated_bad_attempts_for_same_account_are_throttled(self):
        self.assertEqual(LoginAccountThrottle().num_requests, 2)
        for _ in range(2):
            response = self.client.post(
                "/api/auth/login/",
                {"username": self.user.username, "password": "wrong"},
                format="json",
                REMOTE_ADDR="198.51.100.10",
            )
            self.assertEqual(response.status_code, 400)

        blocked = self.client.post(
            "/api/auth/login/",
            {"username": self.user.username, "password": "wrong"},
            format="json",
            REMOTE_ADDR="198.51.100.10",
        )

        self.assertEqual(blocked.status_code, 429)

    def test_normal_login_succeeds_below_limit(self):
        response = self.client.post(
            "/api/auth/login/",
            {"username": self.user.username, "password": "correct-password"},
            format="json",
            REMOTE_ADDR="198.51.100.11",
        )

        self.assertEqual(response.status_code, 200)


@override_settings(
    LOGIN_IP_THROTTLE_RATE="2/min",
    LOGIN_ACCOUNT_THROTTLE_RATE="100/min",
)
class LoginIpThrottleTests(TestCase):
    def setUp(self):
        cache.clear()
        self.client = APIClient()

    def tearDown(self):
        cache.clear()

    def test_username_spraying_from_one_address_is_throttled(self):
        self.assertEqual(LoginIpThrottle().num_requests, 2)
        for username in ("missing-one", "missing-two"):
            response = self.client.post(
                "/api/auth/login/",
                {"username": username, "password": "wrong"},
                format="json",
                REMOTE_ADDR="203.0.113.44",
            )
            self.assertEqual(response.status_code, 400)

        blocked = self.client.post(
            "/api/auth/login/",
            {"username": "missing-three", "password": "wrong"},
            format="json",
            REMOTE_ADDR="203.0.113.44",
        )

        self.assertEqual(blocked.status_code, 429)
