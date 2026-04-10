"""
gemini_client.py — Sends the prompt to Google Gemini and returns the response

Uses the google-genai SDK (replaces deprecated google-generativeai).
API key is read from the GEMINI_API_KEY environment variable (set in .env).
"""

import os
from google import genai
from google.genai import types
from prompt_builder import SYSTEM_PROMPT


# ---------------------------------------------------------------------------
# Initialise the client on first use
# ---------------------------------------------------------------------------

_client = None


def _get_client():
    global _client
    if _client is None:
        api_key = os.environ.get('GEMINI_API_KEY')
        if not api_key:
            raise RuntimeError('GEMINI_API_KEY environment variable is not set.')
        _client = genai.Client(
            api_key=api_key,
            http_options=types.HttpOptions(api_version='v1'),
        )
    return _client


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

MODEL = 'gemini-1.5-flash'


def get_setup_advice(user_prompt: str) -> str:
    """
    Send the user prompt to Gemini and return the text response.

    Args:
        user_prompt: the formatted prompt from prompt_builder.build_user_prompt()

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
            config=types.GenerateContentConfig(
                system_instruction=SYSTEM_PROMPT,
                temperature=0.4,
                max_output_tokens=2048,
            ),
        )

        # Gemini 2.5+ thinking models: response.text is None when the model
        # includes thinking tokens. Collect only the non-thought parts.
        if response.text is not None:
            return response.text

        candidates = response.candidates or []
        if candidates and candidates[0].content and candidates[0].content.parts:
            parts = candidates[0].content.parts
            text = ''.join(p.text for p in parts if p.text and not p.thought)
            if text:
                return text

        raise RuntimeError('Gemini returned an empty response.')

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
    print('Sending to Gemini...\n')

    advice = get_setup_advice(prompt)
    print(advice)
