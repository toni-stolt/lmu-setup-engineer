"""
ld_reader.py — MoTeC .ld file reader for LMU Setup Engineer

Wraps ldparser and handles:
- Correct channel scaling (three tiers: direct, shift-corrected, relative)
- Lap segmentation by Lap Number channel
- Exclusion of dead/irrelevant channels
- Detection of non-functional channels (flat data)
"""

import numpy as np
from ldparser import ldData


# ---------------------------------------------------------------------------
# Channel classification
# ---------------------------------------------------------------------------

# Channels confirmed dead/irrelevant in LMU — never include
ALWAYS_EXCLUDE = {
    # Confirmed flat in LMU GT3 (aero not exported)
    'Front Downforce', 'Rear Downforce', 'Drag', 'Front Wing Height',
    # Aggregate ride heights are flat — use per-corner FL/FR/RL/RR instead
    'Front Ride Height', 'Rear Ride Height',
    # Flat in LMU
    'Grip Fract FL', 'Grip Fract FR', 'Grip Fract RL', 'Grip Fract RR',
    'Lat Force FL', 'Lat Force FR', 'Lat Force RL', 'Lat Force RR',
    'Long Force FL', 'Long Force FR', 'Long Force RL', 'Long Force RR',
    'Tyre Load FL', 'Tyre Load FR', 'Tyre Load RL', 'Tyre Load RR',
    'Turbo Boost Pressure',
    # Administrative / race state — irrelevant to setup analysis
    'Anti Stall Activated', 'Beacon (Internal)', 'Best Laptime',
    'Best Sector 1', 'Best Sector 2', 'Cloud Darkness',
    'Cur Sector 1', 'Cur Sector 2',
    'Delta Best', 'Dent Severity 1', 'Dent Severity 2', 'Dent Severity 3',
    'Dent Severity 4', 'Dent Severity 5', 'Dent Severity 6',
    'Dent Severity 7', 'Dent Severity 8',
    'Driver Type', 'FFB Output', 'Finish Status', 'Flag', 'Game Phase',
    'Headlights State', 'Ignition State', 'In Pits',
    'Lap Start Elapsed Time', 'Laps Behind Leader', 'Laps Behind Next',
    'Last Impact Elapsed Time', 'Last Impact Magnitude',
    'Last Impact X Pos', 'Last Impact Y Pos', 'Last Impact Z Pos',
    'Last Laptime', 'Last Sector 1', 'Last Sector 2',
    'Marker', 'Max Straight Speed', 'Min Corner Speed',
    'Min Path Wetness', 'Motor State',
    'Num Penalties', 'Num Pitstops', 'Num Red Lights',
    'Off Path Wetness', 'Overheating State',
    'PitStatus', 'Place', 'Realtime Loss',
    'Raining', 'Sector Flag 1', 'Sector Flag 2', 'Sector Flag 3',
    'Server Scored', 'Session Elapsed Time', 'Speed Limiter On',
    'Start Light', 'Surface Type FL', 'Surface Type FR',
    'Surface Type RL', 'Surface Type RR',
    'Terrain Idx FL', 'Terrain Idx FR', 'Terrain Idx RL', 'Terrain Idx RR',
    'Time Behind Leader', 'Time Behind Next',
    'Tyre Flat FL', 'Tyre Flat FR', 'Tyre Flat RL', 'Tyre Flat RR',
    'Wheel Detached FL', 'Wheel Detached FR',
    'Wheel Detached RL', 'Wheel Detached RR',
    'Wind Heading', 'Wind Speed',
    'Yellow Flag State',
}

# These channels need `value - shift` to get physical units.
# Verified empirically against known physical ranges.
SHIFT_CORRECTED = {
    'Ground Speed',    # output - shift = km/h
    'Engine RPM',      # output - shift = rpm
    'Motor RPM',       # output - shift = rpm (hybrid cars)
}

# Channels where ldparser output is already in correct physical units
# (everything not in SHIFT_CORRECTED, not ALWAYS_EXCLUDE, and not RELATIVE_ONLY)

