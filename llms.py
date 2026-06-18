"""
LegalEase LLM Module - Centralized LLM Logic
============================================

WHY RAG INSTEAD OF FINE-TUNING?
-------------------------------
RAG (Retrieval-Augmented Generation) is used instead of fine-tuning because:
1. No training required - works immediately with any documents
2. Dynamic updates - add/remove documents without retraining
3. Source attribution - can cite exact document sources
4. Cost effective - no GPU training costs
5. Hallucination control - answers grounded in actual documents

WHY NO FINE-TUNING?
-------------------
Fine-tuning is NOT required because:
1. Legal documents change frequently (new laws, amendments)
2. RAG provides real-time access to current documents
3. Fine-tuning would "bake in" outdated information
4. Prompt engineering controls behavior sufficiently
"""

import logging
import os
import json
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple
from urllib.parse import urlparse

logger = logging.getLogger(__name__)

from dotenv import load_dotenv

_ROOT_DIR = Path(__file__).resolve().parent
load_dotenv(_ROOT_DIR / ".env")
load_dotenv()

try:
    import requests
    REQUESTS_AVAILABLE = True
except ImportError:
    REQUESTS_AVAILABLE = False

DDG_LEGACY = False
ddg = None

try:
    from duckduckgo_search import DDGS
    DDGS_AVAILABLE = True
except ImportError:
    try:
        from ddgs import DDGS  # type: ignore
        DDGS_AVAILABLE = True
    except ImportError:
        DDGS_AVAILABLE = False
        try:
            from duckduckgo_search import ddg
            DDG_LEGACY = True
        except ImportError:
            DDG_LEGACY = False

# SentenceTransformer imported lazily in _try_load_sentence_transformer (keeps API import fast).

# Avoid tokenizer fork warnings and meta-device races on Windows.
os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")
os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
if sys.platform == "win32":
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    os.environ.setdefault("MKL_NUM_THREADS", "1")
    os.environ.setdefault("KMP_DUPLICATE_LIB_OK", "TRUE")
    os.environ.setdefault("CUDA_VISIBLE_DEVICES", "")

_EMBEDDINGS_STATUS: dict = {
    "ready": False,
    "loading": False,
    "error": "",
    "model": "",
    "device": "cpu",
}
_EMBEDDINGS_BG_STARTED = False
_EMBEDDINGS_BG_LOCK = threading.Lock()

# LM Studio Configuration (default: same machine — override LM_STUDIO_URL for a remote server)
DEFAULT_LM_STUDIO_URL = "http://127.0.0.1:1234"
LM_STUDIO_BASE_URL = os.getenv("LM_STUDIO_URL") or os.getenv("LM_STUDIO_BASE_URL") or DEFAULT_LM_STUDIO_URL
LM_STUDIO_MODEL = os.getenv("LM_STUDIO_MODEL") or os.getenv("LLM_MODEL") or "meta-llama-3.1-8b-instruct"
LM_STUDIO_CONNECT_TIMEOUT = float(os.getenv("LM_STUDIO_CONNECT_TIMEOUT", "2.5"))
LM_STUDIO_READ_TIMEOUT = float(os.getenv("LM_STUDIO_READ_TIMEOUT", "180"))

# Ollama configuration (optional local backend)
DEFAULT_OLLAMA_URL = "http://127.0.0.1:11434"
OLLAMA_BASE_URL = os.getenv("OLLAMA_URL") or os.getenv("OLLAMA_BASE_URL") or DEFAULT_OLLAMA_URL
OLLAMA_MODEL = os.getenv("OLLAMA_MODEL") or os.getenv("LLM_MODEL") or "legalease-tuned"
LLM_BACKEND_DEFAULT = (os.getenv("LLM_BACKEND") or "ollama").strip().lower()

# Tavily (preferred web intelligence for legal research)
TAVILY_API_KEY = (os.getenv("TAVILY_API_KEY") or "").strip().strip("\"'")
TAVILY_SEARCH_URL = os.getenv("TAVILY_SEARCH_URL", "https://api.tavily.com/search")
TAVILY_SEARCH_DEPTH = os.getenv("TAVILY_SEARCH_DEPTH", "advanced")
TAVILY_MAX_RESULTS = int(os.getenv("TAVILY_MAX_RESULTS", "8"))
WEB_INTEL_FAST = os.getenv("WEB_INTEL_FAST", "1").lower() in ("1", "true", "yes")
WEB_PREFER_TAVILY_REST = os.getenv("WEB_PREFER_TAVILY_REST", "1").lower() in ("1", "true", "yes")
WEB_SEARCH_MAX_RESULTS = int(os.getenv("WEB_SEARCH_MAX_RESULTS", "6"))
TAVILY_REST_TIMEOUT = float(os.getenv("TAVILY_REST_TIMEOUT", "10"))
TAVILY_MCP_TIMEOUT = float(os.getenv("TAVILY_MCP_TIMEOUT", "8"))
WEB_SKIP_TAVILY_MCP = os.getenv("WEB_SKIP_TAVILY_MCP", "1").lower() in ("1", "true", "yes")

SERP_API_KEY = (os.getenv("SERP_API_KEY") or "").strip().strip("\"'")
SERP_TIMEOUT = float(os.getenv("SERP_TIMEOUT", "10"))
GOOGLE_API_KEY = os.getenv("GOOGLE_API_KEY", "")
GOOGLE_CSE_ID = (
    os.getenv("GOOGLE_CSE_ID")
    or os.getenv("GOOGLE_SEARCH_ENGINE_ID")
    or os.getenv("GOOGLE_CX")
    or ""
)

LEGAL_ONLY_WEB = os.getenv("LEGAL_ONLY_WEB", "1").lower() in {"1", "true", "yes"}
LEGACY_WEB = os.getenv("LEGACY_WEB", "0").lower() in {"1", "true", "yes"}
LEGAL_QUERY_HINTS = (
    "law", "legal", "act", "section", "ipc", "bns", "crpc", "court", "judgment",
    "statute", "contract", "tort", "petition", "fir", "bail", "appeal", "precedent",
    "india", "supreme", "high court", "tribunal", "arbitration", "compliance",
)


def _clean_base_url(base_url: str) -> str:
    """Normalize user-provided LM Studio URLs for Windows/.env friendliness."""
    cleaned = (base_url or LM_STUDIO_BASE_URL).strip().strip("\"'")
    return cleaned.rstrip(" /.,")


