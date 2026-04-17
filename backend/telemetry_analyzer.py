"""
telemetry_analyzer.py — Telemetry analysis for LMU Setup Engineer

Takes a Lap object from ld_reader and produces a structured summary dict
ready to be formatted into an AI prompt. Two-stage:

  1. base_summary()      — always-include statistics
  2. targeted_analysis() — additional data driven by the issue description

All values are in physical units (mm, kPa, °C, N, %, km/h, etc.).
"""

import numpy as np
from scipy.signal import find_peaks
from ld_reader import Lap


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resample(data, target_len):
    """Downsample or upsample a 1D array to target_len via linear interpolation."""
    if len(data) == target_len:
        return data
    x_old = np.linspace(0, 1, len(data))
    x_new = np.linspace(0, 1, target_len)
    return np.interp(x_new, x_old, data)


def _rolling_mean(data, window):
    """Simple rolling mean."""
    if window <= 1:
        return data
    kernel = np.ones(window) / window
    return np.convolve(data, kernel, mode='same')


def _pct_above(data, threshold):
    """Percentage of samples where data > threshold."""
    return float(np.mean(data > threshold) * 100)


def _pct_below(data, threshold):
    """Percentage of samples where data < threshold."""
    return float(np.mean(data < threshold) * 100)


# ---------------------------------------------------------------------------
# Corner detection
# ---------------------------------------------------------------------------

# Speed thresholds for corner classification
SPEED_LOW    = 100   # km/h — below this = low-speed corner
SPEED_HIGH   = 180   # km/h — above this = high-speed corner
# Minimum speed drop from local peak to count as a corner
CORNER_DROP_KMH = 20
# Minimum distance between corners (metres)
CORNER_MIN_SEPARATION_M = 200


def detect_corners(lap):
    """
    Detect corners from the speed trace and label them.

    Returns a list of dicts, one per detected corner, sorted by track position.
    """
    speed_ch    = lap.ch('Ground Speed')
    dist_ch     = lap.ch('Lap Distance')
    steer_ch    = lap.ch('Steering')
    throttle_ch = lap.ch('Throttle Pos')
    brake_ch    = lap.ch('Brake Pos')

    if speed_ch is None or dist_ch is None:
        return []

    n     = len(speed_ch.data)
    speed = speed_ch.data.copy()
    dist  = _resample(dist_ch.data, n)

    steer    = _resample(steer_ch.data, n)    if steer_ch    else np.zeros(n)
    throttle = _resample(throttle_ch.data, n) if throttle_ch else np.zeros(n)
    brake    = _resample(brake_ch.data, n)    if brake_ch    else np.zeros(n)

    smoothed = _rolling_mean(speed, window=5)
    valleys, _ = find_peaks(-smoothed, prominence=CORNER_DROP_KMH, distance=10)

    if len(valleys) == 0:
        return []

    corners = []
    prev_dist = -np.inf

    for idx in valleys:
        apex_dist = float(dist[idx])
        if apex_dist - prev_dist < CORNER_MIN_SEPARATION_M:
            continue
        prev_dist = apex_dist

        apex_speed = float(speed[idx])

        entry_start = max(0, idx - 50)
        entry_end   = max(0, idx - 5)
        exit_start  = min(n - 1, idx + 5)
        exit_end    = min(n, idx + 50)

        entry_speed = float(np.mean(speed[entry_start:entry_end])) if entry_end > entry_start else apex_speed
        exit_speed  = float(np.mean(speed[exit_start:exit_end]))   if exit_end > exit_start  else apex_speed

        direction = 'right' if steer[idx] > 0 else 'left'

        if apex_speed < SPEED_LOW:
            speed_class = 'low'
        elif apex_speed > SPEED_HIGH:
            speed_class = 'high'
        else:
            speed_class = 'medium'

        corners.append({
            'number':               len(corners) + 1,
            'position_m':           round(apex_dist, 0),
            'direction':            direction,
            'speed_class':          speed_class,
            'apex_speed_kmh':       round(apex_speed, 1),
            'entry_speed_kmh':      round(entry_speed, 1),
            'exit_speed_kmh':       round(exit_speed, 1),
            'throttle_at_apex_pct': round(float(throttle[idx]), 1),
            'brake_at_entry_pct':   round(float(np.max(brake[entry_start:idx])) if idx > entry_start else 0.0, 1),
            'steering_at_apex_deg': round(float(steer[idx]), 1),
        })

    return corners


