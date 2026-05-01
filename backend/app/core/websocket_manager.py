class WebSocketManager:
    """
    Placeholder for future real-time event broadcasting.

    The trading engine does not depend on this manager; instead, application
    services can publish events here once WebSocket streaming is implemented.
    """

    async def broadcast(self, event_type: str, payload: dict) -> None:
        _ = (event_type, payload)
