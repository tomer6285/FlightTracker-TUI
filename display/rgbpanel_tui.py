"""
TUIPanel - Terminal User Interface (TUI) display driver for FlightTracker.

Renders the RGB display canvas directly in any ANSI-compatible terminal
using Unicode half-block characters (▀) with 24-bit TrueColor escaping.
Each character cell displays two vertical pixels (top half foreground,
bottom half background), resulting in square pixel rendering that matches
a physical RGB LED matrix panel.
"""

from __future__ import annotations

import atexit
import contextlib
import os
import select
import shutil
import signal
import sys
from datetime import datetime
from typing import TYPE_CHECKING

from display.bdf_font import BDFFont
from display.bdf_font import draw_text as bdf_draw_text
from display.rgbpanel import Colour, RGBPanel, channel_permutation

if TYPE_CHECKING:
    from PIL import Image


# ---------------------------------------------------------------------------
# TUICanvas - flat pixel buffer matching the matrix display grid
# ---------------------------------------------------------------------------


class TUICanvas:
    """In-memory pixel buffer for the TUI display."""

    __slots__ = ("cols", "rows", "buf")

    def __init__(self, cols: int, rows: int):
        self.cols = cols
        self.rows = rows
        # Flat list: index = y * cols + x, value = (r, g, b)
        self.buf: list[tuple[int, int, int]] = [(0, 0, 0)] * (cols * rows)

    @property
    def width(self) -> int:
        return self.cols

    @property
    def height(self) -> int:
        return self.rows

    def set_pixel(self, x: int, y: int, r: int, g: int, b: int) -> None:
        if 0 <= x < self.cols and 0 <= y < self.rows:
            self.buf[y * self.cols + x] = (
                max(0, min(255, int(r))),
                max(0, min(255, int(g))),
                max(0, min(255, int(b))),
            )

    def get_pixel(self, x: int, y: int) -> tuple[int, int, int]:
        if 0 <= x < self.cols and 0 <= y < self.rows:
            return self.buf[y * self.cols + x]
        return (0, 0, 0)

    def clear(self) -> None:
        self.buf = [(0, 0, 0)] * (self.cols * self.rows)

    def fill(self, r: int, g: int, b: int) -> None:
        r_c = max(0, min(255, int(r)))
        g_c = max(0, min(255, int(g)))
        b_c = max(0, min(255, int(b)))
        self.buf = [(r_c, g_c, b_c)] * (self.cols * self.rows)

    def copy(self) -> TUICanvas:
        c = TUICanvas(self.cols, self.rows)
        c.buf = list(self.buf)
        return c


# ---------------------------------------------------------------------------
# Drawing helpers (operate on TUICanvas or any compatible canvas)
# ---------------------------------------------------------------------------


def _draw_line(canvas, x0: int, y0: int, x1: int, y1: int, colour) -> None:
    r, g, b = colour.red, colour.green, colour.blue
    dx = abs(x1 - x0)
    dy = abs(y1 - y0)
    sx = 1 if x0 < x1 else -1
    sy = 1 if y0 < y1 else -1
    err = dx - dy

    while True:
        canvas.set_pixel(x0, y0, r, g, b)
        if x0 == x1 and y0 == y1:
            break
        e2 = 2 * err
        if e2 > -dy:
            err -= dy
            x0 += sx
        if e2 < dx:
            err += dx
            y0 += sy


def _draw_circle(canvas, cx: int, cy: int, radius: int, colour) -> None:
    r, g, b = colour.red, colour.green, colour.blue

    def _plot8(dx, dy):
        canvas.set_pixel(cx + dx, cy + dy, r, g, b)
        canvas.set_pixel(cx - dx, cy + dy, r, g, b)
        canvas.set_pixel(cx + dx, cy - dy, r, g, b)
        canvas.set_pixel(cx - dx, cy - dy, r, g, b)
        canvas.set_pixel(cx + dy, cy + dx, r, g, b)
        canvas.set_pixel(cx - dy, cy + dx, r, g, b)
        canvas.set_pixel(cx + dy, cy - dx, r, g, b)
        canvas.set_pixel(cx - dy, cy - dx, r, g, b)

    x, y = 0, radius
    d = 3 - 2 * radius
    while x <= y:
        _plot8(x, y)
        if d < 0:
            d += 4 * x + 6
        else:
            d += 4 * (x - y) + 10
            y -= 1
        x += 1


def _draw_square(canvas, x0: int, y0: int, x1: int, y1: int, colour) -> None:
    r, g, b = colour.red, colour.green, colour.blue
    left, right = (x0, x1) if x0 <= x1 else (x1, x0)
    top, bottom = (y0, y1) if y0 <= y1 else (y1, y0)
    for x in range(left, right):
        _draw_line(canvas, x, top, x, bottom, Colour(r, g, b))


