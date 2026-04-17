# LMU Setup Engineer — Project Briefing

## What This Is
An AI-powered setup advisor for Le Mans Ultimate sim racers. Users upload a MoTeC .ld telemetry file, describe a handling issue, and receive specific setup change suggestions powered by Google Gemini.

## Architecture
- **Backend:** Python / Flask — parses .ld files, extracts telemetry, calls Gemini API
- **Frontend:** Vanilla HTML/CSS/JS — hosted on Netlify (not a PWA, desktop use only)
- **AI:** Google Gemini free tier
- **Hosting:** Backend on Render free tier, frontend on Netlify free tier
- **Auth:** None — anonymous, IP-based rate limit (100 requests/day/IP)

## Key Files
- `backend/ld_reader.py` — reads .ld files, fixes float32 scaling bug in ldparser
- `backend/telemetry_analyzer.py` — computes stats, corner detection via GPS, damper histograms
- `backend/prompt_builder.py` — builds Gemini prompt from telemetry + user description
- `backend/gemini_client.py` — Gemini API integration
- `backend/app.py` — Flask routes

## Critical Technical Notes
- ldparser has a scaling bug for float32 channels — ld_reader.py must bypass ldparser's
  conversion for those channels and read raw float32 values directly
- GPS (Latitude/Longitude at 5Hz) is available — use for corner detection and track position mapping
- Channels confirmed dead in LMU (always exclude): Front/Rear Downforce, Drag, Front Wing Height,
  Grip Fract, Lat/Long Force per wheel, Tyre Load, Motor channels (for GT3), Turbo Boost Pressure
- Per-corner ride height works: Ride Height FL/FR/RL/RR — use these, not Front/Rear Ride Height
- Third spring elements (Front/Rear 3rd Pos) are active — include when non-zero

## Channel Strategy
Three tiers: always-include, always-exclude, conditional (based on described issue).
Full channel classification has not yet been formally documented — revisit and formalise
after initial version is working and prompt quality is proven.

---

## LMU Physics & Setup Knowledge (gathered from user)

### Ride Height — critical for all classes
- 25mm is where the bottom of the car starts to scrape the road. Universal across all cars.
- Both front AND rear ride height are equally important for every car class.
- Dynamic ride height is determined by: static ride height + spring stiffness + packer thickness
  + 3rd spring stiffness + 3rd spring packers (where applicable).
- Goal: get the car as low as possible without bottoming out causing problems.
- For GT3: front ride height is almost always run at or near minimum. AI may still suggest
  lowering it if relevant, but must add "if already at minimum, consider X instead."
- For LMP2 / Hypercar: ride height is a critical tuning variable — wrong rake leads to
  bottoming out or packer contact in corners (both bad for mechanical grip and aero).

### 3rd Spring / Heave Spring — LMP2 and Hypercar only
- GT3: no 3rd springs.
- LMP2: has 3rd springs but LIMITED settings. Only front 3rd spring stiffness is adjustable.
  No 3rd spring dampers. Rear 3rd spring is not adjustable.
- Hypercar: full 3rd spring control — stiffness, dampers, and packers on both front and rear.
- Purpose: support the car at high speed (on straights) while keeping the car compliant in corners.
- It is DESIRABLE for the 3rd spring to sit on its packer at very high speeds (straights).
- Some 3rd spring packer contact in fast corners may still be acceptable/desirable.
- What must have travel available are the CORNER (main) suspension packers — they must not
  be fully compressed during cornering, as this destroys mechanical grip.
- Packer contact is only a problem when it happens under cornering load (lateral G). Packer
  contact on a straight at high speed is not an issue regardless of speed.

### Packer Contact — detection and interpretation
- Packer contact means the suspension has reached its physical travel limit. The effective
  spring rate changes suddenly, hurting mechanical grip.
- In MoTeC, packer contact appears as a suspension position channel "flattening out" at its
  minimum value — the trace stops moving and sits on the floor.
