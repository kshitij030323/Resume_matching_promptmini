"""Provider-agnostic wrapper for schema-constrained LLM calls.

Every LLM call in the project goes through :func:`structured_call`, which returns a
validated Pydantic model. Two providers are supported:

* **Google Gemini** (REST ``generateContent``). The output is constrained with
  ``responseJsonSchema``; if a model rejects the schema, the call falls back to JSON
  mode with the schema in the system prompt. Key from the Settings page, or from
  ``GEMINI_API_KEY`` / ``GOOGLE_API_KEY`` (also read from ``backend/.env``).
* **Anthropic Claude** (SDK structured outputs with the server-side refusal fallback).
  Key from ``ANTHROPIC_API_KEY`` / ``ANTHROPIC_AUTH_TOKEN`` or ``ant auth login``.

Both paths validate again with Pydantic and, on failure, re-ask once with the
validation error appended ("automatic repair"). With no provider configured (or
DISABLE_LLM=1), ``llm_available()`` is False and callers use their offline versions.
"""

from __future__ import annotations

import json
import os
import re
import threading
import time
from pathlib import Path
from typing import Optional, TypeVar

import httpx
from pydantic import BaseModel, ValidationError

from . import config

T = TypeVar("T", bound=BaseModel)

PROVIDER_LABELS = {"gemini": "Gemini", "anthropic": "Claude"}


class LLMUnavailable(RuntimeError):
    pass


class GeminiHTTPError(LLMUnavailable):
    def __init__(self, status: int, message: str):
        super().__init__(f"Gemini API error {status}: {message}")
        self.status = status
        self.message = message


# ----------------------------------------------------------------------------- settings
_lock = threading.Lock()
_settings: dict = {"gemini_api_key": None, "gemini_model": None, "remembered": False}
_gemini_models: dict[str, list[str]] = {}       # key fingerprint -> model ids
_schema_mode: dict[str, str] = {}                # model id -> "json_schema" | "prompt"


