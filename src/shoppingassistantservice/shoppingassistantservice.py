#!/usr/bin/python
#
# Copyright 2024 Google LLC
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#      https://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.

import json
import os
from urllib.parse import unquote

from flask import Flask, request
from langchain_core.messages import HumanMessage
from langchain_ollama import ChatOllama

OLLAMA_BASE_URL = os.environ.get("OLLAMA_BASE_URL", "http://ollama:11434")
LLM_MODEL = os.environ.get("LLM_MODEL", "llama3.2:1b")
VISION_MODEL = os.environ.get("VISION_MODEL", "none")
PRODUCTS_JSON = os.environ.get("PRODUCTS_JSON", "/data/products.json")

with open(PRODUCTS_JSON, encoding="utf-8") as products_file:
    products = json.load(products_file)["products"]

llm = ChatOllama(model=LLM_MODEL, base_url=OLLAMA_BASE_URL, temperature=0.2)
vision_llm = None if VISION_MODEL == "none" else ChatOllama(
    model=VISION_MODEL, base_url=OLLAMA_BASE_URL, temperature=0.2
)

def describe_room(image):
    if not image or vision_llm is None:
        return ""

    message = HumanMessage(content=[
        {
            "type": "text",
            "text": "Describe the interior style of this room briefly.",
        },
        {"type": "image_url", "image_url": {"url": image}},
    ])
    return vision_llm.invoke([message]).content


def create_app():
    app = Flask(__name__)

    @app.get("/healthz")
    def healthz():
        return {"status": "ok"}

    @app.post("/")
    def talk_to_ollama():
        body = request.get_json(force=True)
        prompt = unquote(body["message"])
        normalized_prompt = prompt.lower().strip()
        if "what can you" in normalized_prompt or normalized_prompt in {
            "help",
            "help me",
            "what do you do",
        }:
            return {
                "content": (
                    "I can recommend products from the Online Boutique catalog, "
                    "help you compare items, and suggest products based on a room "
                    "image when image analysis is enabled."
                )
            }

        room_description = describe_room(body.get("image"))
        catalog = "\n".join(
            f"ID: {product['id']} | {product['name']} | {product.get('description', '')}"
            for product in products
        )
        design_prompt = (
            "You are the shopping assistant for Online Boutique. Recommend only products "
            "from the catalog below when the customer asks for recommendations. If the "
            "customer did not ask for products, answer the question directly and do not "
            "include product IDs. Recommend one product by default and up to three only "
            "when the customer asks for options. Never invent IDs.\n\n"
            f"Customer request: {prompt}\n"
            f"Room style: {room_description or 'No room image was provided; do not infer one.'}\n\n"
            f"Catalog:\n{catalog}"
        )
        response = llm.invoke(design_prompt)
        return {"content": response.content}

    return app

if __name__ == "__main__":
    # Create an instance of flask server when called directly
    app = create_app()
    app.run(host='0.0.0.0', port=8080)
