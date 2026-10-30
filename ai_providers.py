"""
ai_providers.py — provider-neutral AI toolkit used by ai_system.py.

Why this exists
---------------
ai_system.py's only real LLM path was a local Ollama server.  When Ollama was
offline (the normal case on a shared host) every message fell through to
regex-driven canned replies, which is why the bot "could not understand" slang,
typos, follow-ups or other languages.  This module adds a real model layer
while leaving the old rule-based engine in place as the last-resort fallback.

Contents
--------
  LLMRouter        OpenAI-compatible providers (custom / Groq / OpenRouter /
                   Gemini / OpenAI) + Ollama + optional keyless fallback, with
                   retries, per-provider circuit breaker, vision support and
                   robust response parsing.
  IntentRouter     "understand first, act second": multilingual, typo-tolerant
                   heuristics, then an LLM classifier that sees recent history.
  detect_language  script + stop-word language detection.
  WebSearch        Tavily / Brave / SearXNG / DuckDuckGo-HTML chain.
  ImageGenerator   OpenAI-compatible images API and Pollinations, downloaded
                   server-side and validated (no more broken hot-linked embeds).
  Translator       LLM first, LibreTranslate / MyMemory as fallbacks.

Configuration is ENV ONLY — no key is ever stored in code:
  AI_LOCAL=1 (or LOCAL_MODEL_PATH / LOCAL_MODEL_REPO+LOCAL_MODEL_FILE)   run a model inside the bot, no API key
                                                        — see local_llm.py for all LOCAL_* settings
  AI_API_BASE, AI_API_KEY, AI_MODEL, AI_VISION_MODEL    any OpenAI-compatible API
  GROQ_API_KEY, OPENROUTER_API_KEY, GEMINI_API_KEY, OPENAI_API_KEY
                                                        convenience presets
  AI_OLLAMA_VISION_MODEL                                vision model for Ollama
  AI_INTENT_LLM=0                                       skip the LLM intent classifier (heuristics only; saves 1 call/message)
  AI_KEYLESS_FALLBACK=1                                 OPT IN to a public keyless endpoint (messages go to a third party)
  AI_KEYLESS_URL, AI_KEYLESS_MODEL                      override the keyless endpoint
  TAVILY_API_KEY, BRAVE_API_KEY, SEARXNG_URL            web search backends
  AI_IMAGE_API_BASE, AI_IMAGE_API_KEY, AI_IMAGE_MODEL   paid image backend (optional)
  AI_IMAGE_MODELS=flux,turbo                            Pollinations model order
  LIBRETRANSLATE_URL, LIBRETRANSLATE_API_KEY            translation fallback
"""
from __future__ import annotations

import asyncio
import base64
import datetime
import difflib
import html
import json
import logging
import os
import re
import time
import unicodedata
import urllib.parse
from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional, Tuple

try:  # aiohttp is only used for ClientTimeout; everything else is duck-typed
    import aiohttp  # type: ignore
except Exception:  # pragma: no cover
    aiohttp = None  # type: ignore

from local_llm import LocalLLM, LocalLLMError, local_enabled, local_model_name  # in-process CPU model

logger = logging.getLogger("gkr_ai.providers")

INTENTS = ("chat", "image_generate", "image_understand", "web_search",
           "translate", "summarize", "code", "joke")


# ═══════════════════════════════════════════════════════════════════════════
# Errors
# ═══════════════════════════════════════════════════════════════════════════

class ProviderError(Exception):
    """One provider failed. `kind` drives retry + user-facing wording."""

    def __init__(self, kind: str, message: str = "", provider: str = "", status: Optional[int] = None,
                 retry_after: Optional[float] = None):
        super().__init__(message or kind)
        self.kind, self.provider, self.status, self.retry_after = kind, provider, status, retry_after

    def hint(self) -> str:
        return {
            "timeout": "timed out",
            "rate_limit": "is rate-limited",
            "auth": "rejected the API key",
            "not_found": "doesn't know that model/endpoint",
            "server": "had a server error",
            "network": "could not be reached",
            "bad_response": "returned an unreadable response",
            "empty": "returned an empty answer",
            "bad_request": "rejected the request",
            "unsupported": "doesn't support this feature",
            "not_installed": "isn't installed",
            "loading": "is still loading",
            "busy": "is busy",
        }.get(self.kind, "failed")


class AllProvidersFailed(Exception):
    def __init__(self, errors: List[ProviderError], configured: int = 0, what: str = "AI"):
        super().__init__("; ".join(f"{e.provider}: {e.kind}" for e in errors) or "no provider")
        self.errors, self.configured, self.what = errors, configured, what

    def user_message(self) -> str:
        if not self.configured:
            return (f"⚠️ No {self.what} provider is set up yet. The bot owner needs to add an API key "
                    f"(for example `AI_API_KEY`) or run Ollama.")
        kinds = {e.kind for e in self.errors}
        if "loading" in kinds:
            return "🧠 My local AI model is still loading (the first start downloads it) — try again in a minute."
        if "busy" in kinds:
            return "⚠️ I'm busy with other requests right now — try again in a few seconds."
        if "not_installed" in kinds and not (kinds & {"rate_limit", "timeout", "server", "auth"}):
            return ("⚠️ The local AI engine isn't installed on the host (it needs the `llama-cpp-python` package). "
                    "The bot owner needs to install it.")
        if kinds <= {"auth"}:
            return f"⚠️ The {self.what} provider rejected its API key. The bot owner needs to check it."
        if "rate_limit" in kinds:
            return f"⚠️ The {self.what} provider is rate-limited right now. Try again in a minute."
        if kinds <= {"timeout"}:
            return f"⚠️ The {self.what} provider timed out. Try again in a moment."
        if "unsupported" in kinds and len(kinds) == 1:
            return f"⚠️ None of the configured providers support {self.what} yet."
        return f"⚠️ The {self.what} provider isn't responding right now. Try again shortly."


class SearchError(Exception):
    pass


class ImageGenError(Exception):
    def user_message(self) -> str:
        return f"⚠️ Image generation failed: {self}"


# ═══════════════════════════════════════════════════════════════════════════
# HTTP helper (duck-typed so it works with aiohttp.ClientSession and test fakes)
# ═══════════════════════════════════════════════════════════════════════════

def _classify_status(status: int) -> str:
    if status in (401, 403):
        return "auth"
    if status == 404:
        return "not_found"
    if status == 429:
        return "rate_limit"
    if status in (400, 405, 413, 415, 422):
        return "bad_request"
    if status >= 500:
        return "server"
    return "bad_response"


async def http_request(session, method: str, url: str, *, json_body: Any = None,
                       headers: Optional[dict] = None, params: Optional[dict] = None,
                       timeout: float = 30, want: str = "text", provider: str = "") -> Tuple[int, Any, dict]:
    """Returns (status, body, headers). body is str (want='text') or bytes (want='bytes').
    Never raises anything except ProviderError."""

    async def _do():
        kw: Dict[str, Any] = {}
        if headers:
            kw["headers"] = headers
        if json_body is not None:
            kw["json"] = json_body
        if params:
            kw["params"] = params
        if aiohttp is not None:
            kw["timeout"] = aiohttp.ClientTimeout(total=timeout)
        async with session.request(method, url, **kw) as resp:
            body = await resp.read() if want == "bytes" else await resp.text()
            return resp.status, body, dict(getattr(resp, "headers", {}) or {})

    try:
        return await asyncio.wait_for(_do(), timeout + 2)
    except asyncio.TimeoutError:
        raise ProviderError("timeout", f"{provider or url} timed out", provider)
    except ProviderError:
        raise
    except Exception as e:
        raise ProviderError("network", f"{type(e).__name__}", provider)


