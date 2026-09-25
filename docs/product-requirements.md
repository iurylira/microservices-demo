## Product Requirements

This document contains a list of requirements that every change made to this repository should meet.
Every change must:
1. Preserve the golden user journey of running the app locally.
1. Preserve the simplicity of demos.
1. Preserve the simplicity of the Docker Compose quickstart.

These requirements are about the default configuration of Online Boutique.
Changes that will violate any of these rules should not be built into the default configuration of Online Boutique.
Such changes should be opt-in only (off by default), and only if they align with the [purpose of Online Boutique](/docs/purpose.md).

### 1. Preserve the golden user journey of running the app locally

The following statement about Online Boutique should always be true:

> A user can run Online Boutique's default configuration on their own machine with `docker compose up --build`, without any cloud account or cloud service.

Being able to run Online Boutique with Docker alone ensures that Online Boutique is free and cloud-agnostic, and useful to developers who are new to microservices.

### 2. Preserve the simplicity of demos

New changes should not complicate the primary user journey showcased in live demos and tutorials.

Today, the primary user journey is as follows:
1. Visit Online Boutique on a web browser.
2. Select an item from the homepage and add the item to the cart.
3. The checkout form is pre-populated with placeholder data (e.g. the shipping address).
4. The user checks out and completes the order.

### 3. Preserve the simplicity of the Docker Compose quickstart

New changes should not add additional complexity in the [main Online Boutique quickstart](/README.md#quickstart-docker-compose).

In particular, new changes should not add extra required steps or additional required tools in that quickstart.

Ideally, extensions to Online Boutique's default functionality (such as a new microservice) should be optional, so that users opt into them rather than being required to run them.
