import io
import json
import tempfile
import unittest
import urllib.error
from pathlib import Path

import classify_comments as app


class FakeResponse:
    def __init__(self, payload): self.payload = payload
    def __enter__(self): return io.StringIO(json.dumps(self.payload))
    def __exit__(self, *args): return False


def valid_response(choice="acceptable"):
    return {"success": True, "result": {"answers": {"moderation": {
        "type": "choice", "choice": choice,
        "probabilities": {"acceptable": .8, "toxic": .1, "spam": .1}, "confidence": .7,
    }}}}


class ClassifierTests(unittest.TestCase):
    def test_input_validation_rejects_missing_text_and_duplicate_id(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "comments.json"
            path.write_text(json.dumps({"comments": [{"id": 1}, {"id": 1, "comment": "x"}]}))
            with self.assertRaisesRegex(app.ValidationError, "comment"):
                app.load_comments(path)

    def test_parse_answer_preserves_scores_and_rejects_bad_labels(self):
        answer = app.parse_answer(valid_response("spam"))
        self.assertEqual(answer["label"], "spam")
        self.assertEqual(answer["confidence"], .7)
        with self.assertRaisesRegex(app.ValidationError, "invalid"):
            app.parse_answer(valid_response("unknown"))

    def test_mocked_success_and_failure_never_become_acceptable(self):
        calls = iter([FakeResponse(valid_response("toxic"))] + [urllib.error.URLError("offline")] * app.MAX_ATTEMPTS)
        def opener(*_args, **_kwargs):
            item = next(calls)
            if isinstance(item, Exception): raise item
            return item
        results = app.classify_all(
            [{"id": 1, "comment": "bad"}, {"id": 2, "comment": "network problem"}],
            "account", "token", opener=opener, sleep=lambda _: None,
        )
        self.assertEqual(results[0]["label"], "toxic")
        self.assertEqual(results[1]["status"], "failed")
        self.assertNotIn("label", results[1])

    def test_malformed_response_is_a_failure(self):
        result = app.request_one("test", "account", "token", opener=lambda *_a, **_k: FakeResponse(valid_response("wrong")), sleep=lambda _: None)
        self.assertEqual(result["status"], "failed")
        self.assertNotIn("label", result)

    def test_rate_limit_and_timeout_are_retried_with_mocked_responses(self):
        rate_limit = urllib.error.HTTPError("https://example.test", 429, "Too Many Requests", {"Retry-After": "0"}, None)
        events = iter([rate_limit, TimeoutError(), FakeResponse(valid_response("spam"))])
        waits = []
        def opener(*_args, **_kwargs):
            event = next(events)
            if isinstance(event, Exception): raise event
            return event
        result = app.request_one("test", "account", "token", opener=opener, sleep=waits.append)
        self.assertEqual(result["status"], "classified")
        self.assertEqual(result["label"], "spam")
        self.assertEqual(waits, [0.0, 4])

    def test_report_escapes_untrusted_comment_text_and_shows_failure(self):
        output = {"model": "clef", "source": {"forum": "<Forum>"}, "results": [
            {"id": 1, "text": "<img src=x onerror=alert(1)>", "source": {"author": "<author>"}, "status": "classified", "label": "acceptable", "confidence": .9},
            {"id": 2, "text": "timed out", "source": {}, "status": "failed", "error": "Request timed out", "attempts": 4},
        ]}
        page = app.report_html(output)
        self.assertIn("Request failed", page)
        self.assertIn("textContent", page)
        self.assertNotIn("<img src=x onerror=alert(1)>", page)
        self.assertIn("\\u003cimg", page)

    def test_output_and_report_are_generated_from_mock_results(self):
        with tempfile.TemporaryDirectory() as directory:
            output_path = Path(directory) / "classifications.json"
            report_path = Path(directory) / "comments.html"
            output = app.write_json(output_path, {"course": "test", "comments": []}, [{"id": 1, "text": "x", "source": {}, "status": "classified", "label": "spam", "attempts": 1}])
            app.write_report(report_path, output)
            self.assertEqual(json.loads(output_path.read_text())["model"], "clef")
            self.assertIn("Clef comment moderation", report_path.read_text())


if __name__ == "__main__":
    unittest.main()
