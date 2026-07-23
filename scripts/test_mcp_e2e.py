#!/usr/bin/env python3
"""End-to-end functional test for ucp-mcp-server against a real UCP merchant.

This script:
1. Initializes the sample UCP merchant database (flower shop).
2. Starts the UCP merchant server on localhost:8182.
3. Starts the ucp-mcp-server via stdio.
4. Uses the official MCP stdio client to run the full shopping flow:
   discover -> create checkout -> apply discount -> set fulfillment -> complete.
5. Prints a summary and cleans up all processes.

Run with:
    uv run python scripts/test_mcp_e2e.py

Requirements:
- uv
- The sample merchant at .ucp-demo/samples/rest/python/server
"""

from __future__ import annotations

import argparse
import asyncio
import json
import os
import shutil
import sys
import tempfile
from pathlib import Path
from typing import Any

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

DB_DIR = Path(tempfile.gettempdir()) / "ucp_mcp_e2e_test"


async def main(*, skip_merchant: bool = False) -> dict[str, Any]:
    """Run the end-to-end functional test."""
    if not MERCHANT_DIR.exists():
        raise E2EError(
            f"Sample merchant directory not found: {MERCHANT_DIR}\n"
            "Make sure the .ucp-demo submodule/sample directory is present."
        )

    if skip_merchant:
        # Use an already running merchant.
        merchant_url = "http://localhost:8182"
    else:
        # Use a free port so the test is isolated from any other merchant.
        port = get_free_port()
        merchant_url = f"http://localhost:{port}"

    scenario = Scenario(
        name="e2e_flow",
        items=[{"id": "bouquet_roses", "quantity": 1}],
        merchant_url=merchant_url,
        discount_codes=["10OFF"],
        buyer_name="Functional Test",
        buyer_email="func@test.example",
    )

    try:
        if skip_merchant:
            result = await run_mcp_flow(scenario, verbose=True)
        else:
            with merchant_server(DB_DIR, port) as url:
                scenario.merchant_url = url
                result = await run_mcp_flow(scenario, verbose=True)
    finally:
        if not skip_merchant and not os.environ.get("UCP_MCP_E2E_KEEP_DB"):
            shutil.rmtree(DB_DIR, ignore_errors=True)

    return result


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="End-to-end functional test for ucp-mcp-server"
    )
    parser.add_argument(
        "--skip-merchant",
        action="store_true",
        help="Assume a UCP merchant server is already running on localhost:8182",
    )
    return parser.parse_args()


if __name__ == "__main__":
    args = _parse_args()

    try:
        completed = asyncio.run(
            asyncio.wait_for(
                main(skip_merchant=args.skip_merchant),
                timeout=300,
            )
        )
    except asyncio.TimeoutError:
        print("\n[FAIL] Test timed out after 300 seconds", file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        print("\nInterrupted by user", file=sys.stderr)
        sys.exit(130)
    except E2EError as exc:
        print(f"\n[FAIL] {exc}", file=sys.stderr)
        sys.exit(1)
    except Exception as exc:  # pragma: no cover - unexpected errors
        print(f"\n[FAIL] Unexpected error: {exc}", file=sys.stderr)
        sys.exit(1)
    else:
        print("\n=== Functional test passed ===")
        print(json.dumps(completed, indent=2))
