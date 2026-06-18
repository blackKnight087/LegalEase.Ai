"""
LegalEase RAG Module - Retrieval-Augmented Generation
=====================================================

WHY RAG INSTEAD OF MODEL TRAINING?
----------------------------------
RAG (Retrieval-Augmented Generation) is preferred over fine-tuning because:

1. DYNAMIC KNOWLEDGE: Legal documents change frequently. RAG allows instant
   updates by simply adding/removing documents without retraining.

2. SOURCE ATTRIBUTION: RAG can cite exact sources (document name, page, chunk).
   Fine-tuned models cannot reliably cite sources.

3. HALLUCINATION CONTROL: By grounding responses in retrieved documents,
   RAG dramatically reduces hallucinations - critical for legal applications.

4. COST EFFECTIVE: No expensive GPU training required. Works with any LLM.

5. TRANSPARENCY: Users can verify answers against source documents.

WHY NO FINE-TUNING REQUIRED?
----------------------------
Fine-tuning is NOT needed because:
- Laws and legal precedents change frequently
- Fine-tuning would "bake in" outdated information
- Prompt engineering + RAG achieves the same behavioral control
- The LLM's general reasoning ability is sufficient when given proper context
"""

import logging
import math
import os
import re
import threading
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional, Tuple, Union

from dotenv import load_dotenv
from langchain_core.embeddings import Embeddings
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_community.vectorstores import FAISS

from llms import clear_embeddings_cache, get_embeddings, get_generator
from prompts import kb_prompt
from answer_orchestrator import orchestrate_kb_answer, intent_aware_fallback
from intent_engine import classify_intent

logger = logging.getLogger(__name__)

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")
load_dotenv()

FAISS_DIR = BASE_DIR / "faiss_index_global"
FAISS_DIR.mkdir(parents=True, exist_ok=True)
FAISS_BASE_DIR = BASE_DIR / "faiss_indexes"
FAISS_BASE_DIR.mkdir(parents=True, exist_ok=True)

CHUNK_SIZE = int(os.getenv("RAG_CHUNK_SIZE", "500"))
CHUNK_OVERLAP = int(os.getenv("RAG_CHUNK_OVERLAP", "100"))
RAG_MAX_CHUNK = int(os.getenv("RAG_MAX_CHUNK", "600"))
RAG_MAX_CHUNKS_PER_DOC = int(os.getenv("RAG_MAX_CHUNKS_PER_DOC", "1000"))
RAG_EMBED_BATCH_QUEUE = int(os.getenv("RAG_EMBED_BATCH_QUEUE", "50"))
RAG_MAX_PAGES_PARALLEL = int(os.getenv("RAG_MAX_PAGES_PARALLEL", "2"))
RAG_FAST_INDEX = os.getenv("RAG_FAST_INDEX", "0").lower() in {"1", "true", "yes"}
INDEX_EMBED_BATCH = int(os.getenv("RAG_INDEX_EMBED_BATCH", "64"))
DEFAULT_RETRIEVAL_K = int(os.getenv("RAG_RETRIEVAL_K", "10"))
TOP_K_DENSE = int(os.getenv("RAG_TOP_K_DENSE", "60"))
TOP_K_KEYWORD = int(os.getenv("RAG_TOP_K_KEYWORD", "60"))
MMR_LAMBDA = float(os.getenv("RAG_MMR_LAMBDA", "0.65"))
# L2 distance on normalized embeddings: lower = more similar (0 = identical).
SCORE_THRESHOLD = float(os.getenv("RAG_SCORE_THRESHOLD", "1.6"))
RAG_CONFIDENCE_THRESHOLD = float(os.getenv("RAG_CONFIDENCE_THRESHOLD", "0.28"))
SIMILARITY_GATE = float(os.getenv("RAG_SIMILARITY_THRESHOLD", "0.30"))
MIN_RETRIEVAL_THRESHOLD = float(os.getenv("RAG_MIN_RETRIEVAL_THRESHOLD", "0.28"))
RAG_RERANK_MODEL = os.getenv("RAG_RERANK_MODEL", "cross-encoder/ms-marco-MiniLM-L-6-v2")
# Fast path: heuristic rerank only (MiniLM cross-encoder is slow on CPU)
RAG_ENABLE_CROSS_ENCODER = os.getenv("RAG_ENABLE_CROSS_ENCODER", "0").lower() in {"1", "true", "yes"}
RERANK_POOL_SIZE = int(os.getenv("RAG_RERANK_POOL_SIZE", "50"))
FINAL_TOP_K = int(os.getenv("RAG_FINAL_TOP_K", "8"))
RAG_MAX_QUERY_EXPANSIONS = max(2, min(12, int(os.getenv("RAG_MAX_QUERY_EXPANSIONS", "5"))))
RAG_LARGE_INDEX_SPARSE_CAP = int(os.getenv("RAG_LARGE_INDEX_SPARSE_CAP", "5000"))
FAISS_VS_CACHE_MAX = max(1, int(os.getenv("FAISS_VS_CACHE_MAX", "8")))
SECTION_SCORE_BOOST = float(os.getenv("RAG_SECTION_BOOST", "0.45"))
INDEX_NAME = "index"

from kb_response_state import KB_NOT_FOUND_MESSAGE

NOT_FOUND_PHRASE = KB_NOT_FOUND_MESSAGE
ENTERPRISE_NOT_FOUND = "❌ **NOT FOUND IN DOCUMENTS: The requested information is not present.**"

_last_query_error: Optional[str] = None
_embeddings_singleton: Optional[Any] = None
_embeddings_init_lock = threading.Lock()
_reranker_singleton: Optional[Any] = None
_reranker_init_lock = threading.Lock()
_last_query_diagnostics: Dict[str, Any] = {}
_faiss_vs_cache: Dict[str, Tuple[int, Any]] = {}
_faiss_vs_cache_lock = threading.Lock()


def _is_low_information_payload(text: str) -> bool:
    normalized = (text or "").strip().lower()
    if not normalized:
        return True
    if normalized in {"{}", "{ }", "[]", "[ ]", "null", "none", '""', "''", "n/a", "na"}:
        return True
    if len(re.findall(r"[A-Za-z0-9]", normalized)) < 5:
        return True
    return False


def handle_legal_query(
    query: str,
    context_chunks: List[Dict],
    temperature: float = 0.12,
    max_tokens: int = 2048,
    conversation_history: Optional[List[Dict]] = None,
) -> str:
    """
    Intent-aware synthesis: understand → reason → answer (not chunk dump).
    """
    if not context_chunks:
        return NOT_FOUND_PHRASE

    from answer_orchestrator import synthesize_kb_answer_from_chunks
    from response_cleaner import clean_kb_response

    answer = clean_kb_response(
        synthesize_kb_answer_from_chunks(
            query,
            context_chunks,
            conversation_history,
            temperature=temperature,
            max_tokens=max_tokens,
        )
    )
    if _is_low_information_payload(answer):
        profile = classify_intent(query, conversation_history)
        answer = intent_aware_fallback(query, context_chunks, profile)
    return clean_kb_response(answer) or NOT_FOUND_PHRASE


def _compose_grounded_markdown(chunks: List[Dict], question: str) -> str:
    """Intent-shaped deterministic fallback (no Main Answer / Key Findings spam)."""
    if not chunks:
        return NOT_FOUND_PHRASE
    profile = classify_intent(question)
    return intent_aware_fallback(question, chunks, profile)


def get_last_query_error() -> Optional[str]:
    """Return the last retrieval error message (for UI/debug)."""
    return _last_query_error


def get_last_query_diagnostics() -> Dict[str, Any]:
    """Return diagnostics from the last hybrid retrieval run."""
    return dict(_last_query_diagnostics or {})


def _resolve_index_dir(index_dir: Optional[Union[str, Path]] = None) -> Path:
    """Resolve an index directory, defaulting to the legacy global index."""
    target = Path(index_dir) if index_dir else FAISS_DIR
    return target.expanduser().resolve()


def _is_safe_index_dir(index_dir: Path) -> bool:
    """Only load FAISS pickle metadata from project-owned index directories."""
    safe_roots = [BASE_DIR.resolve(), FAISS_DIR.resolve(), FAISS_BASE_DIR.resolve()]
    env_faiss = os.getenv("FAISS_BASE_DIR", "").strip()
    if env_faiss:
        safe_roots.append(Path(env_faiss).expanduser().resolve())
    try:
        resolved = index_dir.resolve()
        return any(resolved == root or root in resolved.parents for root in safe_roots)
    except Exception:
        return False


def index_exists(index_dir: Optional[Union[str, Path]] = None) -> bool:
    """Return True when a persisted FAISS index is present on disk."""
    target = _resolve_index_dir(index_dir)
    return (target / f"{INDEX_NAME}.faiss").exists() and (target / f"{INDEX_NAME}.pkl").exists()


def count_index_vectors(index_dir: Optional[Union[str, Path]] = None) -> int:
    """Return number of vectors in the on-disk FAISS index (0 if missing)."""
    target = _resolve_index_dir(index_dir)
    faiss_path = target / f"{INDEX_NAME}.faiss"
    if not faiss_path.exists():
        return 0
    try:
        import faiss

        idx = faiss.read_index(str(faiss_path))
        return int(getattr(idx, "ntotal", 0) or 0)
    except Exception as exc:
        logger.warning("count_index_vectors failed for %s: %s", target, exc)
        return 0


class HuggingFaceEmbeddingsWrapper(Embeddings):
    """
    Fallback wrapper to make SentenceTransformer compatible with LangChain FAISS.
    """

    def __init__(self, model: Optional[str] = None, st_model: Any = None):
        model_name = model or os.getenv("HF_EMBEDDING_MODEL", "sentence-transformers/all-MiniLM-L6-v2")
        if st_model is not None:
            self._model = st_model
        else:
            from backend.app.core.embedding_manager import get_manager

            self._model = get_manager().get_model(wait_timeout=float(os.getenv("EMBEDDING_MODEL_LOAD_TIMEOUT_SEC", "90")))
        logger.info("[EMBEDDING] LangChain wrapper ready: %s", model_name)

    def _encode(self, texts: List[str]) -> List[List[float]]:
        if hasattr(self._model, "encode"):
            try:
                embeddings = self._model.encode(
                    texts,
                    convert_to_numpy=True,
                    normalize_embeddings=True,
                    show_progress_bar=False,
                )
            except TypeError:
                embeddings = self._model.encode(texts, convert_to_numpy=True)
            return embeddings.tolist()

        if hasattr(self._model, "embed_documents"):
            return self._model.embed_documents(texts)

        raise TypeError("Embedding model must provide encode() or embed_documents().")

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        return self._encode(texts)

    def embed_query(self, text: str) -> List[float]:
        return self._encode([text])[0]

    # Keep callable compatibility for older/langchain-community FAISS paths.
    def __call__(self, text: str) -> List[float]:
        return self.embed_query(text)


def _reset_embeddings_singleton() -> None:
    global _embeddings_singleton
    _embeddings_singleton = None
    try:
        clear_embeddings_cache()
    except Exception:
        pass


