"""MCP Server exposing UCP shopping capabilities as tools."""

from typing import Any

from mcp.server.fastmcp import FastMCP

from .ucp_client import UCPClient, UCPClientError

# Initialize FastMCP server
mcp = FastMCP("ucp-shopping")


@mcp.tool()
async def ucp_products_list(merchant_url: str) -> dict[str, Any]:
    """
    List available products from a UCP merchant's catalog.

    Args:
        merchant_url: The base URL of the UCP-enabled merchant

    Returns:
        Dictionary containing:
        - products: List of products with id, title, price, and image_url
    """
    try:
        async with UCPClient() as client:
            result = await client.list_products(merchant_url)
            return {
                "products": [
                    {
                        "id": p.id,
                        "title": p.title,
                        "price": p.price,
                        "image_url": p.image_url,
                    }
                    for p in result.products
                ]
            }
    except UCPClientError as e:
        return {"error": str(e)}


@mcp.tool()
async def ucp_products_search(
    merchant_url: str,
    query: str | None = None,
    color: str | None = None,
    category: str | None = None,
    location: str | None = None,
    max_price: int | None = None,
    min_price: int | None = None,
    sort_by: str | None = None,
    specs: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """
    Search and filter products from a UCP merchant's catalog.

    Args:
        merchant_url: The base URL of the UCP-enabled merchant
        query: Text search query to match against product titles
        color: Filter by product color (e.g., 'red', 'blue', 'black')
        category: Filter by product category (e.g., 'pc', 'laptop', 'monitor')
        location: Filter by product location/availability (e.g., 'Madrid', 'Barcelona')
        max_price: Maximum price filter in cents (e.g., 200000 for 2000 EUR)
        min_price: Minimum price filter in cents
        sort_by: Sort results by field ('price_asc', 'price_desc', 'name')
        specs: Filter by product specifications (e.g., {'ram': '16GB', 'gpu': 'RTX 4090'})

    Returns:
        Dictionary containing:
        - products: List of matching products
        - total: Number of products found
        - filters_applied: Summary of filters that were applied
    """
    try:
        async with UCPClient() as client:
            result = await client.list_products(merchant_url)
            products = result.products

            # Apply filters
            filters_applied = {}

            if query:
                query_lower = query.lower()
                products = [
                    p for p in products
                    if query_lower in p.title.lower()
                ]
                filters_applied["query"] = query

            if color:
                color_lower = color.lower()
                products = [
                    p for p in products
                    if p.color and p.color.lower() == color_lower
                ]
                filters_applied["color"] = color

            if category:
                category_lower = category.lower()
                products = [
                    p for p in products
                    if p.category and p.category.lower() == category_lower
                ]
                filters_applied["category"] = category

            if location:
                location_lower = location.lower()
                products = [
                    p for p in products
                    if p.location and location_lower in p.location.lower()
                ]
                filters_applied["location"] = location

            if max_price is not None:
                products = [p for p in products if p.price <= max_price]
                filters_applied["max_price"] = max_price

            if min_price is not None:
                products = [p for p in products if p.price >= min_price]
                filters_applied["min_price"] = min_price

            if specs:
                for key, value in specs.items():
                    value_lower = str(value).lower()
                    products = [
                        p for p in products
                        if key in p.specs and str(p.specs[key]).lower() == value_lower
                    ]
                filters_applied["specs"] = specs

            # Apply sorting
            if sort_by == "price_asc":
                products = sorted(products, key=lambda p: p.price)
            elif sort_by == "price_desc":
                products = sorted(products, key=lambda p: p.price, reverse=True)
            elif sort_by == "name":
                products = sorted(products, key=lambda p: p.title)

            return {
                "products": [
                    {
                        "id": p.id,
                        "title": p.title,
                        "price": p.price,
                        "image_url": p.image_url,
                        "color": p.color,
                        "category": p.category,
                        "location": p.location,
                        "specs": p.specs,
                    }
                    for p in products
                ],
                "total": len(products),
                "filters_applied": filters_applied,
            }
    except UCPClientError as e:
        return {"error": str(e)}


@mcp.tool()
async def ucp_discover(merchant_url: str) -> dict[str, Any]:
    """
    Discover a merchant's UCP capabilities and supported payment methods.

    Args:
        merchant_url: The base URL of the UCP-enabled merchant (e.g., http://localhost:8182)

    Returns:
        Dictionary containing:
        - capabilities: List of UCP capabilities the merchant supports
        - payment_handlers: List of payment methods accepted
        - ucp_version: The UCP protocol version
    """
    try:
        async with UCPClient() as client:
            result = await client.discover(merchant_url)
            return {
                "ucp_version": result.ucp_version,
                "capabilities": [
                    {
                        "name": cap.name,
                        "version": cap.version,
                        "spec": cap.spec,
                    }
                    for cap in result.capabilities
                ],
                "payment_handlers": [
                    {
                        "id": h.id,
                        "name": h.name,
                        "version": h.version,
                    }
                    for h in result.payment_handlers
                ],
            }
    except UCPClientError as e:
        return {"error": str(e)}


@mcp.tool()
async def ucp_checkout_create(
    merchant_url: str,
    items: list[dict[str, Any]],
    buyer_name: str,
    buyer_email: str,
    currency: str = "USD",
) -> dict[str, Any]:
    """
    Create a new checkout session with a UCP merchant.

    Args:
        merchant_url: The base URL of the UCP-enabled merchant
        items: List of items to purchase, each with 'id' and 'quantity'
        buyer_name: Full name of the buyer
        buyer_email: Email address of the buyer
        currency: Currency code (default: USD)

    Returns:
        Dictionary containing:
        - checkout_id: The ID of the created checkout session
        - status: Current status of the checkout
        - total: Total amount in smallest currency unit (e.g., cents)
        - line_items: List of items in the cart
    """
    try:
        async with UCPClient() as client:
            result = await client.create_checkout(
                merchant_url=merchant_url,
                items=items,
                buyer={"name": buyer_name, "email": buyer_email},
                currency=currency,
            )
            return {
                "checkout_id": result.id,
                "status": result.status,
                "total": result.total,
                "subtotal": result.subtotal,
                "currency": result.currency,
                "line_items": [
                    {
                        "id": li.item.get("id"),
                        "title": li.item.get("title"),
                        "quantity": li.quantity,
                    }
                    for li in result.line_items
                ],
            }
    except UCPClientError as e:
        return {"error": str(e)}


@mcp.tool()
async def ucp_checkout_complete(
    merchant_url: str,
    checkout_id: str,
    payment_handler_id: str = "mock_payment_handler",
    card_token: str = "success_token",
    card_brand: str = "Visa",
    card_last_digits: str = "4242",
) -> dict[str, Any]:
    """
    Complete a checkout session by submitting payment. This finalizes the purchase.

    Args:
        merchant_url: The base URL of the UCP-enabled merchant
        checkout_id: The ID of the checkout session to complete
        payment_handler_id: The ID of the payment handler to use (from ucp_discover)
        card_token: Payment token from the payment provider
        card_brand: Card brand (e.g., Visa, Mastercard)
        card_last_digits: Last 4 digits of the card

    Returns:
        Dictionary containing:
        - checkout_id: The checkout session ID
        - status: Final status (should be 'complete')
        - total: Final total charged
        - order_id: The order ID for tracking
        - order_url: Permalink to the order
    """
    try:
        async with UCPClient() as client:
            result = await client.complete_checkout(
                merchant_url=merchant_url,
                checkout_id=checkout_id,
                payment_handler_id=payment_handler_id,
                card_token=card_token,
                card_brand=card_brand,
                card_last_digits=card_last_digits,
            )
            response = {
                "checkout_id": result.id,
                "status": result.status,
                "total": result.total,
                "currency": result.currency,
            }
            if result.order:
                response["order_id"] = result.order.id
                response["order_url"] = result.order.permalink_url
            return response
    except UCPClientError as e:
        return {"error": str(e)}


@mcp.tool()
async def ucp_checkout_set_fulfillment(
    merchant_url: str,
    checkout_id: str,
) -> dict[str, Any]:
    """
    Set up shipping/fulfillment for a checkout. Automatically selects the first
    available shipping address and delivery option. Must be called before
    completing checkout if the merchant requires fulfillment.

    Args:
        merchant_url: The base URL of the UCP-enabled merchant
        checkout_id: The ID of the checkout session

    Returns:
        Dictionary containing:
        - checkout_id: The checkout session ID
        - status: Current status
        - total: Updated total (may include shipping costs)
        - fulfillment: Details of selected shipping method
    """
    try:
        async with UCPClient() as client:
            data = await client.setup_fulfillment(
                merchant_url=merchant_url,
                checkout_id=checkout_id,
            )
            return {
                "checkout_id": data["id"],
                "status": data["status"],
                "total": next(
                    (
                        t["amount"]
                        for t in data.get("totals", [])
                        if t["type"] == "total"
                    ),
                    0,
                ),
                "currency": data.get("currency", "USD"),
                "fulfillment": data.get("fulfillment"),
            }
    except UCPClientError as e:
        return {"error": str(e)}


@mcp.tool()
async def ucp_order_get(
    merchant_url: str,
    order_id: str,
) -> dict[str, Any]:
    """
    Get the current status of an order, including fulfillment details.

    Args:
        merchant_url: The base URL of the UCP-enabled merchant
        order_id: The ID of the order to track

    Returns:
        Dictionary containing:
        - order_id: The order ID
        - status: Current order status
        - currency: Order currency
        - total: Total amount charged
        - fulfillment: Fulfillment details (method, tracking, status)
    """
    try:
        async with UCPClient() as client:
            data = await client.get_order(merchant_url=merchant_url, order_id=order_id)
            return {
                "order_id": data.get("id", order_id),
                "status": data.get("status", "unknown"),
                "currency": data.get("currency", "USD"),
                "total": next(
                    (
                        t["amount"]
                        for t in data.get("totals", [])
                        if t["type"] == "total"
                    ),
                    0,
                ),
                "fulfillment": data.get("fulfillment", {}),
            }
    except UCPClientError as e:
        return {"error": str(e)}


@mcp.tool()
async def ucp_testing_simulate_shipping(
    merchant_url: str,
    order_id: str,
) -> dict[str, Any]:
    """
    Simulate shipping an order via the merchant's testing endpoint.

    Args:
        merchant_url: The base URL of the UCP-enabled merchant
        order_id: The ID of the order to mark as shipped

    Returns:
        Dictionary containing:
        - status: The result of the simulation (e.g., 'shipped')
    """
    try:
        async with UCPClient() as client:
            result = await client.simulate_shipping(
                merchant_url=merchant_url, order_id=order_id
            )
            return result
    except UCPClientError as e:
        return {"error": str(e)}


@mcp.tool()
async def ucp_checkout_update(
    merchant_url: str,
    checkout_id: str,
    discount_codes: list[str] | None = None,
) -> dict[str, Any]:
    """
    Update an existing checkout session (e.g., apply discount codes).

    Args:
        merchant_url: The base URL of the UCP-enabled merchant
        checkout_id: The ID of the checkout session to update
        discount_codes: List of discount/promo codes to apply

    Returns:
        Dictionary containing updated checkout information:
        - checkout_id: The checkout session ID
        - status: Current status
        - total: Updated total amount
        - discount_applied: Amount discounted
        - discounts: Details of applied discounts
    """
    try:
        async with UCPClient() as client:
            result = await client.update_checkout(
                merchant_url=merchant_url,
                checkout_id=checkout_id,
                discount_codes=discount_codes,
            )
            return {
                "checkout_id": result.id,
                "status": result.status,
                "total": result.total,
                "subtotal": result.subtotal,
                "discount_applied": result.discount_amount,
                "currency": result.currency,
                "discounts": result.discounts,
            }
    except UCPClientError as e:
        return {"error": str(e)}


def main():
    """Run the MCP server."""
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
