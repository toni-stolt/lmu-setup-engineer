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
See app-ideas.md in parent directory for full channel classification.
Revisit and optimise channel selection after initial version is working.

## Current Status
Project structure set up. Starting with ld_reader.py (Phase 1).
