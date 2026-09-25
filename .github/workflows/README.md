# GitHub Actions Workflows

This page describes the CI workflows for the Online Boutique app, which run in GitHub Actions.

## Infrastructure

The CI pipelines run on standard GitHub-hosted runners (Ubuntu). They need no cloud project,
cluster or secrets: they only build and unit-test the service code.

## Workflows

### Code Tests (pull requests) - [ci-pr.yaml](ci-pr.yaml)

Runs on every commit of every open pull request targeting `main` (changes that touch only
Markdown, `docs/` or `LICENSE` are skipped). The `code-tests` job runs:

1. Go unit tests for `shippingservice`, `productcatalogservice` and `frontend/validator`.
2. C# unit tests for `cartservice` (`dotnet test src/cartservice/`).

### Code Tests (main / release) - [ci-main.yaml](ci-main.yaml)

Runs the same `code-tests` job on every push to `main` or a `release/*` branch (Go unit tests for
`shippingservice` and `productcatalogservice`, and the `cartservice` C# unit tests).

To run the whole app end to end, use Docker Compose locally (`docker compose up --build`); see the
[live-smoke runbook](../../docs/test/README.md).
