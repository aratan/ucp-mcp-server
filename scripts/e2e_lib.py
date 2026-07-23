"""Shared helpers for end-to-end functional tests of ucp-mcp-server.

This module contains reusable utilities for:
- Initializing and starting the sample UCP merchant server.
- Connecting to the ucp-mcp-server via the MCP stdio client.
- Running the full shopping flow (discover, create, discount, fulfillment, complete).
"""

from __future__ import annotations

import json
import socket
import subprocess
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import httpx

__all__ = [
    "MERCHANT_DIR",
    "MERCHANT_DATA_DIR",
    "Scenario",
    "E2EError",
    "call_tool",
    "get_free_port",
    "init_merchant_database",
    "merchant_server",
    "port_is_free",
    "run_cmd",
    "run_mcp_flow",
    "terminate_process",
    "wait_for_merchant",
]

try:
    from mcp.client.session import ClientSession
    from mcp.client.stdio import StdioServerParameters, stdio_client
except ImportError as exc:  # pragma: no cover
    raise SystemExit(
        "mcp package is required. Install with: uv pip install mcp"
    ) from exc


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------
ROOT = Path(__file__).resolve().parent.parent
MERCHANT_DIR = ROOT / ".ucp-demo" / "samples" / "rest" / "python" / "server"
MERCHANT_DATA_DIR = MERCHANT_DIR.parent / "test_data" / "flower_shop"


