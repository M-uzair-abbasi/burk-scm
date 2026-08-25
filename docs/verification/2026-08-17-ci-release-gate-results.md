# CI and release-gate verification — 2026-08-17

| Gate | Local contract result | Hosted-run status |
|---|---|---|
| PostgreSQL 16 service/full suite | Workflow verified | Pending first GitHub Actions run |
| Three concurrency repetitions | Workflow verified | Pending first GitHub Actions run |
| uv/npm frozen dependency install | Verified locally/workflow | Pending hosted run |
| Migration/deploy/release policy | Verified locally | Pending hosted run |
| Integrity/health/metrics acceptance | Workflow verified | Pending hosted run |
| Frontend type/lint/standalone build | Verified locally | Pending hosted run |
| Compose config/image builds | Config verified; local daemon blocked | Pending hosted runner image build |
| External providers/hardware | Not fabricated | External blocker checklist |

All third-party actions are pinned to immutable 40-character commit SHAs. Cache
configuration names only lockfiles/dependency caches and includes neither
secrets nor media paths. A hosted run cannot occur until the user pushes these
uncommitted changes; no push or commit was made automatically.
