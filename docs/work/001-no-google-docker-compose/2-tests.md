# 001 — Run Online Boutique without Google services, on Docker Compose — Behaviour spec

> Step 2 of the pipeline (tests: behaviour spec only — no production code, no plan).
> Input: [`1-research.md`](1-research.md) (approved, incl. its **Decisions**).
> Branch: `work/001-no-google-docker-compose`. Task tier: **standard**.

## Where each check runs

This container has `go`, `node`, `python3`, `java` (Gradle wrapper), the `docker` CLI and Compose v5,
but **no Docker daemon and no `dotnet`**. Every scenario therefore names one of two venues:

- **(a) container** — runs here and in the quality gate: `go build`/`go test`/`go list`, `node --check`,
  `python3 -m compileall`, `bash gradlew --no-daemon assemble`, `docker compose config`, and
  grep-based repository assertions.
- **(b) user-local** — needs a Docker daemon: run by the user with `docker compose up --build` from a
  fresh clone (Decision 3). **cartservice** build and unit tests also land here (the .NET build
  happens inside its Dockerfile) or in CI (`.github/workflows` C# job). They **cannot be verified in
  this container**; cart commits are flagged "unverified-here" until (b) or CI runs.

Common definitions used below:

- **SCOPE** = `src/` **excluding** `src/shoppingassistantservice/`, plus the new root
  `docker-compose.yml`. Lockfile `go.sum` is excluded from text greps (it can keep checksums of
  modules that are in the graph but never compiled in; T-002 checks the compiled graph instead).
- **GOOGLE_PATTERN** (extended regex, case-sensitive unless noted):
  `cloud\.google\.com|@google-cloud/|google-cloud-|gcr\.io|pkg\.dev|metadata\.google\.internal|googleapis\.com|fonts\.gstatic\.com|google-api-core|google-auth|google\.api_core|google\.auth|googlecloudprofiler|Google\.Cloud\.|GCP_PROJECT_ID|[Ss]panner|[Aa]lloy[Dd][Bb]|secretmanager`
  It deliberately does **not** match `google.golang.org/grpc`, `google.golang.org/protobuf`,
  `google-protobuf`, `googleapis-common-protos`, `com.google.protobuf` or the `"Google LLC"` licence
  headers — those are protobuf/gRPC libraries and copyright text, not Google services (research Q13,
  Python slice).

## In scope to test
- Repo-wide "zero Google" in SCOPE: dependency manifests, source, Dockerfile base images, HTML
  templates (fonts), adservice log keys (Decisions 1, 2, 4, 5).
- Every touched service still builds; existing unit tests stay green.
- productcatalogservice always loads `products.json` (AlloyDB env no longer selects anything).
- cartservice store selection: `REDIS_ADDR` → Redis; nothing set → in-memory; Spanner/AlloyDB env
  vars select nothing.
- frontend starts without GCP metadata and with a placeholder `SHOPPING_ASSISTANT_SERVICE_ADDR`.
- The root `docker-compose.yml`: validity, service set, wiring (addresses/ports), build-from-source,
  no Google registry images.
- The user-local live smoke of the full stack (browse, cart, currency, checkout, no Google hosts,
  loadgenerator, Redis persistence, Redis outage).

## Out of scope to test
- `shoppingassistantservice/` (not wired; still Google-dependent by design — Decision 4 / Q3).
- `kubernetes-manifests/`, `kustomize/`, `helm-chart/`, `istio-manifests/`, `terraform/`,
  `skaffold.yaml`, `cloudbuild.yaml`, `.github/` — untouched deploy paths; they may keep `gcr.io` /
  `pkg.dev` references.
- Tracing (OTel, off by default), the packaging service (`PACKAGING_SERVICE_URL` unset), the
  `ENV_PLATFORM="gcp"` cosmetic label (kept per Q7 — it is a label, not a Google call).
- Compose healthchecks / startup ordering details (a plan choice, Q4); only their *effect* is covered
  by the live smoke.
- The pre-existing `grpc` breakage in `currencyservice/client.js` (Q11) beyond `node --check`.
- Visual fidelity of the replacement system font stack / icon glyphs (not observable by a test;
  checked by eye in T-020 only insofar as the page renders).

## Seams
| Seam | Under test via | Substitute? |
| :-- | :-- | :-- |
| productcatalogservice `loadCatalog` ↔ local `products.json` | Go unit test in the package (`go test` cwd is `src/productcatalogservice/`, where `products.json` lives), env set with `t.Setenv` | None — real file |
| cartservice `Startup.ConfigureServices` store selection | Existing `TestServer` pattern in `tests/CartServiceTests.cs`, with host configuration supplied through the host builder (e.g. an in-memory configuration source) | None for in-memory; **real Redis** only in the live smoke (no Redis mock) |
| Redis (cart DB) | Live Compose `redis` container | None — real Redis; no mock anywhere |
| frontend ↔ GCP metadata server | Compiled dependency graph (`go list -deps`) + grep + live start with no metadata server reachable | None |
| Compose file | `docker compose config` (normalised model) parsed with `python3 -m json` / `--format json` | None |
| Whole stack ↔ browser/HTTP | `curl` (and optionally a browser DevTools network log) against the published frontend | None |

No mocks are introduced. Existing test doubles (the in-memory catalog seeded in
`product_catalog_test.go:31`) are reused unchanged.

## Scenarios

### A. Zero-Google static assertions (container)

**T-001 — No Google service references in SCOPE** · happy-path
- **Given** the repository after the change
- **When** `grep -rInE "$GOOGLE_PATTERN" src docker-compose.yml --exclude-dir=shoppingassistantservice --exclude=go.sum` runs
- **Then** it prints nothing (exit status 1). Baseline today (over `src/` only, since
  `docker-compose.yml` does not exist yet and the literal command exits 2): **38 files / 246 lines**,
  incl. `cartservice.csproj`, `Startup.cs`, `catalog_loader.go`, all four Go `go.mod`/`main.go|server.go`
  and Dockerfiles, both Node `package.json`/`package-lock.json`, both Python `requirements.*`, the two
  HTML templates, `log4j2.xml` and the commented `storage.googleapis.com` profiler line in
  `src/adservice/Dockerfile:36`.
- **Verified by:** (a) container — the grep above as a shell assertion.

**T-002 — Go binaries compile in no Google Cloud module** · happy-path
- **Given** each of `src/frontend`, `src/checkoutservice`, `src/productcatalogservice`, `src/shippingservice`
- **When** `go list -deps ./... | grep -E '^(cloud\.google\.com/|google\.golang\.org/api/)'` runs in each
- **Then** it prints nothing, **and** `grep -E '^\s*(require\s+)?cloud\.google\.com/' go.mod` prints nothing
  (profiler, compute/metadata, alloydbconn, secretmanager all gone after `go mod tidy`).
- **Verified by:** (a) container — `go list` + grep per Go service.

**T-003 — No Google-registry base images; Go runtimes on alpine** · happy-path
- **Given** every `Dockerfile` under SCOPE (`src/*/Dockerfile`, `src/cartservice/src/Dockerfile`)
- **When** its `FROM` lines are listed (`grep -n '^FROM' …`)
- **Then** none references `gcr.io` or `pkg.dev`, and the final (runtime) stage of the four Go
  Dockerfiles is an `alpine` image (Decision 4 / Q9) instead of `gcr.io/distroless/static`.
- **Verified by:** (a) container — grep over `FROM` lines.

**T-004 — Node services have no `@google-cloud/*` and still parse** · happy-path
- **Given** `src/currencyservice` and `src/paymentservice`
- **When** `package.json` and `package-lock.json` are grepped for `@google-cloud/` and every
  first-party `*.js` (excluding `node_modules/`) is checked with `node --check`
- **Then** the grep is empty and every `node --check` exits 0 (`server.js`, `index.js`, `client.js`,
  `charge.js`, `logger.js`).
- **Verified by:** (a) container — grep + `node --check`. (The lockfile's installability — `npm ci`
  inside the Dockerfile, now without `python3 make g++` — is proven in T-019.)

**T-005 — Python services have no google-api-core / google-auth / google-cloud-* and still compile** · happy-path
- **Given** `src/emailservice`, `src/recommendationservice`, `src/loadgenerator`
- **When** `requirements.in` / `requirements.txt` are grepped for `^google-api-core|^google-auth|^google-cloud-`
  and the `*.py` for `google\.api_core|google\.auth|googlecloudprofiler|GCP_PROJECT_ID`,
  `src/emailservice/Dockerfile` is grepped for `ENABLE_PROFILER`, and `python3 -m compileall -q`
  runs on each directory
- **Then** the greps are empty (transitive `googleapis-common-protos` may remain; the dead
  `ENV ENABLE_PROFILER=1` at `emailservice/Dockerfile:38-39` is gone) and compileall exits 0.
- **Verified by:** (a) container — grep + `compileall`. (Installability of the recompiled
  `requirements.txt` is proven in T-019.)

**T-006 — No Google Fonts in served templates** · happy-path
- **Given** `src/frontend/templates/*.html` and `src/emailservice/templates/*.html`
- **When** they are grepped for `fonts\.googleapis\.com|fonts\.gstatic\.com|Google\+Symbols`
- **Then** nothing matches (Decision 1; `header.html:34-37`, `confirmation.html:21` today).
- **Verified by:** (a) container — grep. Browser-side confirmation in T-024.

**T-007 — adservice logs neutral trace keys and still builds** · happy-path
- **Given** `src/adservice/src/main/resources/log4j2.xml`
- **When** it is grepped for `logging.googleapis.com` and for `key="trace_id"`, `key="span_id"`, `key="trace_sampled"`
- **Then** the first grep is empty and all three neutral keys are present (Decision 5), and
  `bash gradlew --no-daemon assemble` in `src/adservice` succeeds.
- **Verified by:** (a) container — grep + Gradle assemble.

**T-008 — cartservice carries no Spanner/AlloyDB/Secret Manager code or packages** · happy-path
- **Given** `src/cartservice/src/`
- **When** `cartservice.csproj` is grepped for `Google\.Cloud\.|Npgsql`, and the files
  `cartstore/SpannerCartStore.cs`, `cartstore/AlloyDBCartStore.cs` are looked up
- **Then** the grep is empty and both files are absent (T-001 already bans `Spanner`/`AlloyDB` text in `Startup.cs`).
- **Verified by:** (a) container — grep + `test ! -e`. Compilation is **not** verifiable here (no
  `dotnet`) → T-010.

### B. Builds and regression nets

**T-009 — Go services build and their existing tests stay green** · happy-path (regression)
- **Given** the four Go services after dependency removal and `go mod tidy`
- **When** `go build ./... && go vet ./... && go test ./...` runs in each
- **Then** all exit 0: `frontend` (`money`, `validator` tests), `checkoutservice` (`money`),
  `productcatalogservice` (`product_catalog_test.go`: Get/List/Search), `shippingservice`
  (`shippingservice_test.go`: GetQuote, GetQuoteEmptyCart, ShipOrder); the frontend compiles.
- **Verified by:** (a) container — per-service `go build/vet/test` (the quality-gate routes).

**T-010 — cartservice builds and existing unit tests stay green** · happy-path (regression)
- **Given** cartservice with Spanner/AlloyDB removed
- **When** `dotnet build src/cartservice/cartservice.sln` and `dotnet test src/cartservice/` run
- **Then** both succeed; `CartServiceTests` (`GetItem_NoAddItemBefore_EmptyCartReturned`,
  `AddItem_ItemExists_Updated`, `AddItem_New_Inserted`) pass on the in-memory branch.
- **Verified by:** (b) **user-local / CI only** — `dotnet` is absent here. Locally the build is also
  exercised by `docker compose build cartservice` (T-019); tests run via a local .NET 10 SDK or the
  CI C# job. Honestly flagged as unverified in this container.

### C. Service behaviour

**T-011 — Catalog loads from `products.json` by default** · happy-path
- **Given** no `ALLOYDB_*` env and an empty `pb.ListProductsResponse`
- **When** `loadCatalog(&catalog)` is called from a unit test in `src/productcatalogservice`
- **Then** it returns `nil` and the catalog holds the 9 products of `products.json`, incl. id `OLJCESPC7Z`.
- **Verified by:** (a) container — new Go unit test, `go test ./...` in productcatalogservice.
  (Existing tests seed the catalog in `TestMain` and never reach `loadCatalog`, so this is new coverage.)

**T-012 — AlloyDB env no longer diverts the catalog loader** · edge/negative
- **Given** `ALLOYDB_CLUSTER_NAME`, `PROJECT_ID`, `REGION` set to non-empty dummy values (`t.Setenv`)
- **When** `loadCatalog(&catalog)` is called
- **Then** it still returns `nil` with the same 9 products from `products.json` — no network/DB
  attempt. **Red today**: `catalog_loader.go:37-39` switches to `loadCatalogFromAlloyDB` and fails.
- **Verified by:** (a) container — new Go unit test in productcatalogservice.

**T-013 — Cart with no store env uses the in-memory store** · happy-path
- **Given** a `TestServer` host for `Startup` with no `REDIS_ADDR` (existing test setup)
- **When** an item is added and the cart is read back over gRPC
- **Then** the item is returned — covered by the existing `AddItem_New_Inserted` (no new test needed).
- **Verified by:** (b) user-local / CI — `dotnet test src/cartservice/` (T-010).

**T-014 — Spanner/AlloyDB env vars select nothing** · edge/negative
- **Given** a `TestServer` host for `Startup` whose configuration sets `SPANNER_PROJECT`,
  `SPANNER_CONNECTION_STRING` and `ALLOYDB_PRIMARY_IP` to dummy values and leaves `REDIS_ADDR` unset
- **When** an item is added and the cart is read back over gRPC
- **Then** the call succeeds and returns the item (in-memory store). **Red today**: `Startup.cs:43-51`
  would register `SpannerCartStore`/`AlloyDBCartStore`, which cannot reach a real backend.
- **Verified by:** (b) user-local / CI — new xUnit test in `tests/CartServiceTests.cs`, `dotnet test`.
  Not runnable in this container.

(The `REDIS_ADDR` → Redis branch is not unit-tested — it needs a real Redis; it is pinned live by T-025.)

### D. Compose file (container, static)

All D-scenarios parse `docker compose config --format json` (run from the repo root, no daemon needed).

**T-015 — Compose file is valid and self-contained** · happy-path
- **Given** a fresh clone with no `.env` file and no extra environment variables exported
- **When** `docker compose config --quiet` runs at the repo root
- **Then** it exits 0 with no warnings about unset variables.
- **Verified by:** (a) container — `docker compose config`.

**T-016 — Exactly the wired services are defined** · happy-path / edge
- **Given** the normalised Compose model
- **When** its `services` keys are listed
- **Then** they are exactly `adservice, cartservice, checkoutservice, currencyservice, emailservice,
  frontend, loadgenerator, paymentservice, productcatalogservice, recommendationservice,
  shippingservice` plus one Redis service (named `redis` or `redis-cart`) — and **no**
  `shoppingassistantservice` (edge: Decision 4).
- **Verified by:** (a) container — `docker compose config --services` / JSON assertion.

**T-017 — Services are built from `src/`, never pulled from a Google registry** · happy-path / edge
- **Given** the normalised Compose model
- **When** each service's `build` and `image` are inspected
- **Then** every app service has a `build.context` under `src/` whose Dockerfile exists
  (`src/cartservice/src` for cartservice, `src/<svc>` otherwise); the Redis service is the only one
  without `build` and uses a Docker Hub `redis` image; no `image` value contains `gcr.io` or `pkg.dev`
  (edge: Q12, released images live on Google Artifact Registry).
- **Verified by:** (a) container — JSON assertion + `test -f <context>/Dockerfile`.

**T-018 — Wiring matches the container ports** · happy-path / edge
- **Given** the normalised Compose model
- **When** environment and ports are inspected
- **Then**
  - frontend: `PORT=8080`; `PRODUCT_CATALOG_SERVICE_ADDR=productcatalogservice:3550`,
    `CURRENCY_SERVICE_ADDR=currencyservice:7000`, `CART_SERVICE_ADDR=cartservice:7070`,
    `RECOMMENDATION_SERVICE_ADDR=recommendationservice:8080`, `SHIPPING_SERVICE_ADDR=shippingservice:50051`,
    `CHECKOUT_SERVICE_ADDR=checkoutservice:5050`, `AD_SERVICE_ADDR=adservice:9555`,
    `SHOPPING_ASSISTANT_SERVICE_ADDR` non-empty (placeholder); `ENABLE_ASSISTANT` not `true`;
    container port 8080 published on the host (e.g. `8080:8080`).
  - checkoutservice: the six addresses above for catalog/shipping/payment(`paymentservice:50051`)/
    currency/cart plus **`EMAIL_SERVICE_ADDR=emailservice:8080`** (edge: not the k8s `:5000`).
  - recommendationservice: `PRODUCT_CATALOG_SERVICE_ADDR=productcatalogservice:3550`.
  - cartservice: `REDIS_ADDR=<redis service name>:6379`.
  - loadgenerator: **`FRONTEND_ADDR=frontend:8080`** (edge: not the k8s `:80`).
  - No service's `environment` in the normalised JSON (`docker compose config --format json`) has
    `ENABLE_TRACING=1` or `ENABLE_PROFILER=1` (asserted directly on the JSON); `ALLOYDB_*` /
    `SPANNER_*` are excluded by T-001's grep of `docker-compose.yml`.
- **Verified by:** (a) container — JSON assertion on the normalised model.

### E. Live smoke (user-local, `docker compose up --build`)

Run from a fresh clone on a machine with a Docker daemon; frontend at `http://localhost:8080`
(or the published port chosen). Evidence goes to `docs/test/001-no-google-docker-compose/`.

**T-019 — The whole stack builds and starts from a clean clone** · happy-path
- **Given** a fresh clone and no prior images
- **When** `docker compose up --build -d` runs
- **Then** every image builds (incl. cartservice .NET, Node `npm ci` without the removed native
  toolchain, Python installs of the recompiled `requirements.txt`), `docker compose ps` shows every
  service `running` (none restarting/exited), and `docker compose logs` contains no panic, no
  `mustMapEnv` failure, and no `metadata.google.internal` / profiler / credential errors.
- **Verified by:** (b) user-local.

**T-020 — Home and product pages render the catalog** · happy-path
- **Given** the stack from T-019
- **When** `curl -fsS http://localhost:8080/` and `curl -fsS http://localhost:8080/product/OLJCESPC7Z`
- **Then** both return HTTP 200; the home page lists the 9 catalog products; the product page shows
  that product with a price; `GET /_healthz` returns `ok`. (Frontend started without any GCP
  metadata server and with the placeholder assistant address.)
- **Verified by:** (b) user-local — curl (+ browser look).

**T-021 — Add to cart and currency switch** · happy-path
- **Given** a browser/cookie-jar session on the running stack
- **When** `POST /cart` (`product_id=OLJCESPC7Z`, `quantity=2`) then `GET /cart`; then `POST /setCurrency` (`currency_code=EUR`) and `GET /`
- **Then** the cart page lists the product with quantity 2; after the switch prices are shown in EUR.
- **Verified by:** (b) user-local — curl with a cookie jar, or browser.

**T-022 — Checkout completes** · happy-path
- **Given** a non-empty cart (T-021)
- **When** the checkout form is submitted (`POST /cart/checkout`) with the form defaults from
  `templates/cart.html`: `email=someone@example.com`, `street_address=1600 Amphitheatre Parkway`,
  `zip_code=94043`, `city=Mountain View`, `state=CA`, `country=United States`,
  `credit_card_number=4432801561520454`, `credit_card_expiration_month=1`,
  `credit_card_expiration_year=<current year + 1>`, `credit_card_cvv=672`
- **Then** HTTP 200 with the "Your order is complete!" page showing a non-empty order ID, and the
  emailservice log shows "A request to send order confirmation email to … has been received."
  (dummy mode, `email_server.py:110`).
- **Verified by:** (b) user-local.

**T-023 — Load generator runs cleanly** · happy-path
- **Given** the running stack
- **When** loadgenerator has run for ~1 minute
- **Then** its logs show requests against `frontend:8080` with no connection errors and a 0 % (or
  near-0, justified) failure rate in the Locust stats.
- **Verified by:** (b) user-local — `docker compose logs loadgenerator`.

**T-024 — The browser contacts no Google host** · edge/negative
- **Given** the home page, a product page, the cart page and the order page loaded in a browser
- **When** the DevTools network log (or a HAR export) is inspected, and the served HTML/CSS is grepped
  (`curl … | grep -E 'googleapis|gstatic|google'`)
- **Then** no request goes to `*.googleapis.com`, `*.gstatic.com` or any other Google domain, and the
  page still renders (system font stack, icons replaced or removed).
- **Verified by:** (b) user-local — browser network log + curl grep.

**T-025 — Cart survives a cartservice restart (Redis-backed)** · edge/negative
- **Given** a session whose cart holds an item (T-021)
- **When** `docker compose restart cartservice` and then `GET /cart` with the same session cookie
- **Then** the item is still in the cart (proves `REDIS_ADDR` selected Redis; the in-memory store
  would lose it).
- **Verified by:** (b) user-local.

**T-026 — Redis outage fails visibly, not silently** · edge/negative
- **Given** the running stack
- **When** `docker compose stop <redis service>` and then `GET /cart` (or `GET /`)
- **Then** the frontend responds with its HTTP 500 error page ("could not retrieve cart"), because
  `RedisCartStore.GetCartAsync` wraps storage failures in `RpcException(FailedPrecondition, "Can't
  access cart storage…")` (`RedisCartStore.cs:83-102`) and the frontend renders that as `renderHTTPError(…, 500)`
  (`handlers.go:74`). **Observational only:** how long the request takes before failing (Redis client
  connect timeout, no frontend gRPC deadline confirmed) and whether the cart recovers after
  `docker compose start <redis>` are recorded, not asserted.
- **Verified by:** (b) user-local.

## ID index
| ID | Title | Kind | Venue |
| :-- | :-- | :-- | :-- |
| T-001 | No Google service references in SCOPE | happy | (a) |
| T-002 | Go binaries compile in no Google Cloud module | happy | (a) |
| T-003 | No Google-registry base images; Go runtimes on alpine | happy | (a) |
| T-004 | Node: no `@google-cloud/*`, `node --check` passes | happy | (a) |
| T-005 | Python: no google-api-core/auth/cloud-*, compileall passes | happy | (a) |
| T-006 | No Google Fonts in templates | happy | (a) |
| T-007 | adservice neutral log keys + assemble | happy | (a) |
| T-008 | cartservice has no Spanner/AlloyDB code/packages | happy | (a) |
| T-009 | Go builds + existing tests green | happy (regression) | (a) |
| T-010 | cartservice builds + existing tests green | happy (regression) | (b)/CI |
| T-011 | Catalog loads `products.json` by default | happy | (a) |
| T-012 | AlloyDB env ignored by catalog loader | edge | (a) |
| T-013 | Cart in-memory with no env | happy | (b)/CI |
| T-014 | Spanner/AlloyDB env select nothing in cart | edge | (b)/CI |
| T-015 | `docker compose config` valid, self-contained | happy | (a) |
| T-016 | Exact service set, no shoppingassistantservice | happy/edge | (a) |
| T-017 | Build from `src/`, no Google registry images | happy/edge | (a) |
| T-018 | Wiring: addresses, ports, host publish | happy/edge | (a) |
| T-019 | Stack builds and starts from clean clone | happy | (b) |
| T-020 | Home + product page render | happy | (b) |
| T-021 | Add to cart + currency switch | happy | (b) |
| T-022 | Checkout completes | happy | (b) |
| T-023 | Loadgenerator runs cleanly | happy | (b) |
| T-024 | Browser contacts no Google host | edge | (b) |
| T-025 | Cart survives cartservice restart (Redis) | edge | (b) |
| T-026 | Redis outage → visible 500 error | edge | (b) |