def _lmstudio_candidates(base_url: str) -> List[Dict[str, str]]:
    """
    Return supported LM Studio API bases.

    LM Studio shows the server as http://host:1234, while the OpenAI-compatible
    endpoints live under /v1. Some versions also expose native /api/v1 routes,
    so both are probed.
    """
    candidates: List[Dict[str, str]] = []

    def add_candidate(api_base: str, style: str, chat_path: str) -> None:
        item = {"base_url": api_base, "style": style, "chat_path": chat_path}
        if item not in candidates:
            candidates.append(item)

    def add_base(base: str) -> None:
        if base.endswith("/v1"):
            add_candidate(base, "openai", "/chat/completions")
        elif base.endswith("/api/v1"):
            add_candidate(base, "lmstudio", "/chat")
        else:
            add_candidate(f"{base}/v1", "openai", "/chat/completions")
            add_candidate(f"{base}/api/v1", "lmstudio", "/chat")

    base = _clean_base_url(base_url)
    add_base(base)

    parsed = urlparse(base)
    scheme = parsed.scheme or "http"
    port = parsed.port or 1234
    # Try IPv4 loopback when user said "localhost" (avoids some Windows IPv6 resolution issues)
    # or when a remote host was configured but LM Studio is actually running locally.
    if parsed.hostname in {"localhost", "::1"}:
        add_base(f"{scheme}://127.0.0.1:{port}")
    elif parsed.hostname and parsed.hostname not in {"127.0.0.1"}:
        add_base(f"{scheme}://127.0.0.1:{port}")

    return candidates


def _extract_chat_content(result: Dict[str, Any]) -> str:
    """Parse OpenAI-compatible and LM Studio native chat response shapes."""
    if not result:
        return ""

    choices = result.get("choices")
    if isinstance(choices, list) and choices:
        first = choices[0] or {}
        message = first.get("message") if isinstance(first, dict) else None
        if isinstance(message, dict):
            content = message.get("content")
            if isinstance(content, str) and content.strip():
                return content
            if isinstance(content, list):
                # Some providers return structured parts: [{"type":"text","text":"..."}]
                text_parts: List[str] = []
                for part in content:
                    if isinstance(part, dict):
                        txt = part.get("text") or part.get("content")
                        if txt:
                            text_parts.append(str(txt))
                    elif part:
                        text_parts.append(str(part))
                if text_parts:
                    return "\n".join(text_parts).strip()
            if content:
                return str(content)
        if isinstance(first, dict) and first.get("text"):
            return str(first["text"])

    message = result.get("message")
    if isinstance(message, dict) and message.get("content"):
        return str(message["content"])

    for key in ("content", "response", "output_text", "text"):
        if result.get(key):
            return str(result[key])

    return str(result)


class LMStudioClient:
    """
    Client for LM Studio's OpenAI-compatible REST API.
    Uses HTTP requests - NO OpenAI SDK required.
    
    This single client is used for ALL three modes:
    - Mode 1: Knowledge Base (RAG)
    - Mode 2: Open Law Intelligence (Web Search)
    - Mode 3: Jurisprudence Engine (Combined)
    
    Behavior is controlled via prompt engineering, not different models.
    """
    
    def __init__(self, base_url: str = None, model: str = None):
        self.raw_base_url = _clean_base_url(base_url or LM_STUDIO_BASE_URL)
        self.base_url = self.raw_base_url
        self.model = model or LM_STUDIO_MODEL
        self.chat_endpoint = ""
        self.api_style = "openai"
        self.available = False
        self.error_message: Optional[str] = None
        self.probe_errors: List[str] = []
        self.available_models: List[str] = []
        self._check_availability()

    def _check_availability(self):
        """Check if LM Studio is running and accessible."""
        if not REQUESTS_AVAILABLE:
            self.error_message = "Python 'requests' package not installed. Run: pip install requests"
            return

        errors: List[str] = []
        for candidate in _lmstudio_candidates(self.raw_base_url):
            base_url = candidate["base_url"]
            try:
                response = requests.get(f"{base_url}/models", timeout=LM_STUDIO_CONNECT_TIMEOUT)
            except requests.exceptions.ConnectionError as exc:
                # Strip noisy urllib3 trace lines.
                msg = str(exc).split("\n", 1)[0][:200]
                errors.append(f"{base_url}: connection refused ({msg})")
                continue
            except requests.exceptions.Timeout:
                errors.append(f"{base_url}: timed out after {LM_STUDIO_CONNECT_TIMEOUT:.1f}s")
                continue
            except Exception as exc:
                errors.append(f"{base_url}: {exc.__class__.__name__}: {exc}")
                continue

            if response.status_code == 200:
                self.base_url = base_url
                self.api_style = candidate["style"]
                self.chat_endpoint = f"{base_url}{candidate['chat_path']}"
                self.available = True
                self.error_message = None
                self.probe_errors = errors
                try:
                    payload = response.json() or {}
                    if isinstance(payload, dict):
                        items = payload.get("data") or payload.get("models") or []
                        self.available_models = [
                            str(m.get("id") or m.get("name") or m)
                            for m in items
                            if m
                        ]
                except Exception:
                    self.available_models = []
                return

            errors.append(f"{base_url}: HTTP {response.status_code} {response.reason or ''}".strip())

        self.available = False
        self.probe_errors = errors
        self.error_message = (
            "Cannot connect to LM Studio. Ensure the Local Server is running and reachable at "
            f"{self.raw_base_url}. Tried: {'; '.join(errors[:3])}"
        )
    
    def generate(self, prompt: str, temperature: float = 0.7, max_tokens: int = 2048, 
                 system_prompt: str = None,
                 frequency_penalty: float = 0.0, presence_penalty: float = 0.0) -> str:
        """
        Generate text using LM Studio's chat completions endpoint.
        
        Args:
            prompt: User message/question
            temperature: Creativity (0.0-1.0)
            max_tokens: Maximum response length
            system_prompt: Optional system message for behavior control
            frequency_penalty: Reduce token repetition (OpenAI-compatible)
            presence_penalty: Encourage new topics (OpenAI-compatible)
        
        Returns:
            Generated text response
        """
        if not self.available:
            # Try to reconnect
            self._check_availability()
            if not self.available:
                return f"❌ LLM Error: {self.error_message or 'LM Studio not available'}"
        
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False
        }
        if frequency_penalty > 0:
            payload["frequency_penalty"] = min(2.0, frequency_penalty)
        if presence_penalty > 0:
            payload["presence_penalty"] = min(2.0, presence_penalty)
        
        try:
            response = requests.post(
                self.chat_endpoint,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=LM_STUDIO_READ_TIMEOUT
            )
            
            if response.status_code == 200:
                result = response.json()
                return _extract_chat_content(result)
            else:
                return f"❌ LM Studio error at {self.chat_endpoint}: {response.status_code} - {response.text[:500]}"
        
        except requests.exceptions.Timeout:
            return "❌ Request timed out. The query may be too complex."
        except requests.exceptions.ConnectionError:
            self.available = False
            self.error_message = "Connection lost to LM Studio"
            return "❌ Lost connection to LM Studio. Please ensure it's running."
        except Exception as e:
            return f"❌ Generation error: {str(e)}"
    
    def chat(self, messages: List[Dict[str, str]], temperature: float = 0.7,
             max_tokens: int = 2048) -> str:
        """
        Chat with multiple messages (for conversation history).
        
        Args:
            messages: List of {"role": "user/assistant/system", "content": "..."}
            temperature: Creativity
            max_tokens: Max response length
        
        Returns:
            Generated response
        """
        if not self.available:
            self._check_availability()
            if not self.available:
                return f"❌ LLM Error: {self.error_message}"
        
        payload = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
            "max_tokens": max_tokens,
            "stream": False
        }
        
        try:
            response = requests.post(
                self.chat_endpoint,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=LM_STUDIO_READ_TIMEOUT
            )
            
            if response.status_code == 200:
                result = response.json()
                return _extract_chat_content(result)
            else:
                return f"❌ LM Studio error at {self.chat_endpoint}: {response.status_code} - {response.text[:500]}"
        except Exception as e:
            return f"❌ Chat error: {str(e)}"


