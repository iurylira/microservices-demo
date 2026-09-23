# Plan: 001-no-google-docker-compose

- **Inputs:** [`1-research.md`](1-research.md) (approved, incl. its **Decisions**) ·
  [`2-tests.md`](2-tests.md) (approved behaviour spec, T-001..T-026).
- **Summary:** Remove every Google-only code path, dependency, base image, font link and log label
  from the wired services (all of `src/` except `shoppingassistantservice/`), and add a
  self-contained root `docker-compose.yml` that builds the 11 wired services from `src/` and runs them
  with a Redis cart DB — so `git clone && docker compose up --build` serves Online Boutique on
  `http://localhost:8080` without contacting any Google service.
- **Commit convention:** every task below is **one atomic commit** carrying one acceptance criterion,
  per [`docs/commit-conventions.md`](../../commit-conventions.md) (conventional-commit subject, staged
  by path, never `git commit -a`, green at the batch boundary; the two red-test commits are
  expected-red by design). All commits land on the session-mandated unit branch
  **`claude/elegant-edison-99ry8y`** (used instead of `work/001-no-google-docker-compose`) —
  **never on `main`**. The unit ends with a **squash PR to `main`** (opened in `work-docs`),
  team-reviewed and **merged manually**; no step of this plan merges anything.
- **Task tier:** standard → every `coder` / `e2e-tester` dispatch runs on **Opus**.

## Environment notes (binding for every batch)

This container has `go` (auto-downloads the pinned `go1.26.4` toolchain), `node` 22, `python3` 3.11,
`java` (Gradle wrapper), the `docker` CLI + Compose v5 — but **no Docker daemon and no `dotnet`**.

1. **.NET 10 SDK (cartservice: P3-04, P3-11, P3-22 — T-008/T-010/T-013/T-014).** The routed quality
   gate runs `dotnet build`/`dotnet test` for any change under `src/cartservice/` and **blocks** when
   the `dotnet` toolchain is missing. So the **first** action of Batch B2 (the first batch touching
   cartservice) is a one-off, uncommitted setup attempt:
   `curl -fsSL https://dot.net/v1/dotnet-install.sh -o <scratchpad>/dotnet-install.sh && bash <scratchpad>/dotnet-install.sh --channel 10.0 --install-dir /root/.dotnet && ln -sf /root/.dotnet/dotnet /usr/local/bin/dotnet && dotnet --version`
   (symlinked onto the default `PATH` so the gate hook sees it; the SDK major must be 10, matching
   `src/cartservice/src/Dockerfile:19` `sdk:10.0.100`).
   - **If it succeeds:** cart tasks are verified normally (`dotnet build src/cartservice/cartservice.sln`
     + `dotnet test src/cartservice/`), and T-010/T-013/T-014 are **verified-here**.
   - **If it fails (no network / proxy refusal):** the coder still makes the minimal change and runs
     the static checks (T-008 grep + `test ! -e`), but **the orchestrator does not bypass the gate**:
     it stops at the first cart task, reports, and asks the user to either provide `dotnet` or
     explicitly approve committing P3-04 / P3-11 / P3-22 as **"unverified-here — verified by
     `docker compose build cartservice` (T-019) and the CI C# job / a local `dotnet test`"**. That
     label goes in each such commit body. Cart changes stay minimal (deletions only + one new test).
2. **Docker daemon.** `docker compose config` (static) works here; `docker compose build/up` does not.
   Image builds and the live smoke (T-019..T-026) are user-local (Decision 3) — see Batch B8.
3. **Static acceptance checks are commands, not committed scripts.** T-001..T-008 and T-015..T-018
   are grep / `go list` / `docker compose config --format json` assertions defined verbatim in
   `2-tests.md`; the coder runs them as each task's acceptance check. No test-harness script is added
   to the repo (YAGNI). `GOOGLE_PATTERN` and `SCOPE` are exactly as defined in `2-tests.md`.
4. **Gate coverage gap.** `docker-compose.yml` (repo root) matches no gate route, and Dockerfile-only
   edits trigger only the service's source build. Those tasks therefore carry an explicit static
   acceptance criterion; the image builds themselves are proven by T-019 (user-local).

## Phase 1 — Baseline

### P3-01: Baseline — record green tree and current Google footprint
- id: P3-01
- phase: baseline
- batch: B0 (orchestrator only, no dispatch)
- mode: serial
- files touched: none
- acceptance criterion: on the branch tip (`60a34de`), `go build ./... && go vet ./... && go test ./...`
  passes in `src/frontend`, `src/checkoutservice`, `src/productcatalogservice`, `src/shippingservice`;
  `node --check` passes for every `*.js` in `src/currencyservice` and `src/paymentservice`;
  `python3 -m compileall -q` passes for `src/emailservice`, `src/recommendationservice`,
  `src/loadgenerator`; `bash gradlew --no-daemon assemble` passes in `src/adservice`; `dotnet` is
  recorded as absent (cart baseline = CI only). The T-001 grep over `src/` (excl.
  `shoppingassistantservice`, `go.sum`) is recorded as **38 files** — the removal target list.