def _retry_after(headers: dict) -> Optional[float]:
    for k, v in (headers or {}).items():
        if str(k).lower() == "retry-after":
            try:
                return float(v)
            except Exception:
                return None
    return None


_THINK_RE = re.compile(r"<think>.*?</think>", re.S | re.I)


def clean_llm_text(text: Any) -> str:
    """Strip reasoning blocks and stray whitespace from a model reply."""
    if text is None:
        return ""
    if isinstance(text, list):  # content-part arrays
        text = "".join(p.get("text", "") if isinstance(p, dict) else str(p) for p in text)
    text = str(text)
    text = _THINK_RE.sub("", text)
    if "<think>" in text.lower() and "</think>" not in text.lower():  # unterminated
        text = re.split(r"<think>", text, flags=re.I)[0]
    return text.strip()


def parse_json_object(text: str) -> Optional[dict]:
    """Pull the first JSON object out of a model reply (handles ```json fences / chatter)."""
    if not text:
        return None
    text = re.sub(r"```(?:json)?", "", text, flags=re.I)
    start = text.find("{")
    while start != -1:
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    try:
                        obj = json.loads(text[start:i + 1])
                        if isinstance(obj, dict):
                            return obj
                    except Exception:
                        pass
                    break
        start = text.find("{", start + 1)
    return None


# ═══════════════════════════════════════════════════════════════════════════
# Providers + LLM router
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class Provider:
    name: str
    kind: str                      # "openai" | "ollama"
    base_url: str
    api_key: str = ""
    model: str = ""
    vision_model: str = ""
    chat_url: str = ""             # full URL override (used by the keyless endpoint)
    keyless: bool = False

    @property
    def supports_vision(self) -> bool:
        return bool(self.vision_model)


@dataclass
class LLMResult:
    text: str
    provider: str
    model: str
    latency: float = 0.0


def load_providers(guild_cfg: Optional[dict] = None, env: Optional[dict] = None) -> List[Provider]:
    """Build the ordered provider list from environment variables (no keys in code)."""
    env = os.environ if env is None else env
    g = lambda k: (env.get(k) or "").strip()
    out: List[Provider] = []

    if g("AI_API_BASE"):
        out.append(Provider("custom", "openai", g("AI_API_BASE").rstrip("/"), g("AI_API_KEY"),
                            g("AI_MODEL") or "gpt-4o-mini", g("AI_VISION_MODEL") or g("AI_MODEL") or "gpt-4o-mini"))
    presets = [
        ("GROQ_API_KEY", "groq", "https://api.groq.com/openai/v1", "openai/gpt-oss-20b",
         "openai/gpt-oss-120b"),
        ("OPENROUTER_API_KEY", "openrouter", "https://openrouter.ai/api/v1",
         "meta-llama/llama-3.3-70b-instruct:free", "google/gemini-2.0-flash-exp:free"),
        ("GEMINI_API_KEY", "gemini", "https://generativelanguage.googleapis.com/v1beta/openai",
         "gemini-2.0-flash", "gemini-2.0-flash"),
        ("OPENAI_API_KEY", "openai", "https://api.openai.com/v1", "gpt-4o-mini", "gpt-4o-mini"),
    ]
    for key_env, name, base, model, vision in presets:
        if g(key_env):
            out.append(Provider(name, "openai", base, g(key_env), g("AI_MODEL") or model, g("AI_VISION_MODEL") or vision))

    if local_enabled(env):
        out.append(Provider("local", "local", "", "", local_model_name(env), ""))

    cfg = guild_cfg or {}
    ollama_url = (cfg.get("ollama_url") or g("OLLAMA_URL") or "http://127.0.0.1:11434").rstrip("/")
    ollama_model = cfg.get("model_name") or "auto"
    vis = g("AI_OLLAMA_VISION_MODEL")
    if not vis and re.search(r"llava|vision|moondream|minicpm|gemma3|qwen.*vl", ollama_model, re.I):
        vis = ollama_model
    out.append(Provider("ollama", "ollama", ollama_url, "", ollama_model, vis))

    if g("AI_KEYLESS_FALLBACK") == "1":   # opt-in: your users' messages would be sent to a third party
        url = g("AI_KEYLESS_URL") or "https://text.pollinations.ai/openai"
        model = g("AI_KEYLESS_MODEL") or "openai"
        out.append(Provider("keyless", "openai", url, "", model, model, chat_url=url, keyless=True))
    return out


