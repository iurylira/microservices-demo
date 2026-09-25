# Adding a new microservice

This document outlines the steps required to add a new microservice to the Online Boutique application.

## 1. Create a new directory

Create a new directory for your microservice within the `src/` directory. The directory name should be the name of your microservice.

## 2. Add source code

Place your microservice's source code inside the newly created directory. The structure of this directory should follow the conventions of the existing microservices. For example, a Python-based service would include at minimum the following files:

- `README.md`: The service's description and documentation.
- `main.py`: The application's entry point.
- `requirements.in`: A list of Python dependencies.
- `Dockerfile`: To containerize the application.

Take a look at existing microservices for inspiration.

## 3. Create a Dockerfile

Create a `Dockerfile` in your microservice's directory. This file will define the steps to build a container image for your service.

Refer to this example and tweak based on your new service's needs: https://github.com/GoogleCloudPlatform/microservices-demo/blob/main/src/frontend/Dockerfile

## 4. Add the service to `docker-compose.yml`

Add a service entry for your microservice to the root [`docker-compose.yml`](../docker-compose.yml)
so it is built and started with the rest of the app. Follow the existing entries:

- `build.context: ./src/<your-service>` so Compose builds the image from your `Dockerfile`.
- `environment:` with the `PORT` it listens on and the `*_SERVICE_ADDR` of any service it calls
  (services reach each other by Compose service name, for example `productcatalogservice:3550`).
- `depends_on:` for the services it needs at startup.
- If an existing service calls your new one, add its address (for example
  `MY_SERVICE_ADDR: "myservice:8080"`) to that service's `environment:`.

Check the file with `docker compose config --quiet`, then run `docker compose up --build` and
verify the new service starts (`docker compose ps`, `docker compose logs <your-service>`).

## 5. Update the documentation

Finally, update the project's documentation to reflect the addition of your new microservice. This may include:

- Adding a section to the main `README.md` if the service introduces significant new functionality.
- Updating the architecture diagrams in the `docs/img` directory.
- Adding a new document in the `docs` directory if the service requires detailed explanation.
