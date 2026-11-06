"""Conservative redaction for persisted third-party audit payloads."""

SENSITIVE_KEY_FRAGMENTS = frozenset(
    {
        "access_token",
        "address",
        "authorization",
        "customer",
        "email",
        "password",
        "phone",
        "recipient",
        "secret",
        "token",
    }
)


def redact_provider_payload(value):
    if isinstance(value, dict):
        return {
            str(key): (
                "[redacted]"
                if any(
                    fragment in str(key).lower()
                    for fragment in SENSITIVE_KEY_FRAGMENTS
                )
                else redact_provider_payload(item)
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_provider_payload(item) for item in value]
    return value
