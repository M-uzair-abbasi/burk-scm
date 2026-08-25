# External integration readiness results — 2026-08-16

The internal adapter contracts, selection rules, required-setting checks, secret redaction, and failure behavior are verified on PostgreSQL. A live external call is intentionally not claimed without organization-owned inputs.

| Dependency | Internal status | Staging/live status | Required external evidence |
|---|---|---|---|
| Daraz orders | Verified | External blocker | Open Platform app key/secret/token, seller staging access, approved API base URL |
| Burk orders | Verified | External blocker | Approved REST/webhook/read-model contract, endpoint, token, and representative staging orders |
| Packaging camera | Verified | External blocker | Warehouse RTSP/USB source, host access, lighting/placement acceptance |
| Courier booking/webhooks | Verified | External blocker | Leopard sandbox credentials, booking schema approval, signed webhook samples |
| WhatsApp | Verified | External blocker | Cloud API token, sender ID, approved templates, delivery-receipt webhook secret |
| SMTP/email | Verified | External blocker | Provider account, sender/domain verification, credentials, deliverability acceptance |
| Burk review destination | Verified | External blocker | Approved review API/base URL, token, destination UX acceptance |

Release must set `PRODUCTION_MODE=True`, `REQUIRE_LIVE_INTEGRATIONS=True`, all live adapter selectors, and the corresponding secrets. Readiness remains unhealthy until every adapter reports `mode=live` and `ok=true`; fixture adapters cannot run in production mode.
