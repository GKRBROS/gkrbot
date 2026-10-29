"""
local_llm.py — run a small open-weights model INSIDE the bot process (CPU), no API key and
no separate server.  Used by ai_providers.LLMRouter as provider "local".

Enable with environment variables (nothing is downloaded unless you opt in):
  AI_LOCAL=1                      use the default model (Qwen2.5-1.5B-Instruct, Q4_K_M, ~1 GB)
  LOCAL_MODEL_PATH=/path/x.gguf   use a GGUF file you already have
  LOCAL_MODEL_REPO + LOCAL_MODEL_FILE
                                  download <file> from huggingface.co/<repo> into LOCAL_MODEL_DIR
  LOCAL_MODEL_DIR=./models        where downloads go
  LOCAL_N_CTX=4096                context window (more = more RAM)
  LOCAL_THREADS=<cpu count>       inference threads
  LOCAL_MAX_TOKENS=400            cap on reply length (CPU speed is ~5-15 tokens/s)
  LOCAL_TIMEOUT=120               seconds to wait for one reply
  LOCAL_MAX_QUEUE=4               requests allowed to wait; extra ones are told "busy"
  LOCAL_LOAD_WAIT=20              seconds a request waits for a model that is still loading
  HF_TOKEN                        only for gated/private repos

Requires:  pip install llama-cpp-python   (compiles C++ unless a prebuilt CPU wheel is available)

Design notes
  * llama.cpp contexts are not thread-safe, so ALL generations run on ONE worker thread; the
    asyncio loop is never blocked.
  * The queue is bounded: when the CPU is saturated users get a quick "busy" instead of a
    ten-minute wait.
  * Loading / downloading happens once, in the background; requests that arrive meanwhile wait a
    short time and then fail fast with kind="loading".
"""
from __future__ import annotations

import asyncio
import logging
import os
import threading
import time
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from typing import Callable, List, Optional

logger = logging.getLogger("gkr_ai.local")

DEFAULT_REPO = "Qwen/Qwen2.5-1.5B-Instruct-GGUF"
DEFAULT_FILE = "qwen2.5-1.5b-instruct-q4_k_m.gguf"
MIN_MODEL_BYTES = 50 * 1024 * 1024        # anything smaller is an error page, not a model


class LocalLLMError(Exception):
    """kind: not_installed | loading | busy | timeout | model_error | not_configured"""

    def __init__(self, kind: str, message: str = ""):
        super().__init__(message or kind)
        self.kind = kind


def local_enabled(env) -> bool:
    g = lambda k: (env.get(k) or "").strip()
    return g("AI_LOCAL") == "1" or bool(g("LOCAL_MODEL_PATH")) or bool(g("LOCAL_MODEL_REPO") and g("LOCAL_MODEL_FILE"))


def local_model_name(env) -> str:
    g = lambda k: (env.get(k) or "").strip()
    return os.path.basename(g("LOCAL_MODEL_PATH")) if g("LOCAL_MODEL_PATH") else (g("LOCAL_MODEL_FILE") or DEFAULT_FILE)


def _default_loader(path: str, n_ctx: int, n_threads: int):
    try:
        from llama_cpp import Llama  # type: ignore
    except Exception as e:
        raise LocalLLMError("not_installed", f"llama-cpp-python is not installed ({type(e).__name__})")
    return Llama(model_path=path, n_ctx=n_ctx, n_threads=n_threads, verbose=False)


def _download_file(url: str, dest: str, token: str = "", progress: Optional[Callable[[int, int], None]] = None) -> None:
    """Blocking streamed download to dest (via a .part file so a crash never leaves a half model)."""
    req = urllib.request.Request(url, headers={"User-Agent": "gkr-bot-local-llm/1.0"})
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    part = dest + ".part"
    os.makedirs(os.path.dirname(os.path.abspath(dest)), exist_ok=True)
    with urllib.request.urlopen(req, timeout=60) as resp, open(part, "wb") as out:
        total = int(resp.headers.get("Content-Length") or 0)
        done = 0
        while True:
            block = resp.read(1024 * 1024)
            if not block:
                break
            out.write(block)
            done += len(block)
            if progress:
                progress(done, total)
    os.replace(part, dest)