def get_free_port() -> int:
    """Return a free TCP port allocated by the operating system."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("", 0))
        return int(sock.getsockname()[1])


class E2EError(RuntimeError):
    """Raised when a functional test step fails."""


# ---------------------------------------------------------------------------
# Scenario model
# ---------------------------------------------------------------------------
@dataclass
class Scenario:
    """A single functional test scenario.

    If ``merchant_url`` is ``None`` the runner will start a local merchant
    instance on a free port and assign the URL automatically. Use
    ``merchant_data_dir`` to point at a custom CSV catalog; ``None`` uses the
    default flower shop sample.
    """

    name: str
    items: list[dict[str, Any]]
    merchant_url: str | None = None
    merchant_data_dir: Path | None = None
    merchant_id: str | None = None
    discount_codes: list[str] = field(default_factory=list)
    buyer_name: str = "Functional Test"
    buyer_email: str = "func@test.example"
    should_fail: bool = False
    expected_error_substring: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "items": self.items,
            "merchant_url": self.merchant_url,
            "merchant_data_dir": str(self.merchant_data_dir)
            if self.merchant_data_dir
            else None,
            "merchant_id": self.merchant_id,
            "discount_codes": self.discount_codes,
            "buyer_name": self.buyer_name,
            "buyer_email": self.buyer_email,
            "should_fail": self.should_fail,
            "expected_error_substring": self.expected_error_substring,
        }

    def effective_data_dir(self) -> Path:
        return self.merchant_data_dir if self.merchant_data_dir else MERCHANT_DATA_DIR

    def merchant_group_key(self) -> tuple[Path, str | None]:
        """Key used to group scenarios that can share a merchant instance."""
        return (self.effective_data_dir(), self.merchant_id)


# ---------------------------------------------------------------------------
# Merchant server helpers
# ---------------------------------------------------------------------------
def run_cmd(cmd: list[str], cwd: Path | None = None, check: bool = True) -> None:
    """Run a shell command, printing what is executed."""
    print(f"[cmd] {' '.join(cmd)}")
    subprocess.run(cmd, cwd=cwd, check=check)


def port_is_free(port: int) -> bool:
    """Return True if the given TCP port is free on localhost."""
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        return sock.connect_ex(("localhost", port)) != 0


def init_merchant_database(db_dir: Path, data_dir: Path | None = None) -> None:
    """Create/populate the merchant SQLite databases from CSV files."""
    data_dir = data_dir or MERCHANT_DATA_DIR
    db_dir.mkdir(parents=True, exist_ok=True)
    run_cmd(
        [
            "uv",
            "run",
            "import_csv.py",
            f"--products_db_path={db_dir / 'products.db'}",
            f"--transactions_db_path={db_dir / 'transactions.db'}",
            f"--data_dir={data_dir}",
        ],
        cwd=MERCHANT_DIR,
    )
    print(f"[merchant] Database initialized from {data_dir}.")


@contextmanager
def merchant_server(
    db_dir: Path,
    port: int | None = None,
    *,
    data_dir: Path | None = None,
) -> Iterator[str]:
    """Start a UCP merchant server and yield its base URL.

    If ``port`` is ``None`` a free port is allocated automatically. An optional
    ``data_dir`` can be passed to populate the database from a custom catalog.

    Note: This helper also initializes (or re-initializes) the merchant
    SQLite databases from CSV files before starting the server.
    """
    port = port if port is not None else get_free_port()

    if not port_is_free(port):
        raise E2EError(
            f"Port {port} is already in use. "
            "Use --skip-merchant if a UCP server is already running."
        )

    init_merchant_database(db_dir, data_dir=data_dir)

    proc = subprocess.Popen(
        [
            "uv",
            "run",
            "server.py",
            f"--products_db_path={db_dir / 'products.db'}",
            f"--transactions_db_path={db_dir / 'transactions.db'}",
            f"--port={port}",
        ],
        cwd=MERCHANT_DIR,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )

    merchant_url = f"http://localhost:{port}"

    try:
        wait_for_merchant(merchant_url)
        print(f"[merchant] UCP merchant server running at {merchant_url}")
        yield merchant_url
    finally:
        print("[merchant] Stopping merchant server...")
        terminate_process(proc)


def wait_for_merchant(merchant_url: str, timeout: float = 30.0) -> None:
    """Poll the discovery endpoint until the merchant is ready."""
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        try:
            response = httpx.get(f"{merchant_url}/.well-known/ucp", timeout=1.0)
            if response.status_code == 200:
                return
        except httpx.RequestError:
            pass
        time.sleep(0.5)
    raise E2EError("UCP merchant server did not start in time")


def terminate_process(proc: subprocess.Popen[Any]) -> None:
    """Terminate a subprocess gracefully, then forcefully if needed."""
    if proc.poll() is not None:
        return
    proc.terminate()
    try:
        proc.wait(timeout=5)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait(timeout=5)


# ---------------------------------------------------------------------------
# MCP client helpers
# ---------------------------------------------------------------------------
async def call_tool(
    session: ClientSession, name: str, arguments: dict[str, Any]
) -> Any:
    """Call an MCP tool and parse its JSON text response."""
    result = await session.call_tool(name, arguments)
    if result.isError:
        raise E2EError(f"Tool {name} returned isError=true: {result.content}")

    if not result.content:
        return None

    for block in result.content:
        if getattr(block, "type", None) == "text":
            text = block.text
            break
    else:
        raise E2EError(f"Tool {name} returned no text block: {result.content}")

    try:
        data = json.loads(text)
    except json.JSONDecodeError as exc:
        raise E2EError(f"Tool {name} returned non-JSON: {text}") from exc

    if isinstance(data, dict) and "error" in data:
        raise E2EError(f"Tool {name} returned business error: {data['error']}")

    return data


async def run_mcp_flow(
    scenario: Scenario,
    *,
    verbose: bool = False,
) -> dict[str, Any]:
    """Connect to the MCP server over stdio and execute the shopping flow."""
    server_params = StdioServerParameters(
        command="uv",
        args=["run", "python", "-m", "ucp_mcp_server"],
        cwd=str(ROOT),
    )

    async with stdio_client(server_params) as (read_stream, write_stream):
        async with ClientSession(read_stream, write_stream) as session:
            await session.initialize()

            if verbose:
                print("[mcp] Connected to ucp-mcp-server via stdio\n")
                print(f"=== Scenario: {scenario.name} ===")

            merchant_url = scenario.merchant_url

            # Step 1: Discovery
            if verbose:
                print("=== Step 1: ucp_discover ===")
            discovery = await call_tool(
                session, "ucp_discover", {"merchant_url": merchant_url}
            )
            if verbose:
                print(json.dumps(discovery, indent=2))
            capability_names = [c["name"] for c in discovery.get("capabilities", [])]
            assert any("checkout" in name for name in capability_names)
            if verbose:
                print("Discovery OK\n")

            # Step 2: Create checkout
            if verbose:
                print("=== Step 2: ucp_checkout_create ===")
            checkout = await call_tool(
                session,
                "ucp_checkout_create",
                {
                    "merchant_url": merchant_url,
                    "items": scenario.items,
                    "buyer_name": scenario.buyer_name,
                    "buyer_email": scenario.buyer_email,
                },
            )
            if verbose:
                print(json.dumps(checkout, indent=2))
            checkout_id = checkout["checkout_id"]
            assert checkout_id
            original_total = checkout["total"]
            if verbose:
                print(f"Checkout created: {checkout_id}\n")

            # Step 3: Apply discount
            if scenario.discount_codes:
                if verbose:
                    print(
                        f"=== Step 3: ucp_checkout_update ({scenario.discount_codes}) ==="
                    )
                updated = await call_tool(
                    session,
                    "ucp_checkout_update",
                    {
                        "merchant_url": merchant_url,
                        "checkout_id": checkout_id,
                        "discount_codes": scenario.discount_codes,
                    },
                )
                if verbose:
                    print(json.dumps(updated, indent=2))
                assert updated["total"] < original_total
                if verbose:
                    print(
                        f"Discount applied: ${updated['discount_applied'] / 100:.2f}\n"
                    )

            # Step 4: Set fulfillment
            if verbose:
                print("=== Step 4: ucp_checkout_set_fulfillment ===")
            fulfillment = await call_tool(
                session,
                "ucp_checkout_set_fulfillment",
                {
                    "merchant_url": merchant_url,
                    "checkout_id": checkout_id,
                },
            )
            if verbose:
                print(json.dumps(fulfillment, indent=2))
            if "error" in fulfillment:
                raise E2EError(f"Fulfillment failed: {fulfillment['error']}")
            if verbose:
                print("Fulfillment configured\n")

            # Step 5: Complete checkout
            if verbose:
                print("=== Step 5: ucp_checkout_complete ===")
            completed = await call_tool(
                session,
                "ucp_checkout_complete",
                {
                    "merchant_url": merchant_url,
                    "checkout_id": checkout_id,
                    "payment_handler_id": "mock_payment_handler",
                    "card_token": "success_token",
                },
            )
            if verbose:
                print(json.dumps(completed, indent=2))
            assert completed["status"] in ("complete", "completed")
            assert completed.get("order_id")
            if verbose:
                print(f"Order placed: {completed['order_id']}\n")

            return completed
