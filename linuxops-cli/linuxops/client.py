"""HTTP client for LinuxOps backend API."""

import httpx
from typing import Any


class LinuxOpsClient:
    """Thin HTTP client — all agent logic lives in the backend."""

    def __init__(self, base_url: str, token: str | None = None, timeout: float = 60.0):
        """Initialize the client.

        Args:
            base_url: Backend API base URL.
            token: Optional API token for auth.
            timeout: Request timeout in seconds.
        """
        self._base_url = base_url.rstrip("/")
        self._headers = {"Content-Type": "application/json"}
        if token:
            self._headers["Authorization"] = f"Bearer {token}"
        self._client = httpx.Client(
            base_url=self._base_url,
            headers=self._headers,
            timeout=timeout,
        )

    def close(self) -> None:
        """Close the HTTP client."""
        self._client.close()

    def __enter__(self):
        return self

    def __exit__(self, *args):
        self.close()

    def chat(self, message: str) -> dict[str, Any]:
        """Send a message to the agent and get the response.

        Args:
            message: The user's message.

        Returns:
            Dict with 'response' and 'tool_calls' keys.

        Raises:
            httpx.HTTPStatusError: On API errors.
        """
        resp = self._client.post("/chat", json={"message": message})
        resp.raise_for_status()
        return resp.json()

    def health(self) -> dict[str, Any]:
        """Check backend health.

        Returns:
            Dict with status, ollama connectivity, latency, providers.
        """
        resp = self._client.get("/health")
        resp.raise_for_status()
        return resp.json()

    def list_conversations(self, limit: int = 20) -> list[dict[str, Any]]:
        """List conversation history.

        Args:
            limit: Max conversations to return.

        Returns:
            List of conversation summaries.
        """
        resp = self._client.get("/conversations", params={"limit": limit})
        resp.raise_for_status()
        return resp.json()

    def get_conversation(self, conv_id: str) -> dict[str, Any]:
        """Get a single conversation with all messages.

        Args:
            conv_id: Conversation ID.

        Returns:
            Full conversation with messages.
        """
        resp = self._client.get(f"/conversations/{conv_id}")
        resp.raise_for_status()
        return resp.json()

    def get_audit_log(self, limit: int = 50) -> list[dict[str, Any]]:
        """Get audit log entries.

        Args:
            limit: Max entries to return.

        Returns:
            List of audit entries (tool executions).
        """
        resp = self._client.get("/audit-log", params={"limit": limit})
        resp.raise_for_status()
        return resp.json()

    def approve_tool_call(self, call_id: str, approved: bool) -> dict[str, Any]:
        """Approve or deny a pending tool call.

        Args:
            call_id: The tool call ID.
            approved: True to approve, False to deny.

        Returns:
            Result of the approval.
        """
        resp = self._client.post(
            "/tools/approve",
            json={"call_id": call_id, "approved": approved},
        )
        resp.raise_for_status()
        return resp.json()