- maps-to test IDs: n/a
- expected-red: no
- high-risk: no

## Phase 2 — Seams

### P3-02: frontend — move the logger out of `deployment_details.go`
- id: P3-02
- phase: seams
- batch: B1
- mode: serial
- files touched: `src/frontend/deployment_details.go`, `src/frontend/logger.go` (new)
- acceptance criterion: the logger moves to the new `logger.go` and is initialised as a
  **package-level variable initialiser** (e.g. `var log = newLogger()`, where `newLogger()` returns the
  same JSON-formatted `*logrus.Logger` `initializeLogger()` builds today) — **not in an `init()`**.
  Reason: Go runs package-level var initialisers before any `init()`, whereas `init()` functions run in
  file-name order, so `deployment_details.go`'s `init()` (which spawns `loadDeploymentDetails()`, which
  logs) would run before a `logger.go` `init()` and hit a nil logger. `initializeLogger()` and the
  `log` declaration are removed from `deployment_details.go`, which keeps only the loader and its
  `init` that starts it. Behaviour is identical;
  `cd src/frontend && go build ./... && go vet ./... && go test ./...` is green. This makes deleting
  `deployment_details.go` in P3-07 a pure removal.
- maps-to test IDs: n/a
- expected-red: no
- high-risk: no

## Phase 3 — Red tests (all up front)

### P3-03: productcatalogservice — catalog loader specs (T-011, T-012)
- id: P3-03
- phase: red-tests
- batch: B2
- mode: serial
- files touched: `src/productcatalogservice/catalog_loader_test.go` (new)
- acceptance criterion: two Given-When-Then Go tests call `loadCatalog(&catalog)` on an empty
  `pb.ListProductsResponse` (cwd = package dir, real `products.json`, no mocks):
  (T-011) with no `ALLOYDB_*` env → returns `nil`, 9 products, includes id `OLJCESPC7Z` — **passes
  today**; (T-012) with `ALLOYDB_CLUSTER_NAME`, `PROJECT_ID`, `REGION` set via `t.Setenv` to dummy
  values → same expectation — **fails today** (the AlloyDB/Secret Manager branch errors). The package
  compiles (`go vet ./...` green); `go test -run 'LoadCatalog' -timeout 60s ./...` shows T-011 PASS
  and T-012 FAIL (a timeout on the AlloyDB branch also counts as the expected red). The existing
  `TestMain` seeding in `product_catalog_test.go` is reused unchanged.
- maps-to test IDs: T-011, T-012
- expected-red: yes
- high-risk: no

### P3-04: cartservice — Spanner/AlloyDB env selects nothing (T-014)
- id: P3-04
- phase: red-tests
- batch: B2
- mode: serial
- files touched: `src/cartservice/tests/CartServiceTests.cs`
- acceptance criterion: a new xUnit `[Fact]` builds a `TestServer` host for `Startup` whose
  configuration (e.g. `webBuilder.UseSetting(...)` or an in-memory configuration source) sets
  `SPANNER_PROJECT`, `SPANNER_CONNECTION_STRING`, `ALLOYDB_PRIMARY_IP` to dummy values with
  `REDIS_ADDR` unset, adds an item over gRPC and reads the cart back, expecting the item. It compiles
  and **fails today** (Spanner store selected). The gRPC calls carry an explicit short deadline
  (e.g. `deadline: DateTime.UtcNow.AddSeconds(10)`) and the `[Fact]` a `Timeout` where the xUnit version
  supports it, so a hang on the Spanner branch **fails fast** instead of stalling the run. Verified with `dotnet test src/cartservice/` if the
  SDK setup (Environment note 1) succeeded; otherwise **unverified-here** (orchestrator asks the user
  before committing). The three existing tests are untouched.
- maps-to test IDs: T-014
- expected-red: yes
- high-risk: no

## Phase 4 — Implementation (red → green)

### Area A — Go services + cartservice source (Batch B3)

### P3-05: productcatalogservice — always load `products.json`
- id: P3-05
- phase: implementation
- batch: B3
- mode: serial
- files touched: `src/productcatalogservice/catalog_loader.go`
- acceptance criterion: `loadCatalog` calls only `loadCatalogFromLocalFile`; the
  `ALLOYDB_CLUSTER_NAME` branch, `getSecretPayload`, `loadCatalogFromAlloyDB` and their imports
  (`alloydbconn`, `secretmanager`, `secretmanagerpb`, `pgxpool`, now-unused stdlib) are removed.
  `go build/vet/test ./...` green in `src/productcatalogservice` — **T-012 turns green**, T-011 and the
  existing Get/List/Search tests stay green. (`go.mod` is tidied later in P3-20; unused requires do
  not break the build.)
- maps-to test IDs: T-011, T-012, T-009
- expected-red: no
- high-risk: no

