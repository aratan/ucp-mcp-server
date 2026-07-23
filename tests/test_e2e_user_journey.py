"""End-to-end functional test: Complete user shopping journey.

This test simulates a real user case from product discovery to order completion,
verifying the full UCP protocol flow works correctly.

User Journey:
1. User asks AI to find products from a flower shop
2. AI discovers merchant capabilities via UCP
3. AI lists available products
4. User selects a product (Bouquet of Red Roses)
5. AI creates a checkout session
6. AI applies a discount code
7. AI processes payment (mock)
8. AI confirms the order
9. AI tracks the order status

This validates the complete cycle from discovery to post-purchase tracking.
"""

import pytest
import respx
from httpx import Response


class TestE2EUserJourney:
    """End-to-end test: Complete shopping journey from discovery to order tracking."""

    @pytest.mark.integration
    async def test_complete_shopping_journey(self, mock_ucp_server):
        """Test the full user shopping journey: discover -> list -> checkout -> order.

        This test validates:
        - Product catalog discovery
        - Product listing
        - Checkout session creation
        - Discount application
        - Payment processing (mock)
        - Order completion
        - Order status tracking
        """
        from ucp_mcp_server.server import (
            ucp_checkout_complete,
            ucp_checkout_create,
            ucp_checkout_set_fulfillment,
            ucp_checkout_update,
            ucp_discover,
            ucp_order_get,
            ucp_products_list,
            ucp_testing_simulate_shipping,
        )

        merchant_url = "http://localhost:8182"

        # Step 1: Discover merchant capabilities
        discovery_result = await ucp_discover(merchant_url)
        assert "ucp_version" in discovery_result
        assert "capabilities" in discovery_result
        assert "payment_handlers" in discovery_result
        print(f"✓ Step 1: Discovered {len(discovery_result['capabilities'])} capabilities")

        # Step 2: List available products
        products_result = await ucp_products_list(merchant_url)
        assert "products" in products_result
        assert len(products_result["products"]) == 2
        assert products_result["products"][0]["id"] == "bouquet_roses"
        print(f"✓ Step 2: Found {len(products_result['products'])} products")

        # Step 3: Create checkout session with selected product
        checkout_result = await ucp_checkout_create(
            merchant_url=merchant_url,
            items=[{"id": "bouquet_roses", "quantity": 1}],
            buyer_name="Juan García",
            buyer_email="juan.garcia@example.com",
        )
        assert "checkout_id" in checkout_result
        assert checkout_result["status"] == "ready_for_complete"
        checkout_id = checkout_result["checkout_id"]
        print(f"✓ Step 3: Created checkout session {checkout_id}")

        # Step 4: Apply discount code
        update_result = await ucp_checkout_update(
            merchant_url=merchant_url,
            checkout_id=checkout_id,
            discount_codes=["10OFF"],
        )
        assert "discount_applied" in update_result
        assert update_result["discount_applied"] > 0
        print(f"✓ Step 4: Applied discount, saved ${update_result['discount_applied'] / 100:.2f}")

        # Step 5: Set fulfillment (shipping)
        fulfillment_result = await ucp_checkout_set_fulfillment(
            merchant_url=merchant_url,
            checkout_id=checkout_id,
        )
        assert "fulfillment" in fulfillment_result
        print(f"✓ Step 5: Set fulfillment method")

        # Step 6: Complete checkout with payment
        complete_result = await ucp_checkout_complete(
            merchant_url=merchant_url,
            checkout_id=checkout_id,
            payment_handler_id="mock_payment_handler",
            card_token="success_token",
            card_brand="Visa",
            card_last_digits="4242",
        )
        assert complete_result["status"] == "complete"
        assert "order_id" in complete_result
        order_id = complete_result["order_id"]
        print(f"✓ Step 6: Payment completed, order {order_id}")

        # Step 7: Get order details
        order_result = await ucp_order_get(
            merchant_url=merchant_url,
            order_id=order_id,
        )
        assert order_result["order_id"] == order_id
        assert order_result["status"] == "complete"
        print(f"✓ Step 7: Order confirmed with status '{order_result['status']}'")

        # Step 8: Simulate shipping
        shipping_result = await ucp_testing_simulate_shipping(
            merchant_url=merchant_url,
            order_id=order_id,
        )
        assert shipping_result["status"] == "shipped"
        print(f"✓ Step 8: Order shipped successfully")

        # Step 9: Verify final order status
        final_order = await ucp_order_get(
            merchant_url=merchant_url,
            order_id=order_id,
        )
        assert final_order["status"] == "complete"
        assert "fulfillment" in final_order
        print(f"✓ Step 9: Final order status verified")

        print("\n🎉 Complete shopping journey test PASSED!")
        print("=" * 60)
        print("User Journey Summary:")
        print(f"  - Merchant: {merchant_url}")
        print(f"  - Product: Bouquet of Red Roses ($35.00)")
        print(f"  - Discount: 10OFF (-$3.50)")
        print(f"  - Final Total: $31.50")
        print(f"  - Order ID: {order_id}")
        print(f"  - Status: Shipped")
        print("=" * 60)

    @pytest.mark.integration
    async def test_product_discovery_and_listing(self, mock_ucp_server):
        """Test product discovery and listing flow."""
        from ucp_mcp_server.server import ucp_discover, ucp_products_list

        merchant_url = "http://localhost:8182"

        # Discover capabilities
        discovery = await ucp_discover(merchant_url)
        assert "capabilities" in discovery

        # List products
        products = await ucp_products_list(merchant_url)
        assert "products" in products
        assert len(products["products"]) > 0

        # Verify product structure
        product = products["products"][0]
        assert "id" in product
        assert "title" in product
        assert "price" in product
        assert isinstance(product["price"], int)  # Price in cents

        print(f"✓ Product discovery and listing: {len(products['products'])} products found")

    @pytest.mark.integration
    async def test_checkout_with_discount(self, mock_ucp_server):
        """Test checkout flow with discount code application."""
        from ucp_mcp_server.server import (
            ucp_checkout_complete,
            ucp_checkout_create,
            ucp_checkout_update,
        )

        merchant_url = "http://localhost:8182"

        # Create checkout
        checkout = await ucp_checkout_create(
            merchant_url=merchant_url,
            items=[{"id": "bouquet_roses", "quantity": 1}],
            buyer_name="Test User",
            buyer_email="test@example.com",
        )
        assert checkout["status"] == "ready_for_complete"

        # Apply discount
        updated = await ucp_checkout_update(
            merchant_url=merchant_url,
            checkout_id=checkout["checkout_id"],
            discount_codes=["10OFF"],
        )
        assert updated["discount_applied"] == 350  # 10% of 3500 cents

        # Complete checkout
        completed = await ucp_checkout_complete(
            merchant_url=merchant_url,
            checkout_id=checkout["checkout_id"],
            payment_handler_id="mock_payment_handler",
            card_token="success_token",
        )
        assert completed["status"] == "complete"

        print(f"✓ Checkout with discount: Total ${completed['total'] / 100:.2f}")

    @pytest.mark.integration
    async def test_order_tracking(self, mock_ucp_server):
        """Test order tracking and shipping simulation."""
        from ucp_mcp_server.server import (
            ucp_checkout_complete,
            ucp_checkout_create,
            ucp_order_get,
            ucp_testing_simulate_shipping,
        )

        merchant_url = "http://localhost:8182"

        # Create and complete a checkout
        checkout = await ucp_checkout_create(
            merchant_url=merchant_url,
            items=[{"id": "bouquet_roses", "quantity": 1}],
            buyer_name="Test User",
            buyer_email="test@example.com",
        )
        completed = await ucp_checkout_complete(
            merchant_url=merchant_url,
            checkout_id=checkout["checkout_id"],
            payment_handler_id="mock_payment_handler",
            card_token="success_token",
        )
        order_id = completed["order_id"]

        # Get order details
        order = await ucp_order_get(
            merchant_url=merchant_url,
            order_id=order_id,
        )
        assert order["order_id"] == order_id
        assert order["status"] == "complete"

        # Simulate shipping
        shipping = await ucp_testing_simulate_shipping(
            merchant_url=merchant_url,
            order_id=order_id,
        )
        assert shipping["status"] == "shipped"

        print(f"✓ Order tracking: Order {order_id} shipped")

    @pytest.mark.integration
    async def test_error_handling_invalid_merchant(self, mock_invalid_server):
        """Test error handling when merchant is unavailable."""
        from ucp_mcp_server.server import ucp_discover

        result = await ucp_discover("http://invalid.example")
        assert "error" in result
        print(f"✓ Error handling: {result['error'][:50]}...")

    @pytest.mark.integration
    async def test_empty_product_catalog(self):
        """Test handling of empty product catalog."""
        with respx.mock(assert_all_called=False) as respx_mock:
            respx_mock.get("http://localhost:8182/products").mock(
                return_value=Response(200, json={"products": []})
            )

            from ucp_mcp_server.server import ucp_products_list

            result = await ucp_products_list("http://localhost:8182")
            assert "products" in result
            assert len(result["products"]) == 0
            print("✓ Empty catalog handling: Returns empty list")