def is_ollama_error_response(text: str) -> bool:
    """True when the client returned an error string instead of an answer."""
    t = (text or "").strip()
    if not t.startswith("❌"):
        return False
    low = t.lower()
    return "ollama" in low or "llm error" in low or "timed out" in low or "connection" in low


def _ollama_request_options(
    *,
    temperature: float,
    max_tokens: int,
    frequency_penalty: float = 0.0,
) -> Dict[str, Any]:
    """Build Ollama /api/chat options — prefer GPU layers when OLLAMA_NUM_GPU is set."""
    opts: Dict[str, Any] = {
        "temperature": temperature,
        "num_predict": max_tokens,
    }
    num_gpu = (os.getenv("OLLAMA_NUM_GPU") or "").strip()
    if num_gpu:
        try:
            opts["num_gpu"] = int(num_gpu)
        except ValueError:
            pass
    num_ctx = (os.getenv("OLLAMA_NUM_CTX") or "").strip()
    if num_ctx:
        try:
            opts["num_ctx"] = int(num_ctx)
        except ValueError:
            pass
    if frequency_penalty > 0:
        opts["repeat_penalty"] = 1.0 + min(1.5, frequency_penalty)
    try:
        opts["num_gpu"] = int(os.getenv("OLLAMA_NUM_GPU") or opts.get("num_gpu") or 999)
    except (TypeError, ValueError):
        pass
    opts.setdefault("num_thread", int(os.getenv("OLLAMA_NUM_THREAD", "4")))
    return opts


def _extract_ollama_content(result: Dict[str, Any]) -> str:
    """Parse Ollama response payloads from /api/chat and /api/generate."""
    message = result.get("message")
    if isinstance(message, dict) and message.get("content"):
        return str(message["content"])
    if result.get("response"):
        return str(result["response"])
    return str(result)


class OllamaClient:
    """
    Client for Ollama local API.
    Supports /api/chat with fallback to /api/generate.
    """

    def __init__(self, base_url: str = None, model: str = None):
        self.raw_base_url = _clean_base_url(base_url or OLLAMA_BASE_URL)
        self.base_url = self.raw_base_url
        self.model = model or OLLAMA_MODEL
        self.chat_endpoint = f"{self.base_url}/api/chat"
        self.generate_endpoint = f"{self.base_url}/api/generate"
        self.api_style = "ollama"
        self.available = False
        self.error_message: Optional[str] = None
        self.probe_errors: List[str] = []
        self.available_models: List[str] = []
        self._check_availability()

    def _check_availability(self):
        if not REQUESTS_AVAILABLE:
            self.error_message = "Python 'requests' package not installed. Run: pip install requests"
            return

        errors: List[str] = []
        try:
            response = requests.get(f"{self.base_url}/api/tags", timeout=LM_STUDIO_CONNECT_TIMEOUT)
            if response.status_code == 200:
                payload = response.json() or {}
                models = payload.get("models") or []
                self.available_models = [
                    str(item.get("name") or item.get("model") or "")
                    for item in models
                    if item
                ]
                self.available = True
                self.error_message = None
                self.probe_errors = []
                return
            errors.append(f"{self.base_url}/api/tags: HTTP {response.status_code} {response.reason or ''}".strip())
        except requests.exceptions.ConnectionError as exc:
            msg = str(exc).split("\n", 1)[0][:200]
            errors.append(f"{self.base_url}/api/tags: connection refused ({msg})")
        except requests.exceptions.Timeout:
            errors.append(f"{self.base_url}/api/tags: timed out after {LM_STUDIO_CONNECT_TIMEOUT:.1f}s")
        except Exception as exc:
            errors.append(f"{self.base_url}/api/tags: {exc.__class__.__name__}: {exc}")

        self.available = False
        self.probe_errors = errors
        self.error_message = (
            "Cannot connect to Ollama. Ensure Ollama is running and reachable at "
            f"{self.raw_base_url}. Tried: {'; '.join(errors[:3])}"
        )

    def _ensure_available(self) -> Optional[str]:
        if not self.available:
            self._check_availability()
            if not self.available:
                return f"❌ LLM Error: {self.error_message or 'Ollama not available'}"
        return None

    def _ollama_free_vram(self) -> None:
        """Unload loaded models from RAM/VRAM before retry (Ollama keep_alive=0)."""
        if not REQUESTS_AVAILABLE:
            return
        try:
            requests.post(
                self.generate_endpoint,
                json={"model": self.model, "prompt": "", "keep_alive": 0},
                timeout=8,
            )
        except Exception:
            pass

    def generate(self, prompt: str, temperature: float = 0.7, max_tokens: int = 2048,
                 system_prompt: str = None,
                 frequency_penalty: float = 0.0, presence_penalty: float = 0.0) -> str:
        unavailable = self._ensure_available()
        if unavailable:
            return unavailable

        messages: List[Dict[str, str]] = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        opts = _ollama_request_options(
            temperature=temperature,
            max_tokens=max_tokens,
            frequency_penalty=frequency_penalty,
        )
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": opts,
        }

        def _post_chat(pl: Dict[str, Any]) -> requests.Response:
            return requests.post(
                self.chat_endpoint,
                json=pl,
                headers={"Content-Type": "application/json"},
                timeout=LM_STUDIO_READ_TIMEOUT,
            )

        try:
            response = _post_chat(payload)
            if response.status_code == 200:
                return _extract_ollama_content(response.json())

            err_body = (response.text or "")[:800]
            if response.status_code == 500 and "system memory" in err_body.lower():
                self._ollama_free_vram()
                response = _post_chat(payload)
                if response.status_code == 200:
                    return _extract_ollama_content(response.json())

            # Fallback to /api/generate for older Ollama variants.
            fallback_prompt = prompt if not system_prompt else f"{system_prompt}\n\n{prompt}"
            fallback_payload = {
                "model": self.model,
                "prompt": fallback_prompt,
                "stream": False,
                "options": opts,
            }
            fallback = requests.post(
                self.generate_endpoint,
                json=fallback_payload,
                headers={"Content-Type": "application/json"},
                timeout=LM_STUDIO_READ_TIMEOUT,
            )
            if fallback.status_code == 200:
                return _extract_ollama_content(fallback.json())
            mem_hint = ""
            if "system memory" in err_body.lower():
                mem_hint = (
                    " | Tip: restart Ollama with GPU — run scripts\\ollama_gpu_serve.ps1 "
                    "or set OLLAMA_NUM_GPU=999 before ollama serve"
                )
            return (
                f"❌ Ollama error at {self.chat_endpoint}: {response.status_code} - {err_body[:500]} | "
                f"fallback {fallback.status_code}: {fallback.text[:300]}{mem_hint}"
            )
        except requests.exceptions.Timeout:
            return "❌ Request timed out. The query may be too complex."
        except requests.exceptions.ConnectionError:
            self.available = False
            self.error_message = "Connection lost to Ollama"
            return "❌ Lost connection to Ollama. Please ensure it's running."
        except Exception as exc:
            return f"❌ Generation error: {exc}"

    def chat(self, messages: List[Dict[str, str]], temperature: float = 0.7,
             max_tokens: int = 2048) -> str:
        unavailable = self._ensure_available()
        if unavailable:
            return unavailable

        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": _ollama_request_options(
                temperature=temperature,
                max_tokens=max_tokens,
            ),
        }
        try:
            response = requests.post(
                self.chat_endpoint,
                json=payload,
                headers={"Content-Type": "application/json"},
                timeout=LM_STUDIO_READ_TIMEOUT,
            )
            if response.status_code == 200:
                return _extract_ollama_content(response.json())
            if response.status_code == 500 and "system memory" in (response.text or "").lower():
                self._ollama_free_vram()
                response = requests.post(
                    self.chat_endpoint,
                    json=payload,
                    headers={"Content-Type": "application/json"},
                    timeout=LM_STUDIO_READ_TIMEOUT,
                )
                if response.status_code == 200:
                    return _extract_ollama_content(response.json())
            return f"❌ Ollama chat error at {self.chat_endpoint}: {response.status_code} - {response.text[:500]}"
        except Exception as exc:
            return f"❌ Chat error: {exc}"


