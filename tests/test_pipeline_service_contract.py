"""Contract tests for PipelineService.create_pipeline().

Regression guard for the runtime failure:

    TypeError: PipelineService.create_pipeline() got an unexpected keyword
    argument 'user_id'

The API layer (``api/execution/pipeline.py``) builds the pipeline with a fixed
set of keyword arguments. When a new one is added at the call site but not to
the service signature — or vice versa — the failure only shows up at request
time. These tests pin the contract so the drift is caught in CI instead.
"""

import inspect

import pytest

# Every kwarg the API execution layer passes to create_pipeline().
# Keep in sync with src/reasoner/api/execution/pipeline.py.
API_CALL_SITE_KWARGS = {
    "router",
    "preset_name",
    "top_k",
    "parallel_perspectives",
    "source_type",
    "domain",
    "enhance_prompt",
    "complexity",
    "batch_critique_jury",
    "initial_state",
    "user_id",
}


class TestCreatePipelineSignature:
    """The service must accept everything its callers pass."""

    def test_accepts_all_api_call_site_kwargs(self):
        from reasoner.application.services.pipeline_service import PipelineService

        params = inspect.signature(PipelineService.create_pipeline).parameters
        accepts_var_kwargs = any(
            p.kind is inspect.Parameter.VAR_KEYWORD for p in params.values()
        )
        missing = API_CALL_SITE_KWARGS - set(params)

        assert accepts_var_kwargs or not missing, (
            f"create_pipeline() is missing kwargs used by the API layer: {sorted(missing)}"
        )

    def test_router_is_the_only_required_argument(self):
        """Every other kwarg must default, so callers can omit them."""
        from reasoner.application.services.pipeline_service import PipelineService

        params = inspect.signature(PipelineService.create_pipeline).parameters
        required = [
            name
            for name, p in params.items()
            if name != "self"
            and p.default is inspect.Parameter.empty
            and p.kind not in (inspect.Parameter.VAR_KEYWORD, inspect.Parameter.VAR_POSITIONAL)
        ]
        assert required == ["router"], f"unexpected required params: {required}"


class TestCreatePipelineForwarding:
    """Constructed pipelines must carry the caller's arguments."""

    def test_forwards_user_id_to_pipeline(self):
        from reasoner.application.services.pipeline_service import PipelineService

        pipeline = PipelineService().create_pipeline(
            router=None,
            preset_name="debate-budget",
            user_id="user-123",
        )
        assert pipeline.user_id == "user-123"

    def test_user_id_defaults_to_none(self):
        from reasoner.application.services.pipeline_service import PipelineService

        pipeline = PipelineService().create_pipeline(router=None, preset_name="debate-budget")
        assert pipeline.user_id is None

    @pytest.mark.parametrize(
        "kwarg,value,attr",
        [
            ("top_k", 4, "top_k"),
            ("parallel_perspectives", False, "parallel"),
            ("preset_name", "jury-premium", "preset_name"),
        ],
    )
    def test_forwards_common_kwargs(self, kwarg, value, attr):
        from reasoner.application.services.pipeline_service import PipelineService

        pipeline = PipelineService().create_pipeline(router=None, **{kwarg: value})
        assert getattr(pipeline, attr) == value
