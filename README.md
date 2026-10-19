# FlightTracker TUI [![Tests and formatting](https://github.com/tomer6285/FlightTracker-TUI/actions/workflows/lint.yml/badge.svg)](https://github.com/tomer6285/FlightTracker-TUI/actions/workflows/lint.yml)

A Terminal User Interface (TUI) flight tracker that shows you what aircraft are overhead directly inside your terminal. It quietly answers the important question: **"What's that plane?"**

FlightTracker TUI takes live aircraft data, works out what is nearby, and displays it in your terminal using ANSI TrueColor 24-bit half-blocks. When there's nothing overhead, it shows the time, weather, temperature, rainfall, or satellite passes.

 - **Terminal Native**: Runs on Linux, macOS, and Windows terminals with ANSI TrueColor support. No LED matrix hardware or GUI/pygame dependencies required.
 - **Live Flight Tracking**: Displays callsign, aircraft type, origin and destination airports, altitude, speed, heading, and distance.
 - **Multi-Provider Support**: Supports FlightRadar24, OpenSky Network, and local ADS-B receivers (tar1090/dump1090).
 - **Web Configuration**: Built-in web UI for configuring location, search radius, flight providers, and display preferences.
 - **Hardware & Simulator Fallbacks**: LED matrix drivers (Pi 3/4/5) and pygame desktop simulator are still supported via `FLIGHTTRACKER_PANEL`.

---

## Installation

### Quick start (TUI)

```bash
git clone https://github.com/tomer6285/FlightTracker-TUI.git
cd FlightTracker-TUI
python3 -m venv env
source env/bin/activate
pip install -r platforms/tui/requirements.txt
python3 flight-tracker.py
```

### Platform guides

| Platform | Guide |
|----------|-------|
| Terminal User Interface (TUI) | [platforms/tui/INSTALL.md](platforms/tui/INSTALL.md) |
| Raspberry Pi 3 / 4 / Zero (RGB Matrix) | [platforms/pi/INSTALL.md](platforms/pi/INSTALL.md) |
| Raspberry Pi 5 (RGB Matrix) | [platforms/pi5/INSTALL.md](platforms/pi5/INSTALL.md) |
| Desktop simulator (pygame window) | [platforms/simulator/INSTALL.md](platforms/simulator/INSTALL.md) |

---

## Terminal Controls

| Key | Action |
|-----|--------|
| `Ctrl+C` or `Q` | Exit application cleanly |
| `+` / `=` | Increase brightness |
| `-` / `_` | Decrease brightness |
| `P` | Save screenshot PNG to `captures/` |
| `S` | Cycle integer scale (`1x` -> `2x` -> `3x` -> `auto` -> `1x`) |
| `]` / `[` | Step scale factor up / down |
| `0` | Reset scale factor to `auto` |
| `1` - `5` | Set scale factor directly (`1x` - `5x`) |

---

## Web Configuration

On startup, FlightTracker launches the built-in web configuration server at `http://localhost:8584/settings` (or the IP displayed on start). You can configure your home coordinates, search radius, flight providers, units, and themes via the browser.

---

## Optional features

### Rainfall chart

If you have a WeatherAPI key configured, you can display a 24-hour rainfall chart alongside the temperature. Set the weather mode to "temperature + rainfall" in the web UI.

### Using a local ADS-B receiver (tar1090)