# Legacy LLMProvider class for backward compatibility
class LLMProvider:
    """
    Backward-compatible wrapper around LMStudioClient.
    Maintains same interface as original code.
    """
    
    def __init__(self, backend: str = "lmstudio", model_name: Optional[str] = None, hf_token: Optional[str] = None):
        self.backend = backend
        self.model_name = model_name or LM_STUDIO_MODEL
        self.client = LMStudioClient(model=self.model_name)
        self.available = self.client.available
        self.error_message = self.client.error_message
    
    def generate(self, prompt: str, temperature: float = 0.7, max_tokens: int = 2048) -> str:
        """Generate text from prompt using LM Studio."""
        return self.client.generate(prompt, temperature=temperature, max_tokens=max_tokens)


# Global client pool (keyed by backend+url+model — supports per-user tuned models)
_clients: dict[str, Any] = {}
_clients_lock = threading.Lock()

USE_TRAINED_ADAPTER = os.getenv("LLM_USE_TRAINED_ADAPTER", "1").lower() in {"1", "true", "yes"}


class PeftLLMClient:
    """Local HF + LoRA adapter client for in-app fine-tuned chat weights."""

    def __init__(self, base_model: str, adapter_path: str):
        self.base_model = base_model
        self.adapter_path = adapter_path
        self.model = None
        self.tokenizer = None
        self.available = False
        self.error_message = ""
        try:
            import torch
            from peft import PeftModel
            from transformers import AutoModelForCausalLM, AutoTokenizer

            self.tokenizer = AutoTokenizer.from_pretrained(adapter_path, trust_remote_code=True)
            if self.tokenizer.pad_token is None:
                self.tokenizer.pad_token = self.tokenizer.eos_token
            base = AutoModelForCausalLM.from_pretrained(
                base_model,
                torch_dtype=torch.float16 if torch.cuda.is_available() else torch.float32,
                trust_remote_code=True,
                low_cpu_mem_usage=False,
                device_map=None,
            )
            if torch.cuda.is_available():
                base = base.to("cuda")
            self.model = PeftModel.from_pretrained(base, adapter_path)
            self.model.eval()
            self.available = True
        except Exception as exc:
            self.error_message = str(exc)[:300]

    def generate(
        self,
        prompt: str,
        temperature: float = 0.7,
        max_tokens: int = 2048,
        system_prompt: str = "",
        frequency_penalty: float = 0.0,
        presence_penalty: float = 0.0,
    ) -> str:
        if not self.available or self.model is None or self.tokenizer is None:
            return f"❌ Trained adapter unavailable: {self.error_message or 'not loaded'}"
        try:
            import torch

            full_prompt = prompt
            if system_prompt:
                full_prompt = f"{system_prompt}\n\n{prompt}"
            inputs = self.tokenizer(full_prompt, return_tensors="pt", truncation=True, max_length=2048)
            if torch.cuda.is_available():
                inputs = {k: v.cuda() for k, v in inputs.items()}
            with torch.no_grad():
                out = self.model.generate(
                    **inputs,
                    max_new_tokens=max_tokens,
                    temperature=max(0.05, temperature),
                    do_sample=temperature > 0.05,
                    pad_token_id=self.tokenizer.pad_token_id,
                    repetition_penalty=1.0 + min(1.2, frequency_penalty),
                )
            text = self.tokenizer.decode(out[0], skip_special_tokens=True)
            if full_prompt in text:
                text = text.split(full_prompt, 1)[-1].strip()
            return text.strip()
        except Exception as exc:
            return f"❌ Adapter generation error: {exc}"


