"""FAISS index validation and automatic repair."""
from __future__ import annotations

import logging
import shutil
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger("legalease.faiss")

INDEX_NAME = "index"


def validate_faiss_index(index_dir: Path) -> Tuple[bool, str]:
    """Return (ok, reason). Detect dimension mismatch, missing pkl, zero vectors."""
    index_dir = Path(index_dir)
    faiss_path = index_dir / f"{INDEX_NAME}.faiss"
    pkl_path = index_dir / f"{INDEX_NAME}.pkl"
    if not faiss_path.exists():
        return False, "missing_faiss_file"
    if not pkl_path.exists():
        return False, "missing_pkl_file"
    try:
        import faiss

        idx = faiss.read_index(str(faiss_path))
        ntotal = int(getattr(idx, "ntotal", 0) or 0)
        dim = int(getattr(idx, "d", 0) or 0)
        if dim <= 0:
            return False, "invalid_dimension"
        if ntotal < 0:
            return False, "invalid_vector_count"
        return True, f"ok vectors={ntotal} dim={dim}"
    except Exception as exc:
        logger.exception("[FAISS] validate failed: %s", index_dir)
        return False, str(exc)[:200]


def backup_corrupt_index(index_dir: Path) -> Optional[Path]:
    index_dir = Path(index_dir)
    if not index_dir.exists():
        return None
    backup = index_dir.parent / f"{index_dir.name}_corrupt_backup"
    try:
        if backup.exists():
            shutil.rmtree(backup, ignore_errors=True)
        shutil.copytree(index_dir, backup)
        logger.info("[FAISS] Backed up corrupt index to %s", backup)
        return backup
    except Exception as exc:
        logger.warning("[FAISS] Backup failed: %s", exc)
        return None


def clear_index_files(index_dir: Path) -> None:
    index_dir = Path(index_dir)
    for name in (f"{INDEX_NAME}.faiss", f"{INDEX_NAME}.pkl"):
        p = index_dir / name
        if p.exists():
            p.unlink()
    logger.info("[FAISS] Cleared index files in %s", index_dir)


def rebuild_index(
    user_id: str,
    *,
    matter_id: str = "",
    use_ocr: Optional[bool] = None,
    only_doc_ids: Optional[list] = None,
    progress_callback=None,
) -> Tuple[bool, str]:
    """Rebuild FAISS without deleting uploaded documents."""
    from backend.app.core.embedding_manager import EmbeddingManager, EmbeddingState

    mgr = EmbeddingManager.instance()
    mgr._set_state(EmbeddingState.RECOVERING)
    try:
        if not mgr.wait_until_ready(timeout_sec=120):
            return False, f"Embeddings not ready: {mgr.get_status().get('error')}"

        from app import build_faiss_index

        mid = (matter_id or "").strip() or None
        ok, msg = build_faiss_index(
            user_id,
            only_doc_ids=only_doc_ids,
            use_ocr=use_ocr,
            incremental=False if only_doc_ids else True,
            rebuild_all=not only_doc_ids,
            matter_id=mid,
            progress_callback=progress_callback,
        )
        return bool(ok), str(msg or "")
    finally:
        if mgr._model:
            mgr._set_state(EmbeddingState.READY)


def repair_if_corrupt(
    user_id: str,
    index_dir: Path,
    *,
    matter_id: str = "",
    use_ocr: Optional[bool] = None,
) -> Tuple[bool, str]:
    ok, reason = validate_faiss_index(index_dir)
    if ok:
        return True, reason
    logger.warning("[FAISS] Corrupt index detected (%s): %s", reason, index_dir)
    backup_corrupt_index(index_dir)
    clear_index_files(index_dir)
    try:
        from rag import _invalidate_faiss_vs_cache
        from backend.app.core.kb_cache import invalidate_index_cache

        invalidate_index_cache(index_dir)
        _invalidate_faiss_vs_cache(index_dir)
    except Exception:
        pass
    return rebuild_index(user_id, matter_id=matter_id, use_ocr=use_ocr)
