"""
Integration test for the OpenAI adapter against a local stand-in server.

There is no OpenAI key in development, so the transport path — request shape,
the parameter-negotiation retries, refusal and truncation handling — would
otherwise be entirely unexercised until it failed in front of a user. These
tests speak real HTTP to a stdlib server that replays the responses the live
API returns in each case.
"""

import json
import sys
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from patently import config, llm

SCHEMA = {
    "type": "object",
    "properties": {"ok": {"type": "boolean"}},
    "required": ["ok"],
    "additionalProperties": False,
}


def completion(content: str, finish="stop", refusal=None):
    return 200, {
        "choices": [{
            "finish_reason": finish,
            "message": {"content": content, "refusal": refusal},
        }]
    }


def error_400(message):
    return 400, {"error": {"message": message}}


class Recorder:
    """Serves a scripted sequence of responses and records what it received."""

    def __init__(self, script):
        self.script = list(script)
        self.requests = []
        handler = self._handler()
        self.server = HTTPServer(("127.0.0.1", 0), handler)
        self.url = f"http://127.0.0.1:{self.server.server_port}/v1/chat/completions"
        # Default poll interval is 0.5s, which shutdown() waits out on every
        # teardown — that alone was most of this file's runtime.
        self.thread = threading.Thread(
            target=lambda: self.server.serve_forever(poll_interval=0.01), daemon=True
        )
        self.thread.start()

    def _handler(self):
        outer = self

        class H(BaseHTTPRequestHandler):
            def do_POST(self):
                body = self.rfile.read(int(self.headers["Content-Length"]))
                outer.requests.append(json.loads(body))
                status, payload = outer.script.pop(0)
                raw = json.dumps(payload).encode()
                self.send_response(status)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(raw)))
                self.end_headers()
                self.wfile.write(raw)

            def log_message(self, *a):
                pass

        return H

    def close(self):
        self.server.shutdown()
        self.server.server_close()


@pytest.fixture
def openai_server(monkeypatch):
    made = []

    def start(script):
        rec = Recorder(script)
        made.append(rec)
        monkeypatch.setattr(llm, "_OPENAI_ENDPOINT", rec.url)
        monkeypatch.setattr(config, "OPENAI_API_KEY", "sk-test")
        monkeypatch.setattr(config, "LLM_PROVIDER", "openai")
        llm._OPENAI_QUIRKS.clear()
        return rec

    yield start
    for rec in made:
        rec.close()
    llm._OPENAI_QUIRKS.clear()


@pytest.mark.asyncio
async def test_happy_path_sends_a_strict_json_schema_request(openai_server):
    rec = openai_server([completion('{"ok": true}')])
    out = await llm.complete_json("sys", "user", SCHEMA, max_tokens=1234, retries=0)

    assert out == {"ok": True}
    sent = rec.requests[0]
    assert sent["model"] == config.OPENAI_MODEL
    assert sent["max_completion_tokens"] == 1234
    assert sent["messages"][0] == {"role": "system", "content": "sys"}
    assert sent["messages"][1] == {"role": "user", "content": "user"}
    fmt = sent["response_format"]
    assert fmt["type"] == "json_schema"
    assert fmt["json_schema"]["strict"] is True
    assert fmt["json_schema"]["schema"] == SCHEMA


@pytest.mark.asyncio
async def test_recovers_when_the_model_rejects_temperature(openai_server):
    """Reasoning models refuse a non-default temperature — one 400, then a
    corrected request, rather than a dead provider."""
    rec = openai_server([
        error_400("Unsupported value: 'temperature' does not support 0.1 with this model."),
        completion('{"ok": true}'),
    ])
    assert await llm.complete_json("s", "u", SCHEMA, retries=0) == {"ok": True}

    assert len(rec.requests) == 2
    assert "temperature" in rec.requests[0]
    assert "temperature" not in rec.requests[1]


@pytest.mark.asyncio
async def test_recovers_when_the_model_wants_the_legacy_token_parameter(openai_server):
    rec = openai_server([
        error_400("Unrecognized request argument supplied: max_completion_tokens"),
        completion('{"ok": true}'),
    ])
    assert await llm.complete_json("s", "u", SCHEMA, max_tokens=99, retries=0) == {"ok": True}

    assert rec.requests[0]["max_completion_tokens"] == 99
    assert rec.requests[1]["max_tokens"] == 99
    assert "max_completion_tokens" not in rec.requests[1]


@pytest.mark.asyncio
async def test_a_learned_correction_is_reused_on_later_calls(openai_server):
    """The correction is worth one round trip per process, not one per call."""
    rec = openai_server([
        error_400("Unsupported value: 'temperature' is not supported with this model."),
        completion('{"ok": true}'),
        completion('{"ok": false}'),
    ])
    await llm.complete_json("s", "u", SCHEMA, retries=0)
    await llm.complete_json("s", "u", SCHEMA, retries=0)

    assert len(rec.requests) == 3
    assert "temperature" not in rec.requests[2]  # no second 400 needed


@pytest.mark.asyncio
async def test_an_unfixable_400_is_reported_not_retried_forever(openai_server):
    rec = openai_server([error_400("You exceeded your current quota.")])
    with pytest.raises(llm.LLMError, match="quota"):
        await llm.complete_json("s", "u", SCHEMA, retries=0)
    assert len(rec.requests) == 1


@pytest.mark.asyncio
async def test_refusal_is_surfaced_rather_than_parsed_as_json(openai_server):
    """A refusal is a 200 with null content; without an explicit check it
    surfaces as a confusing 'empty response' parse error."""
    openai_server([completion(None, refusal="I can't help with that.")])
    with pytest.raises(llm.LLMError, match="declined"):
        await llm.complete_json("s", "u", SCHEMA, retries=0)


@pytest.mark.asyncio
async def test_truncated_output_names_the_token_cap(openai_server):
    openai_server([completion('{"ok": tr', finish="length")])
    with pytest.raises(llm.LLMError, match="token cap"):
        await llm.complete_json("s", "u", SCHEMA, retries=0)


@pytest.mark.asyncio
async def test_bad_key_and_missing_model_get_actionable_messages(openai_server):
    openai_server([(401, {"error": {"message": "Incorrect API key"}})])
    with pytest.raises(llm.LLMError, match=r"\.env"):
        await llm.complete_json("s", "u", SCHEMA, retries=0)

    openai_server([(404, {"error": {"message": "The model does not exist"}})])
    with pytest.raises(llm.LLMError, match="check_provider"):
        await llm.complete_json("s", "u", SCHEMA, retries=0)