def _load_saved_settings() -> None:
    try:
        saved = json.loads(config.LLM_SETTINGS_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return
    if isinstance(saved, dict) and saved.get("gemini_api_key"):
        _settings.update(gemini_api_key=saved["gemini_api_key"], gemini_model=saved.get("gemini_model"),
                         remembered=True)


def _persist() -> None:
    path = config.LLM_SETTINGS_PATH
    if _settings["remembered"] and _settings["gemini_api_key"]:
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {"gemini_api_key": _settings["gemini_api_key"], "gemini_model": _settings["gemini_model"]}
        fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(payload, fh)
    else:
        path.unlink(missing_ok=True)


_load_saved_settings()


def _gemini_key() -> tuple[Optional[str], Optional[str]]:
    """(key, source) - a key entered on the Settings page wins over the environment."""
    if _settings["gemini_api_key"]:
        return _settings["gemini_api_key"], "settings"
    env = os.getenv("GEMINI_API_KEY") or os.getenv("GOOGLE_API_KEY")
    if env:
        return env.strip(), "env"
    return None, None


def anthropic_configured() -> bool:
    if os.getenv("ANTHROPIC_API_KEY") or os.getenv("ANTHROPIC_AUTH_TOKEN"):
        return True
    # `ant auth login` stores a profile the SDK picks up automatically.
    return (Path.home() / ".config" / "anthropic").is_dir()


def active_provider() -> Optional[str]:
    if config.DISABLE_LLM:
        return None
    has_gemini = _gemini_key()[0] is not None
    has_claude = anthropic_configured()
    pref = config.LLM_PROVIDER
    if pref == "gemini":
        return "gemini" if has_gemini else None
    if pref in {"anthropic", "claude"}:
        return "anthropic" if has_claude else None
    if has_gemini:
        return "gemini"
    if has_claude:
        return "anthropic"
    return None


def llm_available() -> bool:
    return active_provider() is not None


def gemini_model() -> str:
    return _settings["gemini_model"] or config.GEMINI_MODEL


def _hint(key: Optional[str]) -> Optional[str]:
    return f"…{key[-4:]}" if key and len(key) >= 8 else ("set" if key else None)


def llm_status(include_models: bool = False) -> dict:
    provider = active_provider()
    key, source = _gemini_key()
    gemini = {
        "configured": key is not None,
        "key_source": source,
        "key_hint": _hint(key),
        "model": gemini_model(),
        "remembered": bool(_settings["remembered"] and source == "settings"),
    }
    if include_models and key:
        try:
            gemini["models"] = list_gemini_models(key)
            gemini["error"] = None
        except LLMUnavailable as exc:
            gemini["models"] = []
            gemini["error"] = str(exc)
    model = gemini_model() if provider == "gemini" else config.LLM_MODEL if provider == "anthropic" else None
    return {
        "enabled": provider is not None,
        "provider": provider or "none",
        "provider_label": PROVIDER_LABELS.get(provider or "", "Offline"),
        "model": model,
        "preference": config.LLM_PROVIDER,
        "disabled": config.DISABLE_LLM,
        "gemini": gemini,
        "anthropic": {"configured": anthropic_configured(), "model": config.LLM_MODEL},
    }


# ----------------------------------------------------------------------------- Gemini: models
_SKIP_MODEL = re.compile(r"embed|aqa|imagen|veo|tts|image|live|audio|robotics|computer-use|gemma|learnlm|nano", re.I)


def _model_rank(name: str) -> tuple:
    """Sort order for the model picker: aliases, then flash, then pro, newest first."""
    n = name.lower()
    alias = n.endswith("-latest")
    family = 0 if "flash" in n and "lite" not in n else 1 if "pro" in n else 2
    version = [float(v) for v in re.findall(r"(\d+(?:\.\d+)?)", n)[:1]] or [0.0]
    preview = "preview" in n or "exp" in n
    return (not alias, family, -version[0], preview, n)


def list_gemini_models(key: str, refresh: bool = False) -> list[str]:
    """Text models the key can call with generateContent (cached per key)."""
    fp = key[-12:]
    if not refresh and fp in _gemini_models:
        return _gemini_models[fp]
    names: list[str] = []
    page_token = None
    for _ in range(10):
        params = {"pageSize": 1000}
        if page_token:
            params["pageToken"] = page_token
        try:
            r = httpx.get(f"{config.GEMINI_BASE_URL}/v1beta/models", params=params,
                          headers={"x-goog-api-key": key}, timeout=20.0)
        except httpx.HTTPError as exc:
            raise LLMUnavailable(f"Could not reach the Gemini API: {exc}") from exc
        if r.status_code != 200:
            raise GeminiHTTPError(r.status_code, _gemini_error_message(r))
        data = r.json()
        for m in data.get("models", []):
            name = str(m.get("name", "")).removeprefix("models/")
            if "generateContent" in (m.get("supportedGenerationMethods") or []) and not _SKIP_MODEL.search(name):
                names.append(name)
        page_token = data.get("nextPageToken")
        if not page_token:
            break
    names = sorted(set(names), key=_model_rank)
    _gemini_models[fp] = names
    return names


def _pick_default_model(models: list[str]) -> str:
    for want in (config.GEMINI_MODEL, "gemini-flash-latest", "gemini-2.5-flash"):
        if want in models:
            return want
    return models[0] if models else config.GEMINI_MODEL


def set_gemini(api_key: Optional[str], model: Optional[str], remember: bool) -> dict:
    """Store (and verify) a Gemini key and/or model chosen on the Settings page."""
    with _lock:
        if api_key is not None:
            api_key = api_key.strip()
            if not api_key or any(c.isspace() for c in api_key) or len(api_key) > 256:
                raise LLMUnavailable("That does not look like an API key.")
            models = list_gemini_models(api_key, refresh=True)   # raises if Google rejects the key
            if not models:
                raise LLMUnavailable("The key works but cannot call any Gemini text model.")
            chosen = model if model in models else (
                _settings["gemini_model"] if _settings["gemini_model"] in models else _pick_default_model(models))
            _settings.update(gemini_api_key=api_key, gemini_model=chosen, remembered=remember)
        else:
            key, _ = _gemini_key()
            if not key:
                raise LLMUnavailable("Add a Gemini API key first.")
            if model:
                models = list_gemini_models(key)
                if models and model not in models:
                    raise LLMUnavailable(f"Model '{model}' is not available for this key.")
                _settings["gemini_model"] = model
            if _settings["gemini_api_key"]:
                _settings["remembered"] = remember
        _persist()
    return llm_status(include_models=True)


def clear_gemini() -> dict:
    with _lock:
        _settings.update(gemini_api_key=None, gemini_model=None, remembered=False)
        _persist()
    return llm_status(include_models=True)


# ----------------------------------------------------------------------------- Gemini: calls
_DROP_KEYS = {"title", "default", "additionalProperties", "examples"}


def gemini_schema(model_cls: type[BaseModel]) -> dict:
    """Pydantic JSON schema with $refs inlined and keywords Gemini may reject removed."""
    schema = model_cls.model_json_schema()
    defs = schema.pop("$defs", {})

    def walk(node, depth=0):
        if depth > 40:
            raise ValueError("schema nesting too deep")
        if isinstance(node, list):
            return [walk(x, depth + 1) for x in node]
        if not isinstance(node, dict):
            return node
        if "$ref" in node:
            target = defs[node["$ref"].split("/")[-1]]
            extra = {k: v for k, v in node.items() if k != "$ref"}
            return walk({**target, **extra}, depth + 1)
        out = {}
        for k, v in node.items():
            if k == "properties":
                out[k] = {name: walk(sub, depth + 1) for name, sub in v.items()}
            elif k not in _DROP_KEYS:
                out[k] = walk(v, depth + 1)
        return out

    return walk(schema)


def _gemini_error_message(r: httpx.Response) -> str:
    try:
        err = r.json().get("error", {})
        return err.get("message") or r.text[:300]
    except ValueError:
        return r.text[:300] or r.reason_phrase


def _retry_delay(r: httpx.Response) -> Optional[float]:
    if r.headers.get("retry-after", "").isdigit():
        return float(r.headers["retry-after"])
    try:
        for d in r.json().get("error", {}).get("details", []):
            if str(d.get("@type", "")).endswith("RetryInfo") and d.get("retryDelay"):
                return float(str(d["retryDelay"]).rstrip("s"))
    except (ValueError, AttributeError):
        pass
    return None


def _gemini_post(key: str, model: str, body: dict) -> dict:
    url = f"{config.GEMINI_BASE_URL}/v1beta/models/{model}:generateContent"
    for attempt in range(5):
        try:
            r = httpx.post(url, json=body, headers={"x-goog-api-key": key}, timeout=180.0)
        except httpx.HTTPError as exc:
            if attempt < 2:
                time.sleep(2 ** attempt)
                continue
            raise LLMUnavailable(f"Could not reach the Gemini API: {exc}") from exc
        if r.status_code == 200:
            return r.json()
        message = _gemini_error_message(r)
        if r.status_code in (429, 500, 502, 503, 504) and attempt < 4:
            delay = _retry_delay(r) or min(2 ** (attempt + 1), 30)
            if "PerDay" in message or "per day" in message.lower() or delay > 65:
                raise LLMUnavailable(f"Gemini quota exhausted: {message}")
            time.sleep(delay + 0.5)
            continue
        if r.status_code in (401, 403) or "API key not valid" in message:
            raise GeminiHTTPError(r.status_code, f"key rejected - {message}")
        raise GeminiHTTPError(r.status_code, message)
    raise LLMUnavailable("Gemini API kept failing after retries")


def _gemini_body(system: str, contents: list[dict], schema: dict, mode: str) -> dict:
    generation = {"responseMimeType": "application/json"}
    if mode == "json_schema":
        generation["responseJsonSchema"] = schema
    else:
        system = (f"{system}\n\nReturn ONLY one JSON object that conforms to this JSON Schema "
                  f"(no prose, no markdown fences):\n{json.dumps(schema)}")
    return {"systemInstruction": {"parts": [{"text": system}]}, "contents": contents,
            "generationConfig": generation}


def _looks_like_schema_error(err: GeminiHTTPError) -> bool:
    m = err.message.lower()
    return err.status == 400 and any(s in m for s in ("schema", "response_json", "responsejson", "unknown name"))


def _gemini_text(data: dict) -> str:
    block = (data.get("promptFeedback") or {}).get("blockReason")
    if block:
        raise LLMUnavailable(f"Gemini blocked the prompt ({block})")
    candidates = data.get("candidates") or []
    if not candidates:
        raise LLMUnavailable("Gemini returned no candidates")
    cand = candidates[0]
    finish = cand.get("finishReason", "")
    if finish == "MAX_TOKENS":
        raise LLMUnavailable("Gemini output was truncated (MAX_TOKENS)")
    if finish in {"SAFETY", "RECITATION", "PROHIBITED_CONTENT", "BLOCKLIST", "SPII", "LANGUAGE"}:
        raise LLMUnavailable(f"Gemini stopped generating ({finish})")
    parts = (cand.get("content") or {}).get("parts") or []
    return "".join(p.get("text", "") for p in parts if not p.get("thought"))


def _strip_fences(text: str) -> str:
    text = text.strip()
    m = re.match(r"^```(?:json)?\s*(.*?)\s*```$", text, re.S)
    return m.group(1) if m else text


def _gemini_structured(system: str, user: str, output_model: type[T]) -> tuple[T, dict]:
    key, _ = _gemini_key()
    if not key:
        raise LLMUnavailable("No Gemini API key configured")
    model = gemini_model()
    schema = gemini_schema(output_model)
    contents: list[dict] = [{"role": "user", "parts": [{"text": user}]}]
    repaired = False
    tokens_in = tokens_out = 0
    t0 = time.perf_counter()

    for attempt in range(2):
        mode = _schema_mode.get(model, "json_schema")
        try:
            data = _gemini_post(key, model, _gemini_body(system, contents, schema, mode))
        except GeminiHTTPError as exc:
            if mode == "json_schema" and _looks_like_schema_error(exc):
                _schema_mode[model] = "prompt"       # remember: this model wants the schema in the prompt
                data = _gemini_post(key, model, _gemini_body(system, contents, schema, "prompt"))
            else:
                raise
        text = _gemini_text(data)
        usage = data.get("usageMetadata") or {}
        tokens_in += int(usage.get("promptTokenCount") or 0)
        tokens_out += int(usage.get("candidatesTokenCount") or 0) + int(usage.get("thoughtsTokenCount") or 0)
        try:
            parsed = output_model.model_validate_json(_strip_fences(text))
        except ValidationError as err:
            if attempt == 1:
                raise LLMUnavailable(f"Gemini output failed schema validation twice: {err}") from err
            repaired = True
            contents = contents + [
                {"role": "model", "parts": [{"text": text or "(empty)"}]},
                {"role": "user", "parts": [{"text": "Your previous output did not validate against the schema:\n"
                                                     f"{err}\nReturn the corrected JSON only."}]},
            ]
            continue
        return parsed, {
            "provider": "gemini",
            "model": data.get("modelVersion") or model,
            "latency_ms": int((time.perf_counter() - t0) * 1000),
            "repaired": repaired,
            "input_tokens": tokens_in,
            "output_tokens": tokens_out,
        }
    raise LLMUnavailable("unreachable")


# ----------------------------------------------------------------------------- Claude
_client = None


def _get_client():
    global _client
    if _client is None:
        try:
            import anthropic
        except ImportError as exc:  # pragma: no cover
            raise LLMUnavailable("anthropic package not installed") from exc
        _client = anthropic.Anthropic(max_retries=3, timeout=180.0)
    return _client


def _anthropic_structured(system: str, user: str, output_model: type[T], effort: str,
                          max_tokens: int) -> tuple[T, dict]:
    import anthropic

    client = _get_client()
    messages: list[dict] = [{"role": "user", "content": user}]
    repaired = False
    t0 = time.perf_counter()

    for attempt in range(2):
        try:
            response = client.beta.messages.parse(
                model=config.LLM_MODEL,
                max_tokens=max_tokens,
                system=system,
                messages=messages,
                output_format=output_model,
                output_config={"effort": effort},
                betas=["server-side-fallback-2026-07-01"],
                fallbacks="default",
            )
        except anthropic.AuthenticationError as exc:
            raise LLMUnavailable(f"Anthropic authentication failed: {exc}") from exc
        except anthropic.RateLimitError as exc:
            raise LLMUnavailable(f"Rate limited by Anthropic API: {exc}") from exc
        except anthropic.APIStatusError as exc:
            raise LLMUnavailable(f"Anthropic API error {exc.status_code}: {exc.message}") from exc
        except anthropic.APIConnectionError as exc:
            raise LLMUnavailable(f"Could not reach Anthropic API: {exc}") from exc

        if response.stop_reason == "refusal":
            raise LLMUnavailable("Model declined the request (refusal)")
        if response.stop_reason == "max_tokens":
            raise LLMUnavailable("Output truncated at max_tokens")

        parsed = getattr(response, "parsed_output", None)
        if parsed is not None:
            return parsed, {
                "provider": "anthropic",
                "model": response.model,
                "latency_ms": int((time.perf_counter() - t0) * 1000),
                "repaired": repaired,
                "input_tokens": response.usage.input_tokens,
                "output_tokens": response.usage.output_tokens,
            }

        # Repair path: validate the raw text ourselves and feed the error back once.
        text = next((b.text for b in response.content if b.type == "text"), "")
        try:
            return output_model.model_validate_json(text), {
                "provider": "anthropic",
                "model": response.model,
                "latency_ms": int((time.perf_counter() - t0) * 1000),
                "repaired": repaired,
            }
        except ValidationError as err:
            if attempt == 1:
                raise LLMUnavailable(f"Output failed schema validation twice: {err}") from err
            repaired = True
            messages = messages + [
                {"role": "assistant", "content": text or "(empty)"},
                {
                    "role": "user",
                    "content": "Your previous output did not validate against the schema:\n"
                    f"{err}\nReturn the corrected JSON only.",
                },
            ]
    raise LLMUnavailable("unreachable")


# ----------------------------------------------------------------------------- entry point
def structured_call(
    *,
    system: str,
    user: str,
    output_model: type[T],
    effort: str = "medium",
    max_tokens: int = 16000,
) -> tuple[T, dict]:
    """Call the active provider and return (validated model instance, meta dict)."""
    provider = active_provider()
    if provider == "gemini":
        return _gemini_structured(system, user, output_model)
    if provider == "anthropic":
        return _anthropic_structured(system, user, output_model, effort, max_tokens)
    raise LLMUnavailable("No LLM provider configured")
