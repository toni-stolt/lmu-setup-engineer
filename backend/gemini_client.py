"""
gemini_client.py — Sends prompts to Google Gemini and returns responses.

Uses the google-genai SDK (replaces deprecated google-generativeai).
API key is read from the GEMINI_API_KEY environment variable (set in .env).

Public functions:
  get_setup_advice(user_prompt)              — single-turn (legacy, preserved for compat)
  create_chat_and_send(user_prompt)          — first turn of a multi-turn session
  send_followup(history, followup_prompt)   — subsequent turns using stored history
"""

import os
from google import genai
from google.genai import types
from prompt_builder import SYSTEM_PROMPT


# ---------------------------------------------------------------------------
# Client initialisation
# ---------------------------------------------------------------------------

_client = None


def _get_client():
    global _client
    if _client is None:
        api_key = os.environ.get('GEMINI_API_KEY')
        if not api_key:
            raise RuntimeError('GEMINI_API_KEY environment variable is not set.')
        _client = genai.Client(api_key=api_key)
    return _client


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MODEL = 'gemini-2.5-flash'

_CONFIG = types.GenerateContentConfig(
    system_instruction=SYSTEM_PROMPT,
    temperature=0.4,
    max_output_tokens=8192,
)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _extract_text(response) -> str:
    """Extract the text payload from a Gemini response.

    Handles thinking models where response.text may be None (thought tokens
    are filtered out by checking the `thought` attribute on each Part).
    """
    if response.text is not None:
        return response.text

    candidates = response.candidates or []
    if candidates and candidates[0].content and candidates[0].content.parts:
        parts = candidates[0].content.parts
        text = ''.join(p.text for p in parts if p.text and not getattr(p, 'thought', False))
        if text:
            return text

    raise RuntimeError('Gemini returned an empty response.')


def _build_contents(history: list) -> list:
    """Convert serialised history dicts to Content objects for the API.

    History format:
      [{'role': 'user',  'parts': [{'text': '...'}]},
       {'role': 'model', 'parts': [{'text': '...'}]}, ...]
    """
    result = []
    for item in history:
        parts = [types.Part(text=p['text']) for p in item['parts'] if p.get('text')]
        result.append(types.Content(role=item['role'], parts=parts))
    return result


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def get_setup_advice(user_prompt: str) -> str:
    """Single-turn analysis — preserved for backward compatibility.

    Args:
        user_prompt: formatted prompt from prompt_builder.build_user_prompt()

    Returns:
        str — Gemini's response text

    Raises:
        RuntimeError if the API call fails
    """
    client = _get_client()

    try:
        response = client.models.generate_content(
            model=MODEL,
            contents=user_prompt,
            config=_CONFIG,
        )
        return _extract_text(response)

    except Exception as e:
        raise RuntimeError(f'Gemini API error: {e}') from e


def create_chat_and_send(user_prompt: str) -> tuple:
    """Start a new multi-turn conversation and send the first message.

    Args:
        user_prompt: formatted prompt from prompt_builder.build_user_prompt()

    Returns:
        (response_text: str, history: list)
        where history is a JSON-serialisable list of message dicts.

    Raises:
        RuntimeError if the API call fails
    """
    client = _get_client()

    try:
        response = client.models.generate_content(
            model=MODEL,
            contents=user_prompt,
            config=_CONFIG,
        )
        text = _extract_text(response)

        # Build the history manually from this first turn
        history = [
            {'role': 'user',  'parts': [{'text': user_prompt}]},
            {'role': 'model', 'parts': [{'text': text}]},
        ]
        return text, history

    except Exception as e:
        raise RuntimeError(f'Gemini API error: {e}') from e


def send_followup(history: list, followup_prompt: str) -> tuple:
    """Continue an existing conversation using a stored history list.

    Args:
        history:          list of dicts from a previous call (create_chat_and_send
                          or send_followup)
        followup_prompt:  the new message to send

    Returns:
        (response_text: str, updated_history: list)

    Raises:
        RuntimeError if the API call fails
    """
    client = _get_client()

    # Build full contents: all previous messages + the new user message
    contents = _build_contents(history) + [
        types.Content(
            role='user',
            parts=[types.Part(text=followup_prompt)],
        )
    ]

    try:
        response = client.models.generate_content(
            model=MODEL,
            contents=contents,
            config=_CONFIG,
        )
        text = _extract_text(response)

        # Extend history with the new turn
        updated_history = history + [
            {'role': 'user',  'parts': [{'text': followup_prompt}]},
            {'role': 'model', 'parts': [{'text': text}]},
        ]
        return text, updated_history

    except Exception as e:
        raise RuntimeError(f'Gemini API error: {e}') from e


# ---------------------------------------------------------------------------
# Quick test — needs GEMINI_API_KEY in environment
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    import sys
    sys.path.insert(0, '.')
    from dotenv import load_dotenv
    load_dotenv()

    import ld_reader, telemetry_analyzer
    from prompt_builder import build_user_prompt

    path = '../../2026-01-20 - 17-54-41 - Circuit de la Sarthe - P1 kierros.ld'
    ld_file = ld_reader.parse(path)
    lap = ld_file.best_lap

    description = 'I have understeer in slow corners on entry'
    analysis = telemetry_analyzer.analyze(lap, description)

    meta = {
        'driver':   ld_file.driver,
        'vehicle':  ld_file.vehicle,
        'venue':    ld_file.venue,
        'datetime': ld_file.datetime,
    }

    prompt = build_user_prompt(analysis, description, meta)
    print('Sending first turn to Gemini...\n')

    text, history = create_chat_and_send(prompt)
    print('Turn 1 response:')
    print(text)
    print(f'\nHistory has {len(history)} messages.')