### P3-06: productcatalogservice — remove Cloud Profiler
- id: P3-06
- phase: implementation
- batch: B3
- mode: serial
- files touched: `src/productcatalogservice/server.go`
- acceptance criterion: the `cloud.google.com/go/profiler` import, the `DISABLE_PROFILER` block
  (`server.go:78-83`) and `initProfiling` are gone; `go build/vet/test ./...` green; `grep -nE
  "$GOOGLE_PATTERN"` over `server.go` and `catalog_loader.go` is empty.
- maps-to test IDs: T-001, T-009
- expected-red: no
- high-risk: no

### P3-07: frontend — remove GCP metadata / deployment detection
- id: P3-07
- phase: implementation
- batch: B3
- mode: serial
- files touched: `src/frontend/deployment_details.go` (deleted), `src/frontend/handlers.go`,
  `src/frontend/templates/footer.html`
- acceptance criterion: `deployment_details.go` is deleted; the `net.LookupHost("metadata.google.internal.")`
  auto-detect in `handlers.go` (`:99-104`) and the `"deploymentDetails"` template key (`:560`) are
  removed, as is the now-dead `deploymentDetails` block in `footer.html` (`:31-40`). `ENV_PLATFORM`
  handling and the `"gcp"` label stay (Q7). `go build/vet/test ./...` green in `src/frontend`; T-001
  grep over `src/frontend/*.go` and templates shows no `metadata.google.internal` / `cloud.google.com`
  outside `go.mod`/`main.go` profiler (removed next).
- maps-to test IDs: T-001, T-009, T-020
- expected-red: no
- high-risk: no

### P3-08: frontend — remove Cloud Profiler
- id: P3-08
- phase: implementation
- batch: B3
- mode: serial
- files touched: `src/frontend/main.go`
- acceptance criterion: profiler import, the `ENABLE_PROFILER` block (`:120-125`) and `initProfiling`
  (`:194-215`) removed; `go build/vet/test ./...` green; no `cloud.google.com` import in any frontend
  `*.go`.
- maps-to test IDs: T-001, T-009
- expected-red: no
- high-risk: no

### P3-09: checkoutservice — remove Cloud Profiler
- id: P3-09
- phase: implementation
- batch: B3
- mode: serial
- files touched: `src/checkoutservice/main.go`
- acceptance criterion: profiler import, the `ENABLE_PROFILER` block (`:98-103`) and `initProfiling`
  (`:180-200`) removed; `go build/vet/test ./...` green in `src/checkoutservice`.
- maps-to test IDs: T-001, T-009
- expected-red: no
- high-risk: no

### P3-10: shippingservice — remove Cloud Profiler
- id: P3-10
- phase: implementation
- batch: B3
- mode: serial
- files touched: `src/shippingservice/main.go`
- acceptance criterion: profiler import, the `DISABLE_PROFILER` block (`:65-70`) and `initProfiling`
  (`:163-183`) removed; `go build/vet/test ./...` green in `src/shippingservice` (GetQuote,
  GetQuoteEmptyCart, ShipOrder).
- maps-to test IDs: T-001, T-009
- expected-red: no
- high-risk: no

### P3-11: cartservice — delete Spanner/AlloyDB stores and their Startup branches
- id: P3-11
- phase: implementation
- batch: B3
- mode: serial
- files touched: `src/cartservice/src/cartstore/SpannerCartStore.cs` (deleted),
  `src/cartservice/src/cartstore/AlloyDBCartStore.cs` (deleted), `src/cartservice/src/Startup.cs`
- acceptance criterion: both store files are gone (`test ! -e`); `Startup.ConfigureServices` keeps only
  `REDIS_ADDR` → Redis and the in-memory fallback (the `SPANNER_*` / `ALLOYDB_PRIMARY_IP` reads and
  branches removed); `grep -nE "$GOOGLE_PATTERN" src/cartservice/src/*.cs src/cartservice/src/cartstore/*.cs`
  is empty. With the SDK: `dotnet build` + `dotnet test src/cartservice/` green — **T-014 turns
  green**, the three existing tests (T-013) stay green. Without the SDK: unverified-here per
  Environment note 1. (`.csproj` packages are removed later in P3-22.)
- maps-to test IDs: T-008, T-010, T-013, T-014
- expected-red: no
- high-risk: no

### Area B — Node, Python, templates, adservice source (Batch B4)

### P3-12: currencyservice — remove profiler and trace-agent code
- id: P3-12
- phase: implementation
- batch: B4
- mode: serial
- files touched: `src/currencyservice/server.js`, `src/currencyservice/client.js`
- acceptance criterion: the `@google-cloud/profiler` block (`server.js:28-39`) and only the
  `@google-cloud/trace-agent` line (`client.js:18`, Q11) are removed; `node --check` passes for every
  `src/currencyservice/*.js`; no `@google-cloud/` in any `*.js` there.
- maps-to test IDs: T-001, T-004
- expected-red: no
- high-risk: no

### P3-13: paymentservice — remove profiler code
- id: P3-13
- phase: implementation
- batch: B4
- mode: serial
- files touched: `src/paymentservice/index.js`
- acceptance criterion: the `@google-cloud/profiler` block (`index.js:21-31`) is removed; `node --check`
  passes for every `src/paymentservice/*.js`; no `@google-cloud/` in any `*.js` there.
