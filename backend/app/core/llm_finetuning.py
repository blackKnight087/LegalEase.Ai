"""
In-app LLM fine-tuning — LoRA SFT and DPO on human feedback.

Trains chat-model adapters from thumbs-up SFT pairs and DPO preference pairs,
then loads adapters at inference via llms.get_generator().
"""
from __future__ import annotations

import json
import logging
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

logger = logging.getLogger(__name__)

ROOT = Path(__file__).resolve().parents[3]
LLM_MODELS_DIR = ROOT / "Data" / "fine_tuned_models" / "llm"

ENABLED = os.getenv("LLM_FINETUNE_ENABLED", "1").lower() in {"1", "true", "yes"}
AUTO_TRAIN = os.getenv("LLM_FINETUNE_AUTO", "1").lower() in {"1", "true", "yes"}
BASE_MODEL = os.getenv("LLM_FINETUNE_BASE_MODEL", "google/gemma-2-2b-it")
MIN_SFT = int(os.getenv("LLM_FINETUNE_MIN_SFT", "5"))
MIN_DPO = int(os.getenv("LLM_FINETUNE_MIN_DPO", "2"))
MAX_STEPS = int(os.getenv("LLM_FINETUNE_MAX_STEPS", "60"))
LORA_RANK = int(os.getenv("LLM_FINETUNE_LORA_RANK", "8"))
MAX_SEQ_LEN = int(os.getenv("LLM_FINETUNE_MAX_SEQ_LEN", "512"))

_train_lock = threading.Lock()
_train_running = False


def _utc() -> str:
    return datetime.now(timezone.utc).isoformat()


def _connect():
    from backend.app.core.database import connect_data_db

    return connect_data_db()


def ensure_llm_tuning_schema() -> None:
    conn = _connect()
    try:
        conn.execute(
            """CREATE TABLE IF NOT EXISTS llm_tuning_runs (
            id TEXT PRIMARY KEY,
            user_id TEXT NOT NULL,
            train_type TEXT NOT NULL,
            status TEXT NOT NULL,
            example_count INTEGER DEFAULT 0,
            base_model TEXT,
            output_path TEXT,
            metrics_json TEXT DEFAULT '{}',
            error TEXT,
            started_at TEXT NOT NULL,
            finished_at TEXT
        )"""
        )
        conn.execute(
            """CREATE INDEX IF NOT EXISTS idx_llm_tuning_uid
            ON llm_tuning_runs(user_id, started_at DESC)"""
        )
        conn.commit()
    finally:
        conn.close()


def _ensure_utf8_for_trl() -> None:
    """Windows cp1252 breaks trl template reads — force UTF-8 for Path.read_text."""
    import os
    import pathlib

    os.environ.setdefault("PYTHONUTF8", "1")
    if getattr(pathlib.Path.read_text, "_legalease_utf8_patch", False):
        return
    _orig = pathlib.Path.read_text

    def _read_text_utf8(self, *args, **kwargs):
        if "encoding" not in kwargs and not args:
            kwargs["encoding"] = "utf-8"
        return _orig(self, *args, **kwargs)

    _read_text_utf8._legalease_utf8_patch = True  # type: ignore[attr-defined]
    pathlib.Path.read_text = _read_text_utf8  # type: ignore[method-assign]


def _local_gpu_available() -> bool:
    try:
        import torch

        return bool(torch.cuda.is_available())
    except Exception:
        return False


def _training_deps_ok() -> Tuple[bool, str]:
    try:
        _ensure_utf8_for_trl()
        import peft  # noqa: F401
        import trl  # noqa: F401
        import torch  # noqa: F401
        from transformers import AutoModelForCausalLM, AutoTokenizer  # noqa: F401

        return True, ""
    except ImportError as exc:
        return False, f"Missing LLM training deps (peft, trl): {exc}"
    except Exception as exc:
        return False, f"LLM training deps check failed: {exc}"


def _user_adapter_dir(user_id: str) -> Path:
    return LLM_MODELS_DIR / str(user_id) / "adapter"