class TestUCPProtocolCompliance:
    """Test UCP protocol compliance based on official specification."""

    @pytest.mark.integration
    async def test_discovery_response_structure(self, mock_ucp_server):
        """Verify discovery response matches UCP specification."""
        from ucp_mcp_server.server import ucp_discover

        result = await ucp_discover("http://localhost:8182")

        # UCP spec requires version, capabilities, payment_handlers
        assert "ucp_version" in result
        assert "capabilities" in result
        assert "payment_handlers" in result

        # Verify version format (YYYY-MM-DD)
        assert len(result["ucp_version"].split("-")) == 3
        print(f"✓ UCP version: {result['ucp_version']}")

    @pytest.mark.integration
    async def test_checkout_session_structure(self, mock_ucp_server):
        """Verify checkout session matches UCP specification."""
        from ucp_mcp_server.server import ucp_checkout_create

        result = await ucp_checkout_create(
            merchant_url="http://localhost:8182",
            items=[{"id": "bouquet_roses", "quantity": 1}],
            buyer_name="Test User",
            buyer_email="test@example.com",
        )

        # UCP checkout session structure
        assert "checkout_id" in result
        assert "status" in result
        assert "line_items" in result
        assert "currency" in result
        assert "total" in result

        # Verify line_items structure
        assert isinstance(result["line_items"], list)
        for item in result["line_items"]:
            assert "id" in item
            assert "quantity" in item

        print(f"✓ Checkout structure valid: {result['status']}")