# ---------------------------------------------------------------------------
# Tyre analysis
# ---------------------------------------------------------------------------

def _tyre_corner(lap, corner_code):
    """Return tyre stats for one corner (FL, FR, RL, RR) in physical units."""
    result = {}

    for zone in ['I', 'C', 'O']:
        ch = lap.ch(f'Tyre Rubber Temp {corner_code} {zone}')
        if ch and not ch.is_flat:
            result[f'temp_{zone.lower()}_C'] = round(float(np.mean(ch.data)), 1)

    carcass = lap.ch(f'Tyre Carcass Temp {corner_code}')
    if carcass and not carcass.is_flat:
        result['carcass_temp_C'] = round(float(np.mean(carcass.data)), 1)

    pressure = lap.ch(f'Tyre Pressure {corner_code}')
    if pressure and not pressure.is_flat:
        result['pressure_kPa'] = round(float(np.mean(pressure.data)), 1)

    wear = lap.ch(f'Tyre Wear {corner_code}')
    if wear and not wear.is_flat:
        result['wear_pct'] = round(float(np.mean(wear.data)), 3)

    return result


def tyre_summary(lap):
    """Return tyre data for all four corners in physical units."""
    result = {}
    for code in ['FL', 'FR', 'RL', 'RR']:
        data = _tyre_corner(lap, code)
        if data:
            result[code] = data

    # Front/rear and left/right temperature balance
    if all(k in result for k in ['FL', 'FR', 'RL', 'RR']):
        def _inner(code):
            return result[code].get('temp_i_C')

        vals = {k: _inner(k) for k in ['FL', 'FR', 'RL', 'RR']}
        if all(v is not None for v in vals.values()):
            front_avg = (vals['FL'] + vals['FR']) / 2
            rear_avg  = (vals['RL'] + vals['RR']) / 2
            left_avg  = (vals['FL'] + vals['RL']) / 2
            right_avg = (vals['FR'] + vals['RR']) / 2

            result['_balance'] = {
                'front_vs_rear_C': round(front_avg - rear_avg, 1),
                'left_vs_right_C': round(left_avg - right_avg, 1),
            }

    return result


# ---------------------------------------------------------------------------
# Suspension / damper analysis
# ---------------------------------------------------------------------------

def suspension_summary(lap):
    """Return suspension position stats (mm) and suspension forces (N)."""
    result = {}

    for code in ['FL', 'FR', 'RL', 'RR']:
        ch = lap.ch(f'Susp Pos {code}')
        if ch is None or ch.is_flat:
            continue
        d = ch.data
        entry = {
            'mean_mm': round(float(np.mean(d)), 2),
            'min_mm':  round(float(np.min(d)), 2),
            'max_mm':  round(float(np.max(d)), 2),
            'std_mm':  round(float(np.std(d)), 2),
        }
        force_ch = lap.ch(f'Susp Force {code}')
        if force_ch and not force_ch.is_flat:
            entry['force_mean_N'] = round(float(np.mean(force_ch.data)), 0)
            entry['force_max_N']  = round(float(np.max(force_ch.data)), 0)
        result[code] = entry

    for label, ch_name in [('front_3rd', 'Front 3rd Pos'), ('rear_3rd', 'Rear 3rd Pos')]:
        ch = lap.ch(ch_name)
        if ch and not ch.is_flat:
            d = ch.data
            result[label] = {
                'mean_mm': round(float(np.mean(d)), 2),
                'min_mm':  round(float(np.min(d)), 2),
                'max_mm':  round(float(np.max(d)), 2),
                'std_mm':  round(float(np.std(d)), 2),
            }

    return result


