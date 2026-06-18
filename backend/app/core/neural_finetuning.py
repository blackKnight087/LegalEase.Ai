"""
Neural fine-tuning for LegalEase — embedding model training from user feedback.

Trains a SentenceTransformer (MiniLM) on (query, relevant_passage) pairs collected
from thumbs-up, successful KB turns, and corrections. The fine-tuned weights improve
dense retrieval quality on your firm's documents and phrasing.

This complements (does not replace) adaptive_learning.py feedback loops.
LLM LoRA export remains available via tuning_export.py for external training.
"""
from __future__ import annotations

import json
import logging
import os
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[3]
MODELS_DIR = ROOT / "Data" / "fine_tuned_models" / "embeddings"
MODELS_DIR.mkdir(parents=True, exist_ok=True)
LATEST_LINK = MODELS_DIR / "latest"
METADATA_FILE = "finetune_metadata.json"

MIN_PAIRS_DEFAULT = int(os.getenv("NEURAL_FINETUNE_MIN_PAIRS", "4" if os.getenv("NEURAL_FINETUNE_RAPID", "1").lower() in {"1", "true", "yes"} else "8"))
EPOCHS_DEFAULT = int(os.getenv("NEURAL_FINETUNE_EPOCHS", "1" if os.getenv("NEURAL_FINETUNE_RAPID", "1").lower() in {"1", "true", "yes"} else "2"))
BATCH_SIZE_DEFAULT = int(os.getenv("NEURAL_FINETUNE_BATCH_SIZE", "16"))
ENABLED = os.getenv("NEURAL_FINETUNE_ENABLED", "1").lower() in {"1", "true", "yes"}
AUTO_TRAIN = os.getenv("NEURAL_FINETUNE_AUTO", "1").lower() in {"1", "true", "yes"}
RAPID_MODE = os.getenv("NEURAL_FINETUNE_RAPID", "1").lower() in {"1", "true", "yes"}

_train_lock = threading.Lock()
_train_running = False


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect():
    from backend.app.core.database import connect_data_db

    return connect_data_db()


def ensure_neural_tuning_schema() -> None:
    conn = _connect()
    try:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS neural_tuning_pairs (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL DEFAULT '',
            query TEXT NOT NULL,
            positive_passage TEXT NOT NULL,
            negative_passage TEXT,
            label REAL DEFAULT 1.0,
            source TEXT,
            used_in_run TEXT,
            created_at TEXT NOT NULL
        )"""
        )
        conn.execute(
            """CREATE TABLE IF NOT EXISTS neural_tuning_runs (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL,
            pair_count INTEGER DEFAULT 0,
            base_model TEXT,
            output_path TEXT,
            metrics_json TEXT,
            error TEXT,
            started_at TEXT NOT NULL,
            finished_at TEXT
        )"""
        )
        conn.commit()
    finally:
        conn.close()


def add_training_pair(
    query: str,
    positive_passage: str,
    *,
    user_id: str = "",
    negative_passage: str = "",
    source: str = "feedback",
    label: float = 1.0,
) -> Optional[str]:
    """Store one (query, passage) pair for embedding fine-tuning."""
    if not ENABLED:
        return None
    q = (query or "").strip()
    p = (positive_passage or "").strip()
    if len(q) < 8 or len(p) < 40:
        return None
    if len(p) > 4000:
        p = p[:4000]

    ensure_neural_tuning_schema()
    pid = str(uuid.uuid4())
    conn = _connect()
    try:
        conn.execute(
            """INSERT INTO neural_tuning_pairs
            (id, user_id, query, positive_passage, negative_passage, label, source, created_at)
            VALUES (?,?,?,?,?,?,?,?)""",
            (pid, str(user_id), q[:2000], p, (negative_passage or "")[:2000], float(label), source[:40], _utc()),
        )
        conn.commit()
    finally:
        conn.close()
    logger.debug("[NEURAL FT] pair added source=%s user=%s", source, user_id)
    return pid


def add_pairs_from_interaction(
    user_id: str,
    query: str,
    chunks: Optional[List[Dict[str, Any]]],
    *,
    source: str = "kb_turn",
    max_pairs: int = 3,
) -> int:
    """Extract top retrieved chunks as positive passages for the query."""
    if not chunks:
        return 0
    added = 0
    for ch in chunks[:max_pairs]:
        body = (ch.get("content") or "").strip()
        if len(body) < 40:
            continue
        if add_training_pair(query, body, user_id=user_id, source=source):
            added += 1
    return added


def collect_pairs_from_feedback(user_id: str = "", limit: int = 500) -> int:
    """Backfill training pairs from adaptive_feedback + interactions."""
    from backend.app.core.adaptive_learning import ensure_learning_schema

    ensure_learning_schema()
    ensure_neural_tuning_schema()
    conn = _connect()
    added = 0
    try:
        uid = str(user_id)
        fb_rows = conn.execute(
            """
            SELECT i.user_id, i.query, i.answer_preview
            FROM adaptive_feedback f
            JOIN adaptive_interactions i ON i.id = f.interaction_id
            WHERE f.signal IN ('thumbs_up', 'helpful', 'copy')
            AND (? = '' OR i.user_id = ?)
            ORDER BY f.created_at DESC
            LIMIT ?
            """,
            (uid, uid, limit),
        ).fetchall()
        for uid_row, query, answer in fb_rows:
            passage = (answer or "").strip()
            if len(passage) < 40:
                continue
            if add_training_pair(query, passage, user_id=str(uid_row), source="thumbs_up"):
                added += 1

        kb_rows = conn.execute(
            """
            SELECT user_id, query, answer_preview
            FROM adaptive_interactions
            WHERE found_in_kb = 1 AND LENGTH(answer_preview) > 120
            AND (? = '' OR user_id = ?)
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (uid, uid, limit),
        ).fetchall()
        for uid_row, query, answer in kb_rows:
            if add_training_pair(query, answer, user_id=str(uid_row), source="kb_success"):
                added += 1
    finally:
        conn.close()
    return added