def get_generator(
    model: str = None,
    backend: Optional[str] = None,
    base_url: str = None,
    user_id: str = "",
):
    """
    Returns the LM Studio / Ollama client instance.

    Per-user tuned Ollama models are resolved when user_id or request context is set.
    """
    try:
        from backend.app.core.request_context import get_user_context

        uid = str(user_id or get_user_context() or "")
    except Exception:
        uid = str(user_id or "")

    if USE_TRAINED_ADAPTER and uid:
        try:
            from backend.app.core.llm_finetuning import BASE_MODEL, get_active_adapter_path

            adapter = get_active_adapter_path(uid)
            if adapter:
                cache_key = f"peft|{BASE_MODEL}|{adapter}"
                with _clients_lock:
                    client = _clients.get(cache_key)
                    if client is None or not isinstance(client, PeftLLMClient):
                        client = PeftLLMClient(BASE_MODEL, adapter)
                        _clients[cache_key] = client
                    if client.available:
                        return client
        except Exception:
            pass

    selected_backend = (backend or os.getenv("LLM_BACKEND") or LLM_BACKEND_DEFAULT or "ollama").strip().lower()
    if selected_backend not in {"lmstudio", "ollama"}:
        selected_backend = "ollama"

    if selected_backend == "ollama":
        # KB chat always uses OLLAMA_MODEL (legalease-tuned) unless caller passes an explicit model.
        desired_model = model or OLLAMA_MODEL
        if not model:
            try:
                from backend.app.core.improvement_automation import AUTO_USE_TUNED, get_active_tuned_model_name

                if AUTO_USE_TUNED and uid:
                    tuned = get_active_tuned_model_name(uid)
                    if tuned:
                        desired_model = tuned
            except Exception:
                pass
        if not model and os.getenv("OLLAMA_KB_LOCK_MODEL", "1").lower() in {"1", "true", "yes"}:
            desired_model = OLLAMA_MODEL
        desired_base_url = _clean_base_url(base_url or OLLAMA_BASE_URL)
        cache_key = f"ollama|{desired_base_url}|{desired_model}"
        with _clients_lock:
            client = _clients.get(cache_key)
            if (
                client is None
                or not isinstance(client, OllamaClient)
                or client.model != desired_model
                or getattr(client, "raw_base_url", None) != desired_base_url
            ):
                client = OllamaClient(base_url=desired_base_url, model=desired_model)
                _clients[cache_key] = client
            # region agent log
            try:
                from backend.app.core.kb_runtime_debug import kb_runtime_log

                kb_runtime_log(
                    "D",
                    "llms.py:get_generator",
                    "ollama_client",
                    {
                        "model": desired_model,
                        "explicit_model_arg": bool(model),
                        "uid": str(uid)[:12],
                    },
                )
            except Exception:
                pass
            # endregion
            return client

    desired_model = model or LM_STUDIO_MODEL
    desired_base_url = _clean_base_url(base_url or LM_STUDIO_BASE_URL)
    cache_key = f"lmstudio|{desired_base_url}|{desired_model}"
    with _clients_lock:
        client = _clients.get(cache_key)
        if (
            client is None
            or not isinstance(client, LMStudioClient)
            or client.model != desired_model
            or getattr(client, "raw_base_url", None) != desired_base_url
        ):
            client = LMStudioClient(base_url=desired_base_url, model=desired_model)
            _clients[cache_key] = client
        return client


def reset_generator() -> None:
    """Force the next LLM call/status check to create fresh clients."""
    global _clients
    with _clients_lock:
        _clients = {}


class TextGenerator:
    """Legacy wrapper for backward compatibility"""
    def __init__(self, model_name: str = None):
        self.model_name = model_name or LM_STUDIO_MODEL
        self.provider = get_generator(model_name)
        self.available = self.provider.available
    
    def generate(self, prompt: str) -> str:
        return self.provider.generate(prompt)


def clear_embeddings_cache(user_id: str = "", *, mark_offline: bool = False) -> None:
    from backend.app.core.embedding_manager import get_manager

    get_manager().clear_embeddings_cache(mark_offline=mark_offline)


def get_embeddings_status() -> dict:
    from backend.app.core.embedding_manager import get_embeddings_status as _st

    return _st()


def ensure_embeddings_background() -> bool:
    from backend.app.core.embedding_manager import ensure_embeddings_background as _start

    return _start()


def ensure_ollama_background() -> bool:
    from backend.app.core.ollama_manager import ensure_ollama_background as _start

    return _start()


def get_ollama_runtime_status() -> dict:
    from backend.app.core.ollama_manager import get_ollama_status

    return get_ollama_status()


def get_embeddings(model: str = "sentence-transformers/all-MiniLM-L6-v2", user_id: str = ""):
    """Return singleton SentenceTransformer via EmbeddingManager."""
    from backend.app.core.embedding_manager import get_manager

    mgr = get_manager()
    mgr.start_background_load()
    return mgr.get_model(user_id=user_id, wait_timeout=float(os.getenv("EMBEDDING_MODEL_LOAD_TIMEOUT_SEC", "90")) + 60)


def warmup_embeddings(model: str | None = None) -> bool:
    from backend.app.core.embedding_manager import warmup_embeddings as _w

    return _w(model)


def warmup_reranker() -> bool:
    """Pre-load cross-encoder reranker when enabled."""
    if os.getenv("RAG_ENABLE_CROSS_ENCODER", "0").lower() not in {"1", "true", "yes"}:
        return True
    try:
        from rag import warmup_rag_reranker

        return warmup_rag_reranker()
    except Exception as exc:
        logger.warning("Reranker warmup skipped: %s", exc)
        return False


def warmup_rag_stack() -> dict:
    """Load all local ML models used by KB retrieval."""
    emb = warmup_embeddings()
    rerank = warmup_reranker()
    return {"embeddings_ok": emb, "reranker_ok": rerank, "embeddings": get_embeddings_status()}


# Web search cache
_web_cache: Dict[str, List[Dict[str, Any]]] = {}


def clear_web_search_cache() -> None:
    """Drop cached web results (e.g. after .env changes or failed Tavily runs)."""
    _web_cache.clear()


def _web_results_cacheable(results: List[Dict[str, Any]]) -> bool:
    if not results:
        return False
    if len(results) == 1:
        provider = (results[0].get("provider") or "").strip()
        if provider in ("Unavailable", "LegalEase"):
            return False
    return True


def _looks_legal_query(query: str, conversation_history: Optional[List] = None) -> bool:
    from legal_web_query import looks_legal_query_for_web

    return looks_legal_query_for_web(query, conversation_history)


