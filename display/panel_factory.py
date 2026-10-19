"""
Panel factory - selects the appropriate display driver at runtime.

For FlightTracker-TUI, the primary driver is the TUIPanel (terminal UI display).
Drivers for Pi 5 (piomatter), Pi 3/4 (rgbmatrix), and the desktop pygame simulator
remain supported as alternatives via the FLIGHTTRACKER_PANEL environment variable.
"""

import importlib
import os

_panel = None


def get_panel():
    """Return the singleton RGBPanel instance, creating it if needed."""
    global _panel
    if _panel is not None:
        return _panel

    driver_choice = os.environ.get("FLIGHTTRACKER_PANEL", "tui").lower()

    if driver_choice in ("tui", "terminal", "default"):
        try:
            mod = importlib.import_module("display.rgbpanel_tui")
            _panel = mod.TUIPanel()
            return _panel
        except ImportError:
            pass

    if driver_choice == "pi5":
        try:
            mod = importlib.import_module("display.rgbpanel_piomatter")
            _panel = mod.PiomatterPanel()
            return _panel
        except ImportError:
            pass

    if driver_choice in ("matrix", "pi", "pi3", "pi4"):
        try:
            mod = importlib.import_module("display.rgbpanel_rgbmatrix")
            _panel = mod.RGBMatrixPanel()
            return _panel
        except ImportError:
            pass

    if driver_choice == "simulator":
        try:
            mod = importlib.import_module("display.rgbpanel_simulator")
            _panel = mod.SimulatorPanel()
            return _panel
        except ImportError:
            pass

    # Default fallback: TUI display
    try:
        mod = importlib.import_module("display.rgbpanel_tui")
        _panel = mod.TUIPanel()
        return _panel
    except ImportError:
        pass

    # Fall back to desktop pygame simulator
    try:
        mod = importlib.import_module("display.rgbpanel_simulator")
        _panel = mod.SimulatorPanel()
        return _panel
    except ImportError:
        pass

    raise ImportError(
        "No display driver available. "
        "Ensure display.rgbpanel_tui is available for TUI display mode."
    )


def reset_panel():
    """Clear the cached panel (used for testing)."""
    global _panel
    _panel = None