class LLMRouter:
    """Tries providers in order with retries and a circuit breaker."""

    FAIL_THRESHOLD = 2
    COOLDOWN = 60.0
    AUTH_COOLDOWN = 600.0

    def __init__(self, session, env: Optional[dict] = None, local: Optional[LocalLLM] = None):
        self.session = session
        self.env = env
        self._local = local
        self.health: Dict[str, dict] = {}
        self._ollama_models: Dict[str, Tuple[float, List[str]]] = {}
        # Local CPU inference thrashes when run in parallel — queue instead (same cap as before).
        self._ollama_sem = asyncio.Semaphore(2)

    # ── in-process model ────────────────────────────────────────────────
    def local(self) -> LocalLLM:
        if self._local is None:
            self._local = LocalLLM(os.environ if self.env is None else self.env)
        return self._local

    async def preload_local(self):
        """Start downloading/loading the local model in the background (safe to call always)."""
        if any(p.kind == "local" for p in self.providers()):
            await self.local().preload()

    def only_local_compute(self, guild_cfg: Optional[dict] = None) -> bool:
        """True when every usable provider burns this machine's CPU (local model / Ollama)."""
        live = [p for p in self.providers(guild_cfg) if not self.is_down(p.name)]
        return bool(live) and all(p.kind in ("local", "ollama") for p in live)

    # ── provider bookkeeping ────────────────────────────────────────────
    def providers(self, guild_cfg: Optional[dict] = None) -> List[Provider]:
        return load_providers(guild_cfg, self.env)

    def _h(self, name: str) -> dict:
        return self.health.setdefault(name, {"fails": 0, "down_until": 0.0, "last_error": "", "last_ok": 0.0, "ok": 0})

    def is_down(self, name: str) -> bool:
        return self._h(name)["down_until"] > time.monotonic()

    def _mark_ok(self, name: str):
        h = self._h(name)
        h.update(fails=0, down_until=0.0, last_ok=time.time(), last_error="")
        h["ok"] += 1

    def _mark_fail(self, name: str, err: ProviderError):
        h = self._h(name)
        h["fails"] += 1
        h["last_error"] = f"{err.kind}" + (f" ({err.status})" if err.status else "")
        if err.kind == "auth":
            h["down_until"] = time.monotonic() + self.AUTH_COOLDOWN
        elif h["fails"] >= self.FAIL_THRESHOLD:
            h["down_until"] = time.monotonic() + self.COOLDOWN

    def has_available(self, guild_cfg: Optional[dict] = None, *, vision: bool = False) -> bool:
        return any(not self.is_down(p.name) and (p.supports_vision or not vision) for p in self.providers(guild_cfg))

    # ── public API ──────────────────────────────────────────────────────
    async def chat(self, messages: List[dict], *, system: str = "", temperature: float = 0.7,
                   max_tokens: int = 700, json_mode: bool = False, images: Optional[List[Tuple[bytes, str]]] = None,
                   guild_cfg: Optional[dict] = None, timeout: float = 40, what: str = "AI", attempts: int = 2) -> LLMResult:
        provs = self.providers(guild_cfg)
        errors: List[ProviderError] = []
        tried = 0
        for p in provs:
            if images and not p.supports_vision:
                errors.append(ProviderError("unsupported", provider=p.name))
                continue
            if self.is_down(p.name):
                continue
            tried += 1
            for attempt in range(max(1, attempts)):
                t0 = time.monotonic()
                try:
                    text, model = await self._call(p, messages, system, temperature, max_tokens, json_mode, images, timeout, what)
                    self._mark_ok(p.name)
                    return LLMResult(text, p.name, model, time.monotonic() - t0)
                except ProviderError as e:
                    e.provider = e.provider or p.name
                    retryable = e.kind in ("timeout", "server", "rate_limit", "network") and p.kind != "local"
                    if retryable and attempt + 1 < max(1, attempts):
                        await asyncio.sleep(min(e.retry_after or 0.8, 4.0))
                        continue
                    self._mark_fail(p.name, e)
                    errors.append(e)
                    logger.warning(f"[AI] provider {p.name} {e.hint()}" + (f" (HTTP {e.status})" if e.status else ""))
                    break
        raise AllProvidersFailed(errors, configured=len(provs), what=what)

    # ── transport ───────────────────────────────────────────────────────
    async def _call(self, p, messages, system, temperature, max_tokens, json_mode, images, timeout, what="AI") -> Tuple[str, str]:
        if p.kind == "local":
            return await self._call_local(p, messages, system, temperature, max_tokens, json_mode, images, timeout, what)
        if p.kind == "ollama":
            async with self._ollama_sem:
                return await self._call_ollama(p, messages, system, temperature, max_tokens, images, timeout)
        return await self._call_openai(p, messages, system, temperature, max_tokens, json_mode, images, timeout)

    @staticmethod
    def _data_url(img: Tuple[bytes, str]) -> str:
        return f"data:{img[1] or 'image/png'};base64,{base64.b64encode(img[0]).decode()}"

    async def _call_openai(self, p, messages, system, temperature, max_tokens, json_mode, images, timeout):
        msgs: List[dict] = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.extend(dict(m) for m in messages)
        model = p.vision_model if images else p.model
        if images and msgs:
            last = msgs[-1]
            parts = [{"type": "text", "text": str(last.get("content", ""))}]
            parts += [{"type": "image_url", "image_url": {"url": self._data_url(i)}} for i in images]
            msgs[-1] = {"role": last.get("role", "user"), "content": parts}
        body: Dict[str, Any] = {"model": model, "messages": msgs, "temperature": temperature, "max_tokens": max_tokens}
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        headers = {"Content-Type": "application/json"}
        if p.api_key:
            headers["Authorization"] = f"Bearer {p.api_key}"
        url = p.chat_url or f"{p.base_url}/chat/completions"

        for _ in range(2):
            status, raw, hdrs = await http_request(self.session, "POST", url, json_body=body, headers=headers,
                                                   timeout=timeout, provider=p.name)
            if status == 400 and "response_format" in body:   # provider doesn't do JSON mode
                body.pop("response_format")
                continue
            break
        if status != 200:
            raise ProviderError(_classify_status(status), raw[:200] if isinstance(raw, str) else "", p.name, status, _retry_after(hdrs))
        try:
            data = json.loads(raw)
        except Exception:
            # some keyless gateways answer with plain text
            txt = clean_llm_text(raw)
            if txt and not txt.lstrip().startswith("<"):
                return txt, model
            raise ProviderError("bad_response", "not JSON", p.name, status)
        if isinstance(data, dict) and data.get("error") and not data.get("choices"):
            err = data["error"]
            msg = err.get("message", "") if isinstance(err, dict) else str(err)
            kind = "rate_limit" if "rate" in msg.lower() else "bad_response"
            raise ProviderError(kind, msg[:200], p.name, status)
        try:
            ch = data["choices"][0]
            content = (ch.get("message") or {}).get("content")
            if content is None:
                content = ch.get("text")
        except Exception:
            raise ProviderError("bad_response", "no choices", p.name, status)
        text = clean_llm_text(content)
        if not text:
            raise ProviderError("empty", "", p.name, status)
        return text, model

    async def _call_local(self, p, messages, system, temperature, max_tokens, json_mode, images, timeout, what):
        if images:
            raise ProviderError("unsupported", "local model has no vision", p.name)
        env = os.environ if self.env is None else self.env
        msgs: List[dict] = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.extend(dict(m) for m in messages)
        cap = int((env.get("LOCAL_MAX_TOKENS") or "400").strip() or 400)
        # CPU inference is slow: allow much longer than a cloud call, except for the quick intent probe
        limit = timeout if what == "intent" else max(timeout, float((env.get("LOCAL_TIMEOUT") or "120").strip() or 120))
        try:
            text = await self.local().generate(msgs, temperature=temperature, max_tokens=min(max_tokens, cap),
                                               json_mode=json_mode, timeout=limit)
        except LocalLLMError as e:
            raise ProviderError(e.kind if e.kind in ("loading", "busy", "timeout", "not_installed") else "bad_response",
                                str(e)[:200], p.name)
        text = clean_llm_text(text)
        if not text:
            raise ProviderError("empty", "", p.name)
        return text, p.model

    async def _ollama_pick_model(self, p: Provider, timeout: float) -> str:
        if p.model and p.model != "auto":
            return p.model
        cached = self._ollama_models.get(p.base_url)
        if cached and time.monotonic() - cached[0] < 30:
            models = cached[1]
        else:
            status, raw, _ = await http_request(self.session, "GET", f"{p.base_url}/api/tags", timeout=4, provider=p.name)
            if status != 200:
                raise ProviderError(_classify_status(status), "", p.name, status)
            try:
                models = [m["name"] for m in json.loads(raw).get("models", [])]
            except Exception:
                raise ProviderError("bad_response", "tags", p.name)
            self._ollama_models[p.base_url] = (time.monotonic(), models)
        if not models:
            raise ProviderError("not_found", "no models pulled", p.name)
        return models[0]

    async def _call_ollama(self, p, messages, system, temperature, max_tokens, images, timeout):
        model = p.vision_model if images else await self._ollama_pick_model(p, timeout)
        msgs: List[dict] = []
        if system:
            msgs.append({"role": "system", "content": system})
        msgs.extend(dict(m) for m in messages)
        if images and msgs:
            msgs[-1]["images"] = [base64.b64encode(i[0]).decode() for i in images]
        body = {"model": model, "messages": msgs, "stream": False,
                "options": {"temperature": temperature, "num_predict": max_tokens}}
        status, raw, hdrs = await http_request(self.session, "POST", f"{p.base_url}/api/chat", json_body=body,
                                               timeout=max(timeout, 45), provider=p.name)
        if status != 200:
            raise ProviderError(_classify_status(status), raw[:200], p.name, status)
        try:
            text = clean_llm_text(json.loads(raw).get("message", {}).get("content"))
        except Exception:
            raise ProviderError("bad_response", "ollama json", p.name, status)
        if not text:
            raise ProviderError("empty", "", p.name, status)
        return text, model

    def status_rows(self, guild_cfg: Optional[dict] = None) -> List[dict]:
        rows = []
        for p in self.providers(guild_cfg):
            h = self._h(p.name)
            state = "down" if self.is_down(p.name) else ("ok" if h["ok"] else "untested")
            detail = self.local().describe() if p.kind == "local" else ""
            rows.append({"name": p.name, "model": p.model, "vision": p.supports_vision, "keyless": p.keyless,
                         "state": state, "last_error": h["last_error"], "ok_calls": h["ok"], "detail": detail,
                         "local": p.kind == "local"})
        return rows