def _filter_legal_results(rows: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Legacy hard filter — prefer _soft_legal_rerank for search_web."""
    return _soft_legal_rerank(rows)


def _soft_legal_rerank(
    rows: List[Dict[str, Any]],
    query: str = "",
) -> List[Dict[str, Any]]:
    """
    Stage 2: rerank broad web results by legal relevance + trust — do NOT hard-drop.
    """
    if not rows:
        return rows

    legal_hints = LEGAL_QUERY_HINTS + (
        "lawyer", "litigation", "plaintiff", "defendant", "verdict", "ruling",
        "guidelines", "judgment", "judgement", "supreme court", "high court",
        "section", "act", "statute", "bns", "ipc", "crpc",
    )
    ql = (query or "").lower()

    def score_row(row: Dict[str, Any]) -> Tuple[int, int, int]:
        blob = " ".join(
            str(row.get(k, "") or "") for k in ("title", "body", "href")
        ).lower()
        legal_hits = sum(1 for h in legal_hints if h in blob)
        query_hits = sum(1 for w in ql.split() if len(w) > 3 and w in blob)
        try:
            from legal_web_engine import source_trust_tier

            tier = source_trust_tier(str(row.get("href", "")))
        except Exception:
            tier = 3
        return (-legal_hits - query_hits, tier, -len(blob))

    ranked = sorted(rows, key=score_row)
    return ranked


def _search_tavily_mcp(
    query: str,
    max_results: int,
    conversation_history: Optional[List] = None,
) -> List[Dict[str, Any]]:
    """Tavily remote MCP — preferred for strict legal web intelligence."""
    try:
        from tavily_mcp import search_legal_mcp

        return search_legal_mcp(
            query, max_results=max_results, conversation_history=conversation_history
        )
    except Exception:
        return []


def _search_tavily(query: str, max_results: int) -> List[Dict[str, Any]]:
    """Tavily REST — open web search (no include_domains restriction)."""
    if not TAVILY_API_KEY or not REQUESTS_AVAILABLE:
        return []
    q = (query or "").strip()[:480]
    if not q:
        return []
    depth = "basic" if WEB_INTEL_FAST else TAVILY_SEARCH_DEPTH
    payload = {
        "api_key": TAVILY_API_KEY,
        "query": q,
        "search_depth": depth,
        "max_results": max(1, min(max_results, TAVILY_MAX_RESULTS, WEB_SEARCH_MAX_RESULTS)),
        "include_answer": False,
        "topic": "general",
    }
    try:
        response = requests.post(TAVILY_SEARCH_URL, json=payload, timeout=TAVILY_REST_TIMEOUT)
        if response.status_code != 200:
            logger.warning(
                "Tavily search failed (%s): %s",
                response.status_code,
                (response.text or "")[:400],
            )
            return []
        data = response.json()
        rows = []
        for item in data.get("results", [])[:max_results]:
            rows.append({
                "title": item.get("title", ""),
                "href": item.get("url", ""),
                "body": item.get("content", "") or item.get("snippet", ""),
                "date": datetime.now(timezone.utc).date().isoformat(),
                "provider": "Tavily",
            })
        return rows
    except Exception as exc:
        logger.warning("Tavily search error: %s", exc)
        return []


def web_search_status() -> Dict[str, Any]:
    gemini: Dict[str, Any] = {}
    try:
        from backend.app.core.web_intelligence import web_intel_status

        gemini = web_intel_status()
    except Exception:
        gemini = {"gemini_configured": False}

    if gemini.get("gemini_configured"):
        return {
            **gemini,
            "legal_only_web": LEGAL_ONLY_WEB,
            "preferred_order": "Gemini Grounded Search (google-genai)",
            "tavily_configured": False,
            "serp_configured": False,
            "google_configured": False,
            "ddgs_available": False,
        }

    try:
        from backend.app.core.serp_search import serp_configured
        serp_ok = serp_configured()
    except Exception:
        serp_ok = bool(SERP_API_KEY)
    status = {
        **gemini,
        "tavily_configured": bool(TAVILY_API_KEY),
        "serp_configured": serp_ok,
        "google_configured": bool(GOOGLE_API_KEY and GOOGLE_CSE_ID),
        "ddgs_available": DDGS_AVAILABLE,
        "legal_only_web": LEGAL_ONLY_WEB,
        "tavily_endpoint": TAVILY_SEARCH_URL,
        "tavily_mcp": False,
        "tavily_domain_restricted": False,
        "preferred_order": "Gemini (not configured) -> Tavily -> SerpAPI -> Google CSE -> DuckDuckGo",
    }
    try:
        from tavily_mcp import mcp_status

        ms = mcp_status()
        status["tavily_mcp"] = ms.get("api_key_configured", False)
        status["tavily_mcp_url"] = ms.get("mcp_url", "")
        status["tavily_domain_restricted"] = ms.get("domain_restricted", False)
    except Exception:
        pass
    return status


def search_web(
    query: str,
    max_results: int = 5,
    conversation_history: Optional[List] = None,
    *,
    skip_gemini: bool = False,
) -> List[Dict[str, Any]]:
    """
    Search the web. Tavily is preferred when configured.
    
    Used by:
    - Mode 2: Open Law Intelligence
    - Mode 3: Jurisprudence Engine (combined with RAG)
    
    Returns list of {title, href, body, date, provider}.
    """
    from legal_web_query import enrich_web_query, looks_legal_query_for_web, search_api_query

    effective_query = enrich_web_query(query, conversation_history)
    api_query = search_api_query(query, conversation_history)
    bare_query = (query or "").strip()

    try:
        from backend.app.core.web_intelligence import gemini_configured, grounded_search_snippets

        if not skip_gemini and gemini_configured():
            return grounded_search_snippets(
                api_query or bare_query,
                max_results=max_results,
                conversation_history=conversation_history,
            )
    except Exception as exc:
        logger.warning("Gemini grounded snippets failed: %s", exc)

    # When Gemini is configured but failed (quota/network), always fall through to
    # Tavily / DuckDuckGo — never dead-end with "configure Tavily" only.

    if LEGAL_ONLY_WEB and not looks_legal_query_for_web(effective_query, conversation_history):
        return [{
            "title": "Legal-only web intelligence",
            "href": "",
            "body": (
                "Open Law Intelligence answers legal questions only. "
                "Rephrase with legal context (statute, section, case, court, contract, etc.)."
            ),
            "date": datetime.now(timezone.utc).date().isoformat(),
            "provider": "LegalEase",
        }]

    cache_key = f"{api_query}|{max_results}|{bare_query}"
    if cache_key in _web_cache:
        cached = _web_cache[cache_key]
        if _web_results_cacheable(cached):
            return cached
        del _web_cache[cache_key]
    
    results: List[Dict[str, Any]] = []
    broad_cap = min(max(max_results * 2, max_results), 12)

    # Stage 1: broad retrieve (more results, no hard filter)
    if WEB_PREFER_TAVILY_REST:
        results = _search_tavily(api_query, broad_cap)
        if not results and api_query != (query or "").strip():
            results = _search_tavily((query or "").strip(), broad_cap)
        if not results and not WEB_SKIP_TAVILY_MCP:
            results = _search_tavily_mcp(api_query, broad_cap, conversation_history)
    else:
        if not WEB_SKIP_TAVILY_MCP:
            results = _search_tavily_mcp(api_query, broad_cap, conversation_history)
        if not results:
            results = _search_tavily(api_query, broad_cap)
        if not results and api_query != (query or "").strip():
            results = _search_tavily((query or "").strip(), broad_cap)

    if results and results[0].get("provider") == "LegalEase":
        return results

    # Stage 2: soft legal rerank (boost legal sources, keep broad coverage)
    results = _soft_legal_rerank(results, api_query or effective_query)
    try:
        from legal_web_engine import rank_legal_snippets

        results = rank_legal_snippets(results, bare_query)
    except Exception:
        pass
    results = results[:max_results]

    cap = min(max_results, WEB_SEARCH_MAX_RESULTS)

    # Fallback: SerpAPI (Google results via SERP_API_KEY) — fast when Tavily empty/fails.
    if not results:
        try:
            from backend.app.core.serp_search import search_serp

            results = search_serp(api_query, cap)
            if not results and api_query != (query or "").strip():
                results = search_serp((query or "").strip(), cap)
            if results:
                results = _soft_legal_rerank(results, api_query or effective_query)
                try:
                    from legal_web_engine import rank_legal_snippets

                    results = rank_legal_snippets(results, bare_query)
                except Exception:
                    pass
                results = results[:max_results]
        except Exception:
            results = []

    # Fallback: Google Custom Search JSON API.
    if not results and GOOGLE_API_KEY and GOOGLE_CSE_ID and REQUESTS_AVAILABLE:
        try:
            response = requests.get(
                "https://www.googleapis.com/customsearch/v1",
                params={
                    "key": GOOGLE_API_KEY,
                    "cx": GOOGLE_CSE_ID,
                    "q": api_query,
                    "num": max(1, min(max_results, 10)),
                    "safe": "active",
                },
                timeout=15,
            )
            if response.status_code == 200:
                data = response.json()
                for item in data.get("items", [])[:max_results]:
                    results.append({
                        "title": item.get("title", ""),
                        "href": item.get("link", ""),
                        "body": item.get("snippet", ""),
                        "date": datetime.now(timezone.utc).date().isoformat(),
                        "provider": "Google Custom Search",
                    })
            elif response.status_code in {400, 403}:
                results.append({
                    "title": "Google Custom Search configuration error",
                    "href": "",
                    "body": (
                        "Google search is enabled but the API key or search engine ID was rejected. "
                        "Set GOOGLE_API_KEY and GOOGLE_CSE_ID in .env."
                    ),
                    "date": datetime.now(timezone.utc).date().isoformat(),
                    "provider": "Google Custom Search",
                })
        except Exception:
            results = []
    
    # Try new DDGS API first
    if not results and DDGS_AVAILABLE:
        try:
            with DDGS() as ddgs:
                search_results = list(ddgs.text(api_query, max_results=max_results))
                for r in search_results:
                    results.append({
                        "title": r.get("title", ""),
                        "href": r.get("href", r.get("link", "")),
                        "body": r.get("body", r.get("snippet", "")),
                        "date": datetime.now(timezone.utc).date().isoformat(),
                        "provider": "DuckDuckGo",
                    })
        except Exception as e:
            pass
    
    # Try legacy ddg function
    if not results and DDG_LEGACY and ddg:
        try:
            raw_results = ddg(api_query, max_results=max_results) or []
            for r in raw_results:
                if isinstance(r, dict):
                    results.append({
                        "title": r.get("title", ""),
                        "href": r.get("href", ""),
                        "body": r.get("body", ""),
                        "date": r.get("date", datetime.now(timezone.utc).date().isoformat()),
                        "provider": "DuckDuckGo",
                    })
        except Exception:
            pass
    
    # Fallback: HTTP scraping
    if not results and REQUESTS_AVAILABLE:
        try:
            search_url = f"https://html.duckduckgo.com/html/?q={query.replace(' ', '+')}"
            response = requests.get(search_url, timeout=10, headers={
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
            })
            # Return placeholder if scraping succeeds
            if response.status_code == 200:
                results = [{
                    "title": f"Web search: {query}",
                    "href": search_url,
                    "body": (
                        f"Search results for: {query}. Configure GOOGLE_API_KEY and GOOGLE_CSE_ID "
                        "for production Google search."
                    ),
                    "date": datetime.now(timezone.utc).date().isoformat(),
                    "provider": "DuckDuckGo HTML",
                }]
        except Exception:
            pass
    
    if not results:
        results = _filter_legal_results(results)

    # Last resort
    if not results:
        results = [{
            "title": "Web search unavailable",
            "href": "",
            "body": (
                "Web search returned no results. Check TAVILY_API_KEY and SERP_API_KEY in .env, "
                "then restart the backend."
            ),
            "date": datetime.now(timezone.utc).date().isoformat(),
            "provider": "Unavailable",
        }]
    
    if _web_results_cacheable(results):
        _web_cache[cache_key] = results
    return results


def generator_status(model: str = None) -> Dict[str, Any]:
    """Return status metadata for UI (availability, model name)."""
    client = get_generator(model)
    client._check_availability()
    available_models = list(getattr(client, "available_models", []) or [])
    model_loaded = (not available_models) or (client.model in available_models)
    backend_name = "Ollama" if isinstance(client, OllamaClient) else "LM Studio"
    return {
        "model": client.model,
        "available": client.available,
        "backend": backend_name,
        "base_url": client.base_url,
        "configured_url": client.raw_base_url,
        "chat_endpoint": client.chat_endpoint,
        "message": f"{backend_name} connected" if client.available else f"{backend_name} not available: {client.error_message}",
        "probe_errors": list(getattr(client, "probe_errors", []) or []),
        "available_models": available_models,
        "model_loaded": bool(model_loaded),
    }


# Convenience function for direct generation
def generate_response(prompt: str, system_prompt: str = None, temperature: float = 0.7, 
                      max_tokens: int = 2048) -> str:
    """
    Direct generation function for use in app.py
    
    Args:
        prompt: The user query/prompt
        system_prompt: Optional system message
        temperature: Creativity level
        max_tokens: Max response length
    
    Returns:
        Generated text
    """
    client = get_generator()
    return client.generate(prompt, temperature=temperature, max_tokens=max_tokens, 
                          system_prompt=system_prompt)


# ========================================
# ADVANCED LLM FUNCTIONS FOR ALL FEATURES
# ========================================

def generate_legal_draft(draft_type: str, context: Dict[str, Any]) -> str:
    """
    Generate legal document drafts using LM Studio.
    Supports: Legal Notice, Affidavit, Chargesheet, Contract, Bail Application, etc.
    """
    client = get_generator()
    
    system_prompt = """You are an expert Indian legal document drafter. 
Generate professional, legally valid documents following Indian legal standards.
Use formal legal language and proper formatting."""

    prompt = f"""Generate a professional {draft_type} document with the following details:

Details provided:
{json.dumps(context, indent=2)}

Requirements:
1. Use proper legal formatting and language
2. Include all necessary sections for a valid {draft_type}
3. Use placeholder [BLANK] for any missing required information
4. Follow Indian legal document standards
5. Include relevant BNS/IPC sections where applicable

Generate the complete {draft_type}:"""

    return client.generate(prompt, system_prompt=system_prompt, temperature=0.3, max_tokens=2048)


def analyze_contract(contract_text: str) -> str:
    """
    AI Contract Review - Analyze contracts for risks and compliance.
    """
    client = get_generator()
    
    prompt = f"""You are an expert contract analyst. Analyze the following contract and provide a detailed review.

CONTRACT TEXT:
{contract_text[:8000]}

Provide analysis in this format:

## CONTRACT ANALYSIS REPORT

### 1. DOCUMENT SUMMARY
Brief overview of the contract type and parties.

### 2. KEY TERMS IDENTIFIED
List important terms, dates, and obligations.

### 3. RISK ASSESSMENT
⚠️ HIGH RISK CLAUSES:
[List any clauses that pose significant legal/financial risk]

⚡ MEDIUM RISK CLAUSES:
[List clauses that need attention]

### 4. MISSING TERMS
List any standard clauses that are missing but should be included.

### 5. COMPLIANCE CHECK
Check against Indian Contract Act and relevant regulations.

### 6. RECOMMENDATIONS
Specific suggestions for improvement.

### 7. OVERALL RISK SCORE
Rate the contract: LOW / MEDIUM / HIGH risk with explanation.

Analyze now:"""

    return client.generate(prompt, temperature=0.2, max_tokens=2048)


def predict_case_outcome(case_details: str, court_type: str = "District Court") -> str:
    """
    Case Outcome Prediction using historical patterns.
    """
    client = get_generator()
    
    prompt = f"""You are a legal analytics expert. Based on the case details provided, analyze the likely outcome.

CASE DETAILS:
{case_details}

COURT TYPE: {court_type}

Provide prediction in this format:

## CASE OUTCOME PREDICTION REPORT

### 1. CASE CLASSIFICATION
Type of case and applicable laws.

### 2. KEY FACTORS ANALYSIS
Factors that will influence the outcome:
- Strengths of the case
- Weaknesses/challenges
- Evidence strength assessment

### 3. SIMILAR CASE PATTERNS
Based on typical Indian court rulings in similar cases.

### 4. OUTCOME PROBABILITY
🟢 Favorable Outcome: [X]%
🟡 Partial Success: [X]%
🔴 Unfavorable: [X]%

### 5. RECOMMENDED STRATEGY
Legal strategy recommendations.

### 6. ESTIMATED TIMELINE
Typical duration for such cases in {court_type}.

### 7. DISCLAIMER
This is an AI-based prediction and should not be considered as legal advice.

Analyze:"""

    return client.generate(prompt, temperature=0.3, max_tokens=1500)


def check_citation_validity(citations: List[str]) -> str:
    """
    Smart Citator - Check if case laws are still valid (Good Law vs Bad Law).
    """
    client = get_generator()
    
    citations_text = "\n".join([f"- {c}" for c in citations])
    
    prompt = f"""You are a legal research expert specializing in Indian case law.

Check the following case citations and determine if they are still valid law:

CITATIONS TO CHECK:
{citations_text}

For each citation, provide:

## CITATION VALIDITY REPORT

For each case:
1. **Case Name & Citation**
2. **Status**: 
   - ✅ GOOD LAW (still valid)
   - ⚠️ PARTIALLY OVERRULED (some aspects modified)
   - ❌ BAD LAW (overruled/reversed)
3. **Overruling Case** (if applicable)
4. **Current Legal Position**
5. **Recommendation**: Safe to cite / Cite with caution / Do not cite

Note: This analysis is based on general legal knowledge. Always verify with official databases.

Analyze:"""

    return client.generate(prompt, temperature=0.2, max_tokens=1500)


def process_voice_to_legal_text(transcription: str) -> str:
    """
    Convert voice transcription to properly formatted legal text.
    """
    client = get_generator()
    
    prompt = f"""You are a legal secretary expert. Convert the following voice dictation into properly formatted legal text.

VOICE TRANSCRIPTION:
{transcription}

Requirements:
1. Correct grammar and punctuation
2. Use proper legal terminology
3. Format into appropriate paragraphs
4. Add proper legal document structure if applicable
5. Maintain the original meaning and intent

FORMATTED LEGAL TEXT:"""

    return client.generate(prompt, temperature=0.2, max_tokens=1500)


def client_intake_interview(responses: Dict[str, str]) -> str:
    """
    Process client intake responses and generate case summary.
    """
    client = get_generator()
    
    prompt = f"""You are a legal intake specialist. Based on the client's responses, prepare a comprehensive case intake summary.

CLIENT RESPONSES:
{json.dumps(responses, indent=2)}

Generate a structured intake report:

## CLIENT INTAKE SUMMARY

### 1. CLIENT INFORMATION
[Extract and organize personal details]

### 2. CASE TYPE CLASSIFICATION
[Identify the type of legal matter]

### 3. FACTS SUMMARY
[Organize the facts chronologically]

### 4. KEY DATES & DEADLINES
[List any important dates mentioned]

### 5. DOCUMENTS NEEDED
[List documents the client should provide]

### 6. PRELIMINARY LEGAL ISSUES
[Identify potential legal issues]

### 7. RECOMMENDED NEXT STEPS
[Suggest immediate actions]

### 8. URGENCY ASSESSMENT
🔴 URGENT / 🟡 MODERATE / 🟢 ROUTINE

Generate the report:"""

    return client.generate(prompt, temperature=0.3, max_tokens=1500)


def generate_odr_resolution(dispute_details: Dict[str, Any]) -> str:
    """
    Online Dispute Resolution - Generate resolution suggestions.
    """
    client = get_generator()
    
    prompt = f"""You are an Online Dispute Resolution (ODR) mediator specializing in Indian consumer and commercial disputes.

DISPUTE DETAILS:
{json.dumps(dispute_details, indent=2)}

Generate a resolution proposal:

## ODR RESOLUTION PROPOSAL

### 1. DISPUTE SUMMARY
[Brief overview of the dispute]

### 2. APPLICABLE LAWS
[Relevant consumer protection/commercial laws]

### 3. ANALYSIS OF CLAIMS
**Complainant's Position:**
[Analysis]

**Respondent's Position:**
[Analysis]

### 4. PROPOSED RESOLUTION OPTIONS

**Option A - Full Settlement:**
[Details and terms]

**Option B - Partial Settlement:**
[Details and terms]

**Option C - Arbitration Referral:**
[When to escalate]

### 5. RECOMMENDED RESOLUTION
[Best option with reasoning]

### 6. SETTLEMENT TERMS
[Specific terms if parties agree]

### 7. TIMELINE FOR RESOLUTION
[Suggested timeline]

Generate the proposal:"""

    return client.generate(prompt, temperature=0.3, max_tokens=1500)


def extract_evidence_summary(text: str, evidence_type: str = "general") -> str:
    """
    E-Discovery - Extract and summarize relevant evidence from text.
    """
    client = get_generator()
    
    prompt = f"""You are a legal e-discovery specialist. Analyze the following text and extract relevant evidence.

TEXT TO ANALYZE:
{text[:6000]}

EVIDENCE TYPE: {evidence_type}

Generate an evidence summary:

## E-DISCOVERY EVIDENCE REPORT

### 1. DOCUMENT TYPE
[Identify the type of document/communication]

### 2. KEY PARTIES IDENTIFIED
[List all persons/entities mentioned]

### 3. RELEVANT FACTS EXTRACTED
[List facts that could be relevant to litigation]

### 4. DATES & TIMELINE
[Chronological list of events/dates mentioned]

### 5. POTENTIAL EVIDENCE VALUE
🔴 HIGH - Directly relevant to case
🟡 MEDIUM - Potentially relevant
🟢 LOW - Background information

### 6. FLAGGED CONTENT
[Any admissions, contradictions, or significant statements]

### 7. RECOMMENDED ACTIONS
[What to do with this evidence]

Analyze:"""

    return client.generate(prompt, temperature=0.2, max_tokens=1500)
