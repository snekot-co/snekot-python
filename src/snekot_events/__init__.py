"""Post product events, identify users and set insights with Snekot. One module, standard library only.

    from snekot_events import Client
    events = Client(token="sk_...", project="acme-store")
    events.track(channel="payments", event="New subscription", icon=":moneybag:", notify=True)
    events.insight.increment(title="Orders", value=1)

"""
import json
import time
import urllib.error
import urllib.request
from datetime import datetime
from typing import Dict, Optional, Sequence, Union

__all__ = ["Client", "FailedToPublish", "Refused", "Unreachable", "Properties", "DEFAULT_ENDPOINT"]
__version__ = "0.4.0"

DEFAULT_ENDPOINT = "https://api.snekot.co"

Properties = Dict[str, Union[str, int, float, bool]]


class FailedToPublish(Exception):
    """A call that did not get through. It is either `Refused` or `Unreachable`; catch this to catch both.

    `status` is the HTTP status, or None when there was no answer. `data` is the server's JSON answer, if any.
    """

    def __init__(self, msg: str = "Failed to publish", data: Optional[dict] = None, status: Optional[int] = None):
        super().__init__(msg)
        self.data = data
        self.status = status


class Refused(FailedToPublish):
    """The server understood the request and said no. The message is its own sentence for what to fix. Never retried."""


class Unreachable(FailedToPublish):
    """No usable answer twice in a row: the network failed, the request timed out, or the server errored."""


class _Insight:
    def __init__(self, client: "Client"):
        self._client = client

    def track(self, title: str, value: Union[str, int, float], icon: Optional[str] = None) -> None:
        """Sets an insight to a value."""
        self._client._send("POST", "/v1/insight", {"title": title, "value": value, "icon": icon})

    def increment(self, title: str, value: Union[int, float] = 1, icon: Optional[str] = None) -> None:
        """Adds to an insight's number, starting from 0 if it has none. Negative subtracts."""
        self._client._send("PATCH", "/v1/insight", {"title": title, "value": {"$inc": value}, "icon": icon})


class Client:
    """Calls block until the server answers. Safe to share between threads.

    `timeout` is how many seconds one attempt may take. `disable_tracking` makes every call succeed without
    sending anything, for tests and local runs.
    """

    def __init__(self, token: str, project: str, disable_tracking: bool = False, endpoint: str = DEFAULT_ENDPOINT,
                 timeout: float = 10):
        self._token = token
        self._project = project
        self._disabled = disable_tracking
        self._endpoint = endpoint.rstrip("/")
        self._timeout = timeout
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
              icon: Optional[str] = None, tags: Optional[Properties] = None, notify: Optional[bool] = None,
              parser: Optional[str] = None, date: Optional[datetime] = None) -> None:
        """Posts an event to a channel.

        `icon` is one emoji or a shortcode such as `:moneybag:`. `notify` pushes it to the phones of everyone on
        the project. `parser` is "markdown" or "text". A `date` in the past makes it a backfill: stored at that
        time, never pushed to a phone.
        """
        self._send("POST", "/v1/log", {
            "channel": channel, "event": event, "user_id": user_id, "description": description, "icon": icon,
            "tags": tags or None, "notify": notify, "parser": parser, "timestamp": int(date.timestamp()) if date else None,
        })

    def identify(self, user_id: str, properties: Properties) -> None:
        """Sets properties on a user; keys sent again replace their old values."""
        self._send("POST", "/v1/identify", {"user_id": user_id, "properties": properties})

    def group(self, group_id: str, user_id: Optional[str] = None, properties: Optional[Properties] = None) -> None:
        """Describes a group such as a company, and puts `user_id` in it when given."""
        self._send("POST", "/v1/group", {"group_id": group_id, "user_id": user_id, "properties": properties or None})

    def subscribe(self, email: str, name: Optional[str] = None, properties: Optional[Properties] = None,
                  source: Optional[str] = None, notify: Optional[bool] = None, language: Optional[str] = None,
                  timezone: Optional[str] = None) -> None:
        """Puts an address on the project's newsletter list. Signing it up again changes nothing.

        `source` is the page the signup came from, such as `/blog/launch`. `language` is the person's language,
        as a tag such as `sv` or `sv-SE`. `timezone` is the person's time zone, as its IANA name, such as
        `Europe/Stockholm`.
        """
        self._send("POST", "/v1/subscribe", {
            "email": email, "name": name, "properties": properties or None, "source": source, "notify": notify,
            "language": language, "timezone": timezone,
        })

    def experiment(self, experiment: str, variants: Sequence[str], user_id: Optional[str] = None,
                   ip: Optional[str] = None, user_agent: Optional[str] = None) -> str:
        """Which variant of an A/B test a person gets. The same person always gets the same one.

        `variants` is two to eight names; the first is the one the others are measured against, so keep the order
        the same everywhere. Say who is asking with `user_id`, or, for someone with no id, their `ip` and
        `user_agent`, which are not stored. With tracking disabled it is the first variant and nothing is sent.
        """
        if self._disabled:
            return variants[0]
        answer = self._request("POST", "/v1/experiment", {
            "experiment": experiment, "variants": list(variants), "user_id": user_id, "ip": ip, "user_agent": user_agent,
        })
        variant = (answer or {}).get("variant")
        return variant if isinstance(variant, str) else variants[0]

    def _send(self, method: str, path: str, body: dict) -> None:
        if not self._disabled:
            self._request(method, path, body)

    def _request(self, method: str, path: str, body: dict) -> Optional[dict]:
        payload = {key: value for key, value in body.items() if value is not None}
        payload["project"] = self._project
        request = urllib.request.Request(
            self._endpoint + path, data=json.dumps(payload).encode(), method=method,
            headers={
                "Content-Type": "application/json",
                "Authorization": "Bearer " + self._token,
                # Named, because the default "Python-urllib" is turned away by many networks before it reaches a server.
                "User-Agent": "snekot-python/" + __version__,
            },
        )
        # One retry, and only where trying again can help: the network failed or the server did. A refusal is final.
        retried = False
        while True:
            try:
                with urllib.request.urlopen(request, timeout=self._timeout) as response:
                    try:
                        answer = json.loads(response.read())
                    except ValueError:
                        answer = None
                return answer if isinstance(answer, dict) else None
            except urllib.error.HTTPError as error:
                status = error.code
                try:
                    data = json.loads(error.read())
                except (ValueError, OSError):
                    data = None
                if not isinstance(data, dict):
                    data = None
                if status < 500:
                    raise Refused(str((data or {}).get("error") or "The server answered %d." % status), data, status) from None
                failure = Unreachable("The server answered %d." % status, data, status)
            except OSError as error:  # URLError, timeouts and dropped connections are all OSError
                failure = Unreachable("The server at %s could not be reached: %s" % (self._endpoint, error))
            if retried:
                raise failure from None
            retried = True
            time.sleep(0.25)