def count_unused_pairs(user_id: str = "") -> int:
    ensure_neural_tuning_schema()
    conn = _connect()
    try:
        if user_id:
            row = conn.execute(
                "SELECT COUNT(*) FROM neural_tuning_pairs WHERE used_in_run IS NULL AND user_id = ?",
                (str(user_id),),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT COUNT(*) FROM neural_tuning_pairs WHERE used_in_run IS NULL",
            ).fetchone()
        return int(row[0] if row else 0)
    finally:
        conn.close()


def _load_training_pairs(user_id: str = "", limit: int = 2000) -> List[Tuple[str, str]]:
    ensure_neural_tuning_schema()
    conn = _connect()
    try:
        if user_id:
            rows = conn.execute(
                """SELECT query, positive_passage FROM neural_tuning_pairs
                WHERE user_id = ? OR user_id = ''
                ORDER BY created_at DESC LIMIT ?""",
                (str(user_id), limit),
            ).fetchall()
        else:
            rows = conn.execute(
                """SELECT query, positive_passage FROM neural_tuning_pairs
                ORDER BY created_at DESC LIMIT ?""",
                (limit,),
            ).fetchall()
    finally:
        conn.close()

    pairs: List[Tuple[str, str]] = []
    seen = set()
    for q, p in rows:
        key = (q[:120].lower(), p[:120].lower())
        if key in seen:
            continue
        seen.add(key)
        if len(q) >= 8 and len(p) >= 40:
            pairs.append((q, p))
    return pairs


def get_finetuned_model_path(user_id: str = "") -> Optional[str]:
    """Return path to active fine-tuned embedding model, if any."""
    env_path = (os.getenv("NEURAL_FINETUNE_MODEL_PATH") or "").strip()
    if env_path and Path(env_path).exists():
        return str(Path(env_path).resolve())

    if user_id:
        user_dir = MODELS_DIR / str(user_id)
        user_latest = user_dir / "latest.txt"
        if user_latest.exists():
            try:
                p = Path(user_latest.read_text(encoding="utf-8").strip())
                if p.exists():
                    return str(p.resolve())
            except OSError:
                pass
        if (user_dir / "config.json").exists() or (user_dir / "modules.json").exists():
            return str(user_dir.resolve())
        if (user_dir / METADATA_FILE).exists():
            return str(user_dir.resolve())

    latest_txt = MODELS_DIR / "latest.txt"
    if latest_txt.exists():
        try:
            p = Path(latest_txt.read_text(encoding="utf-8").strip())
            if p.exists():
                return str(p.resolve())
        except OSError:
            pass

    if LATEST_LINK.exists():
        return str(LATEST_LINK.resolve())

    global_dir = MODELS_DIR / "global"
    if (global_dir / "config.json").exists() or (global_dir / "modules.json").exists():
        return str(global_dir.resolve())

    return None


