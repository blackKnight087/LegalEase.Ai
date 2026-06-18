"""Adaptive learning API — feedback and improvement stats."""
from __future__ import annotations

import os
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from ....core.auth import get_current_user
from ....core.adaptive_learning import (
    ensure_learning_schema,
    learning_stats,
    promote_scope_to_global,
    record_feedback,
    record_implicit_correction,
)
from ....core.observability import emit_event

router = APIRouter(tags=["learning"])
SCOPE_PROMOTION_ENABLED = os.getenv("LEARNING_SCOPE_PROMOTION_ENABLED", "1").lower() in (
    "1",
    "true",
    "yes",
)


class FeedbackRequest(BaseModel):
    signal: str = Field(
        ...,
        description=(
            "thumbs_up | thumbs_down | verbal_positive | verbal_negative | copy | regenerate | helpful | follow_up_click | "
            "export_docx | export_pdf | export_client_safe | save_to_matter | edit_diff | "
            "dwell_time | mode_switch"
        ),
    )
    interaction_id: str = ""
    chat_id: str = ""
    comment: str = ""
    tags: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class SignalRequest(BaseModel):
    signal: str
    interaction_id: str = ""
    chat_id: str = ""
    comment: str = ""
    tags: List[str] = Field(default_factory=list)
    metadata: Dict[str, Any] = Field(default_factory=dict)


class CorrectionRequest(BaseModel):
    previous_query: str
    correction_query: str
    mode: str = "knowledge_base"


class ScopePromotionRequest(BaseModel):
    user_id: str = Field(..., min_length=1)
    matter_id: str = Field(..., min_length=1)
    limit: int = 500


@router.post("/feedback")
def post_feedback(
    body: FeedbackRequest,
    user: Dict[str, Any] = Depends(get_current_user),
):
    from backend.app.core.feedback_async import ensure_schema_once, json_safe
    from backend.app.core.learning_signals import process_learning_signal

    try:
        ensure_schema_once()
    except Exception as exc:
        return json_safe({"ok": False, "error": f"schema: {str(exc)[:120]}"})

    membership = str(user.get("membership") or user.get("plan") or "Free")
    try:
        result = process_learning_signal(
            str(user["id"]),
            body.signal,
            interaction_id=body.interaction_id,
            chat_id=body.chat_id,
            comment=body.comment,
            tags=body.tags,
            metadata=body.metadata,
            membership=membership,
        )
    except Exception as exc:
        return json_safe({"ok": False, "error": str(exc)[:200]})

    if not result.get("ok") and body.signal in ("thumbs_up", "thumbs_down", "copy"):
        try:
            from backend.app.core.adaptive_learning import record_feedback

            fb = record_feedback(
                str(user["id"]),
                interaction_id=body.interaction_id,
                chat_id=body.chat_id,
                thread_id=str(body.metadata.get("thread_id") or ""),
                signal=body.signal,
                comment=body.comment,
                tags=body.tags,
                metadata=body.metadata,
            )
            if fb.get("ok"):
                result = fb
        except Exception:
            pass

    if body.signal in ("thumbs_down", "verbal_negative") and result.get("ok"):
        try:
            from backend.app.core.feedback_learning import enqueue_feedback

            meta = body.metadata or {}
            enqueue_feedback(
                str(user["id"]),
                signal="thumbs_down" if body.signal == "thumbs_down" else "verbal_negative",
                interaction_id=body.interaction_id,
                chat_id=body.chat_id,
                mode=str(meta.get("mode") or ""),
                query_text=str(meta.get("user_query") or meta.get("query") or ""),
                answer_text=str(meta.get("answer") or meta.get("answer_text") or ""),
                confidence=float(meta.get("confidence") or 0),
                metadata=meta,
            )
        except Exception:
            pass

    if not result.get("queued"):
        try:
            from backend.app.core.improvement_automation import schedule_improvement_pipeline

            if body.signal in (
                "thumbs_up", "thumbs_down", "verbal_positive", "verbal_negative",
                "helpful", "copy", "regenerate",
                "export_docx", "export_pdf", "save_to_matter",
            ) and result.get("ok"):
                schedule_improvement_pipeline(str(user["id"]), trigger=body.signal)
        except Exception:
            pass
    return json_safe(result)