# ---------------------------------------------------------------------------
# TUIPanel implementation
# ---------------------------------------------------------------------------


class TUIPanel(RGBPanel):
    """Terminal User Interface (TUI) display driver for FlightTracker."""

    def __init__(self, use_alt_screen: bool = True, show_border: bool = True):
        self._width = 64
        self._height = 32
        self._brightness = 50
        self._rotation = 0
        self._colour_order = "RGB"
        self._perm: tuple[int, int, int] | None = None

        self._use_alt_screen = use_alt_screen
        self._show_border = show_border
        self._in_alt_screen = False
        self._is_tty = sys.stdout.isatty()

        self._last_rendered_str = ""

        # Captures directory
        self._capture_dir = os.path.join(
            os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "captures"
        )

        # Register cleanup on process exit
        atexit.register(self.cleanup)
        with contextlib.suppress(ValueError, AttributeError):
            signal.signal(signal.SIGTERM, self._signal_handler)

    def _signal_handler(self, _signum, _frame):
        self.cleanup()
        sys.exit(0)

    def cleanup(self) -> None:
        """Restore terminal state (cursor, alternate screen, colors)."""
        if self._in_alt_screen and self._is_tty:
            with contextlib.suppress(Exception):
                sys.stdout.write("\033[?25h\033[0m\033[?1049l")
                sys.stdout.flush()
            self._in_alt_screen = False

    @property
    def is_pi5(self) -> bool:
        return False

    @property
    def is_matrix(self) -> bool:
        return False

    @property
    def width(self) -> int:
        return self._width

    @property
    def height(self) -> int:
        return self._height

    # -- RGBPanel interface ------------------------------------------------

    def init_matrix(
        self,
        width=64,
        height=32,
        brightness=50,
        rotation=0,
        hat_pwm=True,
        gpio_slowdown=1,
        colour_order="RGB",
    ):
        self._width = int(width)
        self._height = int(height)
        self._brightness = max(0, min(100, int(brightness)))
        self._rotation = rotation
        self._colour_order = colour_order or "RGB"
        try:
            self._perm = channel_permutation(self._colour_order)
        except ValueError:
            self._perm = None

    def create_canvas(self) -> TUICanvas:
        canvas = TUICanvas(self._width, self._height)
        canvas.clear()
        return canvas

    def load_font(self, path: str) -> BDFFont:
        return BDFFont(path)

    def draw_text(self, canvas, font, x: int, y: int, colour, text: str) -> int:
        # BDF fonts are baseline-relative
        y = y - 1
        return bdf_draw_text(canvas, font, x, y, colour, text)

    def draw_line(self, canvas, x0: int, y0: int, x1: int, y1: int, colour) -> None:
        _draw_line(canvas, x0, y0, x1, y1, colour)

    def draw_circle(self, canvas, cx: int, cy: int, radius: int, colour) -> None:
        _draw_circle(canvas, cx, cy, radius, colour)

    def set_pixel(self, canvas, x: int, y: int, r: int, g: int, b: int) -> None:
        canvas.set_pixel(x, y, r, g, b)

    def fill(self, canvas, r: int, g: int, b: int) -> None:
        canvas.fill(r, g, b)

    def clear(self, canvas) -> None:
        canvas.clear()

    def set_brightness(self, percent: int) -> None:
        self._brightness = max(0, min(100, int(percent)))

    def get_brightness(self) -> int:
        return self._brightness

    def draw_square(self, canvas, x0: int, y0: int, x1: int, y1: int, colour) -> None:
        _draw_square(canvas, x0, y0, x1, y1, colour)

    def draw_image(self, canvas, x: int, y: int, image: Image.Image) -> None:
        """Draw a PIL Image at (x, y), skipping transparent pixels."""
        if image.mode != "RGBA":
            image = image.convert("RGBA")
        rgb = image.convert("RGB")
        alpha = image.split()[3]
        for py in range(image.height):
            for px in range(image.width):
                if alpha.getpixel((px, py)) > 0:
                    r, g, b = rgb.getpixel((px, py))
                    canvas.set_pixel(x + px, y + py, r, g, b)

    def make_colour(self, r: int, g: int, b: int) -> Colour:
        return Colour(r, g, b)

    # -- Terminal Rendering ------------------------------------------------

    def _get_pixel_color(
        self, canvas: TUICanvas, x: int, y: int
    ) -> tuple[int, int, int]:
        """Fetch pixel (x, y) with rotation, channel remap, and brightness applied."""
        if self._rotation == 180:
            rx = self._width - 1 - x
            ry = self._height - 1 - y
        else:
            rx = x
            ry = y

        p = canvas.get_pixel(rx, ry)

        if self._perm is not None:
            p = (p[self._perm[0]], p[self._perm[1]], p[self._perm[2]])

        if self._brightness != 100:
            scale = self._brightness / 100.0
            p = (
                int(round(p[0] * scale)),
                int(round(p[1] * scale)),
                int(round(p[2] * scale)),
            )

        return p

    def render_to_string(self, canvas: TUICanvas) -> str:
        """Render the canvas to an ANSI TrueColor string with half-blocks."""
        term_cols, term_rows = shutil.get_terminal_size((80, 24))

        char_rows = self._height // 2
        content_lines: list[str] = []

        for cy in range(char_rows):
            y_top = cy * 2
            y_bot = y_top + 1

            line_parts: list[str] = []
            last_fg: tuple[int, int, int] | None = None
            last_bg: tuple[int, int, int] | None = None

            for x in range(self._width):
                c_top = self._get_pixel_color(canvas, x, y_top)
                c_bot = (
                    self._get_pixel_color(canvas, x, y_bot)
                    if y_bot < self._height
                    else (0, 0, 0)
                )

                if c_top != last_fg:
                    line_parts.append(f"\033[38;2;{c_top[0]};{c_top[1]};{c_top[2]}m")
                    last_fg = c_top

                if c_bot != last_bg:
                    line_parts.append(f"\033[48;2;{c_bot[0]};{c_bot[1]};{c_bot[2]}m")
                    last_bg = c_bot

                line_parts.append("▀")

            line_parts.append("\033[0m")
            content_lines.append("".join(line_parts))

        # Check if terminal is large enough for box borders and padding
        box_width = self._width + 4  # "│ " + 64 + " │"
        box_height = char_rows + 4  # top border, header, content, bottom border

        if self._show_border and term_cols >= box_width and term_rows >= box_height:
            pad_left_len = max(0, (term_cols - box_width) // 2)
            pad_left = " " * pad_left_len
            pad_top_len = max(0, (term_rows - box_height) // 2)
            pad_top = "\n" * pad_top_len

            # Header with plane icon and display info
            title = f" ✈ FlightTracker TUI [{self._width}x{self._height}] "
            dashes = max(0, self._width - len(title))
            top_border = f"{pad_left}\033[1;36m┌{title}{'─' * dashes}──┐\033[0m\n"

            # Bottom status bar
            status = f" Brightness: {self._brightness}% │ [Ctrl+C] Exit "
            bottom_dashes = max(0, self._width - len(status))
            bottom_border = f"{pad_left}\033[1;36m└{status}{'─' * bottom_dashes}──┘\033[0m\n"

            body_lines = [
                f"{pad_left}\033[1;36m│\033[0m {row}\033[0m \033[1;36m│\033[0m\n"
                for row in content_lines
            ]

            frame = pad_top + top_border + "".join(body_lines) + bottom_border
        else:
            # Fallback for small terminals or no-border mode
            frame = "\n".join(content_lines) + "\n"

        return frame

    def swap(self, canvas: TUICanvas) -> TUICanvas:
        """Push the canvas to the terminal (VSync / show)."""
        frame_str = self.render_to_string(canvas)
        self._last_rendered_str = frame_str

        if self._is_tty:
            if not self._in_alt_screen and self._use_alt_screen:
                # Enter alternate screen buffer, hide cursor, clear
                sys.stdout.write("\033[?1049h\033[?25l\033[2J")
                self._in_alt_screen = True

            # Move cursor home and write frame
            sys.stdout.write("\033[H" + frame_str)
            sys.stdout.flush()

            self._poll_input()

        return canvas

    def _poll_input(self) -> None:
        """Poll for keypresses non-blockingly if stdin is an interactive TTY."""
        if not sys.stdin.isatty():
            return
        try:
            rlist, _, _ = select.select([sys.stdin], [], [], 0)
            if rlist:
                ch = sys.stdin.read(1)
                if ch in ("q", "Q"):
                    self.cleanup()
                    raise KeyboardInterrupt
                elif ch in ("+", "="):
                    self.set_brightness(self._brightness + 10)
                elif ch in ("-", "_"):
                    self.set_brightness(self._brightness - 10)
                elif ch in ("p", "P"):
                    self.save_screenshot()
        except OSError:
            pass

    def save_screenshot(self, canvas: TUICanvas | None = None, path: str | None = None) -> str:
        """Save the current canvas as a PNG screenshot."""
        from PIL import Image

        os.makedirs(self._capture_dir, exist_ok=True)
        if path is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            path = os.path.join(self._capture_dir, f"capture_{timestamp}.png")

        img = Image.new("RGB", (self._width, self._height))
        if canvas is not None:
            for y in range(self._height):
                for x in range(self._width):
                    img.putpixel((x, y), self._get_pixel_color(canvas, x, y))

        img.save(path)
        return path
