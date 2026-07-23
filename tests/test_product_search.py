"""Tests for product search and filtering functionality."""

import pytest


class TestProductSearch:
    """Test product search with various filters."""

    @pytest.mark.integration
    async def test_search_by_color(self, mock_pc_store):
        """Test filtering products by color."""
        from ucp_mcp_server.server import ucp_products_search

        result = await ucp_products_search(
            merchant_url="http://localhost:8182",
            color="red",
        )

        assert result["total"] == 4
        assert all(p["color"] == "red" for p in result["products"])
        assert result["filters_applied"]["color"] == "red"

    @pytest.mark.integration
    async def test_search_by_category(self, mock_pc_store):
        """Test filtering products by category."""
        from ucp_mcp_server.server import ucp_products_search

        result = await ucp_products_search(
            merchant_url="http://localhost:8182",
            category="pc",
        )

        assert result["total"] == 5
        assert all(p["category"] == "pc" for p in result["products"])

    @pytest.mark.integration
    async def test_search_by_location(self, mock_pc_store):
        """Test filtering products by location."""
        from ucp_mcp_server.server import ucp_products_search

        result = await ucp_products_search(
            merchant_url="http://localhost:8182",
            location="Madrid",
        )

        assert result["total"] == 5
        assert all("Madrid" in p["location"] for p in result["products"])

    @pytest.mark.integration
    async def test_search_by_max_price(self, mock_pc_store):
        """Test filtering products by maximum price."""
        from ucp_mcp_server.server import ucp_products_search

        result = await ucp_products_search(
            merchant_url="http://localhost:8182",
            max_price=200000,  # 2000 EUR in cents
        )

        # Products under 2000 EUR: pc-red-001 (150000), pc-red-003 (185000),
        # pc-blue-001 (120000), pc-black-001 (80000), laptop-red-001 (195000)
        assert result["total"] == 5
        assert all(p["price"] <= 200000 for p in result["products"])

    @pytest.mark.integration
    async def test_search_by_specs(self, mock_pc_store):
        """Test filtering products by specifications."""
        from ucp_mcp_server.server import ucp_products_search

        result = await ucp_products_search(
            merchant_url="http://localhost:8182",
            specs={"use_case": "ai"},
        )

        assert result["total"] == 2
        assert all(p["specs"].get("use_case") == "ai" for p in result["products"])

    @pytest.mark.integration
    async def test_search_combined_filters(self, mock_pc_store):
        """Test combining multiple filters."""
        from ucp_mcp_server.server import ucp_products_search

        result = await ucp_products_search(
            merchant_url="http://localhost:8182",
            color="red",
            category="pc",
            location="Madrid",
            max_price=200000,
        )

        assert result["total"] == 2
        assert all(
            p["color"] == "red"
            and p["category"] == "pc"
            and "Madrid" in p["location"]
            and p["price"] <= 200000
            for p in result["products"]
        )

    @pytest.mark.integration
    async def test_search_sort_by_price_asc(self, mock_pc_store):
        """Test sorting products by price ascending."""
        from ucp_mcp_server.server import ucp_products_search

        result = await ucp_products_search(
            merchant_url="http://localhost:8182",
            color="red",
            sort_by="price_asc",
        )

        prices = [p["price"] for p in result["products"]]
        assert prices == sorted(prices)

    @pytest.mark.integration
    async def test_search_sort_by_price_desc(self, mock_pc_store):
        """Test sorting products by price descending."""
        from ucp_mcp_server.server import ucp_products_search

        result = await ucp_products_search(
            merchant_url="http://localhost:8182",
            color="red",
            sort_by="price_desc",
        )

        prices = [p["price"] for p in result["products"]]
        assert prices == sorted(prices, reverse=True)

    @pytest.mark.integration
    async def test_search_no_results(self, mock_pc_store):
        """Test search with no matching results."""
        from ucp_mcp_server.server import ucp_products_search

        result = await ucp_products_search(
            merchant_url="http://localhost:8182",
            color="green",
        )

        assert result["total"] == 0
        assert result["products"] == []

    @pytest.mark.integration
    async def test_search_returns_all_fields(self, mock_pc_store):
        """Test that search returns all product fields."""
        from ucp_mcp_server.server import ucp_products_search

        result = await ucp_products_search(
            merchant_url="http://localhost:8182",
            color="red",
        )

        for product in result["products"]:
            assert "id" in product
            assert "title" in product
            assert "price" in product
            assert "color" in product
            assert "category" in product
            assert "location" in product
            assert "specs" in product


class TestUserSearchJourney:
    """Test realistic user search scenarios."""

    @pytest.mark.integration
    async def test_find_red_pc_for_ai_in_madrid(self, mock_pc_store):
        """User wants to find a red PC for AI in Madrid under 2000 EUR.

        This test simulates the user's request:
        'Quiero un PC rojo de menos de 2000 euros para IA en Madrid
        con el precio más bajo'
        """
        from ucp_mcp_server.server import ucp_products_search

        # Search with all user criteria
        result = await ucp_products_search(
            merchant_url="http://localhost:8182",
            color="red",
            category="pc",
            location="Madrid",
            max_price=200000,  # 2000 EUR in cents
            specs={"use_case": "ai"},
            sort_by="price_asc",  # Lowest price first
        )

        # Should find 1 matching product
        assert result["total"] == 1

        # Verify it's the correct product
        product = result["products"][0]
        assert product["id"] == "pc-red-003"
        assert product["title"] == "PC IA Rojo NVIDIA H100"
        assert product["price"] == 185000  # 1850 EUR
        assert product["color"] == "red"
        assert product["category"] == "pc"
        assert product["location"] == "Madrid"
        assert product["specs"]["use_case"] == "ai"

        # Verify it's the cheapest option
        assert product["price"] <= 200000

        print(f"\n✓ Found PC: {product['title']}")
        print(f"  Price: {product['price'] / 100:.2f} EUR")
        print(f"  Specs: {product['specs']}")

    @pytest.mark.integration
    async def test_find_cheapest_gaming_pc(self, mock_pc_store):
        """User wants the cheapest gaming PC."""
        from ucp_mcp_server.server import ucp_products_search

        result = await ucp_products_search(
            merchant_url="http://localhost:8182",
            category="pc",
            specs={"use_case": "gaming"},
            sort_by="price_asc",
        )

        assert result["total"] == 2
        # First result should be cheapest
        assert result["products"][0]["price"] < result["products"][1]["price"]
        assert result["products"][0]["specs"]["use_case"] == "gaming"

    @pytest.mark.integration
    async def test_find_all_products_in_madrid(self, mock_pc_store):
        """User wants all products available in Madrid."""
        from ucp_mcp_server.server import ucp_products_search

        result = await ucp_products_search(
            merchant_url="http://localhost:8182",
            location="Madrid",
        )

        assert result["total"] == 5
        assert all("Madrid" in p["location"] for p in result["products"])

    @pytest.mark.integration
    async def test_find_products_under_budget(self, mock_pc_store):
        """User has a budget of 1500 EUR."""
        from ucp_mcp_server.server import ucp_products_search

        result = await ucp_products_search(
            merchant_url="http://localhost:8182",
            max_price=150000,  # 1500 EUR
            sort_by="price_asc",
        )

        # Products under 1500 EUR: pc-red-001 (150000), pc-blue-001 (120000),
        # pc-black-001 (80000)
        assert result["total"] == 3
        assert all(p["price"] <= 150000 for p in result["products"])
        # Verify sorted by price
        prices = [p["price"] for p in result["products"]]
        assert prices == sorted(prices)