def get_active_adapter_path(user_id: str = "") -> str:
    """Return path to active LoRA adapter for user, or empty string."""
    uid = str(user_id or "").strip()
    if not uid:
        return ""
    adapter = _user_adapter_dir(uid)
    latest = adapter / "latest.txt"
    if latest.exists():
        path = Path(latest.read_text(encoding="utf-8").strip())
        if path.exists():
            return str(path)
    if (adapter / "adapter_config.json").exists():
        return str(adapter)
    return ""


def _load_sft_examples(user_id: str, limit: int = 500) -> List[Dict[str, str]]:
    from backend.app.core.adaptive_learning import ensure_learning_schema
    from backend.app.core.human_training import ensure_human_training_schema

    ensure_learning_schema()
    ensure_human_training_schema()
    conn = _connect()
    try:
        rows = conn.execute(
            """SELECT i.query, i.answer_preview
            FROM adaptive_feedback f
            JOIN adaptive_interactions i ON i.id = f.interaction_id
            WHERE i.user_id=? AND f.signal IN (
                'thumbs_up', 'helpful', 'verbal_positive', 'copy',
                'export_docx', 'export_pdf', 'save_to_matter'
            )
            ORDER BY f.created_at DESC LIMIT ?""",
            (str(user_id), limit),
        ).fetchall()
    finally:
        conn.close()

    examples: List[Dict[str, str]] = []
    for q, a in rows:
        if q and a and len(a) >= 40:
            examples.append({"query": q, "answer": a[:1500]})
    return examples


def _load_dpo_examples(user_id: str, limit: int = 200) -> List[Dict[str, str]]:
    from backend.app.core.human_training import ensure_human_training_schema

    ensure_human_training_schema()
    conn = _connect()
    try:
        rows = conn.execute(
            """SELECT query, chosen_answer, rejected_answer
            FROM preference_pairs WHERE user_id=?
            ORDER BY created_at DESC LIMIT ?""",
            (str(user_id), limit),
        ).fetchall()
    finally:
        conn.close()

    examples: List[Dict[str, str]] = []
    for q, chosen, rejected in rows:
        if q and chosen and rejected and chosen != rejected:
            examples.append({
                "prompt": q,
                "chosen": chosen[:1500],
                "rejected": rejected[:1500],
            })
    return examples


def _format_sft_text(query: str, answer: str) -> str:
    return (
        f"<start_of_turn>user\n{query}\n<end_of_turn>\n"
        f"<start_of_turn>model\n{answer}\n<end_of_turn>"
    )


def _run_lora_sft(examples: List[Dict[str, str]], out_dir: Path) -> Dict[str, Any]:
    _ensure_utf8_for_trl()
    import torch
    from datasets import Dataset
    from peft import LoraConfig, get_peft_model, prepare_model_for_kbit_training
    from transformers import AutoModelForCausalLM, AutoTokenizer, TrainingArguments
    from trl import SFTTrainer

    texts = [_format_sft_text(ex["query"], ex["answer"]) for ex in examples]
    ds = Dataset.from_dict({"text": texts})

    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    use_cuda = torch.cuda.is_available()
    dtype = torch.float16 if use_cuda else torch.float32
    model = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL,
        torch_dtype=dtype,
        trust_remote_code=True,
        low_cpu_mem_usage=False,
        device_map=None,
    )
    if use_cuda:
        model = model.to("cuda")
        model = prepare_model_for_kbit_training(model)

    lora = LoraConfig(
        r=LORA_RANK,
        lora_alpha=LORA_RANK * 2,
        lora_dropout=0.05,
        bias="none",
        task_type="CAUSAL_LM",
        target_modules=["q_proj", "v_proj", "k_proj", "o_proj"],
    )
    model = get_peft_model(model, lora)

    args = TrainingArguments(
        output_dir=str(out_dir / "checkpoints"),
        per_device_train_batch_size=1,
        gradient_accumulation_steps=4,
        max_steps=min(MAX_STEPS, max(10, len(examples) * 2)),
        learning_rate=2e-4,
        logging_steps=5,
        save_strategy="no",
        report_to=[],
        fp16=use_cuda,
        no_cuda=not use_cuda,
    )

    trainer = SFTTrainer(
        model=model,
        args=args,
        train_dataset=ds,
        processing_class=tokenizer,
        max_seq_length=MAX_SEQ_LEN,
    )
    train_result = trainer.train()
    adapter_dir = out_dir / "adapter"
    adapter_dir.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(str(adapter_dir))
    tokenizer.save_pretrained(str(adapter_dir))

    return {
        "train_loss": float(getattr(train_result, "training_loss", 0) or 0),
        "steps": train_result.global_step,
        "adapter_path": str(adapter_dir),
    }


