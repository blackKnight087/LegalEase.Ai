from legal_tools import map_law_references, extract_timeline


def test_mapping_engine():
    text = "As per Section 420 of IPC, cheating applies."
    mappings = map_law_references(text)
    assert any(m["ipc_section"] == "Section 420" for m in mappings)


def test_timeline_extraction_orders_dates():
    text = "The incident happened on 01/01/2020 and arrest on 05/02/2020."
    events = extract_timeline(text, "doc.pdf")
    assert events[0]["date"] <= events[-1]["date"]

