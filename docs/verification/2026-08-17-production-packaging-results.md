# Production packaging verification — 2026-08-17

| Requirement | Result | Evidence |
|---|---|---|
| Non-root API/worker image | Verified | Dockerfile contract test; locked Gunicorn runtime |
| Non-root standalone frontend | Verified | Dockerfile test and successful `.next/standalone/server.js` build |
| Explicit migrations/static | Verified | `service_completed_successfully` Compose dependency |
| PostgreSQL not published | Verified | expanded Compose model has no DB ports |
| Raw media not public | Verified | media volume absent from nginx; `/media/` returns 404 |
| Only edge published | Verified | expanded model shows only loopback nginx port |
| Health/restart policy | Verified | DB/API/worker/frontend/nginx health checks; long-running restart policies |
| Production Django security profile | Verified | deploy check exits zero under production settings |
| Actual image build/start | External blocker | local Docker socket permission denied |

The last row requires a Docker-capable deployment or CI runner. It does not
change the verified application/configuration result and remains explicit in
the final release matrix until that runner supplies evidence.
