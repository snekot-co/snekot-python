# snekot-events

The [Snekot](https://snekot.co) SDK for Python. Post product events, get them as push notifications, identify users and set insights.

One module, standard library only. Python 3.8 or newer.

```bash
pip install "snekot-events @ git+https://github.com/snekot-co/snekot-python@0.1.0"
```

That installs from this repository's `0.1.0` tag. The package is not on PyPI yet.

## Use

```python
from snekot_events import Client

events = Client(token=token, project="acme-store")

events.track(channel="payments", event="New subscription", icon="💰", notify=True, tags={"plan": "pro"})
events.identify(user_id="user-123", properties={"plan": "pro"})
events.group(user_id="user-123", group_id="acme", properties={"name": "Acme"})
events.subscribe("jane@example.com", name="Jane Park")
events.insight.track(title="MRR", value="$1,289")
events.insight.increment(title="Orders", value=1)
```

Use a private key (`sk_…`) on a server. Keys are made in the app under Setup; see [Keys](https://snekot.co/docs/keys).

### Behaviour

- Calls block, and one attempt may take 10 seconds.
- A refusal (a 4xx, such as a bad channel name) raises `FailedToPublish` with the server's own sentence for what to fix, the `status` and the JSON answer as `data`.
- A network failure raises `urllib.error.URLError`. This SDK does not retry yet.
- `disable_tracking=True`, or `events.disable_tracking()`, makes every call succeed without sending anything, for tests and local runs.
- `endpoint` defaults to `https://api.snekot.co`.

## Develop

```bash
python -m unittest discover -s tests
```

The test runs the cases in `tests/conformance.json`, the wire contract every Snekot SDK is tested against, through a stub server on your machine.

## Licence

MIT