@router.post("/signals")
def post_learning_signal(
    body: SignalRequest,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Implicit / auxiliary learning signals (dwell, mode switch, follow-up click, edit diff, export)."""
    from backend.app.core.learning_signals import ensure_signal_schema, process_learning_signal

    ensure_signal_schema()
    membership = str(user.get("membership") or user.get("plan") or "Free")
    return process_learning_signal(
        str(user["id"]),
        body.signal,
        interaction_id=body.interaction_id,
        chat_id=body.chat_id,
        comment=body.comment,
        tags=body.tags,
        metadata=body.metadata,
        membership=membership,
    )


@router.get("/signals/tags")
def get_feedback_tags(user: Dict[str, Any] = Depends(get_current_user)):
    from backend.app.core.learning_signals import TAG_LABELS

    return {"tags": TAG_LABELS}


@router.get("/signals/stats")
def get_signal_stats(user: Dict[str, Any] = Depends(get_current_user)):
    from backend.app.core.learning_signals import ensure_signal_schema, signal_stats

    ensure_signal_schema()
    return signal_stats(str(user["id"]))


@router.post("/correction")
def post_correction(
    body: CorrectionRequest,
    user: Dict[str, Any] = Depends(get_current_user),
):
    from backend.app.core.adaptive_learning import normalize_query

    record_implicit_correction(
        user["id"],
        body.mode,
        normalize_query(body.previous_query),
        body.correction_query,
    )
    return {"ok": True, "message": "Learned from your correction"}


@router.get("/stats")
def get_stats(user: Dict[str, Any] = Depends(get_current_user)):
    ensure_learning_schema()
    return learning_stats(user["id"])


@router.post("/tuning/scope/promote")
def promote_scope_tuning(
    body: ScopePromotionRequest,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """
    Admin-controlled promotion: matter-scoped learning -> global scope.
    """
    if not SCOPE_PROMOTION_ENABLED:
        from fastapi import HTTPException

        raise HTTPException(403, "Scope promotion is disabled")
    role = str(user.get("role") or "user")
    if role != "admin":
        from fastapi import HTTPException

        emit_event(
            "scope_promotion_denied",
            actor_user_id=str(user.get("id") or ""),
            target_user_id=str(body.user_id),
            matter_id=str(body.matter_id),
            reason="admin_required",
        )
        raise HTTPException(403, "Admin role required")
    ensure_learning_schema()
    out = promote_scope_to_global(
        str(body.user_id),
        matter_id=body.matter_id,
        promoted_by=str(user.get("id") or ""),
        limit=max(1, min(int(body.limit or 500), 5000)),
    )
    emit_event(
        "scope_promotion_completed",
        actor_user_id=str(user.get("id") or ""),
        target_user_id=str(body.user_id),
        matter_id=str(body.matter_id),
        interactions_copied=int(out.get("interactions_copied") or 0),
        feedback_copied=int(out.get("feedback_copied") or 0),
    )
    return out


@router.get("/analytics/full")
def analytics_full(user: Dict[str, Any] = Depends(get_current_user)):
    """Learning + judicial + enterprise usage for Analytics page."""
    from backend.app.core.enterprise_repo import judge_disposition_stats, list_deal_rooms
    from backend.app.core.enterprise_repo import list_witness_sessions

    ensure_learning_schema()
    uid = str(user["id"])
    learn = learning_stats(uid)
    judicial = judge_disposition_stats("", "437")
    clusters: List[Dict[str, Any]] = []
    try:
        from backend.app.core.research_service import similar_case_clusters

        clusters = similar_case_clusters(uid)
    except Exception:
        pass
    return {
        "learning": learn,
        "judicial": judicial,
        "deal_rooms": list_deal_rooms(uid),
        "witness_sessions": list_witness_sessions(uid),
        "similar_case_clusters": clusters,
    }


@router.post("/tuning/export")
def tuning_export(user: Dict[str, Any] = Depends(get_current_user)):
    """Stage 3 — export JSONL for fine-tuning from positive feedback."""
    from backend.app.core.tuning_export import export_positive_interactions

    return export_positive_interactions(str(user["id"]))


@router.post("/tuning/export-saas")
def tuning_export_saas(user: Dict[str, Any] = Depends(get_current_user)):
    """Stage 3 — billing, CRM, and e-discovery training pairs."""
    from backend.app.core.tuning_export import export_saas_training_pairs

    return export_saas_training_pairs(str(user["id"]))


@router.get("/tuning/neural/status")
def neural_tuning_status(user: Dict[str, Any] = Depends(get_current_user)):
    """Status of neural embedding fine-tuning."""
    from backend.app.core.neural_finetuning import ensure_neural_tuning_schema, tuning_status

    ensure_neural_tuning_schema()
    return tuning_status(str(user["id"]))


@router.post("/tuning/neural/collect")
def neural_tuning_collect(user: Dict[str, Any] = Depends(get_current_user)):
    """Backfill training pairs from thumbs-up and successful KB answers."""
    from backend.app.core.neural_finetuning import collect_pairs_from_feedback, ensure_neural_tuning_schema

    ensure_neural_tuning_schema()
    added = collect_pairs_from_feedback(str(user["id"]), limit=500)
    return {"ok": True, "pairs_added": added}


@router.post("/tuning/neural/train")
def neural_tuning_train(user: Dict[str, Any] = Depends(get_current_user)):
    """
    Fine-tune the embedding model on collected query–passage pairs.
    Improves KB dense retrieval for your firm's phrasing. Re-index after training.
    """
    from backend.app.core.neural_finetuning import ensure_neural_tuning_schema, train_embedding_model

    ensure_neural_tuning_schema()
    return train_embedding_model(str(user["id"]), scope="user")


@router.get("/engine/status")
def learning_engine_status(user: Dict[str, Any] = Depends(get_current_user)):
    """Unified adaptive + neural + answer memory + KB rescue stats."""
    from backend.app.core.learning_engine import ensure_learning_engine_schema, get_learning_engine_status

    ensure_learning_engine_schema()
    return get_learning_engine_status(str(user["id"]))


@router.post("/engine/auto-improve")
def learning_engine_auto_improve(user: Dict[str, Any] = Depends(get_current_user)):
    """
    Collect training pairs from feedback and run auto-improvement when thresholds are met.
    Safe to call manually from Settings — mirrors background maybe_auto_train.
    """
    from backend.app.core.learning_engine import ensure_learning_engine_schema, get_learning_engine_status
    from backend.app.core.neural_finetuning import (
        collect_pairs_from_feedback,
        ensure_neural_tuning_schema,
        maybe_auto_train,
        tuning_status,
    )

    ensure_learning_engine_schema()
    ensure_neural_tuning_schema()
    uid = str(user["id"])
    pairs_added = collect_pairs_from_feedback(uid, limit=500)
    before = tuning_status(uid)
    train_result = maybe_auto_train(uid)
    after = tuning_status(uid)
    status = get_learning_engine_status(uid)
    return {
        "ok": True,
        "pairs_added": pairs_added,
        "training_started": bool(train_result and train_result.get("ok")),
        "training": train_result,
        "unused_pairs_before": before.get("unused_pairs", 0),
        "unused_pairs_after": after.get("unused_pairs", 0),
        "status": status,
    }


@router.post("/engine/rescue-test")
def learning_engine_rescue_test(
    body: CorrectionRequest,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Test KB rescue chain for a query (diagnostics)."""
    from backend.app.core.learning_engine import ensure_learning_engine_schema, rescue_broken_kb

    ensure_learning_engine_schema()
    result = rescue_broken_kb(str(user["id"]), body.correction_query or body.previous_query)
    if not result:
        return {"ok": False, "rescued": False}
    answer, chunks, diag = result
    return {"ok": True, "rescued": True, "answer_preview": answer[:500], "diag": diag, "chunks": len(chunks)}


class CoachToggleRequest(BaseModel):
    enabled: bool = True


class CoachDirectivesRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=4000)
    apply: bool = True


