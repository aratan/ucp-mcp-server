"""HTTP client for UCP API calls with rate limiting, retry, and structured logging."""

import asyncio
import logging
import time
import uuid
from typing import Any

import httpx

from .config import config
from .models import (
    CheckoutSession,
    PaymentHandler,
    ProductListResponse,
    UCPCapability,
    UCPDiscoveryResponse,
)

logger = logging.getLogger("ucp_mcp_server")


class UCPClientError(Exception):
    """Error from UCP client operations."""

    pass


class RateLimiter:
    """Token bucket rate limiter for async operations."""

    def __init__(self, max_per_second: float = 100):
        self._max_per_second = max_per_second
        self._tokens = max_per_second
        self._last_refill = time.monotonic()
        self._lock = asyncio.Lock()

    async def acquire(self) -> None:
        """Acquire a rate limit token, waiting if necessary."""
        async with self._lock:
            now = time.monotonic()
            elapsed = now - self._last_refill
            self._tokens = min(self._max_per_second, self._tokens + elapsed * self._max_per_second)
            self._last_refill = now

            if self._tokens < 1:
                wait_time = (1 - self._tokens) / self._max_per_second
                logger.debug(f"Rate limit: waiting {wait_time:.3f}s")
                await asyncio.sleep(wait_time)
                self._tokens = 0
            else:
                self._tokens -= 1


class DiscoveryCache:
    """Simple TTL cache for discovery responses."""

    def __init__(self, ttl: int = 300):
        self._cache: dict[str, tuple[float, Any]] = {}
        self._ttl = ttl

    def get(self, merchant_url: str) -> Any | None:
        """Get cached discovery response if valid."""
        if merchant_url in self._cache:
            timestamp, data = self._cache[merchant_url]
            if time.time() - timestamp < self._ttl:
                logger.debug(f"Discovery cache hit: {merchant_url}")
                return data
            del self._cache[merchant_url]
        return None

    def set(self, merchant_url: str, data: Any) -> None:
        """Cache a discovery response."""
        self._cache[merchant_url] = (time.time(), data)


# Global instances
_rate_limiter = RateLimiter(config.RATE_LIMIT_PER_SECOND)
_discovery_cache = DiscoveryCache(config.DISCOVERY_CACHE_TTL)


