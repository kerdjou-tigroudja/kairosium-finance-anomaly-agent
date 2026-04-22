"""Matérialise un CSV joint (inline_data) du Dev UI en fichier local pour l'ingestion."""

from __future__ import annotations

import logging
import os
import tempfile
from typing import TYPE_CHECKING

from google.genai import types

if TYPE_CHECKING:
    from google.adk.agents.context import Context
    from google.adk.models.llm_request import LlmRequest

logger = logging.getLogger(__name__)

# Clé de session : chemin local absolu ou chaîne vide (substitution {playground_csv_path})
PLAYGROUND_CSV_STATE_KEY = "playground_csv_path"


def _is_csv_mime(mime: str | None) -> bool:
    if not mime:
        return False
    m = mime.lower()
    return "csv" in m or m in ("text/comma-separated-values",)


def _extract_latest_user_csv_bytes(contents: list[types.Content]) -> bytes | None:
    """CSV inline uniquement dans le **dernier** tour utilisateur (évite un vieux joint)."""
    last_user: types.Content | None = None
    for content in reversed(contents):
        if content.role == "user":
            last_user = content
            break
    if last_user is None:
        return None
    for part in last_user.parts or []:
        blob = part.inline_data
        if blob is None or blob.data is None:
            continue
        if not _is_csv_mime(blob.mime_type):
            continue
        data = blob.data
        if isinstance(data, str):
            return data.encode("utf-8")
        return bytes(data)
    return None


def _unlink_silent(path: str) -> None:
    try:
        os.unlink(path)
    except OSError:
        pass


def persist_playground_csv_before_model(
    callback_context: Context,
    llm_request: LlmRequest,
) -> None:
    """Si la requête contient un CSV inline (playground), l'écrit sous /tmp et remplit le state."""
    state = callback_context.state
    prev = state.get(PLAYGROUND_CSV_STATE_KEY)

    raw = _extract_latest_user_csv_bytes(list(llm_request.contents or []))
    if not raw:
        state[PLAYGROUND_CSV_STATE_KEY] = ""
        return

    tmp_dir = tempfile.gettempdir()
    fd, path = tempfile.mkstemp(prefix="adk_playground_", suffix=".csv", dir=tmp_dir)
    try:
        os.write(fd, raw)
    finally:
        os.close(fd)

    if (
        isinstance(prev, str)
        and prev
        and prev != path
        and prev.startswith(tmp_dir)
        and "adk_playground_" in prev
    ):
        _unlink_silent(prev)

    state[PLAYGROUND_CSV_STATE_KEY] = path
    logger.info("CSV inline matérialisé pour ingestion : %s (%d octets)", path, len(raw))
