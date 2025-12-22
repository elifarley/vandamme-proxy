import pytest

from src.conversion.errors import SSEParseError


@pytest.mark.unit
def test_sse_parse_error_has_stable_type_and_message() -> None:
    err = SSEParseError("bad json", context={"chunk_data": "x"})
    assert err.error_type == "sse_parse_error"
    assert err.message == "bad json"
    assert err.context == {"chunk_data": "x"}
