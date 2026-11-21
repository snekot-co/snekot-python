"""The shared cases in conformance.json, against a stub server on this machine: every call must put exactly that
method, path and body on the wire. Run with `python -m unittest discover -s tests`."""
import json
import os
import sys
import threading
import unittest
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, HTTPServer

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from snekot_events import Client, FailedToPublish, Refused, Unreachable, __version__  # noqa: E402

with open(os.path.join(os.path.dirname(__file__), "conformance.json"), encoding="utf-8") as fixture:
    SUITE = json.load(fixture)

seen = []
answers = []


class Stub(BaseHTTPRequestHandler):
    def _answer(self):
        body = json.loads(self.rfile.read(int(self.headers["Content-Length"])))
        seen.append({"method": self.command, "path": self.path, "body": body, "auth": self.headers["Authorization"], "type": self.headers["Content-Type"], "agent": self.headers["User-Agent"]})
        status, answer = answers.pop(0) if answers else (200, "{}")
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(answer.encode())

    do_POST = _answer
    do_PATCH = _answer

    def log_message(self, *args):
        pass


def call(client, name, args):
    args = dict(args)
    if name == "track":
        if "timestamp" in args:
            args["date"] = datetime.fromtimestamp(args.pop("timestamp"), tz=timezone.utc)
        return client.track(**args)
    if name == "identify":
        return client.identify(**args)
    if name == "group":
        return client.group(**args)
    if name == "subscribe":
        return client.subscribe(**args)
    if name == "insight.track":
        return client.insight.track(**args)
    if name == "insight.increment":
        return client.insight.increment(**args)
    raise AssertionError("unknown call " + name)


class Conformance(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(("127.0.0.1", 0), Stub)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        cls.endpoint = "http://127.0.0.1:%d" % cls.server.server_port

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        del seen[:]
        del answers[:]
        self.client = Client(token="sk_test", project=SUITE["project"], endpoint=self.endpoint + "/")

    def test_every_case_matches_the_wire_format(self):
        for case in SUITE["cases"]:
            with self.subTest(call=case["call"], args=case["args"]):
                del seen[:]
                call(self.client, case["call"], case["args"])
                self.assertEqual(len(seen), 1)
                sent, expect = seen[0], case["expect"]
                self.assertEqual(sent["method"], expect["method"])
                self.assertEqual(sent["path"], expect["path"])
                self.assertEqual(sent["body"], expect["body"])
                self.assertEqual(sent["agent"], "snekot-python/" + __version__)
                self.assertEqual(sent["auth"], "Bearer sk_test")
                self.assertEqual(sent["type"], "application/json")

    def test_a_refusal_carries_the_servers_sentence(self):
        answers.append((400, '{"error": "bad channel"}'))
        with self.assertRaises(Refused) as raised:
            self.client.track(channel="x", event="y")
        self.assertIsInstance(raised.exception, FailedToPublish)
        self.assertEqual(str(raised.exception), "bad channel")
        self.assertEqual(raised.exception.status, 400)
        self.assertEqual(len(seen), 1)

    def test_a_server_error_is_retried_once(self):
        answers.append((503, "{}"))
        self.client.track(channel="x", event="y")
        self.assertEqual(len(seen), 2)

    def test_two_server_errors_surface_as_unreachable(self):
        answers.extend([(503, "{}"), (500, "not json")])
        with self.assertRaises(Unreachable) as raised:
            self.client.track(channel="x", event="y")
        self.assertEqual(raised.exception.status, 500)
        self.assertEqual(len(seen), 2)

    def test_no_server_surfaces_as_unreachable(self):
        nowhere = Client(token="sk_test", project="p", endpoint="http://127.0.0.1:1", timeout=2)
        with self.assertRaises(Unreachable) as raised:
            nowhere.track(channel="x", event="y")
        self.assertIsNone(raised.exception.status)

    def test_an_experiment_answers_with_the_servers_variant(self):
        answers.append((200, '{"experiment": "pricing", "variant": "new"}'))
        variant = self.client.experiment("pricing", ["control", "new"], user_id="user-1")
        self.assertEqual(variant, "new")
        self.assertEqual(seen[0]["path"], "/v1/experiment")
        self.assertEqual(seen[0]["body"], {"project": SUITE["project"], "experiment": "pricing", "variants": ["control", "new"], "user_id": "user-1"})

    def test_a_disabled_experiment_is_its_first_variant(self):
        self.client.disable_tracking()
        self.assertEqual(self.client.experiment("pricing", ("control", "new")), "control")
        self.assertEqual(seen, [])

    def test_disabled_tracking_sends_nothing(self):
        self.client.disable_tracking()
        self.client.track(channel="x", event="y")
        self.assertEqual(seen, [])
        self.assertTrue(self.client.is_disabled())


if __name__ == "__main__":
    unittest.main()
