# Development Guide

This doc explains how to build, test and run the Online Boutique source code locally. The whole app
runs with Docker Compose; each service can also be built and tested on its own.

## Prerequisites

- [Docker Desktop](https://docs.docker.com/desktop/), or Docker Engine with Compose v2
  (`docker compose version` prints v2.x or later).
- Clone the repository.
    ```sh
    git clone https://github.com/<your-fork>/microservices-demo.git
    cd microservices-demo/
    ```
- Only for building or testing a single service outside Docker: that service's toolchain (Go,
  .NET 10 SDK, JDK, Node.js or Python 3).

## Run the whole app (Docker Compose)

1. From the repository root, build and start the stack:

    ```sh
    docker compose up --build        # add -d to run it in the background
    ```

    The first build is slow (eleven images). It starts the 11 application services plus Redis.

2. Navigate to <http://localhost:8080> to access the web frontend. Only the frontend port is
   published on the host.

3. After changing a service's code, rebuild and restart just that service:

    ```sh
    docker compose up --build -d <service>    # for example: frontend
    ```

4. Follow logs with `docker compose logs -f <service>`.

See the [README quickstart](../README.md#quickstart-docker-compose) for the service list and
troubleshooting, and the [live-smoke runbook](test/README.md) to check a run end to end.

## Build and test one service

Run these from the repository root. They are the same commands the quality gate uses
([`.claude/quality-gate.routes`](../.claude/quality-gate.routes)).

| Service | Build | Test |
| :------ | :---- | :--- |
| `frontend`, `checkoutservice`, `productcatalogservice`, `shippingservice` (Go) | `cd src/<service> && go build ./...` | `cd src/<service> && go test ./...` |
| `cartservice` (C#/.NET 10) | `dotnet build src/cartservice/cartservice.sln` | `dotnet test src/cartservice/` |
| `adservice` (Java/Gradle) | `cd src/adservice && bash gradlew --no-daemon assemble` | no unit tests |
| `currencyservice`, `paymentservice` (Node.js) | `node --check` on each `*.js` file | no test suite |
| `emailservice`, `recommendationservice`, `loadgenerator`, `shoppingassistantservice` (Python) | `python3 -m compileall -q src/<service>` | no test suite |

## Adding a new microservice

In general, the set of core microservices for Online Boutique is fairly complete and unlikely to change in the future, but it can be useful to add an additional optional microservice that can be deployed to complement the core services.

See the [Adding a new microservice](adding-new-microservice.md) guide for instructions on how to add a new microservice.

## Cleanup

Stop the stack with `docker compose down`. Add `-v` to also remove Redis's leftover anonymous
volume.
