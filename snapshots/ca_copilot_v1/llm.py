"""Thin provider-agnostic wrapper over OpenAI-compatible chat APIs (DeepSeek, Qwen/DashScope)."""
from __future__ import annotations

import json
import os
import re
import time

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()

PROVIDERS = {
    "deepseek": {
        "base_url": "https://api.deepseek.com",
        "key_env": "DEEPSEEK_API_KEY",
        "model_env": "DEEPSEEK_MODEL",
        "default_model": "deepseek-chat",
    },
    "qwen": {
        "base_url": "https://dashscope.aliyuncs.com/compatible-mode/v1",
        "key_env": "DASHSCOPE_API_KEY",
        "model_env": "QWEN_MODEL",
        "default_model": "qwen-plus",
    },
}


class LLM:
    def __init__(self, provider: str, model: str | None = None, temperature: float = 0.8):
        cfg = PROVIDERS[provider]
        key = os.getenv(cfg["key_env"])
        if not key:
            raise RuntimeError(f"Missing {cfg['key_env']} (set it in .env)")
        self.provider = provider
        self.model = model or os.getenv(cfg["model_env"], cfg["default_model"])
        self.temperature = temperature
        self.client = OpenAI(api_key=key, base_url=os.getenv(f"{provider.upper()}_BASE_URL", cfg["base_url"]))

    @property
    def name(self) -> str:
        return f"{self.provider}:{self.model}"

    def json_chat(self, system: str, user: str, temperature: float | None = None, retries: int = 3) -> dict:
        last_err = None
        for attempt in range(retries):
            try:
                resp = self.client.chat.completions.create(
                    model=self.model,
                    messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                    temperature=self.temperature if temperature is None else temperature,
                    response_format={"type": "json_object"},
                )
                return parse_json(resp.choices[0].message.content)
            except Exception as e:  # network / rate-limit / malformed JSON
                last_err = e
                time.sleep(2 * (attempt + 1))
        raise RuntimeError(f"{self.name} failed after {retries} attempts: {last_err}")


def parse_json(text: str) -> dict:
    text = text.strip()
    m = re.search(r"```(?:json)?\s*(.*?)```", text, re.S)
    if m:
        text = m.group(1)
    return json.loads(text)
