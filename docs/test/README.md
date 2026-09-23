# Live e2e smoke runbook — Online Boutique (microservices-demo)

The `e2e-tester` subagent follows THIS file to prove a change works against the **real, running**
system. It is the contract: prerequisites, entry point, exact steps, expected results,
troubleshooting. Evidence + `summary.md` go to `docs/test/NNN-<slug>/`.

> **Current status: a lightweight local run exists; live smokes run user-locally.** The root
> `docker-compose.yml` (unit 001) brings the whole app up with Docker alone — no Kubernetes. In the
> agent's cloud container, however, image builds fail: egress goes through a TLS-intercepting proxy
> whose CA the build-step containers don't trust (`x509: certificate signed by unknown authority`
> during `go mod download`; see `docs/test/001-no-google-docker-compose/summary.md`). So live smokes
> of the Compose path are run **user-locally** and the agent's verdict is `PENDING — user-local run`.
> The routed quality gate (`.claude/quality-gate.routes`) stays the mechanical floor in the container.

## Prerequisites (shared bring-up)

### Primary: Docker Compose (lightweight, no Kubernetes)
- Docker (Desktop, or Engine 24+) with **Compose v2** (`docker compose version`); about 8 GB RAM and
  10 GB disk for Docker; host port 8080 free; unrestricted egress to the image registries and
  package mirrors (Docker Hub, `mcr.microsoft.com`, Go proxy, npm, PyPI, Maven Central).
- Bring the whole app up from the repo root: `docker compose up --build` (add `-d` to detach). It
  builds the 11 app services from `src/` and starts them plus `redis` (the cart store);
  `shoppingassistantservice` is intentionally not wired.
- Wait for `frontend` to turn healthy (`docker compose ps frontend` shows `(healthy)`); adservice (JVM)
  is the slowest to start.
- Reach the storefront directly at `http://localhost:8080` — the port is published, no port-forward
  needed.
- Tear down with `docker compose down -v`.
- Worked example of a full Compose smoke (build, browse, cart, checkout, load generator,
  no-Google-host check, Redis restart/outage, teardown):
  `docs/test/001-no-google-docker-compose/runbook.md`.

### Alternative: Kubernetes via Skaffold
- A Kubernetes cluster: local (`minikube start` / `kind create cluster`) or remote (GKE).
- `kubectl` and `skaffold` on PATH; Docker for local image builds.
- Bring the whole app up from the repo root: `skaffold run` (build + deploy) or `skaffold dev`
  (rebuild-on-change). Wait for all deployments to become available
  (`kubectl wait --for=condition=available --timeout=600s deployment --all`).
- Reach the storefront: `kubectl port-forward deployment/frontend 8080:8080`, then open
  `http://localhost:8080` (or the `frontend-external` LoadBalancer IP on a cloud cluster).

### Both paths
- Never capture or commit secrets; use synthetic/test data only (see Evidence & retention).

## Entry point
See **Prerequisites** — the primary entry point is `docker compose up --build` → `http://localhost:8080`
(teardown `docker compose down -v`); the alternative is `skaffold run` + the frontend port-forward.
Per service, follow the matching subsection under **## Services** once filled.

## Expected verdict
PASS = the documented observable outcomes hold. A timeout, a 5xx, an auth wall, or fabricated
output is a **FAIL** — captured, never a false pass.

## Services (fill one subsection per service as the team works on it)
The dispatch names the service(s) under test; the tester follows **that service's** subsection only.
The storefront `frontend` is the natural smoke surface for most user-visible changes; back-end
services (checkout, cart, product catalog, shipping, currency, payment, etc.) are exercised through
the frontend flows or via direct gRPC calls (`grpcurl`) against a port-forwarded pod.

### frontend
- **Entry point:** Compose: `http://localhost:8080` directly. Skaffold:
  `kubectl port-forward deployment/frontend 8080:8080` → `http://localhost:8080`.
- **Steps & expected results:**
  1. Load the home page → product grid renders with prices in the selected currency. Capture
     `01-home.png`.
  2. Open a product, "Add to Cart", then view cart → item appears with correct quantity/price.
     Capture `02-cart.png`.
  3. Complete checkout with test card data → order-confirmation page with an order ID. Capture
     `03-order-confirmation.png`.
- **Expected verdict:** PASS = browse → cart → checkout completes with no 5xx and correct totals.

## Troubleshooting
- Compose build fails with `x509: certificate signed by unknown authority` → a TLS-intercepting proxy
  is in the path (this is what blocks builds in the agent's cloud container). Run from a network
  without interception, or configure Docker/BuildKit to trust the proxy's CA; don't edit the
  Dockerfiles for it.
- Compose frontend 500 "could not retrieve …" right after start → a backend (adservice, cartservice)
  is still starting; wait and retry, else capture `docker compose logs <svc>`.
- Pods stuck `Pending` → cluster lacks resources; give minikube/kind more CPU/memory.
- `ImagePullBackOff` on a local cluster → build with Skaffold (`skaffold dev`) rather than pulling
  pre-built images, or point Skaffold at your local Docker daemon.
- Frontend 500s referencing a downstream service → that gRPC dependency isn't ready; re-check
  `kubectl get pods` and wait for all deployments to be available.

## Evidence & retention
Screenshots are **committed to the repo** as a visual audit trail of what the smoke actually saw — a
deliberate feature, kept for the long run. The catch: a committed image is **permanent in git
history**, so the discipline here is about **security**, not avoidance:
- **Never capture a secret.** No screen showing real credentials, tokens, API keys, or PII — a leaked
  secret baked into an image is permanent and can't be `git rm`-ed out of history. Use throwaway /
  test accounts and seeded or synthetic data; redact or crop anything sensitive before you capture.
- **Capture the viewport, not the full page** — enough to prove the step, no more surface to leak.
- **`summary.md` stands alone.** It must read completely without the images; the screenshots back up
  what it already states, they don't replace it.