- In our telemetry data: suspension position is in relative units (0–1). A channel with mean
  near 0 and very low std deviation suggests the suspension is consistently near full compression
  — likely on the packer. This needs to be interpreted in context (straight vs corner).
- The hockey-stick scatter plot (susp force vs susp position) is the professional method but
  is hard to replicate in our current setup. Trial and error may be needed to validate detection.
- KEY AI ADVICE TARGET: distinguish between packer contact on straights (fine) vs packer
  contact under cornering load (bad — needs intervention).
- Example of ideal advice: "You are only hitting the packer at the end of the straight, never
  in corners — this is fine. You could soften the suspension or lower the ride height further."

### Bottoming out (ride height below 25mm)
- Brief spikes below 25mm are still DESIRABLE — they mean the car is running as low as possible.
- Extended periods below 25mm = bad bottoming out = aero instability and speed loss (scraping creates drag).
- Signs of severe bottoming out to look for in data:
  - Ride height channel spending long continuous periods below the 25mm threshold
  - Speed loss on straights at full throttle — scraping the ground creates drag and costs speed
- Note: detecting this properly requires actual mm values from the ride height channels.
  Our current system uses relative units. Exact bottoming-out detection may need further
  telemetry work. Flag as a known limitation until resolved.

### Class-Specific Differences Summary
| Topic                  | GT3              | LMP2                        | Hypercar                    |
|------------------------|------------------|-----------------------------|-----------------------------|
| ABS                    | Yes              | No                          | No                          |
| Brake locking          | Not an issue     | Real problem, diagnose      | Real problem, diagnose      |
| Brake migration        | No               | No                          | Yes (Hypercar only)         |
| Front ride height      | Usually minimum  | Critical variable           | Critical variable           |
| Rear ride height       | Important        | Equally important           | Equally important           |
| 3rd spring             | None             | Front stiffness only        | Full control (F+R)          |
| 3rd spring dampers     | None             | None                        | Yes                         |
| Packer on straights    | N/A              | Desirable (3rd spring)      | Desirable (3rd spring)      |
| Packer in corners      | Bad              | Bad                         | Bad                         |

### Tyre Wear
- Tyre wear issues are very hard to solve with setup changes in LMU.
- Do not give overconfident advice in the tyre wear category.
- Camber and toe affect wear but the margin for improvement is limited.
- Always set expectations: "setup changes have limited impact on wear in LMU."

### PDF Reference
- File: `Sim Racers Performance Guide V2.pdf` — written by rF2 professionals, applies to LMU.
- Chapters 6 and 7 are not relevant (driver performance / bibliography).
- Key knowledge extracted below.

### Problem-Solution Matrix (from PDF Chapter 5a)
Note: prioritised steps in order. "Low speed" and "high speed" are corner speed categories.

**Low speed — Understeer:**
- Entry: ↑ front slow bump, ↑ front slow rebound, ↑ rear springs
- Mid: ↑ front ARB / ↓ rear ARB, ↓ rear slow rebound, ↓ rear springs
- Exit: ↓ rear slow bump, ↓ front springs, ↓ rear springs

**Low speed — Oversteer:**
- Entry: ↓ coast diff lock, ↓ front slow bump, ↑ front springs, ↓ rear slow rebound
- Mid: ↓ front ARB / ↑ rear ARB, ↓ front springs, ↑ rear springs
- Exit: ↑ rear slow bump, ↑ front slow rebound, ↑ rear springs, ↓ power diff lock

**High speed — Understeer:**
- Entry/Mid: ↓ front wing / ↑ rear wing, ↑ front slow bump

**High speed — Oversteer:**
- Entry: ↑ rear ride height, ↓ rear springs, ↓ rear bump, ↓ front slow rebound, ↑ diff power
- Mid/Exit: ↓ rear wing / ↑ front wing, ↓ front slow bump

