# User-local smoke runbook — unit 001 `no-google-docker-compose` (T-019..T-026)

This is the live smoke for the root `docker-compose.yml` (11 app services + Redis, frontend on
`http://localhost:8080`). Run it on a machine with a working Docker daemon and unrestricted egress to
Docker Hub, `mcr.microsoft.com`, the Go module proxy, npm, PyPI and Maven Central. Scenario source:
`docs/work/001-no-google-docker-compose/2-tests.md` §E.

Save each step's output under `docs/test/001-no-google-docker-compose/` using the evidence file name
given for that step. Numbering continues from the files already in the directory (`01-`, `02-` are
the blocked in-container attempt). Then set the verdict in `summary.md` to PASS or FAIL, with a
PASS/FAIL line for each ID.

## 0. Prerequisites

- Docker Desktop, or Docker Engine 24+ with **Compose v2** (`docker compose version` prints v2.x or later).
- About 8 GB of free RAM for Docker and about 10 GB of disk. The .NET, Java and Python images are large.
- `git`, `curl`, `grep`, and a Chromium-based browser or Firefox for T-024.
- Port 8080 free on the host.

```bash
git clone https://github.com/<your-fork>/microservices-demo.git
cd microservices-demo
git checkout claude/elegant-edison-99ry8y
docker compose version
docker compose config --quiet && echo "compose config OK"
```
Expected: `compose config OK`.

## T-019 — Stack builds and starts from a clean clone

```bash
docker compose up --build -d 2>&1 | tee 03-compose-up.txt
docker compose ps -a 2>&1 | tee 04-compose-ps.txt
docker compose logs --no-color > 05-compose-logs.txt 2>&1
grep -nEi 'panic|mustMapEnv|metadata\.google\.internal|profiler|credentials|googleapis' 05-compose-logs.txt \
  | tee 06-log-grep.txt ; echo "grep exit=$?"
```
Expected:
- Every image builds with no errors. The build must include `cartservice` (.NET), the Node `npm install`
  (no python3/make/g++ toolchain) and the Python `pip install` steps.
- `04-compose-ps.txt` lists `frontend checkoutservice productcatalogservice shippingservice
  cartservice currencyservice paymentservice emailservice recommendationservice adservice
  loadgenerator redis`. Every service shows `Up` (frontend and redis show `(healthy)`), and none
  shows `Restarting` or `Exited`. `shoppingassistantservice` is **not** listed.
- `06-log-grep.txt` is empty and `grep exit=1`.

If `frontend` is still `(health: starting)`, wait until it turns healthy:
`until docker compose ps frontend | grep -q healthy; do sleep 3; done`. adservice (JVM) is the
slowest to start.

## T-020 — Home and product pages render the catalog

```bash
curl -fsS -o /dev/null -w 'home %{http_code}\n' http://localhost:8080/ | tee 07-t020-status.txt
curl -fsS http://localhost:8080/ | grep -c 'class="col-md-4 hot-product-card"' | tee -a 07-t020-status.txt
curl -fsS -o /dev/null -w 'product %{http_code}\n' http://localhost:8080/product/OLJCESPC7Z | tee -a 07-t020-status.txt
curl -fsS http://localhost:8080/product/OLJCESPC7Z | grep -E -m3 'Sunglasses|\$[0-9]+\.[0-9]{2}' | tee -a 07-t020-status.txt
curl -fsS http://localhost:8080/_healthz | tee -a 07-t020-status.txt; echo
```
Expected: `home 200`, then `9` (nine product cards), then `product 200`, then lines that show the product
(OLJCESPC7Z = "Sunglasses") and a `$NN.NN` price, then `ok`. Optionally open `http://localhost:8080/` in the
browser and save a viewport screenshot as `08-home.png`.

## T-021 — Add to cart and currency switch (cookie jar)

