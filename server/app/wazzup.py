from __future__ import annotations

import httpx


class WazzupError(RuntimeError):
    pass


class WazzupClient:
    """Small adapter for the official Wazzup v3 API."""

    def __init__(self, token: str, base_url: str = "https://api.wazzup24.com",
                 client: httpx.Client | None = None) -> None:
        self.token = token
        self.base_url = base_url.rstrip("/")
        self.client = client or httpx.Client()

    def _headers(self) -> dict[str, str]:
        if not self.token:
            raise WazzupError("WAZZUP_API_TOKEN is not configured")
        return {
            "Authorization": f"Bearer {self.token}",
            "Content-Type": "application/json",
        }

    def channels(self) -> list[dict]:
        response = self.client.get(
            f"{self.base_url}/v3/channels", headers=self._headers(), timeout=15
        )
        response.raise_for_status()
        payload = response.json()
        return payload.get("data", payload) if isinstance(payload, dict) else payload

    def send_text(
        self,
        *,
        channel_id: str,
        chat_type: str,
        chat_id: str,
        text: str,
        reply_to: str | None = None,
        crm_message_id: str | None = None,
    ) -> dict:
        body = {
            "channelId": channel_id,
            "chatType": chat_type,
            "chatId": chat_id,
            "text": text,
            "clearUnanswered": True,
        }
        if reply_to:
            body["refMessageId"] = reply_to
        if crm_message_id:
            body["crmMessageId"] = crm_message_id
        response = self.client.post(
            f"{self.base_url}/v3/message",
            headers=self._headers(),
            json=body,
            timeout=20,
        )
        response.raise_for_status()
        return response.json()

