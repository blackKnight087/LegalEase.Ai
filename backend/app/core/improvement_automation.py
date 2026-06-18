"""
Fully automated improvement pipeline — no manual Settings clicks required.

After enough thumbs-up feedback:
  1. Collect neural training pairs
  2. Auto-train embedding model
  3. Auto re-index KB (new embeddings)
  4. Export Modelfile + run `ollama create legalease-tuned`
  5. Switch local LLM to tuned model (OLLAMA_AUTO_USE_TUNED)

Runs in background threads — never blocks chat.
"""
from __future__ import annotations

import logging
import os
import re
import subprocess
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, Optional

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[3]
EXPORT_DIR = ROOT / "Data" / "ollama_exports"
ACTIVE_MODEL_FILE = EXPORT_DIR / "active_ollama_model.txt"
AUTOMATION_LOG = EXPORT_DIR / "automation_log.jsonl"

ENABLED = os.getenv("IMPROVEMENT_AUTO", "1").lower() in {"1", "true", "yes"}
AUTO_REINDEX = os.getenv("OLLAMA_AUTO_REINDEX", "1").lower() in {"1", "true", "yes"}
AUTO_OLLAMA_CREATE = os.getenv("OLLAMA_AUTO_CREATE", "1").lower() in {"1", "true", "yes"}
AUTO_USE_TUNED = os.getenv("OLLAMA_AUTO_USE_TUNED", "1").lower() in {"1", "true", "yes"}
AUTO_ENABLE_COACH = os.getenv("COACH_AUTO_ENABLE_ON_FEEDBACK", "1").lower() in {"1", "true", "yes"}
MIN_THUMBS_FOR_EXPORT = int(os.getenv("OLLAMA_AUTO_EXPORT_MIN_THUMBS", "20"))
OLLAMA_CREATE_TIMEOUT = int(os.getenv("OLLAMA_CREATE_TIMEOUT_SEC", "900"))
DEFAULT_TUNED_NAME = os.getenv("OLLAMA_TUNED_MODEL_NAME", "legalease-tuned").strip()

_running_users: set[str] = set()
_lock = threading.Lock()


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _log_event(user_id: str, event: str, detail: Dict[str, Any]) -> None:
    try:
        EXPORT_DIR.mkdir(parents=True, exist_ok=True)
        import json

        line = json.dumps(
            {"ts": _utc(), "user_id": str(user_id), "event": event, **detail},
            ensure_ascii=False,
        )
        with AUTOMATION_LOG.open("a", encoding="utf-8") as f:
            f.write(line + "\n")
    except Exception:
        pass


def count_thumbs_up(user_id: str) -> int:
    from backend.app.core.adaptive_learning import ensure_learning_schema
    from backend.app.core.database import connect_data_db

    ensure_learning_schema()
    conn = connect_data_db()
    try:
        row = conn.execute(
            """SELECT COUNT(*) FROM adaptive_feedback f
            JOIN adaptive_interactions i ON i.id = f.interaction_id
            WHERE i.user_id = ? AND f.signal IN ('thumbs_up', 'helpful', 'verbal_positive', 'copy')""",
            (str(user_id),),
        ).fetchone()
        return int(row[0] if row else 0)
    finally:
        conn.close()


def _user_active_model_file(user_id: str) -> Path:
    uid = str(user_id or "").strip()
    if not uid:
        return ACTIVE_MODEL_FILE
    return EXPORT_DIR / uid / "active_model.txt"


def get_active_tuned_model_name(user_id: str = "") -> str:
    """Read the auto-created Ollama model name for a user (used by llms.get_generator)."""
    uid = str(user_id or "").strip()
    if uid:
        try:
            path = _user_active_model_file(uid)
            if path.exists():
                name = path.read_text(encoding="utf-8").strip()
                if name:
                    return name
        except OSError:
            pass
        return ""
    # Legacy global file only when no user context (never cross-tenant in request paths).
    try:
        if ACTIVE_MODEL_FILE.exists():
            name = ACTIVE_MODEL_FILE.read_text(encoding="utf-8").strip()
            if name:
                return name
    except OSError:
        pass
    return ""


