# 001 — Run Online Boutique without Google services, on Docker Compose — Research

> Step 1 of the pipeline (research only — no tests, no plan, no code).
> Unit: "Run the whole project without any Google service, with the DB etc. running on Docker."
> Branch: `work/001-no-google-docker-compose`.

## Decisions (user-confirmed at research checkpoint)
1. **Google Fonts: in scope.** Remove every `fonts.googleapis.com` / `fonts.gstatic.com` reference
   from `src/frontend/templates/header.html:34-37` and `src/emailservice/templates/confirmation.html:21`
   (`footer.html` has none); use a system font stack. No self-hosted font files unless trivially
   required (the "Google Symbols" icon font needs a non-Google replacement or removal of its glyphs).
2. **Python `google-api-core` / `google-auth`: remove.** Replace the exception imports in
   `email_server.py` and `recommendation_server.py`, drop the deps from `requirements.in`, recompile
   `requirements.txt`; also drop `google-cloud-trace` and the dead profiler / `GCP_PROJECT_ID` code.
3. **e2e:** the live smoke is run by the **user locally** with `docker compose up`. In this container
   we verify statically (per-service builds/tests + `docker compose config`) and deliver a smoke
   checklist. The Compose file must be self-contained: clone the repo, run
   `docker compose up --build`, nothing else.
4. **Defaults accepted:** `shoppingassistantservice` not wired (Q3); cart DB is Redis; `alpine`
   replaces distroless (Q9); drop the Node `apk add python3 make g++` line if no longer needed (Q10);
   remove only the trace-agent line from `currencyservice/client.js` (Q11).
5. **adservice log keys (reviewer nit, part of "zero Google"):** rename the
   `logging.googleapis.com/*` JSON keys in `log4j2.xml` to neutral keys (see adservice slice).

## Scope

### In scope (user-confirmed)
1. **`docker-compose.yml` at repo root** that builds every wired service from `src/<svc>/` and runs
   them plus a `redis` container (cart DB). Front end reachable on the host.
2. **Remove (not just disable) Google-only code paths and dependencies:**
   - cartservice: `SpannerCartStore`, `AlloyDBCartStore`, their Startup branches, and the
     `Google.Cloud.Spanner.Data`, `Google.Cloud.SecretManager.V1` (and AlloyDB-only `Npgsql`) packages.
   - Cloud Profiler in **all four Go services** (frontend, checkoutservice, productcatalogservice,
     shippingservice — the brief listed two; checkout and shipping also import it) and both Node
     services (currencyservice, paymentservice).
   - frontend GCP metadata / deployment detection (`deployment_details.go`, the
     `metadata.google.internal` lookup in `handlers.go`).
   - productcatalogservice AlloyDB + Secret Manager catalog loader.
   - currencyservice `client.js` `@google-cloud/trace-agent`.
   - `gcr.io/distroless/static` runtime base images (4 Go Dockerfiles).
   - The commented-out Python Cloud Profiler blocks / `GCP_PROJECT_ID` plumbing (dead code).
   - Python `google-api-core`, `google-auth`, `google-cloud-trace` (emailservice,
     recommendationservice) — Decision 2.
   - Google Fonts in frontend `header.html` and emailservice `confirmation.html` — Decision 1.
   - adservice `log4j2.xml` `logging.googleapis.com/*` key names — Decision 5.
3. **Cart DB = Redis** via the existing `RedisCartStore` (`REDIS_ADDR`).

### Out of scope
- `kubernetes-manifests/`, `kustomize/`, `helm-chart/`, `istio-manifests/`, `terraform/` — left intact.
- `skaffold.yaml` / `cloudbuild.yaml` (reference `gcb` profile and `gcr.io`) — left intact; they are
  an alternative deploy path, not used by Compose.
- `shoppingassistantservice` (Gemini + AlloyDB + Secret Manager) — **not wired into Compose**
  (see Q3). Frontend assistant stays hidden (`ENABLE_ASSISTANT` unset).