**Medium speed:** Blend of high and low speed remedies.

**Wheelspin on exit:** ↓ rear camber, ↑ diff preload/power lock, ↓ rear spring rate,
check rear ride height for packer contact, check rear slow bump.

**Brake lockup:** Move bias away from locking end, ↓ brake pressure, ↓ camber, check brake fade.

**Rear lockup on downshifts:** ↓ engine braking.

**Kerbs:** Use fast dampers to address kerb issues, NOT slow dampers.

### Tyre Wear Impact (from PDF Chapter 5b)
- More aero → less wear
- Stiffer springs → more wear
- Stiffer dampers → more wear
- More diff lock → more front wear, less rear wear
- Brake bias away from an end → less wear at that end
- Lower brake pressure → less wear
- Stiffer ARB at one end → more wear at that end

### Key Setup Theory (from PDF — applies to LMU)
- **Stiffer end pushes weight away; softer end attracts weight.** Applies to both springs and ARBs.
- **Slow dampers** control chassis movement (driver inputs: braking, throttle, steering).
  **Fast dampers** control wheel/road movement (bumps, kerbs). These are independent on 4-way adjustable cars.
- Reducing front slow bump → chassis settles earlier on front axle → more front grip at entry.
- Diff should be adjusted LAST after suspension is dialled in. It is a blunt tool for controlling
  extremes, not for building base balance. Too much lock hurts mid-corner response.
- Front springs too stiff → good initial response, then mid-corner understeer.
- Front springs too soft → slow initial response, then oversteer.
- Softer ARB may need more camber to compensate (car leans more, outside tyre loads up more).
- Tyre temp deltas (inner vs outer): in LMU the priority is maximizing contact patch, not hitting
  a specific delta target. Do not use the 25°C delta rule from the PDF — it may not apply in LMU.

### Braking — all car classes

**Brake pressure** — available on every car.
- GT3: typically run at very high values — ABS prevents lockup so high pressure is safe.
- LMP2 / Hypercar: more personal preference and car dependent. Some professionals don't
  run maximum pressure even when they could. It is a matter of driver skill and taste.
- Tradeoff of lowering brake pressure: slightly reduced maximum braking performance.

**Brake balance (BB) — important note:**
- Do NOT judge the BB value as "high" or "low" in absolute terms. It varies enormously between
  cars. A value that is aggressive on one car may be conservative on another.
- Instead: suggest moving BB forwards or backwards based on what the issue and data indicate.
- Future improvement: add typical BB ranges per car when that data becomes available.

**Lockup diagnosis priority (non-GT3):**
1. Identify which wheels are locking using wheel rotation speed data under braking — especially
   at the specific corner the driver mentions. Wheel speed dropping faster than others = that
   wheel is locking. Suggest BB or migration changes based on which end/wheel is locking.
2. Special case: if the front INSIDE wheel is locking specifically when the driver is braking
   while turning in, consider a softer front ARB — the inside front is being unloaded by the
   cornering force and locks more easily. Only suggest this if fronts are not also locking in
   straight-line braking zones, which would indicate a general front lock issue instead.
3. If balance/migration look already optimised, suggest lowering brake pressure.
   Always note the tradeoff: slightly less braking performance, driver skill dependent.

**GT3 ABS:**
- 9 settings available. Competitive GT3 setups almost universally run ABS 9 (Understeer).
- If a GT3 driver reports spinning under braking or instability:
  1. First ask/confirm: is ABS set to 9 (Understeer)? This is the likely fix if not.
  2. Then check brake balance — still meaningfully affects handling under braking even with ABS.
  3. Then look at suspension-related causes.
- Do NOT suggest lowering brake pressure for GT3 lockup issues — ABS handles that.

### Traction Control — all car classes
Every car in LMU has three TC settings. These should be considered BEFORE mechanical changes
when diagnosing wheelspin or traction issues:
- **TC (Traction Control):** how much longitudinal slip is allowed before TC Cut intervenes.
  Primary setting for wheelspin out of slow corners.
