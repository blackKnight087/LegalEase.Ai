from prompts import kb_prompt, web_prompt, NOT_FOUND_PHRASE


def test_kb_prompt_contains_citation_format():
    ctx = [{"content": "Example", "metadata": {"filename": "doc.pdf", "chunk_index": "1"}}]
    prompt = kb_prompt(ctx, "What is this?")
    assert "[[doc.pdf:1]]" in prompt
    assert NOT_FOUND_PHRASE in prompt


def test_web_prompt_includes_urls():
    snippets = [{"title": "Case", "href": "http://example.com", "body": "snippet", "date": "2024-01-01"}]
    prompt = web_prompt(snippets, "question")
    assert "example.com" in prompt
