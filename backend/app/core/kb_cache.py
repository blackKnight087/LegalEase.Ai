"""Short-lived in-memory cache for repeated KB retrieval queries."""

from __future__ import annotations



import hashlib

import os

import time

from pathlib import Path

from typing import Any, Dict, List, Optional, Tuple



_TTL_SEC = float(os.getenv("KB_CACHE_TTL_SEC", "300"))

_MAX_ENTRIES = int(os.getenv("KB_CACHE_MAX_ENTRIES", "256"))

_store: Dict[str, Tuple[float, List[Dict[str, Any]]]] = {}

_index_epoch: Dict[str, int] = {}





def _index_key(index_dir: Any) -> str:

    return str(Path(str(index_dir)).expanduser().resolve())





def index_version(index_dir: Any) -> str:

    """Fingerprint index dir + epoch so cache keys change after reindex."""

    base = Path(str(index_dir))

    parts: List[str] = [_index_key(index_dir), str(_index_epoch.get(_index_key(index_dir), 0))]

    for name in ("index.faiss", "index.pkl"):

        p = base / name

        if p.exists():

            try:

                st = p.stat()

                parts.append(f"{name}:{st.st_mtime_ns}:{st.st_size}")

            except OSError:

                parts.append(name)

    return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]





def _cache_key(query: str, index_dir: str, k: int, scope_key: str = "") -> str:

    version = index_version(index_dir)

    raw = f"{query.strip().lower()}|{index_dir}|{k}|{version}|{scope_key}"

    return hashlib.sha256(raw.encode()).hexdigest()[:32]





def get_cached_chunks(

    query: str,

    index_dir: Any,

    k: int,

    *,

    scope_key: str = "",

) -> Optional[List[Dict[str, Any]]]:

    key = _cache_key(query, str(index_dir), k, scope_key=scope_key)

    entry = _store.get(key)

    if not entry:

        return None

    ts, chunks = entry

    if time.time() - ts > _TTL_SEC:

        _store.pop(key, None)

        return None

    return [dict(c) for c in chunks]





def set_cached_chunks(

    query: str,

    index_dir: Any,

    k: int,

    chunks: List[Dict[str, Any]],

    *,

    scope_key: str = "",

) -> None:

    if len(_store) >= _MAX_ENTRIES:

        oldest = min(_store.items(), key=lambda x: x[1][0])[0]

        _store.pop(oldest, None)

    key = _cache_key(query, str(index_dir), k, scope_key=scope_key)

    _store[key] = (time.time(), chunks)





def invalidate_index_cache(index_dir: Any) -> int:

    """Bump epoch so prior retrieval cache keys no longer match."""

    ik = _index_key(index_dir)

    _index_epoch[ik] = _index_epoch.get(ik, 0) + 1

    return _index_epoch[ik]

