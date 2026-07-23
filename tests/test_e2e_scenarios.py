"""Unit tests for the end-to-end scenario loader and JSON parsing.

These tests cover the ``Scenario`` dataclass, scenario file loading, and
serialization helpers used by ``scripts/test_mcp_scenarios.py`` and
``scripts/e2e_lib.py``. They do not start any merchant or MCP server.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import asdict
from pathlib import Path

import pytest

try:
    from builtins import ExceptionGroup
except ImportError:  # pragma: no cover - Python < 3.11
    ExceptionGroup = None  # type: ignore[misc,assignment]

from e2e_lib import MERCHANT_DATA_DIR, E2EError, Scenario
from test_mcp_scenarios import (
    BUILT_IN_SCENARIOS,
    _extract_e2e_error,
    _select_scenarios,
    load_scenarios_from_file,
    write_sample_scenarios_file,
)

_REQUIRES_EXCEPTION_GROUP = pytest.mark.skipif(
    ExceptionGroup is None,
    reason="ExceptionGroup requires Python 3.11+",
)


class TestExtractE2EError:
    """Tests for ``_extract_e2e_error`` ExceptionGroup unwrapping."""

    def test_returns_error_directly(self) -> None:
        exc = E2EError("boom")
        assert _extract_e2e_error(exc) is exc

    def test_returns_none_for_unrelated_exception(self) -> None:
        exc = ValueError("not an e2e error")
        assert _extract_e2e_error(exc) is None

    @_REQUIRES_EXCEPTION_GROUP
    def test_extracts_from_exception_group(self) -> None:
        exc = E2EError("boom")
        group = ExceptionGroup("group", [exc])
        assert _extract_e2e_error(group) is exc

    @_REQUIRES_EXCEPTION_GROUP
    def test_extracts_from_nested_exception_group(self) -> None:
        exc = E2EError("boom")
        inner = ExceptionGroup("inner", [exc])
        outer = ExceptionGroup("outer", [inner])
        assert _extract_e2e_error(outer) is exc

    @_REQUIRES_EXCEPTION_GROUP
    def test_returns_none_if_no_e2e_error_in_group(self) -> None:
        group = ExceptionGroup("group", [ValueError("nope")])
        assert _extract_e2e_error(group) is None

    @_REQUIRES_EXCEPTION_GROUP
    def test_extracts_first_e2e_error_from_mixed_group(self) -> None:
        first = E2EError("first")
        second = E2EError("second")
        group = ExceptionGroup("mixed", [ValueError("nope"), first, second])
        assert _extract_e2e_error(group) is first


class TestScenarioModel:
    """Tests for the ``Scenario`` dataclass helpers."""

    def test_to_dict_roundtrip(self) -> None:
        scenario = Scenario(
            name="roundtrip",
            items=[{"id": "x", "quantity": 2}],
            merchant_url="http://localhost:9000",
            discount_codes=["COUPON"],
            should_fail=True,
            expected_error_substring="boom",
        )
        data = scenario.to_dict()
        assert data == {
            "name": "roundtrip",
            "items": [{"id": "x", "quantity": 2}],
            "merchant_url": "http://localhost:9000",
            "merchant_data_dir": None,
            "merchant_id": None,
            "discount_codes": ["COUPON"],
            "buyer_name": "Functional Test",
            "buyer_email": "func@test.example",
            "should_fail": True,
            "expected_error_substring": "boom",
        }
        restored = Scenario(**data)
        assert restored == scenario

    def test_full_file_roundtrip_with_custom_data_dir(self, tmp_path: Path) -> None:
        """Scenario -> to_dict -> JSON -> loader must reconstruct the scenario."""
        custom_dir = tmp_path / "my_catalog"
        custom_dir.mkdir()
        original = Scenario(
            name="full_roundtrip",
            items=[{"id": "a", "quantity": 1}],
            merchant_url=None,
            merchant_data_dir=custom_dir,
            merchant_id="merchant_x",
            discount_codes=["10OFF"],
            should_fail=True,
            expected_error_substring="out of stock",
        )
        file_path = tmp_path / "scenarios.json"
        file_path.write_text(json.dumps([original.to_dict()]))
        loaded = load_scenarios_from_file(file_path)
        assert len(loaded) == 1
        assert loaded[0] == original

    def test_effective_data_dir_defaults_to_merchant_data_dir(self) -> None:
        scenario = Scenario(name="default", items=[])
        assert scenario.effective_data_dir() == MERCHANT_DATA_DIR

    def test_effective_data_dir_uses_custom_dir(self, tmp_path: Path) -> None:
        custom_dir = tmp_path / "custom_catalog"
        scenario = Scenario(name="custom", items=[], merchant_data_dir=custom_dir)
        assert scenario.effective_data_dir() == custom_dir

    def test_merchant_group_key_uses_data_dir_and_id(self, tmp_path: Path) -> None:
        custom_dir = tmp_path / "custom_catalog"
        scenario = Scenario(
            name="grouped", items=[], merchant_data_dir=custom_dir, merchant_id="m1"
        )
        assert scenario.merchant_group_key() == (custom_dir, "m1")

    def test_merchant_group_key_without_id(self) -> None:
        scenario = Scenario(name="default_group", items=[])
        assert scenario.merchant_group_key() == (MERCHANT_DATA_DIR, None)


class TestScenarioFileLoading:
    """Tests for ``load_scenarios_from_file`` and ``write_sample_scenarios_file``."""

    def test_load_valid_scenarios(self, tmp_path: Path) -> None:
        file_path = tmp_path / "scenarios.json"
        file_path.write_text(
            json.dumps(
                [
                    {
                        "name": "s1",
                        "items": [{"id": "a", "quantity": 1}],
                        "merchant_url": "http://localhost:1111",
                    },
                    {
                        "name": "s2",
                        "items": [{"id": "b", "quantity": 2}],
                        "merchant_url": None,
                        "merchant_id": "merchant_b",
                        "should_fail": True,
                    },
                ]
            )
        )
        scenarios = load_scenarios_from_file(file_path)
        assert len(scenarios) == 2
        assert scenarios[0].name == "s1"
        assert scenarios[0].merchant_url == "http://localhost:1111"
        assert scenarios[1].merchant_url is None
        assert scenarios[1].merchant_id == "merchant_b"
        assert scenarios[1].should_fail is True

    def test_load_scenarios_with_data_dir(self, tmp_path: Path) -> None:
        file_path = tmp_path / "scenarios.json"
        custom_dir = tmp_path / "catalog"
        file_path.write_text(
            json.dumps(
                [
                    {
                        "name": "s3",
                        "items": [{"id": "c", "quantity": 3}],
                        "merchant_data_dir": str(custom_dir),
                        "merchant_id": "merchant_c",
                    }
                ]
            )
        )
        scenarios = load_scenarios_from_file(file_path)
        assert len(scenarios) == 1
        assert scenarios[0].merchant_data_dir == custom_dir
        assert scenarios[0].effective_data_dir() == custom_dir

    def test_load_defaults_populated_correctly(self, tmp_path: Path) -> None:
        file_path = tmp_path / "defaults.json"
        file_path.write_text(
            json.dumps([{"name": "minimal", "items": [{"id": "x", "quantity": 1}]}])
        )
        scenarios = load_scenarios_from_file(file_path)
        assert len(scenarios) == 1
        scenario = scenarios[0]
        assert scenario.merchant_url is None
        assert scenario.merchant_data_dir is None
        assert scenario.merchant_id is None
        assert scenario.discount_codes == []
        assert scenario.should_fail is False
        assert scenario.expected_error_substring == ""
        assert scenario.buyer_name == "Functional Test"

    def test_load_non_list_json_raises(self, tmp_path: Path) -> None:
        file_path = tmp_path / "bad.json"
        file_path.write_text(json.dumps({"name": "not_a_list"}))
        with pytest.raises(E2EError, match="must contain a JSON list"):
            load_scenarios_from_file(file_path)

    def test_load_malformed_json_raises(self, tmp_path: Path) -> None:
        file_path = tmp_path / "broken.json"
        file_path.write_text('{"name": "unclosed')
        with pytest.raises(json.JSONDecodeError):
            load_scenarios_from_file(file_path)

    def test_write_sample_scenarios_file_roundtrip(self, tmp_path: Path) -> None:
        file_path = tmp_path / "sample.json"
        write_sample_scenarios_file(file_path)
        loaded = load_scenarios_from_file(file_path)
        assert len(loaded) == len(BUILT_IN_SCENARIOS)
        for original, restored in zip(BUILT_IN_SCENARIOS, loaded):
            assert asdict(restored) == asdict(original)


class TestScenarioSelection:
    """Tests for the CLI scenario selection helper."""

    def test_select_all_builtin_by_default(self) -> None:
        args = argparse.Namespace(scenarios_file=None, scenario=None)
        selected = _select_scenarios(args)
        assert selected == BUILT_IN_SCENARIOS

    def test_select_builtin_by_name(self) -> None:
        args = argparse.Namespace(scenarios_file=None, scenario="single_roses")
        selected = _select_scenarios(args)
        assert len(selected) == 1
        assert selected[0].name == "single_roses"

    def test_select_unknown_builtin_raises(self) -> None:
        args = argparse.Namespace(scenarios_file=None, scenario="does_not_exist")
        with pytest.raises(E2EError, match="Unknown scenario"):
            _select_scenarios(args)

    def test_select_from_file(self, tmp_path: Path) -> None:
        file_path = tmp_path / "scenarios.json"
        file_path.write_text(
            json.dumps(
                [
                    {"name": "a", "items": [{"id": "1", "quantity": 1}]},
                    {"name": "b", "items": [{"id": "2", "quantity": 2}]},
                ]
            )
        )
        args = argparse.Namespace(scenarios_file=file_path, scenario=None)
        selected = _select_scenarios(args)
        assert [s.name for s in selected] == ["a", "b"]

    def test_select_single_from_file(self, tmp_path: Path) -> None:
        file_path = tmp_path / "scenarios.json"
        file_path.write_text(
            json.dumps(
                [
                    {"name": "a", "items": [{"id": "1", "quantity": 1}]},
                    {"name": "b", "items": [{"id": "2", "quantity": 2}]},
                ]
            )
        )
        args = argparse.Namespace(scenarios_file=file_path, scenario="b")
        selected = _select_scenarios(args)
        assert len(selected) == 1
        assert selected[0].name == "b"
