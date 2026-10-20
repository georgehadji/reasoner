"""GET an untrusted URL without ever connecting to a non-public address.

Three gaps closed here (docs/plans/audit-remediation-2026-10-20.md SEC-3):

* Redirects. Callers used ``follow_redirects=True`` after checking only the
  first URL. A public page answering ``302 -> http://169.254.169.254/...``
  reached the cloud metadata service. Here every hop is re-resolved and
  re-checked.
* DNS rebinding. The URL is resolved once and the request goes to that
  checked IP. The original host is kept in ``Host`` and in TLS SNI, so
  virtual hosting and certificate checks still work.
* Unbounded bodies. The body is streamed and cut at ``max_bytes``.
"""

from __future__ import annotations

from urllib.parse import urljoin

import httpx

from reasoner.core.constants_limits import SAFE_FETCH_MAX_REDIRECTS
from reasoner.security.url_validator import UnsafeURLError, resolve_public_url


async def safe_get(
    client: httpx.AsyncClient,
    url: str,
    *,
    max_bytes: int,
    headers: dict[str, str] | None = None,
    max_redirects: int = SAFE_FETCH_MAX_REDIRECTS,
) -> tuple[httpx.Response, bytes]:
    """Return the final response (already closed) and up to *max_bytes* of its body.

    *client* must not follow redirects itself; this function follows them.

    Raises:
        UnsafeURLError: a hop is not public, or there are too many redirects.
        httpx.HTTPStatusError: the final response is 4xx/5xx.
        httpx.HTTPError: transport failures, as from ``client.get``.
    """
    for _ in range(max_redirects + 1):
        pinned = await resolve_public_url(url)
        request = client.build_request(
            "GET",
            pinned.url,
            headers={**(headers or {}), "Host": pinned.host},
            extensions={"sni_hostname": pinned.sni},
        )
        response = await client.send(request, stream=True)
        try:
            if response.is_redirect:
                url = urljoin(url, response.headers["location"])
                continue
            response.raise_for_status()
            body = bytearray()
            async for chunk in response.aiter_bytes():
                body += chunk
                if len(body) >= max_bytes:
                    break
            return response, bytes(body[:max_bytes])
        finally:
            await response.aclose()
    raise UnsafeURLError(f"More than {max_redirects} redirects: {url}")
