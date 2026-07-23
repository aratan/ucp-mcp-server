"""Tests for UCP product catalog functionality.

These tests define our goals for the ucp_products_list tool:
- Goal 1: Agent can list products from a merchant's catalog
- Goal 2: Empty catalog is handled gracefully
- Goal 3: Missing /products endpoint returns error, not exception
- Goal 4: Connection errors return error dict, not exception
"""

import pytest
import respx
from httpx import Response

from ucp_mcp_server.models import Product, ProductListResponse
from ucp_mcp_server.server import ucp_products_list


class TestProductModels:
    """Tests for Pydantic product models (layer: unit)."""

    def test_product_model_validates_required_fields(self):
        """Product model requires id, title, price."""
        p = Product(id="sku_1", title="Widget", price=999)
        assert p.id == "sku_1"
        assert p.title == "Widget"
        assert p.price == 999
        assert p.image_url is None

    def test_product_model_accepts_image_url(self):
        """Product model accepts optional image_url."""
        p = Product(id="sku_2", title="Gadget", price=1500, image_url="http://img.co/x.jpg")
        assert p.image_url == "http://img.co/x.jpg"

    def test_product_list_response_default_empty(self):
        """ProductListResponse defaults to empty products list."""
        resp = ProductListResponse()
        assert resp.products == []

    def test_product_list_response_from_dict(self):
        """ProductListResponse parses dict with nested products."""
        data = {
            "products": [
                {"id": "a", "title": "A", "price": 100},
                {"id": "b", "title": "B", "price": 200, "image_url": "http://img.co/b.png"},
            ]
        }
        resp = ProductListResponse(**data)
        assert len(resp.products) == 2
        assert resp.products[0].id == "a"
        assert resp.products[1].image_url == "http://img.co/b.png"


class TestUCPProductsListTool:
    """Tests for the ucp_products_list MCP tool (layer: integration with respx)."""

    @pytest.mark.asyncio
    async def test_list_products_returns_all_fields(self, mock_ucp_server):
        """Happy path: returns products with all fields populated."""
        result = await ucp_products_list(merchant_url="http://localhost:8182")

        assert "products" in result
        assert len(result["products"]) == 2

        first = result["products"][0]
        assert first["id"] == "bouquet_roses"
        assert first["title"] == "Bouquet of Red Roses"
        assert first["price"] == 3500
        assert first["image_url"] == "http://localhost:8182/images/roses.jpg"

        second = result["products"][1]
        assert second["id"] == "sunflower_bunch"
        assert second["image_url"] is None

    @pytest.mark.asyncio
    async def test_list_products_empty_catalog_returns_empty_list(self):
        """Edge case: merchant has no products."""
        with respx.mock(assert_all_called=False) as respx_mock:
            respx_mock.get("http://localhost:8182/products").mock(
                return_value=Response(200, json={"products": []})
            )
            result = await ucp_products_list(merchant_url="http://localhost:8182")

            assert result["products"] == []
            assert "error" not in result

    @pytest.mark.asyncio
    async def test_list_products_404_returns_error_dict(self):
        """Error path: merchant lacks /products endpoint."""
        with respx.mock(assert_all_called=False) as respx_mock:
            respx_mock.get("http://localhost:8182/products").mock(
                return_value=Response(404, json={"error": "not found"})
            )
            result = await ucp_products_list(merchant_url="http://localhost:8182")

            assert "error" in result
            assert "products" not in result

    @pytest.mark.asyncio
    async def test_list_products_connection_error_returns_error_dict(self):
        """Error path: merchant unreachable."""
        import httpx

        with respx.mock(assert_all_called=False) as respx_mock:
            respx_mock.get("http://unreachable.example/products").mock(
                side_effect=httpx.ConnectError("Connection refused")
            )
            result = await ucp_products_list(
                merchant_url="http://unreachable.example"
            )

            assert "error" in result
            assert "products" not in result

    @pytest.mark.asyncio
    async def test_list_products_response_follows_existing_tool_pattern(self, mock_ucp_server):
        """Consistency: tool returns dict with 'products' key, same as other tools."""
        result = await ucp_products_list(merchant_url="http://localhost:8182")

        assert isinstance(result, dict)
        assert "products" in result
        for p in result["products"]:
            assert isinstance(p, dict)
            assert "id" in p
            assert "title" in p
            assert "price" in p