- The optional "packaging" HTTP service (`PACKAGING_SERVICE_URL`) — unset in Compose, feature off.
- Tracing (OpenTelemetry collector) — off by default (see Q5).
- `.github/workflows` — unchanged.

## System slice (files touched, with file:line)

### frontend (Go) — `src/frontend/`
- `go.mod:8` `cloud.google.com/go/compute/metadata` (direct), `go.mod:9` `cloud.google.com/go/profiler`
  (direct); many indirect `cloud.google.com/go/*`, `google.golang.org/api` deps drop on `go mod tidy`.
- `main.go:24` imports profiler; `main.go:120-125` starts it only when `ENABLE_PROFILER=1` (opt-in);
  `main.go:194-215` `initProfiling`.
- `deployment_details.go:8` imports `compute/metadata`; `:15-20` `init()` spawns
  `loadDeploymentDetails()` which queries the GCE metadata server (`:39-51`) for cluster/zone.
  Consumed at `handlers.go:560` (`"deploymentDetails": deploymentDetailsMap`) and rendered in
  `templates/footer.html:31-38` (all `if`-guarded, so a nil/empty map renders nothing).
  NB: `deployment_details.go:12-34` also **declares the package-level `log` and
  `initializeLogger()`** — removing the file requires relocating those (seam).
- `handlers.go:92-104` `ENV_PLATFORM` handling + `net.LookupHost("metadata.google.internal.")`
  auto-detect that forces `env="gcp"`; `handlers.go:120-138` `setPlatformDetails` has a `"gcp"`
  branch (cosmetic "Google Cloud" banner/CSS). Removing the auto-detect is required; whether to drop
  the `"gcp"` enum/CSS is a judgment call (Q7).
- `main.go:139` `mustMapEnv(..., "SHOPPING_ASSISTANT_SERVICE_ADDR")` **panics if unset**
  (`main.go:217-222`) — Compose must set a placeholder value even though the service is not wired,
  or the frontend must make it optional (Q3). HTTP call site `handlers.go:464` only fires on `/bot`.
- `templates/header.html:34-37` loads **Google Fonts** (`fonts.googleapis.com`, `fonts.gstatic.com`,
  incl. the "Google Symbols" icon font) from the browser — a Google service not in the brief (Q6,
  now in scope). Same DM Sans link in `src/emailservice/templates/confirmation.html:21`.
- `packaging_info.go:26,43-47` optional Google-demo packaging service, gated on env — leave.
- `Dockerfile:32` `FROM gcr.io/distroless/static`; binary built `CGO_ENABLED=0` (`Dockerfile:30`).
- Tests: only `money/money_test.go`, `validator/validator_test.go` — none touch removed code.

### checkoutservice (Go) — `src/checkoutservice/`
- `go.mod:8` profiler; `main.go:24` import, `main.go:98-103` opt-in `ENABLE_PROFILER=1`,
  `main.go:180-200` `initProfiling`.
- Env (`kubernetes-manifests/checkoutservice.yaml:55-68`): `PORT=5050`, `PRODUCT_CATALOG_SERVICE_ADDR`,
  `SHIPPING_SERVICE_ADDR`, `PAYMENT_SERVICE_ADDR`, `EMAIL_SERVICE_ADDR`, `CURRENCY_SERVICE_ADDR`,
  `CART_SERVICE_ADDR` (all `mustMapEnv`, `main.go:111-116`).
- `Dockerfile:33` distroless. Tests: `money/money_test.go` only.

### productcatalogservice (Go) — `src/productcatalogservice/`
- `go.mod:8-10` `alloydbconn`, `profiler`, `secretmanager`; `go.mod:12` `jackc/pgx/v5` (used only by
  the AlloyDB loader).
- `catalog_loader.go:25-27` imports; `:37-39` switches to `loadCatalogFromAlloyDB` when
  `ALLOYDB_CLUSTER_NAME` is set; `:62-83` `getSecretPayload` (Secret Manager); `:85-…`
  `loadCatalogFromAlloyDB` (env `PROJECT_ID`, `REGION`, `ALLOYDB_*`). Local path
  `loadCatalogFromLocalFile` (`:44-60`, reads `products.json`) is the one to keep.
