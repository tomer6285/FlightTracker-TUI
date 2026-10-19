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

    def __init__(
        self,
        use_alt_screen: bool = True,
        show_border: bool = True,
        scale: int | str | None = None,
    ):
        self._width = 64
        self._height = 32
        self._brightness = 50
        self._rotation = 0
        self._colour_order = "RGB"
        self._perm: tuple[int, int, int] | None = None

        self._scale: int | str = "auto"
        scale_env = os.environ.get("FLIGHTTRACKER_SCALE", os.environ.get("TUI_SCALE"))
        if scale is not None:
            self.set_scale(scale)
        elif scale_env is not None:
            self.set_scale(scale_env)
        else:
            self.set_scale("auto")

        self._use_alt_screen = use_alt_screen
        self._show_border = show_border
        self._in_alt_screen = False
        self._is_tty = sys.stdout.isatty()

        self._last_rendered_str = ""
        self._last_term_size: tuple[int, int] | None = None
        self._last_effective_scale: int | None = None

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

    @property
    def scale(self) -> int | str:
        return self._scale

    def set_scale(self, scale: int | str) -> None:
        """Set integer scale factor (>=1) or 'auto'."""
        if str(scale).strip().lower() in ("auto", "0"):
            self._scale = "auto"
            return
        try:
            val = int(scale)
            self._scale = max(1, val)
        except (ValueError, TypeError):
            self._scale = "auto"

    def get_scale(self) -> int | str:
        return self._scale

    def get_effective_scale(
        self, term_cols: int | None = None, term_rows: int | None = None
    ) -> int:
        """Return the active integer scale (>= 1)."""
        if self._scale != "auto":
            try:
                return max(1, int(self._scale))
            except (ValueError, TypeError):
                return 1

        if term_cols is None or term_rows is None:
            term_cols, term_rows = shutil.get_terminal_size((80, 24))

        border_x = 4 if self._show_border else 0
        border_y = 4 if self._show_border else 0
        avail_cols = max(1, term_cols - border_x)
        avail_rows = max(1, term_rows - border_y)

        scale_x = avail_cols // max(1, self._width)
        scale_y = (avail_rows * 2) // max(1, self._height)
        fit = min(scale_x, scale_y)
        return max(1, fit)

    def cycle_scale(self) -> int | str:
        """Cycle through scale modes: 1x -> 2x -> ... -> max_fit -> auto -> 1x."""
        term_cols, term_rows = shutil.get_terminal_size((80, 24))
        border_x = 4 if self._show_border else 0
        border_y = 4 if self._show_border else 0
        max_fit = max(
            1,
            min(
                (term_cols - border_x) // max(1, self._width),
                ((term_rows - border_y) * 2) // max(1, self._height),
            ),
        )

        if self._scale == "auto":
            self.set_scale(1)
        elif isinstance(self._scale, int):
            if self._scale < max_fit:
                self.set_scale(self._scale + 1)
            else:
                self.set_scale("auto")
        else:
            self.set_scale("auto")
        return self._scale

    def step_scale(self, delta: int) -> int:
        """Step scale up or down by delta."""
        eff = self.get_effective_scale()
        target = max(1, eff + delta)
        self.set_scale(target)
        return target

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
        scale=None,
        **kwargs,
    ):
        self._width = int(width)
        self._height = int(height)
        self._brightness = max(0, min(100, int(brightness)))
        self._rotation = rotation
        self._colour_order = colour_order or "RGB"
        if scale is not None:
            self.set_scale(scale)
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
        scale = self.get_effective_scale(term_cols, term_rows)

        char_rows = (self._height * scale + 1) // 2
        content_lines: list[str] = []

        for cy in range(char_rows):
            vy_top = cy * 2
            vy_bot = cy * 2 + 1
            y_top = vy_top // scale
            y_bot = vy_bot // scale

            line_parts: list[str] = []
            last_fg: tuple[int, int, int] | None = None
            last_bg: tuple[int, int, int] | None = None

            for x in range(self._width):
                c_top = (
                    self._get_pixel_color(canvas, x, y_top)
                    if y_top < self._height
                    else (0, 0, 0)
                )
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

                line_parts.append("▀" * scale)

            line_parts.append("\033[0m")
            content_lines.append("".join(line_parts))

        rendered_width = self._width * scale

        # Header with plane icon and display info
        scale_tag = f" @ {scale}x" + (" (auto)" if self._scale == "auto" else "")
        title = f" ✈ FlightTracker TUI [{self._width}x{self._height}{scale_tag}] "

        # Bottom status bar
        scale_stat = f"{scale}x (auto)" if self._scale == "auto" else f"{scale}x"
        status = f" Brightness: {self._brightness}% │ Scale: {scale_stat} [s] │ [Ctrl+C] Exit "
        if len(status) > rendered_width and rendered_width >= 40:
            status = f" Bri: {self._brightness}% │ Scale: {scale}x [s] │ ^C Exit "

        inner_width = max(rendered_width, len(title), len(status))
        box_width = inner_width + 4  # "│ " + content + " │"
        box_height = char_rows + 4  # top border, header, content, bottom border

        if self._show_border and term_cols >= box_width and term_rows >= box_height:
            pad_left_len = max(0, (term_cols - box_width) // 2)
            pad_left = " " * pad_left_len
            pad_top_len = max(0, (term_rows - box_height) // 2)
            pad_top = "\n" * pad_top_len

            dashes = max(0, inner_width - len(title))
            top_border = f"{pad_left}\033[1;36m┌{title}{'─' * dashes}──┐\033[0m\n"

            bottom_dashes = max(0, inner_width - len(status))
            bottom_border = (
                f"{pad_left}\033[1;36m└{status}{'─' * bottom_dashes}──┘\033[0m\n"
            )

            pad_content = " " * max(0, inner_width - rendered_width)
            body_lines = [
                f"{pad_left}\033[1;36m│\033[0m {row}{pad_content}\033[0m \033[1;36m│\033[0m\n"
                for row in content_lines
            ]

            frame = pad_top + top_border + "".join(body_lines) + bottom_border
        else:
            # Fallback for small terminals or no-border mode
            frame = "\n".join(content_lines) + "\n"

        return frame

    def swap(self, canvas: TUICanvas) -> TUICanvas:
        """Push the canvas to the terminal (VSync / show)."""
        term_cols, term_rows = shutil.get_terminal_size((80, 24))
        scale = self.get_effective_scale(term_cols, term_rows)

        frame_str = self.render_to_string(canvas)
        self._last_rendered_str = frame_str

        if self._is_tty:
            need_clear = False
            if not self._in_alt_screen and self._use_alt_screen:
                # Enter alternate screen buffer, hide cursor, clear
                sys.stdout.write("\033[?1049h\033[?25l\033[2J")
                self._in_alt_screen = True
                need_clear = True

            if (
                term_cols,
                term_rows,
            ) != self._last_term_size or scale != self._last_effective_scale:
                need_clear = True
                self._last_term_size = (term_cols, term_rows)
                self._last_effective_scale = scale

            prefix = "\033[2J\033[H" if need_clear else "\033[H"
            sys.stdout.write(prefix + frame_str)
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
                elif ch in ("s", "S"):
                    self.cycle_scale()
                elif ch == "]":
                    self.step_scale(1)
                elif ch == "[":
                    self.step_scale(-1)
                elif ch in ("0",):
                    self.set_scale("auto")
                elif ch in ("1", "2", "3", "4", "5"):
                    self.set_scale(int(ch))
        except OSError:
            pass

    def save_screenshot(
        self,
        canvas: TUICanvas | None = None,
        path: str | None = None,
        scale: int | None = None,
    ) -> str:
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

        if scale is not None and scale > 1:
            img = img.resize(
                (self._width * scale, self._height * scale),
                resample=Image.Resampling.NEAREST,
            )

        img.save(path)
        return path
