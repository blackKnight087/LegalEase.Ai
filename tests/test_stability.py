from backend.app.core.stability import operation_profile


def test_operation_profile_shape():
    p = operation_profile()
    assert "mode" in p
    assert "message" in p
    assert "api_ok" in p
