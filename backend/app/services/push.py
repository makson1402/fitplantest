"""Server push through the Expo push service (B-26; FR-R7, decision D11).

`PushSender` is the seam: the jobs depend on the protocol, tests use a fake, production uses `ExpoPushSender`.
Expo answers one *ticket* per message. A ticket with `details.error == "DeviceNotRegistered"` means the token is dead
(the app was uninstalled): the job removes it.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx

log = logging.getLogger(__name__)

BATCH_SIZE = 100  # Expo accepts at most 100 messages per request


@dataclass
class PushMessage:
    to: str
    title: str
    body: str
    data: dict[str, Any] = field(default_factory=dict)


@dataclass
class PushResult:
    delivered: int = 0
    invalid_tokens: list[str] = field(default_factory=list)


class PushDeliveryError(Exception):
    """The push service could not be reached or refused the request as a whole: nothing was delivered, retry later."""


class PushSender(Protocol):
    async def send(self, messages: list[PushMessage]) -> PushResult: ...


class ExpoPushSender:
    def __init__(self, url: str, access_token: str | None = None, *, client: httpx.AsyncClient | None = None):
        self.url, self.access_token = url, access_token
        self.client = client or httpx.AsyncClient(timeout=15)

    async def send(self, messages: list[PushMessage]) -> PushResult:
        result = PushResult()
        headers = {"Accept": "application/json", "Content-Type": "application/json"}
        if self.access_token:
            headers["Authorization"] = f"Bearer {self.access_token}"
        for start in range(0, len(messages), BATCH_SIZE):
            batch = messages[start:start + BATCH_SIZE]
            payload = [{"to": m.to, "title": m.title, "body": m.body, "data": m.data, "sound": "default"}
                       for m in batch]
            try:
                response = await self.client.post(self.url, json=payload, headers=headers)
                response.raise_for_status()
                tickets = response.json()["data"]
            except (httpx.HTTPError, ValueError, KeyError, TypeError) as exc:
                # the message text may hold personal data: log the kind of error only
                raise PushDeliveryError(type(exc).__name__) from exc
            for message, ticket in zip(batch, tickets, strict=False):
                if ticket.get("status") == "ok":
                    result.delivered += 1
                elif (ticket.get("details") or {}).get("error") == "DeviceNotRegistered":
                    result.invalid_tokens.append(message.to)
                else:
                    log.warning("push refused: %s", (ticket.get("details") or {}).get("error", "unknown"))
        return result

    async def aclose(self) -> None:
        await self.client.aclose()
