"""
session_store.py — In-memory conversation session store.

Each session holds the conversation history (list of message dicts) for the
multi-turn analysis workflow.  Sessions expire after 1 hour; hard cap at 200.
"""

import threading
import time
import uuid
from typing import Optional

SESSION_TTL = 3600   # seconds — 1 hour
SESSION_CAP = 200    # maximum concurrent sessions


_store: dict = {}
_lock = threading.Lock()


def _purge_expired() -> None:
    """Remove expired sessions. Must be called while holding _lock."""
    now = time.time()
    expired = [k for k, v in _store.items() if now - v['ts'] > SESSION_TTL]
    for k in expired:
        del _store[k]


def new_session(history: list) -> str:
    """Create a new session with the given history. Returns the session ID."""
    session_id = str(uuid.uuid4())
    with _lock:
        _purge_expired()
        if len(_store) >= SESSION_CAP:
            # Evict the oldest session to stay under the cap
            oldest = min(_store, key=lambda k: _store[k]['ts'])
            del _store[oldest]
        _store[session_id] = {'history': history, 'ts': time.time()}
    return session_id


def get_history(session_id: str) -> Optional[list]:
    """Return the history for a session ID, or None if expired / not found."""
    with _lock:
        entry = _store.get(session_id)
        if entry is None:
            return None
        if time.time() - entry['ts'] > SESSION_TTL:
            del _store[session_id]
            return None
        return entry['history']


def update_history(session_id: str, history: list) -> None:
    """Replace the history for an existing session and reset its TTL."""
    with _lock:
        if session_id in _store:
            _store[session_id]['history'] = history
            _store[session_id]['ts'] = time.time()