# ═══════════════════════════════════════════════════════════════════════════
# Language detection / names
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class LangInfo:
    code: str
    name: str
    confidence: float = 0.5


_SCRIPTS = [  # (code, name, (lo, hi))
    ("ml", "Malayalam", (0x0D00, 0x0D7F)), ("hi", "Hindi", (0x0900, 0x097F)), ("ta", "Tamil", (0x0B80, 0x0BFF)),
    ("te", "Telugu", (0x0C00, 0x0C7F)), ("kn", "Kannada", (0x0C80, 0x0CFF)), ("bn", "Bengali", (0x0980, 0x09FF)),
    ("gu", "Gujarati", (0x0A80, 0x0AFF)), ("pa", "Punjabi", (0x0A00, 0x0A7F)), ("ar", "Arabic", (0x0600, 0x06FF)),
    ("he", "Hebrew", (0x0590, 0x05FF)), ("ru", "Russian", (0x0400, 0x04FF)), ("el", "Greek", (0x0370, 0x03FF)),
    ("th", "Thai", (0x0E00, 0x0E7F)), ("ko", "Korean", (0xAC00, 0xD7AF)), ("ja", "Japanese", (0x3040, 0x30FF)),
    ("zh", "Chinese", (0x4E00, 0x9FFF)),
]

_STOP = {
    "en": "the and you that this what with for are was have not can how why please it is of to in do i my me your".split(),
    "es": "el la los las que de y en un una es por con para como pero qué hola gracias quiero puedes".split(),
    "fr": "le la les des est une un que et pour pas vous nous avec dans je bonjour merci peux".split(),
    "de": "der die das und ist nicht ich du wir sie mit für ein eine auf den hallo danke kannst".split(),
    "pt": "o a os as que de e em um uma não para com por você olá obrigado quero pode".split(),
    "it": "il lo la gli che di e un una non per con sono ciao grazie voglio puoi come".split(),
    "id": "yang dan di ini itu dengan untuk tidak saya kamu apa bagaimana tolong terima kasih".split(),
    "tr": "ve bir bu için ben sen ne nasıl değil merhaba teşekkürler lütfen".split(),
    "nl": "de het een en van is niet ik je wij met voor hallo bedankt kun".split(),
}
_LATIN_NAMES = {"en": "English", "es": "Spanish", "fr": "French", "de": "German", "pt": "Portuguese",
                "it": "Italian", "id": "Indonesian", "tr": "Turkish", "nl": "Dutch"}


def detect_language(text: str) -> LangInfo:
    """Script-first, stop-word second. Romanized Hinglish/Manglish are handled by the
    caller (DialectEngine) because they need curated word lists."""
    letters = [c for c in text if c.isalpha()]
    if not letters:
        return LangInfo("en", "English", 0.2)
    counts: Dict[str, int] = {}
    for c in letters:
        o = ord(c)
        for code, _name, (lo, hi) in _SCRIPTS:
            if lo <= o <= hi:
                counts[code] = counts.get(code, 0) + 1
                break
    if counts:
        code = max(counts, key=counts.get)
        if "ja" in counts:                      # kana is decisive even with kanji mixed in
            code = "ja"
        share = counts[code] / len(letters)
        if share >= 0.25 or counts[code] >= 3:
            name = next(n for c, n, _ in _SCRIPTS if c == code)
            return LangInfo(code, name, min(0.99, 0.5 + share / 2))
    words = re.findall(r"[^\W\d_]+", text.lower())
    if not words:
        return LangInfo("en", "English", 0.2)
    scores = {c: sum(1 for w in words if w in sw) for c, sw in _STOP.items()}
    best = max(scores, key=scores.get)
    second = sorted(scores.values())[-2]
    if scores[best] >= 2 and scores[best] > second:
        return LangInfo(best, _LATIN_NAMES[best], min(0.95, 0.4 + 0.1 * scores[best]))
    if scores[best] >= 1 and best == "en":
        return LangInfo("en", "English", 0.5)
    return LangInfo("en", "English", 0.3)


LANG_NAMES: Dict[str, Tuple[str, str]] = {}


def _reg(code: str, english: str, *aliases: str):
    for a in (english.lower(),) + tuple(x.lower() for x in aliases):
        LANG_NAMES[a] = (code, english)


for _args in [
    ("en", "English", "inglés", "ingles", "anglais", "englisch"), ("es", "Spanish", "español", "espanol", "espagnol", "spanisch"),
    ("fr", "French", "français", "francais", "französisch", "frances", "francés"), ("de", "German", "deutsch", "alemán", "allemand", "alemao"),
    ("pt", "Portuguese", "português", "portugues", "portugais"), ("it", "Italian", "italiano", "italien"),
    ("nl", "Dutch", "nederlands"), ("ru", "Russian", "русский", "russe", "ruso"), ("uk", "Ukrainian", "українська"),
    ("pl", "Polish", "polski"), ("tr", "Turkish", "türkçe", "turkce"), ("ar", "Arabic", "العربية", "arabe"),
    ("he", "Hebrew", "עברית"), ("fa", "Persian", "farsi", "فارسی"), ("hi", "Hindi", "हिंदी", "हिन्दी"),
    ("ur", "Urdu", "اردو"), ("bn", "Bengali", "bangla", "বাংলা"), ("ta", "Tamil", "தமிழ்"), ("te", "Telugu", "తెలుగు"),
    ("ml", "Malayalam", "മലയാളം"), ("kn", "Kannada", "ಕನ್ನಡ"), ("mr", "Marathi", "मराठी"), ("gu", "Gujarati", "ગુજરાતી"),
    ("pa", "Punjabi", "ਪੰਜਾਬੀ"), ("ne", "Nepali", "नेपाली"), ("si", "Sinhala"), ("ja", "Japanese", "日本語", "japonais", "japonés"),
    ("ko", "Korean", "한국어", "coréen"), ("zh", "Chinese", "中文", "mandarin", "chinois", "chino"),
    ("id", "Indonesian", "bahasa indonesia"), ("ms", "Malay", "bahasa melayu"), ("th", "Thai", "ไทย"),
    ("vi", "Vietnamese", "tiếng việt"), ("tl", "Filipino", "tagalog"), ("sw", "Swahili"), ("el", "Greek", "ελληνικά"),
    ("sv", "Swedish", "svenska"), ("no", "Norwegian", "norsk"), ("da", "Danish", "dansk"), ("fi", "Finnish", "suomi"),
    ("cs", "Czech", "čeština"), ("hu", "Hungarian", "magyar"), ("ro", "Romanian", "română"),
]:
    _reg(*_args)


