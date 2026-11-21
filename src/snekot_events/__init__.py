"""Post product events, identify users and set insights with Snekot. One file, standard library only.

    from snekot_events import Client
    events = Client(token="sk_...", project="acme-store")
    events.track(channel="payments", event="New subscription", icon=":moneybag:", notify=True)
    events.insight.increment(title="Orders", value=1)

"""
import json
import urllib.error
import urllib.request
from datetime import datetime
from typing import Dict, Optional, Union

__all__ = ["Client", "FailedToPublish", "Properties", "DEFAULT_ENDPOINT"]
__version__ = "0.1.0"

DEFAULT_ENDPOINT = "https://api.snekot.co"

Properties = Dict[str, Union[str, int, float, bool]]


class FailedToPublish(Exception):
    """The server refused a request; `status` is the HTTP status and `data` its JSON answer."""

    def __init__(self, msg: str = "Failed to publish", data: Optional[dict] = None, status: Optional[int] = None):
        super().__init__(msg)
        self.data = data
        self.status = status


class _Insight:
    def __init__(self, client: "Client"):
        self._client = client

    def track(self, title: str, value: Union[str, int, float], icon: Optional[str] = None) -> None:
        """Sets an insight to a value."""
        self._client._send("POST", "/v1/insight", {"title": title, "value": value, "icon": icon})

    def increment(self, title: str, value: Union[int, float], icon: Optional[str] = None) -> None:
        """Adds to an insight's number, starting from 0 if it has none."""
        self._client._send("PATCH", "/v1/insight", {"title": title, "value": {"$inc": value}, "icon": icon})


class Client:
    def __init__(self, token: str, project: str, disable_tracking: bool = False, endpoint: str = DEFAULT_ENDPOINT):
        self._token = token
        self._project = project
        self._disabled = disable_tracking
        self._endpoint = endpoint.rstrip("/")
        self.insight = _Insight(self)

    def disable_tracking(self) -> None:
        self._disabled = True

    def enable_tracking(self) -> None:
        self._disabled = False

    def is_disabled(self) -> bool:
        return self._disabled

    def get_project(self) -> str:
        return self._project

    def track(self, channel: str, event: str, user_id: Optional[str] = None, description: Optional[str] = None,
              icon: Optional[str] = None, tags: Optional[Properties] = None, notify: bool = False,
              parser: Optional[str] = None, date: Optional[datetime] = None) -> None:
        """Posts an event to a channel. A `date` in the past makes it a backfill."""
        self._send("POST", "/v1/log", {
            "channel": channel, "event": event, "user_id": user_id, "description": description, "icon": icon,
            "tags": tags, "notify": notify, "parser": parser, "timestamp": date.timestamp() if date else None,
        })

    def identify(self, user_id: str, properties: Properties) -> None:
        self._send("POST", "/v1/identify", {"user_id": user_id, "properties": properties})

    def group(self, user_id: Optional[str], group_id: str, properties: Optional[Properties] = None) -> None:
        self._send("POST", "/v1/group", {"user_id": user_id, "group_id": group_id, "properties": properties or {}})

    def subscribe(self, email: str, name: Optional[str] = None, properties: Optional[Properties] = None,
                  source: Optional[str] = None, notify: bool = False) -> None:
        """Puts an address on the project's newsletter list. Signing it up again changes nothing."""
        self._send("POST", "/v1/subscribe", {
            "email": email, "name": name, "properties": properties, "source": source, "notify": True if notify else None,
        })

    def _send(self, method: str, path: str, body: dict) -> None:
        if self._disabled:
            return
        payload = {key: value for key, value in body.items() if value is not None}
        payload["project"] = self._project
        request = urllib.request.Request(
            self._endpoint + path, data=json.dumps(payload).encode(), method=method,
            headers={"Content-Type": "application/json", "Authorization": "Bearer " + self._token},
        )
        try:
            urllib.request.urlopen(request, timeout=10).close()
        except urllib.error.HTTPError as error:
            try:
                data = json.loads(error.read())
            except ValueError:
                data = None
            if not isinstance(data, dict):
                data = None
            raise FailedToPublish((data or {}).get("error") or "Failed to publish", data, error.code) from None


