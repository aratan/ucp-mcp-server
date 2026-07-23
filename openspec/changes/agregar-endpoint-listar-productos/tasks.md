# Tasks: Add Product Listing Endpoint

## Review Workload Forecast

| Field | Value |
|-------|-------|
| Estimated changed lines | 135–175 |
| 400-line budget risk | Low |
| Chained PRs recommended | No |
| Suggested split | Single PR |
| Delivery strategy | auto-chain |
| Chain strategy | pending |

Decision needed before apply: No
Chained PRs recommended: No
Chain strategy: pending
400-line budget risk: Low

### Suggested Work Units

| Unit | Goal | Likely PR | Focused test command | Runtime harness | Rollback boundary |
|------|------|-----------|----------------------|-----------------|-------------------|
| 1 | Pydantic models + client method | PR 1 | `pytest tests/test_products.py -v` | mock HTTP server via respx | `models.py` + `ucp_client.py` changes |
| 2 | MCP tool + integration tests | PR 1 | `pytest tests/test_products.py -v` | mock HTTP server via respx | `server.py` tool + `tests/` additions |

## Phase 1: Foundation (Pydantic Models)

- [x] 1.1 Add `Product` model to `src/ucp_mcp_server/models.py` in a new "Product Catalog Models" section — fields: `id: str`, `title: str`, `price: int`, `image_url: str | None = None`
- [x] 1.2 Add `ProductListResponse` model to `src/ucp_mcp_server/models.py` — field: `products: list[Product] = Field(default_factory=list)`

## Phase 2: RED — Write Failing Tests (Client Layer)

- [x] 2.1 Add `SAMPLE_PRODUCTS_RESPONSE` fixture and `/products` mock route to `tests/conftest.py`
- [x] 2.2 Create `tests/test_products.py` with test: successful product listing returns list of Product objects
- [x] 2.3 Add test: empty catalog returns empty list, no error
- [x] 2.4 Add test: 404 from merchant returns error dict, not exception
- [x] 2.5 Add test: connection error returns error dict

## Phase 3: GREEN — Implement Client Method

- [x] 3.1 Add `list_products(merchant_url: str) -> ProductListResponse` to `src/ucp_mcp_server/ucp_client.py` with `GET {merchant_url}/products` and standard `UCPClientError` handling for 404/ConnectError

## Phase 4: REFACTOR — Verify Client Tests Pass

- [x] 4.1 Run `pytest tests/test_products.py -v` — all 4 client tests pass

## Phase 5: RED — Write Failing Test (Server Tool)

- [x] 5.1 Add test to `tests/test_products.py`: calling `ucp_products_list(merchant_url)` returns `{"products": [...]}` dict (not Pydantic objects)

## Phase 6: GREEN — Implement MCP Tool

- [x] 6.1 Add `ucp_products_list` tool to `src/ucp_mcp_server/server.py` — `@mcp.tool()` decorated, accepts `merchant_url: str`, calls `UCPClient.list_products()`, returns `dict[str, Any]`

## Phase 7: REFACTOR — Verify All Tests Pass

- [x] 7.1 Run `pytest tests/test_products.py -v` — all tests (client + server) pass
- [x] 7.2 Run `pytest` (full suite) — no regressions

## Phase 8: Cleanup

- [x] 8.1 Verify no temporary/mock-only code leaked into production files
- [x] 8.2 Confirm models are importable: `python -c "from ucp_mcp_server.models import Product, ProductListResponse"`
