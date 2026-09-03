"""Exercise the real HTTP client against an isolated fake AnkiConnect server."""

import copy
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import importlib.util
import json
import os
from pathlib import Path
import socket
import tempfile
import threading
import unittest
from unittest.mock import patch

spec = importlib.util.spec_from_file_location("anki_connect", Path(__file__).parents[1] / "scripts" / "anki_connect.py")
ac = importlib.util.module_from_spec(spec)
spec.loader.exec_module(ac)


class FakeAnki:
    def __init__(self):
        self.notes = {}
        self.actions = []
        self.raw_requests = []
        self.profile = "测试档案"
        self.fields = ["正面", "背面"]
        self.templates = {"卡片 1": {"Front": "{{正面}}", "Back": "{{FrontSide}}<hr>{{背面}}"}}
        self.reject = False
        self.drop_at = None
        self.corrupt = None
        self.extra_card = False
        self.error_key = None

    def call(self, action, params):
        if action == "version":
            return 6
        if action == "getActiveProfile":
            return self.profile
        if action == "deckNames":
            return ["语言::法语"]
        if action == "modelNames":
            return ["基础"]
        if action == "modelFieldNames":
            return self.fields
        if action == "modelTemplates":
            return self.templates
        if action == "canAddNotes":
            return [not self.reject and not any(n["fields"]["正面"] == old["fields"]["正面"]
                                                for old in self.notes.values()) for n in params["notes"]]
        if action == "addNote":
            note_id = 100 + len(self.notes)
            self.notes[note_id] = copy.deepcopy(params["note"])
            return note_id
        if action == "notesInfo":
            result = []
            for note_id in params["notes"]:
                note = self.notes[note_id]
                fields = {k: {"value": v, "order": i} for i, (k, v) in enumerate(note["fields"].items())}
                if self.corrupt == "field":
                    fields["正面"]["value"] = "乱码??"
                result.append({"noteId": note_id, "modelName": note["modelName"], "fields": fields,
                               "tags": ["wrong"] if self.corrupt == "tag" else note["tags"],
                               "cards": [note_id * 10, note_id * 10 + 1] if self.extra_card else [note_id * 10]})
            return result
        if action == "cardsInfo":
            return [{"cardId": card_id, "note": card_id // 10,
                     "deckName": "Wrong" if self.corrupt == "deck" else self.notes[card_id // 10]["deckName"]}
                    for card_id in params["cards"]]
        raise AssertionError("Unexpected API action: " + action)


class IntegrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.path = Path(self.temp.name) / "batch.json"
        self.receipts = Path(self.temp.name) / "receipts"
        self.fake = FakeAnki()
        fake = self.fake

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def do_POST(self):
                raw = self.rfile.read(int(self.headers["Content-Length"]))
                fake.raw_requests.append((raw, self.headers["Content-Type"]))
                request = json.loads(raw.decode("utf-8", errors="strict"))
                fake.actions.append(request["action"])
                if fake.error_key:
                    payload = {"result": None, "error": "Invalid key: " + fake.error_key}
                else:
                    result = fake.call(request["action"], request["params"])
                    if request["action"] == "addNote" and len(fake.notes) == fake.drop_at:
                        self.connection.shutdown(socket.SHUT_RDWR)
                        self.connection.close()
                        return
                    payload = {"result": result, "error": None}
                body = ac.encoded(payload)
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.thread = threading.Thread(target=self.server.serve_forever, kwargs={"poll_interval": 0.01}, daemon=True)
        self.thread.start()
        self.addCleanup(self.stop_server)
        self.client = ac.Client(f"http://127.0.0.1:{self.server.server_port}")
        self.data = {"profile": "测试档案", "deck": "语言::法语", "model": "基础", "front_field": "正面",
                     "back_field": "背面", "tag_rule": "按语言分类", "tags": ["lang::fr"],
                     "notes": [{"front": {"title": "原创练习 éèà", "items": [
                         {"parts": [{"text": "stimuler：激发", "bold": True}], "children": [
                             {"parts": [{"text": "动词；搭配："},
                                        {"text": "stimuler l’imagination", "red": True},
                                        {"text": "（激发想象力）"}]}]}]},
                                "back": ""}]}
        self.write_batch()

    def stop_server(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=2)

    def write_batch(self):
        self.path.write_bytes(ac.encoded(self.data))

    def run_import(self, approved=None):
        if approved is None:
            approved = ac.preview(self.client, self.path)["review_sha256"]
        return ac.import_batch(self.client, self.path, approved, self.receipts)

    def test_preview_read_only_and_success_unicode_and_resume(self):
        review = ac.preview(self.client, self.path)
        self.assertNotIn("addNote", self.fake.actions)
        self.assertIn('<strong>stimuler：激发</strong>',
                      review["confirmation"]["notes"][0]["fields"]["正面"])
        self.assertIn('<span style="color: red;">stimuler l’imagination</span>',
                      review["confirmation"]["notes"][0]["fields"]["正面"])
        result = self.run_import(review["review_sha256"])
        self.assertEqual(result["new_notes"], 1)
        self.assertEqual(result["verified_cards"], 1)
        self.assertEqual(self.fake.notes[100]["fields"]["背面"], "")
        self.assertIn("éèà", self.fake.notes[100]["fields"]["正面"])
        self.assertTrue(any("语言".encode("utf-8") in raw for raw, _ in self.fake.raw_requests))
        self.assertTrue(all("charset=utf-8" in header for _, header in self.fake.raw_requests))
        self.assertEqual(self.run_import()["new_notes"], 0)
        self.assertEqual(self.fake.actions.count("addNote"), 1)

    def test_changed_content_or_tags_requires_fresh_confirmation(self):
        approved = ac.preview(self.client, self.path)["review_sha256"]
        self.data["tags"] = ["new"]
        self.write_batch()
        with self.assertRaisesRegex(ac.SafeError, "Confirmation hash"):
            self.run_import(approved)
        self.assertNotIn("addNote", self.fake.actions)

    def test_template_change_invalidates_confirmation(self):
        approved = ac.preview(self.client, self.path)["review_sha256"]
        self.fake.templates["卡片 1"]["Back"] += "changed"
        with self.assertRaisesRegex(ac.SafeError, "Confirmation hash"):
            self.run_import(approved)

    def test_wrong_profile_and_missing_deck(self):
        self.fake.profile = "其他档案"
        with self.assertRaisesRegex(ac.SafeError, "profile differs"):
            self.run_import()
        self.fake.profile = "测试档案"
        self.data["deck"] = "不存在"
        self.write_batch()
        with self.assertRaisesRegex(ac.SafeError, "deck does not exist"):
            self.run_import()

    def test_duplicate_preflight_adds_nothing(self):
        self.fake.reject = True
        with self.assertRaisesRegex(ac.SafeError, "Preflight rejected"):
            self.run_import()
        self.assertFalse(self.fake.notes)

    def test_batch_duplicates_and_invalid_tags(self):
        self.data["notes"] *= 2
        self.write_batch()
        with self.assertRaisesRegex(ac.SafeError, "Repeated front"):
            ac.load_batch(self.path)
        self.data["notes"] = self.data["notes"][:1]
        self.data["tags"] = ["two words"]
        self.write_batch()
        with self.assertRaisesRegex(ac.SafeError, "whitespace"):
            ac.load_batch(self.path)

    def test_partial_write_lost_response_never_retries(self):
        self.data["notes"].append({"front": "第二张", "back": "解释"})
        self.write_batch()
        self.fake.drop_at = 2
        with self.assertRaisesRegex(ac.SafeError, "no automatic retry"):
            self.run_import()
        self.assertEqual(len(self.fake.notes), 2)
        with self.assertRaisesRegex(ac.SafeError, "outcome unknown"):
            self.run_import()
        self.assertEqual(self.fake.actions.count("addNote"), 2)
        state = json.loads(next(self.receipts.glob("*.json")).read_text(encoding="utf-8"))
        self.assertEqual([e["status"] for e in state["entries"]], ["verified", "pending"])

    def test_readback_mismatch_stops_without_overwrite(self):
        self.fake.corrupt = "field"
        with self.assertRaisesRegex(ac.SafeError, "mismatch"):
            self.run_import()
        self.assertEqual(len(self.fake.notes), 1)
        self.fake.corrupt = None
        self.assertEqual(self.run_import()["new_notes"], 0)

    def test_wrong_deck_is_detected(self):
        self.fake.corrupt = "deck"
        with self.assertRaisesRegex(ac.SafeError, "deck mismatch"):
            self.run_import()

    def test_wrong_tags_are_detected(self):
        self.fake.corrupt = "tag"
        with self.assertRaisesRegex(ac.SafeError, "tag mismatch"):
            self.run_import()

    def test_multiple_cards_are_detected(self):
        self.fake.extra_card = True
        with self.assertRaisesRegex(ac.SafeError, "exactly one card"):
            self.run_import()

    def test_unsupported_model_is_rejected_before_write(self):
        self.fake.templates["反向"] = {"Front": "{{背面}}", "Back": "{{正面}}"}
        with self.assertRaisesRegex(ac.SafeError, "single-template"):
            self.run_import()
        self.assertFalse(self.fake.notes)

    def test_empty_back_and_empty_tags_are_supported(self):
        self.data["tags"] = []
        self.data["tag_rule"] = "无标签"
        self.write_batch()
        self.assertEqual(self.run_import()["tags"], [])

    def test_markup_is_escaped_and_not_executed(self):
        self.assertEqual(ac.render('<script>alert("x")</script>'),
                         '<div style="text-align: left;">&lt;script&gt;alert(&quot;x&quot;)&lt;/script&gt;</div>')
        rendered = ac.render({"title": "", "lines": [{"parts": [
            {"text": '<script>alert("styled")</script>', "bold": True, "red": True}]}]})
        self.assertNotIn("<script>", rendered)
        self.assertIn('<strong><span style="color: red;">&lt;script&gt;', rendered)

    def test_invalid_rich_text_is_rejected(self):
        plain = ac.render({"title": "", "items": [{"text": "plain", "children": ["child"]}]})
        self.assertIn('<li style="text-align: left;">plain', plain)
        self.assertIn('<li style="text-align: left;">child</li>', plain)
        with self.assertRaisesRegex(ac.SafeError, "exactly one"):
            ac.render({"title": "", "items": [{"text": "plain", "parts": [{"text": "rich"}]}]})
        with self.assertRaisesRegex(ac.SafeError, "red must be"):
            ac.render({"title": "", "items": [{"parts": [{"text": "rich", "red": "yes"}]}]})

    def test_replacement_characters_rejected(self):
        self.data["notes"][0]["back"] = "??"
        self.write_batch()
        with self.assertRaisesRegex(ac.SafeError, "replacement characters"):
            ac.load_batch(self.path)

    def test_lock_prevents_concurrent_import(self):
        approved = ac.preview(self.client, self.path)["review_sha256"]
        self.receipts.mkdir()
        (self.receipts / (approved + ".lock")).touch()
        with self.assertRaisesRegex(ac.SafeError, "locked"):
            self.run_import(approved)
        self.assertFalse(self.fake.notes)

    def test_api_key_is_redacted(self):
        self.fake.error_key = "secret-test-token"
        with patch.dict(os.environ, {"ANKICONNECT_API_KEY": self.fake.error_key}):
            with self.assertRaises(ac.SafeError) as error:
                ac.inspect(self.client)
        self.assertNotIn(self.fake.error_key, str(error.exception))

    def test_external_endpoints_are_rejected(self):
        for endpoint in ("https://example.com", "http://0.0.0.0:8765", "http://127.0.0.1@evil.test", "http://127.0.0.1/?key=x"):
            with self.subTest(endpoint=endpoint), self.assertRaises(ac.SafeError):
                ac.Client(endpoint)


if __name__ == "__main__":
    unittest.main()
