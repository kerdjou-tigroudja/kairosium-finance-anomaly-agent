"""Tests matérialisation CSV inline (Dev UI)."""

from __future__ import annotations

import os
from unittest.mock import MagicMock

from google.genai import types

from orchestrator.inline_csv import (
    PLAYGROUND_CSV_STATE_KEY,
    _extract_latest_user_csv_bytes,
    persist_playground_csv_before_model,
)


def test_extract_last_user_turn_prefers_latest_user_only():
    csv_bytes = b"tx_id,amount\nTX_1,1.0\n"
    with_csv = types.Content(
        role="user",
        parts=[
            types.Part(
                inline_data=types.Blob(mime_type="text/csv", data=csv_bytes)
            )
        ],
    )
    text_only = types.Content(role="user", parts=[types.Part(text="hello")])
    contents = [with_csv, text_only]
    assert _extract_latest_user_csv_bytes(contents) is None


def test_extract_from_last_user_when_csv_attached():
    csv_bytes = b"tx_id,amount\nTX_1,1.0\n"
    text_only = types.Content(role="user", parts=[types.Part(text="hello")])
    with_csv = types.Content(
        role="user",
        parts=[
            types.Part(text="analyse"),
            types.Part(
                inline_data=types.Blob(mime_type="text/csv", data=csv_bytes)
            ),
        ],
    )
    contents = [text_only, with_csv]
    assert _extract_latest_user_csv_bytes(contents) == csv_bytes


def test_persist_writes_file_and_sets_state(tmp_path, monkeypatch):
    monkeypatch.setenv("TMPDIR", str(tmp_path))
    csv_bytes = b"h1,h2\n1,2\n"
    llm_request = MagicMock()
    llm_request.contents = [
        types.Content(
            role="user",
            parts=[
                types.Part(
                    inline_data=types.Blob(mime_type="text/csv", data=csv_bytes)
                )
            ],
        )
    ]
    state: dict = {}
    ctx = MagicMock()
    ctx.state = state

    persist_playground_csv_before_model(ctx, llm_request)

    path = state.get(PLAYGROUND_CSV_STATE_KEY)
    assert path
    assert os.path.isfile(path)
    assert open(path, "rb").read() == csv_bytes
    os.unlink(path)


def test_persist_clears_state_when_no_inline():
    llm_request = MagicMock()
    llm_request.contents = [
        types.Content(role="user", parts=[types.Part(text="no file")])
    ]
    state = {PLAYGROUND_CSV_STATE_KEY: "/tmp/old.csv"}
    ctx = MagicMock()
    ctx.state = state

    persist_playground_csv_before_model(ctx, llm_request)

    assert state[PLAYGROUND_CSV_STATE_KEY] == ""
