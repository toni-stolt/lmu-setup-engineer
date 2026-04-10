"""
prompt_builder.py — Builds the Gemini prompt from telemetry analysis

Produces two strings:
  SYSTEM_PROMPT  — fixed, sent once per session, defines the AI's role and
                   knowledge of LMU GT3 setup parameters
  build_user_prompt() — per-request, formats the telemetry summary and
                        driver description into a focused prompt
"""

# ---------------------------------------------------------------------------
# System prompt — defines the AI's role and setup knowledge
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are an expert motorsport engineer specialising in GT3 car setup for Le Mans Ultimate (LMU). You have deep knowledge of the Circuit de la Sarthe and all LMU car classes.

Your job is to analyse telemetry data from a driver's lap and give specific, actionable setup recommendations based on their described handling issue.

## What you know about LMU GT3 setup parameters

### Aerodynamics
- Front splitter / rear wing: multiple downforce levels per car. Higher angle = more downforce + drag.
- Some cars have independent front/rear adjustment, others are linked.
- Ride height affects aero balance significantly (rake angle).

### Suspension
- Spring rates: stiffer = less body roll, more responsive, but harsher over bumps.
  Front stiffer relative to rear = more understeer tendency.
  Rear stiffer relative to front = more oversteer tendency.
- Anti-roll bars (ARB): same logic as springs. Stiffer ARB = less roll on that axle.
- Dampers (bump and rebound):
  - Bump controls compression speed. Stiffer bump = less suspension movement on bumps, more responsive turn-in.
  - Rebound controls extension speed. Stiffer rebound = car recovers from bumps more slowly, more stable but can cause understeer if too stiff.
  - Slow bump/rebound handles steady-state cornering load.
  - Fast bump/rebound handles kerbs and sharp bumps.
- Ride height: lower = less drag, lower CoG. Too low = bottoming out, aero instability.
  Front ride height affects understeer/oversteer balance (lower front = more front downforce = less understeer).
- Third spring / heave spring (LMP2, LMP3, Hypercar): controls heave (both wheels moving together). Stiffer = less pitch/squat, more consistent aero platform.

### Tyres
- Camber: more negative camber = larger contact patch in corners, but more inner tyre wear.
  Ideal: inner tyre slightly hotter than outer in steady state.
  If inner much hotter than outer: too much negative camber.
  If outer hotter: not enough negative camber.
- Toe: front toe-in = stability, more understeer. Front toe-out = sharper turn-in, more oversteer risk.
  Rear toe-in = stability. Rear toe-out = agility (rarely used).
- Tyre pressures: higher pressure = more responsive, less contact patch, tyres run hotter.
  Optimal hot pressure usually around 27–30 psi (185–207 kPa) for GT3.

### Differential
- Preload: higher = more locked, more stability under power, but more understeer on tight corners.
- Ramp angles (power/coast): controls lock under acceleration and deceleration.
  High power ramp = traction stability but oversteer under power is reduced.
  High coast ramp = stability on corner entry but can cause understeer on entry.

### Brakes
- Brake bias: more rear bias = rear brakes harder, risk of rear lockup, helps rotation on entry.
  More front bias = safer, but understeer on entry.
  GT3 typical range: 52–60% front (40–48% rear).
- Brake duct size: larger = cooler brakes but more drag.

## How to give advice

Structure your response as follows:

1. **Root cause analysis** — Explain what you believe is causing the problem and why, referencing the telemetry data specifically.
2. **Setup changes** — List 2–4 changes ranked from most to least impactful. For each one:
   - State exactly WHAT to adjust and in WHICH direction
   - Explain WHY it addresses the issue
   - Note any negative side effects or trade-offs the driver should be aware of
3. **Testing reminder** — End with a brief reminder to change only one thing at a time and test after each change before making the next adjustment.

Be concise and direct. Avoid generic advice — reference the actual data. Use plain language. The driver is a sim racer, not a professional engineer.

## Important notes on the telemetry data
- Suspension position, ride heights, tyre temperatures and some other channels are in
  RELATIVE units (0–1 normalised within the session). Use them for comparison only.
  Do not quote them as absolute physical values.
- Camber values ARE in degrees and can be quoted directly.
- Speed, throttle, brake, RPM, and brake bias are in physical units.
- Damper histograms show velocity distributions in relative units. High percentage in
  the fast bump range (high velocity values) suggests the car is hitting bump stops or
  reacting harshly to kerbs.
