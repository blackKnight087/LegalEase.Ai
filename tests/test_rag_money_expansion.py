"""RAG must not treat currency amounts as IPC section numbers."""
from __future__ import annotations

from rag import _detect_query_type, _expand_queries, _extract_query_signals


def test_five_lakhs_not_ipc_section_five():
    q = (
        "My company hired a vendor who took our down payment of 5 lakhs in Kolkata "
        "and stopped answering. Possible cheating under IPC."
    )
    signals = _extract_query_signals(q)
    assert "5" not in signals["bare_identifiers"]
    assert _detect_query_type(q) != "exact_identifier"
    expanded = _expand_queries(q, _detect_query_type(q), signals)
    assert "IPC 5" not in expanded
    assert "Section 5" not in expanded


def test_ipc_420_still_expands():
    q = "Explain IPC 420 cheating"
    signals = _extract_query_signals(q)
    assert "420" in signals["bare_identifiers"] or "420" in "".join(signals["sections"])
    assert _detect_query_type(q) == "exact_identifier"