def _run_lora_dpo(examples: List[Dict[str, str]], out_dir: Path, sft_adapter: str = "") -> Dict[str, Any]:
    _ensure_utf8_for_trl()
    import torch
    from datasets import Dataset
    from peft import LoraConfig, PeftModel, get_peft_model
    from transformers import AutoModelForCausalLM, AutoTokenizer, TrainingArguments
    from trl import DPOTrainer

    ds = Dataset.from_dict({
        "prompt": [ex["prompt"] for ex in examples],
        "chosen": [ex["chosen"] for ex in examples],
        "rejected": [ex["rejected"] for ex in examples],
    })

    tokenizer = AutoTokenizer.from_pretrained(BASE_MODEL, trust_remote_code=True)
    if tokenizer.pad_token is None:
        tokenizer.pad_token = tokenizer.eos_token

    use_cuda = torch.cuda.is_available()
    dtype = torch.float16 if use_cuda else torch.float32
    model = AutoModelForCausalLM.from_pretrained(
        BASE_MODEL,
        torch_dtype=dtype,
        trust_remote_code=True,
        low_cpu_mem_usage=False,
        device_map=None,
    )
    if use_cuda:
        model = model.to("cuda")

    if sft_adapter and Path(sft_adapter).exists():
        model = PeftModel.from_pretrained(model, sft_adapter, is_trainable=True)
    else:
        lora = LoraConfig(
            r=LORA_RANK,
            lora_alpha=LORA_RANK * 2,
            lora_dropout=0.05,
            bias="none",
            task_type="CAUSAL_LM",
            target_modules=["q_proj", "v_proj", "k_proj", "o_proj"],
        )
        model = get_peft_model(model, lora)

    args = TrainingArguments(
        output_dir=str(out_dir / "dpo_checkpoints"),
        per_device_train_batch_size=1,
        gradient_accumulation_steps=4,
        max_steps=min(MAX_STEPS, max(10, len(examples) * 3)),
        learning_rate=5e-5,
        logging_steps=5,
        save_strategy="no",
        report_to=[],
        fp16=use_cuda,
        no_cuda=not use_cuda,
        remove_unused_columns=False,
    )

    trainer = DPOTrainer(
        model=model,
        args=args,
        processing_class=tokenizer,
        train_dataset=ds,
        max_length=MAX_SEQ_LEN,
        max_prompt_length=min(256, MAX_SEQ_LEN // 2),
    )
    train_result = trainer.train()
    adapter_dir = out_dir / "adapter"
    adapter_dir.mkdir(parents=True, exist_ok=True)
    model.save_pretrained(str(adapter_dir))
    tokenizer.save_pretrained(str(adapter_dir))

    return {
        "train_loss": float(getattr(train_result, "training_loss", 0) or 0),
        "steps": train_result.global_step,
        "adapter_path": str(adapter_dir),
    }


def _activate_adapter(user_id: str, adapter_path: str) -> None:
    uid = str(user_id)
    base = _user_adapter_dir(uid)
    base.mkdir(parents=True, exist_ok=True)
    (base / "latest.txt").write_text(adapter_path, encoding="utf-8")
    try:
        import llms

        llms.reset_generator()
    except Exception:
        pass


def train_lora_sft(user_id: str, *, min_examples: Optional[int] = None) -> Dict[str, Any]:
    """Fine-tune LoRA adapter on human thumbs-up SFT pairs."""
    global _train_running
    if not ENABLED:
        return {"ok": False, "error": "LLM fine-tuning disabled (LLM_FINETUNE_ENABLED=0)"}

    deps_ok, deps_err = _training_deps_ok()
    if not deps_ok:
        return {"ok": False, "error": deps_err}
    if not _local_gpu_available():
        return {
            "ok": False,
            "skipped": True,
            "error": "LLM LoRA training requires a CUDA GPU (skipped on CPU-only hosts).",
        }

    min_ex = min_examples if min_examples is not None else MIN_SFT
    examples = _load_sft_examples(user_id)
    if len(examples) < min_ex:
        return {
            "ok": False,
            "error": f"Need at least {min_ex} SFT examples (have {len(examples)})",
            "example_count": len(examples),
        }

    with _train_lock:
        if _train_running:
            return {"ok": False, "skipped": True, "reason": "training_already_running"}
        _train_running = True

    run_id = str(uuid.uuid4())
    out_dir = LLM_MODELS_DIR / str(user_id) / f"run_{run_id[:8]}"
    out_dir.mkdir(parents=True, exist_ok=True)

    ensure_llm_tuning_schema()
    conn = _connect()
    try:
        conn.execute(
            """INSERT INTO llm_tuning_runs
            (id, user_id, train_type, status, example_count, base_model, output_path, started_at)
            VALUES (?,?,?,?,?,?,?,?)""",
            (run_id, str(user_id), "sft", "running", len(examples), BASE_MODEL, str(out_dir), _utc()),
        )
        conn.commit()
    finally:
        conn.close()

    try:
        metrics = _run_lora_sft(examples, out_dir)
        adapter_path = metrics["adapter_path"]
        _activate_adapter(user_id, adapter_path)
        status = "completed"
        err = ""
    except Exception as exc:
        logger.warning("LLM SFT training failed: %s", exc)
        metrics = {}
        adapter_path = ""
        status = "failed"
        err = str(exc)[:400]

    conn = _connect()
    try:
        conn.execute(
            """UPDATE llm_tuning_runs SET status=?, metrics_json=?, error=?, finished_at=?, output_path=?
            WHERE id=?""",
            (status, json.dumps(metrics), err, _utc(), adapter_path or str(out_dir), run_id),
        )
        conn.commit()
    finally:
        conn.close()

    with _train_lock:
        _train_running = False

    return {
        "ok": status == "completed",
        "train_type": "sft",
        "example_count": len(examples),
        "adapter_path": adapter_path,
        "metrics": metrics,
        "error": err or None,
    }


def train_dpo(user_id: str, *, min_pairs: Optional[int] = None) -> Dict[str, Any]:
    """Fine-tune LoRA adapter with DPO on preference pairs."""
    global _train_running
    if not ENABLED:
        return {"ok": False, "error": "LLM fine-tuning disabled (LLM_FINETUNE_ENABLED=0)"}

    deps_ok, deps_err = _training_deps_ok()
    if not deps_ok:
        return {"ok": False, "error": deps_err}

    min_p = min_pairs if min_pairs is not None else MIN_DPO
    examples = _load_dpo_examples(user_id)
    if len(examples) < min_p:
        return {
            "ok": False,
            "error": f"Need at least {min_p} DPO pairs (have {len(examples)})",
            "pair_count": len(examples),
        }

    with _train_lock:
        if _train_running:
            return {"ok": False, "skipped": True, "reason": "training_already_running"}
        _train_running = True

    run_id = str(uuid.uuid4())
    out_dir = LLM_MODELS_DIR / str(user_id) / f"dpo_{run_id[:8]}"
    out_dir.mkdir(parents=True, exist_ok=True)
    sft_adapter = get_active_adapter_path(user_id)

    ensure_llm_tuning_schema()
    conn = _connect()
    try:
        conn.execute(
            """INSERT INTO llm_tuning_runs
            (id, user_id, train_type, status, example_count, base_model, output_path, started_at)
            VALUES (?,?,?,?,?,?,?,?)""",
            (run_id, str(user_id), "dpo", "running", len(examples), BASE_MODEL, str(out_dir), _utc()),
        )
        conn.commit()
    finally:
        conn.close()

    try:
        metrics = _run_lora_dpo(examples, out_dir, sft_adapter=sft_adapter)
        adapter_path = metrics["adapter_path"]
        _activate_adapter(user_id, adapter_path)
        status = "completed"
        err = ""
    except Exception as exc:
        logger.exception("LLM DPO training failed")
        metrics = {}
        adapter_path = ""
        status = "failed"
        err = str(exc)[:400]

    conn = _connect()
    try:
        conn.execute(
            """UPDATE llm_tuning_runs SET status=?, metrics_json=?, error=?, finished_at=?, output_path=?
            WHERE id=?""",
            (status, json.dumps(metrics), err, _utc(), adapter_path or str(out_dir), run_id),
        )
        conn.commit()
    finally:
        conn.close()

    with _train_lock:
        _train_running = False

    return {
        "ok": status == "completed",
        "train_type": "dpo",
        "pair_count": len(examples),
        "adapter_path": adapter_path,
        "metrics": metrics,
        "error": err or None,
    }


def maybe_auto_train_llm(user_id: str) -> Dict[str, Any]:
    """Auto-train SFT then DPO when enough data exists."""
    if not AUTO_TRAIN:
        return {"skipped": True, "reason": "auto_train_disabled"}
    out: Dict[str, Any] = {}
    sft_examples = _load_sft_examples(user_id)
    if len(sft_examples) >= MIN_SFT:
        out["sft"] = train_lora_sft(user_id)
    dpo_examples = _load_dpo_examples(user_id)
    if len(dpo_examples) >= MIN_DPO:
        out["dpo"] = train_dpo(user_id)
    if not out:
        out["skipped"] = True
        out["sft_needed"] = MIN_SFT
        out["dpo_needed"] = MIN_DPO
        out["sft_have"] = len(sft_examples)
        out["dpo_have"] = len(dpo_examples)
    return out


def tuning_status(user_id: str = "") -> Dict[str, Any]:
    ensure_llm_tuning_schema()
    deps_ok, deps_err = _training_deps_ok()
    sft_count = len(_load_sft_examples(user_id)) if user_id else 0
    dpo_count = len(_load_dpo_examples(user_id)) if user_id else 0

    last_run = None
    if user_id:
        conn = _connect()
        try:
            row = conn.execute(
                """SELECT id, train_type, status, example_count, base_model, output_path,
                          metrics_json, error, started_at, finished_at
                FROM llm_tuning_runs WHERE user_id=?
                ORDER BY started_at DESC LIMIT 1""",
                (str(user_id),),
            ).fetchone()
            if row:
                last_run = {
                    "id": row[0],
                    "train_type": row[1],
                    "status": row[2],
                    "example_count": row[3],
                    "base_model": row[4],
                    "output_path": row[5],
                    "metrics": json.loads(row[6] or "{}"),
                    "error": row[7],
                    "started_at": row[8],
                    "finished_at": row[9],
                }
        finally:
            conn.close()

    adapter = get_active_adapter_path(user_id)
    return {
        "enabled": ENABLED,
        "auto_train": AUTO_TRAIN,
        "training_deps_ok": deps_ok,
        "training_deps_error": deps_err,
        "base_model": BASE_MODEL,
        "sft_examples": sft_count,
        "dpo_pairs": dpo_count,
        "min_sft_required": MIN_SFT,
        "min_dpo_required": MIN_DPO,
        "sft_ready": sft_count >= MIN_SFT,
        "dpo_ready": dpo_count >= MIN_DPO,
        "active_adapter_path": adapter,
        "adapter_loaded": bool(adapter and Path(adapter).exists()),
        "last_run": last_run,
    }