"""


# ---------------------------------------------------------------------------
# User prompt builder
# ---------------------------------------------------------------------------

def build_user_prompt(analysis, driver_description, ld_file_meta):
    """
    Build the per-request user prompt from telemetry analysis.

    Args:
        analysis:          dict from telemetry_analyzer.analyze()
        driver_description: raw string from the driver
        ld_file_meta:      dict with driver, vehicle, venue, datetime

    Returns:
        str — the formatted user prompt
    """
    parts = []

    # --- Session header ---
    session = analysis.get('session', {})
    parts.append(_section('SESSION', _format_session(session, ld_file_meta)))

    # --- Overview ---
    parts.append(_section('LAP OVERVIEW', _format_overview(analysis.get('overview', {}))))

    # --- Corners ---
    corners = analysis.get('corners', [])
    targeted = analysis.get('targeted', {})
    relevant_corners = targeted.get('relevant_corners', corners)
    corner_filter = targeted.get('corner_filter')

    if relevant_corners:
        header = f'CORNERS'
        if corner_filter:
            header += f' (filtered to: {corner_filter})'
        parts.append(_section(header, _format_corners(relevant_corners)))

    # --- Tyres ---
    tyres = analysis.get('tyres', {})
    if tyres:
        parts.append(_section('TYRE DATA', _format_tyres(tyres)))

    # --- Suspension ---
    susp = analysis.get('suspension', {})
    if susp:
        parts.append(_section('SUSPENSION / DAMPERS', _format_suspension(susp)))

    # --- Ride heights ---
    rh = analysis.get('ride_heights', {})
    if rh:
        parts.append(_section('RIDE HEIGHTS (relative)', _format_ride_heights(rh)))

    # --- Camber ---
    camber = analysis.get('camber', {})
    if camber:
        parts.append(_section('CAMBER (degrees)', _format_camber(camber)))

    # --- Targeted extra data ---
    extra = targeted.get('data', {})
    categories = targeted.get('detected_categories', [])
    if extra:
        parts.append(_section('ADDITIONAL DATA', _format_targeted_extra(extra, categories)))

    # --- Driver description (last — so AI answers it specifically) ---
    parts.append(_section('DRIVER DESCRIPTION', driver_description.strip()))

    # --- Request ---
    parts.append(
        '\nBased on the telemetry above and the driver\'s description, '
        'provide specific setup recommendations.'
    )

    return '\n'.join(parts)


# ---------------------------------------------------------------------------
# Formatters
# ---------------------------------------------------------------------------

def _section(title, content):
    line = '─' * 60
    return f'\n{line}\n{title}\n{line}\n{content}'


def _format_session(session, meta):
    lines = [
        f"Driver:   {meta.get('driver', 'Unknown')}",
        f"Car:      {meta.get('vehicle', 'Unknown')}",
        f"Track:    {meta.get('venue', 'Unknown')}",
        f"Date:     {meta.get('datetime', 'Unknown')}",
        f"Lap:      {session.get('lap_number', '?')}",
        f"Lap time: {session.get('lap_time_str', 'unknown')}",
    ]
    return '\n'.join(lines)


def _format_overview(ov):
    if not ov:
        return 'No overview data.'
    lines = []
    if 'max_speed_kmh' in ov:
        lines.append(f"Max speed:          {ov['max_speed_kmh']} km/h")
    if 'avg_speed_kmh' in ov:
        lines.append(f"Avg speed:          {ov['avg_speed_kmh']} km/h")
    if 'throttle_mean_pct' in ov:
        lines.append(f"Throttle mean:      {ov['throttle_mean_pct']}%")
    if 'throttle_full_pct' in ov:
        lines.append(f"Full throttle:      {ov['throttle_full_pct']}% of lap")
    if 'brake_active_pct' in ov:
        lines.append(f"Braking:            {ov['brake_active_pct']}% of lap")
    if 'engine_rpm_max' in ov:
        lines.append(f"Max RPM:            {int(ov['engine_rpm_max'])}")
    if 'brake_bias_rear_pct' in ov:
        lines.append(f"Brake bias (rear):  {ov['brake_bias_rear_pct']}%")
    return '\n'.join(lines)


def _format_corners(corners):
    if not corners:
        return 'No corners detected.'
    lines = []
    for c in corners:
        direction = c['direction'].capitalize()
        sc = c['speed_class'].capitalize()
        lines.append(
            f"T{c['number']:>2} | {c['position_m']:>6}m | {direction:<5} | {sc:<6} | "
            f"Entry {c['entry_speed_kmh']:>5.1f} → Apex {c['apex_speed_kmh']:>5.1f} → Exit {c['exit_speed_kmh']:>5.1f} km/h | "
            f"Brake {c['brake_at_entry_pct']:>5.1f}% | Throttle@apex {c['throttle_at_apex_pct']:>5.1f}% | "
            f"Steer {c['steering_at_apex_deg']:>+6.1f}°"
        )
    return '\n'.join(lines)


def _format_tyres(tyres):
    lines = []
    for code in ['FL', 'FR', 'RL', 'RR']:
        t = tyres.get(code)
        if not t:
            continue
        parts = [f"{code}:"]
        if 'temp_i_rel' in t:
            parts.append(
                f"temp I/C/O = {t['temp_i_rel']:.3f}/{t.get('temp_c_rel', '?'):.3f}/{t.get('temp_o_rel', '?'):.3f} (rel)"
            )
        if 'pressure_rel' in t:
            parts.append(f"pressure = {t['pressure_rel']:.3f} (rel)")
        if 'wear_rel' in t:
            parts.append(f"wear = {t['wear_rel']:.3f} (rel)")
        lines.append('  ' + '  |  '.join(parts))

    balance = tyres.get('_balance')
    if balance:
        f_r = balance['front_vs_rear']
        l_r = balance['left_vs_right']
        lines.append(
            f"\n  Balance (inner temp): "
            f"Front vs Rear = {f_r:+.3f}  |  Left vs Right = {l_r:+.3f}"
        )
        if f_r < -0.05:
            lines.append('  → Rears significantly hotter than fronts (relative)')
        elif f_r > 0.05:
            lines.append('  → Fronts significantly hotter than rears (relative)')

    return '\n'.join(lines)


def _format_suspension(susp):
    lines = []
    for code in ['FL', 'FR', 'RL', 'RR', 'front_3rd', 'rear_3rd']:
        s = susp.get(code)
        if not s:
            continue
        label = code if len(code) == 2 else code.replace('_', ' ').title()
        lines.append(f"\n  {label}:")
        lines.append(f"    Position (rel): mean={s['mean_rel']:.3f}  range={s['range_rel']:.3f}")

        hist = s.get('damper_histogram')
        if hist:
            bump_fast = sum(b['pct'] for b in hist['bump'][3:])
            reb_fast  = sum(b['pct'] for b in hist['rebound'][:3])
            lines.append(
                f"    Bump: slow={hist['bump'][0]['pct']:.1f}%  "
                f"medium={hist['bump'][1]['pct']+hist['bump'][2]['pct']:.1f}%  "
                f"fast={bump_fast:.1f}%"
            )
            lines.append(
                f"    Rebound: slow={hist['rebound'][-1]['pct']:.1f}%  "
                f"medium={hist['rebound'][-2]['pct']+hist['rebound'][-3]['pct']:.1f}%  "
                f"fast={reb_fast:.1f}%"
            )

    return '\n'.join(lines) if lines else 'No suspension data.'


def _format_ride_heights(rh):
    lines = []
    for code in ['FL', 'FR', 'RL', 'RR']:
        r = rh.get(code)
        if r:
            lines.append(
                f"  {code}: mean={r['mean_rel']:.3f}  min={r['min_rel']:.3f}  max={r['max_rel']:.3f}"
            )
    return '\n'.join(lines) if lines else 'No ride height data.'


def _format_camber(camber):
    lines = []
    for code in ['FL', 'FR', 'RL', 'RR']:
        c = camber.get(code)
        if c:
            lines.append(
                f"  {code}: mean={c['mean_deg']:+.2f}°  "
                f"range [{c['min_deg']:+.2f}° to {c['max_deg']:+.2f}°]"
            )
    return '\n'.join(lines) if lines else 'No camber data.'


def _format_targeted_extra(extra, categories):
    lines = [f'Detected issue categories: {", ".join(categories) if categories else "none"}']

    brakes = extra.get('brake_detail')
    if brakes:
        lines.append('\nBrake detail per corner:')
        for code in ['FL', 'FR', 'RL', 'RR']:
            b = brakes.get(code, {})
            if b:
                parts = [f'  {code}:']
                if 'pressure_rel' in b:
                    p = b['pressure_rel']
                    parts.append(f"pressure mean={p['mean']:.3f} max={p['max']:.3f} (rel)")
                if 'temp_rel' in b:
                    t = b['temp_rel']
                    parts.append(f"temp mean={t['mean']:.3f} max={t['max']:.3f} (rel)")
                lines.append('  '.join(parts))

    bumps = extra.get('bump_detail')
    if bumps:
        lines.append('\nBump/kerb detail:')
        for code in ['FL', 'FR', 'RL', 'RR']:
            b = bumps.get(code, {})
            if b:
                parts = [f'  {code}:']
                if 'susp_force_rel' in b:
                    f_ = b['susp_force_rel']
                    parts.append(f"susp force max={f_['max']:.3f} (rel)")
                if 'tyre_deflection_rel' in b:
                    d = b['tyre_deflection_rel']
                    parts.append(f"tyre deflection max={d['max']:.3f} (rel)")
                lines.append('  '.join(parts))

    hybrid = extra.get('hybrid')
    if hybrid:
        lines.append('\nHybrid/ERS data:')
        for ch_name, stats in hybrid.items():
            lines.append(f"  {ch_name}: mean={stats['mean']:.1f}  max={stats['max']:.1f}")

    return '\n'.join(lines)


# ---------------------------------------------------------------------------
# Quick test
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    import sys
    sys.path.insert(0, '.')
    import ld_reader, telemetry_analyzer

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

    print(SYSTEM_PROMPT)
    print('\n' + '=' * 60 + ' USER PROMPT ' + '=' * 60)
    print(build_user_prompt(analysis, description, meta))