def _build_langchain_embeddings(model_name: str):
    use_lc_hf = os.getenv("RAG_USE_LANGCHAIN_HF", "0").lower() in {"1", "true", "yes"}
    if not use_lc_hf:
        wrapper = HuggingFaceEmbeddingsWrapper(model_name)
        logger.info(
            "RAG embeddings: SentenceTransformer wrapper (%s). "
            "Set RAG_USE_LANGCHAIN_HF=1 to use langchain_huggingface.",
            model_name,
        )
        return wrapper

    try:
        from langchain_huggingface import HuggingFaceEmbeddings

        logger.info("[INFO] Embeddings initialized via langchain_huggingface: %s", model_name)
        return HuggingFaceEmbeddings(
            model_name=model_name,
            model_kwargs={"device": "cpu"},
            encode_kwargs={"normalize_embeddings": True},
        )
    except Exception as exc:
        logger.warning(
            "langchain_huggingface unavailable (%s); using SentenceTransformer wrapper.",
            exc,
        )
        return HuggingFaceEmbeddingsWrapper(model_name)


def _get_langchain_embeddings():
    """Single embedding path via EmbeddingManager (no duplicate loaders)."""
    from backend.app.core.embedding_manager import get_manager

    return get_manager().get_langchain_embeddings()


def _chunk_size_for_text(text: str, document_type: str = "") -> Tuple[int, int]:
    """Adaptive chunking — long PDFs get slightly larger chunks; dense statutes stay smaller."""
    length = len(text or "")
    size = CHUNK_SIZE
    overlap = CHUNK_OVERLAP
    dt = (document_type or "").lower()
    if length > 400_000:
        size = min(int(os.getenv("RAG_CHUNK_SIZE_LONG", "700")), RAG_MAX_CHUNK)
        overlap = min(120, size // 5)
    elif length > 120_000:
        size = min(int(os.getenv("RAG_CHUNK_SIZE_MEDIUM", "600")), RAG_MAX_CHUNK)
        overlap = min(100, size // 5)
    elif dt in ("contract", "nda", "agreement", "court_judgment", "general"):
        size = min(int(os.getenv("RAG_CHUNK_SIZE_PROSE", "550")), RAG_MAX_CHUNK)
    return size, overlap


def _subdivide_chunk_text(
    block: str,
    start: int,
    *,
    chunk_size: int,
    chunk_overlap: int,
) -> List[Tuple[str, int, int]]:
    """Split an oversized statute block into embedding-sized pieces (keeps start offsets)."""
    block = (block or "").strip()
    if len(block) <= RAG_MAX_CHUNK:
        return [(block, start, start + len(block))]
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    pieces = [p.strip() for p in splitter.split_text(block) if p and p.strip()]
    if not pieces:
        return [(block[:RAG_MAX_CHUNK], start, start + min(len(block), RAG_MAX_CHUNK))]
    out: List[Tuple[str, int, int]] = []
    cursor = start
    for piece in pieces:
        idx = block.find(piece, max(0, cursor - start))
        if idx < 0:
            idx = 0
        abs_start = start + idx
        abs_end = abs_start + len(piece)
        out.append((piece, abs_start, abs_end))
        cursor = abs_end
    return out


def _split_by_statute_headings(
    text: str,
    *,
    chunk_size: int = CHUNK_SIZE,
    chunk_overlap: int = CHUNK_OVERLAP,
) -> List[Tuple[str, int, int]]:
    """
    Split on IPC Section headings, then sub-divide large blocks so big PDFs index hundreds
    of vectors — not a dozen megachunks.
    """
    heading_count = len(
        re.findall(r"\b(?:IPC|BNS|CrPC|BNSS)\s+Section\s+\d{1,4}[a-z]?\b", text, re.I)
    )
    if heading_count < 3:
        return []
    parts = re.split(
        r"(?=\b(?:IPC|BNS|CrPC|BNSS)\s+Section\s+\d{1,4}[a-z]?\b)",
        text,
        flags=re.I,
    )
    out: List[Tuple[str, int, int]] = []
    cursor = 0
    for part in parts:
        block = (part or "").strip()
        if len(block) < 40:
            continue
        idx = text.find(block, cursor)
        if idx < 0:
            idx = cursor
        for piece, pstart, pend in _subdivide_chunk_text(
            block, idx, chunk_size=chunk_size, chunk_overlap=chunk_overlap
        ):
            out.append((piece, pstart, pend))
        cursor = idx + max(1, len(block) // 2)
    if len(out) < 5:
        return []
    logger.info("[INDEX] Statute-heading split produced %s chunks (sub-divided)", len(out))
    return out


def _split_text(text: str, document_type: str = "") -> List[Tuple[str, int, int]]:
    """Chunk text for indexing. Fast mode uses paragraph splitter only."""
    from kb_preprocess import clean_legal_text, split_semantic_legal_chunks

    cleaned = clean_legal_text(text)
    if not cleaned:
        return []
    chunk_size, chunk_overlap = _chunk_size_for_text(cleaned, document_type)
    statute_chunks = _split_by_statute_headings(
        cleaned, chunk_size=chunk_size, chunk_overlap=chunk_overlap
    )
    if statute_chunks:
        return statute_chunks
    if RAG_FAST_INDEX:
        splitter = RecursiveCharacterTextSplitter(
            chunk_size=chunk_size,
            chunk_overlap=chunk_overlap,
            separators=["\n\n", "\n", ". ", " ", ""],
        )
        chunks = [c.strip() for c in splitter.split_text(cleaned) if c and c.strip()]
        out: List[Tuple[str, int, int]] = []
        cursor = 0
        for chunk in chunks:
            idx = cleaned.find(chunk, cursor)
            if idx == -1:
                idx = cursor
            out.append((chunk, idx, idx + len(chunk)))
            cursor = idx + len(chunk)
        return out
    positions = split_semantic_legal_chunks(
        cleaned,
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        max_chunk=RAG_MAX_CHUNK,
    )
    if positions:
        return positions
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        separators=["\n\n", "\n", ". ", " ", ""],
    )
    chunks = [c.strip() for c in splitter.split_text(cleaned) if c and c.strip()]
    out: List[Tuple[str, int, int]] = []
    cursor = 0
    for chunk in chunks:
        idx = cleaned.find(chunk, cursor)
        if idx == -1:
            idx = cursor
        out.append((chunk, idx, idx + len(chunk)))
        cursor = idx + len(chunk)
    return out


def _format_result(doc, score: float) -> Dict:
    meta = dict(doc.metadata or {})
    return {
        "content": doc.page_content,
        "metadata": meta,
        "score": float(score),
    }


def _tokenize(text: str) -> List[str]:
    return re.findall(r"[a-z0-9][a-z0-9._-]{1,}", (text or "").lower())


_MONEY_AMOUNT_RE = re.compile(
    r"\b(\d+(?:\.\d+)?)\s*(?:lakh|lakhs|lac|lacs|crore|crores|cr|₹|rs\.?|rupees?)\b",
    re.I,
)


def _money_amount_tokens(query: str) -> set:
    """Digits used as currency amounts — not IPC/BNS section numbers."""
    out: set = set()
    for m in _MONEY_AMOUNT_RE.finditer(query or ""):
        out.add(m.group(1).lower())
        try:
            out.add(str(int(float(m.group(1)))))
        except ValueError:
            pass
    return out


def _extract_query_signals(query: str) -> Dict[str, Any]:
    q = (query or "").strip()
    ql = q.lower()
    money_nums = _money_amount_tokens(q)
    try:
        from backend.app.services.legal_query_parser import (
            default_law_for_query,
            section_numbers_from_query,
        )

        parser_secs = section_numbers_from_query(q)
    except Exception:
        parser_secs = []
    sections = {m.lower() for m in re.findall(r"\bsection\s+([0-9]{1,4}[a-z]?)\b", ql)}
    for ps in parser_secs:
        sections.add(ps.lower())
    articles = {m.lower() for m in re.findall(r"\barticle\s+([0-9]{1,4}[a-z]?)\b", ql)}
    bare_identifiers = {
        m.lower()
        for m in re.findall(r"\b([0-9]{1,4}[a-z]?)\b", ql)
        if m.lower() not in money_nums
    }
    # IPC 307, BNS 120, IT Act 66C (without the word "section")
    for law_tag, num in re.findall(
        r"\b(ipc|bns|crpc|it\s*act)\s+([0-9]{1,4}[a-z]?)\b", ql
    ):
        bare_identifiers.add(num.lower())
        sections.add(num.lower())
    # Standalone statutory tokens: 66C, 307
    for token in re.findall(r"\b([0-9]{1,4}[a-z])\b", ql):
        bare_identifiers.add(token.lower())
    laws = []
    law_patterns = [
        ("ipc", r"\bipc\b|\bindian penal code\b"),
        ("bns", r"\bbns\b|\bbharatiya nyaya sanhita\b"),
        ("crpc", r"\bcrpc\b|\bcriminal procedure code\b"),
        ("it act", r"\bit act\b|\binformation technology act\b"),
        ("evidence act", r"\bevidence act\b"),
    ]
    for law_name, pattern in law_patterns:
        if re.search(pattern, ql):
            laws.append(law_name)

    # Named phrase cues for entity/case queries.
    title_phrases = [
        p.strip() for p in re.findall(r"\b([A-Z][a-z]+(?:\s+[A-Z][a-z]+){1,5})\b", q)
        if len(p.strip()) >= 5
    ]

    return {
        "sections": sorted(sections),
        "articles": sorted(articles),
        "bare_identifiers": sorted(bare_identifiers),
        "laws": laws,
        "title_phrases": title_phrases[:8],
    }


def _detect_query_type(query: str) -> str:
    ql = (query or "").lower()
    signals = _extract_query_signals(query)
    try:
        from kb_legal_query_rewrite import is_law_replacement_query

        if is_law_replacement_query(query):
            return "law_mapping"
    except Exception:
        pass
    if re.search(r"\b(compare|difference|differentiate|distinguish|versus|vs\.?|between)\b", ql):
        return "cross_document"
    if (
        signals["sections"]
        or signals["articles"]
        or re.search(r"\b(?:section|sec\.?)\s*[0-9]{1,4}[a-z]?\b", ql)
        or re.search(r"\b(?:ipc|bns)\s*[0-9]{1,4}[a-z]?\b", ql)
        or (signals["bare_identifiers"] and signals["laws"])
        or re.search(r"\b(66c|66c\b|ipc\s*\d+|bns\s*\d+)", ql)
    ):
        return "exact_identifier"
    if re.search(r"\b(which case|what case|judgment|judgement|v\.| vs |recognized|recognised)\b", ql):
        return "entity"
    return "conceptual"


def _expand_queries(query: str, query_type: str, signals: Dict[str, Any]) -> List[str]:
    q = (query or "").strip()
    expansions: List[str] = [q]

    if query_type == "exact_identifier":
        for sec in signals.get("sections", []):
            expansions.extend([
                f"Section {sec}",
                f"Section {sec.upper()}",
                sec,
            ])
            for law in signals.get("laws", []):
                expansions.append(f"Section {sec} {law}")
                if law == "ipc":
                    expansions.extend([f"IPC {sec}", f"Indian Penal Code Section {sec}"])
                if law == "bns":
                    expansions.extend([f"BNS {sec}", f"Bharatiya Nyaya Sanhita Section {sec}"])
                if law == "it act":
                    expansions.extend([
                        f"IT Act {sec}",
                        f"Section {sec} IT Act",
                        f"Information Technology Act Section {sec}",
                    ])
        for art in signals.get("articles", []):
            expansions.extend([
                f"Article {art}",
                f"Article {art.upper()}",
                art,
            ])
        for bare in signals.get("bare_identifiers", []):
            expansions.extend([bare, bare.upper(), f"Section {bare}"])
            if "ipc" in signals.get("laws", []):
                expansions.append(f"IPC {bare}")
            if "it act" in signals.get("laws", []):
                expansions.append(f"66C" if bare == "66c" else f"IT Act {bare}")

    elif query_type == "entity":
        core = re.sub(r"\b(which|what|who|is|the|a|an|of|in|to|for)\b", " ", q, flags=re.I)
        core = re.sub(r"\s+", " ", core).strip()
        if core:
            expansions.extend([core, f"case law {core}", f"judgment {core}"])
        expansions.extend(signals.get("title_phrases", []))

    elif query_type == "cross_document":
        parts = re.split(r"\b(?:and|vs\.?|versus|between)\b", q, flags=re.I)
        for part in parts:
            part = part.strip(" ,.-")
            if len(part) >= 4:
                expansions.append(part)
        expansions.append(f"comparison {q}")

    elif query_type == "law_mapping":
        try:
            from kb_legal_query_rewrite import expand_law_replacement_queries

            expansions.extend(expand_law_replacement_queries(q))
        except Exception:
            expansions.extend([f"IPC BNS replacement {q}", f"CrPC BNSS mapping {q}"])

    else:  # conceptual
        expansions.extend([
            f"definition {q}",
            f"explain {q}",
        ])
        try:
            from kb_legal_query_rewrite import is_law_replacement_query, expand_law_replacement_queries

            if is_law_replacement_query(q):
                expansions.extend(expand_law_replacement_queries(q))
        except Exception:
            pass

    seen = set()
    unique: List[str] = []
    for item in expansions:
        norm = re.sub(r"\s+", " ", (item or "").strip().lower())
        if not norm or norm in seen:
            continue
        seen.add(norm)
        unique.append(item.strip())
    return unique[:RAG_MAX_QUERY_EXPANSIONS]


def _result_key(meta: Dict[str, Any], content: str) -> Tuple[str, str, str, str]:
    return (
        str(meta.get("doc_id", "")),
        str(meta.get("filename", "")),
        str(meta.get("chunk_index", "")),
        (content or "")[:96],
    )


def _semantic_from_distance(distance: float) -> float:
    # Convert L2 distance (lower better) into bounded similarity score.
    return 1.0 / (1.0 + max(distance, 0.0))


def exact_section_lookup(
    index_dir: Optional[Union[str, Path]],
    sections: List[str],
    *,
    law: str = "IPC",
    top_k: int = 12,
) -> List[Dict[str, Any]]:
    """
    Priority 1 retrieval: metadata + strict text match for section numbers.
    Never returns chunks for a different section when the target section exists.
    """
    if not sections or not index_dir:
        return []
    target_dir = _resolve_index_dir(index_dir)
    if not index_exists(target_dir):
        return []

    law_u = (law or "IPC").upper()
    want = [s.lower() for s in sections if s]
    hits: List[Dict[str, Any]] = []
    seen: set = set()

    try:
        vs = _load_docstore_only(target_dir)
        if not vs:
            return []
        store = getattr(vs, "docstore", None)
        doc_dict = getattr(store, "_dict", None) or {}
        for doc in doc_dict.values():
            content = getattr(doc, "page_content", None) or str(doc)
            meta = dict(getattr(doc, "metadata", None) or {})
            meta_secs = {
                s.strip().lower()
                for s in (meta.get("section_numbers") or "").split(",")
                if s.strip()
            }
            primary_meta = str(meta.get("primary_section") or "").lower()
            matched_sec = None
            for sec in want:
                if primary_meta and primary_meta != sec:
                    continue
                if sec in meta_secs and _chunk_matches_strict_section(content, sec, law_u):
                    matched_sec = sec
                    break
                if _chunk_matches_strict_section(content, sec, law_u):
                    matched_sec = sec
                    break
            if not matched_sec:
                continue
            key = _result_key(meta, content)
            if key in seen:
                continue
            seen.add(key)
            node = {
                "content": content,
                "metadata": meta,
                "dense_distance": 0.05,
                "semantic_score": 0.98,
                "lexical_score": 1.0,
                "metadata_score": 1.0,
                "section_boost": 1.0,
                "hybrid_score": 2.5,
                "final_score": 2.5,
                "entity": matched_sec,
                "retrieval_mode": "exact_section",
            }
            hits.append(node)
    except Exception as exc:
        logger.debug("exact_section_lookup failed: %s", exc)
        return []

    per_sec: Dict[str, List[Dict[str, Any]]] = {s: [] for s in want}
    for h in hits:
        sec = str(h.get("entity") or "")
        if sec in per_sec:
            per_sec[sec].append(h)

    ordered: List[Dict[str, Any]] = []
    for sec in want:
        ordered.extend(per_sec.get(sec, [])[: max(2, top_k // max(1, len(want)))])

    if ordered:
        return ordered[:top_k]

    try:
        from kb_legal_query_rewrite import keyword_fallback_from_vectorstore

        vs = _load_faiss_vectorstore(target_dir, _get_langchain_embeddings())
        if vs:
            for sec in want:
                kw = keyword_fallback_from_vectorstore(
                    vs, f"{law_u} Section {sec}", top_k=6
                )
                for h in kw:
                    if _chunk_matches_strict_section(h.get("content", ""), sec, law_u):
                        hc = dict(h)
                        hc["final_score"] = 2.2
                        hc["retrieval_mode"] = "exact_section_keyword"
                        hc["entity"] = sec
                        ordered.append(hc)
    except Exception:
        pass

    return ordered[:top_k]


def _chunk_matches_strict_section(content: str, section: str, law: str = "") -> bool:
    """True when chunk clearly references the requested section (not another IPC section)."""
    text = (content or "").lower()
    sec = (section or "").lower()
    if not sec:
        return False

    law_l = (law or "ipc").lower()
    if law_l in ("ipc", "indian penal code", ""):
        if re.search(
            rf"\b(?:ipc|indian penal code)\s*(?:section\s*)?{re.escape(sec)}\b",
            text,
            re.I,
        ):
            return True
        if re.search(rf"\bsection\s*{re.escape(sec)}\b", text, re.I) and re.search(
            r"\b(?:ipc|indian penal code|penal code)\b", text, re.I
        ):
            return True
    elif law_l == "bns":
        if re.search(rf"\bbns\s*(?:section\s*)?{re.escape(sec)}\b", text, re.I):
            return True
    else:
        if re.search(rf"\bsection\s*{re.escape(sec)}\b", text, re.I):
            return True

    # Bare "Section N" in indexed text (common in PDF extracts without IPC prefix)
    if re.search(rf"\bsection\s*{re.escape(sec)}\b", text, re.I):
        other_secs = {
            m.group(1).lower()
            for m in re.finditer(r"\bsection\s+(\d{1,4}[a-z]?)\b", text, re.I)
        }
        if not other_secs or sec in other_secs:
            return True

    for m in re.finditer(r"\b(?:ipc|bns)\s*(?:section\s*)?(\d{1,4}[a-z]?)\b", text, re.I):
        found = m.group(1).lower()
        if found == sec:
            return True
    return False


def strict_section_filter(
    candidates: Dict[Tuple[str, str, str, str], Dict[str, Any]],
    signals: Dict[str, Any],
    *,
    law: str = "",
) -> Dict[Tuple[str, str, str, str], Dict[str, Any]]:
    """
    For statute queries, keep only chunks that mention the target section(s).

    Applied before hybrid scoring to prevent semantic drift to generic intros.
    """
    sections = signals.get("sections") or signals.get("bare_identifiers") or []
    if not sections:
        return candidates

    filtered: Dict[Tuple[str, str, str, str], Dict[str, Any]] = {}
    for key, node in candidates.items():
        content = str(node.get("content", ""))
        if any(_chunk_matches_strict_section(content, sec, law) for sec in sections):
            filtered[key] = node

    if filtered:
        return filtered
    return {}


def _exact_section_priority_boost(content: str, signals: Dict[str, Any], query_type: str) -> float:
    """
    Large boost when chunk clearly contains the requested section number.
    Overrides semantic drift toward generic IPC introductions.
    """
    text = (content or "").lower()
    target_sections = signals.get("sections") or signals.get("bare_identifiers") or []
    if not target_sections:
        return 0.0
    if not target_sections:
        return 0.0

    best = 0.0
    for sec in target_sections:
        if re.search(rf"\bsection\s*{re.escape(sec)}\b", text):
            best = max(best, 1.0)
        elif re.search(rf"\b(?:ipc|s\.)\s*{re.escape(sec)}\b", text):
            best = max(best, 0.92)
        elif re.search(rf"\b{re.escape(sec)}\b", text):
            best = max(best, 0.45)

    # Demote generic intros when user asked for a specific section
    if best < 0.5 and re.search(
        r"\bgeneral principles\b|\bprimary criminal code\b|\bintroduction\b|\boverview of\b",
        text,
    ):
        best = -0.35
    return best


def _metadata_match_score(query: str, content: str, filename: str, signals: Dict[str, Any], query_type: str) -> float:
    text = f"{filename}\n{content}".lower()
    score = 0.0
    checks = 0

    for sec in signals.get("sections", []):
        checks += 1
        if re.search(rf"\bsection\s*{re.escape(sec)}\b", text):
            score += 1.25
        elif re.search(rf"\b(?:ipc|s\.)\s*{re.escape(sec)}\b", text):
            score += 1.1
        elif re.search(rf"\b{re.escape(sec)}\b", text):
            score += 0.55

    for art in signals.get("articles", []):
        checks += 1
        if re.search(rf"\barticle\s*{re.escape(art)}\b", text):
            score += 1.0

    for law in signals.get("laws", []):
        checks += 1
        if law in text:
            score += 1.0

    if query_type == "entity":
        for phrase in signals.get("title_phrases", []):
            p = phrase.lower().strip()
            if len(p) < 4:
                continue
            checks += 1
            if p in text:
                score += 1.0
        if "case" in (query or "").lower() and re.search(r"\b(v\.|vs\.?|case|judgment|judgement)\b", text):
            checks += 1
            score += 1.0

    if checks == 0:
        return 0.0
    return max(0.0, min(1.0, score / checks))


def _keyword_terms(query: str) -> List[str]:
    terms = _tokenize(query)
    stop = {
        "the", "and", "for", "are", "what", "who", "when", "where", "how",
        "from", "with", "that", "this", "your", "about", "does", "have",
        "listed", "document", "uploaded", "question", "explain",
    }
    return [t for t in terms if t not in stop and len(t) > 2]


def _sparse_scores(vs: FAISS, query: str, top_n: int = 40) -> List[Tuple[object, float]]:
    """BM25-style sparse retrieval over indexed chunks."""
    terms = _keyword_terms(query)
    if not terms:
        return []

    docs: List[Tuple[Any, List[str]]] = []
    for _idx, doc_id in vs.index_to_docstore_id.items():
        doc = vs.docstore.search(doc_id)
        if not doc or not getattr(doc, "page_content", ""):
            continue
        docs.append((doc, _tokenize(doc.page_content)))
    if not docs:
        return []

    n_docs = len(docs)
    avgdl = sum(len(tokens) for _, tokens in docs) / max(n_docs, 1)
    term_df: Dict[str, int] = {t: 0 for t in terms}
    for _, tokens in docs:
        token_set = set(tokens)
        for term in terms:
            if term in token_set:
                term_df[term] += 1

    k1, b = 1.5, 0.75
    scored: List[Tuple[Any, float]] = []
    for doc, tokens in docs:
        dl = len(tokens)
        if dl == 0:
            continue
        token_count: Dict[str, int] = {}
        for t in tokens:
            if t in term_df:
                token_count[t] = token_count.get(t, 0) + 1
        score = 0.0
        for term in terms:
            tf = token_count.get(term, 0)
            if tf <= 0:
                continue
            df = max(term_df.get(term, 0), 1)
            idf = math.log((n_docs - df + 0.5) / (df + 0.5) + 1.0)
            numer = tf * (k1 + 1.0)
            denom = tf + k1 * (1.0 - b + b * (dl / max(avgdl, 1.0)))
            score += idf * (numer / max(denom, 1e-9))
        if score > 0:
            scored.append((doc, score))

    scored.sort(key=lambda item: item[1], reverse=True)
    return scored[:top_n]


def _get_reranker() -> Optional[Any]:
    global _reranker_singleton
    if _reranker_singleton is not None:
        return None if _reranker_singleton is False else _reranker_singleton
    if not RAG_ENABLE_CROSS_ENCODER:
        _reranker_singleton = False
        return None
    with _reranker_init_lock:
        if _reranker_singleton is not None:
            return None if _reranker_singleton is False else _reranker_singleton
        try:
            from sentence_transformers import CrossEncoder

            device = (os.getenv("RAG_RERANK_DEVICE") or "cpu").strip() or "cpu"
            _reranker_singleton = CrossEncoder(
                RAG_RERANK_MODEL,
                device=device,
                max_length=int(os.getenv("RAG_RERANK_MAX_LENGTH", "512")),
            )
            logger.info("RAG reranker initialized: %s (device=%s)", RAG_RERANK_MODEL, device)
            return _reranker_singleton
        except Exception as exc:
            logger.warning(
                "Cross-encoder reranker unavailable (%s). Using heuristic reranking.",
                exc,
            )
            _reranker_singleton = False
            return None


def warmup_rag_reranker() -> bool:
    """Pre-load cross-encoder at startup (avoids first-query latency)."""
    if not RAG_ENABLE_CROSS_ENCODER:
        return True
    reranker = _get_reranker()
    return reranker is not None and reranker is not False


def _heuristic_rerank_score(query: str, content: str, metadata_score: float) -> float:
    q_terms = _keyword_terms(query)
    if not q_terms:
        return metadata_score
    text = (content or "").lower()
    overlap = sum(1 for t in q_terms if t in text)
    lexical = overlap / max(len(q_terms), 1)
    return max(0.0, min(1.0, (0.7 * lexical) + (0.3 * metadata_score)))


def _law_mismatch_penalty(content: str, query: str) -> float:
    """Deprioritize IT Act / cyber chunks when user asked about IPC."""
    ql = (query or "").lower()
    text = (content or "").lower()
    wants_ipc = bool(re.search(r"\b(ipc|indian penal code|all\s+ipc)\b", ql))
    if not wants_ipc:
        return 0.0
    has_ipc = bool(re.search(r"\b(ipc|indian penal code)\b", text))
    is_it_cyber = bool(
        re.search(
            r"\b(it act|information technology|cyber\s*law|section\s+66[cd]|electronic)\b",
            text,
        )
    )
    if is_it_cyber and not has_ipc:
        return -0.85
    if has_ipc:
        return 0.12
    return 0.0


def _mmr_select(
    ranked: List[Dict[str, Any]],
    query: str,
    k: int,
    lambda_mult: float = MMR_LAMBDA,
) -> List[Dict[str, Any]]:
    """Maximal Marginal Relevance — reduce near-duplicate chunks."""
    if not ranked or k <= 0:
        return []
    if len(ranked) <= k:
        return ranked[:k]

    selected: List[Dict[str, Any]] = []
    remaining = list(ranked)
    q_terms = set(_keyword_terms(query))

    def _sim_to_query(node: Dict[str, Any]) -> float:
        text = (node.get("content") or "").lower()
        if not q_terms:
            return float(node.get("final_score", 0.0))
        overlap = sum(1 for t in q_terms if t in text)
        return float(node.get("final_score", 0.0)) + 0.1 * overlap

    def _sim_docs(a: str, b: str) -> float:
        ta = set(_tokenize(a)[:80])
        tb = set(_tokenize(b)[:80])
        if not ta or not tb:
            return 0.0
        return len(ta & tb) / max(len(ta | tb), 1)

    selected.append(remaining.pop(0))
    while remaining and len(selected) < k:
        best_idx = 0
        best_mmr = -1e9
        for i, cand in enumerate(remaining):
            rel = _sim_to_query(cand)
            div = max(
                (_sim_docs(cand.get("content", ""), s.get("content", "")) for s in selected),
                default=0.0,
            )
            mmr = lambda_mult * rel - (1.0 - lambda_mult) * div
            if mmr > best_mmr:
                best_mmr = mmr
                best_idx = i
        selected.append(remaining.pop(best_idx))
    return selected


def _validate_context(query: str, query_type: str, signals: Dict[str, Any], chunks: List[Dict]) -> Tuple[bool, float, str]:
    if not chunks:
        return False, 0.0, "no_chunks"

    top = chunks[:3]
    joined = "\n".join((c.get("content", "") or "") for c in top).lower()

    if query_type == "exact_identifier":
        sec_hits = 0
        identifiers = (
            list(signals.get("sections", []))
            + list(signals.get("articles", []))
            + list(signals.get("bare_identifiers", []))
        )
        required = max(1, len(set(identifiers)))
        for ident in set(identifiers):
            if re.search(rf"\bsection\s*{re.escape(ident)}\b", joined):
                sec_hits += 1
            elif re.search(rf"\b{re.escape(ident)}\b", joined):
                sec_hits += 1
        valid = sec_hits >= 1
        score = min(1.0, sec_hits / max(required, 1))
        return valid, score, "identifier_validation"

    if query_type == "entity":
        has_case_signal = bool(re.search(r"\b(v\.|vs\.?|case|judgment|judgement)\b", joined))
        phrase_hits = 0
        for phrase in signals.get("title_phrases", []):
            if phrase.lower() in joined:
                phrase_hits += 1
        score = 0.4 + (0.3 if has_case_signal else 0.0) + min(0.3, 0.1 * phrase_hits)
        return score >= 0.45, min(1.0, score), "entity_validation"

    if query_type == "cross_document":
        terms = _keyword_terms(query)
        distinct_hits = sum(1 for t in terms[:8] if t in joined)
        score = min(1.0, distinct_hits / max(3, min(8, len(terms) or 1)))
        return score >= 0.35, score, "cross_validation"

    if query_type == "law_mapping":
        try:
            from kb_legal_query_rewrite import chunk_matches_law_query

            matched = sum(
                1 for c in top if chunk_matches_law_query(c.get("content", ""), query)
            )
            if matched >= 1:
                return True, min(1.0, 0.5 + 0.2 * matched), "law_mapping_validation"
        except Exception:
            pass
        if re.search(r"\b(ipc|bns|crpc|bnss|bsa)\b", joined):
            return True, 0.72, "law_mapping_keyword_validation"

    # conceptual
    terms = _keyword_terms(query)
    overlap = sum(1 for t in terms[:8] if t in joined)
    score = min(1.0, overlap / max(2, min(8, len(terms) or 1)))
    return True, score, "concept_validation"


def _load_docstore_only(index_dir: Path) -> Any:
    """Load FAISS docstore from pickle without initializing embedding models."""
    import pickle

    pkl_path = index_dir / f"{INDEX_NAME}.pkl"
    if not pkl_path.exists():
        return None
    try:
        with open(pkl_path, "rb") as fh:
            payload = pickle.load(fh)
    except Exception as exc:
        logger.warning("Docstore pickle load failed for %s: %s", index_dir, exc)
        return None

    docstore = None
    index_to_docstore_id = None
    if isinstance(payload, tuple) and len(payload) >= 2:
        docstore, index_to_docstore_id = payload[0], payload[1]
    elif isinstance(payload, dict):
        docstore = payload.get("docstore")
        index_to_docstore_id = payload.get("index_to_docstore_id")
    elif hasattr(payload, "docstore") and hasattr(payload, "index_to_docstore_id"):
        docstore = payload.docstore
        index_to_docstore_id = payload.index_to_docstore_id

    if docstore is None or index_to_docstore_id is None:
        return None

    class _DocstoreView:
        pass

    view = _DocstoreView()
    view.docstore = docstore
    view.index_to_docstore_id = index_to_docstore_id
    return view


def _scan_docstore_generic(view: Any, query: str, top_k: int = 8) -> List[Dict[str, Any]]:
    """BM25-style scan over docstore when dense embeddings are unavailable."""
    terms = _keyword_terms(query)
    if not terms or view is None:
        return []

    try:
        doc_ids = view.index_to_docstore_id.values()
    except Exception:
        return []

    scored: List[Tuple[Dict[str, Any], float]] = []
    for doc_id in doc_ids:
        try:
            doc = view.docstore.search(doc_id)
        except Exception:
            continue
        if not doc or not getattr(doc, "page_content", ""):
            continue
        content = doc.page_content
        cl = content.lower()
        score = sum(1.0 for t in terms if t in cl)
        if score <= 0:
            continue
        meta = dict(getattr(doc, "metadata", {}) or {})
        result = {
            "content": content,
            "metadata": meta,
            "score": max(0.0, 1.0 - (0.5 / max(score, 1))),
            "final_score": min(1.0, 0.3 + score * 0.15),
            "hybrid_score": min(1.0, 0.3 + score * 0.15),
            "source": "docstore_keyword",
        }
        scored.append((result, score))

    scored.sort(key=lambda x: x[1], reverse=True)
    return [item for item, _ in scored[:top_k]]


def _filter_results_by_scope(
    chunks: List[Dict[str, Any]],
    document_scope: Optional[Dict[str, Any]],
) -> List[Dict[str, Any]]:
    if not chunks or not (document_scope or {}).get("strict"):
        return chunks
    from backend.app.core.kb_doc_scope import chunk_matches_scope

    return [
        c
        for c in chunks
        if chunk_matches_scope(c.get("metadata") or {}, document_scope or {})
    ]


def _keyword_fallback_docstore_only(
    query: str,
    index_dir: Path,
    *,
    original_query: str = "",
    top_k: int = DEFAULT_RETRIEVAL_K,
    document_scope: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Last-resort retrieval when embedding model fails — scan indexed text only."""
    if (document_scope or {}).get("strict"):
        return []
    view = _load_docstore_only(index_dir)
    if view is None:
        return []
    try:
        from kb_legal_query_rewrite import keyword_fallback_from_vectorstore

        hits = keyword_fallback_from_vectorstore(view, original_query or query, top_k=top_k)
        if not hits:
            hits = _scan_docstore_generic(view, original_query or query, top_k=top_k)
        hits = _filter_results_by_scope(hits, document_scope)
        if hits:
            logger.info(
                "[KB RAG] Docstore keyword fallback returned %s chunks for %r",
                len(hits),
                (original_query or query)[:80],
            )
        return hits
    except Exception as exc:
        logger.warning("Docstore keyword fallback failed: %s", exc)
        return []


def _try_keyword_fallback(
    vs: Any,
    original_query: str,
    *,
    rewritten_query: str = "",
    expanded_queries: Optional[List[str]] = None,
    reason: str = "",
    document_scope: Optional[Dict[str, Any]] = None,
) -> List[Dict[str, Any]]:
    """Secondary exact-keyword retrieval before returning empty results."""
    if (document_scope or {}).get("strict"):
        return []
    try:
        from kb_legal_query_rewrite import keyword_fallback_from_vectorstore, log_rag_debug

        fallback = keyword_fallback_from_vectorstore(vs, original_query, top_k=DEFAULT_RETRIEVAL_K)
        if not fallback:
            view = _load_docstore_only(_resolve_index_dir(locals().get("target_dir", FAISS_DIR)))
            if view is not None:
                fallback = _scan_docstore_generic(view, original_query, top_k=DEFAULT_RETRIEVAL_K)
        fallback = _filter_results_by_scope(fallback, document_scope)
        if fallback:
            logger.info("[KB RAG] Keyword fallback recovered %s chunks (%s)", len(fallback), reason)
            log_rag_debug(
                user_query=original_query,
                rewritten_query=rewritten_query or original_query,
                expanded_queries=expanded_queries or [],
                top_chunks=fallback,
                selected_chunk=fallback[0] if fallback else None,
            )
            return fallback
    except Exception as exc:
        logger.warning("Keyword fallback failed: %s", exc)
    return []


def _response_fails_self_check(answer: str, query: str, snippets: List[Dict]) -> bool:
    if _is_low_information_payload(answer):
        return True
    text = (answer or "").strip().lower()
    if not text:
        return True
    if "information not found in document." in text:
        return False
    query_signals = _extract_query_signals(query)
    if query_signals["sections"]:
        if not any(re.search(rf"\b{re.escape(sec)}\b", text) for sec in query_signals["sections"]):
            return True
    if query_signals["articles"]:
        if not any(re.search(rf"\b{re.escape(art)}\b", text) for art in query_signals["articles"]):
            return True

    # Ensure answer uses retrieved evidence terms.
    ctx = " ".join((c.get("content", "") or "") for c in snippets).lower()
    tokens = [t for t in _keyword_terms(query) if len(t) > 2][:8]
    if tokens:
        overlap = sum(1 for t in tokens if t in text and t in ctx)
        if overlap < 1:
            return True
    return False


def index_documents(
    documents: List[Dict[str, str]],
    progress_callback: Optional[Callable[[str], None]] = None,
    index_dir: Optional[Union[str, Path]] = None,
) -> Tuple[bool, str, int]:
    """
    Build FAISS index from provided documents.

    Returns:
        (ok, message, total_chunks)
    """
    global _last_query_error
    _last_query_error = None

    if not documents:
        return False, "No documents supplied for indexing.", 0

    target_dir = _resolve_index_dir(index_dir)
    if not _is_safe_index_dir(target_dir):
        return False, "Unsafe FAISS index path refused.", 0
    target_dir.mkdir(parents=True, exist_ok=True)

    logger.info("[INFO] Building FAISS index at %s", target_dir)
    embeddings = _get_langchain_embeddings()
    texts: List[str] = []
    metadatas: List[Dict[str, str]] = []
    total_pages = 0

    for doc_idx, doc in enumerate(documents, start=1):
        filename = doc.get("filename", "doc")
        if progress_callback:
            progress_callback(f"Processing {filename} ({doc_idx}/{len(documents)})")

        raw_text = doc.get("text") or ""
        if isinstance(raw_text, tuple):
            raw_text = raw_text[0] if raw_text else ""
        text = str(raw_text).strip()
        if not text:
            logger.warning("[WARN] No text for document: %s", filename)
            continue

        page_markers = re.findall(r"\[Page (\d+)\]", doc.get("text") or "")
        if page_markers:
            total_pages += len(page_markers)
        else:
            total_pages += max(1, len(text) // 2500)

        logger.info(
            "[INFO] PDF loaded successfully: %s | text length=%s chars",
            filename,
            len(text),
        )

        doc_texts, doc_meta = _documents_to_chunk_batches([doc])
        try:
            from backend.app.core.pdf_index_quality import is_underchunked

            page_est = len(re.findall(r"\[Page\s+\d+\]", text, re.I)) or max(1, len(text) // 2500)
            if is_underchunked(text, len(doc_texts), page_est):
                logger.error(
                    "[INDEX] Under-chunked %s: %s chunks for %s chars / ~%s pages — check PDF extraction",
                    filename,
                    len(doc_texts),
                    len(text),
                    page_est,
                )
        except Exception:
            pass
        texts.extend(doc_texts)
        metadatas.extend(doc_meta)
        logger.info("[INFO] Created %s chunks for %s", len(doc_texts), filename)

    if not texts:
        return False, "No text extracted from supplied documents.", 0

    logger.info("[INFO] Embedding %s chunks (chunk_size=%s, overlap=%s)", len(texts), CHUNK_SIZE, CHUNK_OVERLAP)

    try:
        from backend.app.core.memory_efficiency import adaptive_index_embed_batch, maybe_collect_garbage

        batch_cap = adaptive_index_embed_batch()
    except Exception:
        batch_cap = INDEX_EMBED_BATCH

        def maybe_collect_garbage(_label: str = "") -> None:
            return None

    batch_size = max(4, min(batch_cap, INDEX_EMBED_BATCH, RAG_EMBED_BATCH_QUEUE))
    vs = None
    embedded = 0
    failed_batches = 0
    total_batches = max(1, (len(texts) + batch_size - 1) // batch_size)
    for start in range(0, len(texts), batch_size):
        end = min(start + batch_size, len(texts))
        batch_texts = texts[start:end]
        batch_meta = metadatas[start:end]
        bn = start // batch_size + 1
        if progress_callback:
            progress_callback(f"Embedding batch {bn}/{total_batches} ({len(batch_texts)} chunks)")
        try:
            if vs is None:
                vs = FAISS.from_texts(batch_texts, embedding=embeddings, metadatas=batch_meta)
            else:
                vs.add_texts(batch_texts, metadatas=batch_meta)
            embedded += len(batch_texts)
            logger.info("[FAISS] Saved batch %s/%s", bn, total_batches)
            if bn % 3 == 0 or bn == total_batches:
                vs.save_local(str(target_dir), index_name=INDEX_NAME)
            maybe_collect_garbage(f"batch_{bn}")
        except Exception as exc:
            failed_batches += 1
            logger.exception("[EMBEDDING] Batch %s failed: %s", bn, exc)
            maybe_collect_garbage(f"batch_{bn}_err")
            if embedded == 0 and bn >= 2:
                return False, f"Embedding failed early ({exc}) — index incomplete.", embedded
            continue

    if vs is None:
        return False, "Failed to create FAISS index.", 0

    if embedded < max(1, int(len(texts) * 0.85)):
        vs.save_local(str(target_dir), index_name=INDEX_NAME)
        return (
            False,
            f"Only {embedded}/{len(texts)} chunks embedded ({failed_batches} batch failures). "
            "Retry re-index or reduce RAG_INDEX_EMBED_BATCH / free RAM.",
            embedded,
        )

    vs.save_local(str(target_dir), index_name=INDEX_NAME)
    logger.info("[FAISS] Indexed %s/%s chunks | pages~%s", embedded, len(texts), total_pages)
    try:
        from backend.app.core.kb_cache import invalidate_index_cache

        invalidate_index_cache(target_dir)
        _invalidate_faiss_vs_cache(target_dir)
    except Exception:
        pass
    return True, f"Indexed {embedded} chunks.", embedded


def _invalidate_faiss_vs_cache(index_dir: Union[str, Path]) -> None:
    key = str(Path(index_dir).expanduser().resolve())
    with _faiss_vs_cache_lock:
        _faiss_vs_cache.pop(key, None)


def _load_faiss_vectorstore(target_dir: Path, embeddings: Embeddings) -> FAISS:
    """Load FAISS from disk with a small in-process cache (avoids reload every query)."""
    key = str(target_dir.resolve())
    faiss_file = target_dir / "index.faiss"
    mtime_ns = faiss_file.stat().st_mtime_ns if faiss_file.exists() else 0
    with _faiss_vs_cache_lock:
        entry = _faiss_vs_cache.get(key)
        if entry and entry[0] == mtime_ns:
            return entry[1]
    vs = FAISS.load_local(
        str(target_dir),
        embeddings,
        index_name=INDEX_NAME,
        allow_dangerous_deserialization=True,
    )
    with _faiss_vs_cache_lock:
        if len(_faiss_vs_cache) >= FAISS_VS_CACHE_MAX:
            oldest = next(iter(_faiss_vs_cache))
            _faiss_vs_cache.pop(oldest, None)
        _faiss_vs_cache[key] = (mtime_ns, vs)
    return vs


def _documents_to_chunk_batches(documents: List[Dict[str, str]]) -> Tuple[List[str], List[Dict[str, str]]]:
    """Build chunk texts + metadata from document dicts (already extracted text)."""
    from kb_preprocess import (
        extract_law_tags,
        extract_page_number,
        extract_page_range,
        extract_section_heading,
        extract_section_numbers,
    )
    from document_classifier import classify_document
    from pathlib import Path as _Path

    texts: List[str] = []
    metadatas: List[Dict[str, str]] = []
    for doc in documents:
        filename = doc.get("filename", "doc")
        raw_text = doc.get("text") or ""
        if isinstance(raw_text, tuple):
            raw_text = raw_text[0] if raw_text else ""
        text = str(raw_text).strip()
        if not text:
            continue
        doc_type = classify_document(text[:12000], str(filename))
        chunks = _split_text(text, doc_type)
        file_type = _Path(str(filename)).suffix.lower().lstrip(".") or "unknown"
        for chunk_index, item in enumerate(chunks):
            if isinstance(item, tuple):
                if len(item) >= 3:
                    chunk, start, end = item[0], item[1], item[2]
                elif len(item) == 2:
                    chunk, start = item[0], item[1]
                    end = int(start) + len(str(chunk))
                else:
                    chunk = str(item[0] if item else "")
                    start, end = 0, len(chunk)
            else:
                chunk, start, end = str(item), 0, len(str(item))
            chunk = str(chunk)
            if len(chunk.strip()) < 20:
                continue
            chunk_type = classify_document(chunk[:8000], str(filename))
            if not chunk_type or chunk_type == "unknown":
                chunk_type = doc_type
            try:
                from backend.app.core.case_narrative_engine import classify_chunk_content_kind

                content_kind = classify_chunk_content_kind(chunk)
            except Exception:
                content_kind = "general"
            if len(texts) >= RAG_MAX_CHUNKS_PER_DOC:
                logger.warning(
                    "[EMBEDDING] Chunk cap %s reached for %s — truncating",
                    RAG_MAX_CHUNKS_PER_DOC,
                    filename,
                )
                break
            texts.append(chunk)
            sec_nums = extract_section_numbers(chunk)
            law_tags = extract_law_tags(chunk)
            try:
                from kb_preprocess import extract_primary_section

                _prim = extract_primary_section(chunk)
                if isinstance(_prim, tuple):
                    primary_code, primary_sec = _prim
                else:
                    primary_code, primary_sec = "", str(_prim or "")
            except ImportError:
                primary_code, primary_sec = "", ""
            except (ValueError, TypeError):
                primary_code, primary_sec = "", ""
            if not primary_sec and sec_nums:
                primary_sec = sec_nums[0]
            if not primary_code and law_tags:
                primary_code = law_tags[0].upper()
            page_rng = extract_page_range(chunk) or str(extract_page_number(chunk) or doc.get("page_number", ""))
            metadatas.append(
                {
                    "doc_id": str(doc.get("doc_id", "")),
                    "filename": str(filename),
                    "source_file": str(filename),
                    "chunk_index": str(chunk_index),
                    "chunk_id": f"{filename}:{chunk_index}",
                    "start_char": str(start),
                    "end_char": str(end),
                    "page_number": str(extract_page_number(chunk) or doc.get("page_number", "")),
                    "page_range": page_rng,
                    "section_heading": extract_section_heading(chunk)[:200],
                    "section_numbers": ",".join(sec_nums),
                    "primary_section": primary_sec,
                    "legal_code": primary_code,
                    "law_tags": ",".join(law_tags),
                    "file_type": file_type,
                    "document_type": chunk_type,
                    "content_kind": content_kind,
                    "extraction_method": str(doc.get("extraction_method", "")),
                    "created_at": str(doc.get("created_at", "")),
                }
            )
    return texts, metadatas


def append_documents_to_index(
    documents: List[Dict[str, str]],
    index_dir: Optional[Union[str, Path]] = None,
    progress_callback: Optional[Callable[[str], None]] = None,
) -> Tuple[bool, str, int]:
    """Add new document chunks to an existing FAISS index (fast upload path)."""
    if not documents:
        return False, "No documents to append.", 0

    target_dir = _resolve_index_dir(index_dir)
    if not _is_safe_index_dir(target_dir):
        return False, "Unsafe FAISS index path refused.", 0

    texts, metadatas = _documents_to_chunk_batches(documents)
    if not texts:
        return False, "No text extracted from document.", 0

    embeddings = _get_langchain_embeddings()
    target_dir.mkdir(parents=True, exist_ok=True)

    if progress_callback:
        progress_callback(f"Embedding {len(texts)} new chunks…")

    try:
        from backend.app.core.memory_efficiency import adaptive_index_embed_batch, maybe_collect_garbage

        batch_cap = adaptive_index_embed_batch()
    except Exception:
        batch_cap = INDEX_EMBED_BATCH

        def maybe_collect_garbage(_label: str = "") -> None:
            return None

    batch_size = max(4, min(batch_cap, INDEX_EMBED_BATCH, RAG_EMBED_BATCH_QUEUE))
    vs = None
    if index_exists(target_dir):
        ok, reason = True, "ok"
        try:
            from backend.app.core.faiss_recovery import validate_faiss_index

            ok, reason = validate_faiss_index(target_dir)
        except Exception:
            pass
        if ok:
            try:
                vs = _load_faiss_vectorstore(target_dir, embeddings)
            except Exception as exc:
                logger.warning("[FAISS] Load failed (%s), rebuilding slice", exc)
                vs = None

    total_batches = max(1, (len(texts) + batch_size - 1) // batch_size)
    for start in range(0, len(texts), batch_size):
        end = min(start + batch_size, len(texts))
        batch_texts = texts[start:end]
        batch_meta = metadatas[start:end]
        bn = start // batch_size + 1
        if progress_callback:
            progress_callback(f"Chunk {end}/{len(texts)} — batch {bn}/{total_batches}")
        try:
            if vs is None:
                vs = FAISS.from_texts(batch_texts, embedding=embeddings, metadatas=batch_meta)
            else:
                vs.add_texts(batch_texts, metadatas=batch_meta)
            if bn % 3 == 0 or bn == total_batches:
                vs.save_local(str(target_dir), index_name=INDEX_NAME)
                logger.info("[FAISS] Checkpoint batch %s/%s", bn, total_batches)
            maybe_collect_garbage(f"append_{bn}")
        except Exception as exc:
            logger.exception("[EMBEDDING] Append batch %s failed", bn)
            maybe_collect_garbage(f"append_{bn}_err")
            continue

    if vs is None:
        return False, "Failed to update FAISS index.", 0

    vs.save_local(str(target_dir), index_name=INDEX_NAME)
    logger.info("[FAISS] Appended %s chunks to %s", len(texts), target_dir)
    try:
        from backend.app.core.kb_cache import invalidate_index_cache

        invalidate_index_cache(target_dir)
        _invalidate_faiss_vs_cache(target_dir)
    except Exception:
        pass
    return True, f"Added {len(texts)} chunks.", len(texts)


def query_kb(
    query: str,
    k: int = DEFAULT_RETRIEVAL_K,
    index_dir: Optional[Union[str, Path]] = None,
    *,
    doc_id: Optional[str] = None,
    filename: Optional[str] = None,
    document_scope: Optional[Dict[str, Any]] = None,
) -> List[Dict]:
    """
    Enterprise multi-stage retrieval pipeline:
    1) query understanding
    2) query expansion
    3) hybrid retrieval (dense + sparse + metadata)
    4) reranking
    5) context validation
    6) confidence gating
    """
    global _last_query_error, _last_query_diagnostics
    _last_query_error = None
    _last_query_diagnostics = {}
    scope_key = ""

    target_dir = _resolve_index_dir(index_dir)
    if not _is_safe_index_dir(target_dir):
        _last_query_error = f"Unsafe index path: {target_dir}"
        logger.error(_last_query_error)
        return []

    if not index_exists(target_dir):
        _last_query_error = f"No FAISS index at {target_dir}"
        logger.warning("[WARN] %s", _last_query_error)
        return []

    try:
        from backend.app.core.kb_cache import get_cached_chunks, set_cached_chunks

        scope_for_cache = document_scope or {}
        if scope_for_cache.get("strict"):
            scope_key = "|".join(
                filter(
                    None,
                    [
                        str(scope_for_cache.get("doc_id", "")),
                        str(scope_for_cache.get("filename", "")),
                    ],
                )
            )
        if not scope_for_cache.get("strict"):
            cached = get_cached_chunks(
                query, target_dir, k, scope_key=scope_key
            )
            if cached is not None:
                logger.debug("[KB CACHE] hit query=%r k=%s", query[:60], k)
                return cached
    except Exception:
        pass

    try:
        try:
            embeddings = _get_langchain_embeddings()
        except Exception as emb_exc:
            _last_query_error = f"Embeddings unavailable: {emb_exc}"
            logger.error("[WARN] %s", _last_query_error)
            fallback = _keyword_fallback_docstore_only(
                query,
                target_dir,
                original_query=query,
                top_k=max(k, DEFAULT_RETRIEVAL_K),
                document_scope=document_scope,
            )
            if fallback:
                return fallback
            return []

        vs = _load_faiss_vectorstore(target_dir, embeddings)
        from kb_retrieval import (
            build_section_retrieval_queries,
            ensure_per_section_chunks,
            extract_comparison_sections,
            is_comparison_query,
        )

        from kb_query_types import detect_query_type as _kb_detect_type, retrieval_k_for_type

        kb_type = _kb_detect_type(query)
        original_query = query
        rewritten_query = query
        try:
            from kb_legal_query_rewrite import is_law_replacement_query, normalize_legal_query

            if is_law_replacement_query(query):
                rewritten_query = normalize_legal_query(query)
                query = rewritten_query
        except Exception:
            pass

        query_type = _detect_query_type(query)
        signals = _extract_query_signals(query)
        k = max(k, retrieval_k_for_type(kb_type, k))

        # Comparison: independent per-entity retrieval (never one shared query pool)
        if is_comparison_query(original_query):
            try:
                from kb_compare_engine import extract_typed_entities, retrieve_for_comparison

                typed = extract_typed_entities(original_query)
                if len(typed) >= 2:
                    compared = retrieve_for_comparison(
                        typed,
                        target_dir,
                        base_query="",
                        k_per_entity=max(6, k // len(typed) + 2),
                    )
                    if compared:
                        try:
                            set_cached_chunks(query, target_dir, k, compared)
                        except Exception:
                            pass
                        return compared[:k]
            except Exception as exc:
                logger.debug("Split comparison retrieval failed (%s); falling back.", exc)

        target_sections = list(signals.get("sections") or signals.get("bare_identifiers") or [])
        law_hint = "IPC"
        if re.search(r"\bipc\b", original_query, re.I):
            law_hint = "IPC"
        elif re.search(r"\bbns\b", original_query, re.I):
            law_hint = "BNS"
        else:
            try:
                from backend.app.services.legal_query_parser import default_law_for_query

                law_hint = default_law_for_query(original_query).upper()
            except Exception:
                pass

        is_replacement_q = False
        try:
            from kb_legal_query_rewrite import is_law_replacement_query

            is_replacement_q = is_law_replacement_query(original_query)
        except Exception:
            pass

        if target_sections and query_type == "exact_identifier" and not is_replacement_q:
            if len(target_sections) == 1 or (
                len(target_sections) >= 2 and not is_comparison_query(original_query)
            ):
                exact_hits = exact_section_lookup(
                    target_dir,
                    target_sections[:4],
                    law=law_hint,
                    top_k=max(k, 8),
                )
                if exact_hits:
                    try:
                        set_cached_chunks(query, target_dir, k, exact_hits)
                    except Exception:
                        pass
                    return exact_hits[:k]

        fetch_k = max(TOP_K_DENSE, k * 2, 12)
        sparse_top = max(TOP_K_KEYWORD, k * 2)
        compare_sections = (
            extract_comparison_sections(query)
            if is_comparison_query(query)
            else []
        )
        if len(compare_sections) >= 2:
            signals["sections"] = compare_sections
            query_type = "exact_identifier"
            expanded_queries = build_section_retrieval_queries(compare_sections, query)
        else:
            expanded_queries = _expand_queries(query, query_type, signals)

        try:
            index_size = len(getattr(vs, "docstore", None)._dict or {})  # type: ignore[attr-defined]
        except Exception:
            index_size = 0
        if index_size > RAG_LARGE_INDEX_SPARSE_CAP:
            sparse_top = min(sparse_top, max(k * 2, 16))
            expanded_queries = expanded_queries[: min(len(expanded_queries), 4)]

        candidates: Dict[Tuple[str, str, str, str], Dict[str, Any]] = {}

        # Stage A: dense retrieval (parallel across expanded queries)
        from concurrent.futures import ThreadPoolExecutor, as_completed

        def _dense_search(eq: str):
            return eq, vs.similarity_search_with_score(eq, k=fetch_k)

        with ThreadPoolExecutor(max_workers=min(6, len(expanded_queries) or 1)) as pool:
            futs = [pool.submit(_dense_search, eq) for eq in expanded_queries[:RAG_MAX_QUERY_EXPANSIONS]]
            for fut in as_completed(futs):
                try:
                    expanded, dense_hits = fut.result()
                except Exception:
                    continue
                for doc, distance in dense_hits:
                    result = _format_result(doc, distance)
                    meta = result.get("metadata", {})
                    content = result.get("content", "")
                    key = _result_key(meta, content)
                    semantic = _semantic_from_distance(float(distance))
                    node = candidates.get(key)
                    if node is None:
                        candidates[key] = {
                            "content": content,
                            "metadata": meta,
                            "dense_distance": float(distance),
                            "semantic_score": semantic,
                            "lexical_score": 0.0,
                            "metadata_score": 0.0,
                        }
                    else:
                        if float(distance) < node.get("dense_distance", 999.0):
                            node["dense_distance"] = float(distance)
                        node["semantic_score"] = max(node.get("semantic_score", 0.0), semantic)

        # Stage B: sparse retrieval (BM25-style), parallel
        sparse_scores: Dict[Tuple[str, str, str, str], float] = {}
        sparse_doc_ref: Dict[Tuple[str, str, str, str], Dict[str, Any]] = {}

        def _sparse_search(eq: str):
            return eq, _sparse_scores(vs, eq, top_n=sparse_top)

        with ThreadPoolExecutor(max_workers=min(6, len(expanded_queries) or 1)) as pool:
            futs = [pool.submit(_sparse_search, eq) for eq in expanded_queries[:RAG_MAX_QUERY_EXPANSIONS]]
            for fut in as_completed(futs):
                try:
                    expanded, sparse_hits = fut.result()
                except Exception:
                    continue
                if not sparse_hits:
                    continue
                max_sparse = max((score for _, score in sparse_hits), default=1.0) or 1.0
                for doc, raw_sparse in sparse_hits:
                    result = _format_result(doc, score=2.5)
                    key = _result_key(result.get("metadata", {}), result.get("content", ""))
                    normalized_sparse = float(raw_sparse) / max_sparse
                    sparse_scores[key] = max(sparse_scores.get(key, 0.0), normalized_sparse)
                    sparse_doc_ref[key] = result

        # Merge sparse-only docs into candidate pool
        for key, lex_score in sparse_scores.items():
            if key not in candidates:
                sparse_doc = sparse_doc_ref[key]
                candidates[key] = {
                    "content": sparse_doc.get("content", ""),
                    "metadata": sparse_doc.get("metadata", {}),
                    "dense_distance": 2.5,
                    "semantic_score": _semantic_from_distance(2.5),
                    "lexical_score": lex_score,
                    "metadata_score": 0.0,
                }
            else:
                candidates[key]["lexical_score"] = max(candidates[key].get("lexical_score", 0.0), lex_score)

        # Stage C: metadata scoring
        scope = document_scope or {}
        if scope.get("strict"):
            from backend.app.core.kb_doc_scope import chunk_matches_scope

            candidates = {
                key: node
                for key, node in candidates.items()
                if chunk_matches_scope(node.get("metadata") or {}, scope)
            }

        for node in candidates.values():
            meta = node.get("metadata", {})
            filename = str(meta.get("filename", ""))
            content = str(node.get("content", ""))
            node["metadata_score"] = _metadata_match_score(
                query=query,
                content=content,
                filename=filename,
                signals=signals,
                query_type=query_type,
            )

        # Statute queries: strict section filter before hybrid merge
        has_sections = bool(signals.get("sections") or signals.get("bare_identifiers"))
        if has_sections or query_type == "exact_identifier":
            law_hint = ""
            if re.search(r"\bipc\b", original_query, re.I):
                law_hint = "IPC"
            elif re.search(r"\bbns\b", original_query, re.I):
                law_hint = "BNS"
            candidates = strict_section_filter(candidates, signals, law=law_hint)

        # Stage D: weighted hybrid score (+ exact section priority for statutory lookups)
        if query_type == "exact_identifier" or has_sections:
            w_sem, w_lex, w_meta = 0.10, 0.40, 0.50
        elif query_type == "law_mapping":
            w_sem, w_lex, w_meta = 0.20, 0.45, 0.35
        else:
            w_sem, w_lex, w_meta = 0.70, 0.30, 0.0

        scope = document_scope or {}
        if scope.get("strict") and not doc_id and not filename:
            doc_id = scope.get("doc_id") or doc_id
            filename = scope.get("filename") or filename

        law_mapping_query = query_type == "law_mapping"
        try:
            from kb_legal_query_rewrite import is_law_mapping_chunk, is_law_replacement_query

            law_mapping_query = law_mapping_query or is_law_replacement_query(original_query)
        except Exception:
            is_law_mapping_chunk = lambda _c: False  # noqa: E731

        ranked = []
        for node in candidates.values():
            meta = node.get("metadata") or {}
            content = str(node.get("content", ""))
            if scope.get("strict"):
                from backend.app.core.kb_doc_scope import chunk_matches_scope

                if not chunk_matches_scope(meta, scope):
                    continue
            semantic = float(node.get("semantic_score", 0.0))
            lexical = float(node.get("lexical_score", 0.0))
            metadata_score = float(node.get("metadata_score", 0.0))
            content = str(node.get("content", ""))
            section_boost = _exact_section_priority_boost(content, signals, query_type)
            hybrid = (w_sem * semantic) + (w_lex * lexical) + (w_meta * metadata_score)
            if has_sections or query_type == "exact_identifier":
                hybrid += 1.15 * max(section_boost, 0.0)
                if section_boost >= 0.5:
                    hybrid += SECTION_SCORE_BOOST
                if section_boost < 0:
                    hybrid += section_boost
            if law_mapping_query:
                try:
                    if is_law_mapping_chunk(content):
                        hybrid += 0.55
                    from kb_legal_query_rewrite import chunk_matches_law_query

                    if chunk_matches_law_query(content, original_query):
                        hybrid += 0.35
                except Exception:
                    pass
            hybrid += _law_mismatch_penalty(content, original_query)
            if scope.get("strict"):
                from backend.app.core.kb_doc_scope import contamination_penalty

                hybrid += contamination_penalty(content, scope)
            from kb_preprocess import is_intro_or_generic_chunk

            if is_intro_or_generic_chunk(content) and signals.get("sections"):
                hybrid -= 0.55
            node["section_boost"] = section_boost
            node["hybrid_score"] = hybrid
            ranked.append(node)

        ranked.sort(key=lambda n: n.get("hybrid_score", 0.0), reverse=True)
        if not ranked:
            if scope.get("strict"):
                try:
                    from backend.app.core.kb_doc_scope import retrieve_scoped_docstore_chunks

                    scoped_hits = retrieve_scoped_docstore_chunks(
                        original_query,
                        target_dir,
                        scope,
                        top_k=max(k, DEFAULT_RETRIEVAL_K),
                    )
                    if scoped_hits:
                        logger.info(
                            "[KB RAG] Scoped docstore fallback returned %s chunks",
                            len(scoped_hits),
                        )
                        return scoped_hits
                except Exception:
                    pass
                _last_query_error = "No chunks matched active document scope."
                return []
            fallback = _try_keyword_fallback(
                vs,
                original_query,
                rewritten_query=rewritten_query,
                expanded_queries=expanded_queries,
                reason="empty_hybrid",
                document_scope=scope,
            )
            if fallback:
                return fallback
            _last_query_error = "Retriever returned no chunks after hybrid merge."
            logger.warning("[WARN] %s", _last_query_error)
            return []

        # Stage E: reranking (cross-encoder when available, else heuristic)
        rerank_pool = ranked[: max(RERANK_POOL_SIZE, k * 4)]
        reranker = _get_reranker()
        if reranker:
            pairs = [(query, (node.get("content", "") or "")[:1600]) for node in rerank_pool]
            try:
                raw_scores = reranker.predict(pairs)
                for node, raw in zip(rerank_pool, raw_scores):
                    # Normalize logits/real outputs to 0..1
                    rerank_score = 1.0 / (1.0 + math.exp(-float(raw)))
                    node["rerank_score"] = rerank_score
            except Exception as exc:
                logger.warning("Cross-encoder rerank failed (%s). Falling back to heuristic.", exc)
                for node in rerank_pool:
                    node["rerank_score"] = _heuristic_rerank_score(
                        query,
                        node.get("content", ""),
                        float(node.get("metadata_score", 0.0)),
                    )
        else:
            for node in rerank_pool:
                node["rerank_score"] = _heuristic_rerank_score(
                    query,
                    node.get("content", ""),
                    float(node.get("metadata_score", 0.0)),
                )

        for node in rerank_pool:
            node["final_score"] = (0.65 * float(node.get("hybrid_score", 0.0))) + (
                0.35 * float(node.get("rerank_score", 0.0))
            )

        rerank_pool.sort(key=lambda n: n.get("final_score", 0.0), reverse=True)

        final_k_target = min(max(k, 5), FINAL_TOP_K, len(rerank_pool))
        rerank_pool = _mmr_select(rerank_pool, query, max(final_k_target, k))

        if len(compare_sections) >= 2:
            rerank_pool = ensure_per_section_chunks(
                rerank_pool, compare_sections, max_total=max(FINAL_TOP_K, k, 8)
            )

        # Stage F: context validation and confidence
        from kb_rag_decision import section_match_in_chunks

        valid, validation_score, validation_note = _validate_context(
            query=query,
            query_type=query_type,
            signals=signals,
            chunks=rerank_pool[: max(3, min(k, 6))],
        )

        top_for_conf = rerank_pool[:3]
        retrieval_component = (
            sum(float(n.get("hybrid_score", 0.0)) for n in top_for_conf) / max(len(top_for_conf), 1)
        )
        rerank_component = (
            sum(float(n.get("rerank_score", 0.0)) for n in top_for_conf) / max(len(top_for_conf), 1)
        )
        confidence = (
            (0.45 * retrieval_component)
            + (0.35 * rerank_component)
            + (0.20 * float(validation_score))
        )
        confidence = max(0.0, min(1.0, confidence))

        _last_query_diagnostics = {
            "query_type": query_type,
            "kb_query_type": kb_type.value,
            "comparison_sections": compare_sections,
            "signals": signals,
            "expanded_queries": expanded_queries,
            "candidates": len(candidates),
            "validation_note": validation_note,
            "validation_score": validation_score,
            "confidence": confidence,
            "confidence_threshold": RAG_CONFIDENCE_THRESHOLD,
            "similarity_gate": SIMILARITY_GATE,
            "valid": valid,
            "retrieved_chunks": [
                {
                    "final_score": round(float(n.get("final_score", 0)), 4),
                    "rerank_score": round(float(n.get("rerank_score", 0)), 4),
                    "section_boost": round(float(n.get("section_boost", 0)), 4),
                    "file": (n.get("metadata") or {}).get("filename"),
                    "excerpt": (n.get("content") or "")[:160],
                }
                for n in rerank_pool[:8]
            ],
            "original_query": original_query,
            "rewritten_query": rewritten_query,
            "expanded_queries": expanded_queries[:8],
        }

        if not valid:
            has_section_hit = section_match_in_chunks(
                rerank_pool, signals.get("sections") or []
            )
            if scope.get("strict") and rerank_pool and has_section_hit:
                valid = True
                validation_note = "scoped_section_match"
            if not valid:
                fallback = _try_keyword_fallback(
                    vs,
                    original_query,
                    rewritten_query=rewritten_query,
                    expanded_queries=expanded_queries,
                    reason=f"validation:{validation_note}",
                    document_scope=scope,
                )
                if fallback:
                    return fallback
                _last_query_error = f"Context validation failed ({validation_note})."
                logger.warning("[WARN] %s", _last_query_error)
                return []

        conf_threshold = RAG_CONFIDENCE_THRESHOLD
        if scope.get("strict"):
            conf_threshold = min(conf_threshold, 0.28)
        if query_type in {"exact_identifier", "law_mapping"} and rerank_pool:
            top_meta = float(rerank_pool[0].get("metadata_score", 0.0))
            if top_meta >= 0.35 or query_type == "law_mapping":
                conf_threshold = min(conf_threshold, 0.22)
        elif query_type == "exact_identifier":
            conf_threshold = min(conf_threshold, 0.25)

        if confidence < conf_threshold:
            law_mapping_hit = False
            try:
                from kb_legal_query_rewrite import chunk_matches_law_query

                law_mapping_hit = any(
                    chunk_matches_law_query(c.get("content", ""), original_query)
                    for c in rerank_pool[:8]
                )
            except Exception:
                pass
            if section_match_in_chunks(rerank_pool, signals.get("sections") or []) or law_mapping_hit:
                confidence = max(confidence, conf_threshold)
                logger.info(
                    "[KB RAG] Confidence below threshold but direct match — treating as FOUND"
                )
            else:
                keep_hybrid = 0.22
                try:
                    from backend.app.core.universal_kb import is_statute_focused_query

                    if not is_statute_focused_query(original_query):
                        keep_hybrid = 0.16
                except Exception:
                    pass
                if query_type in {"topic_query", "summary", "unknown", "general"}:
                    keep_hybrid = min(keep_hybrid, 0.18)
                if rerank_pool and float(rerank_pool[0].get("hybrid_score", 0)) >= keep_hybrid:
                    logger.info(
                        "[KB RAG] Low confidence %.3f but keeping %s chunks (hybrid=%.3f)",
                        confidence,
                        len(rerank_pool),
                        float(rerank_pool[0].get("hybrid_score", 0)),
                    )
                    confidence = max(confidence, conf_threshold)
                else:
                    fallback = _try_keyword_fallback(
                        vs,
                        original_query,
                        rewritten_query=rewritten_query,
                        expanded_queries=expanded_queries,
                        reason=f"low_confidence:{confidence:.3f}",
                        document_scope=scope,
                    )
                    if fallback:
                        return fallback
                    _last_query_error = (
                        f"Low retrieval confidence ({confidence:.3f} < {conf_threshold:.3f})."
                    )
                    logger.warning("[WARN] %s", _last_query_error)
                    return []

        final_k = min(len(rerank_pool), max(k, 3), FINAL_TOP_K)
        final_results: List[Dict[str, Any]] = []
        for node in rerank_pool[:final_k]:
            dense_distance = float(node.get("dense_distance", 2.5))
            final_score = float(node.get("final_score", 0.0))
            final_results.append(
                {
                    "content": node.get("content", ""),
                    "metadata": node.get("metadata", {}),
                    # Keep compatibility with app.py relevance labeling (lower = better).
                    "score": max(0.0, 1.0 - final_score),
                    "dense_distance": dense_distance,
                    "semantic_score": float(node.get("semantic_score", 0.0)),
                    "lexical_score": float(node.get("lexical_score", 0.0)),
                    "metadata_score": float(node.get("metadata_score", 0.0)),
                    "hybrid_score": float(node.get("hybrid_score", 0.0)),
                    "rerank_score": float(node.get("rerank_score", 0.0)),
                    "final_score": final_score,
                    "confidence": confidence,
                    "query_type": query_type,
                }
            )

        for rank, item in enumerate(final_results, start=1):
            preview = (item.get("content") or "").replace("\n", " ")[:200]
            logger.debug(
                "[DEBUG] Final chunk #%s final=%.4f hybrid=%.4f rerank=%.4f: %s",
                rank,
                item.get("final_score", -1),
                item.get("hybrid_score", -1),
                item.get("rerank_score", -1),
                preview,
            )

        final_results = _filter_results_by_scope(final_results, scope)

        if len(final_results) < max(3, k // 2):
            try:
                extra = _keyword_fallback_docstore_only(
                    original_query,
                    target_dir,
                    original_query=original_query,
                    top_k=max(k, DEFAULT_RETRIEVAL_K),
                    document_scope=scope,
                )
                if extra:
                    seen = {(r.get("content") or "")[:80] for r in final_results}
                    for item in extra:
                        key = (item.get("content") or "")[:80]
                        if key and key not in seen:
                            final_results.append(item)
                            seen.add(key)
                    final_results = final_results[: max(k, FINAL_TOP_K)]
            except Exception:
                pass

        try:
            from kb_legal_query_rewrite import log_rag_debug

            log_rag_debug(
                user_query=original_query,
                rewritten_query=rewritten_query,
                expanded_queries=expanded_queries,
                top_chunks=final_results[:8],
                selected_chunk=final_results[0] if final_results else None,
            )
        except Exception:
            pass

        if not final_results:
            fallback = _keyword_fallback_docstore_only(
                original_query,
                target_dir,
                original_query=original_query,
                top_k=max(k, DEFAULT_RETRIEVAL_K),
                document_scope=scope,
            )
            if fallback:
                return fallback

        try:
            from backend.app.core.kb_cache import set_cached_chunks

            set_cached_chunks(
                query, target_dir, k, final_results, scope_key=scope_key
            )
        except Exception:
            pass

        return final_results

    except Exception as exc:
        _last_query_error = str(exc)
        logger.exception("Knowledge base query failed: %s", exc)
        if "meta tensor" in str(exc).lower():
            _reset_embeddings_singleton()
        fallback = _keyword_fallback_docstore_only(
            query,
            target_dir,
            original_query=locals().get("original_query", query),
            top_k=k if "k" in locals() else DEFAULT_RETRIEVAL_K,
            document_scope=locals().get("document_scope"),
        )
        if fallback:
            return fallback
        return []


def build_faiss_index(
    documents: List[Dict[str, str]],
    progress_callback=None,
    index_dir: Optional[Union[str, Path]] = None,
):
    """Wrapper for UI consumption."""
    ok, msg, total = index_documents(documents, progress_callback=progress_callback, index_dir=index_dir)
    return ok, msg, total


def get_relevant_context(query: str, k: int = DEFAULT_RETRIEVAL_K, index_dir: Optional[Union[str, Path]] = None) -> str:
    """Get relevant context as a formatted string for prompts."""
    chunks = query_kb(query, k=k, index_dir=index_dir)
    if not chunks:
        return NOT_FOUND_PHRASE

    context_parts = []
    for chunk in chunks:
        meta = chunk.get("metadata", {})
        filename = meta.get("filename", "unknown")
        chunk_idx = meta.get("chunk_index", 0)
        content = chunk.get("content", "")
        context_parts.append(f"[[{filename}:{chunk_idx}]]\n{content}")

    return "\n\n---\n\n".join(context_parts)


def retrieval_has_signal(chunks: List[Dict]) -> bool:
    """True when at least one retrieved chunk is plausibly relevant."""
    if not chunks:
        return False
    if any("final_score" in chunk for chunk in chunks):
        return max(float(chunk.get("final_score", 0.0)) for chunk in chunks) >= MIN_RETRIEVAL_THRESHOLD
    return min(chunk.get("score", 999.0) for chunk in chunks) <= SCORE_THRESHOLD


def diagnose_kb_health(
    index_dir: Optional[Union[str, Path]] = None,
    document_count: int = 0,
    db_chunk_count: int = 0,
    db_status: str = "unknown",
) -> Dict:
    """
    Structured health report for UI — includes file paths and fix hints.
    """
    target = _resolve_index_dir(index_dir)
    issues: List[Dict[str, str]] = []
    checks: Dict[str, bool] = {}

    # Python / deps
    try:
        import faiss  # noqa: F401
        checks["faiss_import"] = True
    except Exception as exc:
        checks["faiss_import"] = False
        issues.append({
            "severity": "error",
            "message": f"FAISS not importable: {exc}",
            "file": "requirements.txt",
            "fix": "Run: .venv_win\\Scripts\\python.exe -m pip install faiss-cpu",
        })

    try:
        _get_langchain_embeddings()
        checks["embeddings"] = True
    except Exception as exc:
        checks["embeddings"] = False
        issues.append({
            "severity": "error",
            "message": f"Embeddings failed: {exc}",
            "file": "rag.py → _get_langchain_embeddings()",
            "fix": "pip install sentence-transformers langchain-huggingface",
        })

    checks["index_on_disk"] = index_exists(target)
    if document_count > 0 and not checks["index_on_disk"]:
        issues.append({
            "severity": "error",
            "message": f"{document_count} PDF(s) in DB but no FAISS index on disk.",
            "file": "app.py → build_faiss_index() / Documents → Index All Documents",
            "fix": f"Rebuild index at: {target}",
        })

    if document_count == 0:
        issues.append({
            "severity": "warning",
            "message": "No documents uploaded.",
            "file": "app.py → render_documents()",
            "fix": "Upload PDFs under Documents, then click Index All Documents.",
        })

    if db_status == "stale":
        issues.append({
            "severity": "warning",
            "message": "Knowledge base status is stale (documents changed after last index).",
            "file": "app.py → knowledge_base_status table",
            "fix": "Click 'Index All Documents' on the Documents page.",
        })

    if db_chunk_count == 0 and document_count > 0 and checks.get("index_on_disk"):
        issues.append({
            "severity": "warning",
            "message": "Index exists but DB reports 0 chunks — re-index recommended.",
            "file": "app.py → get_knowledge_base_status()",
            "fix": "Re-run build_faiss_index(user_id).",
        })

    err = get_last_query_error()
    if err:
        issues.append({
            "severity": "error",
            "message": err,
            "file": "rag.py → query_kb()",
            "fix": "See message above; ensure index files exist and embeddings load.",
        })

    healthy = not any(i["severity"] == "error" for i in issues)
    return {
        "healthy": healthy,
        "index_path": str(target),
        "index_exists": checks.get("index_on_disk", False),
        "document_count": document_count,
        "db_chunk_count": db_chunk_count,
        "db_status": db_status,
        "checks": checks,
        "issues": issues,
        "chunk_size": CHUNK_SIZE,
        "score_threshold": SCORE_THRESHOLD,
        "confidence_threshold": RAG_CONFIDENCE_THRESHOLD,
        "cross_encoder_enabled": RAG_ENABLE_CROSS_ENCODER,
        "rerank_model": RAG_RERANK_MODEL,
    }
