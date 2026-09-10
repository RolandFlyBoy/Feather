"""Type annotations on the public API most likely to be called wrong (0.9.8).

py.typed already ships, so these annotations are what an editor or an
assistant sees. The tests assert the annotations resolve and say the right
thing; they are not a mypy gate.
"""

import inspect
import typing

import pytest

pytestmark = pytest.mark.unit


def hints(obj):
    return typing.get_type_hints(obj)


class TestPaginate:
    def test_paginate_is_generic_over_the_model(self):
        from feather.db.pagination import paginate

        signature = inspect.signature(paginate)
        # The module uses `from __future__ import annotations`, so these are
        # the source strings.
        assert str(signature.parameters["page"].annotation) == "int"
        assert str(signature.parameters["per_page"].annotation) == "int"
        assert str(signature.parameters["max_per_page"].annotation) == "int"
        # Return type mentions PaginatedResult parameterised by the item type
        assert "PaginatedResult[T]" in str(signature.return_annotation)

    def test_paginated_result_items_are_typed(self):
        from feather.db.pagination import PaginatedResult

        annotations = PaginatedResult.__annotations__
        assert "List[T]" in str(annotations["items"]) or "list[T]" in str(annotations["items"])

    def test_to_dict_returns_a_typed_mapping(self):
        from feather.db.pagination import PaginatedResult

        assert "dict[str," in str(inspect.signature(PaginatedResult.to_dict).return_annotation)


class TestModelToDict:
    def test_to_dict_is_annotated(self):
        from feather.db.base import Model

        annotation = str(inspect.signature(Model.to_dict).return_annotation)
        assert annotation.startswith("dict[str,")
        assert "Any" in annotation


class TestJobResultGeneric:
    def test_job_result_is_generic(self):
        from feather.jobs.base import JobResult

        assert hasattr(JobResult, "__class_getitem__")
        parameterised = JobResult[int]
        assert parameterised is not None

    def test_result_field_uses_the_type_variable(self):
        from feather.jobs.base import JobResult

        assert "T" in str(JobResult.__annotations__["result"])

    def test_plain_job_result_still_constructs(self):
        from feather.jobs.base import JobResult, JobStatus

        result = JobResult(job_id="x", status=JobStatus.QUEUED)
        assert result.job_id == "x"
        assert result.result is None

    def test_is_finished_and_is_successful_annotated(self):
        from feather.jobs.base import JobResult

        assert inspect.signature(JobResult.is_finished).return_annotation is bool
        assert inspect.signature(JobResult.is_successful).return_annotation is bool


class TestInject:
    def test_inject_signature_is_annotated(self):
        from feather.core.decorators import inject

        signature = inspect.signature(inject)
        assert "type" in str(signature.parameters["service_classes"].annotation).lower()
        assert "Callable" in str(signature.return_annotation)


class TestAbstractBackends:
    def test_cache_backend_methods_annotated(self):
        from feather.cache.base import CacheBackend

        assert inspect.signature(CacheBackend.get).return_annotation is not inspect.Signature.empty
        assert inspect.signature(CacheBackend.set).parameters["ttl"].annotation is not inspect.Signature.empty
        for name in ("get", "set", "delete", "clear", "exists", "get_many", "set_many",
                     "delete_many", "increment", "decrement"):
            method = getattr(CacheBackend, name)
            assert method.__annotations__.get("return") is not None, name

    def test_storage_backend_methods_annotated(self):
        from feather.storage.base import StorageBackend

        for name in ("upload", "download", "delete", "get_url", "exists", "get_content_type"):
            method = getattr(StorageBackend, name)
            assert method.__annotations__.get("return") is not None, name

    def test_job_queue_methods_annotated(self):
        from feather.jobs.base import JobQueue

        for name in ("enqueue", "get_job", "cancel_job", "enqueue_at", "enqueue_in",
                     "get_queue_length", "get_failed_jobs", "retry_job", "clear_queue"):
            method = getattr(JobQueue, name)
            assert method.__annotations__.get("return") is not None, name

    def test_annotations_resolve_at_runtime(self):
        from feather.cache.base import CacheBackend
        from feather.jobs.base import JobQueue
        from feather.storage.base import StorageBackend

        for cls in (CacheBackend, StorageBackend, JobQueue):
            for name, member in vars(cls).items():
                if inspect.isfunction(member):
                    hints(member)  # raises if an annotation is unresolvable