- maps-to test IDs: T-001, T-004
- expected-red: no
- high-risk: no

### P3-14: emailservice — drop Google exception imports and dead profiler code
- id: P3-14
- phase: implementation
- batch: B4
- mode: serial
- files touched: `src/emailservice/email_server.py`
- acceptance criterion: the `google.api_core` / `google.auth` imports are gone; `except GoogleAPICallError`
  (`:100`) becomes a built-in `except Exception as err:` using `print(err)` (built-in exceptions have
  no `.message`), `except (KeyError, DefaultCredentialsError)`
  becomes `except KeyError` (the existing `except Exception` still covers the rest); the commented
  profiler / `GCP_PROJECT_ID` code (`:40,140-160`) and the "Profiler enabled" branch (`:169-176`) are
  removed. `grep -nE 'google\.api_core|google\.auth|googlecloudprofiler|GCP_PROJECT_ID'` is empty and
  `python3 -m compileall -q src/emailservice` passes.
- maps-to test IDs: T-001, T-005
- expected-red: no
- high-risk: no

### P3-15: recommendationservice — drop Google exception import and dead profiler code
- id: P3-15
- phase: implementation
- batch: B4
- mode: serial
- files touched: `src/recommendationservice/recommendation_server.py`
- acceptance criterion: the `DefaultCredentialsError` import and use (`:26,125` → `except KeyError`),
  the commented `googlecloudprofiler` import (`:24`) and the dead profiler / `GCP_PROJECT_ID` plumbing
  (`:45-60,99-106`) are removed; the same grep as P3-14 is empty and
  `python3 -m compileall -q src/recommendationservice` passes.
- maps-to test IDs: T-001, T-005
- expected-red: no
- high-risk: no

### P3-16: frontend + emailservice — replace Google Fonts with a system font stack
- id: P3-16
- phase: implementation
- batch: B4
- mode: serial
- files touched: `src/frontend/templates/header.html`, `src/frontend/static/styles/styles.css`,
  `src/emailservice/templates/confirmation.html`
- acceptance criterion: the four `fonts.googleapis.com` / `fonts.gstatic.com` lines in `header.html`
  (`:34-37`, incl. the unused "Google Symbols" icon font — no template/CSS references its glyphs) and
  the DM Sans link in `confirmation.html` (`:21`) are removed; the `'DM Sans'` `font-family`
  declarations (`styles.css:25`, `confirmation.html:25`) become one system stack
  (e.g. `system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif`).
  The T-006 grep over both template dirs is empty; `cd src/frontend && go build ./... && go test ./...`
  and `python3 -m compileall -q src/emailservice` pass.
- maps-to test IDs: T-001, T-006, T-024
- expected-red: no
- high-risk: no

### P3-17: adservice — neutral trace log keys
- id: P3-17
- phase: implementation
- batch: B4
- mode: serial
- files touched: `src/adservice/src/main/resources/log4j2.xml`
- acceptance criterion: the `logging.googleapis.com/trace|spanId|traceSampled` keys (`:26-31`) are
  renamed to `trace_id`, `span_id`, `trace_sampled` and the Stackdriver comment is dropped; the T-007
  greps hold and `cd src/adservice && bash gradlew --no-daemon assemble` succeeds.
  Not high-risk: `log4j2.xml` is a runtime log-layout resource, not build tooling or a dependency
  manifest — it renames three JSON output keys only and cannot affect the build (the assemble above
  proves it still packages), so it stays in the feature batch.
- maps-to test IDs: T-001, T-007
- expected-red: no
- high-risk: no

### Area C — dependency manifests & lockfiles (Batch B5, all high-risk)

### P3-18: frontend — `go mod tidy` drops Google Cloud modules
- id: P3-18
- phase: implementation
- batch: B5
- mode: serial
- files touched: `src/frontend/go.mod`, `src/frontend/go.sum`
- acceptance criterion: after `go mod tidy`, `go.mod` has no `cloud.google.com/` requirement and
  `go list -deps ./... | grep -E '^(cloud\.google\.com/|google\.golang\.org/api/)'` is empty (T-002);
  the `go`/`toolchain` directives and the direct `google.golang.org/grpc` / `protobuf` / OTel versions
  are unchanged (the diff is removals only — if tidy upgrades anything, stop and report); `go build/vet/test ./...` green.
- maps-to test IDs: T-002, T-009
- expected-red: no
- high-risk: yes

### P3-19: checkoutservice — `go mod tidy` drops Google Cloud modules
- id: P3-19
- phase: implementation
- batch: B5
- mode: serial
- files touched: `src/checkoutservice/go.mod`, `src/checkoutservice/go.sum`
- acceptance criterion: same as P3-18 for `src/checkoutservice` (T-002 empty, removals-only diff,
  build/vet/test green).
- maps-to test IDs: T-002, T-009
- expected-red: no
- high-risk: yes

