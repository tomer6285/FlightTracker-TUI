"""Unit tests for TUIPanel, TUICanvas, and panel_factory selection."""

from __future__ import annotations

import os
from unittest.mock import patch

from PIL import Image

from display.panel_factory import get_panel, reset_panel
from display.rgbpanel import Colour
from display.rgbpanel_tui import TUICanvas, TUIPanel


class TestTUICanvas:
    def test_init_and_properties(self):
        c = TUICanvas(64, 32)
        assert c.cols == 64
        assert c.rows == 32
        assert c.width == 64
        assert c.height == 32
        assert len(c.buf) == 64 * 32
        assert c.get_pixel(0, 0) == (0, 0, 0)

    def test_set_and_get_pixel(self):
        c = TUICanvas(10, 10)
        c.set_pixel(2, 3, 255, 128, 64)
        assert c.get_pixel(2, 3) == (255, 128, 64)
        # Out of bounds should return (0, 0, 0) and not raise
        assert c.get_pixel(15, 15) == (0, 0, 0)
        assert c.get_pixel(-1, 0) == (0, 0, 0)

    def test_pixel_clamping(self):
        c = TUICanvas(10, 10)
        c.set_pixel(0, 0, -50, 300, 128)
        assert c.get_pixel(0, 0) == (0, 255, 128)

    def test_clear_and_fill(self):
        c = TUICanvas(4, 4)
        c.fill(10, 20, 30)
        assert c.get_pixel(0, 0) == (10, 20, 30)
        assert c.get_pixel(3, 3) == (10, 20, 30)
        c.clear()
        assert c.get_pixel(0, 0) == (0, 0, 0)
        assert c.get_pixel(3, 3) == (0, 0, 0)

    def test_copy(self):
        c1 = TUICanvas(5, 5)
        c1.set_pixel(1, 1, 100, 100, 100)
        c2 = c1.copy()
        assert c2.get_pixel(1, 1) == (100, 100, 100)
        # Modify c2, c1 should remain unchanged
        c2.set_pixel(1, 1, 200, 200, 200)
        assert c1.get_pixel(1, 1) == (100, 100, 100)