By default the tracker pulls flight data from FlightRadar24. If you run your own ADS-B receiver with [tar1090](https://github.com/wiedehopf/tar1090) or a compatible [PiAware](https://www.flightaware.com/adsb/piaware/) / [dump1090-fa](https://github.com/flightaware/dump1090) setup, you can use that as your primary data source instead - no FlightRadar24 account or API access required.

#### What you need

- A device running dump1090-fa, readsb, or similar, with tar1090 installed
- The device must be reachable on your local network from the Flight Tracker machine
- tar1090-db enrichment active (the default in most installations) - it provides the aircraft type descriptions used by this software

#### Finding your aircraft.json URL

Try each of the following in your browser, replacing `your-receiver` with your device's hostname or IP address, until you get a response containing a list of aircraft:

```
http://your-receiver/tar1090/data/aircraft.json
http://your-receiver:8080/data/aircraft.json
http://your-receiver/dump1090-fa/data/aircraft.json
http://your-receiver/skyaware/data/aircraft.json
```

The response should be a JSON object with an `"aircraft"` array.

#### Enabling tar1090 as your data source

Once you have the URL, open the web UI and go to **Providers** → **Provider Settings** → **tar1090**, enter the URL, then enable tar1090 (and order it ahead of FlightRadar24 if you want the local receiver to win) under **Providers** → **Lookup Priority**.

### Using OpenSky Network as your data source

[OpenSky Network](https://opensky-network.org) is a free, community-driven ADS-B network that can be used instead of (or ahead of) FlightRadar24 as the flight data source. No subscription is required - a free registered account gives you enough API credits for 30-second polling.

#### What you need

- A free account at [opensky-network.org](https://opensky-network.org)
- An API client created under Account -> API Clients (gives you a Client ID and Client Secret)

#### Enabling OpenSky Network

1. Log in to the FlightTracker web interface
2. Go to **Providers** → **Provider Settings** → **OpenSky Network** and enter your **Client ID** and **Client Secret**
3. Enable OpenSky (and order it ahead of FlightRadar24) under **Providers** → **Lookup Priority**
4. Save - the tracker will restart and begin fetching from OpenSky

---
## Satellite Tracking

To see when a particular satellite is overhead enter its [NORAD ID](https://celestrak.org/SATCAT/search.php) in the device config and it will show its trajectory, altitude, and speed.

## Running the tracker from the command line

The main entrypoint is the script at the repo root:

```bash
python3 flight-tracker.py help
```

The CLI supports a small set of commands for configuration and maintenance:

```text
Usage: python flight-tracker.py [command]
Commands:
  config                 Dump current configuration as JSON
  data                   Print the platform data directory path
  screen-test            Cycle each colour through 100/66/33% brightness (2s each)
  reset password         Clear web_password_hash in the config
  reset settings         Delete the config.json file
  cache clear            Wipe all on-disk cache files (routes and TLE)
  interface enable       Enable the web interface in the config
  interface disable      Disable the web interface in the config
  test flights           Test the flight provider chain (JSON output)
  test flights --provider tar1090
                         Test a single provider
  test tle               Test TLE satellite lookup
  help                   Show this help message
  --version              Print the program version
```

Test commands accept `--parameters` and `--interval`/`--limit` for repeated runs. Run `python flight-tracker.py test <target> --help` for details.

For normal operation, start the tracker with `python3 flight-tracker.py` and use the configuration file or the web settings UI to control its behaviour.

---

## Settings reference

This table is for reference if you've disabled the web interface (`web_interface_enabled: false`). All settings are otherwise accessible through the web UI.

| Key | Description | Default |
|-----|-------------|---------|
| `flight_location_mode` | `"simple"` (centre + radius) or `"advanced"` (drawn box + observer) | `"simple"` |
| `flight_lat` / `flight_lng` | Centre of the flight search zone (simple mode) | `55.87` / `-4.25` |
| `flight_radius` | Search radius in km (simple mode) | `20.0` |
| `flight_zone_tl_y` / `flight_zone_tl_x` | Search box top-left corner, lat/lng (advanced mode) | `56.05` / `-4.57` |
| `flight_zone_br_y` / `flight_zone_br_x` | Search box bottom-right corner, lat/lng (advanced mode) | `55.69` / `-3.93` |
| `flight_observer_lat` / `flight_observer_lng` | Observer position for weather, sunrise/sunset, satellite passes, and flight distance sorting (advanced mode) | `55.87` / `-4.25` |
| `flight_min_altitude` | Ignore aircraft below this altitude (metres) | `100.0` |
| `flight_max_altitude` | Ignore aircraft above this altitude (metres) | `10000.0` |
| `airport_display_style` | `0` = short code, `1` = airport name, `2` = abbreviated name, `3` = municipality, `4` = municipality + country | `0` |
| `home_airport_code` | IATA code of your local airport - highlighted on the display | `""` |
| `journey_blank_filler` | Filler shown for blank journey segments | `"???"` |
| `details` | Bottom row: `0` = aircraft make/model, `1` = altitude/speed/heading | `0` |
| `weatherapi_key` | API key for [weatherapi.com](https://www.weatherapi.com/pricing.aspx). Leave blank to disable weather | `""` |
| `weather_mode` | `0` = off, `1` = temperature only, `2` = temperature + 24-hour rainfall graph | `0` |
| `rain_sensitivity` | `0` = dry, `1` = moderate, `2` = wet | `1` |
| `temperature_unit` | `"c"` for Celsius, `"f"` for Fahrenheit | `"c"` |
| `speed_unit` | `"kmh"` for km/h, `"mph"` for miles/h, `"kts"` for knots | `"kmh"` |
| `height_unit` | `"m"` for metres, `"ft"` for feet | `"m"` |
| `theme` | `0` = default, `1` = monochrome, `2` = pastel | `0` |
| `brightness_mode` | `"simple"` (brightness slider + schedule) or `"advanced"` | `"simple"` |
| `screen_brightness` | Display brightness from `1` (dim) to `5` (full) | `3` |
| `screen_rotate` | Rotate the display by 180° | `false` |
| `display_speed` | Animation speed preset: `default`, `slower`, or `faster` | `"default"` |
| `screen_schedule_enabled` | Enable scheduled brightness changes | `false` |
| `screen_schedule_auto` | Use the brightness schedule automatically | `false` |
| `screen_schedule_start` | Schedule start time (`HH:MM`) | `"22:00"` |
| `screen_schedule_end` | Schedule end time (`HH:MM`) | `"07:00"` |
| `screen_schedule_brightness` | Brightness level used during the scheduled window | `0` |
| `screen_schedule_advanced` | Advanced schedule: JSON list of `{"time": "HH:MM", "brightness": 0-5}` pairs, sorted by time; each entry holds until the next, the last holds overnight | `[]` |
| `clock_24hr` | `true` for 24-hour clock | `true` |
| `date_format` | `0` = YYYY-MM-DD, `1` = DD-MM-YYYY, `2` = MM-DD-YYYY | `0` |
| `web_interface_enabled` | Enable the config UI and QR code on boot | `true` |
| `web_port` | TCP port for the Flask config server (1024-65535) | `8584` |
| `web_password_hash` | SHA-256 hash for the web UI password | `""` |
| `gpio_slowdown` | `1`-`4`; increase if the display flickers | `1` |
| `hat_pwm_enabled` | Enable PWM via Pi audio hardware (requires a solder bridge) | `true` |
| `loading_indicator` | Loading indicator mode: `"none"`, `"pixel"` (on-screen blink), or `"gpio"` (external LED) | `"pixel"` |
| `loading_led_gpio_pin` | GPIO pin number for the loading LED (only used when `loading_indicator` is `"gpio"`) | `""` |
| `flight_providers` | Ordered flight-provider list: `[{"provider": "fr24", "enabled": true}, ...]` | `[{"provider": "fr24", "enabled": true}]` |\
| `route_providers` | Ordered route-provider list (aerodatabox, hexdb, adsbdb, fr24) | see defaults |
| `providers` | Per-provider settings keyed by provider id (e.g. `providers.tar1090.url`) | `{}` |
| `max_flight_lookup` | Number of nearby flights to track at once | `5` |
| `max_flight_track_minutes` | Drop a flight after this many minutes in the rotation (0-1440); 0 tracks for as long as it stays in range. A flight that leaves and returns starts fresh | `0` |
| `callsign_format` | `"icao"` for ICAO callsign (e.g. BAW123), `"iata"` for IATA flight number (e.g. BA123) | `"icao"` |
| `satellite_tracking_enabled` | Enable satellite pass tracking | `true` |
| `satellite_norad_ids` | NORAD IDs for tracked satellites | `[25544]` |
| `satellite_min_elevation` | Minimum elevation for satellite passes | `20` |
| `satellite_max_count` | Maximum number of satellites to plot at once | `5` |
| `satellite_timeout_enabled` | Limit how long the satellite scene is shown per pass | `false` |
| `satellite_timeout_seconds` | Seconds from a pass's start (AOS) before the scene yields to flight tracking | `30` |
| `log_level` | Logging verbosity: `DEBUG`, `INFO`, `WARNING`, `ERROR`, or `CRITICAL` | `"INFO"` |

---

## Contributing

If you'd like to contribute to FlightTracker TUI - whether it's a bug report, feature idea, or pull request - please read [CONTRIBUTING.md](CONTRIBUTING.md).

---

## Acknowledgements

FlightTracker TUI is forked from the [FlightTracker project by Colin Waddell](https://github.com/ColinWaddell/FlightTracker).

---

## License

FlightTracker TUI is released under the GNU General Public License v3.0. See [LICENSE.md](LICENSE.md) for details.
