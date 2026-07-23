"""Integration tests against real UCP servers.

These tests are designed to run against the UCP sample flower shop server.
They are marked with @pytest.mark.integration and skipped by default.

To run these tests:
1. Start the UCP sample flower shop server on port 8182
2. Run: pytest tests/test_integration.py -v -m integration --run-integration

Setup instructions for the flower shop server:
```bash
# Clone and set up the UCP samples
git clone https://github.com/Universal-Commerce-Protocol/python-sdk.git sdk/python
git clone https://github.com/Universal-Commerce-Protocol/samples.git
cd samples/rest/python/server
uv sync

# Create database with sample products
mkdir /tmp/ucp_test
uv run import_csv.py \
    --products_db_path=/tmp/ucp_test/products.db \
    --transactions_db_path=/tmp/ucp_test/transactions.db \
    --data_dir=../test_data/flower_shop

# Start the server
uv run server.py \
    --products_db_path=/tmp/ucp_test/products.db \
    --transactions_db_path=/tmp/ucp_test/transactions.db \
    --port=8182
```
"""

import os

import pytest

from ucp_mcp_server.server import (
    ucp_checkout_complete,
    ucp_checkout_create,
    ucp_checkout_set_fulfillment,
    ucp_checkout_update,
    ucp_discover,
    ucp_order_get,
    ucp_testing_simulate_shipping,
)


# Skip integration tests by default
pytestmark = pytest.mark.integration


def pytest_configure(config):
    config.addinivalue_line(
        "markers", "integration: mark test as integration test (requires live server)"
    )


@pytest.fixture
def integration_server_url():
    """Get the integration server URL from environment or default."""
    return os.environ.get("UCP_TEST_SERVER", "http://localhost:8182")


@pytest.fixture
def skip_if_no_server(integration_server_url):
    """Skip test if integration server is not available."""
    import httpx

    try:
        response = httpx.get(f"{integration_server_url}/.well-known/ucp", timeout=5.0)
        if response.status_code != 200:
            pytest.skip(
                f"Integration server not responding correctly at {integration_server_url}"
            )
    except Exception as e:
        pytest.skip(
            f"Integration server not available at {integration_server_url}: {e}"
        )


class TestIntegrationDiscovery:
    """Integration tests for discovery against real server."""

    @pytest.mark.asyncio
    async def test_discover_real_flower_shop(
        self, integration_server_url, skip_if_no_server
    ):
        """Test discovery against real flower shop server."""
        result = await ucp_discover(merchant_url=integration_server_url)

        # Should have no error
        assert "error" not in result, f"Got error: {result.get('error')}"

        # Should have capabilities
        assert "capabilities" in result
        assert len(result["capabilities"]) > 0

        # Should include checkout capability
        capability_names = [c["name"] for c in result["capabilities"]]
        assert any("checkout" in name for name in capability_names)

        # Should have payment handlers
        assert "payment_handlers" in result

        print(f"\nDiscovered capabilities: {capability_names}")
        print(f"Payment handlers: {[h['id'] for h in result['payment_handlers']]}")


