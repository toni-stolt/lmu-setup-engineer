"""
app.py — Flask backend for LMU Setup Engineer

Routes:
  POST /analyze  — accepts a .ld file + driver description, returns AI advice.
                   Supports multi-turn sessions via optional session_id / history fields.
  GET  /health   — simple health check
"""

import json
import os
import tempfile
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
from collections import defaultdict
from datetime import date

import ld_reader
import telemetry_analyzer
import session_store
from prompt_builder import build_user_prompt, build_followup_prompt
from gemini_client import create_chat_and_send, send_followup, get_setup_advice


def _fmt_laptime(seconds):
    if seconds is None:
        return 'unknown'
    m = int(seconds) // 60
    s = seconds - m * 60
    return f'{m}:{s:06.3f}'

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '.env'))

app = Flask(__name__)
CORS(app)

# ---------------------------------------------------------------------------
# IP-based rate limiting — 100 requests per IP per day
# ---------------------------------------------------------------------------

_request_counts = defaultdict(lambda: {'date': None, 'count': 0})
DAILY_LIMIT = 100


def _check_rate_limit(ip: str) -> bool:
    """Returns True if the request is allowed, False if limit exceeded."""
    today = date.today().isoformat()
    record = _request_counts[ip]
    if record['date'] != today:
        record['date'] = today
        record['count'] = 0
    if record['count'] >= DAILY_LIMIT:
        return False
    record['count'] += 1
    return True


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route('/health', methods=['GET'])
def health():
    return jsonify({'status': 'ok'})


@app.route('/analyze', methods=['POST'])
def analyze():
    ip = request.headers.get('X-Forwarded-For', request.remote_addr).split(',')[0].strip()

    if not _check_rate_limit(ip):
        return jsonify({'error': 'Daily request limit reached. Try again tomorrow.'}), 429

    # --- Validate required inputs ---
    if 'file' not in request.files:
        return jsonify({'error': 'No file uploaded.'}), 400

    file = request.files['file']
    if not file.filename.lower().endswith('.ld'):
        return jsonify({'error': 'Only .ld files are supported.'}), 400

    description = request.form.get('description', '').strip()
    if not description:
        return jsonify({'error': 'Please describe your handling issue.'}), 400
    if len(description) > 1000:
        return jsonify({'error': 'Description too long (max 1000 characters).'}), 400

    # --- Optional fields ---
    track_name          = request.form.get('track_name', '').strip()
    lap_index           = request.form.get('lap_index')
    car_class           = request.form.get('car_class', '').strip()       # GT3 / LMP2 / Hypercar
    issue_category      = request.form.get('issue_category', '').strip()  # Understeer / etc.
    session_id_in       = request.form.get('session_id', '').strip()      # follow-up: existing session
    changes_description = request.form.get('changes_description', '').strip()  # follow-up: what changed

    # history: JSON string — client-side backup in case server session expired
    history_json = request.form.get('history', '')
    client_history = None
    if history_json:
        try:
            client_history = json.loads(history_json)
        except (json.JSONDecodeError, ValueError):
            pass

    is_followup = bool(session_id_in)

    # --- Save to temp file and parse ---
    tmp_path = None
    try:
        with tempfile.NamedTemporaryFile(suffix='.ld', delete=False) as tmp:
            file.save(tmp.name)
            tmp_path = tmp.name

        ld_file = ld_reader.parse(tmp_path)

    except Exception as e:
        return jsonify({'error': f'Could not read .ld file: {e}'}), 400

    finally:
        if tmp_path:
            try:
                os.unlink(tmp_path)
            except Exception:
                pass

    if not ld_file.laps:
        return jsonify({'error': 'No laps found in the file.'}), 400

    # --- Select lap ---
    if lap_index is not None:
        try:
            idx = int(lap_index)
            if idx < 0 or idx >= len(ld_file.laps):
                return jsonify({'error': f'Lap index {idx} out of range (file has {len(ld_file.laps)} laps).'}), 400
            lap = ld_file.laps[idx]
        except ValueError:
            return jsonify({'error': 'lap_index must be an integer.'}), 400
    else:
        lap = ld_file.best_lap

    # --- Analyse telemetry ---
    try:
        analysis = telemetry_analyzer.analyze(lap, description)
    except Exception as e:
        return jsonify({'error': f'Telemetry analysis failed: {e}'}), 500

    # --- Build metadata ---
    meta = {
        'driver':    ld_file.driver,
        'vehicle':   ld_file.vehicle,
        'venue':     track_name if track_name else ld_file.venue,
        'datetime':  ld_file.datetime,
        'car_class': car_class,
    }

    # --- Call AI ---
    try:
        if not is_followup:
            # ── First turn: new analysis ──────────────────────────────────
            user_prompt = build_user_prompt(analysis, description, meta)
            advice, history = create_chat_and_send(user_prompt)
            new_session_id = session_store.new_session(history)
            turn_number = 1

        else:
            # ── Follow-up turn ────────────────────────────────────────────
            if not changes_description:
                return jsonify({'error': 'Please describe what setup changes you made.'}), 400

            # Prefer server-side session; fall back to client-supplied history
            history = session_store.get_history(session_id_in) or client_history
            if not history:
                return jsonify({
                    'error': 'Session not found or expired. Please start a new analysis.'
                }), 400

            followup_prompt = build_followup_prompt(analysis, changes_description, meta)
            advice, updated_history = send_followup(history, followup_prompt)

            # Persist updated history; create new session entry if old one expired
            if session_store.get_history(session_id_in) is not None:
                session_store.update_history(session_id_in, updated_history)
                new_session_id = session_id_in
            else:
                new_session_id = session_store.new_session(updated_history)

            history = updated_history
            # turn_number = number of user messages in history
            turn_number = sum(1 for h in history if h['role'] == 'user')

    except Exception as e:
        return jsonify({'error': f'AI request failed: {e}'}), 502

    # --- Build response ---
    laps_info = [
        {
            'index':        i,
            'lap_number':   lp.lap_number,
            'lap_time_str': _fmt_laptime(lp.lap_time_s),
        }
        for i, lp in enumerate(ld_file.laps)
    ]

    return jsonify({
        'advice':     advice,
        'session_id': new_session_id,
        'history':    history,
        'turn_number': turn_number,
        'session': {
            'driver':   meta['driver'],
            'vehicle':  meta['vehicle'],
            'venue':    meta['venue'],
            'datetime': meta['datetime'],
        },
        'lap': {
            'index':        ld_file.laps.index(lap),
            'lap_number':   lap.lap_number,
            'lap_time_str': _fmt_laptime(lap.lap_time_s),
        },
        'all_laps': laps_info,
    })


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5002))
    app.run(host='0.0.0.0', port=port, debug=False)