def find_language(text: str) -> Optional[Tuple[str, str]]:
    """Find a language name mentioned in `text`; prefers the LAST mention ('... to french')."""
    low = text.lower()
    best: Optional[Tuple[int, Tuple[str, str]]] = None
    for alias, val in LANG_NAMES.items():
        if re.search(r"(?<![\w])" + re.escape(alias) + r"(?![\w])", low):
            pos = low.rfind(alias)
            if best is None or pos > best[0]:
                best = (pos, val)
    return best[1] if best else None


# ═══════════════════════════════════════════════════════════════════════════
# Intent routing (heuristics → LLM classifier)
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class Intent:
    name: str = "chat"
    query: str = ""
    target_language: str = ""
    image_prompt: str = ""
    language: str = ""
    confidence: float = 0.5
    source: str = "default"        # heuristic | llm | default | forced


def _norm(text: str) -> str:
    t = unicodedata.normalize("NFKD", text.lower())
    t = "".join(c for c in t if not unicodedata.combining(c) or ord(c) > 0x0900)  # keep Indic matras
    t = re.sub(r"(.)\1{2,}", r"\1\1", t)      # soooo → soo
    return t


def _tokens(text: str) -> List[str]:
    return re.findall(r"[^\W_]+", _norm(text))


def _fuzzy_has(tokens: List[str], vocab, cutoff: float = 0.84) -> bool:
    vset = set(vocab)
    for t in tokens:
        if t in vset:
            return True
        if len(t) >= 4 and difflib.get_close_matches(t, vset, n=1, cutoff=cutoff):
            return True
    return False


_IMG_VERBS = {"generate", "create", "make", "draw", "paint", "sketch", "imagine", "render", "design", "produce",
              "genera", "dibuja", "crea", "haz", "dessine", "crée", "cree", "génère", "genere", "erstelle", "zeichne",
              "generiere", "gera", "desenha", "disegna", "banao", "banado", "bana", "undakku", "undaakku", "vara", "varaku"}
_IMG_NOUNS = {"image", "images", "picture", "pictures", "pic", "pics", "photo", "photos", "drawing", "art", "artwork",
              "illustration", "wallpaper", "logo", "portrait", "painting", "poster", "avatar", "pfp", "meme",
              "imagen", "imagem", "bild", "foto", "dessin", "image", "immagine", "tasveer", "tasvir", "chitra",
              "ചിത്രം", "फोटो", "तस्वीर", "चित्र", "படம்", "画像", "이미지", "изображение", "картинку", "صورة"}
_DRAW_ONLY = {"draw", "paint", "sketch", "dibuja", "dessine", "zeichne", "desenha", "disegna", "imagine"}
_TRANSLATE = {"translate", "translation", "translator", "traduce", "traducir", "traduire", "traduis", "übersetze",
              "ubersetze", "traduza", "traduzir", "traduci", "anuvad", "tarjuma", "parivarthanam", "vivartanam", "翻译", "翻訳"}
_SUMMARIZE = {"summarize", "summarise", "summary", "tldr", "tl;dr", "recap", "shorten", "resume", "resumen", "résume",
              "zusammenfassung", "zusammenfassen", "sumarizar", "riassumi", "saaransh", "sankshepam"}
_SEARCH = {"search", "google", "lookup", "websearch", "serach", "seach", "bing", "duckduckgo", "buscar", "busca",
           "recherche", "suche", "pesquisar", "cerca", "khoj", "khojo", "thappu", "nokku"}
_FRESH = {"latest", "news", "weather", "forecast", "score", "scores", "price", "prices", "stock", "stocks",
          "release", "released", "trending", "noticias", "actualités", "nachrichten", "mausam", "kaalavastha"}
_FRESH_RE = re.compile(r"\bwho(?:'s| is) the current\b|\bcurrent (?:president|ceo|prime minister|champion|version|price|rate)\b"
                       r"|\bwhat(?:'s| is) happening\b|\bright now\b|\bwho won\b")
_JOKE = {"joke", "jokes", "chiste", "blague", "witz", "mazak", "chutkula"}
_JOKE_VERBS = {"tell", "say", "give", "crack", "make", "got", "have", "para", "sunao", "bolo", "cuéntame", "dis", "erzähl"}
_CODE_WORDS = {"python", "javascript", "typescript", "java", "rust", "golang", "c++", "html", "css", "sql", "bash", "regex",
               "script", "function", "code", "bug", "traceback", "stacktrace", "compile", "debug", "program", "snippet",
               "discord.py", "cog", "api", "json", "docker", "node", "react"}
_CODE_VERBS = {"write", "fix", "debug", "explain", "refactor", "optimize", "convert", "make", "create", "implement",
               "why", "help", "review", "error", "solve"}


def _strip_image_request(text: str) -> str:
    t = text.strip()
    pat = re.compile(
        r"^\s*(?:hey\s+|hi\s+|yo\s+)?(?:please\s+|pls\s+|plz\s+)?(?:can|could|would|will)?\s*(?:you\s+)?(?:please\s+)?"
        r"(?:generate|create|make|draw|paint|sketch|imagine|render|design|produce|show|give|send)\s*(?:me\s+|us\s+)?"
        r"(?:an?\s+|the\s+|some\s+)?(?:(?:image|picture|pic|photo|drawing|art|illustration|wallpaper|logo|portrait|painting|poster)s?\s*)?"
        r"(?:of|showing|with|about|for|:)?\s*", re.I)
    out = pat.sub("", t, count=1).strip(" :,-")
    out = re.sub(r"\b(?:image|picture|pic|photo)\s+(?:banao|undakku|banado)\b", "", out, flags=re.I).strip()
    return out or t