class TestTUIPanel:
    def test_initial_state(self):
        panel = TUIPanel(use_alt_screen=False, show_border=False)
        assert panel.width == 64
        assert panel.height == 32
        assert panel.get_brightness() == 50
        assert panel.is_pi5 is False
        assert panel.is_matrix is False

    def test_init_matrix(self):
        panel = TUIPanel(use_alt_screen=False)
        panel.init_matrix(
            width=64, height=64, brightness=80, rotation=180, colour_order="BGR"
        )
        assert panel.width == 64
        assert panel.height == 64
        assert panel.get_brightness() == 80
        assert panel._rotation == 180
        assert panel._colour_order == "BGR"

    def test_set_brightness_clamping(self):
        panel = TUIPanel(use_alt_screen=False)
        panel.set_brightness(-10)
        assert panel.get_brightness() == 0
        panel.set_brightness(150)
        assert panel.get_brightness() == 100
        panel.set_brightness(75)
        assert panel.get_brightness() == 75

    def test_draw_primitives(self):
        panel = TUIPanel(use_alt_screen=False)
        canvas = panel.create_canvas()

        # Draw line
        panel.draw_line(canvas, 0, 0, 4, 0, Colour(255, 0, 0))
        for x in range(5):
            assert canvas.get_pixel(x, 0) == (255, 0, 0)

        # Draw square
        panel.draw_square(canvas, 10, 10, 13, 13, Colour(0, 255, 0))
        for x in range(10, 13):
            for y in range(10, 13):
                assert canvas.get_pixel(x, y) == (0, 255, 0)

        # Draw circle
        panel.draw_circle(canvas, 20, 20, 3, Colour(0, 0, 255))
        assert canvas.get_pixel(23, 20) == (0, 0, 255)
        assert canvas.get_pixel(17, 20) == (0, 0, 255)

    def test_draw_image_with_alpha(self):
        panel = TUIPanel(use_alt_screen=False)
        canvas = panel.create_canvas()

        # Create 2x2 RGBA image: top-left opaque red, top-right transparent
        img = Image.new("RGBA", (2, 2), (0, 0, 0, 0))
        img.putpixel((0, 0), (255, 0, 0, 255))
        img.putpixel((1, 0), (0, 255, 0, 0))  # Fully transparent

        panel.draw_image(canvas, 5, 5, img)
        assert canvas.get_pixel(5, 5) == (255, 0, 0)
        assert canvas.get_pixel(6, 5) == (0, 0, 0)  # Transparent pixel was skipped

    def test_render_to_string_halfblocks(self):
        panel = TUIPanel(use_alt_screen=False, show_border=False)
        panel.init_matrix(width=4, height=4, brightness=100)
        canvas = panel.create_canvas()
        canvas.set_pixel(0, 0, 255, 0, 0)  # Top pixel: red
        canvas.set_pixel(0, 1, 0, 0, 255)  # Bottom pixel: blue

        rendered = panel.render_to_string(canvas)
        assert "▀" in rendered
        # Red foreground (\033[38;2;255;0;0m)
        assert "38;2;255;0;0m" in rendered
        # Blue background (\033[48;2;0;0;255m)
        assert "48;2;0;0;255m" in rendered

    def test_brightness_scaling_in_render(self):
        panel = TUIPanel(use_alt_screen=False, show_border=False)
        panel.init_matrix(width=2, height=2, brightness=50)
        canvas = panel.create_canvas()
        canvas.set_pixel(0, 0, 200, 100, 50)

        col = panel._get_pixel_color(canvas, 0, 0)
        assert col == (100, 50, 25)

    def test_rotation_in_render(self):
        panel = TUIPanel(use_alt_screen=False, show_border=False)
        panel.init_matrix(width=10, height=10, brightness=100, rotation=180)
        canvas = panel.create_canvas()
        canvas.set_pixel(0, 0, 255, 255, 255)

        # In 180 rotation, (0, 0) maps to (9, 9)
        col_9_9 = panel._get_pixel_color(canvas, 9, 9)
        assert col_9_9 == (255, 255, 255)
        col_0_0 = panel._get_pixel_color(canvas, 0, 0)
        assert col_0_0 == (0, 0, 0)

    def test_colour_order_in_render(self):
        panel = TUIPanel(use_alt_screen=False, show_border=False)
        panel.init_matrix(width=2, height=2, brightness=100, colour_order="BGR")
        canvas = panel.create_canvas()
        canvas.set_pixel(0, 0, 255, 128, 64)  # R=255, G=128, B=64

        # In BGR order, channel 0 carries B(64), channel 1 carries G(128), channel 2 carries R(255)
        col = panel._get_pixel_color(canvas, 0, 0)
        assert col == (64, 128, 255)

    def test_save_screenshot(self, tmp_path):
        panel = TUIPanel(use_alt_screen=False)
        canvas = panel.create_canvas()
        canvas.fill(100, 150, 200)

        out_file = str(tmp_path / "shot.png")
        saved = panel.save_screenshot(canvas, path=out_file)
        assert os.path.exists(saved)
        loaded = Image.open(saved)
        assert loaded.size == (panel.width, panel.height)
        assert loaded.getpixel((0, 0)) == (50, 75, 100)  # default brightness 50%

    def test_swap_non_tty(self):
        panel = TUIPanel(use_alt_screen=False)
        canvas = panel.create_canvas()
        # Non-tty should execute without throwing
        res = panel.swap(canvas)
        assert res is canvas
        assert len(panel._last_rendered_str) > 0

    def test_scale_setting_and_effective(self):
        panel = TUIPanel(use_alt_screen=False, show_border=True)
        assert panel.scale == "auto"
        # Small terminal (80x24) -> scale 1
        assert panel.get_effective_scale(80, 24) == 1
        # Large terminal (140x40) -> scale 2
        assert panel.get_effective_scale(140, 40) == 2
        # Huge terminal (220x60) -> scale 3
        assert panel.get_effective_scale(220, 60) == 3

        # Explicit scale
        panel.set_scale(2)
        assert panel.scale == 2
        assert panel.get_effective_scale(80, 24) == 2

        panel.set_scale("auto")
        assert panel.scale == "auto"

        panel.set_scale("invalid")
        assert panel.scale == "auto"

    def test_scale_from_env(self):
        with patch.dict(os.environ, {"FLIGHTTRACKER_SCALE": "3"}):
            panel = TUIPanel(use_alt_screen=False)
            assert panel.scale == 3

    def test_cycle_and_step_scale(self):
        panel = TUIPanel(use_alt_screen=False, show_border=True)
        panel.set_scale(1)
        panel.step_scale(1)
        assert panel.scale == 2
        panel.step_scale(-1)
        assert panel.scale == 1

        # cycle_scale with mock terminal (140x40 -> max_fit=2)
        with patch("shutil.get_terminal_size", return_value=(140, 40)):
            panel.set_scale(1)
            panel.cycle_scale()
            assert panel.scale == 2
            panel.cycle_scale()
            assert panel.scale == "auto"
            panel.cycle_scale()
            assert panel.scale == 1

    def test_render_to_string_scaled(self):
        panel = TUIPanel(use_alt_screen=False, show_border=False, scale=2)
        panel.init_matrix(width=4, height=4, brightness=100)
        canvas = panel.create_canvas()
        canvas.set_pixel(0, 0, 255, 0, 0)
        rendered = panel.render_to_string(canvas)
        assert "▀▀" in rendered

    def test_save_screenshot_scaled(self, tmp_path):
        panel = TUIPanel(use_alt_screen=False)
        canvas = panel.create_canvas()
        canvas.fill(100, 150, 200)

        out_file = str(tmp_path / "shot_scaled.png")
        saved = panel.save_screenshot(canvas, path=out_file, scale=2)
        assert os.path.exists(saved)
        loaded = Image.open(saved)
        assert loaded.size == (panel.width * 2, panel.height * 2)

    def test_poll_input_scale_keys(self):
        panel = TUIPanel(use_alt_screen=False)
        panel.set_scale(1)

        with (
            patch("sys.stdin.isatty", return_value=True),
            patch("select.select", return_value=([True], [], [])),
            patch("sys.stdin.read", side_effect=["s", "]", "[", "2", "0"]),
        ):
            panel._poll_input()
            # s cycled from 1
            panel._poll_input()
            # ] stepped up
            panel._poll_input()
            # [ stepped down
            panel._poll_input()
            assert panel.scale == 2
            panel._poll_input()
            assert panel.scale == "auto"


class TestPanelFactory:
    def setup_method(self):
        reset_panel()

    def teardown_method(self):
        reset_panel()

    def test_default_returns_tui_panel(self):
        with patch.dict(os.environ, {}, clear=True):
            p = get_panel()
            assert isinstance(p, TUIPanel)

    def test_explicit_tui_env(self):
        with patch.dict(os.environ, {"FLIGHTTRACKER_PANEL": "tui"}):
            p = get_panel()
            assert isinstance(p, TUIPanel)

    def test_singleton_cached(self):
        p1 = get_panel()
        p2 = get_panel()
        assert p1 is p2
        reset_panel()
        p3 = get_panel()
        assert p3 is not p1