@router.get("/tuning/coach/status")
def ollama_coach_status(user: Dict[str, Any] = Depends(get_current_user)):
    """Settings-only Gemini coach status for tuning local Ollama."""
    from backend.app.core.gemini_ollama_coach import coach_status, ensure_coach_schema

    ensure_coach_schema()
    membership = str(user.get("membership") or user.get("plan") or "Free")
    return coach_status(str(user["id"]), membership=membership)


@router.post("/tuning/coach/toggle")
def ollama_coach_toggle(
    body: CoachToggleRequest,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Enable/disable per-user AI tuning coach (Settings only — never runs in chat)."""
    from backend.app.core.gemini_ollama_coach import ensure_coach_schema, set_coach_enabled

    ensure_coach_schema()
    return set_coach_enabled(str(user["id"]), body.enabled)


@router.post("/tuning/coach/analyze")
def ollama_coach_analyze(user: Dict[str, Any] = Depends(get_current_user)):
    """Analyze feedback with Gemini — insights only, no auto-apply."""
    from backend.app.core.gemini_ollama_coach import analyze_feedback, ensure_coach_schema

    ensure_coach_schema()
    membership = str(user.get("membership") or user.get("plan") or "Free")
    return analyze_feedback(str(user["id"]), membership=membership, apply=False)


@router.post("/tuning/coach/apply")
def ollama_coach_apply(user: Dict[str, Any] = Depends(get_current_user)):
    """Apply insights from the last coaching analysis."""
    from backend.app.core.gemini_ollama_coach import apply_coaching_insights, ensure_coach_schema, get_coach_prefs

    ensure_coach_schema()
    prefs = get_coach_prefs(str(user["id"]))
    insights = prefs.get("last_insights") or {}
    if not insights:
        return {"ok": False, "error": "No coaching insights yet. Run analyze first."}
    applied = apply_coaching_insights(str(user["id"]), insights)
    return {"ok": True, "applied": applied, "insights": insights}


@router.post("/tuning/coach/run")
def ollama_coach_run(user: Dict[str, Any] = Depends(get_current_user)):
    """
    Full tuning cycle: analyze feedback → apply insights → neural train → Modelfile → ollama create.
    """
    from backend.app.core.gemini_ollama_coach import (
        coach_available,
        ensure_coach_schema,
        get_coach_prefs,
        run_coaching_cycle,
    )

    ensure_coach_schema()
    uid = str(user["id"])
    if not coach_available():
        return {
            "ok": False,
            "error": "AI tuning coach unavailable. Set GEMINI_OLLAMA_TUNING=1 and GEMINI_API_KEY in .env, then restart the backend.",
        }
    if not get_coach_prefs(uid).get("enabled"):
        return {
            "ok": False,
            "error": "Turn on “Enable automatic tuning coach” above, then run the cycle again.",
        }
    membership = str(user.get("membership") or user.get("plan") or "Free")
    return run_coaching_cycle(uid, membership=membership, auto_train=True)


@router.get("/automation/status")
def improvement_automation_status(user: Dict[str, Any] = Depends(get_current_user)):
    from backend.app.core.improvement_automation import automation_status

    return automation_status(str(user["id"]))


@router.post("/automation/run-now")
def improvement_automation_run_now(user: Dict[str, Any] = Depends(get_current_user)):
    """Queue or run full improvement pipeline (train, re-index, export, ollama create)."""
    from backend.app.core.improvement_automation import run_full_improvement_pipeline
    from backend.app.core.ml_job_queue import enqueue_ml_job, should_use_ml_queue

    membership = str(user.get("membership") or user.get("plan") or "Free")
    uid = str(user["id"])
    if should_use_ml_queue():
        out = enqueue_ml_job(
            uid,
            "improvement_pipeline",
            {"trigger": "manual", "membership": membership, "force_export": True},
        )
        if out.get("ok") is not False:
            return {"ok": True, "queued": True, **out}
    return run_full_improvement_pipeline(
        uid, trigger="manual", membership=membership, force_export=True
    )


@router.get("/automation/jobs")
def list_automation_jobs(
    limit: int = 10,
    user: Dict[str, Any] = Depends(get_current_user),
):
    from backend.app.core.ml_job_queue import list_user_ml_jobs

    return {"jobs": list_user_ml_jobs(str(user["id"]), limit=min(limit, 30))}


@router.get("/automation/jobs/{job_id}")
def get_automation_job(job_id: str, user: Dict[str, Any] = Depends(get_current_user)):
    from backend.app.core.ml_job_queue import get_ml_job

    job = get_ml_job(job_id)
    if not job or str(job.get("user_id")) != str(user["id"]):
        from fastapi import HTTPException

        raise HTTPException(404, "Job not found")
    return job


@router.get("/tuning/coach/directives")
def ollama_coach_get_directives(user: Dict[str, Any] = Depends(get_current_user)):
    from backend.app.core.gemini_ollama_coach import ensure_coach_schema, get_directives, list_coach_memories

    ensure_coach_schema()
    uid = str(user["id"])
    return {
        "directives_text": get_directives(uid),
        "memories": list_coach_memories(uid, limit=12),
    }


@router.post("/tuning/coach/directives")
def ollama_coach_save_directives(
    body: CoachDirectivesRequest,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Save user instructions for how Ollama should improve; optionally analyze with Gemini."""
    from backend.app.core.gemini_ollama_coach import (
        analyze_user_directives,
        ensure_coach_schema,
        save_directives,
    )

    ensure_coach_schema()
    uid = str(user["id"])
    if not body.apply:
        return save_directives(uid, body.text)
    membership = str(user.get("membership") or user.get("plan") or "Free")
    return analyze_user_directives(uid, body.text, membership=membership, apply=True)


class CoachScheduleToggleRequest(BaseModel):
    enabled: bool = True


@router.post("/tuning/coach/schedule/toggle")
def ollama_coach_schedule_toggle(
    body: CoachScheduleToggleRequest,
    user: Dict[str, Any] = Depends(get_current_user),
):
    """Enable/disable weekly auto-coaching when enough new feedback exists."""
    from backend.app.core.coach_scheduler import set_auto_schedule
    from backend.app.core.gemini_ollama_coach import ensure_coach_schema

    ensure_coach_schema()
    return set_auto_schedule(str(user["id"]), body.enabled)


@router.get("/tuning/coach/schedule/status")
def ollama_coach_schedule_status(user: Dict[str, Any] = Depends(get_current_user)):
    from backend.app.core.coach_scheduler import get_schedule_prefs
    from backend.app.core.gemini_ollama_coach import ensure_coach_schema

    ensure_coach_schema()
    return get_schedule_prefs(str(user["id"]))


@router.post("/tuning/coach/schedule/run-now")
def ollama_coach_schedule_run_now(user: Dict[str, Any] = Depends(get_current_user)):
    """Force scheduled improvement pass for current user."""
    from backend.app.core.coach_scheduler import count_feedback_since, run_auto_coach_for_user
    from backend.app.core.gemini_ollama_coach import ensure_coach_schema

    ensure_coach_schema()
    uid = str(user["id"])
    if count_feedback_since(uid) < 1:
        return {"ok": False, "error": "Need at least one feedback entry before improvement."}
    membership = str(user.get("membership") or user.get("plan") or "Free")
    return run_auto_coach_for_user(uid, membership=membership)


@router.post("/tuning/ollama/export-modelfile")
def ollama_export_modelfile(user: Dict[str, Any] = Depends(get_current_user)):
    """Export Ollama Modelfile + training.jsonl from coaching dataset."""
    from backend.app.core.gemini_ollama_coach import export_and_optionally_create_modelfile

    return export_and_optionally_create_modelfile(str(user["id"]))


@router.get("/tuning/ollama/export-status")
def ollama_export_status(user: Dict[str, Any] = Depends(get_current_user)):
    from backend.app.core.ollama_modelfile_export import latest_export_info

    return latest_export_info(str(user["id"]))


@router.get("/progress")
def learning_progress(user: Dict[str, Any] = Depends(get_current_user)):
    """Unified learning progress for Settings and chat bar."""
    from backend.app.core.learning_progress import get_learning_progress

    return get_learning_progress(str(user["id"]))


@router.post("/eval/holdout")
def run_holdout_eval_endpoint(user: Dict[str, Any] = Depends(get_current_user)):
    from backend.app.core.eval_holdout import run_holdout_eval

    return run_holdout_eval(str(user["id"]))


@router.get("/quality-gate")
def export_quality_gate_status(user: Dict[str, Any] = Depends(get_current_user)):
    from backend.app.core.export_quality_gate import check_export_quality_gate

    return check_export_quality_gate(str(user["id"]), force=False)


@router.get("/preferences")
def get_user_preferences(user: Dict[str, Any] = Depends(get_current_user)):
    from backend.app.core.user_preferences import ensure_preferences_schema, get_preference_profile

    ensure_preferences_schema()
    return get_preference_profile(str(user["id"]))


@router.get("/training/status")
def human_training_status(user: Dict[str, Any] = Depends(get_current_user)):
    from backend.app.core.human_training import ensure_human_training_schema, training_pipeline_status
    from backend.app.core.retrieval_learning import retrieval_learning_stats

    ensure_human_training_schema()
    uid = str(user["id"])
    return {
        "pipeline": training_pipeline_status(uid),
        "retrieval": retrieval_learning_stats(uid),
    }


@router.post("/training/export-sft")
def export_human_sft(user: Dict[str, Any] = Depends(get_current_user)):
    from backend.app.core.human_training import ensure_human_training_schema, export_sft_jsonl

    ensure_human_training_schema()
    return export_sft_jsonl(str(user["id"]))


@router.post("/training/export-dpo")
def export_human_dpo(user: Dict[str, Any] = Depends(get_current_user)):
    from backend.app.core.human_training import ensure_human_training_schema, export_dpo_jsonl

    ensure_human_training_schema()
    return export_dpo_jsonl(str(user["id"]))


@router.post("/training/train-sft")
def train_llm_sft(user: Dict[str, Any] = Depends(get_current_user)):
    """In-app LoRA SFT on human thumbs-up pairs."""
    from backend.app.core.llm_finetuning import train_lora_sft

    return train_lora_sft(str(user["id"]))


@router.post("/training/train-dpo")
def train_llm_dpo(user: Dict[str, Any] = Depends(get_current_user)):
    """In-app LoRA DPO on preference pairs."""
    from backend.app.core.llm_finetuning import train_dpo

    return train_dpo(str(user["id"]))


@router.get("/training/llm-status")
def llm_finetuning_status(user: Dict[str, Any] = Depends(get_current_user)):
    from backend.app.core.llm_finetuning import tuning_status
    from backend.app.core.reward_inference import get_reward_summary

    uid = str(user["id"])
    return {
        "llm": tuning_status(uid),
        "inference_rewards": get_reward_summary(uid),
    }