class LocalLLM:
    def __init__(self, env=None, loader: Optional[Callable] = None, downloader: Optional[Callable] = None):
        self.env = os.environ if env is None else env
        self._loader = loader or _default_loader
        self._downloader = downloader or _download_file
        self._model = None
        self._exec = ThreadPoolExecutor(max_workers=1, thread_name_prefix="local-llm")
        self._load_task: Optional[asyncio.Task] = None
        self._pending = 0
        self._plock = threading.Lock()
        self.state = "idle"            # idle | downloading | loading | ready | error
        self.detail = ""

    # ── configuration ───────────────────────────────────────────────────
    def _g(self, k: str, default: str = "") -> str:
        return (self.env.get(k) or default).strip()

    @property
    def n_ctx(self) -> int:
        return int(self._g("LOCAL_N_CTX", "4096") or 4096)

    @property
    def n_threads(self) -> int:
        return int(self._g("LOCAL_THREADS") or (os.cpu_count() or 2))

    @property
    def max_queue(self) -> int:
        return int(self._g("LOCAL_MAX_QUEUE", "4") or 4)

    def model_name(self) -> str:
        return local_model_name(self.env)

    def _model_path(self) -> str:
        path = self._g("LOCAL_MODEL_PATH")
        if path:
            return path
        folder = self._g("LOCAL_MODEL_DIR") or os.path.join(os.path.dirname(os.path.abspath(__file__)), "models")
        return os.path.join(folder, self.model_name())

    def _download_url(self) -> str:
        repo = self._g("LOCAL_MODEL_REPO") or DEFAULT_REPO
        return f"https://huggingface.co/{repo}/resolve/main/{self.model_name()}"

    # ── loading ─────────────────────────────────────────────────────────
    def _set(self, state: str, detail: str = ""):
        self.state, self.detail = state, detail

    async def _load(self):
        loop = asyncio.get_running_loop()
        path = self._model_path()
        try:
            if not os.path.isfile(path):
                if self._g("LOCAL_MODEL_PATH"):
                    raise LocalLLMError("not_configured", f"LOCAL_MODEL_PATH not found: {path}")
                self._set("downloading", "starting…")
                last = [0.0]

                def progress(done: int, total: int):
                    if time.monotonic() - last[0] > 5:
                        last[0] = time.monotonic()
                        pct = f"{done * 100 // total}%" if total else f"{done // (1024 * 1024)} MB"
                        self.detail = pct
                        logger.info(f"[LocalLLM] downloading {self.model_name()} … {pct}")

                await loop.run_in_executor(None, lambda: self._downloader(self._download_url(), path, self._g("HF_TOKEN"), progress))
                if os.path.getsize(path) < MIN_MODEL_BYTES:
                    os.remove(path)
                    raise LocalLLMError("model_error", "downloaded file is too small to be a model")
            self._set("loading", "reading model into RAM…")
            self._model = await loop.run_in_executor(self._exec, self._loader, path, self.n_ctx, self.n_threads)
            self._set("ready", f"{self.model_name()} · ctx {self.n_ctx} · {self.n_threads} threads")
            logger.info(f"[LocalLLM] ready: {self.detail}")
        except LocalLLMError as e:
            self._set("error", f"{e.kind}: {e}")
            logger.error(f"[LocalLLM] {e.kind}: {e}")
            raise
        except Exception as e:
            self._set("error", f"model_error: {type(e).__name__}: {e}"[:200])
            logger.error(f"[LocalLLM] failed to load: {e!r}")
            raise LocalLLMError("model_error", f"{type(e).__name__}: {e}")

    async def preload(self):
        """Start loading in the background (call at bot start). Never raises."""
        try:
            await self.ensure_ready(wait=3600)
        except Exception:
            pass

    async def ensure_ready(self, wait: float = 20.0):
        if self._model is not None:
            return
        if self._load_task is None or (self._load_task.done() and self._model is None):
            self._load_task = asyncio.create_task(self._load())
        try:
            await asyncio.wait_for(asyncio.shield(self._load_task), wait)
        except asyncio.TimeoutError:
            raise LocalLLMError("loading", f"model is still {self.state} ({self.detail})")

    # ── generation ──────────────────────────────────────────────────────
    def _fit(self, messages: List[dict], max_tokens: int) -> List[dict]:
        """Drop oldest turns so prompt + reply fit the context window (≈3 chars per token, conservative)."""
        budget = max(1000, (self.n_ctx - max_tokens - 64) * 3)
        system = [m for m in messages if m["role"] == "system"]
        rest = [m for m in messages if m["role"] != "system"]
        sys_chars = sum(len(str(m["content"])) for m in system)
        if sys_chars > budget // 2:
            system = [{"role": "system", "content": str(system[0]["content"])[: budget // 2]}] if system else []
            sys_chars = budget // 2
        kept, used = [], sys_chars
        for m in reversed(rest):
            c = len(str(m["content"]))
            if used + c > budget and kept:
                break
            kept.append(m)
            used += c
        last = kept[0] if kept else None            # newest message is never dropped, only shortened
        if last and used > budget:
            kept[0] = {"role": last["role"], "content": str(last["content"])[-max(200, budget - sys_chars):]}
        return system + list(reversed(kept))

    def _dec(self, *_):
        with self._plock:
            self._pending -= 1

    def _run(self, messages, temperature, max_tokens, json_mode):
        kw = dict(messages=self._fit(messages, max_tokens), temperature=temperature, max_tokens=max_tokens)
        try:
            out = self._model.create_chat_completion(**(dict(kw, response_format={"type": "json_object"}) if json_mode else kw))
        except (TypeError, ValueError):
            if not json_mode:
                raise
            out = self._model.create_chat_completion(**kw)      # build without JSON-mode support
        return out["choices"][0]["message"]["content"] or ""

    async def generate(self, messages: List[dict], *, temperature: float = 0.7, max_tokens: int = 400,
                       json_mode: bool = False, timeout: float = 120.0) -> str:
        await self.ensure_ready(wait=float(self._g("LOCAL_LOAD_WAIT", "20") or 20))
        with self._plock:
            if self._pending >= self.max_queue:
                raise LocalLLMError("busy", "too many requests are already waiting for the local model")
            self._pending += 1
        try:
            cf = self._exec.submit(self._run, messages, temperature, max_tokens, json_mode)
        except Exception:
            self._dec()
            raise
        cf.add_done_callback(self._dec)          # runs on completion OR cancellation → counter never leaks
        try:
            return await asyncio.wait_for(asyncio.wrap_future(cf), timeout)
        except asyncio.TimeoutError:
            raise LocalLLMError("timeout", f"no reply within {int(timeout)}s")
        except LocalLLMError:
            raise
        except Exception as e:
            raise LocalLLMError("model_error", f"{type(e).__name__}: {e}")

    def describe(self) -> str:
        return f"{self.state}" + (f" — {self.detail}" if self.detail else "")
