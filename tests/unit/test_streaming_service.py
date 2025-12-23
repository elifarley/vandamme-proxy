import pytest


@pytest.mark.unit
@pytest.mark.asyncio
async def test_with_streaming_metrics_finalizer_calls_end(monkeypatch):
    from src.api.services.streaming import with_streaming_metrics_finalizer

    ended = []

    class FakeTracker:
        async def end_request(self, request_id: str) -> None:
            ended.append(request_id)

    def fake_get_request_tracker(_http_request):
        return FakeTracker()

    import src.api.services.streaming as streaming

    monkeypatch.setattr(streaming, "get_request_tracker", fake_get_request_tracker)

    class FakeRequest:
        pass

    async def gen():
        yield "a"
        yield "b"

    out = []
    async for x in with_streaming_metrics_finalizer(
        original_stream=gen(),
        http_request=FakeRequest(),
        request_id="req-1",
        enabled=True,
    ):
        out.append(x)

    assert out == ["a", "b"]
    assert ended == ["req-1"]


@pytest.mark.unit
@pytest.mark.asyncio
async def test_with_streaming_metrics_finalizer_skips_when_disabled(monkeypatch):
    from src.api.services.streaming import with_streaming_metrics_finalizer

    ended = []

    class FakeTracker:
        async def end_request(self, request_id: str) -> None:
            ended.append(request_id)

    def fake_get_request_tracker(_http_request):
        return FakeTracker()

    import src.api.services.streaming as streaming

    monkeypatch.setattr(streaming, "get_request_tracker", fake_get_request_tracker)

    class FakeRequest:
        pass

    async def gen():
        yield "x"

    out = []
    async for x in with_streaming_metrics_finalizer(
        original_stream=gen(),
        http_request=FakeRequest(),
        request_id="req-2",
        enabled=False,
    ):
        out.append(x)

    assert out == ["x"]
    assert ended == []
