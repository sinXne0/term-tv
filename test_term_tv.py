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
#EXTINF:-1 group-title="News",News Channel
https://example.com/live/news.m3u8
#EXTINF:-1,Local Station
station.mp4
"""
        channels = tvp.parse_playlist(playlist, "https://example.com/list.m3u")
        self.assertEqual(channels[0].name, "News Channel")
        self.assertEqual(channels[0].source, "https://example.com/live/news.m3u8")
        self.assertEqual(channels[0].category, "News")
        self.assertEqual(channels[1].source, "https://example.com/station.mp4")
        self.assertEqual(channels[1].category, "Other")

    def test_url_detection_rejects_other_schemes(self):
        self.assertTrue(tvp.is_url("https://example.com/live.m3u8"))
        self.assertFalse(tvp.is_url("file:///tmp/video.mp4"))

    def test_youtube_url_detection(self):
        self.assertTrue(tvp.is_youtube_url("https://www.youtube.com/watch?v=abc"))
        self.assertTrue(tvp.is_youtube_url("https://youtu.be/abc"))
        self.assertFalse(tvp.is_youtube_url("https://example.com/video.mp4"))

    @mock.patch.object(tvp.subprocess, "run")
    @mock.patch.object(tvp.shutil, "which")
    def test_youtube_runtime_accepts_supported_deno(self, which, run):
        which.side_effect = lambda name: "/usr/bin/deno" if name == "deno" else None
        run.return_value = mock.Mock(stdout="deno 2.9.0\n")
        self.assertEqual(tvp.youtube_js_runtime(), "deno:/usr/bin/deno")

    @mock.patch.object(tvp.Path, "home")
    @mock.patch.object(tvp.shutil, "which", return_value=None)
    def test_require_program_checks_user_local_bin(self, _which, home):
        home.return_value = Path("/tmp/home")
        with mock.patch.object(tvp.Path, "is_file", return_value=True), mock.patch.object(
            tvp.os, "access", return_value=True
        ):
            self.assertEqual(
                tvp.require_program("yt-dlp"), "/tmp/home/.local/bin/yt-dlp"
            )

    def test_parse_plain_m3u(self):
        channels = tvp.parse_playlist("https://example.com/live.m3u8")
        self.assertEqual(channels[0].name, "live.m3u8")

    def test_built_in_guide_has_cartoon_and_news_channels(self):
        categories = {channel.category for channel in tvp.BUILT_IN_CHANNELS}
        self.assertIn("Kids", categories)
        self.assertIn("News", categories)
        self.assertIn("Documentary", categories)
        self.assertGreaterEqual(len(tvp.BUILT_IN_CHANNELS), 20)

    def test_channel_filter_matches_name_and_category(self):
        channels = [
            tvp.Channel("World Report", "https://example.com/1", "News"),
            tvp.Channel("Nature Live", "https://example.com/2", "Nature"),
        ]
        self.assertEqual(
            tvp.filter_channels(channels, query="world"), [channels[0]]
        )
        self.assertEqual(
            tvp.filter_channels(channels, query="news"), [channels[0]]
        )
        self.assertEqual(
            tvp.filter_channels(channels, category="Nature"), [channels[1]]
        )

    @mock.patch.object(tvp.subprocess, "run")
    @mock.patch.object(tvp, "youtube_js_runtime", return_value="deno:/usr/bin/deno")
    @mock.patch.object(tvp, "require_program", return_value="/usr/bin/yt-dlp")
    def test_youtube_resolver_returns_separate_video_and_audio(
        self, _require_program, _runtime, run
    ):
        run.return_value = mock.Mock(
            stdout="https://video.example/stream\nhttps://audio.example/stream\n"
        )
        resolved = tvp.resolve_youtube("terminal video player")
        self.assertEqual(resolved.video, "https://video.example/stream")
        self.assertEqual(resolved.audio, "https://audio.example/stream")
        command = run.call_args.args[0]
        self.assertIn("ytsearch1:terminal video player", command)
        self.assertIn("--no-playlist", command)
        self.assertIn("deno:/usr/bin/deno", command)

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

    def test_player_drops_up_to_one_second_of_late_frames(self):
        player = tvp.Player(
            "video.mp4",
            tvp.VideoInfo(width=1920, height=1080, fps=30, duration=60),
            no_audio=True,
            quality="balanced",
            renderer="text",
        )
        player.frame_rate = 15
        player.started_at = 0
        player.frame_index = 0
        frames = [bytes([index]) for index in range(20)]

        def read_frame():
            return frames.pop(0)

        with mock.patch.object(tvp.time, "monotonic", return_value=2.0):
            with mock.patch.object(player, "read_frame", side_effect=read_frame):
                frame = player.drop_late_frames(b"old")

        self.assertEqual(frame, bytes([14]))
        self.assertEqual(player.frame_index, 15)

    def test_adaptive_quality_steps_down_after_slow_frames(self):
        player = tvp.Player(
            "video.mp4",
            tvp.VideoInfo(width=1920, height=1080, fps=30, duration=60),
            no_audio=True,
            quality="high",
            renderer="text",
        )
        player.started_at = 0
        with mock.patch.object(player, "start") as start:
            for _ in range(12):
                changed = player.adapt_after_frame(1.0)

        self.assertTrue(changed)
        self.assertEqual(player.quality, "balanced")
        start.assert_called_once()

    def test_lag_resync_adjusts_clock_without_restarting_decoder(self):
        player = tvp.Player(
            "video.mp4",
            tvp.VideoInfo(width=1920, height=1080, fps=30, duration=60),
            no_audio=True,
            quality="balanced",
            renderer="text",
        )
        player.frame_rate = 15
        player.frame_index = 0
        player.started_at = 0

        with mock.patch.object(tvp.time, "monotonic", return_value=2.0):
            with mock.patch.object(player, "start") as start:
                changed = player.resync_clock_if_far_behind()

        self.assertTrue(changed)
        start.assert_not_called()
        self.assertAlmostEqual(player.started_at, 2.0 - (1 / 15))

    def test_no_adaptive_keeps_requested_quality(self):
        player = tvp.Player(
            "video.mp4",
            tvp.VideoInfo(width=1920, height=1080, fps=30, duration=60),
            no_audio=True,
            quality="high",
            renderer="text",
            adaptive=False,
        )
        for _ in range(20):
            changed = player.adapt_after_frame(1.0)

        self.assertFalse(changed)
        self.assertEqual(player.quality, "high")

    def test_status_shows_back_and_home_controls(self):
        player = tvp.Player(
            "video.mp4",
            tvp.VideoInfo(width=1920, height=1080, fps=30, duration=60),
            no_audio=True,
            quality="balanced",
            renderer="text",
        )
        status = player.status().decode()
        self.assertIn("b back", status)
        self.assertIn("h home", status)

    def test_explicit_start_mode_prefers_navigation_flags(self):
        args = mock.Mock(tv=True, playlist=None, youtube=None, video=None)
        self.assertEqual(tvp.explicit_start_mode(args), "tv")

        args = mock.Mock(tv=False, playlist="channels.m3u", youtube=None, video=None)
        self.assertEqual(tvp.explicit_start_mode(args), "playlist")

        args = mock.Mock(tv=False, playlist=None, youtube="NASA live", video=None)
        self.assertEqual(tvp.explicit_start_mode(args), "youtube")

        args = mock.Mock(
            tv=False,
            playlist=None,
            youtube=None,
            video="https://youtu.be/example",
        )
        self.assertEqual(tvp.explicit_start_mode(args), "youtube")

        args = mock.Mock(tv=False, playlist=None, youtube=None, video="movie.mp4")
        self.assertEqual(tvp.explicit_start_mode(args), "direct")

        args = mock.Mock(tv=False, playlist=None, youtube=None, video=None)
        self.assertIsNone(tvp.explicit_start_mode(args))


if __name__ == "__main__":
    unittest.main()