def packer_analysis(lap):
    """
    Detect likely packer contact by analysing suspension position channels.

    A channel is flagged when it spends significant time within
    PACKER_TOLERANCE_MM of its observed minimum — that minimum being the
    packer contact point.

    Note: 3rd spring packer contact on straights is normal and desirable.
    Corner packer contact (main suspension) is the problem to detect.

    Returns a dict per corner and per 3rd spring with:
      min_mm        — lowest observed position (mm)
      pct_at_packer — % of lap within PACKER_TOLERANCE_MM of min
      flag          — 'likely' / 'possible' / 'none'
    """
    PACKER_TOLERANCE_MM = 0.5  # within this of min = considered at packer
    FLAG_LIKELY         = 15.0
    FLAG_POSSIBLE       = 5.0

    channels = {
        'FL':        'Susp Pos FL',
        'FR':        'Susp Pos FR',
        'RL':        'Susp Pos RL',
        'RR':        'Susp Pos RR',
        'front_3rd': 'Front 3rd Pos',
        'rear_3rd':  'Rear 3rd Pos',
    }

    result = {}
    for label, ch_name in channels.items():
        ch = lap.ch(ch_name)
        if ch is None or ch.is_flat:
            continue
        d = ch.data
        min_val = float(d.min())
        pct = float(np.mean(d < (min_val + PACKER_TOLERANCE_MM)) * 100)
        if pct >= FLAG_LIKELY:
            flag = 'likely'
        elif pct >= FLAG_POSSIBLE:
            flag = 'possible'
        else:
            flag = 'none'
        result[label] = {
            'min_mm':        round(min_val, 2),
            'pct_at_packer': round(pct, 1),
            'flag':          flag,
        }

    return result


def ride_height_summary(lap):
    """
    Return ride height stats per corner in mm.

    Includes pct_below_25mm to detect bottoming out (25mm = scrape threshold).
    """
    BOTTOMING_MM = 25.0
    result = {}
    for code in ['FL', 'FR', 'RL', 'RR']:
        ch = lap.ch(f'Ride Height {code}')
        if ch and not ch.is_flat:
            d = ch.data
            result[code] = {
                'mean_mm':        round(float(np.mean(d)), 1),
                'min_mm':         round(float(np.min(d)), 1),
                'max_mm':         round(float(np.max(d)), 1),
                'pct_below_25mm': round(_pct_below(d, BOTTOMING_MM), 1),
            }
    return result


# ---------------------------------------------------------------------------
# Base summary
# ---------------------------------------------------------------------------

def base_summary(lap):
    """
    Produce the always-include telemetry summary for a lap.

    Returns a structured dict suitable for formatting into an AI prompt.
    """
    result = {}

    # --- Session metadata ---
    result['session'] = {
        'lap_number':  lap.lap_number,
        'lap_time_s':  round(lap.lap_time_s, 3) if lap.lap_time_s else None,
        'lap_time_str': _format_laptime(lap.lap_time_s),
    }

    # --- Overview ---
    overview = {}
    speed = lap.ch('Ground Speed')
    if speed:
        overview['max_speed_kmh'] = round(speed.stats()['max'], 1)
        overview['avg_speed_kmh'] = round(speed.stats()['mean'], 1)

    throttle = lap.ch('Throttle Pos')
    if throttle:
        overview['throttle_mean_pct'] = round(throttle.stats()['mean'], 1)
        overview['throttle_full_pct'] = round(_pct_above(throttle.data, 95), 1)
        overview['throttle_lift_pct'] = round(_pct_below(throttle.data, 5), 1)

    brake = lap.ch('Brake Pos')
    if brake:
        overview['brake_mean_pct']   = round(brake.stats()['mean'], 1)
        overview['brake_active_pct'] = round(_pct_above(brake.data, 5), 1)

    rpm = lap.ch('Engine RPM')
    if rpm:
        overview['engine_rpm_mean'] = round(rpm.stats()['mean'], 0)
        overview['engine_rpm_max']  = round(rpm.stats()['max'], 0)

    bias = lap.ch('Brake Bias Rear')
    if bias:
        overview['brake_bias_rear_pct'] = round(bias.stats()['mean'], 1)

    result['overview'] = overview

    # --- Corners ---
    result['corners'] = detect_corners(lap)

    # --- Tyres ---
    result['tyres'] = tyre_summary(lap)

    # --- Suspension / dampers ---
    result['suspension'] = suspension_summary(lap)

    # --- Packer contact analysis ---
    result['packer_analysis'] = packer_analysis(lap)

    # --- Ride heights ---
    result['ride_heights'] = ride_height_summary(lap)

    # --- Body attitude ---
    body = {}
    for ch_name, key in [('Body Pitch', 'pitch_rad'), ('Body Roll', 'roll_rad')]:
        ch = lap.ch(ch_name)
        if ch and not ch.is_flat:
            body[key] = {
                'mean': round(float(np.mean(ch.data)), 4),
                'min':  round(float(np.min(ch.data)), 4),
                'max':  round(float(np.max(ch.data)), 4),
            }
    if body:
        result['body_attitude'] = body

    # --- Camber ---
    camber = {}
    for code in ['FL', 'FR', 'RL', 'RR']:
        ch = lap.ch(f'Camber {code}')
        if ch and not ch.is_flat:
            d_deg = np.degrees(ch.data)
            camber[code] = {
                'mean_deg': round(float(np.mean(d_deg)), 2),
                'min_deg':  round(float(np.min(d_deg)), 2),
                'max_deg':  round(float(np.max(d_deg)), 2),
            }
    if camber:
        result['camber'] = camber

    # --- Steering ---
    steer = lap.ch('Steering')
    if steer:
        result['steering'] = {
            'max_left_deg':  round(abs(float(steer.data.min())), 1),
            'max_right_deg': round(abs(float(steer.data.max())), 1),
        }

    return result


