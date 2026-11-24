# snekot-events

The [Snekot](https://snekot.co) SDK for Python. Post product events, get them as push notifications, identify users and set insights.

One module, standard library only. Python 3.8 or newer.

```bash
pip install snekot-events
```

## Use

```python
from snekot_events import Client

events = Client(token=token, project="acme-store")

events.track(channel="payments", event="New subscription", icon="💰", notify=True, tags={"plan": "pro"})
events.identify(user_id="user-123", properties={"plan": "pro"})
events.group("acme", user_id="user-123", properties={"name": "Acme"})
events.subscribe("jane@example.com", name="Jane Park", language="sv-SE", timezone="Europe/Stockholm")
events.insight.track(title="MRR", value="$1,289")
events.insight.increment(title="Orders", value=1)
```

`experiment` asks which variant of an [A/B test](https://snekot.co/docs/experiments) a person gets:

```python
variant = events.experiment("pricing-page", ["control", "annual-first"], user_id="user-123")
```

Use a private key (`sk_…`) on a server. Keys are made in the app under Setup; see [Keys](https://snekot.co/docs/keys).

### Behaviour

- Calls block, and one attempt may take 10 seconds (`timeout`, in seconds).
- A network failure or a server error is retried once, after a quarter of a second, then raises `Unreachable`.
- A refusal (a 4xx, such as a bad channel name) is never retried. It raises `Refused` with the server's own sentence for what to fix, the `status` and the JSON answer as `data`.
- Both are a `FailedToPublish`, so catching that catches everything this SDK raises.
- `disable_tracking=True`, or `events.disable_tracking()`, makes every call succeed without sending anything, for tests and local runs.
- `endpoint` defaults to `https://api.snekot.co`.

## Develop

```bash
python -m unittest discover -s tests
```

Publishing a release here publishes its version to PyPI; the release's tag must be the version in `pyproject.toml`.

The test runs the cases in `tests/conformance.json`, the wire contract every Snekot SDK is tested against, through a stub server on your machine.

## Licence

MIT