### P3-20: productcatalogservice — `go mod tidy` drops AlloyDB / Secret Manager / profiler / pgx
- id: P3-20
- phase: implementation
- batch: B5
- mode: serial
- files touched: `src/productcatalogservice/go.mod`, `src/productcatalogservice/go.sum`
- acceptance criterion: same as P3-18 for `src/productcatalogservice`; additionally `alloydbconn`,
  `secretmanager`, `profiler` and `github.com/jackc/pgx/v5` are gone from `go.mod`; T-011/T-012 and the
  existing tests stay green.
- maps-to test IDs: T-002, T-009
- expected-red: no
- high-risk: yes

### P3-21: shippingservice — `go mod tidy` drops Google Cloud modules
- id: P3-21
- phase: implementation
- batch: B5
- mode: serial
- files touched: `src/shippingservice/go.mod`, `src/shippingservice/go.sum`
- acceptance criterion: same as P3-18 for `src/shippingservice`.
- maps-to test IDs: T-002, T-009
- expected-red: no
- high-risk: yes

### P3-22: cartservice — remove Google / AlloyDB packages from the csproj
- id: P3-22
- phase: implementation
- batch: B5
- mode: serial
- files touched: `src/cartservice/src/cartservice.csproj`
- acceptance criterion: the `Google.Cloud.Spanner.Data`, `Npgsql` and `Google.Cloud.SecretManager.V1`
  `PackageReference`s are removed; `grep -nE 'Google\.Cloud\.|Npgsql'` on the csproj is empty (T-008).
  With the SDK: `dotnet build src/cartservice/cartservice.sln` and `dotnet test src/cartservice/`
  green (T-010, all four tests). Without it: unverified-here per Environment note 1.
- maps-to test IDs: T-008, T-010
- expected-red: no
- high-risk: yes

### P3-23: currencyservice — drop `@google-cloud/*` deps and regenerate the lockfile
- id: P3-23
- phase: implementation
- batch: B5
- mode: serial
- files touched: `src/currencyservice/package.json`, `src/currencyservice/package-lock.json`
- acceptance criterion: `@google-cloud/profiler` and `@google-cloud/trace-agent` are removed from
  `package.json`; `package-lock.json` is regenerated with `npm install --package-lock-only --ignore-scripts`
  (no `node_modules` committed; `lockfileVersion` unchanged; remaining direct deps keep their exact
  versions — diff is removals of the Google subtrees only, else stop and report). `grep '@google-cloud/'`
  on both files is empty, `npm ls --package-lock-only` reports no missing/invalid deps, and
  `node --check` passes for every `*.js`. Installability inside the image is proven by T-019.
- maps-to test IDs: T-001, T-004, T-019
- expected-red: no
- high-risk: yes

### P3-24: paymentservice — drop `@google-cloud/profiler` and regenerate the lockfile
- id: P3-24
- phase: implementation
- batch: B5
- mode: serial
- files touched: `src/paymentservice/package.json`, `src/paymentservice/package-lock.json`
- acceptance criterion: same as P3-23 for `src/paymentservice` (`@google-cloud/profiler` only).
- maps-to test IDs: T-001, T-004, T-019
- expected-red: no
- high-risk: yes