- `server.go:33` profiler import; `server.go:78-83` **on by default** unless `DISABLE_PROFILER` set;
  `server.go:179-197` `initProfiling`.
- Tests: `product_catalog_test.go` (`TestMain` `:31`, Get/List/Search) exercise `parseCatalog` →
  `loadCatalog` (`product_catalog.go:74-76`) → local file path. They are the regression net for the
  loader change; they do not reference AlloyDB.
- `Dockerfile:32` distroless. Trial `go build ./...` here: **passes** (baseline green).

### shippingservice (Go) — `src/shippingservice/`
- `go.mod:8` profiler; `main.go:23` import; `main.go:65-70` **on by default** unless
  `DISABLE_PROFILER`; `main.go:163-183` `initProfiling`. `main.go:57-63` tracing is a no-op stub
  ("temporarily unavailable") unless `DISABLE_TRACING` set — harmless.
- `Dockerfile:32` distroless. Tests: `shippingservice_test.go` — no profiler reference.

### cartservice (C#/.NET 10) — `src/cartservice/`
- `src/cartservice.csproj:11,13` `Google.Cloud.Spanner.Data`, `Google.Cloud.SecretManager.V1`;
  `:12` `Npgsql` (only referenced by `AlloyDBCartStore.cs`).
- `src/cartstore/SpannerCartStore.cs:16`, `src/cartstore/AlloyDBCartStore.cs:21` — delete.
- `src/Startup.cs:29-56`: `REDIS_ADDR` → Redis; else `SPANNER_*` → Spanner; else
  `ALLOYDB_PRIMARY_IP` → AlloyDB; else in-memory `RedisCartStore` over `AddDistributedMemoryCache`.
  Only the Redis + in-memory branches remain.
- `tests/CartServiceTests.cs` uses `TestServer` (`:37`) with no env → in-memory branch. No
  Spanner/AlloyDB references — unaffected, stays the regression net.
- `src/Dockerfile:36` runtime is `mcr.microsoft.com/dotnet/runtime-deps:…-noble-chiseled` (no shell),
  listens `7070` (`ASPNETCORE_HTTP_PORTS=7070`). Not Google.
- Env (`kubernetes-manifests/cartservice.yaml:50-51`): `REDIS_ADDR=redis-cart:6379`; Redis image
  `redis:alpine` (`:118`).

### currencyservice (Node) — `src/currencyservice/`
- `package.json:11` `@google-cloud/profiler`, `:12` `@google-cloud/trace-agent`.
  (`google-protobuf` `:16` is a plain protobuf runtime lib, keep.)
- `server.js:28-39` profiler loaded unless `DISABLE_PROFILER` set.
- `client.js:18` `require('@google-cloud/trace-agent').start()` unconditionally; `client.js:21`
  also `require('grpc')`, which is **not in package.json** — the test client is already broken
  independent of this unit (note only; `node --check` still passes).
- `Dockerfile:20-25` installs `python3 make g++` "for @google-cloud/profiler post-install" — can be
  dropped once profiler is gone (optional simplification, Q8). Runtime `alpine:3.24.1` (`:33`), port 7000.

### paymentservice (Node) — `src/paymentservice/`
- `package.json:13` `@google-cloud/profiler`; `index.js:21-31` loaded unless `DISABLE_PROFILER`.
- Same `apk add python3 make g++` builder pattern; runtime `alpine`; port 50051.
- `package-lock.json` in both Node services must be regenerated after removing deps.

### emailservice / recommendationservice (Python)
- `emailservice/requirements.in:1` `google-api-core`, `:6` `google-cloud-trace` (unused in code —
  no `google.cloud` import in `emailservice/*.py`). `requirements.txt:9,13,17,19` pins
  `google-api-core[grpc]`, `google-auth`, `google-cloud-trace`, `googleapis-common-protos`.
- `email_server.py:25-26` import `GoogleAPICallError`, `DefaultCredentialsError`; used at `:100`
  (inside `EmailService.send_email`, a class whose `__init__` raises "not implemented", `:62-63`)
  and `:195` (tracing `except`). The service only runs `start(dummy_mode=True)`.