class UCPClient:
    """Async HTTP client for UCP merchant APIs with rate limiting and retry."""

    def __init__(
        self,
        timeout: float | None = None,
        max_retries: int | None = None,
    ):
        self.timeout = timeout or config.TIMEOUT
        self.max_retries = max_retries or config.MAX_RETRIES
        self._client: httpx.AsyncClient | None = None

    async def __aenter__(self) -> "UCPClient":
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(self.timeout, connect=config.CONNECT_TIMEOUT),
            limits=httpx.Limits(
                max_connections=config.MAX_CONCURRENT_REQUESTS,
                max_keepalive_connections=config.MAX_CONCURRENT_REQUESTS // 2,
            ),
        )
        return self

    async def __aexit__(self, *args) -> None:
        if self._client:
            await self._client.aclose()
            self._client = None

    def _get_client(self) -> httpx.AsyncClient:
        if self._client is None:
            raise UCPClientError("Client not initialized. Use async context manager.")
        return self._client

    async def _request_with_retry(
        self,
        method: str,
        url: str,
        **kwargs,
    ) -> httpx.Response:
        """Execute HTTP request with retry and exponential backoff."""
        last_error = None

        for attempt in range(self.max_retries + 1):
            await _rate_limiter.acquire()

            try:
                client = self._get_client()
                response = await client.request(method, url, **kwargs)

                # Don't retry on 4xx errors (client errors)
                if 400 <= response.status_code < 500:
                    response.raise_for_status()

                # Retry on 5xx errors
                if response.status_code >= 500:
                    raise httpx.HTTPStatusError(
                        f"Server error: {response.status_code}",
                        request=response.request,
                        response=response,
                    )

                return response

            except (httpx.ConnectError, httpx.TimeoutException, httpx.HTTPStatusError) as e:
                last_error = e
                if attempt < self.max_retries:
                    backoff = min(
                        config.RETRY_BACKOFF_BASE * (2 ** attempt),
                        config.RETRY_BACKOFF_MAX,
                    )
                    logger.warning(
                        f"Request failed (attempt {attempt + 1}/{self.max_retries + 1}), "
                        f"retrying in {backoff:.1f}s: {e}"
                    )
                    await asyncio.sleep(backoff)
                else:
                    logger.error(f"Request failed after {self.max_retries + 1} attempts: {e}")

        raise last_error

    async def discover(self, merchant_url: str) -> UCPDiscoveryResponse:
        """Discover merchant UCP capabilities with caching."""
        # Check cache first
        cached = _discovery_cache.get(merchant_url)
        if cached is not None:
            return cached

        url = f"{merchant_url.rstrip('/')}/.well-known/ucp"

        try:
            response = await self._request_with_retry("GET", url)
            data = response.json()
        except httpx.ConnectError as e:
            raise UCPClientError(f"Could not connect to merchant: {e}")
        except httpx.HTTPStatusError as e:
            raise UCPClientError(f"HTTP error from merchant: {e}")
        except Exception as e:
            raise UCPClientError(f"Error discovering merchant: {e}")

        # Parse the UCP response
        ucp_data = data.get("ucp", {})

        # The server returns capabilities as a dict of {name: [version_objects]}.
        # Flatten to a list of UCPCapability objects, one per version entry.
        capabilities = []
        for cap_name, cap_versions in ucp_data.get("capabilities", {}).items():
            for ver in cap_versions:
                capabilities.append(
                    UCPCapability(
                        name=cap_name,
                        version=ver.get("version", "unknown"),
                        spec=ver.get("spec"),
                    )
                )

        # Payment handlers live under ucp.payment_handlers, not payment.handlers.
        # Same dict-of-lists format.
        handlers = []
        for handler_name, handler_versions in ucp_data.get(
            "payment_handlers", {}
        ).items():
            for ver in handler_versions:
                handlers.append(
                    PaymentHandler(
                        id=ver.get("id", handler_name),
                        name=ver.get("name", handler_name),
                        version=ver.get("version", "unknown"),
                        spec=ver.get("spec"),
                        config=ver.get("config", {}),
                    )
                )

        result = UCPDiscoveryResponse(
            version=ucp_data.get("version", "unknown"),
            capabilities=capabilities,
            payment_handlers=handlers,
        )

        # Cache the result
        _discovery_cache.set(merchant_url, result)

        return result

    async def list_products(self, merchant_url: str) -> ProductListResponse:
        """List products from a merchant's catalog."""
        url = f"{merchant_url.rstrip('/')}/products"

        try:
            response = await self._request_with_retry("GET", url)
            data = response.json()
        except httpx.ConnectError as e:
            raise UCPClientError(f"Could not connect to merchant: {e}")
        except httpx.HTTPStatusError as e:
            raise UCPClientError(
                f"HTTP error from merchant: {e.response.status_code} - {e.response.text}"
            )
        except Exception as e:
            raise UCPClientError(f"Error listing products: {e}")

        return ProductListResponse(**data)

    async def create_checkout(
        self,
        merchant_url: str,
        items: list[dict[str, Any]],
        buyer: dict[str, str],
        currency: str = "USD",
        payment_handlers: list[dict] | None = None,
    ) -> CheckoutSession:
        """Create a new checkout session."""
        url = f"{merchant_url.rstrip('/')}/checkout-sessions"

        # Build line items
        line_items = [
            {
                "item": {"id": item["id"], "title": item.get("title", "")},
                "quantity": item["quantity"],
            }
            for item in items
        ]

        payload = {
            "line_items": line_items,
            "buyer": {
                "full_name": buyer.get("name", ""),
                "email": buyer.get("email", ""),
            },
            "currency": currency,
            "payment": {
                "instruments": [],
                "handlers": payment_handlers or [],
            },
        }

        headers = {
            "Content-Type": "application/json",
            "UCP-Agent": 'profile="https://ucp-mcp-server.example/profile"',
            "request-signature": "test",
            "idempotency-key": str(uuid.uuid4()),
            "request-id": str(uuid.uuid4()),
        }

        try:
            response = await self._request_with_retry("POST", url, json=payload, headers=headers)
            data = response.json()
        except httpx.ConnectError as e:
            raise UCPClientError(f"Could not connect to merchant: {e}")
        except httpx.HTTPStatusError as e:
            raise UCPClientError(
                f"HTTP error from merchant: {e.response.status_code} - {e.response.text}"
            )
        except Exception as e:
            raise UCPClientError(f"Error creating checkout: {e}")

        return CheckoutSession(**data)

    async def complete_checkout(
        self,
        merchant_url: str,
        checkout_id: str,
        payment_handler_id: str,
        card_token: str = "success_token",
        card_brand: str = "Visa",
        card_last_digits: str = "4242",
    ) -> CheckoutSession:
        """Complete a checkout session by submitting payment."""
        url = f"{merchant_url.rstrip('/')}/checkout-sessions/{checkout_id}/complete"

        payload = {
            "payment": {
                "instruments": [
                    {
                        "id": f"instr_{uuid.uuid4().hex[:8]}",
                        "handler_id": payment_handler_id,
                        "type": "card",
                        "credential": {
                            "type": "token",
                            "token": card_token,
                        },
                        "billing_address": {
                            "street_address": "123 Main St",
                            "address_locality": "Anytown",
                            "address_region": "CA",
                            "address_country": "US",
                            "postal_code": "12345",
                        },
                    }
                ],
            },
            "risk_signals": {
                "ip": "127.0.0.1",
                "browser": "ucp-mcp-server",
            },
        }

        headers = {
            "Content-Type": "application/json",
            "UCP-Agent": 'profile="https://ucp-mcp-server.example/profile"',
            "request-signature": "test",
            "idempotency-key": str(uuid.uuid4()),
            "request-id": str(uuid.uuid4()),
        }

        try:
            response = await self._request_with_retry("POST", url, json=payload, headers=headers)
            data = response.json()
        except httpx.ConnectError as e:
            raise UCPClientError(f"Could not connect to merchant: {e}")
        except httpx.HTTPStatusError as e:
            raise UCPClientError(
                f"HTTP error from merchant: {e.response.status_code} - {e.response.text}"
            )
        except Exception as e:
            raise UCPClientError(f"Error completing checkout: {e}")

        return CheckoutSession(**data)

    async def get_checkout(
        self,
        merchant_url: str,
        checkout_id: str,
    ) -> dict[str, Any]:
        """Fetch current checkout state."""
        url = f"{merchant_url.rstrip('/')}/checkout-sessions/{checkout_id}"
        headers = {
            "UCP-Agent": 'profile="https://ucp-mcp-server.example/profile"',
            "request-signature": "test",
            "request-id": str(uuid.uuid4()),
        }
        try:
            response = await self._request_with_retry("GET", url, headers=headers)
            return response.json()
        except httpx.ConnectError as e:
            raise UCPClientError(f"Could not connect to merchant: {e}")
        except httpx.HTTPStatusError as e:
            raise UCPClientError(
                f"HTTP error from merchant: {e.response.status_code} - {e.response.text}"
            )
        except Exception as e:
            raise UCPClientError(f"Error fetching checkout: {e}")

    async def raw_update_checkout(
        self,
        merchant_url: str,
        checkout_id: str,
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """Send a raw update payload to a checkout session."""
        url = f"{merchant_url.rstrip('/')}/checkout-sessions/{checkout_id}"
        headers = {
            "Content-Type": "application/json",
            "UCP-Agent": 'profile="https://ucp-mcp-server.example/profile"',
            "request-signature": "test",
            "idempotency-key": str(uuid.uuid4()),
            "request-id": str(uuid.uuid4()),
        }
        try:
            response = await self._request_with_retry("PUT", url, json=payload, headers=headers)
            return response.json()
        except httpx.ConnectError as e:
            raise UCPClientError(f"Could not connect to merchant: {e}")
        except httpx.HTTPStatusError as e:
            raise UCPClientError(
                f"HTTP error from merchant: {e.response.status_code} - {e.response.text}"
            )
        except Exception as e:
            raise UCPClientError(f"Error updating checkout: {e}")

    async def setup_fulfillment(
        self,
        merchant_url: str,
        checkout_id: str,
    ) -> dict[str, Any]:
        """Set up fulfillment (shipping) for a checkout. Auto-selects first address and option."""
        # Get current checkout state
        current = await self.get_checkout(merchant_url, checkout_id)

        # Extract line item IDs from the current checkout
        line_item_ids = [
            li.get("id") or li.get("item", {}).get("id")
            for li in current.get("line_items", [])
        ]

        base_payload = {
            "id": checkout_id,
            "line_items": current["line_items"],
            "currency": current["currency"],
            "payment": current["payment"],
        }

        method_id = str(uuid.uuid4())
        dest_id = f"dest_{uuid.uuid4().hex[:8]}"

        # Step 1: Trigger fulfillment generation with a default shipping address
        # so the merchant can calculate shipping options.
        payload = {
            **base_payload,
            "fulfillment": {
                "methods": [
                    {
                        "id": method_id,
                        "type": "shipping",
                        "line_item_ids": line_item_ids,
                        "destinations": [
                            {
                                "id": dest_id,
                                "street_address": "123 Main St",
                                "address_locality": "Anytown",
                                "address_region": "CA",
                                "address_country": "US",
                                "postal_code": "12345",
                            }
                        ],
                    }
                ]
            },
        }
        data = await self.raw_update_checkout(merchant_url, checkout_id, payload)

        # Step 2: Select first destination
        fulfillment = data.get("fulfillment", {})
        methods = fulfillment.get("methods", [])
        if not methods:
            return data

        method = methods[0]
        method_id = method.get("id", method_id)
        destinations = method.get("destinations", [])
        if not destinations:
            return data

        dest_id = destinations[0]["id"]
        payload = {
            **base_payload,
            "line_items": data["line_items"],
            "payment": data["payment"],
            "fulfillment": {
                "methods": [
                    {
                        "id": method_id,
                        "type": "shipping",
                        "line_item_ids": line_item_ids,
                        "selected_destination_id": dest_id,
                    }
                ]
            },
        }
        data = await self.raw_update_checkout(merchant_url, checkout_id, payload)

        # Step 3: Select first shipping option
        fulfillment = data.get("fulfillment", {})
        methods = fulfillment.get("methods", [])
        if not methods:
            return data

        method = methods[0]
        groups = method.get("groups", [])
        if not groups or not groups[0].get("options"):
            return data

        option_id = groups[0]["options"][0]["id"]
        group_id = groups[0].get("id", f"group_{uuid.uuid4()}")
        payload = {
            **base_payload,
            "line_items": data["line_items"],
            "payment": data["payment"],
            "fulfillment": {
                "methods": [
                    {
                        "id": method_id,
                        "type": "shipping",
                        "line_item_ids": line_item_ids,
                        "selected_destination_id": dest_id,
                        "groups": [
                            {
                                "id": group_id,
                                "line_item_ids": line_item_ids,
                                "selected_option_id": option_id,
                            }
                        ],
                    }
                ]
            },
        }
        data = await self.raw_update_checkout(merchant_url, checkout_id, payload)
        return data

    async def get_order(
        self,
        merchant_url: str,
        order_id: str,
    ) -> dict[str, Any]:
        """Fetch an order by ID."""
        url = f"{merchant_url.rstrip('/')}/orders/{order_id}"
        headers = {
            "UCP-Agent": 'profile="https://ucp-mcp-server.example/profile"',
            "request-signature": "test",
            "request-id": str(uuid.uuid4()),
        }
        try:
            response = await self._request_with_retry("GET", url, headers=headers)
            return response.json()
        except httpx.ConnectError as e:
            raise UCPClientError(f"Could not connect to merchant: {e}")
        except httpx.HTTPStatusError as e:
            raise UCPClientError(
                f"HTTP error from merchant: {e.response.status_code} - {e.response.text}"
            )
        except Exception as e:
            raise UCPClientError(f"Error fetching order: {e}")

    async def simulate_shipping(
        self,
        merchant_url: str,
        order_id: str,
    ) -> dict[str, Any]:
        """Simulate shipping an order (merchant testing endpoint)."""
        url = f"{merchant_url.rstrip('/')}/testing/simulate-shipping/{order_id}"
        headers = {
            "UCP-Agent": 'profile="https://ucp-mcp-server.example/profile"',
            "request-signature": "test",
            "request-id": str(uuid.uuid4()),
        }
        try:
            response = await self._request_with_retry("POST", url, headers=headers)
            return response.json()
        except httpx.ConnectError as e:
            raise UCPClientError(f"Could not connect to merchant: {e}")
        except httpx.HTTPStatusError as e:
            raise UCPClientError(
                f"HTTP error from merchant: {e.response.status_code} - {e.response.text}"
            )
        except Exception as e:
            raise UCPClientError(f"Error simulating shipping: {e}")

    async def update_checkout(
        self,
        merchant_url: str,
        checkout_id: str,
        discount_codes: list[str] | None = None,
        line_items: list[dict] | None = None,
    ) -> CheckoutSession:
        """Update an existing checkout session."""
        url = f"{merchant_url.rstrip('/')}/checkout-sessions/{checkout_id}"

        # First, fetch the current checkout state so we can send required fields
        get_headers = {
            "UCP-Agent": 'profile="https://ucp-mcp-server.example/profile"',
            "request-signature": "test",
            "request-id": str(uuid.uuid4()),
        }
        try:
            get_response = await self._request_with_retry("GET", url, headers=get_headers)
            current = get_response.json()
        except Exception:
            # If we can't fetch, build a minimal payload
            current = {}

        payload: dict[str, Any] = {"id": checkout_id}

        # Include required fields from current checkout state
        if current.get("line_items"):
            payload["line_items"] = current["line_items"]
        if line_items:
            payload["line_items"] = line_items

        payload["currency"] = current.get("currency", "USD")
        payload["payment"] = current.get("payment", {"instruments": [], "handlers": []})

        if discount_codes:
            payload["discounts"] = {"codes": discount_codes}

        headers = {
            "Content-Type": "application/json",
            "UCP-Agent": 'profile="https://ucp-mcp-server.example/profile"',
            "request-signature": "test",
            "idempotency-key": str(uuid.uuid4()),
            "request-id": str(uuid.uuid4()),
        }

        try:
            response = await self._request_with_retry("PUT", url, json=payload, headers=headers)
            data = response.json()
        except httpx.ConnectError as e:
            raise UCPClientError(f"Could not connect to merchant: {e}")
        except httpx.HTTPStatusError as e:
            raise UCPClientError(
                f"HTTP error from merchant: {e.response.status_code} - {e.response.text}"
            )
        except Exception as e:
            raise UCPClientError(f"Error updating checkout: {e}")

        return CheckoutSession(**data)