def _activate_tuned_model(user_id: str, model_name: str) -> None:
    uid = str(user_id or "").strip()
    if not uid:
        EXPORT_DIR.mkdir(parents=True, exist_ok=True)
        ACTIVE_MODEL_FILE.write_text(model_name.strip(), encoding="utf-8")
    else:
        path = _user_active_model_file(uid)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(model_name.strip(), encoding="utf-8")
    try:
        import llms

        llms.reset_generator()
    except Exception:
        pass
    logger.info("[IMPROVE AUTO] Active Ollama model set to %s for user %s", model_name, uid[:8] or "global")


def ensure_coach_auto_enabled(user_id: str) -> None:
    """Auto-enable tuning coach on first feedback (Settings still controllable)."""
    if not AUTO_ENABLE_COACH:
        return
    try:
        from backend.app.core.gemini_ollama_coach import coach_available, ensure_coach_schema, set_coach_enabled

        if not coach_available():
            return
        ensure_coach_schema()
        from backend.app.core.gemini_ollama_coach import get_coach_prefs

        prefs = get_coach_prefs(user_id)
        if not prefs.get("enabled"):
            set_coach_enabled(str(user_id), True)
            logger.info("[IMPROVE AUTO] Auto-enabled tuning coach for user %s", str(user_id)[:8])
    except Exception as exc:
        logger.debug("[IMPROVE AUTO] Coach auto-enable skipped: %s", exc)


def auto_reindex_kb(user_id: str) -> Dict[str, Any]:
    """Re-index all documents so FAISS uses the new embedding weights."""
    if not AUTO_REINDEX:
        return {"ok": False, "skipped": True, "reason": "auto_reindex_disabled"}
    try:
        from backend.app.core.reindex_scheduler import run_auto_reindex

        result = run_auto_reindex(str(user_id), use_ocr=False)
        _log_event(user_id, "kb_reindex", result)
        logger.info(
            "[IMPROVE AUTO] KB re-index user=%s chunks %s→%s",
            str(user_id)[:8],
            result.get("chunks_before"),
            result.get("chunks_after"),
        )
        return result
    except Exception as exc:
        logger.warning("[IMPROVE AUTO] Re-index failed: %s", exc)
        return {"ok": False, "error": str(exc)[:200]}


def run_ollama_create(modelfile_dir: str, model_name: str, user_id: str = "") -> Dict[str, Any]:
    """Run `ollama create model_name -f Modelfile` in export directory."""
    if not AUTO_OLLAMA_CREATE:
        return {"ok": False, "skipped": True, "reason": "auto_create_disabled"}
    path = Path(modelfile_dir)
    mf = path / "Modelfile"
    if not mf.exists():
        return {"ok": False, "error": f"Modelfile not found in {modelfile_dir}"}
    try:
        try:
            from backend.app.core.ollama_manager import ollama_gpu_subprocess_env

            run_env = ollama_gpu_subprocess_env()
        except Exception:
            run_env = None
        proc = subprocess.run(
            ["ollama", "create", model_name, "-f", "Modelfile"],
            cwd=str(path),
            capture_output=True,
            text=True,
            timeout=OLLAMA_CREATE_TIMEOUT,
            check=False,
            env=run_env,
        )
        if proc.returncode != 0:
            err = (proc.stderr or proc.stdout or "ollama create failed")[:400]
            return {"ok": False, "error": err, "returncode": proc.returncode}
        if AUTO_USE_TUNED:
            _activate_tuned_model(str(user_id), model_name)
        return {
            "ok": True,
            "model_name": model_name,
            "modelfile_dir": str(path),
            "command": f"ollama create {model_name} -f Modelfile",
            "stdout": (proc.stdout or "")[:300],
        }
    except FileNotFoundError:
        return {
            "ok": False,
            "error": "Ollama CLI not found. Install Ollama and ensure `ollama` is on PATH.",
        }
    except subprocess.TimeoutExpired:
        return {"ok": False, "error": f"ollama create timed out after {OLLAMA_CREATE_TIMEOUT}s"}
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:200]}


