#!/usr/bin/env python3
"""Scenario-based end-to-end functional tests for ucp-mcp-server.

This script runs multiple shopping scenarios against one or more UCP merchants.
It can either start the sample merchant server locally or connect to an already
running merchant.

Run all built-in scenarios:
    uv run python scripts/test_mcp_scenarios.py

Run a specific scenario:
    uv run python scripts/test_mcp_scenarios.py --scenario single_roses

Use an external merchant:
    uv run python scripts/test_mcp_scenarios.py --skip-merchant --merchant-url http://localhost:8182

Load custom scenarios from a JSON file:
    uv run python scripts/test_mcp_scenarios.py --scenarios-file scenarios.json
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import tempfile
from collections import defaultdict
from contextlib import ExitStack
from pathlib import Path

# Ensure scripts/e2e_lib.py is importable when running from the repo root.
sys.path.insert(0, str(Path(__file__).resolve().parent))

from e2e_lib import (
    MERCHANT_DIR,
    Scenario,
    E2EError,
    get_free_port,
    merchant_server,
    run_mcp_flow,
)

try:
    from builtins import BaseExceptionGroup as _BaseExceptionGroup
except ImportError:  # pragma: no cover - Python < 3.11
    _BaseExceptionGroup = None  # type: ignore[misc,assignment]

# Built-in scenarios for the sample flower shop merchant.
BUILT_IN_SCENARIOS: list[Scenario] = [
    Scenario(
        name="single_roses",
        items=[{"id": "bouquet_roses", "quantity": 1}],
        discount_codes=["10OFF"],
    ),
    Scenario(
        name="multi_items",
        items=[
            {"id": "bouquet_roses", "quantity": 2},
            {"id": "pot_ceramic", "quantity": 1},
        ],
        discount_codes=["WELCOME20"],
    ),
    Scenario(
        name="fixed_discount",
        items=[{"id": "bouquet_tulips", "quantity": 1}],
        discount_codes=["FIXED500"],
    ),
    Scenario(
        name="no_discount",
        items=[{"id": "orchid_white", "quantity": 1}],
    ),
    Scenario(
        name="out_of_stock",
        items=[{"id": "gardenias", "quantity": 1}],
        should_fail=True,
        expected_error_substring="insufficient stock",
    ),
    # Example of a second merchant instance using the same catalog but a different ID.
    Scenario(
        name="second_merchant",
        items=[{"id": "bouquet_roses", "quantity": 1}],
        merchant_url=None,
        merchant_id="merchant_b",
        discount_codes=["10OFF"],
    ),
]


# ---------------------------------------------------------------------------
# Scenario loading
# ---------------------------------------------------------------------------
def load_scenarios_from_file(path: Path) -> list[Scenario]:
    """Load scenario definitions from a JSON file."""
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, list):
        raise E2EError("Scenarios file must contain a JSON list of scenarios")
    scenarios = []
    for item in data:
        if "merchant_data_dir" in item and item["merchant_data_dir"] is not None:
            item["merchant_data_dir"] = Path(item["merchant_data_dir"])
        if "merchant_id" not in item:
            item["merchant_id"] = None
        scenarios.append(Scenario(**item))
    return scenarios


def write_sample_scenarios_file(path: Path) -> None:
    """Write a sample scenarios JSON file for users to customize."""
    sample = [s.to_dict() for s in BUILT_IN_SCENARIOS]
    path.write_text(json.dumps(sample, indent=2), encoding="utf-8")


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------
def _extract_e2e_error(exc: BaseException) -> E2EError | None:
    """Recursively extract an E2EError, even if wrapped in an ExceptionGroup."""
    if isinstance(exc, E2EError):
        return exc
    if _BaseExceptionGroup is not None and isinstance(exc, _BaseExceptionGroup):
        for sub in exc.exceptions:
            if found := _extract_e2e_error(sub):
                return found
    return None


def _handle_expected_failure(
    exc: E2EError, scenario: Scenario, results: list[tuple[str, bool, str]]
) -> None:
    error_text = str(exc).lower()
    if scenario.should_fail:
        expected = scenario.expected_error_substring
        if not expected or expected.lower() in error_text:
            results.append((scenario.name, True, f"Expected failure: {exc}"))
        else:
            results.append(
                (scenario.name, False, f"Expected substring not found: {exc}")
            )
    else:
        results.append((scenario.name, False, str(exc)))


# ---------------------------------------------------------------------------
# Scenario execution
# ---------------------------------------------------------------------------
async def run_all_scenarios(
    scenarios: list[Scenario],
    *,
    skip_merchant: bool = False,
) -> list[tuple[str, bool, str]]:
    """Run all scenarios and return per-scenario results.

    Scenarios whose ``merchant_url`` is ``None`` (and ``skip_merchant`` is
    ``False``) are grouped by their merchant group key (data directory and
    optional merchant_id). One merchant instance is started per unique group
    on a free port, so multiple merchants can run simultaneously.
    """
    results: list[tuple[str, bool, str]] = []

    async def _run_single(scenario: Scenario) -> None:
        try:
            completed = await run_mcp_flow(scenario)
            if scenario.should_fail:
                results.append(
                    (
                        scenario.name,
                        False,
                        f"Expected failure but succeeded: {completed}",
                    )
                )
            else:
                results.append(
                    (scenario.name, True, f"Order {completed.get('order_id')}")
                )
        except Exception as exc:
            if e2e_exc := _extract_e2e_error(exc):
                _handle_expected_failure(e2e_exc, scenario, results)
            else:
                results.append((scenario.name, False, f"Unexpected error: {exc}"))

    if skip_merchant:
        for scenario in scenarios:
            await _run_single(scenario)
        return results

    # Group scenarios that need a local merchant by their merchant group key.
    grouped: dict[tuple[Path, str | None], list[Scenario]] = defaultdict(list)
    for scenario in scenarios:
        if scenario.merchant_url is None:
            grouped[scenario.merchant_group_key()].append(scenario)

    with ExitStack() as stack:
        # Start one merchant per unique group key.
        for group_key in grouped:
            data_dir, _ = group_key
            port = get_free_port()
            db_dir = Path(
                stack.enter_context(tempfile.TemporaryDirectory(prefix="ucp_mcp_"))
            )
            merchant_url = stack.enter_context(
                merchant_server(db_dir, port, data_dir=data_dir)
            )
            for scenario in grouped[group_key]:
                scenario.merchant_url = merchant_url

        # Run all scenarios sequentially against their assigned merchant URLs.
        for scenario in scenarios:
            await _run_single(scenario)

    return results


def _select_scenarios(args: argparse.Namespace) -> list[Scenario]:
    if args.scenarios_file:
        loaded = load_scenarios_from_file(args.scenarios_file)
        if args.scenario:
            names = {s.name: s for s in loaded}
            if args.scenario not in names:
                raise E2EError(
                    f"Scenario '{args.scenario}' not found in {args.scenarios_file}"
                )
            return [names[args.scenario]]
        return loaded

    if args.scenario:
        names = {s.name: s for s in BUILT_IN_SCENARIOS}
        if args.scenario not in names:
            raise E2EError(
                f"Unknown scenario '{args.scenario}'. "
                f"Available: {', '.join(s.name for s in BUILT_IN_SCENARIOS)}"
            )
        return [names[args.scenario]]

    return list(BUILT_IN_SCENARIOS)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------
async def main() -> int:
    parser = argparse.ArgumentParser(
        description="Scenario-based end-to-end functional tests for ucp-mcp-server"
    )
    parser.add_argument(
        "--scenario",
        type=str,
        help="Run a single built-in or file-loaded scenario by name",
    )
    parser.add_argument(
        "--scenarios-file",
        type=Path,
        help="Load scenario definitions from a JSON file (list of scenario objects)",
    )
    parser.add_argument(
        "--skip-merchant",
        action="store_true",
        help="Assume a UCP merchant server is already running; use --merchant-url to set its URL",
    )
    parser.add_argument(
        "--merchant-url",
        type=str,
        default=None,
        help="Default merchant URL for scenarios without a merchant_url. "
        "When omitted, scenarios with merchant_url=None get a local merchant on a free port.",
    )
    parser.add_argument(
        "--generate-sample",
        type=Path,
        metavar="PATH",
        help="Generate a sample scenarios JSON file and exit",
    )
    args = parser.parse_args()

    if args.generate_sample:
        write_sample_scenarios_file(args.generate_sample)
        print(f"Sample scenarios written to {args.generate_sample}")
        return 0

    if not MERCHANT_DIR.exists():
        raise E2EError(
            f"Sample merchant directory not found: {MERCHANT_DIR}\n"
            "Make sure the .ucp-demo submodule/sample directory is present."
        )

    scenarios = _select_scenarios(args)
    if args.merchant_url:
        for scenario in scenarios:
            if scenario.merchant_url is None:
                scenario.merchant_url = args.merchant_url

    try:
        results = await asyncio.wait_for(
            run_all_scenarios(scenarios, skip_merchant=args.skip_merchant),
            timeout=300,
        )
    except asyncio.TimeoutError:
        print("\n[FAIL] Test timed out after 300 seconds", file=sys.stderr)
        return 1

    # Report
    print("\n" + "=" * 60)
    print("Scenario Results")
    print("=" * 60)
    for name, passed, message in results:
        status = "PASS" if passed else "FAIL"
        print(f"[{status}] {name}: {message}")

    passed_count = sum(1 for _, passed, _ in results if passed)
    print("=" * 60)
    print(f"Passed: {passed_count}/{len(results)}")

    if passed_count != len(results):
        return 1

    return 0


if __name__ == "__main__":
    try:
        sys.exit(asyncio.run(main()))
    except KeyboardInterrupt:
        print("\nInterrupted by user", file=sys.stderr)
        sys.exit(130)
    except E2EError as exc:
        print(f"\n[FAIL] {exc}", file=sys.stderr)
        sys.exit(1)
