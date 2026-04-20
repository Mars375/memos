"""Structural regression tests for the FeedbackFacade mixin extraction.

Verifies that FeedbackFacade methods exist on MemOS via inheritance, have
correct signatures, are defined on the facade, and that the mixin is a pure mixin.
"""

import inspect

from memos._feedback_facade import FeedbackFacade
from memos.core import MemOS

FEEDBACK_METHODS = ("record_feedback", "get_feedback", "feedback_stats")


class TestFeedbackFacadeInheritance:
    def test_memos_inherits_feedback_facade(self):
        assert issubclass(MemOS, FeedbackFacade)

    def test_feedback_facade_is_mixin(self):
        assert "__init__" not in FeedbackFacade.__dict__, "FeedbackFacade should not define __init__"

    def test_memos_instance_has_all_feedback_methods(self):
        mem = MemOS(backend="memory", sanitize=False)
        for name in FEEDBACK_METHODS:
            assert hasattr(mem, name), f"MemOS instance missing method: {name}"
            assert callable(getattr(mem, name)), f"MemOS.{name} is not callable"


class TestMethodSignatures:
    def test_record_feedback_signature(self):
        sig = inspect.signature(MemOS.record_feedback)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "item_id" in params
        assert "feedback" in params
        assert "query" in params
        assert "score_at_recall" in params
        assert "agent_id" in params

    def test_get_feedback_signature(self):
        sig = inspect.signature(MemOS.get_feedback)
        params = list(sig.parameters.keys())
        assert "self" in params
        assert "item_id" in params
        assert "limit" in params
        assert sig.parameters["limit"].default == 100

    def test_feedback_stats_signature(self):
        sig = inspect.signature(MemOS.feedback_stats)
        params = list(sig.parameters.keys())
        assert "self" in params


class TestNoDuplicationInCore:
    def test_methods_defined_on_facade(self):
        for name in FEEDBACK_METHODS:
            assert name in FeedbackFacade.__dict__, f"{name} should be defined on FeedbackFacade, not just inherited"


class TestFeedbackFacadeDelegation:
    def test_record_feedback_validates_input(self):
        import pytest

        mem = MemOS(backend="memory", sanitize=False)
        with pytest.raises(ValueError, match="Invalid feedback"):
            mem.record_feedback("any-id", "invalid-value")

    def test_record_feedback_relevant_returns_entry(self):
        mem = MemOS(backend="memory", sanitize=False)
        item = mem.learn("feedback test", tags=["test"])
        entry = mem.record_feedback(item.id, "relevant", query="q")
        assert entry.feedback == "relevant"
        assert entry.item_id == item.id

    def test_get_feedback_returns_list(self):
        mem = MemOS(backend="memory", sanitize=False)
        result = mem.get_feedback()
        assert isinstance(result, list)

    def test_feedback_stats_returns_object(self):
        mem = MemOS(backend="memory", sanitize=False)
        stats = mem.feedback_stats()
        assert hasattr(stats, "total_feedback")
        assert hasattr(stats, "relevant_count")
        assert stats.total_feedback == 0
