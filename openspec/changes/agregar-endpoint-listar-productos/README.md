# Change Request: agregar-endpoint-listar-productos

## Summary
Add a new MCP tool to list products from UCP-enabled merchants. This endpoint will allow AI assistants to browse available products from a merchant's catalog before initiating checkout.

## Motivation
- Users need visibility into what products are available for purchase
- Enables product discovery and browsing capabilities alongside existing shopping workflow
- Aligns with common e-commerce patterns where customers want to see inventory before buying

## Scope
- Create `ucp_list_products` MCP tool in server.py
- Add UCP API client method to fetch products from merchant `/products` endpoint
- Define Pydantic models for product response (Product, ProductList)
- Write unit and integration tests following existing patterns
- Documentation updates to README.md

## Out of Scope
- Filtering/sorting capabilities (v2 feature)
- Product search or recommendations
- Inventory checks beyond availability status

## Success Criteria
1. Agent can list products from a UCP merchant
2. Response includes product IDs, titles, prices, and availability
3. Tests pass with 80%+ coverage for new code