def heuristic_intent(text: str, has_image: bool = False) -> Optional[Intent]:
    """Cheap, multilingual, typo-tolerant first pass. Returns None when unsure."""
    raw = text.strip()
    if not raw:
        return None
    toks = _tokens(raw)
    tokset = set(toks)
    low = _norm(raw)

    # translate: "translate X to Y", "how do you say X in Y", "X in french"
    if _fuzzy_has(toks, _TRANSLATE) or re.search(r"\bhow (?:do|would) (?:you|i) say\b", low) \
            or re.search(r"\bwhat(?:'s| is) .{1,80} in (?:" + "|".join(re.escape(a) for a in sorted(LANG_NAMES, key=len, reverse=True)[:60]) + r")\b", low):
        lang = find_language(raw)
        if lang:
            body = re.sub(r"(?i)\b(?:please\s+)?(?:translate|translation of|how do you say|how would you say)\b", "", raw)
            body = re.sub(r"(?i)\b(?:in|into|to|in to)\s+" + re.escape(next((a for a, v in LANG_NAMES.items() if v == lang and a in low), lang[1])) + r"\b.*$", "", body).strip(" :,-\"'")
            return Intent("translate", query=body or raw, target_language=lang[1], confidence=0.9, source="heuristic")
        if _fuzzy_has(toks, _TRANSLATE):
            return Intent("translate", query=raw, confidence=0.6, source="heuristic")

    # summarize
    if _fuzzy_has(toks, _SUMMARIZE, 0.86) or re.search(r"\bsum (?:it )?up\b|\bin (?:short|brief)\b", low):
        body = re.sub(r"(?i)\b(?:please\s+)?(?:summari[sz]e|summary of|tl;?dr|sum (?:it )?up|recap)\b[:\s,-]*", "", raw, count=1).strip()
        return Intent("summarize", query=body or raw, confidence=0.85, source="heuristic")

    # image generation (verb + noun, or a bare 'draw ...')
    if not has_image or _fuzzy_has(toks, _IMG_VERBS, 0.88):
        verb = _fuzzy_has(toks, _IMG_VERBS, 0.86)
        noun = _fuzzy_has(toks, _IMG_NOUNS, 0.86)
        negative = re.search(r"\b(?:how (?:do|to|can)|what is|explain|tutorial|meaning)\b.*\b(?:draw|paint|make)\b", low)
        if verb and noun and not negative:
            return Intent("image_generate", image_prompt=_strip_image_request(raw), query=raw, confidence=0.9, source="heuristic")
        if tokset & _DRAW_ONLY and len(toks) >= 2 and not negative and toks[0] in _DRAW_ONLY | {"please", "pls", "can", "could", "hey"}:
            return Intent("image_generate", image_prompt=_strip_image_request(raw), query=raw, confidence=0.8, source="heuristic")
        if re.search(r"\b(?:image|photo|picture|pic|tasveer)\s+(?:banao|undakku|undaakku|banado|taru|edo)\b", low):
            return Intent("image_generate", image_prompt=_strip_image_request(raw), query=raw, confidence=0.85, source="heuristic")

    if has_image:
        return Intent("image_understand", query=raw, confidence=0.9, source="heuristic")

    # jokes
    if _fuzzy_has(toks, _JOKE, 0.88) and (tokset & _JOKE_VERBS or len(toks) <= 3):
        return Intent("joke", query=raw, confidence=0.85, source="heuristic")
    if "make me laugh" in low or "oru joke para" in low:
        return Intent("joke", query=raw, confidence=0.9, source="heuristic")

    # code
    if "```" in raw or re.search(r"\btraceback \(most recent|\bdef \w+\(|\bimport \w+|SyntaxError|TypeError|NameError", raw):
        return Intent("code", query=raw, confidence=0.85, source="heuristic")
    if _fuzzy_has(toks, _CODE_VERBS, 0.9) and (tokset & _CODE_WORDS):
        return Intent("code", query=raw, confidence=0.7, source="heuristic")

    # explicit web search / fresh information
    if _fuzzy_has(toks, _SEARCH, 0.86) or re.search(r"\blook (?:it )?up\b|\bfind out\b|\bon the (?:web|internet)\b", low):
        body = re.sub(r"(?i)\b(?:please\s+)?(?:search(?: the web)?(?: for)?|google|look (?:it )?up|find out)\b[:\s,-]*", "", raw, count=1).strip()
        return Intent("web_search", query=body or raw, confidence=0.85, source="heuristic")
    if (tokset & _FRESH) or _FRESH_RE.search(low):
        return Intent("web_search", query=raw, confidence=0.6, source="heuristic")
    return None


class IntentRouter:
    def __init__(self, router: LLMRouter):
        self.router = router

    async def classify(self, text: str, *, has_image: bool = False, history: Optional[List[dict]] = None,
                       guild_cfg: Optional[dict] = None, use_llm: bool = True) -> Intent:
        h = heuristic_intent(text, has_image)
        if h and h.confidence >= 0.8:
            return h
        toks = _tokens(text)
        if not has_image and len(toks) <= 2:
            return h or Intent("chat", query=text, confidence=0.6, source="default")
        env = self.router.env if self.router.env is not None else os.environ
        flag = (env.get("AI_INTENT_LLM") or "").strip()      # "0" off · "1" always · unset = auto
        llm_ok = flag == "1" or (flag != "0" and not self.router.only_local_compute(guild_cfg))
        if use_llm and llm_ok and self.router.has_available(guild_cfg):
            try:
                llm = await self._classify_llm(text, has_image, history or [], guild_cfg)
                if llm:
                    return llm
            except AllProvidersFailed as e:
                logger.info(f"[AI] intent LLM unavailable: {e}")
            except Exception as e:  # never let routing crash a reply
                logger.warning(f"[AI] intent LLM error: {e!r}")
        return h or Intent("chat", query=text, confidence=0.5, source="default")

    async def _classify_llm(self, text, has_image, history, guild_cfg) -> Optional[Intent]:
        tail = "\n".join(f"{m['role']}: {str(m['content'])[:160]}" for m in history[-4:])
        system = (
            "You are the intent router of a Discord assistant. Users write casually: slang, typos, abbreviations, "
            "mixed languages and romanized Hindi/Malayalam/etc. Understand them anyway.\n"
            "Reply with ONE JSON object and nothing else:\n"
            '{"intent": "<chat|image_generate|image_understand|web_search|translate|summarize|code|joke>", '
            '"language": "<user\'s language>", "query": "<the task in the user\'s own words>", '
            '"target_language": "<English name of target language, only for translate>", '
            '"image_prompt": "<detailed ENGLISH image prompt, only for image_generate>"}\n'
            "Rules: image_generate ONLY when the user clearly wants a NEW picture created. "
            f"image_understand ONLY when an image is attached (attached={str(has_image).lower()}) and they ask about it. "
            "web_search when the answer needs current/live facts (news, weather, prices, scores, releases, 'who is the "
            "current…') or they ask to search. translate/summarize/code/joke as named. Everything else is chat. "
            "Use the recent messages to resolve follow-ups such as 'and in French?' or 'make it darker'."
        )
        user = (f"Recent messages:\n{tail}\n\n" if tail else "") + f"New message: {text}"
        res = await self.router.chat([{"role": "user", "content": user}], system=system, temperature=0.0,
                                     max_tokens=220, json_mode=True, guild_cfg=guild_cfg, timeout=8, what="intent", attempts=1)
        obj = parse_json_object(res.text)
        if not obj:
            return None
        name = str(obj.get("intent", "")).strip().lower()
        if name not in INTENTS:
            return None
        if name == "image_understand" and not has_image:
            name = "chat"
        return Intent(name, query=str(obj.get("query") or text), target_language=str(obj.get("target_language") or ""),
                      image_prompt=str(obj.get("image_prompt") or ""), language=str(obj.get("language") or ""),
                      confidence=0.9, source="llm")


async def refine_image_prompt(router: "LLMRouter", text: str, fallback: str, guild_cfg: Optional[dict] = None) -> str:
    """Turn a casual / non-English / romanized request into one clean English image prompt.
    Falls back to `fallback` (the heuristic extraction) if no model is reachable."""
    try:
        res = await router.chat(
            [{"role": "user", "content": text}], guild_cfg=guild_cfg, temperature=0.3, max_tokens=160, timeout=20,
            system=("Convert the user's request into ONE vivid English prompt for an image generator. Describe only the "
                    "picture (subject, setting, style, lighting). Drop chit-chat like 'bro', 'please', 'yaar'. "
                    "Output only the prompt, max 60 words, no quotes."), what="prompt")
        out = res.text.strip().strip('"').strip()
        return out[:600] if out else fallback
    except Exception as e:
        logger.info(f"[AI] image prompt refine skipped: {e}")
        return fallback


# ═══════════════════════════════════════════════════════════════════════════
# Prompt building + memory helpers
# ═══════════════════════════════════════════════════════════════════════════

