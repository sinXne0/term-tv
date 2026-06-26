import importlib.util
import os
import sys
import unittest
from pathlib import Path
from unittest import mock


MODULE_PATH = Path(__file__).with_name("term_tv.py")
SPEC = importlib.util.spec_from_file_location("term_tv", MODULE_PATH)
assert SPEC and SPEC.loader
tvp = importlib.util.module_from_spec(SPEC)
sys.modules["term_tv"] = tvp
SPEC.loader.exec_module(tvp)


class RenderTests(unittest.TestCase):
    def test_format_time(self):
        self.assertEqual(tvp.format_time(0), "00:00")
        self.assertEqual(tvp.format_time(125.9), "02:05")

    def test_two_rows_become_one_half_block_row(self):
        frame = bytes([255, 0, 0, 0, 0, 255])
        rendered = tvp.render_frame(frame, width=1, height=2)
        self.assertTrue(rendered.startswith(b"\x1b[1;1H"))
        self.assertIn(b"\x1b[38;2;255;0;0;48;2;0;0;255m", rendered)
        self.assertEqual(rendered.count("▀".encode()), 1)
        self.assertNotIn(b"\n", rendered)

    def test_video_extensions_include_common_formats(self):
        self.assertIn(".mp4", tvp.VIDEO_EXTENSIONS)
        self.assertIn(".mkv", tvp.VIDEO_EXTENSIONS)
        self.assertIn(".webm", tvp.VIDEO_EXTENSIONS)

    def test_parse_extended_m3u(self):
        playlist = """#EXTM3U
#EXTINF:-1,News Channel
https://example.com/live/news.m3u8
#EXTINF:-1,Local Station
station.mp4
"""
        channels = tvp.parse_playlist(playlist, "https://example.com/list.m3u")
        self.assertEqual(channels[0].name, "News Channel")
        self.assertEqual(channels[0].source, "https://example.com/live/news.m3u8")
        self.assertEqual(channels[1].source, "https://example.com/station.mp4")

    def test_url_detection_rejects_other_schemes(self):
        self.assertTrue(tvp.is_url("https://example.com/live.m3u8"))
        self.assertFalse(tvp.is_url("file:///tmp/video.mp4"))

    def test_parse_plain_m3u(self):
        channels = tvp.parse_playlist("https://example.com/live.m3u8")
        self.assertEqual(channels[0].name, "live.m3u8")

    def test_built_in_guide_has_cartoon_and_news_channels(self):
        names = [channel.name for channel in tvp.BUILT_IN_CHANNELS]
        self.assertTrue(any("CARTOONS" in name for name in names))
        self.assertTrue(any("NEWS" in name for name in names))

    def test_quality_presets_trade_resolution_for_speed(self):
        self.assertLess(
            tvp.QUALITY_PROFILES["fast"].fps,
            tvp.QUALITY_PROFILES["high"].fps,
        )
        self.assertLess(
            tvp.QUALITY_PROFILES["fast"].max_width,
            tvp.QUALITY_PROFILES["high"].max_width,
        )
        self.assertEqual(tvp.QUALITY_PROFILES["high"].renderer, "quadrant")
        self.assertEqual(tvp.QUALITY_PROFILES["high"].scaler, "lanczos")
        self.assertGreaterEqual(tvp.QUALITY_PROFILES["high"].fps, 24)

    def test_quadrant_renderer_uses_one_cell_for_four_pixels(self):
        frame = bytes(
            [
                255, 255, 255, 0, 0, 0,
                0, 0, 0, 255, 255, 255,
            ]
        )
        rendered = tvp.render_frame_quadrant(frame, width=2, height=2)
        self.assertTrue(rendered.startswith(b"\x1b[1;1H"))
        self.assertEqual(sum(rendered.count(char.encode()) for char in tvp.QUADRANTS[1:]), 1)
        self.assertIn("▚".encode(), rendered)
        self.assertNotIn(b"\n", rendered)

    def test_renderer_positions_each_row_without_newlines(self):
        frame = bytes([0, 0, 0] * 8)
        rendered = tvp.render_frame(frame, width=2, height=4)
        self.assertIn(b"\x1b[1;1H", rendered)
        self.assertIn(b"\x1b[2;1H", rendered)
        self.assertNotIn(b"\n", rendered)

    def test_quadrant_palette_separates_equal_brightness_colors(self):
        red = (255, 0, 0)
        dark_green = (0, 130, 0)
        mask, foreground, background = tvp.quadrant_palette(
            [red, dark_green, dark_green, red]
        )
        self.assertNotEqual(mask, 15)
        self.assertEqual({foreground, background}, {red, dark_green})

    def test_high_quality_filter_uses_lanczos_chroma_scaling(self):
        player = tvp.Player(
            "video.mp4",
            tvp.VideoInfo(width=1920, height=1080, fps=30, duration=60),
            no_audio=True,
            quality="high",
            renderer="text",
        )
        player.width, player.height = 158, 44
        video_filter = player.video_filter()
        self.assertIn("flags=lanczos+accurate_rnd+full_chroma_int", video_filter)

    def test_quadrant_dimensions_double_horizontal_samples(self):
        player = tvp.Player(
            "video.mp4",
            tvp.VideoInfo(width=1920, height=1080, fps=30, duration=60),
            no_audio=True,
            quality="balanced",
            renderer="text",
        )
        width, height = player.dimensions()
        self.assertGreater(width, height * 3)

    def test_dimensions_leave_last_terminal_column_unused(self):
        player = tvp.Player(
            "video.mp4",
            tvp.VideoInfo(width=1920, height=1080, fps=30, duration=60),
            no_audio=True,
            quality="high",
            renderer="text",
        )
        with mock.patch.object(
            tvp.shutil, "get_terminal_size", return_value=os.terminal_size((80, 24))
        ):
            width, _ = player.dimensions()
        self.assertLessEqual(width // 2, 79)

    def test_kitty_root_command_contains_graphics_escape(self):
        command = tvp.kitty_root_frame(
            bytes([255, 0, 0]), 1, 1, 80, 23, image_id=2
        )
        self.assertTrue(command.startswith(b"\x1b_G"))
        self.assertIn(b"a=T,f=24", command)
        self.assertIn(b"p=1", command)
        self.assertIn(b"i=2", command)

    def test_kitty_delete_frees_image_data(self):
        command = tvp.kitty_delete_image(2)
        self.assertIn(b"a=d,d=I,i=2", command)

    def test_text_renderer_does_not_enable_synchronized_output(self):
        self.assertFalse(hasattr(tvp, "SYNC_START"))

    def test_auto_renderer_uses_native_graphics_in_kitty(self):
        old_term = os.environ.get("TERM")
        old_kitty_window = os.environ.get("KITTY_WINDOW_ID")
        try:
            os.environ["TERM"] = "xterm-kitty"
            os.environ["KITTY_WINDOW_ID"] = "1"
            player = tvp.Player(
                "video.mp4",
                tvp.VideoInfo(width=1920, height=1080, fps=30, duration=60),
                no_audio=True,
                quality="fast",
                renderer="auto",
            )
            self.assertEqual(player.renderer, "kitty")
        finally:
            if old_term is None:
                os.environ.pop("TERM", None)
            else:
                os.environ["TERM"] = old_term
            if old_kitty_window is None:
                os.environ.pop("KITTY_WINDOW_ID", None)
            else:
                os.environ["KITTY_WINDOW_ID"] = old_kitty_window


if __name__ == "__main__":
    unittest.main()
