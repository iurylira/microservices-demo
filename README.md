<!-- <p align="center">
<img src="/src/frontend/static/icons/Hipster_HeroLogoMaroon.svg" width="300" alt="Online Boutique" />
</p> -->

**Online Boutique** is a microservices demo application: a web-based e-commerce store where users
browse items, add them to a cart, and purchase them. It is made of 11 services written in Go, C#,
Java, Node.js and Python that talk to each other over gRPC. It runs entirely on your own machine
with Docker Compose, with no cloud services.

## Architecture

**Online Boutique** is composed of 11 microservices written in different
languages that talk to each other over gRPC.

[![Architecture of
microservices](/docs/img/architecture-diagram.png)](/docs/img/architecture-diagram.png)

Find **Protocol Buffers Descriptions** at the [`./protos` directory](/protos). For the full system
design (layers, dependency graph, request flows, configuration), see
[docs/architecture.md](/docs/architecture.md).

| Service                                              | Language      | Description                                                                                                                       |
| ---------------------------------------------------- | ------------- | --------------------------------------------------------------------------------------------------------------------------------- |
| [frontend](/src/frontend)                           | Go            | Exposes an HTTP server to serve the website. Does not require signup/login and generates session IDs for all users automatically. |
| [cartservice](/src/cartservice)                     | C#            | Stores the items in the user's shopping cart in Redis and retrieves it.                                                           |
| [productcatalogservice](/src/productcatalogservice) | Go            | Provides the list of products from a JSON file and ability to search products and get individual products.                        |
| [currencyservice](/src/currencyservice)             | Node.js       | Converts one money amount to another currency, using a bundled table of exchange rates. It's the highest QPS service.            |
| [paymentservice](/src/paymentservice)               | Node.js       | Charges the given credit card info (mock) with the given amount and returns a transaction ID.                                     |
| [shippingservice](/src/shippingservice)             | Go            | Gives shipping cost estimates based on the shopping cart. Ships items to the given address (mock)                                 |
| [emailservice](/src/emailservice)                   | Python        | Sends users an order confirmation email (mock).                                                                                   |
| [checkoutservice](/src/checkoutservice)             | Go            | Retrieves user cart, prepares order and orchestrates the payment, shipping and the email notification.                            |
| [recommendationservice](/src/recommendationservice) | Python        | Recommends other products based on what's given in the cart.                                                                      |
| [adservice](/src/adservice)                         | Java          | Provides text ads based on given context words.                                                                                   |
| [loadgenerator](/src/loadgenerator)                 | Python/Locust | Continuously sends requests imitating realistic user shopping flows to the frontend.                                              |

## Screenshots

| Home Page                                                                                                         | Checkout Screen                                                                                                    |
| ----------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------ |
| [![Screenshot of store homepage](/docs/img/online-boutique-frontend-1.png)](/docs/img/online-boutique-frontend-1.png) | [![Screenshot of checkout screen](/docs/img/online-boutique-frontend-2.png)](/docs/img/online-boutique-frontend-2.png) |

## Quickstart (Docker Compose)

The whole store runs on one machine with Docker Compose. The
[`docker-compose.yml`](/docker-compose.yml) at the repository root builds every service from
source under [`src/`](/src).

1. Ensure you have the following requirements:
   - [Docker Desktop](https://docs.docker.com/desktop/), or Docker Engine with Compose v2
     (`docker compose version` prints v2.x or later).
   - Enough memory and disk for eleven images. The .NET, Java and Python images are large, so the
     first build takes a while.
   - Port `8080` free on the host.

2. Clone the repository, then build and start the stack.

   ```sh
   git clone https://github.com/<your-fork>/microservices-demo.git
   cd microservices-demo/
   docker compose up --build        # add -d to run it in the background
   ```

3. Open <http://localhost:8080> in a web browser.

4. Follow the logs of a service, or stop the stack.

   ```sh
   docker compose logs -f frontend  # any service name from the table below
   docker compose down              # add -v to also remove Redis's leftover anonymous volume
   ```

The stack runs 11 application services plus Redis. Only the frontend is published on the host.

| Compose service         | Language      | Container port | Role                                                        |
| ----------------------- | ------------- | -------------- | ----------------------------------------------------------- |
| `frontend`              | Go            | 8080 (host 8080) | Serves the website over HTTP.                             |
| `checkoutservice`       | Go            | 5050           | Places orders: payment, shipping and confirmation email.    |
| `productcatalogservice` | Go            | 3550           | Serves the product list from `products.json`.               |
| `shippingservice`       | Go            | 50051          | Shipping quotes and mock shipping.                          |
| `cartservice`           | C#            | 7070           | Stores shopping carts in Redis.                             |
| `currencyservice`       | Node.js       | 7000           | Converts money between currencies.                          |
| `paymentservice`        | Node.js       | 50051          | Charges the card (mock).                                    |
| `emailservice`          | Python        | 8080           | Sends the order confirmation email (mock).                  |
| `recommendationservice` | Python        | 8080           | Recommends other products.                                  |
| `adservice`             | Java          | 9555           | Serves text ads.                                            |
| `loadgenerator`         | Python/Locust | none           | Sends simulated shopper traffic to the frontend.            |
| `redis`                 | Redis         | 6379           | Cart database (`redis:8.10.2-alpine` image, pinned by digest). |

The `loadgenerator` starts sending traffic once the frontend is healthy. To stop it, run
`docker compose stop loadgenerator`.

What is different from a cloud deployment:

- No cloud-provider dependencies. There is no managed database, profiler or metadata server:
  every image is built locally from `src/`, the frontend uses the system font stack, and the cart
  lives in the bundled Redis container.
- The shopping assistant is not included (see [Shopping assistant](#shopping-assistant)).

To check a run end to end, follow the
[live-smoke runbook](/docs/test/001-no-google-docker-compose/runbook.md).

### Troubleshooting

- **Build fails with `x509: certificate signed by unknown authority`**: a TLS-intercepting proxy is
  in the path. Build from a network without interception, or configure Docker/BuildKit to trust
  your proxy's CA.
- **`frontend` exits at start with `mustMapEnv`**: an `*_SERVICE_ADDR` environment variable is
  missing from `docker-compose.yml`.
- **Frontend shows a 500 "could not retrieve …" right after start**: a backend (often `adservice`
  or `cartservice`) is still starting. Wait and retry; if it persists, check
  `docker compose logs <service>`.
- **Port 8080 busy**: stop whatever is using it on the host.

## Shopping assistant

[`src/shoppingassistantservice`](/src/shoppingassistantservice) is still the upstream Gemini +
AlloyDB version, so it is **not wired** into the Compose stack. The frontend only gets a placeholder
`SHOPPING_ASSISTANT_SERVICE_ADDR`, and the assistant UI stays off unless `ENABLE_ASSISTANT=true`
(requests to `/bot` then fail, since no backend runs). A plan for running it with a local LLM
through Ollama and a local Postgres + pgvector store, not yet implemented, is in
[Shopping assistant with Ollama](/docs/shopping-assistant-ollama.md).

## Documentation

- [Architecture](/docs/architecture.md): system design, service catalog and request flows.
- [Adding a new microservice](/docs/adding-new-microservice.md).
- [Live-smoke runbook](/docs/test/001-no-google-docker-compose/runbook.md): verify a Docker Compose run.
- [Shopping assistant with Ollama](/docs/shopping-assistant-ollama.md): plan for a local-LLM assistant.

## License

Apache 2.0, see [LICENSE](/LICENSE).