CORE_RULES = (
    "UNDERSTANDING: Users write casually — slang, typos, abbreviations, emojis, mixed languages. Work out what they mean "
    "instead of asking them to rephrase. Use the earlier messages to resolve 'it', 'that', 'and you?', 'why?' and other "
    "follow-ups. Ask ONE short clarifying question only if the request is genuinely ambiguous.\n"
    "LANGUAGE: Reply in the same language and script as the user's latest message (mirror romanized Hinglish or Manglish "
    "too). If the user asks for a specific language, use that.\n"
    "STYLE: You are chatting on Discord — be natural and concise (under ~1800 characters unless asked for more), use "
    "markdown sparingly, never claim to have done something you cannot do, and say so when you are not sure instead of "
    "guessing facts."
)


def build_system_prompt(persona_prompt: str, mood_prompt: str, user_name: str, lang: Optional[LangInfo] = None,
                        dialect_hint: str = "", server_facts: Optional[List[str]] = None, user_notes: str = "",
                        custom_prompt: str = "", extra: str = "") -> str:
    parts = [custom_prompt.strip() if custom_prompt else f"{persona_prompt} {mood_prompt}".strip()]
    parts.append(f"Today is {datetime.datetime.now(datetime.timezone.utc):%A, %d %B %Y} (UTC). You are talking with {user_name}.")
    parts.append(CORE_RULES)
    if dialect_hint:
        parts.append(dialect_hint)
    elif lang and lang.code != "en" and lang.confidence >= 0.6:
        parts.append(f"The user is writing in {lang.name}; reply in {lang.name}.")
    if user_notes:
        parts.append(f"What you know about {user_name}: {user_notes[:400]}")
    if server_facts:
        parts.append("Facts this server taught you (use if relevant): " + " | ".join(f[:300] for f in server_facts[:3]))
    if extra:
        parts.append(extra)
    return "\n\n".join(p for p in parts if p)


def trim_history(history: List[dict], max_chars: int = 6000, min_keep: int = 2) -> List[dict]:
    """Keep the newest turns that fit a character budget (≈ token budget) — never fewer than min_keep."""
    out: List[dict] = []
    total = 0
    for m in reversed(history):
        c = len(str(m.get("content", "")))
        if total + c > max_chars and len(out) >= min_keep:
            break
        out.append({"role": m["role"], "content": str(m["content"])})
        total += c
    return list(reversed(out))


# ═══════════════════════════════════════════════════════════════════════════
# Web search
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class SearchResult:
    title: str
    url: str
    snippet: str


_DDG_A = re.compile(r'<a[^>]+class="[^"]*result__a[^"]*"[^>]*href="([^"]+)"[^>]*>(.*?)</a>', re.S | re.I)
_DDG_S = re.compile(r'<a[^>]+class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</a>', re.S | re.I)


def _strip_tags(s: str) -> str:
    return html.unescape(re.sub(r"<[^>]+>", "", s)).strip()


def parse_ddg_html(page: str, limit: int = 6) -> List[SearchResult]:
    anchors, snippets = _DDG_A.findall(page), _DDG_S.findall(page)
    out: List[SearchResult] = []
    for i, (href, title) in enumerate(anchors):
        if href.startswith("//"):
            href = "https:" + href
        m = re.search(r"[?&]uddg=([^&]+)", href)
        url = urllib.parse.unquote(m.group(1)) if m else href
        if not url.startswith("http") or "duckduckgo.com/y.js" in url:   # ads
            continue
        out.append(SearchResult(_strip_tags(title), url, _strip_tags(snippets[i]) if i < len(snippets) else ""))
        if len(out) >= limit:
            break
    return out


class WebSearch:
    def __init__(self, session, env: Optional[dict] = None):
        self.session, self.env = session, (os.environ if env is None else env)

    def backends(self) -> List[str]:
        e = self.env
        names = []
        if (e.get("TAVILY_API_KEY") or "").strip():
            names.append("tavily")
        if (e.get("BRAVE_API_KEY") or "").strip():
            names.append("brave")
        if (e.get("SEARXNG_URL") or "").strip():
            names.append("searxng")
        names.append("duckduckgo")
        return names

    async def search(self, query: str, limit: int = 5) -> List[SearchResult]:
        errors: List[str] = []
        for name in self.backends():
            try:
                res = await getattr(self, f"_{name}")(query, limit)
                if res:
                    return res[:limit]
                errors.append(f"{name}: no results")
            except ProviderError as e:
                errors.append(f"{name}: {e.kind}")
            except Exception as e:
                errors.append(f"{name}: {type(e).__name__}")
        raise SearchError("; ".join(errors) or "no search backend")

    async def _tavily(self, q, n):
        st, raw, h = await http_request(self.session, "POST", "https://api.tavily.com/search", timeout=20, provider="tavily",
                                        json_body={"api_key": self.env["TAVILY_API_KEY"].strip(), "query": q, "max_results": n})
        if st != 200:
            raise ProviderError(_classify_status(st), provider="tavily", status=st)
        return [SearchResult(r.get("title", ""), r.get("url", ""), (r.get("content") or "")[:400])
                for r in json.loads(raw).get("results", [])]

    async def _brave(self, q, n):
        st, raw, h = await http_request(self.session, "GET", "https://api.search.brave.com/res/v1/web/search", timeout=15,
                                        params={"q": q, "count": n}, provider="brave",
                                        headers={"X-Subscription-Token": self.env["BRAVE_API_KEY"].strip(), "Accept": "application/json"})
        if st != 200:
            raise ProviderError(_classify_status(st), provider="brave", status=st)
        return [SearchResult(r.get("title", ""), r.get("url", ""), _strip_tags(r.get("description", "")))
                for r in json.loads(raw).get("web", {}).get("results", [])]

    async def _searxng(self, q, n):
        base = self.env["SEARXNG_URL"].strip().rstrip("/")
        st, raw, h = await http_request(self.session, "GET", f"{base}/search", params={"q": q, "format": "json"}, timeout=15, provider="searxng")
        if st != 200:
            raise ProviderError(_classify_status(st), provider="searxng", status=st)
        return [SearchResult(r.get("title", ""), r.get("url", ""), (r.get("content") or "")[:400])
                for r in json.loads(raw).get("results", [])]

    async def _duckduckgo(self, q, n):
        st, raw, h = await http_request(self.session, "GET", "https://html.duckduckgo.com/html/", params={"q": q}, timeout=15,
                                        provider="duckduckgo",
                                        headers={"User-Agent": "Mozilla/5.0 (compatible; DiscordBot/1.0)", "Accept-Language": "en"})
        if st != 200:
            raise ProviderError(_classify_status(st), provider="duckduckgo", status=st)
        return parse_ddg_html(raw, n)


def format_search_context(results: List[SearchResult]) -> str:
    return "\n".join(f"[{i}] {r.title}\n    {r.snippet}\n    {r.url}" for i, r in enumerate(results, 1))


def format_sources(results: List[SearchResult], limit: int = 3) -> str:
    return "\n".join(f"[{i}] <{r.url}>" for i, r in enumerate(results[:limit], 1))


# ═══════════════════════════════════════════════════════════════════════════
# Image generation
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class GeneratedImage:
    data: bytes
    ext: str
    mime: str
    model: str
    backend: str


def sniff_image(data: bytes) -> Optional[Tuple[str, str]]:
    if data[:8] == b"\x89PNG\r\n\x1a\n":
        return "png", "image/png"
    if data[:3] == b"\xff\xd8\xff":
        return "jpg", "image/jpeg"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp", "image/webp"
    if data[:4] in (b"GIF8",):
        return "gif", "image/gif"
    return None


