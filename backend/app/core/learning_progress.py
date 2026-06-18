"""Unified learning progress for UI — thumbs, signals, coach schedule, export gate."""
from __future__ import annotations

from typing import Any, Dict


def get_learning_progress(user_id: str) -> Dict[str, Any]:
    uid = str(user_id)
    out: Dict[str, Any] = {"user_id": uid}

    try:
        from backend.app.core.improvement_automation import (
            MIN_THUMBS_FOR_EXPORT,
            automation_status,
            count_thumbs_up,
        )

        auto = automation_status(uid)
        thumbs = count_thumbs_up(uid)
        out["thumbs_up"] = thumbs
        out["min_thumbs_for_export"] = MIN_THUMBS_FOR_EXPORT
        out["thumbs_progress_pct"] = min(100, int(100 * thumbs / max(1, MIN_THUMBS_FOR_EXPORT)))
        out["export_ready_count"] = thumbs >= MIN_THUMBS_FOR_EXPORT
        out["automation"] = auto
    except Exception as exc:
        out["automation_error"] = str(exc)[:120]

    try:
        from backend.app.core.export_quality_gate import check_export_quality_gate

        out["quality_gate"] = check_export_quality_gate(uid, force=False, include_holdout=False)
    except Exception as exc:
        out["quality_gate"] = {"passed": False, "error": str(exc)[:120]}

    try:
        from backend.app.core.learning_signals import signal_stats

        out["signals"] = signal_stats(uid)
    except Exception as exc:
        out["signals"] = {"error": str(exc)[:120]}

    try:
        from backend.app.core.human_training import training_pipeline_status

        out["training_pipeline"] = training_pipeline_status(uid)
    except Exception as exc:
        out["training_pipeline"] = {"error": str(exc)[:120]}

    try:
        from backend.app.core.coach_scheduler import get_schedule_prefs

        out["coach_schedule"] = get_schedule_prefs(uid)
    except Exception as exc:
        out["coach_schedule"] = {"error": str(exc)[:120]}

    try:
        from backend.app.core.user_preferences import get_preference_profile

        out["preferences"] = get_preference_profile(uid)
    except Exception as exc:
        out["preferences"] = {"error": str(exc)[:120]}

    try:
        from backend.app.core.retrieval_learning import retrieval_learning_stats

        out["retrieval"] = retrieval_learning_stats(uid)
    except Exception as exc:
        out["retrieval"] = {"error": str(exc)[:120]}

    gate = out.get("quality_gate") or {}
    auto = out.get("automation") or {}
    out["can_export_modelfile"] = bool(
        auto.get("export_ready") and gate.get("passed")
    )
    out["next_milestone"] = _next_milestone(out)
    return out


def _next_milestone(progress: Dict[str, Any]) -> str:
    thumbs = int(progress.get("thumbs_up") or 0)
    min_t = int(progress.get("min_thumbs_for_export") or 20)
    gate = progress.get("quality_gate") or {}
    if thumbs < min_t:
        return f"Rate {min_t - thumbs} more good answers (thumbs-up or copy) to unlock Modelfile export."
    if not gate.get("passed"):
        reasons = gate.get("reasons") or []
        if reasons:
            return str(reasons[0])
        return "Complete quality checks before tuned model export."
    if not (progress.get("automation") or {}).get("active_tuned_model"):
        return "Export ready — run improvement pipeline or wait for daily automation."
    return "Tuned model active — keep giving feedback to improve retrieval and style."
