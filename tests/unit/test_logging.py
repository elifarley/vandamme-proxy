import logging
from io import StringIO

import pytest

from src.core.logging.configuration import (
    NOISY_HTTP_LOGGERS,
    configure_root_logging,
    set_noisy_http_logger_levels,
)
from src.core.config import config
from src.core.logging.filters.http import HttpRequestLogDowngradeFilter
from src.core.logging.formatters.correlation import CorrelationFormatter


@pytest.mark.unit
class TestHttpRequestLogDowngradeFilter:
    def setup_method(self) -> None:
        self.stream = StringIO()
        self.handler = logging.StreamHandler(self.stream)
        self.handler.setFormatter(logging.Formatter("%(levelname)s:%(message)s"))
        self.handler.addFilter(HttpRequestLogDowngradeFilter(*NOISY_HTTP_LOGGERS))

    def _emit(self, logger_name: str, level: int, message: str) -> str:
        logger = logging.getLogger(logger_name)
        logger.handlers = [self.handler]
        logger.setLevel(logging.DEBUG)
        logger.propagate = False
        logger.log(level, message)
        self.handler.flush()
        output = self.stream.getvalue()
        self.stream.truncate(0)
        self.stream.seek(0)
        return output

    def test_downgrades_noisy_http_info_logs(self):
        output = self._emit("openai.client", logging.INFO, "HTTP Request: POST")
        assert output.startswith("DEBUG:HTTP Request: POST")

    def test_preserves_non_noisy_info_logs(self):
        output = self._emit("conversation", logging.INFO, "Important info message")
        assert output.startswith("INFO:Important info message")


@pytest.mark.unit
class TestNoisyHttpLoggerLevelSetter:
    def test_sets_warning_by_default(self):
        set_noisy_http_logger_levels("INFO")
        for name in NOISY_HTTP_LOGGERS:
            assert logging.getLogger(name).level == logging.WARNING

    def test_stays_debug_when_global_debug(self):
        set_noisy_http_logger_levels("DEBUG")
        for name in NOISY_HTTP_LOGGERS:
            assert logging.getLogger(name).level == logging.DEBUG


@pytest.mark.unit
class TestCorrelationFormatter:
    def test_adds_correlation_id(self):
        formatter = CorrelationFormatter("%(message)s")
        record = logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname=__file__,
            lineno=10,
            msg="hello",
            args=(),
            exc_info=None,
        )
        record.correlation_id = "1234567890"

        formatted = formatter.format(record)
        assert formatted.startswith("[12345678] hello")


@pytest.mark.unit
class TestConfigureRootLogging:
    def test_emits_debug_startup_line_when_log_level_debug(self, monkeypatch, caplog):
        monkeypatch.setattr(config, "log_level", "DEBUG")
        caplog.set_level(logging.DEBUG)

        configure_root_logging(use_systemd=False)

        assert "LOG_LEVEL=DEBUG: noisy HTTP log suppression disabled" in caplog.text

    def test_does_not_emit_debug_startup_line_when_log_level_info(self, monkeypatch, caplog):
        monkeypatch.setattr(config, "log_level", "INFO")
        caplog.set_level(logging.DEBUG)

        configure_root_logging(use_systemd=False)

        assert "LOG_LEVEL=DEBUG: noisy HTTP log suppression disabled" not in caplog.text

    def teardown_method(self):
        # Avoid cross-test leakage since configure_root_logging mutates global logging.
        logging.getLogger().handlers.clear()
        for logger_name in ("uvicorn", "uvicorn.access", "uvicorn.error", "uvicorn.server"):
            logging.getLogger(logger_name).handlers.clear()
        for name in NOISY_HTTP_LOGGERS:
            logging.getLogger(name).setLevel(logging.NOTSET)
        logging.getLogger("src.core.logging.configuration").handlers.clear()
        logging.getLogger("src.core.logging.configuration").setLevel(logging.NOTSET)
        logging.getLogger("src.core.logging.configuration").propagate = True

        config.log_level = "INFO"