- `email_server.py:40,140-160` commented profiler + `GCP_PROJECT_ID`; `:169-176` "Profiler enabled"
  branch calls an effectively empty `initStackdriverProfiling()`. `Dockerfile:38-39` sets
  `ENV ENABLE_PROFILER=1` (dead).
- `recommendationservice/requirements.in:1` `google-api-core`; `recommendation_server.py:24,26`
  (commented profiler, `DefaultCredentialsError` import used at `:125`); `:45-60,99-106` dead
  profiler plumbing.
- `googleapis-common-protos` / `grpcio-status` are transitive gRPC deps (not a Google *service*).

### adservice (Java) — `src/adservice/`
- No Google Cloud client usage. `build.gradle:2,3,36,44` are protobuf / google-java-format /
  common-protos build libraries. `build.gradle:102,112` and `Dockerfile:33-38` are **commented-out**
  Cloud Profiler agent references. `src/main/resources/log4j2.xml:26-31` emits JSON log keys
  `logging.googleapis.com/trace`, `/spanId`, `/traceSampled` (Stackdriver special-field names) —
  labels only, no Google call. *Rec (Decision 5):* rename to neutral `trace_id`, `span_id`,
  `trace_sampled` and drop the Stackdriver comment. Runtime `eclipse-temurin:…-jre-alpine` (`Dockerfile:31`), port 9555.

### loadgenerator (Python)
- No Google deps. `Dockerfile:52` `locust --host="http://${FRONTEND_ADDR}"`; k8s sets
  `FRONTEND_ADDR=frontend:80` (`loadgenerator.yaml:82-83`) — in Compose it must be `frontend:8080`.

### shoppingassistantservice (Python) — not wired
- `requirements.in:2,5,6` `langchain-google-genai`, `langchain-google-alloydb-pg`,
  `google-cloud-secret-manager`; `shoppingassistantservice.py:19` `secretmanager_v1`, `:22` Gemini.
  Entirely Google-dependent; no non-Google fallback.

## Stack & seams

### Port / env map for Compose (canonical: `kubernetes-manifests/*.yaml`)
| service | container port | key env | k8s Service port ≠ container? |
| :-- | :-- | :-- | :-- |
| frontend | 8080 (`frontend.yaml:49,67`) | 8 `*_SERVICE_ADDR` (`:69-84`), `ENABLE_PROFILER=0` | **yes: 80 → 8080** (`:120-121`) |
| productcatalogservice | 3550 | `PORT`, `DISABLE_PROFILER=1` | no |
| cartservice | 7070 | `REDIS_ADDR` | no |
| redis (`redis-cart`) | 6379 | — | no |
| currencyservice | 7000 | `PORT`, `DISABLE_PROFILER=1` | no |
| paymentservice | 50051 | `PORT`, `DISABLE_PROFILER=1` | no |
| shippingservice | 50051 | `PORT`, `DISABLE_PROFILER=1` | no |
| emailservice | 8080 (`emailservice.yaml:48-51`) | `PORT`, `DISABLE_PROFILER=1` | **yes: 5000 → 8080** (`:82-83`) |
| checkoutservice | 5050 | `PORT` + 6 addrs | no |
| recommendationservice | 8080 | `PORT`, `PRODUCT_CATALOG_SERVICE_ADDR` | no |
| adservice | 9555 | `PORT` | no |
| loadgenerator | — | `FRONTEND_ADDR`, `USERS`, `RATE` | — |

Compose has no Service port remapping: **`EMAIL_SERVICE_ADDR` must be `emailservice:8080`** (not
`:5000`), **`FRONTEND_ADDR` must be `frontend:8080`** (not `:80`). Host exposure: publish
frontend `8080:8080` (or `80:8080`). Redis host name: either name the service `redis-cart` or set
`REDIS_ADDR=redis:6379`. `SHOPPING_ASSISTANT_SERVICE_ADDR` needs a non-empty placeholder (see Q3).