### P3-25: emailservice — drop `google-api-core` / `google-cloud-trace` and recompile requirements
- id: P3-25
- phase: implementation
- batch: B5
- mode: serial
- files touched: `src/emailservice/requirements.in`, `src/emailservice/requirements.txt`
- acceptance criterion: both lines are removed from `requirements.in`; `requirements.txt` is recompiled
  with the same tool that generated it (header: `uv pip compile requirements.in -o requirements.txt`),
  run from a throw-away venv in the scratchpad (`python3 -m venv … && pip install uv`) with
  `--python-version 3.14` (the image's `python:3.14.6-alpine`), so existing pins are kept as
  preferences and only orphaned pins disappear. **Fallback if the network blocks PyPI:** hand-edit
  `requirements.txt`, removing only the pins whose every `# via` chain leads to the removed packages
  (`google-api-core`, `google-auth`, `google-cloud-trace` and their exclusive transitives such as
  `cachetools`, `rsa`, `pyasn1*`, `proto-plus`), and fix the `# via` comments; record the fallback in the
  commit body. Check: T-005 greps empty (`googleapis-common-protos` may remain); where network allows,
  re-running the compile yields no diff (resolvable). Installability in the image is proven by T-019.
- maps-to test IDs: T-001, T-005, T-019
- expected-red: no
- high-risk: yes

### P3-26: recommendationservice — drop `google-api-core` and recompile requirements
- id: P3-26
- phase: implementation
- batch: B5
- mode: serial
- files touched: `src/recommendationservice/requirements.in`, `src/recommendationservice/requirements.txt`
- acceptance criterion: same procedure and fallback as P3-25 for `src/recommendationservice`; T-005
  greps empty; `python3 -m compileall -q src/recommendationservice` passes.
- maps-to test IDs: T-001, T-005, T-019
- expected-red: no
- high-risk: yes

### Area D — images & Compose (Batch B6, all high-risk)

### P3-27: Go Dockerfiles — alpine runtime instead of distroless
- id: P3-27
- phase: implementation
- batch: B6
- mode: serial
- files touched: `src/frontend/Dockerfile`, `src/checkoutservice/Dockerfile`,
  `src/productcatalogservice/Dockerfile`, `src/shippingservice/Dockerfile`
- acceptance criterion: each runtime stage `FROM gcr.io/distroless/static` becomes the digest-pinned
  image already used by the Node runtimes (DRY):
  `alpine:3.24.1@sha256:28bd5fe8b56d1bd048e5babf5b10710ebe0bae67db86916198a6eec434943f8b`; nothing else in
  the Dockerfiles changes (binaries are `CGO_ENABLED=0`; alpine ships CA certs). T-003 holds:
  `grep -n '^FROM' src/*/Dockerfile src/cartservice/src/Dockerfile` (excl. shoppingassistantservice)
  shows no `gcr.io`/`pkg.dev` and alpine runtimes for the four Go services. Image build proven by T-019.
- maps-to test IDs: T-001, T-003, T-019
- expected-red: no
- high-risk: yes

### P3-28: Node Dockerfiles — drop the profiler-only native toolchain
- id: P3-28
- phase: implementation
- batch: B6
- mode: serial
- files touched: `src/currencyservice/Dockerfile`, `src/paymentservice/Dockerfile`
- acceptance criterion: in each builder stage the `@google-cloud/profiler` comment and the
  `apk add --update --no-cache python3 make g++` block (`:20-25`) are removed — **only if** the
  regenerated lockfile (P3-23/P3-24) has no remaining native-build dependency (check every
  `"hasInstallScript": true` entry and any `node-gyp`/`binding.gyp` dependency; pure-JS install scripts
  are fine). If a native dep remains, keep the `apk` line and remove only the Google comment, and say so
  in the commit body. T-001 grep over both Dockerfiles is empty; `npm install --only=production` in the
  image is proven by T-019.
- maps-to test IDs: T-001, T-004, T-019
- expected-red: no
- high-risk: yes

### P3-29: emailservice + adservice Dockerfiles — remove dead profiler config
- id: P3-29
- phase: implementation
- batch: B6
- mode: serial
- files touched: `src/emailservice/Dockerfile`, `src/adservice/Dockerfile`
- acceptance criterion: `# Enable Profiler` + `ENV ENABLE_PROFILER=1` (`emailservice/Dockerfile:38-39`)
  and the commented Cloud Profiler agent block (`adservice/Dockerfile:33-38`, incl. the
  `storage.googleapis.com` URL) are removed; `grep ENABLE_PROFILER src/emailservice/Dockerfile` and the
  T-001 grep over both files are empty; `bash gradlew --no-daemon assemble` (adservice) and
  `compileall` (emailservice) still pass. (The commented profiler lines in `adservice/build.gradle`
  do not match `GOOGLE_PATTERN` and are left untouched — surgical.)
- maps-to test IDs: T-001, T-005, T-019
- expected-red: no
- high-risk: yes

### P3-30: root `docker-compose.yml` — the whole stack on Docker with Redis
- id: P3-30
- phase: implementation
- batch: B6
- mode: serial
- files touched: `docker-compose.yml` (new, repo root)
- acceptance criterion: a self-contained Compose file (no `.env`, no `${VAR}` without default, no
  `profiles`) defining exactly the 11 wired services + one `redis` service, and **no**
  `shoppingassistantservice`:
  - every app service has `build.context: ./src/<svc>` (cartservice: `./src/cartservice/src`), no `image`
    from `gcr.io`/`pkg.dev`; `redis` is the only non-built service, using a Docker Hub `redis` alpine
    image pinned to an explicit version **and digest** (resolved by the coder from Docker Hub's registry
    API; if the network blocks it, an explicit version tag such as `redis:<x.y.z>-alpine` and a note in
    the commit body);
  - env exactly per T-018 (frontend `PORT=8080` + the 7 `*_SERVICE_ADDR`s,
    `SHOPPING_ASSISTANT_SERVICE_ADDR` non-empty placeholder with a comment, no `ENABLE_ASSISTANT`;
    checkoutservice the six addresses with `EMAIL_SERVICE_ADDR=emailservice:8080`;
    recommendationservice `PRODUCT_CATALOG_SERVICE_ADDR`; each gRPC service's `PORT` from the
    research port map; `cartservice` `REDIS_ADDR=redis:6379`; loadgenerator `FRONTEND_ADDR=frontend:8080`,
    `USERS`/`RATE` as in `kubernetes-manifests/loadgenerator.yaml`); no `ENABLE_TRACING=1` /
    `ENABLE_PROFILER=1` / `ALLOYDB_*` / `SPANNER_*`;
  - frontend publishes `8080:8080`;
  - startup (Q4 option a): `redis` healthcheck `redis-cli ping`; cartservice `depends_on: redis:
    condition: service_healthy`; frontend healthcheck `wget -qO- http://localhost:8080/_healthz`
    (busybox `wget` exists now that the runtime is alpine, P3-27) and loadgenerator `depends_on:
    frontend: condition: service_healthy` (so T-023 sees no connection errors); everything else
    `service_started` / no condition.
  Checks (container): T-015 `docker compose config --quiet` exits 0 with no warnings in a clean env;
  T-016 `docker compose config --services` equals the expected set; T-017 and T-018 asserted on
  `docker compose config --format json` with a `python3 -c` JSON check (plus `test -f <context>/Dockerfile`);
  T-001 grep over `docker-compose.yml` empty. Build/run proven user-locally by T-019..T-026.
- maps-to test IDs: T-001, T-015, T-016, T-017, T-018, T-019, T-020, T-021, T-022, T-023, T-024, T-025, T-026
- expected-red: no
- high-risk: yes

## Phase 5 — Consolidation / coverage

### P3-31: full static sweep — zero Google in SCOPE, all container checks green
- id: P3-31
- phase: consolidation
- batch: B7 (orchestrator-run, **no dispatch**; a `coder` is dispatched only if a check fails)
- mode: serial
- files touched: only files already touched by P3-02..P3-30 that the sweep shows need a fix (none
  expected); no new files
- acceptance criterion: every container-venue scenario passes on the final tree in one run:
  T-001 (the exact grep over `src docker-compose.yml`, excl. `shoppingassistantservice` and `go.sum`,
  prints nothing), T-002..T-007, T-008 (static part), T-009 (build/vet/test all four Go services),
  T-011/T-012, T-015..T-018; plus T-010/T-013/T-014 via `dotnet` if the SDK is present. Any leftover
  hit is fixed minimally by a `coder` dispatched only for that failure (one `fix(...)` commit); if
  the sweep is already clean there is **no dispatch and no commit**, and this line is ticked inside the
  e2e runbook commit. No refactor beyond leftovers (DRY:
  the pinned alpine digest is reused, not re-declared; Compose uses no anchors — YAGNI).
- maps-to test IDs: T-001, T-002, T-003, T-004, T-005, T-006, T-007, T-008, T-009, T-011, T-012, T-015, T-016, T-017, T-018
- expected-red: no
- high-risk: no

## Phase 6 — E2E live smoke

### P3-32: live smoke of the Compose stack (user-local run)
- id: P3-32
- phase: e2e
- batch: B8
- mode: serial
- files touched: `docs/test/001-no-google-docker-compose/runbook.md` (new),
  `docs/test/001-no-google-docker-compose/summary.md` (new), evidence files under the same dir
- acceptance criterion: the unit **is** user-observable (the app now runs via `docker compose up`), so
  e2e is required — not `n/a`. Dispatched to **`e2e-tester`**. It first tries to obtain a daemon here
  (`dockerd` present and startable with the container's privileges → `docker info` succeeds); **if it
  does**, it runs T-019..T-026 live and the normal acceptance applies (PASS `summary.md` + ordered
  evidence, committed as `test(e2e): …`, box ticked).
  **Expected path (no daemon here) — explicit deviation from the standard "PASS `summary.md` +
  evidence" criterion,** because this container has no Docker daemon (research Decision 3), so the live
  smoke physically cannot run here:
  1. `e2e-tester` writes `runbook.md` — the user-local smoke checklist for T-019..T-026 with the exact
     commands from `2-tests.md` (`docker compose up --build -d`, `docker compose ps`/`logs`, the curl +
     cookie-jar flows for home/product/cart/currency/checkout, loadgenerator log check, browser
     network/HAR check for Google hosts, `docker compose restart cartservice`, `docker compose stop
     redis`), expected results and evidence file names — and `summary.md` with the verdict
     **"PENDING — user-local run"** (never PASS), listing the static checks already green (P3-31) and
     the cart verification status (verified-here vs. CI).
  2. The orchestrator **commits both files** on the unit branch as
     `test(e2e): add user-local compose smoke runbook (verdict PENDING)`.
  3. The **P3-32 checkbox stays unticked** in that commit; it is ticked only once the user runs the
     runbook locally and reports PASS (their evidence + `summary.md` verdict updated to PASS in a
     follow-up `test(e2e): …` commit).
  4. `work-execute` **stops for the user** after this commit — `work-docs` and the squash PR do not
     start until the user has reported the local smoke result.
- maps-to test IDs: n/a
- expected-red: no
- high-risk: no

## TODO (work-execute consumes this)

Branch for every commit: `claude/elegant-edison-99ry8y` (never `main`; no merge step).

### Batch B0 — baseline (orchestrator only, no dispatch)
- [x] P3-01 (baseline) verify Go/Node/Python/Java green, record `dotnet` absent + T-001 baseline (38 files)

### Batch B1 — seams (1 coder dispatch, serial)
- [x] P3-02 (seams) frontend: move logger into `logger.go` as a package-level var initialiser (not `init()`)

### Batch B2 — red tests (1 coder dispatch, serial) [expected-red] — first attempts .NET 10 SDK install (Environment note 1)
- [x] P3-03 (red-tests) [expected-red] productcatalogservice loader specs  -> maps T-011, T-012
- [x] P3-04 (red-tests) [expected-red] cartservice Spanner/AlloyDB env selects nothing (unverified-here without SDK)  -> maps T-014

### Batch B3 — implementation: Go services + cartservice source (1 coder dispatch, serial)
- [ ] P3-05 (implementation) productcatalogservice always loads products.json  -> maps T-011, T-012, T-009
- [ ] P3-06 (implementation) productcatalogservice remove Cloud Profiler  -> maps T-001, T-009
- [ ] P3-07 (implementation) frontend remove GCP metadata / deployment detection  -> maps T-001, T-009, T-020
- [ ] P3-08 (implementation) frontend remove Cloud Profiler  -> maps T-001, T-009
- [ ] P3-09 (implementation) checkoutservice remove Cloud Profiler  -> maps T-001, T-009
- [ ] P3-10 (implementation) shippingservice remove Cloud Profiler  -> maps T-001, T-009
- [ ] P3-11 (implementation) cartservice delete Spanner/AlloyDB stores + Startup branches  -> maps T-008, T-010, T-013, T-014

### Batch B4 — implementation: Node, Python, templates, adservice source (1 coder dispatch, serial)
- [ ] P3-12 (implementation) currencyservice remove profiler + trace-agent code  -> maps T-001, T-004
- [ ] P3-13 (implementation) paymentservice remove profiler code  -> maps T-001, T-004
- [ ] P3-14 (implementation) emailservice drop Google exceptions + dead profiler  -> maps T-001, T-005
- [ ] P3-15 (implementation) recommendationservice drop Google exception + dead profiler  -> maps T-001, T-005
- [ ] P3-16 (implementation) system font stack instead of Google Fonts  -> maps T-001, T-006, T-024
- [ ] P3-17 (implementation) adservice neutral trace log keys  -> maps T-001, T-007

### Batch B5 — implementation: dependency manifests & lockfiles (1 coder dispatch, serial) [high-risk]
- [ ] P3-18 (implementation) [high-risk] frontend go mod tidy  -> maps T-002, T-009
- [ ] P3-19 (implementation) [high-risk] checkoutservice go mod tidy  -> maps T-002, T-009
- [ ] P3-20 (implementation) [high-risk] productcatalogservice go mod tidy  -> maps T-002, T-009
- [ ] P3-21 (implementation) [high-risk] shippingservice go mod tidy  -> maps T-002, T-009
- [ ] P3-22 (implementation) [high-risk] cartservice csproj drop Google/Npgsql packages  -> maps T-008, T-010
- [ ] P3-23 (implementation) [high-risk] currencyservice drop @google-cloud deps + regen lockfile  -> maps T-001, T-004, T-019
- [ ] P3-24 (implementation) [high-risk] paymentservice drop @google-cloud dep + regen lockfile  -> maps T-001, T-004, T-019
- [ ] P3-25 (implementation) [high-risk] emailservice drop google deps + recompile requirements  -> maps T-001, T-005, T-019
- [ ] P3-26 (implementation) [high-risk] recommendationservice drop google-api-core + recompile requirements  -> maps T-001, T-005, T-019

### Batch B6 — implementation: images & Compose (1 coder dispatch, serial) [high-risk]
- [ ] P3-27 (implementation) [high-risk] Go Dockerfiles alpine runtime  -> maps T-001, T-003, T-019
- [ ] P3-28 (implementation) [high-risk] Node Dockerfiles drop profiler-only toolchain  -> maps T-001, T-004, T-019
- [ ] P3-29 (implementation) [high-risk] emailservice/adservice Dockerfiles remove dead profiler config  -> maps T-001, T-005, T-019
- [ ] P3-30 (implementation) [high-risk] root docker-compose.yml with Redis  -> maps T-001, T-015, T-016, T-017, T-018, T-019, T-020, T-021, T-022, T-023, T-024, T-025, T-026

### Batch B7 — consolidation (orchestrator-run static sweep, no dispatch; coder only if a check fails)
- [ ] P3-31 (consolidation) full static sweep, zero Google in SCOPE, final green (commit only if a fix is needed)  -> maps T-001..T-009, T-011, T-012, T-015..T-018

### Batch B8 — e2e live smoke (1 e2e-tester dispatch)
- [ ] P3-32 (e2e) Compose live smoke per runbook -> evidence + summary in docs/test/001-no-google-docker-compose/. No daemon here (expected): commit runbook.md + summary.md (verdict "PENDING — user-local run") as `test(e2e): add user-local compose smoke runbook (verdict PENDING)`, leave this box UNTICKED, and STOP for the user's local PASS before work-docs / PR.

Dispatch total: 7 (coder B1, B2, B3, B4, B5, B6 + e2e-tester B8); B0 and B7 are orchestrator-run.
