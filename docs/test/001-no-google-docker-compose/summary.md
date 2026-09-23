# Live smoke — unit 001 `no-google-docker-compose` (P3-32, T-019..T-026)

**Verdict: PENDING — user-local run.** Not PASS, not FAIL: the live Compose smoke could not execute
in the agent container. Run [`runbook.md`](./runbook.md) locally, then update this file.

- System under test: root `docker-compose.yml` (11 app services + `redis`), frontend on `http://localhost:8080`.
- Branch: `claude/elegant-edison-99ry8y` · Date of attempt: 2026-09-23.

## Why it is pending

1. **A daemon could be started** (`dockerd` in background; `docker info` OK — Server 29.3.1, overlayfs,
   Compose v5.1.1; pulling and running the pinned `redis:8.10.2-alpine@sha256:72ce…` worked).
   Evidence: [`01-daemon-up.txt`](./01-daemon-up.txt)
2. **Image builds cannot fetch dependencies**: egress goes through a TLS-re-terminating agent proxy whose
   CA build-step containers do not trust. `docker compose build productcatalogservice`:

   ```text
   #12 [builder 4/6] RUN go mod download
   go: github.com/cenkalti/backoff/v5@v5.0.3: Get "https://proxy.golang.org/github.com/cenkalti/backoff/v5/@v/v5.0.3.mod": tls: failed to verify certificate: x509: certificate signed by unknown authority
   failed to solve: process "/bin/sh -c go mod download" did not complete successfully: exit code: 1
   ```
   Evidence: [`02-build-blocked-tls.txt`](./02-build-blocked-tls.txt). Injecting the proxy CA into build
   stages was denied by the environment's permission policy, so it was not pursued. This is an
   environment limitation, not a defect in the Dockerfiles.

## Per-scenario status

| ID | Scenario | Status |
| :-- | :-- | :-- |
| T-019 | Stack builds and starts from a clean clone | PENDING — blocked at build here |
| T-020 | Home and product pages render the catalog | PENDING — user-local |
| T-021 | Add to cart and currency switch | PENDING — user-local |
| T-022 | Checkout completes (+ emailservice log line) | PENDING — user-local |
| T-023 | Load generator runs cleanly | PENDING — user-local |
| T-024 | Browser contacts no Google host | PENDING — user-local |
| T-025 | Cart survives `docker compose restart cartservice` | PENDING — user-local |
| T-026 | Redis outage fails visibly (HTTP 500) | PENDING — user-local |

## Static evidence already green (in-container, P3-31 sweep on the final tree)

- T-001: `git grep` for GOOGLE_PATTERN over SCOPE → no matches.
- T-002, T-009: Go build + tests green for frontend, checkout, productcatalog, shipping; no `cloud.google.com` in `go list -deps`.
- T-003..T-008: base images, Node/Python deps, fonts, adservice log keys + `gradlew assemble`, cartservice csproj/stores.
- T-010, T-013, T-014: `dotnet build` 0 errors; `dotnet test` 4/4 passed (.NET SDK 10.0.112).
- T-011, T-012: catalog loader tests green.
- T-015..T-018: `docker compose config` valid with no `.env`; service set, build contexts, wiring.

## How to close this out

Run [`runbook.md`](./runbook.md) on a machine with Docker and direct egress, add evidence files
from `03-` onward, and replace the verdict and table with PASS/FAIL per ID. P3-32 in `3-plan.md`
is ticked only after that PASS.