```bash
JAR=$(mktemp)
curl -fsS -c "$JAR" -b "$JAR" -o /dev/null http://localhost:8080/            # obtain shop_session-id
curl -sS  -c "$JAR" -b "$JAR" -o /dev/null -w 'add %{http_code}\n' \
  -X POST -d 'product_id=OLJCESPC7Z' -d 'quantity=2' http://localhost:8080/cart | tee 09-t021.txt
curl -fsS -c "$JAR" -b "$JAR" http://localhost:8080/cart > 10-cart.html
grep -nE 'Sunglasses|Quantity: 2|>2<' 10-cart.html | tee -a 09-t021.txt
curl -sS  -c "$JAR" -b "$JAR" -o /dev/null -w 'setCurrency %{http_code}\n' \
  -X POST -d 'currency_code=EUR' http://localhost:8080/setCurrency | tee -a 09-t021.txt
curl -fsS -c "$JAR" -b "$JAR" http://localhost:8080/ | grep -c '€' | tee -a 09-t021.txt
```
Expected: `add 302` (redirect to `/cart`). The cart page shows Sunglasses with quantity 2.
`setCurrency 302`. After the switch, the `€` count is greater than 0 because prices now render in EUR.
**Keep `$JAR` for T-022 and T-025.** In the browser, the same flow (add 2 Sunglasses, then pick EUR in
the header currency selector) can be captured as `11-cart.png`.

## T-022 — Checkout completes

The cart must be non-empty, so add the item again if T-021 was run in a different shell.
```bash
docker compose logs --no-color emailservice > /dev/null   # (baseline, optional)
curl -sS -c "$JAR" -b "$JAR" -X POST http://localhost:8080/cart/checkout \
  -d 'email=someone@example.com' \
  --data-urlencode 'street_address=1600 Amphitheatre Parkway' \
  -d 'zip_code=94043' \
  --data-urlencode 'city=Mountain View' \
  -d 'state=CA' \
  --data-urlencode 'country=United States' \
  -d 'credit_card_number=4432801561520454' \
  -d 'credit_card_expiration_month=1' \
  -d "credit_card_expiration_year=$(( $(date +%Y) + 1 ))" \
  -d 'credit_card_cvv=672' \
  -w '\ncheckout %{http_code}\n' > 12-order.html
tail -1 12-order.html | tee 13-t022.txt
grep -c 'Your order is complete!' 12-order.html | tee -a 13-t022.txt
grep -A3 'Confirmation #' 12-order.html | tee -a 13-t022.txt
docker compose logs --no-color emailservice | grep 'A request to send order confirmation email to' | tee -a 13-t022.txt
```
Expected: `checkout 200`, then `1`, then a non-empty order ID (UUID) under "Confirmation #", then an
emailservice log line containing `A request to send order confirmation email to someone@example.com
has been received.` The test card is synthetic, so it is safe to capture. Browser screenshot: `14-order.png`.

## T-023 — Load generator runs cleanly

Let the stack run for at least 60 s after `frontend` turns healthy, then:
```bash
docker compose logs --no-color loadgenerator > 15-loadgen.txt 2>&1
grep -nEi 'ConnectionError|ConnectionRefused|Max retries|Traceback' 15-loadgen.txt ; echo "error-grep exit=$?"
grep -E 'Aggregated|Name +# reqs' 15-loadgen.txt | tail -4
```
Expected: `error-grep exit=1` (no matches). The latest Locust `Aggregated` row shows requests greater
than 0 and `# fails` of 0, or near 0 with a written justification (for example a transient 5xx
during adservice JVM warm-up in the first seconds).

## T-024 — The browser contacts no Google host

Server-side grep of the served HTML and CSS:
```bash
for p in / /product/OLJCESPC7Z /cart; do curl -fsS -b "$JAR" "http://localhost:8080$p"; done > 16-pages.html
curl -fsS http://localhost:8080/static/styles/styles.css http://localhost:8080/static/styles/cart.css \
     http://localhost:8080/static/styles/order.css > 16-styles.css 2>/dev/null
grep -nEio '[a-z0-9.-]*(googleapis|gstatic|google)[a-z0-9./-]*' 16-pages.html 16-styles.css 12-order.html \
  | tee 17-google-grep.txt ; echo "grep exit=$?"
```
Expected: `grep exit=1` and `17-google-grep.txt` empty. If a CSS path above 404s, list the real ones with
`curl -s localhost:8080/ | grep -o '/static/[^"]*\.css'` and use those.