class TestIntegrationCheckout:
    """Integration tests for checkout against real server."""

    @pytest.mark.asyncio
    async def test_create_checkout_with_real_product(
        self, integration_server_url, skip_if_no_server
    ):
        """Test creating checkout with a real product."""
        result = await ucp_checkout_create(
            merchant_url=integration_server_url,
            items=[{"id": "bouquet_roses", "quantity": 1}],
            buyer_name="Integration Test",
            buyer_email="integration@test.com",
        )

        # Should have no error
        assert "error" not in result, f"Got error: {result.get('error')}"

        # Should have checkout ID
        assert "checkout_id" in result
        assert result["checkout_id"] != ""

        # Should have status
        assert result["status"] == "ready_for_complete"

        # Should have total > 0
        assert result["total"] > 0

        print(f"\nCreated checkout: {result['checkout_id']}")
        print(f"Total: ${result['total'] / 100:.2f}")

    @pytest.mark.asyncio
    async def test_apply_discount_to_real_checkout(
        self, integration_server_url, skip_if_no_server
    ):
        """Test applying discount to real checkout."""
        # Create checkout first
        checkout = await ucp_checkout_create(
            merchant_url=integration_server_url,
            items=[{"id": "bouquet_roses", "quantity": 1}],
            buyer_name="Integration Test",
            buyer_email="integration@test.com",
        )

        assert "error" not in checkout, f"Checkout error: {checkout.get('error')}"
        original_total = checkout["total"]

        # Apply discount
        result = await ucp_checkout_update(
            merchant_url=integration_server_url,
            checkout_id=checkout["checkout_id"],
            discount_codes=["10OFF"],
        )

        # Should have no error
        assert "error" not in result, f"Got error: {result.get('error')}"

        # Total should be reduced
        assert result["total"] < original_total

        print(f"\nOriginal total: ${original_total / 100:.2f}")
        print(f"Discounted total: ${result['total'] / 100:.2f}")
        print(f"Saved: ${(original_total - result['total']) / 100:.2f}")


async def _create_completed_order(merchant_url: str) -> dict:
    """Helper to create and complete a checkout, returning the completed result.

    Creates a fresh checkout, applies a discount, sets up fulfillment, and
    completes payment so that callers get a valid order_id for order tests.
    """
    checkout = await ucp_checkout_create(
        merchant_url=merchant_url,
        items=[{"id": "bouquet_roses", "quantity": 2}],
        buyer_name="John Doe",
        buyer_email="john.doe@example.com",
    )
    assert "error" not in checkout, f"Checkout error: {checkout.get('error')}"

    updated = await ucp_checkout_update(
        merchant_url=merchant_url,
        checkout_id=checkout["checkout_id"],
        discount_codes=["10OFF"],
    )
    assert "error" not in updated, f"Update error: {updated.get('error')}"

    fulfillment = await ucp_checkout_set_fulfillment(
        merchant_url=merchant_url,
        checkout_id=checkout["checkout_id"],
    )
    assert "error" not in fulfillment, f"Fulfillment error: {fulfillment.get('error')}"

    completed = await ucp_checkout_complete(
        merchant_url=merchant_url,
        checkout_id=checkout["checkout_id"],
        payment_handler_id="mock_payment_handler",
        card_token="success_token",
    )
    assert "error" not in completed, f"Complete error: {completed.get('error')}"
    assert completed.get("order_id") is not None
    return completed


class TestIntegrationOrder:
    """Integration tests for order tracking and shipping simulation."""

    @pytest.mark.asyncio
    async def test_get_order(self, integration_server_url, skip_if_no_server):
        """Test retrieving order details after completing a purchase."""
        completed = await _create_completed_order(integration_server_url)
        order_id = completed["order_id"]

        result = await ucp_order_get(
            merchant_url=integration_server_url,
            order_id=order_id,
        )

        assert "error" not in result, f"Got error: {result.get('error')}"
        assert result["order_id"] == order_id
        assert result.get("status")
        assert "fulfillment" in result
        print(f"\nOrder {order_id} status: {result['status']}")

    @pytest.mark.asyncio
    async def test_simulate_shipping(self, integration_server_url, skip_if_no_server):
        """Test simulating shipping and verifying the order is marked shipped."""
        completed = await _create_completed_order(integration_server_url)
        order_id = completed["order_id"]

        # Confirm the order is not marked as shipped before simulation
        before = await ucp_order_get(
            merchant_url=integration_server_url,
            order_id=order_id,
        )
        assert "error" not in before, f"Got error: {before.get('error')}"
        pre_ship_methods = before.get("fulfillment", {}).get("methods", [])
        assert pre_ship_methods, (
            "Expected fulfillment methods before simulating shipping"
        )
        assert not any(
            method.get("status") == "shipped" for method in pre_ship_methods
        ), "Order should not be shipped before simulation"

        # Simulate shipping (testing endpoint provided by the sample merchant)
        shipping_result = await ucp_testing_simulate_shipping(
            merchant_url=integration_server_url,
            order_id=order_id,
        )
        assert "error" not in shipping_result, (
            f"Got error: {shipping_result.get('error')}"
        )
        assert shipping_result.get("status") == "shipped"
        print(f"\nSimulate shipping result: {shipping_result}")

        # Verify the order is now marked as shipped
        after = await ucp_order_get(
            merchant_url=integration_server_url,
            order_id=order_id,
        )
        assert "error" not in after, f"Got error: {after.get('error')}"
        post_ship_methods = after.get("fulfillment", {}).get("methods", [])
        assert post_ship_methods, (
            "Expected fulfillment methods after simulating shipping"
        )
        assert any(method.get("status") == "shipped" for method in post_ship_methods), (
            "Expected at least one fulfillment method to be marked as shipped"
        )


