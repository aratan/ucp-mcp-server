# Product Catalog Specification

## Purpose

Enable AI assistants to discover available products from a UCP merchant before initiating checkout, closing the gap between `ucp_discover` and `ucp_checkout_create`.

## Requirements

### Requirement: Product Listing Retrieval

The system SHALL expose a `ucp_products_list` MCP tool that calls `GET {merchant_url}/products` and returns a structured product catalog.

The tool SHALL accept a `merchant_url` string parameter.

The response SHALL include an array of products, each with: `id` (string), `title` (string), `price` (integer, cents), `image_url` (string, nullable).

#### Scenario: Successful product listing

- GIVEN a merchant exposes a valid `/products` endpoint
- WHEN the AI assistant calls `ucp_products_list` with the merchant URL
- THEN the tool returns a list of Product objects with all required fields populated

#### Scenario: Empty product catalog

- GIVEN a merchant exposes `/products` returning an empty array
- WHEN the AI assistant calls `ucp_products_list`
- THEN the tool returns an empty list with no error

### Requirement: Graceful Error on Missing Endpoint

The system SHALL return a clear, user-facing error when the merchant does not expose a `/products` endpoint (HTTP 404 or connection error).

The error message SHALL indicate the merchant URL that failed and suggest the merchant may not support product listing.

#### Scenario: Merchant lacks /products endpoint

- GIVEN a merchant does not expose a `/products` endpoint
- WHEN the AI assistant calls `ucp_products_list`
- THEN the tool returns an error message indicating the endpoint was not found
- AND the error does not raise an unhandled exception

### Requirement: Response Schema Compliance

The response schema SHALL follow the Pydantic model structure: `ProductListResponse` containing a `products` array of `Product` objects.

#### Scenario: Response model validation

- GIVEN a merchant returns product data from `/products`
- WHEN the response is parsed
- THEN each product conforms to the `Product` model (id, title, price, image_url)
- AND the overall response conforms to `ProductListResponse`

### Requirement: Integration with Existing Tool Pattern

The tool implementation SHALL follow the same 3-layer pattern (models → client → server) and error handling conventions as existing UCP tools.

#### Scenario: Consistent tool behavior

- GIVEN an AI assistant calls `ucp_products_list`
- WHEN the tool executes
- THEN it uses the same UCPClient instance and error handling pattern as `ucp_discover`, `ucp_checkout_create`, etc.
