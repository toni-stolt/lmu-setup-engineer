"""
app.py — Flask backend for LMU Setup Engineer

Routes:
  POST /analyze  — accepts a .ld file + driver description, returns AI advice
  GET  /health   — simple health check
"""

import os
import tempfile
from flask import Flask, request, jsonify
from flask_cors import CORS
from dotenv import load_dotenv
from collections import defaultdict
from datetime import date

import ld_reader
import telemetry_analyzer
from prompt_builder import build_user_prompt
from gemini_client import get_setup_advice


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

    # --- Validate inputs ---
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

    track_name = request.form.get('track_name', '').strip()
    car_class  = request.form.get('car_class', '').strip()
    lap_index  = request.form.get('lap_index')

    # --- Save to temp file and parse ---
    try:
        with tempfile.NamedTemporaryFile(suffix='.ld', delete=False) as tmp:
            file.save(tmp.name)
            tmp_path = tmp.name

        ld_file = ld_reader.parse(tmp_path)

    except Exception as e:
        return jsonify({'error': f'Could not read .ld file: {e}'}), 400

    finally:
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

    # --- Build prompt and call AI ---
    meta = {
        'driver':    ld_file.driver,
        'vehicle':   ld_file.vehicle,
        'venue':     track_name if track_name else ld_file.venue,
        'datetime':  ld_file.datetime,
        'car_class': car_class,
    }

    try:
        user_prompt = build_user_prompt(analysis, description, meta)
        advice = get_setup_advice(user_prompt)
    except Exception as e:
        return jsonify({'error': f'AI request failed: {e}'}), 502

    # --- Build response ---
    laps_info = [
        {
            'index': i,
            'lap_number': lp.lap_number,
            'lap_time_str': _fmt_laptime(lp.lap_time_s),
        }
        for i, lp in enumerate(ld_file.laps)
    ]

    return jsonify({
        'advice': advice,
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
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)
