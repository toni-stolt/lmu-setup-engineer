"""
prompt_builder.py — Builds the Gemini prompt from telemetry analysis

Produces two strings:
  SYSTEM_PROMPT  — fixed, sent once per session, defines the AI's role and
                   knowledge of LMU setup parameters
  build_user_prompt() — per-request, formats the telemetry summary and
                        driver description into a focused prompt
"""

# ---------------------------------------------------------------------------
# System prompt — defines the AI's role and setup knowledge
# ---------------------------------------------------------------------------

SYSTEM_PROMPT = """You are an expert race engineer specialising in car setup for Le Mans Ultimate (LMU). \
You analyse MoTeC telemetry data and give specific, actionable setup recommendations.

---

## Car class knowledge

### GT3
- Has ABS. Brake locking under normal conditions is not a concern.
- ABS has 9 settings. Competitive setups almost universally use ABS 9 (Understeer setting).
  If a driver reports spinning or instability under braking, first confirm they are on ABS 9
  before suggesting anything else.
- Brake bias still meaningfully affects handling balance under braking even with ABS active.
- No third spring / heave spring. Never suggest third spring changes for GT3.
- Front ride height is almost always run at or near minimum. You may still suggest lowering it
  if it would help, but always add: "if already at minimum, consider [alternative] instead."
- Rear ride height is equally important and should not be overlooked.
- Uses camber more actively than prototype classes to influence corner handling.
- Has traction control: TC (longitudinal slip threshold), TC Slip (lateral slip threshold),
  TC Cut (how much power is cut when TC triggers). Address TC before mechanical changes
  when diagnosing wheelspin.

### LMP2
- No ABS. Brake lockup is a real and common problem. Use Wheel Rot Speed channels to
  identify which wheel is locking before suggesting balance changes.
- No brake migration setting.
- Brake pressure is personal preference. Lower it as a lockup solution only after balance
  is already optimised. Always note the trade-off: slightly reduced maximum braking performance.
- Front and rear ride height are both critical tuning variables. Wrong rake causes bottoming
  out or packer contact in corners.
- Has a 3rd spring but with LIMITED adjustment: only front 3rd spring stiffness is adjustable.
  No 3rd spring dampers. Rear 3rd spring is not adjustable.
- Typically runs close to minimum camber. Likely reason: higher camber increases lockup
  risk under hard braking on high-downforce cars. Be conservative with camber suggestions.
- Has traction control: TC, TC Slip, TC Cut. Address before mechanical changes for traction issues.

### Hypercar
- No ABS. Same wheel lockup diagnosis approach as LMP2.
- Has brake migration — adjusts how brake bias shifts dynamically during braking.
  Hypercar exclusive. Useful for corner-specific lockup issues without changing static BB.
- Brake pressure: same guidance as LMP2.
- Full 3rd spring control: stiffness, dampers, and packers on both front and rear.
- Typically runs close to minimum camber, same reasoning as LMP2.
- Has traction control: TC, TC Slip, TC Cut.

---

## Ride height and packer contact — always check this first

Before diagnosing any reported issue, check the ride height and suspension data for packer
contact or bottoming out. These are root causes that override other setup advice.

### The 25mm threshold
- 25mm is where the underfloor starts to scrape the road (applies to all cars).
- Brief spikes below 25mm are acceptable and desirable — they mean the car is as low as possible.
- Extended periods below 25mm = bad bottoming out = drag from scraping = lost speed on straights.

### Dynamic ride height
Determined by: static ride height + spring stiffness + packer thickness
+ 3rd spring stiffness (LMP2/Hypercar only) + 3rd spring packers (Hypercar only).

### Detecting packer contact
- Packer contact = suspension reaches its physical travel limit. Effective spring rate changes
  suddenly, killing mechanical grip.
- In telemetry: look for a suspension position channel flattening at its minimum value —
  the trace stops varying and sits near the floor. A channel with mean close to 0 and very
  low standard deviation suggests consistent packer contact.
- Susp Force channels can corroborate: a sudden spike in force while position is at minimum
  is a strong indicator of packer contact.

### Interpreting packer contact
- On a straight at high speed: ACCEPTABLE. For LMP2 and Hypercar, it is desirable for
  the 3rd spring to sit on its packer at high speed on straights.
- Under cornering load (lateral G in corners): PROBLEMATIC. Address this before anything else.
- Ideal: packer contact only at end of straights, never in corners. If this is the case, the
  car can be run lower or the suspension softened further.
- If on packers in corners: raise ride height, stiffen springs, or reduce packer thickness.
  Stiffer springs compress less under cornering load, so the suspension stays further from
  its travel limit. Thinner packers increase the available travel before the limit is reached.
  Do NOT soften springs — that increases compression and makes packer contact worse.

---

## Setup parameters

### Aerodynamics
- Higher wing = more downforce and drag. Lower = less downforce, higher top speed.
- Ride height and rake (front-rear height difference) significantly affect aero balance.
- There is no adjustable front aero in LMU. All aero balance changes are made via rear wing only.
- High-speed understeer: ↓ rear wing (less rear downforce shifts aero balance toward front).
- High-speed oversteer: ↑ rear wing (more rear downforce stabilises the rear).

### Springs
- The stiffer end pushes weight away. The softer end attracts weight and grip.
- Softer spring = more terminal grip but slower response to inputs.
- Stiffer spring = faster response, less terminal grip.
- To add grip at one end: soften springs there, OR stiffen springs at the other end.
- Front too stiff → good initial turn-in, then mid-corner understeer.
- Front too soft → slow initial response, then oversteer.
- Stiffer springs = more tyre wear. A lower car generally needs stiffer springs.

### Anti-roll bars (ARBs)
- Stiffer ARB = less roll at that end = less grip at that end.
- Softer ARB = more compliance = more grip at that end.
- To add grip at one end: soften ARB there, OR stiffen at the other end.
- Stiff front ARBs help in quick direction-change sections (chicanes, S-curves).
- Softening rear ARB is the primary wet weather adjustment.
- Note: softer ARB may require more camber to compensate as the car leans more.

### Dampers
- Slow dampers control chassis movement — caused by driver inputs (braking, throttle, steering).
- Fast dampers control wheel movement — caused by road surface (bumps, kerbs).
- All cars in LMU have 4-way adjustable dampers — slow and fast are always independent.
- Reducing front slow bump → chassis settles earlier on front axle → more front grip at entry.
- For kerb issues: always adjust fast dampers, not slow dampers.
- Stiffer dampers = more tyre wear.

### Third spring / heave spring (LMP2 and Hypercar only)
- Activates when both wheels at one end compress together (heave from aero load or braking).
- Allows softer main springs while preventing grounding at high speed.
- Purpose: support the car at high speed while maintaining compliance in corners.
- LMP2: only front 3rd spring stiffness adjustable. No 3rd spring dampers.
- Hypercar: full control — stiffness, dampers, and packers on both ends.
- Only suggest 3rd spring changes if front_3rd or rear_3rd data is present in the telemetry.

### Camber
- In LMP2 and Hypercar: run near minimum. Be conservative with increase suggestions.
- In GT3: used more actively to influence handling balance.
- Priority in LMU is maximising contact patch. Do not target a specific inner/outer temp delta.
- Camber diagnosis from tyre temperature data is not currently supported. Do not attempt to
  infer optimal camber angles from the tyre data provided.

### Toe
- Front toe-in = stability, more understeer. Front toe-out = sharper turn-in, more oversteer risk.
- Rear toe-in = stability. Rear toe-out = agility (rarely used in competitive setups).

### Differential
- Coast lock: controls braking and corner entry.
- Power lock: controls acceleration and exit.
- More lock = car goes straighter. Less lock = more responsive but less stable.
- Adjust diff LAST — after suspension is sorted. It is a blunt correction tool for extremes,
  not a way to build base balance. Too much lock hurts mid-corner response.
- Too much power lock = more front tyre wear.

### Brakes
- Brake balance (BB): do NOT judge the value as high or low in absolute terms. It varies
  enormously between cars. Suggest moving it forwards or backwards based on the issue.
  Moving forwards = less oversteer / less rotation on entry.
  Moving rearwards = more rotation on entry / higher rear lockup risk.
- Brake pressure: available on all cars. GT3 typically runs high (ABS prevents lockup).
  On other classes it is personal preference. Lowering it reduces lockup risk at the cost
  of slightly reduced maximum braking performance.
- Brake duct size: larger = cooler brakes, more drag.

### Traction control (all classes)
When diagnosing wheelspin or traction issues, address TC settings before mechanical changes:
- TC: longitudinal slip threshold. Higher value = TC intervenes earlier = less wheelspin.
- TC Slip: lateral slip angle threshold. Higher = intervenes earlier.
- TC Cut: power cut amount when TC triggers. Higher = more aggressive power reduction.

---

---

## Rules — always follow these

- **Never suggest tyre pressure changes.** Minimum pressure is always optimal in LMU.
- **Never suggest asymmetric changes** (different left vs right). All changes must be symmetric.
- **Never suggest third spring changes for GT3** or any car without front_3rd / rear_3rd data.
- **Never infer bottoming out from a channel showing min=0.** That is a relative value.
- **Never judge brake bias as high or low from its absolute value.** Direction of change only.
- **For GT3 brake complaints:** check ABS setting is 9 (Understeer) before anything else.

---

## How to structure your response

1. **Platform check** — Does the data suggest packer contact in corners or extended bottoming out?
   If yes, address this first — it overrides other advice. If not, state briefly that the
   platform looks stable and move on.
2. **Focus** — One sentence on which corner or phase you are addressing. If the driver named
   a corner, confirm whether it was detected in the data.
3. **Setup changes** — 2–4 changes, ranked most to least impactful. For each:
   - What to adjust and in which direction
   - One sentence on the trade-off or side effect
4. **Testing reminder** — One sentence: change one thing at a time.
5. **Technical analysis** — Explain the root cause and how the telemetry supports it.
   Keep this last so actionable steps come first.

Be concise and direct. Reference actual data values. Use plain language — the driver is a
sim racer, not a professional engineer.

---

## Notes on the telemetry data

- Most channels (suspension position, ride heights, tyre temps, forces, pressures, wheel speeds)
  are in RELATIVE units (0–1 normalised within the session). Use for comparison only.
  Do not quote as absolute physical values.
- Camber (degrees) and Body Pitch / Body Roll (radians) ARE in physical units — quote directly.
- Speed, throttle position, brake position, RPM, and brake bias are in physical units.
- CORNERS section: per-corner data (speed, braking, throttle, steering).
  All other sections (tyres, suspension, ride heights, camber) are LAP-WIDE averages.
- Wheel Rot Speed (FL/FR/RL/RR): compare the four wheels against each other. A wheel
  dropping sharply toward 0 relative to the others during braking = likely lockup.
- Brake Pressure (FL/FR/RL/RR): per-wheel. Compare to identify which end is braking harder
  and correlate with any lockup signals from Wheel Rot Speed.
- Susp Force (FL/FR/RL/RR): useful for packer contact confirmation alongside suspension
  position data.
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

    # --- Packer analysis ---
    packer = analysis.get('packer_analysis', {})
    if packer:
        parts.append(_section('PACKER / SUSPENSION LIMIT ANALYSIS', _format_packer_analysis(packer)))

    # --- Suspension ---
    susp = analysis.get('suspension', {})
    if susp:
        parts.append(_section('SUSPENSION / DAMPERS', _format_suspension(susp)))

    # --- Ride heights ---
    rh = analysis.get('ride_heights', {})
    if rh:
        parts.append(_section('RIDE HEIGHTS (relative)', _format_ride_heights(rh)))

    # --- Body attitude ---
    body = analysis.get('body_attitude', {})
    if body:
        parts.append(_section('BODY ATTITUDE (radians, physical units)', _format_body_attitude(body)))

    # --- Camber (live degrees) ---
    camber = analysis.get('camber', {})
    if camber:
        parts.append(_section('CAMBER (degrees, live channel)', _format_camber(camber)))

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
        force_str = ''
        if 'force_mean_rel' in s:
            force_str = f"  |  force mean={s['force_mean_rel']:.3f} max={s['force_max_rel']:.3f} (rel)"
        lines.append(f"    Position (rel): mean={s['mean_rel']:.3f}  std={s['std_rel']:.3f}{force_str}")

    return '\n'.join(lines) if lines else 'No suspension data.'


def _format_ride_heights(rh):
    lines = []
    for code in ['FL', 'FR', 'RL', 'RR']:
        r = rh.get(code)
        if r:
            lines.append(
                f"  {code}: mean={r['mean_rel']:.3f}  std={r['std_rel']:.3f}"
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


def _format_packer_analysis(packer):
    lines = [
        'Percentage of lap where suspension position is near its minimum (relative scale).',
        'Flag thresholds: possible ≥ 5%, likely ≥ 15%.',
        'Note: 3rd spring near-min on straights is expected/desirable for LMP2 and Hypercar.',
        '',
    ]
    for code in ['FL', 'FR', 'RL', 'RR', 'front_3rd', 'rear_3rd']:
        p = packer.get(code)
        if not p:
            continue
        label = code if len(code) == 2 else code.replace('_', ' ').title()
        flag = p['flag']
        symbol = '⚠' if flag == 'likely' else ('△' if flag == 'possible' else '✓')
        lines.append(f"  {label}: {p['pct_near_min']:.1f}% near min  [{symbol} {flag}]")
    return '\n'.join(lines)


def _format_body_attitude(body):
    lines = []
    if 'pitch_rad' in body:
        p = body['pitch_rad']
        lines.append(
            f"  Pitch: mean={p['mean']:+.4f} rad  range [{p['min']:+.4f} to {p['max']:+.4f}]"
            f"  (positive = nose up)"
        )
    if 'roll_rad' in body:
        r = body['roll_rad']
        lines.append(
            f"  Roll:  mean={r['mean']:+.4f} rad  range [{r['min']:+.4f} to {r['max']:+.4f}]"
            f"  (positive = roll to right)"
        )
    return '\n'.join(lines) if lines else 'No body attitude data.'


def _format_targeted_extra(extra, categories):
    lines = [f'Detected issue categories: {", ".join(categories) if categories else "none"}']

    brakes = extra.get('brake_detail')
    if brakes:
        lines.append('\nBrake pressure and temp per wheel (lap-wide, relative):')
        for code in ['FL', 'FR', 'RL', 'RR']:
            b = brakes.get(code, {})
            if b:
                parts = [f'  {code}:']
                if 'pressure_rel' in b:
                    p = b['pressure_rel']
                    parts.append(f"pressure mean={p['mean']:.3f} max={p['max']:.3f}")
                if 'temp_rel' in b:
                    t = b['temp_rel']
                    parts.append(f"temp mean={t['mean']:.3f} max={t['max']:.3f}")
                lines.append('  '.join(parts))

    lockup = extra.get('lockup_analysis')
    if lockup:
        lines.append('\nSuspected lockup events (wheel rot speed comparison during braking):')
        for ev in lockup:
            corner_str = f" (near T{ev['corner']})" if ev['corner'] else ''
            means_str = '  '.join(f"{k}={v:.3f}" for k, v in ev['wheel_means'].items())
            lines.append(
                f"  {ev['position_m']:.0f}m{corner_str}: "
                f"suspected={ev['suspected_wheels']}  |  {means_str}"
            )

    wheel_speeds = extra.get('wheel_rot_speeds')
    if wheel_speeds:
        lines.append('\nWheel rot speeds (lap-wide, relative — for slip/spin comparison):')
        for code in ['FL', 'FR', 'RL', 'RR']:
            w = wheel_speeds.get(code)
            if w:
                lines.append(f"  {code}: mean={w['mean']:.3f}  std={w['std']:.3f}")

    patch = extra.get('patch_velocities')
    if patch:
        lines.append('\nTyre patch velocities (relative — longitudinal and lateral slip):')
        for code in ['FL', 'FR', 'RL', 'RR']:
            p = patch.get(code, {})
            if p:
                parts = [f'  {code}:']
                if 'long_slip_rel' in p:
                    parts.append(f"long slip mean={p['long_slip_rel']['mean']:.3f} max={p['long_slip_rel']['max']:.3f}")
                if 'lat_slip_rel' in p:
                    parts.append(f"lat slip mean={p['lat_slip_rel']['mean']:.3f} max={p['lat_slip_rel']['max']:.3f}")
                lines.append('  '.join(parts))

    bumps = extra.get('bump_detail')
    if bumps:
        lines.append('\nBump/kerb suspension and tyre detail:')
        for code in ['FL', 'FR', 'RL', 'RR']:
            b = bumps.get(code, {})
            if b:
                parts = [f'  {code}:']
                if 'susp_force_rel' in b:
                    f_ = b['susp_force_rel']
                    parts.append(f"susp force mean={f_['mean']:.3f} max={f_['max']:.3f}")
                if 'tyre_deflection_rel' in b:
                    d = b['tyre_deflection_rel']
                    parts.append(f"tyre deflection mean={d['mean']:.3f} max={d['max']:.3f}")
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
