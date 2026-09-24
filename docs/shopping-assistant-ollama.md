# Shopping assistant with Ollama (local LLM)

This guide explains how to run `src/shoppingassistantservice` with a **local LLM served by
[Ollama](https://github.com/ollama/ollama)** and a **local Postgres + pgvector** vector store,
instead of Google Gemini and AlloyDB. When you finish, the assistant runs inside the root
[`docker-compose.yml`](../docker-compose.yml) with no Google services and no API keys.

> **Status: this is a plan, not shipped code.** Nothing in this guide is implemented yet. Today
> the assistant is still the Gemini + AlloyDB version and is **not** part of the Compose stack
> (see [Architecture](architecture.md)). Do this work later as its own unit, through the dev-kit
> pipeline (research → tests → plan → execute → docs, see [docs/work/README.md](work/README.md)),
> on its own `work/NNN-<slug>` branch. The code and YAML below are **illustrative**. They are
> based on the current source, but they have not been built or run. Check the library versions
> again when you do the work.

Contents:

1. [How the assistant works today](#1-how-the-assistant-works-today)
2. [Target design](#2-target-design)
3. [Step by step](#3-step-by-step)
4. [Hardware, model sizing and performance](#4-hardware-model-sizing-and-performance)
5. [Check it end to end](#5-check-it-end-to-end)
6. [Troubleshooting](#6-troubleshooting)
7. [Alternative: any OpenAI-compatible local server](#7-alternative-any-openai-compatible-local-server)
8. [Notes for the follow-up unit](#8-notes-for-the-follow-up-unit)
9. [Sources](#9-sources)

---

## 1. How the assistant works today

### 1.1 The HTTP contract (keep this unchanged)

The browser never calls the assistant directly. The chain is:

1. [`src/frontend/templates/assistant.html`](../src/frontend/templates/assistant.html) reads an
   optional uploaded image as a **data URL** (`FileReader.readAsDataURL`, so the value looks like
   `data:image/jpeg;base64,...`). It then sends
   `POST {baseUrl}/bot` with the JSON body `{"message": "<text>", "image": "<data URL>"}`. If the
   user uploads no image, `image` is `undefined`, so `JSON.stringify` **leaves the key out**.
2. `chatBotHandler` in [`src/frontend/handlers.go`](../src/frontend/handlers.go) forwards the
   request body **unchanged** to `POST http://$SHOPPING_ASSISTANT_SERVICE_ADDR/`. It reads the
   JSON reply as `{"content": "<text>"}` (a `details` field is also declared but not used). It
   returns `{"message": <content>}` to the browser. It uses `http.DefaultClient`, which has **no
   timeout**, so slow local inference does not break the call.
3. The page looks for product IDs in the reply with the regex `\[([a-zA-Z0-9-]+)\]`. For each ID
   it calls `GET /product-meta/<id>` and shows a product card. It also cuts the displayed text at
   the first line that starts with `-`, `*` or a digit (`/\n+[-*\d][\S\s]*/`).

So the service must:

- listen on HTTP, on port `8080` (as in the [Dockerfile](../src/shoppingassistantservice/Dockerfile));
- accept `POST /` with `{"message": str, "image"?: str}` (`message` is URL-decoded with `unquote`);
- return `{"content": str}`, where the text ends with product IDs written as
  `[ID1], [ID2], [ID3]`. The IDs must be real IDs from
  [`products.json`](../src/productcatalogservice/products.json).

The frontend side needs two settings:

- `SHOPPING_ASSISTANT_SERVICE_ADDR` is **required**. `main.go` calls `mustMapEnv` and stops if it
  is missing. Compose already sets a placeholder value, `shoppingassistantservice:80`.
- `ENABLE_ASSISTANT=true` shows the wand icon in the header (`assistant_enabled` in
  `header.html`). The `/assistant` and `/bot` routes are always registered, whatever this flag
  says.

### 1.2 The RAG pipeline in `shoppingassistantservice.py`

[`shoppingassistantservice.py`](../src/shoppingassistantservice/shoppingassistantservice.py)
runs three steps per request:

1. **Describe the room.** It sends the text prompt *"You are a professional interior designer…"*
   plus `{"type": "image_url", "image_url": request.json['image']}` to
   `ChatGoogleGenerativeAI(model="gemini-1.5-flash")`.
2. **Vector search.** It runs `similarity_search` on an `AlloyDBVectorStore` with the user prompt
   and the room description. The query is embedded with
   `GoogleGenerativeAIEmbeddings(model="models/embedding-001")`. The table uses `id_column="id"`,
   `content_column="description"`, `embedding_column="product_embedding"` and
   `metadata_columns=["id","name","categories"]`.
3. **Write the answer.** It builds a design prompt from the room description, the retrieved
   documents (`doc.to_json()`) and the user request. The prompt asks for the IDs of the top 3
   products in the format `[<id>], [<id>], [<id>]`. It sends this to Gemini again and returns
   `{'content': design_response.content}`.

Other Google dependencies:

- **Secret Manager** holds the AlloyDB password (`secretmanager_v1`, `ALLOYDB_SECRET_NAME`).
- **Required env vars:** `PROJECT_ID`, `REGION`, `ALLOYDB_*` and `GOOGLE_API_KEY` (set by the
  upstream deploy manifest, removed from this repo; last present at commit `9b5c94a`).
- **[`requirements.in`](../src/shoppingassistantservice/requirements.in):**
  `langchain-google-genai`, `langchain-google-alloydb-pg`, `google-cloud-secret-manager`.
- **How the vector table was filled.** Two upstream seeding scripts (a shell script and a Python
  SQL generator, removed from this repo with the deploy assets; last present at commit `9b5c94a`)
  created `products.catalog_items (id, name, description, picture, price_usd_*, categories,
  product_embedding VECTOR(768), embed_model)`, inserted one row for each product in
  `products.json`, and then computed the embeddings **inside AlloyDB** with
  `embedding('textembedding-gecko@003', description)`.

  > Side note: the rows are embedded with `textembedding-gecko@003`, but queries are embedded
  > with `models/embedding-001`. The new design uses **one** `EMBEDDING_MODEL` for both the seed
  > and the queries. Vectors from two different models cannot be compared in a meaningful way.

```mermaid
flowchart LR
  B[Browser<br/>assistant.html] -- "POST /bot<br/>{message, image}" --> F[frontend<br/>chatBotHandler]
  F -- "POST /<br/>same body" --> S[shoppingassistantservice<br/>Flask :8080]
  S -- "1. describe room<br/>(image + text)" --> G[(Gemini API<br/>gemini-1.5-flash)]
  S -- "2. similarity_search<br/>(embedding-001)" --> A[(AlloyDB<br/>catalog_items + pgvector)]
  S -- "3. design prompt" --> G
  S -. "password" .-> SM[(Secret Manager)]
  S -- "{content}" --> F
  F -- "{message}" --> B
  B -- "GET /product-meta/ID" --> F
```

### 1.3 What must change

| Today | Replace with |
| :---- | :----------- |
| `ChatGoogleGenerativeAI` (Gemini, vision) | `ChatOllama` (`langchain-ollama`) with a vision-capable model |
| `GoogleGenerativeAIEmbeddings` | `OllamaEmbeddings` (for example `nomic-embed-text`) |
| `AlloyDBEngine` / `AlloyDBVectorStore` | `PGEngine` / `PGVectorStore` (`langchain-postgres`) on `pgvector/pgvector` |
| Secret Manager password | `DATABASE_URL` env var (local only) |
| AlloyDB `embedding()` SQL plus shell scripts | a Python seed script that embeds `products.json` with the same `EMBEDDING_MODEL` |
| No local runtime (upstream cloud-only deploy) | new services in the root `docker-compose.yml` |

The HTTP contract in [section 1.1](#11-the-http-contract-keep-this-unchanged) and the three-step
prompt flow **stay the same**.

---

## 2. Target design

```mermaid
flowchart LR
  B[Browser] -- "POST /bot" --> F[frontend]
  F -- "POST /" --> S[shoppingassistantservice<br/>Flask :8080]
  S -- "1. describe room<br/>VISION_MODEL" --> O[(ollama<br/>:11434)]
  S -- "2. embed query<br/>EMBEDDING_MODEL" --> O
  S -- "2. cosine search" --> P[(vectordb<br/>pgvector/pgvector)]
  S -- "3. answer<br/>LLM_MODEL" --> O
  subgraph one-shot jobs
    PULL[ollama-pull<br/>ollama pull models] --> O
    SEED[assistant-seed<br/>seed_products.py] -- "embed products.json" --> O
    SEED -- "insert rows" --> P
  end
```

New or changed Compose services:

| Service | Image | Role |
| :------ | :---- | :--- |
| `ollama` | `ollama/ollama` | Model server on port 11434. Models are kept in a named volume. GPU is optional. |
| `ollama-pull` | `ollama/ollama` (CLI only) | One-shot job. Runs `ollama pull` for the chat, vision and embedding models against the `ollama` server, then exits `0`. |
| `vectordb` | `pgvector/pgvector` | Postgres with the `vector` extension. |
| `assistant-seed` | built from `src/shoppingassistantservice` | One-shot job. Reads `products.json`, embeds each description with `EMBEDDING_MODEL`, and (re)creates the `catalog_items` table. |
| `shoppingassistantservice` | built from `src/shoppingassistantservice` | The Flask service. It uses `ChatOllama`, `OllamaEmbeddings` and `PGVectorStore`. |
| `frontend` (changed) | — | Set `SHOPPING_ASSISTANT_SERVICE_ADDR=shoppingassistantservice:8080` and `ENABLE_ASSISTANT=true`. |

### 2.1 Configuration (the "any model" switch)

Every model name is an environment variable, so you can switch models without changing code:

| Variable | Used by | Default (suggested) | Meaning |
| :------- | :------ | :------------------ | :------ |
| `OLLAMA_BASE_URL` | service, seed | `http://ollama:11434` | Ollama server URL. Passed as `base_url` to `ChatOllama` and `OllamaEmbeddings`. |
| `LLM_MODEL` | service | `llava:7b` | Model that writes the final recommendation (step 3). It can be any chat model. |
| `VISION_MODEL` | service | same as `LLM_MODEL` | Model that describes the room image (step 1). It **must** be able to read images. Set it to `none` to skip the image step and use a text-only `LLM_MODEL`. |
| `EMBEDDING_MODEL` | service, seed | `nomic-embed-text` | Embedding model. It **must be the same** for the seed and the service. |
| `DATABASE_URL` | service, seed | `postgresql+psycopg://postgres:postgres@vectordb:5432/products` | SQLAlchemy **async-capable** URL for `PGEngine`. `psycopg` 3 supports async. |
| `VECTOR_TABLE` | service, seed | `catalog_items` | Table name. It replaces `ALLOYDB_TABLE_NAME`. |

With Compose variable interpolation (`${LLM_MODEL:-llava:7b}`), switching the model is one
command:

```sh
LLM_MODEL=llama3.2-vision:11b docker compose up --build
# or pin it in a .env file next to docker-compose.yml:
#   LLM_MODEL=qwen2.5vl:7b
#   EMBEDDING_MODEL=nomic-embed-text
```

`ollama-pull` reads the same variables, so the model you choose is downloaded before the
service starts.

**Vision vs text-only models.** The assistant is built around a *room photo*. Step 1 needs a
multimodal model. Examples from the Ollama library: `llava`, `llama3.2-vision`, `qwen2.5vl`,
`gemma3` (check the exact tags at <https://ollama.com/library>, unverified from here). If you
want a text-only model (for example `llama3.2`, `mistral`, `qwen2.5`) you have two options:

- **Split the roles:** `VISION_MODEL=llava:7b` and `LLM_MODEL=qwen2.5:7b`. A small vision model
  describes the room, and a stronger text model writes the answer. Ollama loads both models; see
  `OLLAMA_MAX_LOADED_MODELS` in [section 4](#4-hardware-model-sizing-and-performance).
- **No vision:** `VISION_MODEL=none`. The service skips step 1 and searches with the user's text
  only. The image is ignored, and the answer says so.

---

## 3. Step by step

### Step 1 — Compose additions

Add the following to the root [`docker-compose.yml`](../docker-compose.yml). This is
illustrative. Pin image tags, and ideally digests, the same way `redis` is pinned today. The tags
below were current when this guide was written: `ollama/ollama` `0.34.3` and `pgvector/pgvector`
`0.8.6-pg17-trixie`. Check them again before use.

```yaml
services:
  # ... existing services ...

  frontend:
    # ... existing keys ...
    environment:
      # ... existing vars ...
      SHOPPING_ASSISTANT_SERVICE_ADDR: "shoppingassistantservice:8080"  # was the :80 placeholder
      ENABLE_ASSISTANT: "true"                                          # shows the wand icon

  ollama:
    image: ollama/ollama:0.34.3
    volumes:
      - ollama-models:/root/.ollama          # model cache survives `docker compose down`
    environment:
      OLLAMA_KEEP_ALIVE: "30m"               # keep models loaded between chats (default 5m)
      # OLLAMA_CONTEXT_LENGTH: "8192"        # default context is 4096 tokens
    # ports: ["11434:11434"]                 # optional: expose to the host for debugging
    healthcheck:
      test: ["CMD", "ollama", "list"]        # the CLI talks to the local server
      interval: 10s
      timeout: 5s
      retries: 30
    # --- optional NVIDIA GPU (needs the NVIDIA Container Toolkit on the host) ---
    # deploy:
    #   resources:
    #     reservations:
    #       devices:
    #         - driver: nvidia
    #           count: all
    #           capabilities: [gpu]
    # --- AMD GPU: use image ollama/ollama:0.34.3-rocm (or :rocm) plus ---
    # devices: ["/dev/kfd", "/dev/dri"]

  ollama-pull:                               # one-shot: download the models, then exit 0
    image: ollama/ollama:0.34.3
    environment:
      OLLAMA_HOST: "ollama:11434"            # point the CLI at the server container
    entrypoint: ["/bin/sh", "-c"]
    command:
      - >-
        ollama pull ${LLM_MODEL:-llava:7b} &&
        ollama pull ${VISION_MODEL:-${LLM_MODEL:-llava:7b}} &&
        ollama pull ${EMBEDDING_MODEL:-nomic-embed-text}
    depends_on:
      ollama:
        condition: service_healthy

  vectordb:
    image: pgvector/pgvector:0.8.6-pg17-trixie
    environment:
      POSTGRES_USER: "postgres"
      POSTGRES_PASSWORD: "postgres"          # local demo only
      POSTGRES_DB: "products"
    # No volume on purpose: the seed rebuilds the table on every `up` (9 products, a few seconds).
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U postgres -d products"]
      interval: 5s
      timeout: 3s
      retries: 20

  assistant-seed:                            # one-shot: embed products.json into vectordb
    build:
      context: ./src/shoppingassistantservice
    entrypoint: ["python", "seed_products.py"]
    environment: &assistant-env
      OLLAMA_BASE_URL: "http://ollama:11434"
      LLM_MODEL: "${LLM_MODEL:-llava:7b}"
      VISION_MODEL: "${VISION_MODEL:-${LLM_MODEL:-llava:7b}}"
      EMBEDDING_MODEL: "${EMBEDDING_MODEL:-nomic-embed-text}"
      DATABASE_URL: "postgresql+psycopg://postgres:postgres@vectordb:5432/products"
      VECTOR_TABLE: "catalog_items"
      PRODUCTS_JSON: "/data/products.json"
    volumes:
      - ./src/productcatalogservice/products.json:/data/products.json:ro   # single source of truth
    depends_on:
      vectordb:
        condition: service_healthy
      ollama-pull:
        condition: service_completed_successfully

  shoppingassistantservice:
    build:
      context: ./src/shoppingassistantservice
    environment:
      <<: *assistant-env
      PORT: "8080"
    depends_on:
      assistant-seed:
        condition: service_completed_successfully

volumes:
  ollama-models:
```

Notes:

- **Why `ollama-pull` is a separate service.** The official image only runs `ollama serve`, and
  the Ollama Docker docs pull models with `docker exec … ollama run/pull`. A one-shot container
  that runs the same CLI against the server (through `OLLAMA_HOST`) does this automatically.
  `service_completed_successfully` then makes the seed and the service wait for the download.
  Downloads are cached in the `ollama-models` volume, so later runs are fast.
- **Why the seed mounts `products.json`.** Mounting the catalog file (instead of copying it into
  the image) keeps [`src/productcatalogservice/products.json`](../src/productcatalogservice/products.json)
  as the single source of truth (DRY).
- The frontend needs **no** `depends_on` on the assistant. It only reads the address at startup
  and calls the service when a user chats.
- `ollama list` as a healthcheck assumes the image's CLI and default `OLLAMA_HOST` reach the
  server inside the container (unverified; `curl` may not be in the image).
- The YAML anchor `&assistant-env` plus `<<: *assistant-env` keeps a single copy of the
  environment for the seed and the service. If you prefer, write the variables out twice.
- `docker compose up` with no profile will start Ollama and download several GB. If the assistant
  should be opt-in, put the five new services under `profiles: ["assistant"]` and start them with
  `docker compose --profile assistant up`. In that case, keep the frontend's placeholder address
  and `ENABLE_ASSISTANT` unset when the profile is off.

### Step 2 — `requirements.in`

Replace the Google packages. Current file:

```text
flask==3.1.3
langchain-google-genai==4.1.2
langchain==1.2.0
pillow==12.1.1
langchain-google-alloydb-pg==0.13.0
google-cloud-secret-manager==2.26.0
```

Target (illustrative; versions are the latest on PyPI when this was written):

```text
flask==3.1.3
langchain-ollama==1.1.0        # ChatOllama, OllamaEmbeddings (pulls in langchain-core + ollama)
langchain-postgres==0.0.18     # PGEngine, PGVectorStore (pulls in psycopg[binary], asyncpg, pgvector, sqlalchemy)
pillow==12.1.1                 # only if you keep it; the new code does not import it
```

- `langchain` itself is not imported (only `langchain_core.messages`). `langchain-core` comes in
  through `langchain-ollama`, so you can drop `langchain` (YAGNI).
- Regenerate the lock file the same way as the header of
  [`requirements.txt`](../src/shoppingassistantservice/requirements.txt):
  `uv pip compile requirements.in -o requirements.txt`.
- The Dockerfile uses `python:3.14.6-slim`. `psycopg-binary` 3.3.6, `asyncpg` 0.31.0 and `numpy`
  2.5.3 publish `cp314` wheels on PyPI, and `ollama` is pure Python, so no new build tools are
  needed.

### Step 3 — code changes in `shoppingassistantservice.py`

Illustrative rewrite. It keeps the Flask app, the route, the three prompts and the response shape,
and changes only the model and store clients. The comments tie each part to the current code.

```python
import os
from urllib.parse import unquote

from flask import Flask, request
from langchain_core.messages import HumanMessage
from langchain_ollama import ChatOllama, OllamaEmbeddings
from langchain_postgres import PGEngine, PGVectorStore

OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://ollama:11434")
LLM_MODEL = os.environ["LLM_MODEL"]
VISION_MODEL = os.environ.get("VISION_MODEL") or LLM_MODEL          # "none" disables step 1
EMBEDDING_MODEL = os.environ["EMBEDDING_MODEL"]
DATABASE_URL = os.environ["DATABASE_URL"]                           # replaces Secret Manager + ALLOYDB_*
VECTOR_TABLE = os.environ.get("VECTOR_TABLE", "catalog_items")

# Replaces AlloyDBEngine.from_instance(...) + AlloyDBVectorStore.create_sync(...)
engine = PGEngine.from_connection_string(url=DATABASE_URL)
vectorstore = PGVectorStore.create_sync(
    engine=engine,
    table_name=VECTOR_TABLE,
    embedding_service=OllamaEmbeddings(model=EMBEDDING_MODEL, base_url=OLLAMA_BASE_URL),
    id_column="id",
    content_column="description",
    embedding_column="product_embedding",
    metadata_columns=["name", "categories"],   # "id" is the id_column; do not list it twice
)

llm = ChatOllama(model=LLM_MODEL, base_url=OLLAMA_BASE_URL, temperature=0.2)
llm_vision = None if VISION_MODEL == "none" else ChatOllama(
    model=VISION_MODEL, base_url=OLLAMA_BASE_URL, temperature=0.2)


def describe_room(image):
    """Step 1. Returns a room description, or '' when there is no image or no vision model."""
    if not image or llm_vision is None:
        return ""
    message = HumanMessage(content=[
        {"type": "text",
         "text": "You are a professional interior designer, give me a detailed decsription "
                 "of the style of the room in this image"},
        # The frontend sends a data URL ("data:image/...;base64,...").
        # ChatOllama strips the "data:...," prefix and sends the base64 part to Ollama.
        {"type": "image_url", "image_url": {"url": image}},
    ])
    return llm_vision.invoke([message]).content


def create_app():
    app = Flask(__name__)

    @app.route("/", methods=["POST"])
    def talk_to_llm():
        prompt = unquote(request.json["message"])
        description_response = describe_room(request.json.get("image"))  # key may be missing

        # Step 2 – similarity search (same prompt as today)
        vector_search_prompt = (
            f" This is the user's request: {prompt} Find the most relevant items for that prompt,"
            f" while matching style of the room described here: {description_response} ")
        docs = vectorstore.similarity_search(vector_search_prompt)

        # PGVectorStore puts the id column in Document.id (not in metadata), so write it out
        # explicitly. The LLM needs the real IDs to produce "[ID]" markers.
        relevant_docs = ", ".join(
            f"{{id: {d.id}, name: {d.metadata.get('name')}, "
            f"categories: {d.metadata.get('categories')}, description: {d.page_content}}}"
            for d in docs)

        # Step 3 – the design_prompt text is unchanged from the current file
        design_prompt = (
            f" You are an interior designer that works for Online Boutique. ... "
            f"{description_response} Here are a list of products that are relevant to it: "
            f"{relevant_docs} ... [<first product ID>], [<second product ID>], [<third product ID>] ")
        design_response = llm.invoke(design_prompt)
        return {"content": design_response.content}

    return app


if __name__ == "__main__":
    create_app().run(host="0.0.0.0", port=int(os.environ.get("PORT", "8080")))
```

Key points:

- **Image block format.** The current code passes `"image_url": <string>`. `ChatOllama` accepts
  both a string and `{"url": <string>}`. For a `data:` URL it splits on `,` and sends the base64
  part as an Ollama `images` entry. Use the dict form, because it also works with `ChatOpenAI`
  (see [section 7](#7-alternative-any-openai-compatible-local-server)).
- **Missing image.** Today `request.json['image']` raises `KeyError` when the user sends no
  picture, and the frontend then returns a 500 error. `request.json.get("image")` together with
  `describe_room` fixes that. This is a small behaviour change, so give it its own test in the
  follow-up unit.
- **`metadata_columns`.** `PGVectorStore` inserts `id_column` and each metadata column as
  separate columns. Listing `"id"` in both places would repeat it, so leave it out of the
  metadata list. The ID comes back as `Document.id`.
- **Distance.** The default `PGVectorStore` strategy is cosine distance (`<=>`). That is a good
  default for text embeddings.
- The module still connects at import time, as the AlloyDB code does, so the table must exist
  before the service starts. The `assistant-seed` dependency ensures this.
- Leaving out `num_ctx` means Ollama uses its default of 4096 tokens. The design prompt plus 4
  short product descriptions fit easily. Raise it (`ChatOllama(num_ctx=8192)` or
  `OLLAMA_CONTEXT_LENGTH`) only if replies are cut off.

### Step 4 — the seed script (`src/shoppingassistantservice/seed_products.py`)

This replaces `generate_sql_from_products.py` and the SQL `embedding()` call. It computes the
embeddings in the app with the **same** `EMBEDDING_MODEL` the service uses. Illustrative:

```python
"""Embed products.json into the pgvector table used by shoppingassistantservice."""
import json
import os

from langchain_core.documents import Document
from langchain_ollama import OllamaEmbeddings
from langchain_postgres import Column, PGEngine, PGVectorStore

TABLE = os.environ.get("VECTOR_TABLE", "catalog_items")
embeddings = OllamaEmbeddings(model=os.environ["EMBEDDING_MODEL"],
                              base_url=os.environ.get("OLLAMA_BASE_URL", "http://ollama:11434"))
engine = PGEngine.from_connection_string(url=os.environ["DATABASE_URL"])

with open(os.environ.get("PRODUCTS_JSON", "/data/products.json")) as f:
    products = json.load(f)["products"]

# Ask the model for its vector size instead of hard-coding 768, so any embedding model works.
vector_size = len(embeddings.embed_query("dimension probe"))

# (Re)create the table. This also runs CREATE EXTENSION IF NOT EXISTS vector.
# overwrite_existing=True makes re-seeding safe after you change EMBEDDING_MODEL.
engine.init_vectorstore_table(
    table_name=TABLE,
    vector_size=vector_size,
    id_column=Column("id", "TEXT", nullable=False),   # product IDs are not UUIDs
    content_column="description",
    embedding_column="product_embedding",
    metadata_columns=[Column("name", "TEXT"), Column("categories", "TEXT")],
    overwrite_existing=True,
)

store = PGVectorStore.create_sync(
    engine=engine, table_name=TABLE, embedding_service=embeddings,
    id_column="id", content_column="description", embedding_column="product_embedding",
    metadata_columns=["name", "categories"],
)
store.add_documents(
    [Document(page_content=p["description"],
              metadata={"name": p["name"], "categories": ",".join(p["categories"])})
     for p in products],
    ids=[p["id"] for p in products],
)
print(f"Seeded {len(products)} products into {TABLE} (dim={vector_size}).")
```

- It uses the same table and column names as the AlloyDB version (`catalog_items`, `id`,
  `description`, `product_embedding`, `name`, `categories`). Price and picture columns are not
  needed: the frontend fetches product cards from the catalog service through
  `/product-meta/<id>`.
- Retrieval quality tip: embedding `f"{name}. {description}"` instead of `description` alone
  usually helps with a catalog this small. That changes behaviour, so decide it in the unit's
  research step.
- The seed runs on every `docker compose up`. It is idempotent: it drops the table, recreates it
  and inserts again.

### Step 5 — Dockerfile

The current [Dockerfile](../src/shoppingassistantservice/Dockerfile) already fits:

- `COPY . .` includes `seed_products.py`. Compose overrides the `entrypoint` for
  `assistant-seed`, so one image serves both roles.
- The `g++` builder stage is probably no longer needed, because all new dependencies ship wheels.
  Removing it is optional cleanup; keep the change surgical.
- `ENV PORT="8080"` / `EXPOSE 8080` are unchanged. The new `__main__` reads `PORT`.

### Step 6 — enable the frontend

In `docker-compose.yml`, on the `frontend` service:

```yaml
SHOPPING_ASSISTANT_SERVICE_ADDR: "shoppingassistantservice:8080"   # host:port, no scheme; the handler adds http://
ENABLE_ASSISTANT: "true"
```

Remove the comment that says the assistant is not deployed, and the header comment at the top of
the file that says the same.

---

## 4. Hardware, model sizing and performance

The figures below are **rough rules of thumb** for 4-bit quantized models (Ollama's default
tags). They are not measured in this repo, and the model pages on ollama.com could not be reached
while writing this, so treat them as unverified. `ollama list` shows each model's real download
size after you pull it.

| Setup | Suggested models | Memory for the models | Expect |
| :---- | :--------------- | :-------------------- | :----- |
| Laptop, CPU only, 16 GB RAM | `llava:7b` (or a smaller vision model) + `nomic-embed-text` | ~5–6 GB | tens of seconds to a few minutes per answer |
| CPU, 32 GB RAM | `llava:7b` for vision + a 7–8B text model for `LLM_MODEL` | ~10–12 GB | slow but usable for demos |
| NVIDIA GPU, 8 GB VRAM | 7B vision model | fits in VRAM | a few seconds per answer |
| NVIDIA GPU, 12–16 GB VRAM | `llama3.2-vision:11b` / `qwen2.5vl:7b` | fits in VRAM | better room descriptions and answers |

Add roughly 2 GB for the rest of the Online Boutique stack. Embedding models such as
`nomic-embed-text` are small (a few hundred MB).

Hardware notes:

- **GPU in Docker.** NVIDIA needs the NVIDIA Container Toolkit on the host, plus the `deploy`
  block in the YAML above. Ollama supports NVIDIA GPUs with compute capability 5.0 or higher
  (driver 550 or newer). AMD uses the `:rocm` image tag with `/dev/kfd` and `/dev/dri`. **Docker
  Desktop on macOS has no GPU passthrough.** On a Mac, run Ollama natively (it uses Metal) and
  point the containers at it with `OLLAMA_BASE_URL=http://host.docker.internal:11434`. In that
  case, remove the `ollama` / `ollama-pull` services and run `ollama pull` on the host.
- **Check that the GPU is used.** Run `docker compose exec ollama ollama ps`. The `PROCESSOR`
  column shows GPU vs CPU.

Performance tips:

- **Keep models loaded.** Set `OLLAMA_KEEP_ALIVE` (the default is 5 minutes) so the first chat
  after a pause does not pay the load time again.
- **Two models loaded at once.** `OLLAMA_MAX_LOADED_MODELS` defaults to 3 on CPU. RAM grows with
  `OLLAMA_NUM_PARALLEL` × context length, so leave `OLLAMA_NUM_PARALLEL` at 1 on small machines.
- **Warm-up.** The first request loads the model from disk. Send one warm-up request after `up`
  (see [section 5](#5-check-it-end-to-end)).
- **Image size.** Large phone photos become large base64 payloads and more image tokens. Resize
  them to about 1024 px in the browser or the service if latency matters.
- **Smaller or split models.** `VISION_MODEL` can be a small vision model, and `LLM_MODEL` a
  stronger text model.

---

## 5. Check it end to end

1. **Start the stack** and watch the one-shot jobs finish:
   ```sh
   docker compose up --build -d
   docker compose logs -f ollama-pull assistant-seed   # expect "Seeded 9 products ..." and exit 0
   docker compose ps -a                                # ollama-pull / assistant-seed: Exited (0)
   ```
2. **Models are present:**
   ```sh
   docker compose exec ollama ollama list
   ```
3. **The vector table is filled** (9 products in the current `products.json`):
   ```sh
   docker compose exec vectordb psql -U postgres -d products \
     -c "SELECT id, name, vector_dims(product_embedding) FROM catalog_items;"
   ```
4. **Call the service through the frontend** (text only):
   ```sh
   curl -s http://localhost:8080/bot -H 'Content-Type: application/json' \
     -d '{"message":"I need something to decorate my kitchen"}'
   # -> {"message":"... [9SIQT8TOJO], [...], [...]"}
   ```
5. **With a room photo** (the same data-URL shape the browser sends):
   ```sh
   IMG="data:image/jpeg;base64,$(base64 -w0 room.jpg)"   # macOS: base64 -i room.jpg
   printf '{"message":"what fits this room?","image":"%s"}' "$IMG" > /tmp/req.json
   curl -s http://localhost:8080/bot -H 'Content-Type: application/json' -d @/tmp/req.json
   ```
6. **In the browser.** Open <http://localhost:8080>, click the wand icon (`/assistant`), upload a
   room photo, type a request, and check that product cards appear under the answer. Those cards
   come from the `[ID]` markers.
7. **No Google traffic.** `docker compose logs shoppingassistantservice` shows only
   `ollama:11434` and `vectordb` activity. A grep of the service for the repo's Google pattern
   (see [section 8](#8-notes-for-the-follow-up-unit)) returns nothing.

---

## 6. Troubleshooting

| Symptom | Likely cause / fix |
| :------ | :----------------- |
| Frontend returns 500 `failed to unmarshal body` on `/bot` | The assistant returned a non-JSON error page (a Flask 500). Run `docker compose logs shoppingassistantservice`. The frontend does not check the status code. |
| Service exits at start with `Id column, id, does not exist` / table errors | The seed did not run or failed. Check `docker compose logs assistant-seed`, then re-run `docker compose up assistant-seed`. |
| `model "…" not found, try pulling it first` | `ollama-pull` failed, or the model name or tag is wrong. Run `docker compose exec ollama ollama pull <model>` and check the tag in the Ollama library. |
| `expected N dimensions, not M` from pgvector | `EMBEDDING_MODEL` changed after seeding, or the seed and the service use different values. Use the same value in both and re-run the seed (it recreates the table). |
| Answer ignores the photo, or the model says it cannot see images | `VISION_MODEL` is text-only. Use a vision model, or set `VISION_MODEL=none` on purpose. |
| No product cards under the answer | The model did not output `[ID]` markers, or it made up IDs. Lower `temperature`, use a larger model, or state in the prompt that it must copy IDs exactly from the list. Remember that the page removes everything after the first line that starts with `-`, `*` or a digit. |
| Very slow first reply | The model is loading from disk. Warm it up, and raise `OLLAMA_KEEP_ALIVE`. |
| Very slow every reply | Inference is running on the CPU. Check `ollama ps`, enable the GPU, or use smaller models. |
| Ollama killed or OOM | The model is too big for RAM/VRAM. Use a smaller tag, lower `OLLAMA_NUM_PARALLEL` / context length, or raise Docker Desktop's memory limit. |
| `ollama-pull` hangs or fails behind a corporate proxy | Set `HTTPS_PROXY` on the `ollama` service. The server does the download, not the CLI. |
| GPU not used in Docker | Install the NVIDIA Container Toolkit, run `nvidia-ctk runtime configure --runtime=docker`, restart Docker, and uncomment the `deploy` block. |

---

## 7. Alternative: any OpenAI-compatible local server

Ollama also serves an **OpenAI-compatible API** under `/v1` (`/v1/chat/completions` with
`image_url` content parts, and `/v1/embeddings`). If the service talks to that API instead of the
native one, the same code works with **any** OpenAI-compatible local server: Ollama, LM Studio,
vLLM, the llama.cpp server, LocalAI, and others. You only change a URL.

Changes compared with [Step 3](#step-3--code-changes-in-shoppingassistantservicepy):

```text
# requirements.in
langchain-openai==1.6.5      # instead of langchain-ollama
```

```python
from langchain_openai import ChatOpenAI, OpenAIEmbeddings

BASE = os.environ["OPENAI_BASE_URL"]          # e.g. http://ollama:11434/v1  or  http://lmstudio:1234/v1
KEY = os.environ.get("OPENAI_API_KEY", "local")   # required by the client; Ollama ignores it

llm = ChatOpenAI(model=LLM_MODEL, base_url=BASE, api_key=KEY, temperature=0.2)
llm_vision = ChatOpenAI(model=VISION_MODEL, base_url=BASE, api_key=KEY)
embeddings = OpenAIEmbeddings(
    model=EMBEDDING_MODEL, base_url=BASE, api_key=KEY,
    check_embedding_ctx_length=False,   # send raw text; most non-OpenAI servers reject token arrays
)
# The image block stays {"type": "image_url", "image_url": {"url": image}} — that is the OpenAI format.
```

Trade-offs:

- **Pros:** you can swap the server freely, and the same client works with a hosted
  OpenAI-compatible provider later.
- **Cons:** Ollama-only options (`num_ctx`, `keep_alive`) are not available per request through
  `/v1`, so set them on the server with `OLLAMA_CONTEXT_LENGTH` / `OLLAMA_KEEP_ALIVE`. Vision
  support depends on the server and the model. Each server has its own way to download models,
  so the `ollama-pull` job only applies to Ollama.

---

## 8. Notes for the follow-up unit

- **This removes Google from the last service.** After this change, `shoppingassistantservice`
  no longer uses `langchain-google-genai`, `langchain-google-alloydb-pg`,
  `google-cloud-secret-manager`, `PROJECT_ID` or `REGION`. Unit 001's "no Google" check
  ([`docs/work/001-no-google-docker-compose/2-tests.md`](work/001-no-google-docker-compose/2-tests.md),
  `GOOGLE_PATTERN`) currently skips this directory with `--exclude-dir=shoppingassistantservice`.
  The follow-up unit can drop that exclusion and run the grep over the whole of `src/`.
- **The Gemini code path.** The upstream cloud deploy assets for the Gemini version were removed
  from this repo, so nothing deploys it any more. The unit's research step must decide whether to
  drop the Gemini code or keep it behind a switch.
- **Run it through dev-kit.** research (decide on the Compose profile, the default models, and
  the missing-image behaviour) → tests (Given-When-Then for the HTTP contract, the seed, and the
  text-only path) → plan → execute (the `coder` writes the code; `e2e-tester` runs
  [section 5](#5-check-it-end-to-end)) → docs (update `README.md`, `docs/architecture.md`,
  `CLAUDE.md` and this page).
- **Quality gate.** The route for `src/shoppingassistantservice/` is
  `python3 -m compileall -q src/shoppingassistantservice`. A real smoke test needs the live stack
  and pulled models (several GB), so plan the e2e evidence for that.

---

## 9. Sources

Repository files read for this guide:
`src/shoppingassistantservice/{shoppingassistantservice.py,requirements.in,requirements.txt,Dockerfile}`,
`src/frontend/{main.go,handlers.go,templates/assistant.html,templates/header.html}`,
`docker-compose.yml`, the upstream shopping-assistant deploy manifest and seeding scripts (removed; see commit `9b5c94a`),
`src/productcatalogservice/products.json`, `docs/work/001-no-google-docker-compose/2-tests.md`.

External sources (fetched 2026-09-23 unless marked):

- Ollama Docker image, CPU/NVIDIA/AMD run commands, NVIDIA Container Toolkit steps:
  <https://github.com/ollama/ollama/blob/main/docs/docker.mdx>
- Ollama REST API (`/api/chat` with `images`, `/api/embed`, `/api/embeddings` superseded,
  `/api/pull`, `/api/tags`, `keep_alive`): <https://github.com/ollama/ollama/blob/main/docs/api.md>
  (the page notes the docs are moving to <https://docs.ollama.com/api>)
- Ollama FAQ (default context 4096 and `OLLAMA_CONTEXT_LENGTH`, `OLLAMA_KEEP_ALIVE`,
  `OLLAMA_MAX_LOADED_MODELS`, `OLLAMA_NUM_PARALLEL`, `OLLAMA_HOST`, no GPU in Docker Desktop on
  macOS): <https://github.com/ollama/ollama/blob/main/docs/faq.mdx>
- Ollama GPU support (NVIDIA compute capability 5.0+, driver 550+):
  <https://github.com/ollama/ollama/blob/main/docs/gpu.mdx>
- Ollama OpenAI compatibility (`/v1`, `image_url` data URLs, `/v1/embeddings`, API key ignored):
  <https://github.com/ollama/ollama/blob/main/docs/api/openai-compatibility.mdx>
- `ollama/ollama` Docker Hub tags (`0.34.3`, `rocm`): <https://hub.docker.com/r/ollama/ollama>
- `langchain-ollama` `ChatOllama` (`base_url`, `num_ctx`, `keep_alive`, `image_url` string or
  `{"url"}` with data-URL splitting):
  <https://github.com/langchain-ai/langchain/blob/master/libs/partners/ollama/langchain_ollama/chat_models.py>;
  `OllamaEmbeddings`:
  <https://github.com/langchain-ai/langchain/blob/master/libs/partners/ollama/langchain_ollama/embeddings.py>;
  PyPI `langchain-ollama` 1.1.0: <https://pypi.org/project/langchain-ollama/>
- `langchain-postgres` (`PGEngine`, `PGVectorStore`, `PGVector` deprecated,
  `init_vectorstore_table`, `Column`, default cosine distance, `Document.id` from the id column):
  <https://github.com/langchain-ai/langchain-postgres> (README, `langchain_postgres/v2/engine.py`,
  `v2/vectorstores.py`, `v2/async_vectorstore.py`, `v2/indexes.py`); PyPI 0.0.18:
  <https://pypi.org/project/langchain-postgres/>
- `langchain-openai` `OpenAIEmbeddings(check_embedding_ctx_length=False)` for non-OpenAI
  providers:
  <https://github.com/langchain-ai/langchain/blob/master/libs/partners/openai/langchain_openai/embeddings/base.py>;
  PyPI 1.6.5: <https://pypi.org/project/langchain-openai/>
- pgvector (Docker image tags, `CREATE EXTENSION vector`, cosine `<=>`, HNSW):
  <https://github.com/pgvector/pgvector>; tags <https://hub.docker.com/r/pgvector/pgvector>
- Postgres image (`POSTGRES_DB`, `pg_isready`, PG18 volume path change):
  <https://github.com/docker-library/docs/blob/master/postgres/content.md>
- Compose variable interpolation, including nested defaults `${A:-${B:-x}}`:
  <https://github.com/compose-spec/compose-spec/blob/main/12-interpolation.md>
- Compose `depends_on` conditions (`service_healthy`, `service_completed_successfully`):
  <https://github.com/compose-spec/compose-spec/blob/main/05-services.md>
- Compose GPU `deploy.resources.reservations.devices`:
  <https://github.com/docker/docs/blob/main/content/manuals/compose/how-tos/gpu-support.md>
  (docs.docker.com itself was not reachable; the same content was read from the GitHub source)
- PyPI wheel availability for Python 3.14 (`psycopg-binary` 3.3.6, `asyncpg` 0.31.0, `numpy`
  2.5.3): <https://pypi.org/project/psycopg-binary/>, <https://pypi.org/project/asyncpg/>,
  <https://pypi.org/project/numpy/>
- **Unverified** (ollama.com and huggingface.co were blocked by the proxy): exact model tags and
  sizes in the Ollama library (<https://ollama.com/library>), the `nomic-embed-text` vector size,
  and whether `curl` is in the `ollama/ollama` image. The seed script measures the vector size at
  runtime, so the guide does not depend on it.