def _format_laptime(seconds):
    if seconds is None or seconds <= 0:
        return 'unknown'
    m = int(seconds // 60)
    s = seconds % 60
    return f'{m}:{s:06.3f}'


# ---------------------------------------------------------------------------
# Targeted analysis
# ---------------------------------------------------------------------------

KEYWORDS = {
    'oversteer':  ['oversteer', 'overst', 'loose', 'rear steps out', 'rear slides', 'snap oversteer'],
    'understeer': ['understeer', 'underst', 'push', 'washes wide', 'front slides', 'ploughs'],
    'braking':    ['braking', 'brake', 'lockup', 'lock up', 'lock-up', 'trail brake', 'stopping'],
    'traction':   ['traction', 'wheelspin', 'wheel spin', 'power oversteer', 'throttle exit'],
    'bumps':      ['bump', 'kerb', 'kerbing', 'curb', 'curbing', 'rough', 'bouncing'],
    'aero':       ['aero', 'downforce', 'high speed', 'high-speed', 'wing', 'straight line'],
    'hybrid':     [r'\bhybrid\b', r'\bers\b', r'\bdeploy\b', r'\bharvest\b',
                   r'\belectric\b', r'\bmotor power\b'],
}


def _detect_keywords(description):
    """Return a set of category names detected in the issue description."""
    import re
    text = description.lower()
    found = set()
    for category, patterns in KEYWORDS.items():
        for p in patterns:
            if p.startswith(r'\b') or '\\b' in p:
                if re.search(p, text):
                    found.add(category)
                    break
            elif p in text:
                found.add(category)
                break
    return found


def _detect_corner_number(description):
    """Try to extract a corner number from the description."""
    import re
    patterns = [r'\bturn\s*(\d+)\b', r'\bcorner\s*(\d+)\b', r'\bt(\d+)\b']
    text = description.lower()
    for p in patterns:
        m = re.search(p, text)
        if m:
            return int(m.group(1))
    return None


def _detect_speed_class(description):
    """Detect if description refers to a specific corner speed class."""
    text = description.lower()
    if any(p in text for p in ['slow corner', 'low speed', 'low-speed', 'hairpin', 'chicane']):
        return 'low'
    if any(p in text for p in ['high speed', 'high-speed', 'fast corner']):
        return 'high'
    if any(p in text for p in ['medium speed', 'medium-speed']):
        return 'medium'
    return None


def _lockup_detection(lap, corners):
    """
    Detect likely wheel lockups during hard braking events.

    Compares all four Wheel Rot Speed channels during braking zones.
    A wheel whose mean is significantly lower than the other three is suspect.

    Returns a list of events with position, nearest corner, and suspected wheels.
    """
    brake_ch = lap.ch('Brake Pos')
    speed_ch = lap.ch('Ground Speed')
    dist_ch  = lap.ch('Lap Distance')

    wheel_chs = {code: lap.ch(f'Wheel Rot Speed {code}') for code in ['FL', 'FR', 'RL', 'RR']}
    if not all([brake_ch, speed_ch, dist_ch]) or not all(wheel_chs.values()):
        return []

    n      = len(speed_ch.data)
    brake  = _resample(brake_ch.data, n)
    dist   = _resample(dist_ch.data, n)
    wheels = {code: _resample(ch.data, n) for code, ch in wheel_chs.items() if not ch.is_flat}

    if len(wheels) < 4:
        return []

    BRAKE_THRESHOLD  = 20.0  # % brake application to count as hard braking
    MIN_ZONE_SAMPLES = 10    # ignore very brief applications
    LOCKUP_RATIO     = 0.60  # wheel below 60% of others mean = suspect lockup
    MIN_SPEED_UNITS  = 1.0   # others must be above this to flag (avoids stopped-car noise)

    events = []
    in_brake   = False
    zone_start = 0

    for i in range(n):
        if brake[i] > BRAKE_THRESHOLD and not in_brake:
            in_brake   = True
            zone_start = i
        elif brake[i] <= BRAKE_THRESHOLD and in_brake:
            in_brake = False
            zone_end = i

            if zone_end - zone_start < MIN_ZONE_SAMPLES:
                continue

            means = {code: float(np.mean(wheels[code][zone_start:zone_end]))
                     for code in wheels}

            suspected = []
            for code, val in means.items():
                others_mean = np.mean([v for k, v in means.items() if k != code])
                if others_mean > MIN_SPEED_UNITS and val < others_mean * LOCKUP_RATIO:
                    suspected.append(code)

            if suspected:
                pos = float(dist[zone_start])
                nearest = None
                if corners:
                    dists = [abs(c['position_m'] - pos) for c in corners]
                    idx = int(np.argmin(dists))
                    if dists[idx] < 300:
                        nearest = corners[idx]['number']

                events.append({
                    'position_m':       round(pos, 0),
                    'corner':           nearest,
                    'suspected_wheels': suspected,
                    'wheel_means':      {k: round(v, 3) for k, v in means.items()},
                })

    return events


def targeted_analysis(lap, description, corners, base):
    """
    Extract additional targeted data based on the issue description.

    Args:
        lap:         Lap object
        description: raw driver description string
        corners:     corner list from base_summary
        base:        the base_summary dict (to avoid re-computing)

    Returns:
        dict of targeted data to merge into the prompt
    """
    categories  = _detect_keywords(description)
    corner_num  = _detect_corner_number(description)
    speed_class = _detect_speed_class(description)

    result = {
        'detected_categories': list(categories),
        'corner_filter':       None,
        'data':                {}
    }

    relevant_corners = corners
    if corner_num is not None:
        relevant_corners = [c for c in corners if c['number'] == corner_num]
        result['corner_filter'] = f'Turn {corner_num}'
    elif speed_class is not None:
        relevant_corners = [c for c in corners if c['speed_class'] == speed_class]
        result['corner_filter'] = f'{speed_class}-speed corners'

    result['relevant_corners'] = relevant_corners

    # --- Oversteer / understeer: wheel speed differential ---
    if 'oversteer' in categories or 'understeer' in categories:
        wheel_data = {}
        for code in ['FL', 'FR', 'RL', 'RR']:
            ch = lap.ch(f'Wheel Rot Speed {code}')
            if ch and not ch.is_flat:
                wheel_data[code] = {
                    'mean': round(ch.stats()['mean'], 2),
                    'std':  round(ch.stats()['std'], 2),
                }
        if wheel_data:
            result['data']['wheel_rot_speeds'] = wheel_data

    # --- Braking: per-wheel brake pressure, temps, and lockup detection ---
    if 'braking' in categories:
        brake_data = {}
        for code in ['FL', 'FR', 'RL', 'RR']:
            pressure = lap.ch(f'Brake Pressure {code}')
            temp     = lap.ch(f'Brake Temp {code}')
            brake_data[code] = {}
            if pressure and not pressure.is_flat:
                brake_data[code]['pressure_pct'] = {
                    'mean': round(pressure.stats()['mean'], 1),
                    'max':  round(pressure.stats()['max'], 1),
                }
            if temp and not temp.is_flat:
                brake_data[code]['temp_C'] = {
                    'mean': round(temp.stats()['mean'], 0),
                    'max':  round(temp.stats()['max'], 0),
                }
        result['data']['brake_detail'] = brake_data

        lockup = _lockup_detection(lap, relevant_corners)
        if lockup:
            result['data']['lockup_analysis'] = lockup

    # --- Traction: wheel rot speeds + longitudinal/lateral patch velocities ---
    if 'traction' in categories:
        wheel_data = {}
        for code in ['FL', 'FR', 'RL', 'RR']:
            ch = lap.ch(f'Wheel Rot Speed {code}')
            if ch and not ch.is_flat:
                wheel_data[code] = {
                    'mean': round(ch.stats()['mean'], 2),
                    'std':  round(ch.stats()['std'], 2),
                }
        if wheel_data:
            result['data']['wheel_rot_speeds'] = wheel_data

        patch_data = {}
        for code in ['FL', 'FR', 'RL', 'RR']:
            long_ch = lap.ch(f'Long Patch Vel {code}')
            lat_ch  = lap.ch(f'Lat Patch Vel {code}')
            patch_data[code] = {}
            if long_ch and not long_ch.is_flat:
                patch_data[code]['long_slip'] = {
                    'mean': round(long_ch.stats()['mean'], 3),
                    'max':  round(long_ch.stats()['max'], 3),
                }
            if lat_ch and not lat_ch.is_flat:
                patch_data[code]['lat_slip'] = {
                    'mean': round(lat_ch.stats()['mean'], 3),
                    'max':  round(lat_ch.stats()['max'], 3),
                }
        if any(patch_data[k] for k in patch_data):
            result['data']['patch_velocities'] = patch_data

    # --- Bumps: suspension force and vertical tyre deflection ---
    if 'bumps' in categories:
        bump_data = {}
        for code in ['FL', 'FR', 'RL', 'RR']:
            force = lap.ch(f'Susp Force {code}')
            defl  = lap.ch(f'Vertical Tyre Deflection {code}')
            bump_data[code] = {}
            if force and not force.is_flat:
                bump_data[code]['susp_force_N'] = {
                    'mean': round(force.stats()['mean'], 0),
                    'max':  round(force.stats()['max'], 0),
                }
            if defl and not defl.is_flat:
                bump_data[code]['tyre_deflection'] = {
                    'mean': round(defl.stats()['mean'], 3),
                    'max':  round(defl.stats()['max'], 3),
                }
        result['data']['bump_detail'] = bump_data

    # --- Hybrid: motor data if non-flat ---
    if 'hybrid' in categories:
        hybrid_data = {}
        for ch_name in ['Motor RPM', 'Motor Torque', 'Battery Charge Level']:
            ch = lap.ch(ch_name)
            if ch and not ch.is_flat:
                hybrid_data[ch_name] = ch.stats()
        result['data']['hybrid'] = hybrid_data

    return result


# ---------------------------------------------------------------------------
# Main entry point
# ---------------------------------------------------------------------------

def analyze(lap, issue_description=''):
    """
    Full analysis of a lap for a given issue description.

    Returns a dict containing base_summary + targeted data,
    ready to be passed to prompt_builder.
    """
    summary  = base_summary(lap)
    corners  = summary.get('corners', [])
    targeted = targeted_analysis(lap, issue_description, corners, summary)
    summary['targeted'] = targeted
    return summary


# ---------------------------------------------------------------------------
# Quick test
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    import sys, json
    sys.path.insert(0, '.')
    import ld_reader

    path = sys.argv[1] if len(sys.argv) > 1 else (
        '../2026-04-02 - 18-44-51 - Paul Ricard - 1A - P1.ld'
    )

    print(f'Parsing: {path}')
    ld_file = ld_reader.parse(path)
    lap = ld_file.best_lap
    print(f'Analysing: {lap}\n')

    result = analyze(lap, issue_description='I have understeer in slow corners on entry')
    print(json.dumps(result, indent=2, default=str))