def _training_deps_ok() -> tuple[bool, str]:
    """Verify packages required for SentenceTransformer.fit()."""
    try:
        import accelerate  # noqa: F401
        from sentence_transformers import SentenceTransformerTrainingArguments  # noqa: F401

        ver = getattr(accelerate, "__version__", "0")
        parts = [int(x) for x in ver.split(".")[:3] if x.isdigit()]
        if parts and tuple(parts[:2]) < (0, 26):
            return False, f"accelerate {ver} too old (need >=0.26.0)"
        return True, ""
    except Exception as exc:
        return False, str(exc)


def tuning_status(user_id: str = "") -> Dict[str, Any]:
    ensure_neural_tuning_schema()
    conn = _connect()
    try:
        last_run = conn.execute(
            """SELECT id, status, pair_count, base_model, output_path, metrics_json, error,
                      started_at, finished_at
            FROM neural_tuning_runs
            WHERE user_id = ? OR user_id = ''
            ORDER BY started_at DESC LIMIT 1""",
            (str(user_id),),
        ).fetchone()
    finally:
        conn.close()

    active = get_finetuned_model_path(user_id)
    deps_ok, deps_error = _training_deps_ok()
    return {
        "enabled": ENABLED,
        "auto_train": AUTO_TRAIN,
        "rapid_mode": RAPID_MODE,
        "training_deps_ok": deps_ok,
        "training_deps_error": deps_error,
        "unused_pairs": count_unused_pairs(user_id),
        "min_pairs_required": MIN_PAIRS_DEFAULT,
        "active_model_path": active,
        "active_model_loaded": bool(active and Path(active).exists()),
        "last_run": (
            {
                "id": last_run[0],
                "status": last_run[1],
                "pair_count": last_run[2],
                "base_model": last_run[3],
                "output_path": last_run[4],
                "metrics": json.loads(last_run[5] or "{}"),
                "error": last_run[6],
                "started_at": last_run[7],
                "finished_at": last_run[8],
            }
            if last_run
            else None
        ),
    }


def train_embedding_model(
    user_id: str = "",
    *,
    min_pairs: Optional[int] = None,
    epochs: Optional[int] = None,
    scope: str = "user",
) -> Dict[str, Any]:
    """
    Fine-tune the embedding model on collected (query, passage) pairs.
    Runs on CPU; typical run is 1–5 minutes for MiniLM with <500 pairs.
    """
    global _train_running
    if not ENABLED:
        return {"ok": False, "error": "Neural fine-tuning disabled (NEURAL_FINETUNE_ENABLED=0)"}

    with _train_lock:
        if _train_running:
            return {"ok": False, "skipped": True, "reason": "training_already_running"}
        _train_running = True

    try:
        return _train_embedding_model_impl(
            user_id,
            min_pairs=min_pairs,
            epochs=epochs,
            scope=scope,
        )
    finally:
        with _train_lock:
            _train_running = False


