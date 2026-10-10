from __future__ import annotations

import json
import urllib.error
import urllib.request
from dataclasses import dataclass

from .config import Config
from .events import Event


class DeliveryError(RuntimeError):
    """An event could not be delivered; contains no response body or secret."""

    def __init__(self, message: str, *, transient: bool):
        super().__init__(message)
        self.transient = transient

    @property
    def permanent(self) -> bool:
        return not self.transient


class _NoRedirectHandler(urllib.request.HTTPRedirectHandler):
    """Never let an approved endpoint redirect to an unapproved transport."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


_OPENER = urllib.request.build_opener(_NoRedirectHandler)


@dataclass(slots=True)
class APIClient:
    config: Config

    def send(self, event: Event) -> None:
        payload = json.dumps(
            {"events": [event.to_dict()]}, separators=(",", ":"), ensure_ascii=False
        ).encode("utf-8")
        headers = {"Content-Type": "application/json", "User-Agent": "devloop-collector/0.1"}
        if self.config.token:
            headers["Authorization"] = f"Bearer {self.config.token}"
        request = urllib.request.Request(
            f"{self.config.api_url}/v1/events/batch", data=payload, headers=headers, method="POST"
        )
        try:
            with _OPENER.open(request, timeout=self.config.timeout_seconds) as response:
                status = response.status
        except urllib.error.HTTPError as exc:
            # A conflict means the server already has this idempotent event.
            if exc.code == 409:
                return
            transient = exc.code in {408, 425, 429} or 500 <= exc.code < 600
            raise DeliveryError(
                f"server returned HTTP {exc.code}", transient=transient
            ) from None
        except (urllib.error.URLError, TimeoutError, OSError):
            # Do not include exception strings: proxies and URLs can contain credentials.
            raise DeliveryError("server is unavailable", transient=True) from None
        if not 200 <= status < 300:
            transient = status in {408, 425, 429} or 500 <= status < 600
            raise DeliveryError(f"server returned HTTP {status}", transient=transient)