# Channels where ldparser output has an unknown absolute offset due to how
# LMU exports float32 data. Values are meaningful for relative comparison
# within and between laps, but absolute physical values are not calibrated yet.
# These are normalised to their observed range [0.0, 1.0] within each lap.
RELATIVE_ONLY = {
    'G Force Lat', 'G Force Long', 'G Force Vert',
    'Local Rot Accel X', 'Local Rot Accel Y', 'Local Rot Accel Z',
    'Local Rotation X', 'Local Rotation Y', 'Local Rotation Z',
    'Susp Pos FL', 'Susp Pos FR', 'Susp Pos RL', 'Susp Pos RR',
    'Susp Force FL', 'Susp Force FR', 'Susp Force RL', 'Susp Force RR',
    'Ride Height FL', 'Ride Height FR', 'Ride Height RL', 'Ride Height RR',
    'Front 3rd Pos', 'Rear 3rd Pos',
    'Tyre Rubber Temp FL I', 'Tyre Rubber Temp FL C', 'Tyre Rubber Temp FL O',
    'Tyre Rubber Temp FR I', 'Tyre Rubber Temp FR C', 'Tyre Rubber Temp FR O',
    'Tyre Rubber Temp RL I', 'Tyre Rubber Temp RL C', 'Tyre Rubber Temp RL O',
    'Tyre Rubber Temp RR I', 'Tyre Rubber Temp RR C', 'Tyre Rubber Temp RR O',
    'Tyre Carcass Temp FL', 'Tyre Carcass Temp FR',
    'Tyre Carcass Temp RL', 'Tyre Carcass Temp RR',
    'Tyre Pressure FL', 'Tyre Pressure FR',
    'Tyre Pressure RL', 'Tyre Pressure RR',
    'Tyre Wear FL', 'Tyre Wear FR', 'Tyre Wear RL', 'Tyre Wear RR',
    'Vertical Tyre Deflection FL', 'Vertical Tyre Deflection FR',
    'Vertical Tyre Deflection RL', 'Vertical Tyre Deflection RR',
    'Brake Temp FL', 'Brake Temp FR', 'Brake Temp RL', 'Brake Temp RR',
    'Brake Pressure FL', 'Brake Pressure FR',
    'Brake Pressure RL', 'Brake Pressure RR',
    'Steering Shaft Torque',
    'Motor Torque', 'Motor Temp', 'Motor Water Temp',
    'Battery Charge Level',
    'Lat Ground Vel FL', 'Lat Ground Vel FR', 'Lat Ground Vel RL', 'Lat Ground Vel RR',
    'Long Ground Vel FL', 'Long Ground Vel FR', 'Long Ground Vel RL', 'Long Ground Vel RR',
    'Lat Patch Vel FL', 'Lat Patch Vel FR', 'Lat Patch Vel RL', 'Lat Patch Vel RR',
    'Long Patch Vel FL', 'Long Patch Vel FR', 'Long Patch Vel RL', 'Long Patch Vel RR',
    'Wheel Rot Speed FL', 'Wheel Rot Speed FR', 'Wheel Rot Speed RL', 'Wheel Rot Speed RR',
    'Wheel Y Location FL', 'Wheel Y Location FR', 'Wheel Y Location RL', 'Wheel Y Location RR',
}

# Minimum meaningful range for a channel to be considered non-flat
FLAT_THRESHOLD = 0.01


# ---------------------------------------------------------------------------
# Core classes
# ---------------------------------------------------------------------------

class Channel:
    """A single telemetry channel with corrected scaling."""

    def __init__(self, name, data, freq, unit, scaling):
        self.name = name
        self.data = data          # numpy array, corrected values
        self.freq = freq          # Hz
        self.unit = unit          # physical unit string ('' if unknown)
        self.scaling = scaling    # 'direct' | 'shift_corrected' | 'relative' | 'excluded'

    @property
    def is_flat(self):
        return (self.data.max() - self.data.min()) < FLAT_THRESHOLD

    def stats(self):
        """Return a dict of basic statistics."""
        return {
            'mean':   float(np.mean(self.data)),
            'min':    float(np.min(self.data)),
            'max':    float(np.max(self.data)),
            'std':    float(np.std(self.data)),
        }

    def percentile(self, p):
        return float(np.percentile(self.data, p))


