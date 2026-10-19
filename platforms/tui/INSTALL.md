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

---

## Configuration

On startup, FlightTracker launches the built-in web configuration server at `http://localhost:8584/settings` (or the IP displayed on start). You can configure your home coordinates, search radius, flight providers, units, and themes via the browser.
