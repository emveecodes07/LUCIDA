"""
llm_client.py
Robust wrapper around a local Ollama server (via its OpenAI-compatible endpoint).
Every function here is designed to fail *helpfully* — the app should never show
a raw Python traceback to the user, only plain-English next steps.

Speed notes:
- Every call passes `keep_alive` so Ollama keeps the model resident in memory
  between requests instead of unloading and reloading it (the single biggest
  source of "why is this slow" latency with local models).
- `warm_up()` fires a throwaway 1-token request so the model is already loaded
  by the time the user sends their first real message.
"""

import requests
from openai import OpenAI

DEFAULT_KEEP_ALIVE = "30m"


class OllamaError(Exception):
    """Base class for friendly, user-facing errors talking to Ollama."""


class OllamaOfflineError(OllamaError):
    pass


class ModelNotFoundError(OllamaError):
    pass


def _native_api_base(openai_base_url: str) -> str:
    """Turn 'http://localhost:11434/v1' into 'http://localhost:11434'."""
    base = openai_base_url.rstrip("/")
    if base.endswith("/v1"):
        base = base[: -len("/v1")]
    return base


def check_ollama_status(base_url: str, timeout: float = 2.0):
    """
    Ping the Ollama server. Never raises — safe to call on every rerun.
    Returns (is_online: bool, installed_models: list[str], error_message: str | None)
    """
    native_base = _native_api_base(base_url)
    try:
        resp = requests.get(f"{native_base}/api/tags", timeout=timeout)
        resp.raise_for_status()
        models = [m["name"] for m in resp.json().get("models", [])]
        return True, models, None
    except requests.exceptions.ConnectionError:
        return False, [], (
            "Can't reach Ollama at this address. Make sure it's running — open a terminal "
            "and run `ollama serve`, or simply `ollama run <model>` (which starts the server "
            "automatically). Everything here is local — no cloud fallback is used."
        )
    except requests.exceptions.Timeout:
        return False, [], "Ollama didn't respond in time. It may still be starting up."
    except Exception as e:
        return False, [], f"Unexpected error reaching Ollama: {e}"


def model_is_available(model: str, installed_models: list) -> bool:
    return any(
        model == m or m.startswith(f"{model}:") or m.split(":")[0] == model.split(":")[0]
        for m in installed_models
    )


def warm_up(base_url: str, model: str, keep_alive: str = DEFAULT_KEEP_ALIVE) -> None:
    """
    Fire a minimal, throwaway request so the model loads into memory NOW instead of
    on the user's first real message. Best-effort only — never raises, since a failed
    warm-up just means the first message pays the normal load cost.
    """
    client = OpenAI(base_url=base_url, api_key="ollama", timeout=30.0)
    try:
        client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "hi"}],
            max_tokens=1,
            temperature=0,
            extra_body={"keep_alive": keep_alive},
        )
    except Exception:
        pass


def stream_chat(base_url: str, model: str, messages: list, temperature: float = 0.65,
                 max_tokens: int = 300, timeout: float = 60.0, keep_alive: str = DEFAULT_KEEP_ALIVE):
    """
    Generator yielding text chunks from the model. Raises a friendly OllamaError
    subclass on failure instead of leaking the raw exception.
    """
    client = OpenAI(base_url=base_url, api_key="ollama", timeout=timeout)
    try:
        stream = client.chat.completions.create(
            model=model,
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            stream=True,
            extra_body={"keep_alive": keep_alive},
        )
        for chunk in stream:
            delta = chunk.choices[0].delta.content
            if delta:
                yield delta
    except Exception as e:
        raise _translate_error(e, model) from e


def complete(base_url: str, model: str, system_prompt: str, user_content: str,
             max_tokens: int = 300, temperature: float = 0.4, timeout: float = 60.0,
             keep_alive: str = DEFAULT_KEEP_ALIVE) -> str:
    """Non-streaming single-shot completion, used for summaries/study packs/memory rollups."""
    client = OpenAI(base_url=base_url, api_key="ollama", timeout=timeout)
    try:
        resp = client.chat.completions.create(
            model=model,
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_content},
            ],
            max_tokens=max_tokens,
            temperature=temperature,
            extra_body={"keep_alive": keep_alive},
        )
        return (resp.choices[0].message.content or "").strip()
    except Exception as e:
        raise _translate_error(e, model) from e


def _translate_error(e: Exception, model: str) -> OllamaError:
    msg = str(e).lower()
    if "connection" in msg or "refused" in msg:
        return OllamaOfflineError(
            "Lost connection to Ollama. Check that `ollama serve` is still running in a terminal."
        )
    if "model" in msg and ("not found" in msg or "404" in msg):
        return ModelNotFoundError(f"Model '{model}' isn't pulled yet. Run `ollama pull {model}`.")
    return OllamaError(f"Something went wrong talking to the model: {e}")