class TestIntegrationFullFlow:
    """Integration test for complete shopping flow."""

    @pytest.mark.asyncio
    async def test_complete_shopping_flow(
        self, integration_server_url, skip_if_no_server
    ):
        """Test complete flow: discover -> checkout -> discount -> fulfillment -> payment."""
        # Step 1: Discover capabilities
        discovery = await ucp_discover(merchant_url=integration_server_url)
        assert "error" not in discovery
        print("\n--- Step 1: Discovery ---")
        print(f"Found {len(discovery['capabilities'])} capabilities")
        print(f"Found {len(discovery['payment_handlers'])} payment handlers")

        # Step 2: Create checkout
        checkout = await ucp_checkout_create(
            merchant_url=integration_server_url,
            items=[
                {"id": "bouquet_roses", "quantity": 2},
            ],
            buyer_name="John Doe",
            buyer_email="john.doe@example.com",
        )
        assert "error" not in checkout
        print("\n--- Step 2: Create Checkout ---")
        print(f"Checkout ID: {checkout['checkout_id']}")
        print(f"Status: {checkout['status']}")
        print(f"Subtotal: ${checkout['subtotal'] / 100:.2f}")

        # Step 3: Apply discount
        updated = await ucp_checkout_update(
            merchant_url=integration_server_url,
            checkout_id=checkout["checkout_id"],
            discount_codes=["10OFF"],
        )
        assert "error" not in updated
        print("\n--- Step 3: Apply Discount ---")
        print(f"Discount applied: ${updated['discount_applied'] / 100:.2f}")
        print(f"New total: ${updated['total'] / 100:.2f}")

        # Verify the flow
        assert updated["total"] < checkout["total"]
        print("\n--- Step 3 Result ---")
        print(
            f"Saved ${(checkout['total'] - updated['total']) / 100:.2f} with discount!"
        )

        # Step 4: Set up fulfillment (shipping)
        fulfillment = await ucp_checkout_set_fulfillment(
            merchant_url=integration_server_url,
            checkout_id=checkout["checkout_id"],
        )
        assert "error" not in fulfillment, f"Got error: {fulfillment.get('error')}"
        print("\n--- Step 4: Set Fulfillment ---")
        print(f"Total with shipping: ${fulfillment['total'] / 100:.2f}")

        # Step 5: Complete checkout (payment)
        completed = await ucp_checkout_complete(
            merchant_url=integration_server_url,
            checkout_id=checkout["checkout_id"],
            payment_handler_id="mock_payment_handler",
            card_token="success_token",
        )
        assert "error" not in completed, f"Got error: {completed.get('error')}"
        print("\n--- Step 5: Complete Checkout ---")
        print(f"Status: {completed['status']}")
        print(f"Order ID: {completed.get('order_id')}")
        print(f"Order URL: {completed.get('order_url')}")

        # Verify completion
        assert completed["status"] in ("complete", "completed")
        assert completed.get("order_id") is not None
        print("\n--- Flow Complete: Purchase Successful! ---")
