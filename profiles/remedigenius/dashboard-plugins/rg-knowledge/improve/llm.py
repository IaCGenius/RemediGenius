"""Model clients for offline improvement: Hermes plugin model access, OpenAI-compatible HTTP, or a scripted mock."""
from __future__ import annotations

import json
import os
import re
import threading
import urllib.request


class Usage:
    def __init__(self):
        self.input = 0
        self.output = 0
        self.calls = 0
        self._lock = threading.Lock()

    def add(self, input_tokens, output_tokens):
        with self._lock:
            self.input += int(input_tokens or 0)
            self.output += int(output_tokens or 0)
            self.calls += 1

    @property
    def total(self):
        return self.input + self.output

    def to_dict(self):
        return {"input_tokens": self.input, "output_tokens": self.output, "total_tokens": self.total, "calls": self.calls}


class BudgetExceeded(RuntimeError):
    pass


class Client:
    """complete(messages) -> text. Tracks tokens and enforces a budget for the whole job."""
    name = "model"

    def __init__(self, budget_tokens: int = 0):
        self.usage = Usage()
        self.budget = budget_tokens

    def complete(self, messages: list[dict], max_tokens: int = 2000, temperature: float = 0.0) -> str:
        if self.budget and self.usage.total >= self.budget:
            raise BudgetExceeded(f"token budget of {self.budget:,} reached")
        text, input_tokens, output_tokens = self._complete(messages, max_tokens, temperature)
        self.usage.add(input_tokens, output_tokens)
        return text

    def _complete(self, messages, max_tokens, temperature):
        raise NotImplementedError


class HermesClient(Client):
    """The model the user configured in Hermes (plugin model access; credentials stay with Hermes)."""

    def __init__(self, budget_tokens: int = 0):
        super().__init__(budget_tokens)
        from pathlib import Path

        from hermes_cli.env_loader import load_hermes_dotenv
        load_hermes_dotenv(hermes_home=Path(os.environ["HERMES_HOME"]))
        from agent.plugin_llm import PluginLlm
        self._llm = PluginLlm(plugin_id="rg-knowledge")
        self.name = "hermes"

    def _complete(self, messages, max_tokens, temperature):
        r = self._llm.complete(messages=messages, max_tokens=max_tokens, temperature=temperature,
                               purpose="rg-knowledge.improve", timeout=300)
        self.name = f"{r.provider}/{r.model}"
        return r.text or "", r.usage.input_tokens, r.usage.output_tokens


class OpenAIClient(Client):
    """Any OpenAI-compatible endpoint (local development); the key comes from an environment variable."""

    def __init__(self, base_url: str, model: str, key_env: str = "REMEDIGENIUS_MODEL_KEY", budget_tokens: int = 0):
        super().__init__(budget_tokens)
        self.base_url, self.model, self.key = base_url.rstrip("/"), model, os.environ.get(key_env, "")
        self.name = f"openai-compatible/{model}"

    def _complete(self, messages, max_tokens, temperature):
        body = json.dumps({"model": self.model, "messages": messages, "max_tokens": max_tokens, "temperature": temperature}).encode()
        req = urllib.request.Request(f"{self.base_url}/chat/completions", data=body, method="POST",
                                     headers={"Content-Type": "application/json", "Authorization": f"Bearer {self.key}"})
        with urllib.request.urlopen(req, timeout=300) as resp:
            data = json.loads(resp.read())
        usage = data.get("usage") or {}
        return data["choices"][0]["message"].get("content") or "", usage.get("prompt_tokens", 0), usage.get("completion_tokens", 0)


class MockClient(Client):
    """Scripted responses for tests: `script(messages) -> text`."""

    def __init__(self, script, budget_tokens: int = 0):
        super().__init__(budget_tokens)
        self.script = script
        self.name = "mock"

    def _complete(self, messages, max_tokens, temperature):
        text = self.script(messages)
        return text, sum(len(m["content"]) for m in messages) // 4, len(text) // 4


def parse_json(text: str):
    """The first JSON object in a model reply (tolerates code fences and prose around it)."""
    text = re.sub(r"^```(?:json)?|```$", "", (text or "").strip(), flags=re.M).strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    start = text.find("{")
    while start != -1:
        depth, in_str, esc = 0, False, False
        for i in range(start, len(text)):
            ch = text[i]
            if in_str:
                esc = (ch == "\\" and not esc)
                if ch == '"' and not esc:
                    in_str = False
                continue
            if ch == '"':
                in_str = True
            elif ch == "{":
                depth += 1
            elif ch == "}":
                depth -= 1
                if depth == 0:
                    try:
                        return json.loads(text[start:i + 1])
                    except json.JSONDecodeError:
                        break
        start = text.find("{", start + 1)
    return None


def from_settings(kind: str, budget_tokens: int, base_url: str = "", model: str = "", script=None) -> Client:
    if kind == "hermes":
        return HermesClient(budget_tokens)
    if kind == "openai":
        return OpenAIClient(base_url, model, budget_tokens=budget_tokens)
    if kind == "mock":
        return MockClient(script, budget_tokens)
    raise ValueError(f"unknown model client {kind!r}")
