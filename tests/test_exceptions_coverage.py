"""
Comprehensive tests for exception taxonomy (exceptions.py).

Covers:
- Exception hierarchy and inheritance
- retryable attribute correctness
- is_retryable() handling of all exception types (custom + third-party)
- classify_error() categorization
- Edge cases: None inputs, invalid status codes, empty messages
"""

from __future__ import annotations

import pytest
from reasoner.exceptions import (
    ReasonerError,
    ParseError,
    JSONExtractionError,
    JSONValidationError,
    ProviderError,
    AuthenticationError,
    RateLimitError,
    ModelNotFoundError,
    ProviderTimeoutError,
    ProviderUnavailableError,
    PipelineError,
    PhaseError,
    ConfigurationError,
    is_retryable,
    classify_error,
)


class TestExceptionHierarchy:

    def test_reasoner_error_is_base(self):
        assert issubclass(ReasonerError, Exception)

    def test_parse_error_is_reasoner_error(self):
        assert issubclass(ParseError, ReasonerError)

    def test_json_extraction_is_parse(self):
        assert issubclass(JSONExtractionError, ParseError)

    def test_provider_error_is_reasoner_error(self):
        assert issubclass(ProviderError, ReasonerError)

    def test_authentication_error_is_provider(self):
        assert issubclass(AuthenticationError, ProviderError)

    def test_rate_limit_error_is_provider(self):
        assert issubclass(RateLimitError, ProviderError)

    def test_phase_error_is_pipeline(self):
        assert issubclass(PhaseError, PipelineError)

    def test_configuration_error_is_reasoner(self):
        assert issubclass(ConfigurationError, ReasonerError)


class TestRetryableAttribute:

    def test_authentication_not_retryable(self):
        assert AuthenticationError.retryable is False

    def test_rate_limit_is_retryable(self):
        assert RateLimitError.retryable is True

    def test_provider_timeout_is_retryable(self):
        assert ProviderTimeoutError.retryable is True

    def test_provider_unavailable_is_retryable(self):
        assert ProviderUnavailableError.retryable is True

    def test_model_not_found_not_retryable(self):
        assert ModelNotFoundError.retryable is False

    def test_parse_error_not_retryable(self):
        assert ParseError.retryable is False

    def test_pipeline_error_not_retryable(self):
        assert PipelineError.retryable is False


class TestExceptionConstructors:

    def test_reasoner_error_default_details(self):
        e = ReasonerError("test")
        assert e.details == {}

    def test_reasoner_error_with_details(self):
        e = ReasonerError("test", {"key": "value"})
        assert e.details == {"key": "value"}

    def test_authentication_error_stores_provider(self):
        e = AuthenticationError("bad key", provider="openai")
        assert e.details["provider"] == "openai"

    def test_rate_limit_error_stores_retry_after(self):
        e = RateLimitError("too fast", provider="openai", retry_after=30)
        assert e.details["retry_after"] == 30

    def test_model_not_found_stores_model(self):
        e = ModelNotFoundError("bad model", model="gpt-99")
        assert e.details["model"] == "gpt-99"

    def test_phase_error_stores_phase_info(self):
        e = PhaseError("failed", phase=3, phase_name="Critique")
        assert e.phase == 3
        assert e.phase_name == "Critique"
        assert e.details["phase"] == 3


class TestIsRetryable:
    """Verify is_retryable() handles all exception types."""

    def test_known_retryable(self):
        assert is_retryable(RateLimitError("limit"))
        assert is_retryable(ProviderTimeoutError("timeout"))
        assert is_retryable(ProviderUnavailableError("down"))

    def test_known_not_retryable(self):
        assert not is_retryable(AuthenticationError("bad"))
        assert not is_retryable(ModelNotFoundError("missing"))
        assert not is_retryable(ParseError("bad json"))
        assert not is_retryable(ConfigurationError("bad config"))

    def test_unknown_exception_not_retryable(self):
        assert not is_retryable(ValueError("generic"))
        assert not is_retryable(RuntimeError("generic"))
        assert not is_retryable(Exception("generic"))

    def test_http_status_429_retryable(self):
        e = Exception("too many requests")
        e.status_code = 429  # type: ignore
        assert is_retryable(e)

    def test_http_status_500_retryable(self):
        e = Exception("server error")
        e.status_code = 500  # type: ignore
        assert is_retryable(e)

    def test_http_status_502_retryable(self):
        e = Exception("bad gateway")
        e.status_code = 502  # type: ignore
        assert is_retryable(e)

    def test_http_status_503_retryable(self):
        e = Exception("unavailable")
        e.status_code = 503  # type: ignore
        assert is_retryable(e)

    def test_http_status_504_retryable(self):
        e = Exception("gateway timeout")
        e.status_code = 504  # type: ignore
        assert is_retryable(e)

    def test_http_status_401_not_retryable(self):
        e = Exception("unauthorized")
        e.status_code = 401  # type: ignore
        assert not is_retryable(e)

    def test_http_status_403_not_retryable(self):
        e = Exception("forbidden")
        e.status_code = 403  # type: ignore
        assert not is_retryable(e)

    def test_http_status_404_not_retryable(self):
        e = Exception("not found")
        e.status_code = 404  # type: ignore
        assert not is_retryable(e)

    def test_fetch_failed_message_retryable(self):
        e = Exception("fetch failed: connection reset")
        assert is_retryable(e)

    def test_network_error_case_insensitive(self):
        e = Exception("FETCH FAILED due to network issue")
        assert is_retryable(e)

    def test_non_integer_status_code_not_retryable(self):
        e = Exception("weird")
        e.status_code = "429"  # type: ignore — string, not int
        assert not is_retryable(e)

    def test_no_status_code_not_retryable(self):
        e = Exception("plain error")
        assert not is_retryable(e)


class TestClassifyError:
    """Verify classify_error() categorizes all exception types."""

    def test_auth_errors(self):
        assert classify_error(AuthenticationError("bad")) == "auth"

    def test_rate_limit_errors(self):
        assert classify_error(RateLimitError("fast")) == "rate_limit"

    def test_model_not_found(self):
        assert classify_error(ModelNotFoundError("missing")) == "model_not_found"

    def test_timeout_errors(self):
        assert classify_error(ProviderTimeoutError("slow")) == "timeout"

    def test_unavailable_errors(self):
        assert classify_error(ProviderUnavailableError("down")) == "unavailable"

    def test_parse_errors(self):
        assert classify_error(ParseError("bad json")) == "parse"
        assert classify_error(JSONExtractionError("extract fail")) == "parse"
        assert classify_error(JSONValidationError("schema")) == "parse"

    def test_pipeline_errors(self):
        assert classify_error(PipelineError("fail")) == "pipeline"
        assert classify_error(PhaseError("fail", 1, "test")) == "pipeline"

    def test_third_party_exception_names(self):
        # classify_error recognizes common third-party exception type names
        e = type("RateLimitError", (Exception,), {})()
        assert classify_error(e) == "rate_limit"

    def test_third_party_auth_errors(self):
        e = type("AuthenticationError", (Exception,), {})()
        assert classify_error(e) == "auth"

    def test_third_party_timeout(self):
        e = type("APITimeoutError", (Exception,), {})()
        assert classify_error(e) == "timeout"

    def test_unknown_error(self):
        assert classify_error(ValueError("generic")) == "unknown"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