def auto_export_and_create_ollama(user_id: str, *, force: bool = False) -> Dict[str, Any]:
    """
    Export Modelfile when thumbs-up count >= MIN_THUMBS_FOR_EXPORT, then ollama create.
    Quality gate blocks export unless force=True (manual Settings override).
    """
    uid = str(user_id)
    thumbs = count_thumbs_up(uid)
    if not force and thumbs < MIN_THUMBS_FOR_EXPORT:
        return {
            "ok": False,
            "skipped": True,
            "reason": "below_threshold",
            "thumbs_up": thumbs,
            "min_required": MIN_THUMBS_FOR_EXPORT,
        }

    try:
        from backend.app.core.export_quality_gate import check_export_quality_gate

        gate = check_export_quality_gate(uid, force=force, include_holdout=True, refresh_holdout=True)
        if not gate.get("passed"):
            return {
                "ok": False,
                "skipped": True,
                "reason": "quality_gate_failed",
                "quality_gate": gate,
                "thumbs_up": thumbs,
            }
    except Exception as exc:
        logger.warning("[IMPROVE AUTO] quality gate error: %s", exc)

    try:
        from backend.app.core.ollama_modelfile_export import export_ollama_bundle

        export = export_ollama_bundle(uid)
    except Exception as exc:
        return {"ok": False, "error": str(exc)[:200]}
    if not export.get("ok"):
        return export
    if export.get("example_count", 0) < min(4, MIN_THUMBS_FOR_EXPORT // 4):
        return {
            "ok": False,
            "skipped": True,
            "reason": "too_few_examples",
            "export": export,
        }
    model_name = export.get("suggested_model_name") or DEFAULT_TUNED_NAME
    model_name = re.sub(r"[^a-z0-9._-]", "-", model_name.lower())[:48]
    export_dir = export.get("export_dir") or ""
    create = run_ollama_create(export_dir, model_name, uid)
    result = {**export, "ollama_create": create, "thumbs_up": thumbs}
    _log_event(uid, "modelfile_export_create", result)
    return result


def on_neural_train_complete(user_id: str, train_result: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    """After embedding fine-tune: reload embeddings + auto re-index KB."""
    out: Dict[str, Any] = {"train": train_result or {}}
    try:
        from backend.app.core.neural_finetuning import _activate_finetuned_model

        _activate_finetuned_model()
    except Exception:
        pass
    if train_result and train_result.get("ok"):
        out["reindex"] = auto_reindex_kb(str(user_id))
    return out


def run_neural_auto_train(user_id: str) -> Dict[str, Any]:
    """Collect pairs + maybe auto-train + reindex on success."""
    uid = str(user_id)
    result: Dict[str, Any] = {}
    try:
        from backend.app.core.neural_finetuning import collect_pairs_from_feedback, maybe_auto_train

        result["pairs_collected"] = collect_pairs_from_feedback(uid, limit=500)
        train = maybe_auto_train(uid)
        result["training"] = train
        if train and train.get("ok"):
            result["post_train"] = on_neural_train_complete(uid, train)
    except Exception as exc:
        result["error"] = str(exc)[:200]
    return result


def run_full_improvement_pipeline(
    user_id: str,
    *,
    trigger: str = "manual",
    membership: str = "Free",
    force_export: bool = False,
) -> Dict[str, Any]:
    """
    Complete automated improvement cycle (background-safe).
    """
    uid = str(user_id)
    summary: Dict[str, Any] = {"ok": True, "trigger": trigger, "user_id": uid}

    ensure_coach_auto_enabled(uid)

    summary["neural"] = run_neural_auto_train(uid)

    try:
        from backend.app.core.llm_finetuning import maybe_auto_train_llm, tuning_status

        llm_status = tuning_status(uid)
        if llm_status.get("sft_ready") or llm_status.get("dpo_ready"):
            summary["llm_finetune"] = maybe_auto_train_llm(uid)
        else:
            summary["llm_finetune"] = {
                "skipped": True,
                "sft_have": llm_status.get("sft_examples", 0),
                "dpo_have": llm_status.get("dpo_pairs", 0),
            }
    except Exception as exc:
        summary["llm_finetune"] = {"ok": False, "error": str(exc)[:120]}

    try:
        from backend.app.core.human_training import export_dpo_jsonl, export_sft_jsonl, training_pipeline_status

        pipe = training_pipeline_status(uid)
        if pipe.get("dpo_ready"):
            summary["dpo_export"] = export_dpo_jsonl(uid)
        if pipe.get("sft_ready"):
            summary["sft_export"] = export_sft_jsonl(uid)
    except Exception:
        pass

    thumbs = count_thumbs_up(uid)
    summary["thumbs_up"] = thumbs
    if thumbs >= MIN_THUMBS_FOR_EXPORT or force_export:
        summary["ollama"] = auto_export_and_create_ollama(uid, force=force_export)
    else:
        summary["ollama"] = {
            "skipped": True,
            "thumbs_up": thumbs,
            "min_required": MIN_THUMBS_FOR_EXPORT,
        }

    try:
        from backend.app.core.gemini_ollama_coach import coach_available, get_coach_prefs, run_coaching_cycle

        if coach_available() and get_coach_prefs(uid).get("enabled"):
            if trigger in ("scheduled", "thumbs_down", "directives", "manual"):
                coach = run_coaching_cycle(uid, membership=membership, auto_train=False)
                summary["coach"] = coach
    except Exception as exc:
        summary["coach"] = {"ok": False, "error": str(exc)[:120]}

    _log_event(uid, "pipeline_complete", {"trigger": trigger, "thumbs_up": thumbs})
    logger.info("[IMPROVE AUTO] Pipeline done trigger=%s user=%s thumbs=%s", trigger, uid[:8], thumbs)
    return summary


def schedule_improvement_pipeline(
    user_id: str,
    *,
    trigger: str = "feedback",
    membership: str = "Free",
    force_export: bool = False,
) -> None:
    """Fire-and-forget background improvement job (deduped per user)."""
    if not ENABLED:
        return
    try:
        from backend.app.core.resource_scheduler import Priority, can_run

        if not can_run(Priority.TUNING):
            logger.info("[IMPROVE AUTO] Pipeline deferred — KB or RAM pressure")
            return
    except Exception:
        pass
    uid = str(user_id)
    try:
        from backend.app.core.ml_job_queue import (
            enqueue_ml_job,
            should_use_ml_queue,
            user_has_active_ml_job,
        )

        if should_use_ml_queue():
            if user_has_active_ml_job(uid):
                return
            out = enqueue_ml_job(
                uid,
                "improvement_pipeline",
                {"trigger": trigger, "membership": membership, "force_export": force_export},
            )
            if out.get("ok") or out.get("deduped"):
                return
            logger.warning(
                "[IMPROVE AUTO] Queue enqueue failed user=%s: %s — falling back to thread",
                uid[:8],
                out.get("error"),
            )
    except Exception as exc:
        logger.warning("[IMPROVE AUTO] Queue unavailable: %s", exc)
    with _lock:
        if uid in _running_users:
            return
        _running_users.add(uid)

    def _job():
        try:
            run_full_improvement_pipeline(
                uid, trigger=trigger, membership=membership, force_export=force_export
            )
        except Exception as exc:
            logger.warning("[IMPROVE AUTO] Pipeline failed user=%s: %s", uid[:8], exc)
        finally:
            with _lock:
                _running_users.discard(uid)

    threading.Thread(target=_job, daemon=True, name=f"improve-{uid[:8]}").start()


def automation_status(user_id: str = "") -> Dict[str, Any]:
    """Status for Settings / engine bar."""
    uid = str(user_id)
    queue_info: Dict[str, Any] = {}
    try:
        from backend.app.core.ml_job_queue import list_user_ml_jobs, should_use_ml_queue

        queue_info = {
            "ml_queue": should_use_ml_queue(),
            "recent_jobs": list_user_ml_jobs(uid, limit=5) if uid else [],
        }
    except Exception:
        pass
    status = {
        "enabled": ENABLED,
        "auto_reindex": AUTO_REINDEX,
        "auto_ollama_create": AUTO_OLLAMA_CREATE,
        "auto_use_tuned_model": AUTO_USE_TUNED,
        "min_thumbs_for_export": MIN_THUMBS_FOR_EXPORT,
        **queue_info,
        "thumbs_up": count_thumbs_up(uid) if uid else 0,
        "active_tuned_model": get_active_tuned_model_name(uid) if AUTO_USE_TUNED and uid else "",
        "export_ready": count_thumbs_up(uid) >= MIN_THUMBS_FOR_EXPORT if uid else False,
        "log_path": str(AUTOMATION_LOG),
    }
    if uid:
        try:
            from backend.app.core.export_quality_gate import check_export_quality_gate

            gate = check_export_quality_gate(uid, force=False, include_holdout=False)
            status["quality_gate"] = gate
            status["can_export_modelfile"] = bool(status["export_ready"] and gate.get("passed"))
        except Exception:
            status["can_export_modelfile"] = status["export_ready"]
    return status
