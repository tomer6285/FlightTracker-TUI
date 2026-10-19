# Installation Guide - Terminal User Interface (TUI) Display

Runs FlightTracker directly inside your terminal as a Text User Interface (TUI). No Raspberry Pi, LED matrix, or graphical desktop/pygame environment required. Works across Linux, macOS, and Windows terminals with ANSI TrueColor support.

---

## Requirements

- Python 3.9+
- An ANSI 24-bit TrueColor compatible terminal (e.g. iTerm2, Alacritty, Kitty, Windows Terminal, GNOME Terminal, VSCode Terminal)

---

## Setup

```bash
git clone https://github.com/tomer6285/FlightTracker-TUI.git
cd FlightTracker-TUI
python3 -m venv env
source env/bin/activate
pip install -r platforms/tui/requirements.txt
```

---

## Running

```bash
python3 flight-tracker.py
```

FlightTracker will launch directly inside your terminal, displaying live flights, journey routes, plane telemetry, weather, clock, and satellite tracking with square-pixel Unicode half-blocks.

### Terminal Controls

| Key | Action |
|-----|--------|
| `Ctrl+C` or `Q` | Exit application cleanly |
| `+` / `=` | Increase brightness |
| `-` / `_` | Decrease brightness |
| `P` | Save screenshot to `captures/` |
| `S` | Cycle scale (`1x` -> `2x` -> `3x` -> `auto` -> `1x`) |
| `]` / `[` | Step scale up / down |
| `0` | Reset scale to `auto` |
| `1` - `5` | Set scale factor directly (`1x` to `5x`) |

### Scaling Options

By default, FlightTracker automatically selects the largest integer scale (`1x`, `2x`, `3x`, etc.) that fits your current terminal window (`auto`).

You can override the scale at startup:
```bash
python3 flight-tracker.py --scale 2       # Force 2x integer scale
python3 flight-tracker.py --scale auto    # Auto-fit to terminal window
# Or via environment variable:
export FLIGHTTRACKER_SCALE=2
```

---

## Configuration

On startup, FlightTracker launches the built-in web configuration server at `http://localhost:8584/settings` (or the IP displayed on start). You can configure your home coordinates, search radius, flight providers, units, and themes via the browser.
