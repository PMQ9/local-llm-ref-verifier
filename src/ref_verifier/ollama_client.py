"""Shared Ollama interaction helper.

Wraps ollama.chat() with structured output support, configurable model,
and graceful error handling when Ollama is not available.
"""

import json
import logging
from typing import TypeVar

import ollama
from pydantic import BaseModel

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=BaseModel)

DEFAULT_MODEL = "llama3.1"


class OllamaClient:
    def __init__(self, model: str = DEFAULT_MODEL, temperature: float = 0.0):
        self.model = model
        self.temperature = temperature
        self._client: ollama.Client | None = None

    def _get_client(self) -> ollama.Client:
        if self._client is None:
            self._client = ollama.Client()
        return self._client

    def check_connection(self) -> bool:
        """Check if Ollama is running and the model is available."""
        try:
            client = self._get_client()
            models = client.list()
            available = [m.model for m in models.models]
            if not any(self.model in name for name in available):
                logger.error(
                    "Model '%s' not found. Available models: %s",
                    self.model,
                    available,
                )
                return False
            return True
        except Exception as e:
            logger.error("Cannot connect to Ollama: %s", e)
            return False

    def chat_structured(
        self,
        prompt: str,
        response_model: type[T],
        system_prompt: str = "",
    ) -> T:
        """Send a prompt to Ollama and parse the response into a Pydantic model.

        Uses Ollama's format= parameter for structured JSON output.
        """
        if not self.check_connection():
            raise ConnectionError(
                f"Ollama is not running or model '{self.model}' is not available. "
                "Start Ollama with 'ollama serve' and pull a model with "
                f"'ollama pull {self.model}'."
            )

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        client = self._get_client()
        response = client.chat(
            model=self.model,
            messages=messages,
            format=response_model.model_json_schema(),
            options={"temperature": self.temperature},
        )

        raw_json = response.message.content
        parsed = json.loads(raw_json)
        return response_model.model_validate(parsed)

    def chat_raw(self, prompt: str, system_prompt: str = "") -> str:
        """Send a prompt and return the raw text response."""
        if not self.check_connection():
            raise ConnectionError(
                f"Ollama is not running or model '{self.model}' is not available."
            )

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        client = self._get_client()
        response = client.chat(
            model=self.model,
            messages=messages,
            options={"temperature": self.temperature},
        )

        return response.message.content
