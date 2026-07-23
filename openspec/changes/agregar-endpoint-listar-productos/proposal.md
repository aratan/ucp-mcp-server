# Proposal: Add Product Listing Endpoint

## Intent

AI assistants cannot discover what products a UCP merchant offers before initiating checkout. The existing 7 tools jump straight from discovery to checkout with product IDs hardcoded. Adding a product listing tool closes this gap, enabling a natural browse → select → buy workflow.

## Scope

### In Scope
- `ucp_products_list` MCP tool that calls `GET /products` on the merchant URL
- `Product` and `ProductListResponse` Pydantic models in `models.py`
- `list_products()` async method in `UCPClient`
- Unit tests (mocked HTTP) and integration tests (respx) following existing patterns
- Graceful error when merchant lacks `/products` endpoint

### Out of Scope
- Product filtering, sorting, search, or recommendations
- Pagination (assumes small catalogs; revisit if needed)
- UCP catalog capability negotiation (no spec exists yet)
- Inventory/stock checks beyond what the endpoint returns
- `ucp_discover` changes to advertise catalog capability

## Capabilities

### New Capabilities
- `product-catalog`: Browse available products from a UCP merchant before checkout

### Modified Capabilities
- None

## Approach

**Merchant-defined, UCP-spec-aligned later.** Follow the established 3-layer pattern:

1. **`models.py`** — Add `Product` (id, title, price, image_url) and `ProductListResponse` Pydantic models
2. **`ucp_client.py`** — Add `list_products(merchant_url) -> ProductListResponse` that calls `GET {merchant_url}/products`
3. **`server.py`** — Add `@mcp.tool() ucp_products_list(merchant_url: str)` with the same error handling pattern as existing tools
4. **Tests** — New `tests/test_products.py` with unit test (mocked client) and integration test (respx mock of `/products`)

If UCP formalizes a catalog spec later, the tool interface stays the same — only the client implementation changes.

## Affected Areas

| Area | Impact | Description |
|------|--------|-------------|
| `src/ucp_mcp_server/models.py` | Modified | Add Product, ProductListResponse models |
| `src/ucp_mcp_server/ucp_client.py` | Modified | Add list_products() method |
| `src/ucp_mcp_server/server.py` | Modified | Add ucp_products_list tool |
| `tests/test_products.py` | New | Unit and integration tests |
| `tests/conftest.py` | Modified | Add /products mock endpoint |

## Risks

| Risk | Likelihood | Mitigation |
|------|------------|------------|
| No standard UCP catalog spec exists | High | Implement pragmatic /products endpoint; document as merchant-defined |
| Some merchants won't expose /products | Medium | Return clear error message; tool fails gracefully like other tools |
| Product model fields may vary across merchants | Medium | Start minimal (id, title, price, image_url); extend later |

## Rollback Plan

Delete the 3 modified files' additions (revert git commits). The new test file gets removed. No database or state changes exist — this is purely additive with no side effects on existing tools.

## Dependencies

None. Uses only existing project dependencies (FastMCP, Pydantic, httpx).

## Success Criteria

- [ ] `ucp_products_list` tool appears in MCP server tool list
- [ ] Tool returns product id, title, price, image_url from merchant
- [ ] Tool returns clear error when `/products` endpoint is unavailable
- [ ] All existing tests still pass (no regressions)
- [ ] New tests achieve 80%+ coverage for new code
- [ ] Code passes `ruff check .` and `ruff format --check`