- **TC Slip:** same principle but for lateral slip angle.
- **TC Cut:** how much power is cut from the engine when either TC or TC Slip triggers.

In the Traction & Exits category, the AI should address TC settings first (easiest to adjust,
immediate effect), then move to mechanical solutions (LSD, rear suspension) only if TC
optimisation alone is insufficient.

### Camber — LMU specific
- LMP2 and Hypercar: almost always run close to minimum camber values. Likely reason: higher
  camber increases lockup risk in hard braking zones on these high-downforce cars.
- GT3: camber is used more actively to influence corner handling balance.
- Camber advice is uncertain territory — do not be overconfident. Flag as a suggestion to test
  rather than a definitive fix. This section needs more research before strong advice is given.

## Current Status (2026-04-14)
**Deployed and working end-to-end. Local testing confirmed working.**
- Backend live on Render.com: `https://lmu-setup-engineer.onrender.com`
- Frontend live on Netlify
- Full flow works: upload .ld → select car class → select lap → describe issue → get AI advice

### What is complete and working
- **ldparser scaling bug fixed** (`ld_reader.py`): all channels deliver real physical units
  (mm, kPa, °C, N). Formula: `raw * mul / (scale * 10^dec) + shift`. Bypasses ldparser entirely.
- **All analyzers use physical units** (`telemetry_analyzer.py`): `_mm`, `_C`, `_kPa`, `_N` keys throughout.
- **`prompt_builder.py` fully updated** to physical unit keys. All formatters correct.
- **Car class dropdown** added to frontend (GT3 / LMP2 / Hypercar). Required field. Passed to backend and included in prompt session header.
- **Bottoming out thresholds** calibrated: < 5% = normal/desirable, 5–15% = monitor, > 15% = flag.
- **SYSTEM_PROMPT** contains full LMU knowledge: packer detection, ride height, TC, ABS 9, brake lockup, 3rd spring, camber, problem-solution matrix.
- **Test file**: `2026-04-02 - 18-44-51 - Paul Ricard - 1A - P1.ld` (Hypercar, project root)

### Local development
```
python backend/app.py        # runs on port 5000
# open frontend/index.html in browser
# set API_BASE in frontend/js/app.js to http://localhost:5000
# API key in backend/.env (GEMINI_API_KEY=...)
```
**Remember to revert `API_BASE` back to the Render URL before deploying.**

### NEXT — pick up here
Evaluate and improve prompt quality. The next big task is the **modular prompt system**:
per car class × issue category knowledge injection (see Next Goals below).

---

## Next Goals (priority order)

### 1. HIGHEST PRIORITY — Prompt quality / modular prompts
Car class dropdown is done. The next step is an **issue category dropdown** + modular prompt assembly.

#### Design decision: modular prompts (NOT one giant master prompt)
- Frontend: add **issue category** dropdown (5 options: Understeer / Oversteer & snap /
  Traction & exits / Braking & rotation / Bumps & kerbs)
- Backend assembles only the relevant knowledge sections for that car class × issue combination
- Rationale: keeps token count low (free tier), improves advice focus, avoids irrelevant context
- This will take significant time — requires writing high-quality prompts per combination
- Do not rush this — prompt quality is the core value of the product

### 2. UI / Visual rework
Full redesign of the frontend look and feel. The current design is functional but needs rework.
Scope and direction to be decided when we start this task. Do not begin until prompt work is done
or until the user explicitly asks to start it.

### 3. Post-v1 feature ideas (deferred)
- Lap comparison — compare two laps to highlight differences

---

## Deployment Rules
- **NEVER deploy a new version to Netlify or Render without explicit user instruction.**
- Only deploy when significant progress has been made — not after every small change.
- Reason: preserving Netlify free tier build minutes.