### Build contexts
Every service has `src/<svc>/Dockerfile` except cartservice (`src/cartservice/src/Dockerfile`, build
context `src/cartservice/src`). All Dockerfiles are multi-stage and self-contained; `skaffold.yaml`
uses the same contexts. `.dockerignore` files exist only for cartservice (`src/cartservice/src/`),
checkoutservice, currencyservice, frontend, paymentservice, productcatalogservice and shippingservice;
adservice, emailservice, recommendationservice and loadgenerator have none.

### Health checks / startup ordering
- No image ships `grpc_health_probe`; Go runtimes are `distroless/static` (no shell), cartservice is
  `-chiseled` (no shell). All gRPC services register the standard `grpc.health.v1` service (k8s
  probes use `grpc:` at e.g. `adservice.yaml:62-68`).
- Frontend exposes `/_healthz` (`frontend/main.go:162`).
- gRPC clients connect lazily (`grpc.NewClient`, `frontend/main.go:224+`), so `depends_on` with
  `condition: service_started` is sufficient for correctness; only Redis benefits from a real
  healthcheck (`redis-cli ping`) before cartservice.
- Options: (a) `service_started` everywhere + Redis healthcheck (simplest); (b) add
  `grpc_health_probe` to images; (c) a `fullstorydev/grpcurl` sidecar check. Recommend (a) — Q4.

### Tracing
OpenTelemetry OTLP exporter to `COLLECTOR_SERVICE_ADDR`; gated on `ENABLE_TRACING=1` in frontend
(`main.go:113`), checkout (`:90`), productcatalog (`server.go:69`), payment (`index.js`), email/
recommendation (`os.environ["ENABLE_TRACING"]`). Vendor-neutral OTel, **not Google-specific**; off by
default. Leave off in Compose.

### Seams (tests/code that must change with removals)
- `frontend/deployment_details.go` owns `log`/`initializeLogger()` — moving these is a prerequisite
  to deleting the file (compile seam; no unit test covers it).
- `productcatalogservice/product_catalog_test.go` — exercises `loadCatalog`; must stay green after
  the AlloyDB branch is removed.
- `cartservice/tests/CartServiceTests.cs` — exercises the in-memory store via `Startup`; must stay
  green after Spanner/AlloyDB removal.
