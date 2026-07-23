"""Tests for UCP order fulfillment tracking functionality.

These tests define our goals for the order tracking tools:
- Goal 1: Agent can fetch order status by order ID
- Goal 2: Agent can simulate shipping via the merchant testing endpoint
"""

import pytest

from ucp_mcp_server.server import ucp_order_get, ucp_testing_simulate_shipping


class TestOrderGet:
    """Tests for the ucp_order_get MCP tool."""

    @pytest.mark.asyncio
    async def test_order_get_returns_order_id(self, mock_ucp_server):
        """Goal: Agent gets order status with order ID."""
        result = await ucp_order_get(
            merchant_url="http://localhost:8182",
            order_id="order-abc-123",
        )

        assert "order_id" in result
        assert result["order_id"] == "order-abc-123"

    @pytest.mark.asyncio
    async def test_order_get_returns_status(self, mock_ucp_server):
        """Goal: Agent knows the order status."""
        result = await ucp_order_get(
            merchant_url="http://localhost:8182",
            order_id="order-abc-123",
        )

        assert "status" in result
        assert result["status"] == "complete"

    @pytest.mark.asyncio
    async def test_order_get_returns_total(self, mock_ucp_server):
        """Goal: Agent knows the order total."""
        result = await ucp_order_get(
            merchant_url="http://localhost:8182",
            order_id="order-abc-123",
        )

        assert "total" in result
        assert result["total"] > 0
        assert isinstance(result["total"], int)

    @pytest.mark.asyncio
    async def test_order_get_returns_fulfillment(self, mock_ucp_server):
        """Goal: Agent gets fulfillment details."""
        result = await ucp_order_get(
            merchant_url="http://localhost:8182",
            order_id="order-abc-123",
        )

        assert "fulfillment" in result
        assert result["fulfillment"]["methods"][0]["status"] == "unfulfilled"

    @pytest.mark.asyncio
    async def test_order_get_invalid_id_returns_error(self):
        """Goal: Invalid order ID returns clear error."""
        import respx
        from httpx import Response

        with respx.mock(assert_all_called=False) as mock:
            mock.get("http://localhost:8182/orders/invalid-id").mock(
                return_value=Response(404, json={"error": "Order not found"})
            )

            result = await ucp_order_get(
                merchant_url="http://localhost:8182",
                order_id="invalid-id",
            )

            assert "error" in result


class TestSimulateShipping:
    """Tests for the ucp_testing_simulate_shipping MCP tool."""

    @pytest.mark.asyncio
    async def test_simulate_shipping_returns_status(self, mock_ucp_server):
        """Goal: Agent can simulate shipping an order."""
        result = await ucp_testing_simulate_shipping(
            merchant_url="http://localhost:8182",
            order_id="order-abc-123",
        )

        assert "status" in result
        assert result["status"] == "shipped"

    @pytest.mark.asyncio
    async def test_simulate_shipping_invalid_id_returns_error(self):
        """Goal: Invalid order ID returns clear error."""
        import respx
        from httpx import Response

        with respx.mock(assert_all_called=False) as mock:
            mock.post(
                "http://localhost:8182/testing/simulate-shipping/invalid-id"
            ).mock(return_value=Response(404, json={"error": "Order not found"}))

            result = await ucp_testing_simulate_shipping(
                merchant_url="http://localhost:8182",
                order_id="invalid-id",
            )

            assert "error" in result