Browser network check:
1. Open DevTools (F12), go to the **Network** tab, tick **Disable cache**, and clear the log.
2. Load in turn `http://localhost:8080/`, `/product/OLJCESPC7Z`, add to cart to reach `/cart`, then place the order
   to reach the order page. Tick **Preserve log** first.
3. Type `-domain:localhost` in the filter box. The list must be **empty**. Also filter `google` and
   `gstatic`; both must be empty.
4. Right-click and choose **Save all as HAR with content**, saving as `18-network.har`. Check it with
   `grep -Eio '"url": *"https?://[^"/]+' 18-network.har | sort -u`, which should show only `localhost:8080`.
5. Screenshot the filtered (empty) Network panel as `19-devtools-network.png`. Pages must render
   normally: system font stack, and icons replaced or absent with no broken layout.

## T-025 — Cart survives a cartservice restart (Redis-backed)

Use the same `$JAR` session and put one item in the cart (checkout empties it):
```bash
curl -sS -c "$JAR" -b "$JAR" -o /dev/null -X POST -d 'product_id=OLJCESPC7Z' -d 'quantity=2' http://localhost:8080/cart
curl -fsS -b "$JAR" http://localhost:8080/cart | grep -c 'Sunglasses' | tee 20-t025.txt   # before
docker compose restart cartservice 2>&1 | tee -a 20-t025.txt
until docker compose ps cartservice | grep -q ' Up '; do sleep 2; done; sleep 3
curl -sS -b "$JAR" -o 21-cart-after-restart.html -w 'cart %{http_code}\n' http://localhost:8080/cart | tee -a 20-t025.txt
grep -c 'Sunglasses' 21-cart-after-restart.html | tee -a 20-t025.txt                      # after
```
Expected: the count is at least 1 before the restart, `cart 200` after it, and the count is still at least 1. The item
survived because the cart lives in Redis. With the in-memory store it would be 0.

## T-026 — Redis outage fails visibly, not silently

```bash
docker compose stop redis 2>&1 | tee 22-t026.txt
curl -sS -b "$JAR" -o 23-cart-redis-down.html \
  -w 'cart-with-redis-down %{http_code} in %{time_total}s\n' --max-time 120 http://localhost:8080/cart | tee -a 22-t026.txt
grep -ciE 'could not retrieve cart|Can.t access cart storage' 23-cart-redis-down.html | tee -a 22-t026.txt
docker compose logs --no-color --tail=30 cartservice >> 22-t026.txt 2>&1
# observational: recovery
docker compose start redis 2>&1 | tee -a 22-t026.txt
until docker compose ps redis | grep -q healthy; do sleep 2; done
curl -sS -b "$JAR" -o /dev/null -w 'cart-after-redis-start %{http_code} in %{time_total}s\n' http://localhost:8080/cart | tee -a 22-t026.txt
```
Expected: `cart-with-redis-down 500`, and the error page mentions `could not retrieve cart` (count at
least 1). A hang with no response, or `200` with an empty cart (a silent failure), is a **FAIL**.
**Record only, don't assert:** the `time_total` before failing, and whether the cart returns `200`
(and whether the item survived) after `docker compose start redis`.

## Teardown

```bash
docker compose down -v 2>&1 | tee 24-compose-down.txt
rm -f "$JAR"
```
Expected: every container and the network are removed, and no volumes remain.

## Troubleshooting

- **Build fails with `x509: certificate signed by unknown authority`**: a TLS-intercepting corporate
  proxy is in the path. This is exactly what blocked the in-container attempt (see `02-build-blocked-tls.txt`).
  Run from a network without interception, or configure Docker/BuildKit to trust your proxy's CA.
  Do not change the repo's Dockerfiles for this.
- **`frontend` exits at start with `mustMapEnv`**: an `*_SERVICE_ADDR` env var is missing in
  `docker-compose.yml`. That is a FAIL of T-019.
- **Frontend 500 "could not retrieve …" while the stack is otherwise healthy**: a backend is still starting
  (adservice or cartservice). Wait and retry. If it persists, it is a FAIL, so capture `docker compose logs <svc>`.
- **Port 8080 busy**: stop whatever uses it. Don't edit the published port, because T-018 checks it.