def _train_embedding_model_impl(
    user_id: str = "",
    *,
    min_pairs: Optional[int] = None,
    epochs: Optional[int] = None,
    scope: str = "user",
) -> Dict[str, Any]:

    try:
        from backend.app.core.resource_scheduler import Priority, acquire

        with acquire(Priority.TUNING, "neural_train") as slot:
            if not slot.get("ok"):
                return {
                    "ok": False,
                    "error": f"Training deferred ({slot.get('reason', 'busy')}). KB answering has priority.",
                    "deferred": True,
                }
    except Exception:
        pass

    min_p = min_pairs if min_pairs is not None else MIN_PAIRS_DEFAULT
    ep = epochs if epochs is not None else EPOCHS_DEFAULT
    pairs = _load_training_pairs(user_id if scope == "user" else "", limit=2000)

    if len(pairs) < min_p:
        return {
            "ok": False,
            "error": f"Need at least {min_p} training pairs (have {len(pairs)}). "
            "Use thumbs-up on good answers or POST /learning/tuning/collect.",
            "pair_count": len(pairs),
        }

    base_model = os.getenv("HF_EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
    run_id = str(uuid.uuid4())
    base_out = MODELS_DIR / ("global" if scope != "user" else str(user_id))
    base_out.mkdir(parents=True, exist_ok=True)
    out_dir = base_out / f"run_{run_id[:8]}"
    out_dir.mkdir(parents=True, exist_ok=True)

    ensure_neural_tuning_schema()
    conn = _connect()
    try:
        conn.execute(
            """INSERT INTO neural_tuning_runs
            (id, user_id, status, pair_count, base_model, output_path, started_at)
            VALUES (?,?,?,?,?,?,?)""",
            (run_id, str(user_id), "running", len(pairs), base_model, str(out_dir), _utc()),
        )
        conn.commit()
    finally:
        conn.close()

    metrics: Dict[str, Any] = {"epochs": ep, "batch_size": BATCH_SIZE_DEFAULT}
    try:
        from sentence_transformers import InputExample, SentenceTransformer, losses
        from torch.utils.data import DataLoader

        try:
            from llms import clear_embeddings_cache

            clear_embeddings_cache(str(user_id) if scope == "user" else "", mark_offline=True)
        except Exception:
            pass

        try:
            from backend.app.core.gpu_runtime import release_ollama_vram_for_training, resolve_neural_train_device

            release_ollama_vram_for_training()
            device = resolve_neural_train_device()
        except ImportError:
            device = (os.getenv("RAG_EMBEDDING_DEVICE") or "cpu").strip() or "cpu"
        if device == "cuda":
            try:
                import torch

                if torch.cuda.is_available():
                    torch.cuda.empty_cache()
            except Exception:
                pass
        os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS", "1")
        os.environ.setdefault("HF_HUB_DISABLE_SYMLINKS_WARNING", "1")
        # Windows + background FastAPI: tqdm during model-card widgets → OSError [Errno 22]
        _prev_tqdm = os.environ.get("TQDM_DISABLE")
        os.environ["TQDM_DISABLE"] = "1"
        try:
            model = SentenceTransformer(
                base_model,
                device=device,
                model_kwargs={"low_cpu_mem_usage": False},
            )
        except TypeError:
            model = SentenceTransformer(base_model, device=device)
        model.train()
        for param in model.parameters():
            param.requires_grad = True
        examples = [InputExample(texts=[q, p]) for q, p in pairs]
        loader = DataLoader(
            examples,
            shuffle=True,
            batch_size=min(BATCH_SIZE_DEFAULT, len(examples)),
            pin_memory=(device == "cuda"),
        )
        loss = losses.MultipleNegativesRankingLoss(model)

        warmup = max(10, len(examples) // BATCH_SIZE_DEFAULT)
        try:
            model.fit(
                train_objectives=[(loader, loss)],
                epochs=ep,
                warmup_steps=min(warmup, 100),
                output_path=None,
                show_progress_bar=False,
            )
            model.save(str(out_dir), create_model_card=False)
        finally:
            if _prev_tqdm is None:
                os.environ.pop("TQDM_DISABLE", None)
            else:
                os.environ["TQDM_DISABLE"] = _prev_tqdm
        del model

        meta = {
            "base_model": base_model,
            "pair_count": len(pairs),
            "trained_at": _utc(),
            "scope": scope,
            "user_id": user_id,
            "run_id": run_id,
        }
        (out_dir / METADATA_FILE).write_text(json.dumps(meta, indent=2), encoding="utf-8")

        # Point latest marker at trained model
        if scope == "user" and user_id:
            user_dir = MODELS_DIR / str(user_id)
            user_dir.mkdir(parents=True, exist_ok=True)
            (user_dir / "latest.txt").write_text(str(out_dir.resolve()), encoding="utf-8")
        elif scope == "global":
            (MODELS_DIR / "latest.txt").write_text(str(out_dir.resolve()), encoding="utf-8")
            try:
                if LATEST_LINK.exists() and LATEST_LINK.is_symlink():
                    LATEST_LINK.unlink()
                if not LATEST_LINK.exists():
                    LATEST_LINK.symlink_to(out_dir, target_is_directory=True)
            except OSError as sym_exc:
                # Windows Errno 22 on symlink — latest.txt pointer is sufficient
                logger.debug("symlink skipped: %s", sym_exc)

        _activate_finetuned_model(str(user_id) if scope == "user" else "")
        metrics["output_path"] = str(out_dir)

        conn = _connect()
        try:
            conn.execute(
                """UPDATE neural_tuning_runs SET status=?, metrics_json=?, finished_at=?
                WHERE id=?""",
                ("completed", json.dumps(metrics), _utc(), run_id),
            )
            conn.execute(
                "UPDATE neural_tuning_pairs SET used_in_run=? WHERE used_in_run IS NULL",
                (run_id,),
            )
            conn.commit()
        finally:
            conn.close()

        logger.info(
            "[NEURAL FT] Completed run %s — %s pairs → %s",
            run_id,
            len(pairs),
            out_dir,
        )
        result = {
            "ok": True,
            "run_id": run_id,
            "pair_count": len(pairs),
            "output_path": str(out_dir),
            "message": "Embedding model fine-tuned. Re-indexing KB automatically.",
            "reindex_recommended": True,
            "metrics": metrics,
        }
        try:
            from backend.app.core.improvement_automation import on_neural_train_complete

            result["automation"] = on_neural_train_complete(user_id, result)
        except Exception:
            pass
        return result
    except Exception as exc:
        logger.exception("Neural fine-tuning failed: %s", exc)
        err_msg = str(exc)
        if getattr(exc, "errno", None) == 22 or "[Errno 22]" in err_msg:
            err_msg = (
                "Training failed on Windows (invalid I/O during model save). "
                "Retry after restarting the backend; if it persists, set TQDM_DISABLE=1 in .env."
            )
        # region agent log
        try:
            from backend.app.core.debug_session_log import debug_log

            debug_log(
                "TRAIN",
                "neural_finetuning.py:_train_embedding_model_impl",
                "train_failed",
                {
                    "errno": getattr(exc, "errno", None),
                    "error": str(exc)[:300],
                    "pair_count": len(pairs),
                    "out_dir": str(out_dir),
                },
                runId="post-fix",
            )
        except Exception:
            pass
        # endregion
        conn = _connect()
        try:
            conn.execute(
                """UPDATE neural_tuning_runs SET status=?, error=?, finished_at=? WHERE id=?""",
                ("failed", err_msg[:500], _utc(), run_id),
            )
            conn.commit()
        finally:
            conn.close()
        try:
            from llms import warmup_embeddings

            warmup_embeddings()
        except Exception:
            pass
        return {"ok": False, "error": str(exc), "run_id": run_id}


def _activate_finetuned_model(user_id: str = "") -> None:
    """Reload embedding singletons after weight update."""
    try:
        from llms import clear_embeddings_cache

        clear_embeddings_cache(str(user_id) if user_id else "", mark_offline=True)
    except Exception:
        pass
    try:
        from rag import _reset_embeddings_singleton

        _reset_embeddings_singleton()
    except Exception:
        pass
    try:
        from llms import warmup_embeddings

        warmup_embeddings()
    except Exception:
        pass


def maybe_auto_train(user_id: str = "") -> Optional[Dict[str, Any]]:
    """Run training automatically when enough new pairs exist."""
    if not ENABLED or not AUTO_TRAIN:
        return None
    try:
        from backend.app.core.resource_scheduler import Priority, can_run, defer_low_priority

        if not can_run(Priority.TUNING):
            logger.info("[NEURAL FT] Deferred — KB answering or high RAM")
            return None
    except Exception:
        pass
    uid = str(user_id or "")
    unused = count_unused_pairs(uid)
    if unused < MIN_PAIRS_DEFAULT:
        return None
    logger.info("[NEURAL FT] Auto-train triggered (%s unused pairs) user=%s", unused, uid[:8])

    def _train() -> Optional[Dict[str, Any]]:
        return train_embedding_model(uid, scope="user" if uid else "global")

    try:
        from backend.app.core.resource_scheduler import defer_low_priority

        defer_low_priority(lambda: _train(), label="neural_auto_train")
        return {"ok": True, "scheduled": True, "pair_count": unused}
    except Exception:
        return train_embedding_model(uid, scope="user" if uid else "global")


def resolve_embedding_model_name(user_id: str = "") -> str:
    """Pick fine-tuned local path or fall back to HF hub base model."""
    if os.getenv("RAG_PREFER_BASE_EMBEDDINGS", "0").lower() in {"1", "true", "yes"}:
        return os.getenv("HF_EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
    ft = get_finetuned_model_path(user_id)
    if ft and Path(ft).exists() and (Path(ft) / "config.json").exists():
        return ft
    if ft and Path(ft).exists() and (Path(ft) / "modules.json").exists():
        return ft
    return os.getenv("HF_EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
