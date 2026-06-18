"""Fast LLM connectivity check — multi-model architecture aware."""

from __future__ import annotations

import os
from typing import Any, Dict, List

import requests

DEFAULT_LM = "http://127.0.0.1:1234"
DEFAULT_OLLAMA = "http://127.0.0.1:11434"


def _ollama_model_names(payload: Any) -> List[str]:
    if not isinstance(payload, dict):
        return []
    names: List[str] = []
    for item in payload.get("models") or []:
        if isinstance(item, dict):
            name = str(item.get("name") or item.get("model") or "").strip()
            if name:
                names.append(name)
    return names


def _model_installed(names: List[str], wanted: str) -> bool:
    w = (wanted or "").strip().lower()
    if not w:
        return False
    return any(w in n.lower() or n.lower().startswith(f"{w}:") for n in names)


def _probe_ollama_model(ollama_url: str, model: str, timeout: float) -> Dict[str, Any]:
    try:
        r = requests.get(f"{ollama_url}/api/tags", timeout=timeout)
        if r.status_code != 200:
            return {"online": False, "available": False, "message": "Ollama unreachable"}
        names = _ollama_model_names(r.json())
        if _model_installed(names, model):
            return {
                "online": True,
                "available": True,
                "message": f"Ollama · {model}",
                "model": model,
            }
        return {
            "online": True,
            "available": False,
            "message": f"Ollama up — run: ollama pull {model}",
            "model": model,
        }
    except requests.RequestException:
        return {
            "online": False,
            "available": False,
            "message": f"Ollama offline — ollama pull {model}",
            "model": model,
        }


def quick_llm_status(timeout: float = 2.5) -> Dict[str, Any]:
    """Ping configured backend; report multi-model roles when router is enabled."""
    backend_pref = (os.getenv("LLM_BACKEND") or "ollama").strip().lower()
    ollama_url = (os.getenv("OLLAMA_URL") or os.getenv("OLLAMA_BASE_URL") or DEFAULT_OLLAMA).rstrip("/")
    ollama_model = (os.getenv("OLLAMA_MODEL") or os.getenv("LLM_MODEL") or "legalease-tuned").strip()

    use_router = False
    try:
        from backend.app.core.llm_task_router import architecture_snapshot, router_enabled

        arch = architecture_snapshot()
        use_router = router_enabled()
    except Exception:
        arch = {}

    if backend_pref == "ollama" and use_router:
        fast = arch.get("models", {}).get("fast_classifier", ollama_model)
        legal = arch.get("models", {}).get("legal_reasoning", ollama_model)
        same_model = fast.lower() == legal.lower()
        legal_st = _probe_ollama_model(ollama_url, legal, timeout)
        fast_st = legal_st if same_model else _probe_ollama_model(ollama_url, fast, timeout)
        ready = legal_st.get("available") and (same_model or fast_st.get("available"))
        label = (
            f"Ollama · {legal}"
            if same_model
            else f"Fast: {fast_st.get('message')} · Legal: {legal_st.get('message')}"
        )
        return {
            "available": ready,
            "online": legal_st.get("online") or fast_st.get("online"),
            "backend": "Ollama (legalease-tuned)" if same_model else "Ollama (multi-model)",
            "base_url": ollama_url,
            "message": label[:120],
            "model": legal,
            "architecture": arch,
            "roles": {
                "fast_classifier": fast_st,
                "legal_reasoning": legal_st,
                "single_model": same_model,
            },
        }

    if backend_pref == "ollama":
        st = _probe_ollama_model(ollama_url, ollama_model, timeout)
        return {
            "available": st.get("available"),
            "online": st.get("online"),
            "backend": "Ollama",
            "base_url": ollama_url,
            "message": st.get("message"),
            "model": ollama_model,
            "architecture": arch,
        }

    if backend_pref == "gemini":
        try:
            from backend.app.core.web_intelligence import gemini_configured, GEMINI_FREE_MODEL

            if gemini_configured():
                cloud_kb = False
                try:
                    from backend.app.core.cloud_kb_gemini import cloud_kb_gemini_enabled

                    cloud_kb = cloud_kb_gemini_enabled()
                except Exception:
                    pass
                msg = f"Gemini · {GEMINI_FREE_MODEL}"
                if cloud_kb:
                    msg += " (KB + Open Law)"
                else:
                    msg += " (Open Law / web; KB needs Ollama or CLOUD_GEMINI_KB)"
                return {
                    "available": True,
                    "online": True,
                    "backend": "Gemini",
                    "base_url": "",
                    "message": msg,
                    "model": GEMINI_FREE_MODEL,
                    "architecture": arch,
                }
        except Exception:
            pass
        return {
            "available": False,
            "online": False,
            "backend": "Gemini",
            "base_url": "",
            "message": "Gemini not configured — set GEMINI_API_KEY",
            "model": "",
            "architecture": arch,
        }

    lm_url = (os.getenv("LM_STUDIO_URL") or os.getenv("LM_STUDIO_BASE_URL") or DEFAULT_LM).rstrip("/")
    lm_model = (os.getenv("LM_STUDIO_MODEL") or os.getenv("LLM_MODEL") or "").strip()
    try:
        r = requests.get(f"{lm_url}/v1/models", timeout=timeout)
        if r.status_code == 200:
            label = f"LM Studio · {lm_model}" if lm_model else "LM Studio connected"
            return {
                "available": True,
                "online": True,
                "backend": "LM Studio",
                "base_url": lm_url,
                "message": label[:60],
                "model": lm_model,
                "architecture": arch,
            }
    except requests.RequestException:
        pass
    return {
        "available": False,
        "online": False,
        "backend": "LM Studio",
        "base_url": lm_url,
        "message": "LM Studio offline — load a model or set LLM_BACKEND=ollama",
        "model": lm_model,
        "architecture": arch,
    }
