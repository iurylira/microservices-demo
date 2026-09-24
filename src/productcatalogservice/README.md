# productcatalogservice

Run the following command to restore dependencies to `vendor/` directory:

    go mod vendor

## Dynamic catalog reloading / artificial delay

This service has a "dynamic catalog reloading" feature that is purposefully
not well implemented. The goal of this feature is to allow you to modify the
`products.json` file and have the changes be picked up without having to
restart the service.

However, this feature is bugged: the catalog is actually reloaded on each
request, introducing a noticeable delay in the frontend. This delay will also
show up in profiling tools: the `parseCatalog` function will take more than 80%
of the CPU time.

You can trigger this feature (and the delay) by sending a `USR1` signal and
remove it (if needed) by sending a `USR2` signal:

```
# Trigger bug
docker compose kill -s USR1 productcatalogservice
# Remove bug
docker compose kill -s USR2 productcatalogservice
```

The server is the container's main process (exec-form `ENTRYPOINT`), so it receives the signal
directly; the container keeps running.

## Latency injection

This service has an `EXTRA_LATENCY` environment variable. This will inject a sleep for the specified [time.Duration](https://golang.org/pkg/time/#ParseDuration) on every call to
to the server.

For example, use `EXTRA_LATENCY="5.5s"` to sleep for 5.5 seconds on every request.
With Docker Compose, add it under `productcatalogservice.environment` in the root
`docker-compose.yml` and restart the service (`docker compose up -d productcatalogservice`).