class Lap:
    """One lap's worth of telemetry data."""

    def __init__(self, lap_number, lap_time_s, channels):
        self.lap_number = lap_number
        self.lap_time_s = lap_time_s       # None if not available
        self.channels = channels           # dict: name -> Channel

    def __repr__(self):
        t = f'{self.lap_time_s:.3f}s' if self.lap_time_s else 'unknown time'
        return f'Lap {self.lap_number} ({t}, {len(self.channels)} channels)'

    def ch(self, name):
        """Get a channel by name, or None."""
        return self.channels.get(name)


class LDFile:
    """Parsed MoTeC .ld file with all laps extracted."""

    def __init__(self, driver, vehicle, venue, datetime_str, laps, all_channels_meta):
        self.driver = driver
        self.vehicle = vehicle
        self.venue = venue
        self.datetime = datetime_str
        self.laps = laps                       # list of Lap objects
        self.all_channels_meta = all_channels_meta  # channel name -> freq, unit

    def __repr__(self):
        return (f'LDFile: {self.driver} | {self.vehicle} | {self.venue} | '
                f'{self.datetime} | {len(self.laps)} laps')

    @property
    def best_lap(self):
        """Return the lap with the fastest lap time."""
        timed = [l for l in self.laps if l.lap_time_s and l.lap_time_s > 0]
        return min(timed, key=lambda l: l.lap_time_s) if timed else self.laps[0]

    def lap_summary(self):
        """Return list of dicts describing each lap — for the UI dropdown."""
        result = []
        for lap in self.laps:
            t = lap.lap_time_s
            if t and t > 0:
                mins = int(t // 60)
                secs = t % 60
                time_str = f'{mins}:{secs:06.3f}'
            else:
                time_str = 'unknown'
            result.append({
                'lap_number': lap.lap_number,
                'lap_time_s': t,
                'lap_time_str': time_str,
            })
        return result


# ---------------------------------------------------------------------------
# Parsing
# ---------------------------------------------------------------------------

def _correct_value(raw_data, channel_meta):
    """
    Apply the correct scaling to raw ldparser output.

    Returns (corrected_data, scaling_label)
    """
    name = channel_meta.name

    if name in SHIFT_CORRECTED:
        return raw_data - channel_meta.shift, 'shift_corrected'

    if name in RELATIVE_ONLY:
        mn, mx = raw_data.min(), raw_data.max()
        rng = mx - mn
        if rng < FLAT_THRESHOLD:
            # Channel is flat — return as-is, caller will detect via is_flat
            return raw_data, 'relative'
        normalised = (raw_data - mn) / rng
        return normalised, 'relative'

    # Default: ldparser output is already correct
    return raw_data, 'direct'


def _segment_laps(ld):
    """
    Segment all channels by lap using the Lap Number channel.

    Returns a list of (lap_number, start_idx, end_idx) tuples,
    indexed into the Lap Number channel's sample array.
    """
    lap_num_ch = None
    for c in ld.channs:
        if c.name == 'Lap Number':
            lap_num_ch = c
            break

    if lap_num_ch is None:
        return []

    lap_arr = lap_num_ch.data.astype(int)
    transitions = np.where(np.diff(lap_arr) != 0)[0]
    boundaries = [0] + list(transitions + 1) + [len(lap_arr)]

    segments = []
    for i in range(len(boundaries) - 1):
        start, end = boundaries[i], boundaries[i + 1]
        lap_n = int(lap_arr[start])
        segments.append((lap_n, start, end))

    return segments, lap_num_ch.freq


def _get_last_laptime(ld, lap_index, segments):
    """
    Get the lap time for a lap from the Last Laptime channel.
    The laptime for lap N is recorded at the start of lap N+1.
    """
    last_lt_ch = None
    for c in ld.channs:
        if c.name == 'Last Laptime':
            last_lt_ch = c
            break

    if last_lt_ch is None or lap_index >= len(segments) - 1:
        return None

    _, _, end_idx = segments[lap_index]
    # Convert index from lap_num_ch freq to last_lt_ch freq
    lap_num_freq = segments[0][1]  # not reliable here — use ratio
    # Use the value at the end of the current lap segment
    ratio = last_lt_ch.freq / 50  # Lap Number is 50Hz
    sample_idx = min(int(end_idx * ratio), len(last_lt_ch.data) - 1)
    val = float(last_lt_ch.data[sample_idx])
    return val if val > 0 else None


def _extract_channel_for_lap(channel_meta, lap_start_50hz, lap_end_50hz, lap_num_freq=50):
    """
    Extract the data slice for a lap from a channel.
    Converts lap boundaries (in Lap Number channel samples at 50Hz)
    to the channel's own sample rate.
    """
    try:
        raw_data = channel_meta.data
    except Exception:
        return None

    # Convert 50Hz indices to this channel's freq
    ratio = channel_meta.freq / lap_num_freq
    start = int(lap_start_50hz * ratio)
    end = int(lap_end_50hz * ratio)
    end = min(end, len(raw_data))
    start = min(start, end)

    if start >= end:
        return None

    return raw_data[start:end]


def parse(filepath):
    """
    Parse a MoTeC .ld file and return an LDFile object.

    Args:
        filepath: path to the .ld file

    Returns:
        LDFile object with all laps extracted and channels corrected
    """
    ld = ldData.fromfile(filepath)

    # --- Header ---
    driver  = ld.head.driver or 'Unknown'
    vehicle = ld.head.vehicleid or 'Unknown'
    venue   = ld.head.venue or 'Unknown'
    dt      = str(ld.head.datetime) if ld.head.datetime else ''

    # --- Lap segmentation ---
    result = _segment_laps(ld)
    if not result:
        raise ValueError('No Lap Number channel found in file.')
    segments, lap_num_freq = result

    # Build a lookup for channel metadata
    chan_by_name = {c.name: c for c in ld.channs}

    # --- Build Lap objects ---
    laps = []
    for i, (lap_n, start, end) in enumerate(segments):
        # Skip very short segments (< 2 seconds) — likely file boundaries
        duration = (end - start) / lap_num_freq
        if duration < 2.0:
            continue

        # Get lap time
        lap_time = None
        last_lt_ch = chan_by_name.get('Last Laptime')
        if last_lt_ch is not None and i + 1 < len(segments):
            _, next_start, _ = segments[i + 1]
            ratio = last_lt_ch.freq / lap_num_freq
            idx = min(int(next_start * ratio), len(last_lt_ch.data) - 1)
            val = float(last_lt_ch.data[idx])
            lap_time = val if val > 0 else None

        # Extract and correct each channel for this lap
        channels = {}
        for name, meta in chan_by_name.items():
            if name in ALWAYS_EXCLUDE:
                continue

            slice_data = _extract_channel_for_lap(meta, start, end, lap_num_freq)
            if slice_data is None or len(slice_data) == 0:
                continue

            corrected, scaling = _correct_value(slice_data, meta)

            unit = meta.short_name if meta.short_name else ''
            ch = Channel(name, corrected, meta.freq, unit, scaling)

            # Skip channels that are confirmed flat (no useful data)
            if ch.is_flat and name not in {
                'Brake Bias Rear', 'Front Tyre Compound', 'Rear Tyre Compound',
                'Gear',  # can be flat on a straight
            }:
                continue

            channels[name] = ch

        laps.append(Lap(lap_n, lap_time, channels))

    # --- All channel metadata (for reference) ---
    all_meta = {
        c.name: {'freq': c.freq, 'unit': c.short_name}
        for c in ld.channs
    }

    return LDFile(driver, vehicle, venue, dt, laps, all_meta)


# ---------------------------------------------------------------------------
# Quick test (run directly)
# ---------------------------------------------------------------------------

if __name__ == '__main__':
    import sys
    path = sys.argv[1] if len(sys.argv) > 1 else (
        '../2026-01-20 - 17-54-41 - Circuit de la Sarthe - P1 kierros.ld'
    )

    print(f'Parsing: {path}\n')
    ld_file = parse(path)
    print(ld_file)
    print()

    for lap in ld_file.laps:
        print(lap)
        print(f'  Active channels: {len(lap.channels)}')
        for name in ['Ground Speed', 'Throttle Pos', 'Brake Pos',
                     'Engine RPM', 'Steering', 'Brake Bias Rear']:
            ch = lap.ch(name)
            if ch:
                s = ch.stats()
                print(f'  {name:<30} [{s["min"]:.1f} – {s["max"]:.1f}]  '
                      f'mean={s["mean"]:.1f}  scaling={ch.scaling}')
        print()