- No existing test references Spanner, AlloyDB, profiler, or deployment details — nothing to delete,
  but also **no test asserts the removals**; new red tests (step 2) would be static/build-level
  (e.g. "no `cloud.google.com` in go.mod", "no `gcr.io` in Dockerfiles", "cart uses Redis when
  `REDIS_ADDR` set") plus the Compose e2e smoke.
- `go.sum` / `package-lock.json` / `requirements.txt` regenerate after dependency removal
  (`go mod tidy`, `npm install --package-lock-only`, `pip-compile`) — build-tooling, high-risk.

### Toolchains in this container (what can be verified here)
- `go` 1.24.7 (`/usr/local/go/bin/go`); go.mod pins `toolchain go1.26.4` and auto-download works —
  `go build ./...` in productcatalogservice succeeded.
- `node` v22.22.2, `python3`, `java` present.
- **`dotnet` NOT installed** → the cartservice gate route (`dotnet build/test`) cannot run here.
- **`docker` CLI 29.3.1 + Compose v5.1.1 present, but no daemon** (`/var/run/docker.sock` missing)
  → `docker compose build/up` and the live e2e smoke **cannot run in this environment**;
  `docker compose config` (static validation) can.
- Quality gate (`.claude/quality-gate.routes`) has no route for the root `docker-compose.yml` or
  Dockerfiles-only changes outside `src/<svc>/` prefixes; Dockerfile edits under `src/<svc>/` trigger
  that service's build route (which does not build the image).

## Unknowns / open questions (each with a recommendation)

1. **Where does the e2e smoke run?** No Docker daemon and no `dotnet` here.
   **Resolved:** the user runs the live smoke locally (`docker compose up --build`); here we verify
   statically and deliver a smoke checklist (Decision 3). Original *rec:* verify statically here (`go build/test`, `node --check`, `compileall`,
   `docker compose config`); run the Compose smoke (`docker compose up --build`, curl `/`,
   add-to-cart, checkout) on a Docker-capable machine or CI, or declare it pending with justification.
   Update `docs/test/README.md` entry point to Compose later (work-docs).
2. **cartservice build can't be verified locally** (no dotnet). *Rec:* either install the .NET 10 SDK
   in the session (setup script) or rely on the Docker build / CI `ci-pr.yaml` C# job; flag the cart
   commits as unverified-here if neither is available.
3. **shoppingassistantservice: delete or leave?** **Resolved:** leave, not wired (Decision 4). *Rec:* leave the source, not wired in Compose
   (surgical; it is self-contained and still used by skaffold/k8s manifests, which are out of scope).
   For the frontend, set `SHOPPING_ASSISTANT_SERVICE_ADDR` to a placeholder in Compose rather than
   changing `mustMapEnv` (smallest change); `ENABLE_ASSISTANT` unset keeps the UI link hidden.
   Note: this means "no Google" is true for the *running* stack, not the whole `src/` tree.
4. **Health checks.** *Rec:* Redis `healthcheck: redis-cli ping`, cartservice
   `depends_on: redis: condition: service_healthy`; everything else `service_started`. Optionally a
   frontend `/_healthz` check only if the runtime base has `wget` (alpine does, scratch doesn't).
   No `grpc_health_probe` (YAGNI).
5. **Tracing.** Not Google-specific. *Rec:* leave code intact, `ENABLE_TRACING` unset, no collector
   container.
6. **Google Fonts in `frontend/templates/header.html:34-37`** (and
   `emailservice/templates/confirmation.html:21`). The browser fetches from
   `fonts.googleapis.com` / `fonts.gstatic.com`. Strictly a Google service.
   **Resolved: in scope** — remove the links, use a system font stack; no self-hosted font files
   unless trivially required; the "Google Symbols" icon font needs a non-Google replacement
   (Decision 1).
7. **`ENV_PLATFORM="gcp"` cosmetic branch** (`handlers.go:129-131`, `gcp-platform` CSS). No Google
   call once the metadata lookup is removed. *Rec:* remove only the `metadata.google.internal`
   auto-detect; keep the `"gcp"` enum (it is a label, not a service) — surgical.
8. **Python `google-api-core` / `google-auth` / `google-cloud-trace`.** Plain PyPI libs; no live Google
   calls in dummy mode. `google-cloud-trace` is unused. **Resolved: remove** — edit the exception
   imports, drop the deps from `requirements.in`, recompile `requirements.txt`, drop
   `google-cloud-trace` and dead profiler code (Decision 2; the "keep the libs" fallback below is
   rejected). Original *rec:* remove `google-cloud-trace` and the dead
   profiler/`GCP_PROJECT_ID` blocks; replace the two exception imports (`GoogleAPICallError` in the
   unimplemented `EmailService`, `DefaultCredentialsError` in tracing `except`) — delete the dead
   `EmailService` cloud class or catch `Exception`, then drop `google-api-core`/`google-auth` from
   `requirements.in` and recompile `requirements.txt`. Tradeoff: requirements recompile needs network
   + pip-tools; if too risky, keep the libs (no network calls) and only remove dead code. Transitive
   `googleapis-common-protos` stays (gRPC/OTel dependency).
9. **Go distroless replacement.** **Resolved:** alpine (Decision 4). *Rec:* `alpine:3.x` pinned by digest (already used by
   currency/payment runtimes, `currencyservice/Dockerfile:33`), giving a shell for optional
   healthchecks. Alternative `scratch` (smallest, but no CA certs/tzdata/shell) or
   `chainguard/static`. The current `gcr.io/distroless/static` tag runs as root (the `:nonroot` tag
   is not used), so a plain alpine runtime keeps behaviour parity; adding `USER` is optional hardening
   (YAGNI).
10. **Node builder toolchain** (`apk add python3 make g++`) after profiler removal. **Resolved:**
    recommendation below is the default (Decision 4). *Rec:* verify
    whether any remaining dep needs native builds (`@grpc/grpc-js` is pure JS); if not, drop the apk
    line (simplification) — and CLAUDE.md's "npm ci fails on native deps" note may become false,
    enabling `npm ci` in the gate (docs step).
11. **currencyservice `client.js`** requires both `@google-cloud/trace-agent` and the unlisted
    `grpc` package. **Resolved:** remove only the trace-agent line (Decision 4). *Rec:* remove only the trace-agent line (in scope); leave `grpc` breakage as a
    noted pre-existing issue (or delete `client.js` if the team agrees it is unused — Dockerfile copies
    it but nothing runs it).
12. **Compose image source:** build from `src/` (user choice) vs pulling released images from
    `us-central1-docker.pkg.dev` (Google Artifact Registry — excluded). *Rec:* build only.
13. **Go dependency tidy** may bump/prune shared indirect modules (`google.golang.org/genproto`,
    OTel). *Rec:* run `go mod tidy` per service and keep `google.golang.org/grpc`/`protobuf` (these are
    gRPC libraries, not Google services).

## Findings & sources

Local (cited inline above): per-service `go.mod`, `package.json`, `requirements.in/.txt`,
`cartservice.csproj`, `build.gradle`, Dockerfiles, `kubernetes-manifests/*.yaml`,
`.claude/quality-gate.routes`, `docs/test/README.md`.

Local findings that correct/extend the brief:
- Cloud Profiler is in **four** Go services, not two: checkoutservice (`main.go:24,98`) and
  shippingservice (`main.go:23,65`) too. Frontend (`main.go:120`) and checkout are opt-in
  (`ENABLE_PROFILER=1`); productcatalog (`server.go:78`) and shipping are on unless `DISABLE_PROFILER`.
- productcatalogservice **does** load from AlloyDB + Secret Manager when `ALLOYDB_CLUSTER_NAME` is set
  (`catalog_loader.go:37-39,62-…`).
- Frontend Google Fonts (`header.html:34-37`) and emailservice `confirmation.html:21` — unlisted
  Google dependency (now in scope).
- adservice `log4j2.xml:26-31` `logging.googleapis.com/*` JSON key names — label only, no Google call.
- Frontend `log` var lives in `deployment_details.go` (removal seam).

External (research subagent):
- Distroless is not published on Docker Hub
  (`hub.docker.com/v2/repositories/distroless/static/` → not found).
- Non-Google static bases: `alpine:3.x`, `scratch` (Go binaries are `CGO_ENABLED=0`), or
  `chainguard/static` (https://hub.docker.com/v2/repositories/chainguard/static/).
- Node/Java/Python/.NET images already avoid gcr.io (Docker Hub `node`, `alpine`,
  `eclipse-temurin`, `python`; `mcr.microsoft.com` for .NET).
- Compose `healthcheck: {test, interval, timeout, retries, start_period}` and
  `depends_on: {svc: {condition: service_healthy}}` — https://docs.docker.com/reference/compose-file/services/
  (URL unverified (proxy 403); standard Compose spec syntax). Redis: `redis-cli ping`.
- gRPC health options: `grpc_health_probe` in images, or `fullstorydev/grpcurl`
  (https://hub.docker.com/v2/repositories/fullstorydev/grpcurl/), or rely on `service_started`
  since gRPC clients connect lazily.
- No authoritative upstream docker-compose exists for this demo (upstream issue search found none).
- Node profiler loaded only when `DISABLE_PROFILER` unset (`currencyservice/server.js:28-39`,
  `paymentservice/index.js:21-31`); `@google-cloud/debug-agent` absent; `client.js:18` trace-agent
  unconditional (test client only).
- Python `googlecloudprofiler` already commented out; `google.api_core` / `google.auth` imports are
  plain PyPI libs with no live Google calls.

Task tier: standard — multi-service code removals (Go, C#, Node, Python), dependency/lockfile regeneration, base-image swaps and a new Compose build/run surface.
