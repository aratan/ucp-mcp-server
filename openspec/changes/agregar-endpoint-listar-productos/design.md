# Design: Add Product Listing Endpoint

## Technical Approach

Add a `ucp_products_list` MCP tool that calls `GET {merchant_url}/products` and returns a structured product catalog. Follows the existing 3-layer pattern (models → client → server) with identical error handling conventions. Purely additive — zero changes to existing tools.

## Architecture Decisions

### Decision: GET-only catalog endpoint (no POST, no auth headers)

| Option | Tradeoff | Decision |
|--------|----------|----------|
| GET with no auth headers | Matches `discover` pattern; catalog is public | **Chosen** |
| GET with UCP-Agent headers | Consistent with other GETs; but catalog likely doesn't need it | Rejected — over-engineering |
| POST with body | No parameters needed for listing; breaks REST conventions | Rejected |

**Rationale**: The `discover` endpoint uses a plain GET. A product catalog is public information that merchants expose for browsing. Adding UCP headers would be defensive but premature — the spec says "merchant-defined, UCP-spec-aligned later."

### Decision: Minimal Product model (4 fields)

| Option | Tradeoff | Decision |
|--------|----------|----------|
| id, title, price, image_url | Matches spec; covers 90% of browse needs | **Chosen** |
| + description, category, inventory | More complete; but spec says filter/sort/search are out of scope | Rejected for now |
| Dict[str, Any] per product | Flexible; loses type safety and MCP schema | Rejected |

**Rationale**: Start minimal. Extending is additive (new optional fields). Pydantic models give us validation and MCP schema generation for free.

### Decision: Typed models for response, dict for return

| Option | Tradeoff | Decision |
|--------|----------|----------|
| Pydantic models internally, dict return | Matches every existing tool pattern | **Chosen** |
| Return Pydantic objects directly | Simpler; breaks MCP serialization pattern | Rejected |

**Rationale**: All 7 existing tools return `dict[str, Any]` from the server function. Consistency > novelty.

## Data Flow

```
AI Assistant
    │
    ▼
ucp_products_list(merchant_url)
    │
    ▼
UCPClient.list_products(merchant_url)
    │
    ▼
GET {merchant_url}/products
    │
    ▼
HTTP 200 → {"products": [...]}
    │
    ▼
Pydantic: ProductListResponse → Product objects
    │
    ▼
Return dict: {"products": [{"id": ..., "title": ..., "price": ..., "image_url": ...}]}
```

Error path:
```
GET {merchant_url}/products → HTTP 404 / ConnectError
    │
    ▼
UCPClientError("Could not connect to merchant: ...")
    │
    ▼
server returns {"error": "..."}
```

## File Changes

| File | Action | Description |
|------|--------|-------------|
| `src/ucp_mcp_server/models.py` | Modify | Add `Product` and `ProductListResponse` models in new "Product Catalog Models" section |
| `src/ucp_mcp_server/ucp_client.py` | Modify | Add `list_products(merchant_url) -> ProductListResponse` method with standard error handling |
| `src/ucp_mcp_server/server.py` | Modify | Add `ucp_products_list` tool function following existing pattern |
| `tests/conftest.py` | Modify | Add `SAMPLE_PRODUCTS_RESPONSE` fixture data and `/products` mock route |
| `tests/test_products.py` | Create | Unit tests: successful listing, empty catalog, 404 error, connection error |

## Interfaces / Contracts

### Pydantic Models (models.py)

```python
class Product(BaseModel):
    """A product in a merchant's catalog."""
    id: str
    title: str
    price: int
    image_url: str | None = None

class ProductListResponse(BaseModel):
    """Response from merchant's /products endpoint."""
    products: list[Product] = Field(default_factory=list)
```

### Client Method (ucp_client.py)

```python
async def list_products(self, merchant_url: str) -> ProductListResponse:
    """List products from a merchant's catalog."""
```

### MCP Tool (server.py)

```python
@mcp.tool()
async def ucp_products_list(merchant_url: str) -> dict[str, Any]:
    """List available products from a UCP merchant's catalog."""
```

## Testing Strategy

| Layer | What to Test | Approach |
|-------|-------------|----------|
| Unit | `list_products` returns products from mock HTTP | Direct function call with `mock_ucp_server` fixture |
| Unit | Empty catalog returns empty list | respx mock returning `{"products": []}` |
| Unit | 404 returns error dict, not exception | respx mock returning 404 |
| Unit | Connection error returns error dict | `mock_invalid_server` fixture with `/products` route |
| Unit | Response validates against Pydantic model | Parse mock response through `ProductListResponse` |

All tests call `ucp_products_list()` directly (no MCP transport), matching existing pattern.

## Threat Matrix

N/A — no routing, shell, subprocess, VCS/PR automation, executable-file classification, or process-integration boundary.

## Migration / Rollout

No migration required. Purely additive — new models, new method, new tool. No database, no state, no existing tool modifications.

## Open Questions

- [ ] Should the tool include UCP-Agent headers for consistency with other GETs, or keep it plain like `discover`? (Design chose plain GET — revisit if merchants require it)
- [ ] Future: If UCP formalizes catalog spec, only `ucp_client.list_products` changes. Tool interface stays stable.