class ImageGenerator:
    MAX_BYTES = 12 * 1024 * 1024

    def __init__(self, session, env: Optional[dict] = None):
        self.session, self.env = session, (os.environ if env is None else env)

    def _g(self, k: str) -> str:
        return (self.env.get(k) or "").strip()

    async def generate(self, prompt: str, width: int = 1024, height: int = 1024, seed: Optional[int] = None,
                       deadline: float = 110.0) -> GeneratedImage:
        t_end = time.monotonic() + deadline
        errors: List[str] = []
        prompt = prompt.strip()[:900]
        if not prompt:
            raise ImageGenError("the prompt was empty.")

        base = self._g("AI_IMAGE_API_BASE") or ("https://api.openai.com/v1" if self._g("OPENAI_API_KEY") else "")
        key = self._g("AI_IMAGE_API_KEY") or self._g("OPENAI_API_KEY")
        if base and key:
            try:
                return await self._openai_images(base, key, prompt, min(60.0, max(5.0, t_end - time.monotonic())))
            except (ProviderError, ImageGenError) as e:
                errors.append(f"api: {getattr(e, 'kind', None) or e}")

        models = [m.strip() for m in (self._g("AI_IMAGE_MODELS") or "flux,turbo").split(",") if m.strip()]
        for model in models:
            for attempt in range(2):
                remaining = t_end - time.monotonic()
                if remaining < 8:
                    break
                try:
                    return await self._pollinations(prompt, width, height, seed, model, min(70.0, remaining))
                except (ProviderError, ImageGenError) as e:
                    kind = getattr(e, "kind", None) or str(e)
                    errors.append(f"{model}: {kind}")
                    if getattr(e, "kind", "") in ("rate_limit", "bad_request"):
                        await asyncio.sleep(1.5)
                    elif attempt == 0:
                        await asyncio.sleep(0.8)
        kinds = " ".join(errors)
        if "rate_limit" in kinds:
            raise ImageGenError("the image service is rate-limited right now. Try again in a minute.")
        if "timeout" in kinds:
            raise ImageGenError("the image service took too long. Try again, or use a simpler prompt.")
        raise ImageGenError("the image service isn't responding right now. Try again shortly.")

    async def _pollinations(self, prompt, w, h, seed, model, timeout) -> GeneratedImage:
        seed = int(time.time() * 1000) % 10_000_000 if seed is None else seed
        url = f"https://image.pollinations.ai/prompt/{urllib.parse.quote(prompt, safe='')}"
        st, body, hdrs = await http_request(self.session, "GET", url, want="bytes", timeout=timeout, provider="pollinations",
                                            params={"width": w, "height": h, "seed": seed, "nologo": "true", "model": model})
        if st != 200:
            raise ProviderError(_classify_status(st), provider="pollinations", status=st)
        return self._validate(body, model, "pollinations")

    async def _openai_images(self, base, key, prompt, timeout) -> GeneratedImage:
        model = self._g("AI_IMAGE_MODEL") or "gpt-image-1"
        size = self._g("AI_IMAGE_SIZE") or "1024x1024"
        body: Dict[str, Any] = {"model": model, "prompt": prompt, "n": 1, "size": size}
        headers = {"Authorization": f"Bearer {key}", "Content-Type": "application/json"}
        for _ in range(2):
            st, raw, hd = await http_request(self.session, "POST", f"{base.rstrip('/')}/images/generations", json_body=body,
                                             headers=headers, timeout=timeout, provider="image-api")
            if st == 400 and "response_format" not in body and model.startswith("dall-e"):
                body["response_format"] = "b64_json"
                continue
            break
        if st != 200:
            raise ProviderError(_classify_status(st), raw[:200], "image-api", st)
        try:
            item = json.loads(raw)["data"][0]
        except Exception:
            raise ProviderError("bad_response", "images json", "image-api", st)
        if item.get("b64_json"):
            return self._validate(base64.b64decode(item["b64_json"]), model, "image-api")
        if item.get("url"):
            st2, data, _ = await http_request(self.session, "GET", item["url"], want="bytes", timeout=timeout, provider="image-api")
            if st2 != 200:
                raise ProviderError(_classify_status(st2), provider="image-api", status=st2)
            return self._validate(data, model, "image-api")
        raise ProviderError("bad_response", "no image in response", "image-api", st)

    def _validate(self, data: bytes, model: str, backend: str) -> GeneratedImage:
        if not data or len(data) < 1500:
            raise ImageGenError("the service returned an empty image.")
        if len(data) > self.MAX_BYTES:
            raise ImageGenError("the generated image was too large.")
        kind = sniff_image(data)
        if not kind:   # HTML / JSON error pages come back with HTTP 200 on some free endpoints
            raise ProviderError("bad_response", "not an image", backend)
        return GeneratedImage(data, kind[0], kind[1], model, backend)


# ═══════════════════════════════════════════════════════════════════════════
# Translation
# ═══════════════════════════════════════════════════════════════════════════

class Translator:
    def __init__(self, router: LLMRouter, session, env: Optional[dict] = None):
        self.router, self.session, self.env = router, session, (os.environ if env is None else env)

    async def translate(self, text: str, target: str, guild_cfg: Optional[dict] = None) -> Tuple[str, str]:
        """Returns (translation, engine). Raises AllProvidersFailed if everything fails."""
        target_info = LANG_NAMES.get(target.lower().strip()) or find_language(target) or (None)
        target_name = target_info[1] if target_info else target.strip().title()
        errors: List[ProviderError] = []
        try:
            res = await self.router.chat(
                [{"role": "user", "content": text}], guild_cfg=guild_cfg, temperature=0.2, max_tokens=900,
                system=(f"You are a precise translation engine. Translate the user's text into {target_name}. "
                        "Keep meaning, tone, slang level, names, emojis and formatting. Output ONLY the translation, "
                        "no notes, no quotes. If the text is already in the target language, output it unchanged."),
                what="translation")
            return res.text, f"LLM · {res.provider}"
        except AllProvidersFailed as e:
            errors = e.errors
        if target_info:
            code = target_info[0]
            lt = (self.env.get("LIBRETRANSLATE_URL") or "").strip().rstrip("/")
            if lt:
                try:
                    body = {"q": text, "source": "auto", "target": code}
                    if (self.env.get("LIBRETRANSLATE_API_KEY") or "").strip():
                        body["api_key"] = self.env["LIBRETRANSLATE_API_KEY"].strip()
                    st, raw, _ = await http_request(self.session, "POST", f"{lt}/translate", json_body=body, timeout=20, provider="libretranslate")
                    if st == 200 and json.loads(raw).get("translatedText"):
                        return json.loads(raw)["translatedText"], "LibreTranslate"
                except Exception as e:
                    logger.info(f"[AI] libretranslate failed: {e!r}")
            if len(text.encode("utf-8")) <= 450:
                try:
                    st, raw, _ = await http_request(self.session, "GET", "https://api.mymemory.translated.net/get", timeout=15,
                                                    params={"q": text, "langpair": f"Autodetect|{code}"}, provider="mymemory")
                    if st == 200:
                        tt = json.loads(raw).get("responseData", {}).get("translatedText", "")
                        if tt and "INVALID" not in tt.upper() and "MYMEMORY WARNING" not in tt.upper():
                            return html.unescape(tt), "MyMemory"
                except Exception as e:
                    logger.info(f"[AI] mymemory failed: {e!r}")
        raise AllProvidersFailed(errors, configured=len(errors) or 1, what="translation")
