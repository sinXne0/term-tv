#!/usr/bin/env python3
"""Play video as true-color half-block characters in a terminal."""

from __future__ import annotations

import argparse
import json
import os
import re
import select
import shutil
import signal
import subprocess
import sys
import termios
import time
import tty
import urllib.parse
import urllib.request
import zlib
from base64 import standard_b64encode
from dataclasses import dataclass
from pathlib import Path


CSI = "\x1b["
ALT_SCREEN = CSI + "?1049h"
MAIN_SCREEN = CSI + "?1049l"
HIDE_CURSOR = CSI + "?25l"
SHOW_CURSOR = CSI + "?25h"
RESET = CSI + "0m"
CLEAR_SCREEN = CSI + "2J"
ERASE_LINE = CSI + "2K"
VIDEO_EXTENSIONS = {
    ".3gp",
    ".avi",
    ".flv",
    ".m2ts",
    ".m4v",
    ".mkv",
    ".mov",
    ".mp4",
    ".mpeg",
    ".mpg",
    ".mts",
    ".ts",
    ".webm",
    ".wmv",
}


@dataclass(frozen=True)
class VideoInfo:
    width: int
    height: int
    fps: float
    duration: float


@dataclass(frozen=True)
class Channel:
    name: str
    source: str
    category: str = "Other"


@dataclass(frozen=True)
class ResolvedSource:
    video: str
    audio: str


@dataclass(frozen=True)
class QualityProfile:
    fps: float
    max_width: int
    sharpen: float
    renderer: str
    scaler: str


QUALITY_PROFILES = {
    "fast": QualityProfile(
        fps=10, max_width=64, sharpen=0, renderer="half", scaler="bilinear"
    ),
    "balanced": QualityProfile(
        fps=15,
        max_width=120,
        sharpen=0.25,
        renderer="quadrant",
        scaler="bicubic",
    ),
    "high": QualityProfile(
        fps=24,
        max_width=240,
        sharpen=0.4,
        renderer="quadrant",
        scaler="lanczos",
    ),
}
QUALITY_ORDER = tuple(QUALITY_PROFILES)
RENDERERS = ("auto", "text", "kitty")


BUILT_IN_CHANNELS = [
    Channel("PBS Kids", "https://livestream.pbskids.org/out/v1/14507d931bbe48a69287e4850e53443c/est.m3u8", "Kids"),
    Channel("HappyKids", "https://dil9xdvretp0f.cloudfront.net/index.m3u8", "Kids"),
    Channel("Kidoodle.TV", "https://amg07653-apmc-amg07653c9-samsung-us-8740.playouts.now.amagi.tv/playlist.m3u8", "Kids"),
    Channel("Kartoon Channel!", "https://d2z0ysa6dgxhlc.cloudfront.net/kchan.m3u8", "Kids"),
    Channel("Animation+", "https://pb-ioe9d0fpkd6pp.akamaized.net/playlist.m3u8", "Animation"),
    Channel("LEGO Channel", "https://dltiqboxjw21d.cloudfront.net/index.m3u8", "Kids"),
    Channel("CBS News 24/7", "https://cbsn-us.cbsnstream.cbsnews.com/out/v1/55a8648e8f134e82a470f83d562deeca/master.m3u8", "News"),
    Channel("NBC News NOW", "https://xumo-drct-nbcnn-ir8ze.fast.nbcuni.com/live/master.m3u8", "News"),
    Channel("LiveNOW from FOX", "https://pb-k5p02dtnr2162.akamaized.net/LiveNOW_from_FOX.m3u8", "News"),
    Channel("Scripps News", "https://aegis-cloudfront-1.tubi.video/7e1c26b7-7975-4240-9a4f-480eaa8f3ea4/playlist.m3u8", "News"),
    Channel("Al Jazeera English", "https://live-hls-apps-aje-fa.getaj.net/AJE/index.m3u8", "World News"),
    Channel("France 24 English", "https://live.france24.com/hls/live/2037218-b/F24_EN_HI_HLS/master_5000.m3u8", "World News"),
    Channel("NHK World-Japan", "https://masterpl.hls.nhkworld.jp/hls/w/live/smarttv.m3u8", "World News"),
    Channel("Bloomberg TV", "https://bloomberg.com/media-manifest/streams/us.m3u8", "Business"),
    Channel("WeatherNation", "https://stream.weathernationtv.com/WNTVStirr_eokxldieulowixkdimn/ND1/playlistSCTE35.m3u8", "Weather"),
    Channel("PBS Nature", "https://d3mr43kyql7wgk.cloudfront.net/PBS_Nature.m3u8", "Nature"),
    Channel("Documentary+", "https://ef79b15c8c7c46c7a9de9d33001dbd07.mediatailor.us-west-2.amazonaws.com/v1/master/ba62fe743df0fe93366eba3a257d792884136c7f/LINEAR-859-DOCUMENTARYPLUS-DOCUMENTARYPLUS/mt/documentaryplus/859/hls/master/playlist.m3u8", "Documentary"),
    Channel("DangerTV", "https://dk0n7jh428tzj.cloudfront.net/v1/dangertv/samsungheadend_us/latest/main/hls/playlist.m3u8", "Documentary"),
    Channel("Curiosity Now", "https://amg00170-amg00170c4-samsung-gb-4232.playouts.now.amagi.tv/playlist.m3u8", "Documentary"),
    Channel("FailArmy", "https://failarmy-international-au.samsung.wurl.tv/playlist.m3u8", "Comedy"),
    Channel("The Pet Collective", "https://pb-jc9emctsujawo.akamaized.net/playlist.m3u8", "Pets"),
    Channel("Tastemade Travel", "https://d6ef3usc6d9cl.cloudfront.net/Tastemade_Travel.m3u8", "Travel"),
]


def require_program(name: str) -> str:
    path = shutil.which(name)
    if path is None:
        local_path = Path.home() / ".local" / "bin" / name
        if local_path.is_file() and os.access(local_path, os.X_OK):
            path = str(local_path)
    if path is None:
        if name == "yt-dlp":
            raise RuntimeError(
                "'yt-dlp' is required for YouTube playback. "
                "Run: ./install.sh --with-youtube"
            )
        raise RuntimeError(
            f"'{name}' is required but was not found. "
            "Install FFmpeg (Ubuntu/Debian: sudo apt install ffmpeg)."
        )
    return path


def is_url(value: str) -> bool:
    return urllib.parse.urlparse(value).scheme.lower() in {"http", "https"}


def is_youtube_url(value: str) -> bool:
    if not is_url(value):
        return False
    host = (urllib.parse.urlparse(value).hostname or "").lower()
    return host == "youtu.be" or host == "youtube.com" or host.endswith(".youtube.com")


def youtube_js_runtime() -> str:
    """Return a supported JavaScript runtime for yt-dlp's YouTube extractor."""
    deno = shutil.which("deno")
    if deno is None:
        local_deno = Path.home() / ".local" / "bin" / "deno"
        if local_deno.is_file() and os.access(local_deno, os.X_OK):
            deno = str(local_deno)
    if deno:
        result = subprocess.run(
            [deno, "--version"], capture_output=True, text=True, check=False
        )
        match = re.search(r"deno\s+(\d+)\.(\d+)", result.stdout)
        if match and (int(match.group(1)), int(match.group(2))) >= (2, 3):
            return f"deno:{deno}"

    node = shutil.which("node")
    if node:
        result = subprocess.run(
            [node, "--version"], capture_output=True, text=True, check=False
        )
        match = re.search(r"v?(\d+)", result.stdout)
        if match and int(match.group(1)) >= 22:
            return f"node:{node}"

    raise RuntimeError(
        "YouTube playback requires Deno 2.3+ (or Node.js 22+). "
        "Run: ./install.sh --with-youtube"
    )


def resolve_youtube(value: str) -> ResolvedSource:
    """Resolve a YouTube URL or search query to direct video and audio URLs."""
    yt_dlp = require_program("yt-dlp")
    target = value if is_youtube_url(value) else f"ytsearch1:{value}"
    command = [
        yt_dlp,
        "--no-warnings",
        "--no-playlist",
        "--js-runtimes",
        youtube_js_runtime(),
        "--format",
        "bestvideo[height<=1080]+bestaudio/best[height<=1080]",
        "--get-url",
        target,
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=True)
    urls = [line.strip() for line in result.stdout.splitlines() if is_url(line.strip())]
    if not urls:
        raise RuntimeError("yt-dlp did not return a playable YouTube stream.")
    return ResolvedSource(video=urls[0], audio=urls[1] if len(urls) > 1 else urls[0])


def probe(source: str) -> VideoInfo:
    ffprobe = require_program("ffprobe")
    command = [
        ffprobe,
        "-v",
        "error",
        "-select_streams",
        "v:0",
        "-show_entries",
        "stream=width,height,avg_frame_rate:format=duration",
        "-of",
        "json",
        source,
    ]
    result = subprocess.run(command, capture_output=True, text=True, check=True)
    data = json.loads(result.stdout)
    if not data.get("streams"):
        raise RuntimeError("The file does not contain a video stream.")

    stream = data["streams"][0]
    numerator, denominator = stream.get("avg_frame_rate", "0/0").split("/")
    fps = float(numerator) / float(denominator) if float(denominator) else 0
    if fps <= 0 or fps > 240:
        fps = 24.0
    return VideoInfo(
        width=int(stream["width"]),
        height=int(stream["height"]),
        fps=fps,
        duration=float(data.get("format", {}).get("duration", 0)),
    )


def render_frame(frame: bytes, width: int, height: int) -> bytes:
    """Convert RGB24 pixels to ANSI true-color upper-half blocks."""
    output = bytearray()
    stride = width * 3
    for y in range(0, height, 2):
        top = y * stride
        bottom = min(y + 1, height - 1) * stride
        row = y // 2 + 1
        output.extend(f"{CSI}{row};1H".encode())
        for x in range(width):
            i = top + x * 3
            j = bottom + x * 3
            tr, tg, tb = frame[i : i + 3]
            br, bg, bb = frame[j : j + 3]
            output.extend(
                f"\x1b[38;2;{tr};{tg};{tb};48;2;{br};{bg};{bb}m▀".encode()
            )
        output.extend(RESET.encode())
    return bytes(output)


QUADRANTS = " ▘▝▀▖▌▞▛▗▚▐▜▄▙▟█"


def average_color(colors: list[tuple[int, int, int]]) -> tuple[int, int, int]:
    count = len(colors)
    return (
        sum(color[0] for color in colors) // count,
        sum(color[1] for color in colors) // count,
        sum(color[2] for color in colors) // count,
    )


def color_distance(
    first: tuple[int, int, int], second: tuple[int, int, int]
) -> int:
    """Return a perceptually weighted squared RGB distance."""
    red = first[0] - second[0]
    green = first[1] - second[1]
    blue = first[2] - second[2]
    return red * red * 2 + green * green * 4 + blue * blue * 3


def quadrant_palette(
    pixels: list[tuple[int, int, int]],
) -> tuple[int, tuple[int, int, int], tuple[int, int, int]]:
    """Approximate four pixels with the best two-color quadrant cell."""
    if pixels[0] == pixels[1] == pixels[2] == pixels[3]:
        return 15, pixels[0], pixels[0]

    # Seed two clusters with the most different source colors. One refinement
    # pass gives a strong approximation without the cost of testing every
    # possible partition for every terminal cell and every frame.
    first_index = 0
    second_index = 1
    greatest_distance = -1
    for left, right in ((0, 1), (0, 2), (0, 3), (1, 2), (1, 3), (2, 3)):
        left_color = pixels[left]
        right_color = pixels[right]
        red = left_color[0] - right_color[0]
        green = left_color[1] - right_color[1]
        blue = left_color[2] - right_color[2]
        distance = red * red * 2 + green * green * 4 + blue * blue * 3
        if distance > greatest_distance:
            greatest_distance = distance
            first_index, second_index = left, right

    foreground = pixels[first_index]
    background = pixels[second_index]
    mask = 0
    foreground_red = foreground_green = foreground_blue = foreground_count = 0
    background_red = background_green = background_blue = background_count = 0
    for index, color in enumerate(pixels):
        red = color[0] - foreground[0]
        green = color[1] - foreground[1]
        blue = color[2] - foreground[2]
        foreground_distance = red * red * 2 + green * green * 4 + blue * blue * 3
        red = color[0] - background[0]
        green = color[1] - background[1]
        blue = color[2] - background[2]
        background_distance = red * red * 2 + green * green * 4 + blue * blue * 3
        if foreground_distance <= background_distance:
            mask |= 1 << index
            foreground_red += color[0]
            foreground_green += color[1]
            foreground_blue += color[2]
            foreground_count += 1
        else:
            background_red += color[0]
            background_green += color[1]
            background_blue += color[2]
            background_count += 1

    foreground = (
        foreground_red // foreground_count,
        foreground_green // foreground_count,
        foreground_blue // foreground_count,
    )
    background = (
        background_red // background_count,
        background_green // background_count,
        background_blue // background_count,
    )

    # Keep the first quadrant in the foreground so equivalent inverted
    # partitions produce a stable Unicode glyph and color ordering.
    if not mask & 1:
        mask ^= 15
        foreground, background = background, foreground
    return mask, foreground, background


def render_frame_quadrant(frame: bytes, width: int, height: int) -> bytes:
    """Render four source pixels per cell using Unicode quadrant blocks."""
    output = bytearray()
    stride = width * 3
    for y in range(0, height, 2):
        row = y // 2 + 1
        output.extend(f"{CSI}{row};1H".encode())
        for x in range(0, width, 2):
            pixels = []
            for px, py in ((x, y), (x + 1, y), (x, y + 1), (x + 1, y + 1)):
                index = min(py, height - 1) * stride + min(px, width - 1) * 3
                pixels.append(tuple(frame[index : index + 3]))

            mask, foreground, background = quadrant_palette(pixels)
            if mask in (0, 15):
                output.extend(
                    f"\x1b[38;2;{foreground[0]};{foreground[1]};"
                    f"{foreground[2]}m█".encode()
                )
                continue

            output.extend(
                f"\x1b[38;2;{foreground[0]};{foreground[1]};{foreground[2]};"
                f"48;2;{background[0]};{background[1]};{background[2]}m"
                f"{QUADRANTS[mask]}".encode()
            )
        output.extend(RESET.encode())
    return bytes(output)


def kitty_chunks(control: str, frame: bytes, continuation_action: str = "") -> bytes:
    """Build a chunked Kitty graphics command with compressed RGB data."""
    payload = standard_b64encode(zlib.compress(frame, 1))
    chunks = [payload[index : index + 4096] for index in range(0, len(payload), 4096)]
    output = bytearray()
    for index, chunk in enumerate(chunks):
        more = int(index < len(chunks) - 1)
        if index == 0:
            chunk_control = f"{control},m={more}"
        else:
            chunk_control = f"{continuation_action}q=2,m={more}"
        output.extend(f"\x1b_G{chunk_control};".encode())
        output.extend(chunk)
        output.extend(b"\x1b\\")
    return bytes(output)


def kitty_root_frame(
    frame: bytes,
    width: int,
    height: int,
    columns: int,
    rows: int,
    image_id: int = 1,
) -> bytes:
    return kitty_chunks(
        f"a=T,f=24,s={width},v={height},o=z,t=d,i={image_id},p=1,"
        f"q=2,C=1,c={columns},r={rows}",
        frame,
    )


def kitty_delete_image(image_id: int) -> bytes:
    """Delete an image and its placement, freeing terminal graphics memory."""
    return f"\x1b_Ga=d,d=I,i={image_id},q=2;\x1b\\".encode()


def kitty_available() -> bool:
    return bool(os.environ.get("KITTY_WINDOW_ID")) or os.environ.get("TERM") == "xterm-kitty"


def format_time(seconds: float) -> str:
    seconds = max(0, int(seconds))
    return f"{seconds // 60:02d}:{seconds % 60:02d}"


def discover_videos() -> list[Path]:
    """Find likely videos without recursively walking the entire home folder."""
    roots = [Path.cwd(), Path.home() / "Videos", Path.home() / "Downloads"]
    found: dict[Path, None] = {}
    for root in roots:
        if not root.is_dir():
            continue
        try:
            for path in root.iterdir():
                if path.is_file() and path.suffix.lower() in VIDEO_EXTENSIONS:
                    found[path.resolve()] = None
        except PermissionError:
            continue
    return sorted(found, key=lambda path: path.name.casefold())


def choose_video() -> Path:
    videos = discover_videos()
    if not videos:
        raise RuntimeError(
            "No videos found in the current folder, ~/Videos, or ~/Downloads.\n"
            "Run: term-tv /path/to/video.mp4"
        )
    if not sys.stdin.isatty():
        raise RuntimeError("A video path is required when input is not interactive.")

    print("Choose a video:\n")
    for index, path in enumerate(videos, 1):
        try:
            label = f"~/{path.relative_to(Path.home())}"
        except ValueError:
            label = str(path)
        print(f"  {index:>2}. {label}")
    print("\n  q. Cancel")

    while True:
        try:
            answer = input("\nVideo number: ").strip()
        except (EOFError, KeyboardInterrupt):
            raise RuntimeError("Selection cancelled.") from None
        if answer.lower() == "q":
            raise RuntimeError("Selection cancelled.")
        if answer.isdigit() and 1 <= int(answer) <= len(videos):
            return videos[int(answer) - 1]
        print(f"Enter a number from 1 to {len(videos)}, or q.")


def read_playlist(location: str) -> tuple[str, str | None]:
    if is_url(location):
        request = urllib.request.Request(
            location, headers={"User-Agent": "term-tv/1.0"}, method="GET"
        )
        with urllib.request.urlopen(request, timeout=15) as response:
            data = response.read(2_000_001)
        if len(data) > 2_000_000:
            raise RuntimeError("Playlist is larger than the 2 MB safety limit.")
        return data.decode("utf-8-sig", errors="replace"), location

    path = Path(location).expanduser().resolve()
    if not path.is_file():
        raise RuntimeError(f"Playlist not found: {path}")
    if path.stat().st_size > 2_000_000:
        raise RuntimeError("Playlist is larger than the 2 MB safety limit.")
    return path.read_text(encoding="utf-8-sig", errors="replace"), path.as_uri()


def parse_playlist(text: str, base: str | None = None) -> list[Channel]:
    channels: list[Channel] = []
    pending_name: str | None = None
    pending_category = "Other"
    for raw_line in text.splitlines():
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("#EXTINF:"):
            pending_name = line.rsplit(",", 1)[-1].strip() or None
            group = re.search(r'group-title="([^"]+)"', line, flags=re.IGNORECASE)
            pending_category = group.group(1).strip() if group else "Other"
            continue
        if line.startswith("#"):
            continue

        source = urllib.parse.urljoin(base, line) if base else line
        if not is_url(source):
            parsed = urllib.parse.urlparse(source)
            if parsed.scheme == "file":
                source = urllib.request.url2pathname(parsed.path)
            else:
                source = str(Path(source).expanduser().resolve())
        name = pending_name or Path(urllib.parse.urlparse(source).path).name or source
        channels.append(Channel(name=name, source=source, category=pending_category))
        pending_name = None
        pending_category = "Other"
    return channels


def filter_channels(
    channels: list[Channel], query: str = "", category: str | None = None
) -> list[Channel]:
    query = query.casefold().strip()
    return [
        channel
        for channel in channels
        if (category is None or channel.category == category)
        and (
            not query
            or query in channel.name.casefold()
            or query in channel.category.casefold()
        )
    ]


def choose_category(channels: list[Channel]) -> str | None:
    categories = sorted({channel.category for channel in channels}, key=str.casefold)
    print(CLEAR_SCREEN + CSI + "H", end="")
    print("\nCategories:\n")
    print("   0. All channels")
    for index, category in enumerate(categories, 1):
        count = sum(channel.category == category for channel in channels)
        print(f"  {index:>2}. {category} ({count})")
    while True:
        try:
            answer = input("\nCategory number (or q): ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            raise RuntimeError("Selection cancelled.") from None
        if answer == "q":
            raise RuntimeError("Selection cancelled.")
        if answer == "0":
            return None
        if answer.isdigit() and 1 <= int(answer) <= len(categories):
            return categories[int(answer) - 1]
        print(f"Enter 0 to {len(categories)}, or q.")


def choose_from_channels(channels: list[Channel], title: str) -> str:
    if not channels:
        raise RuntimeError("The channel list contains no playable entries.")
    if not sys.stdin.isatty():
        raise RuntimeError("Channel selection requires an interactive terminal.")

    category: str | None = None
    query = ""
    with MenuScreen():
        while True:
            print(CLEAR_SCREEN + CSI + "H", end="")
            visible = sorted(
                filter_channels(channels, query, category),
                key=lambda channel: (
                    channel.category.casefold(),
                    channel.name.casefold(),
                ),
            )
            active_filters = []
            if category:
                active_filters.append(f"category: {category}")
            if query:
                active_filters.append(f"search: {query}")
            suffix = f" · {' · '.join(active_filters)}" if active_filters else ""
            print(f"\n{title} ({len(visible)}/{len(channels)}){suffix}\n")
            if visible:
                previous_category = None
                for index, channel in enumerate(visible, 1):
                    if channel.category != previous_category:
                        print(f"  ── {channel.category} ──")
                        previous_category = channel.category
                    print(f"  {index:>3}. {channel.name}")
            else:
                print("  No matching channels.")
            print("\n  /text search · c category · a clear filters · q cancel")

            try:
                answer = input("\nChoose: ").strip()
            except (EOFError, KeyboardInterrupt):
                raise RuntimeError("Selection cancelled.") from None
            command = answer.lower()
            if command == "q":
                raise RuntimeError("Selection cancelled.")
            if command == "c":
                category = choose_category(channels)
                continue
            if command == "a":
                category = None
                query = ""
                continue
            if answer.startswith("/"):
                query = answer[1:].strip()
                continue
            if answer.isdigit() and 1 <= int(answer) <= len(visible):
                return visible[int(answer) - 1].source
            print("Enter a channel number, /search, c, a, or q.")


def choose_channel(playlist: str) -> str:
    text, base = read_playlist(playlist)
    return choose_from_channels(parse_playlist(text, base), "Playlist")


def choose_mode() -> str:
    if not sys.stdin.isatty():
        raise RuntimeError("A video path or option is required.")
    print("term-tv\n")
    print("  1. Internet TV")
    print("  2. Local video")
    print("  3. YouTube")
    print("  q. Quit")
    while True:
        try:
            answer = input("\nChoose: ").strip().lower()
        except (EOFError, KeyboardInterrupt):
            raise RuntimeError("Selection cancelled.") from None
        if answer == "1":
            return "tv"
        if answer == "2":
            return "local"
        if answer == "3":
            return "youtube"
        if answer == "q":
            raise RuntimeError("Selection cancelled.")
        print("Enter 1, 2, 3, or q.")


def choose_youtube() -> str:
    try:
        value = input("\nYouTube URL or search: ").strip()
    except (EOFError, KeyboardInterrupt):
        raise RuntimeError("Selection cancelled.") from None
    if not value:
        raise RuntimeError("A YouTube URL or search query is required.")
    return value


class MenuScreen:
    def __enter__(self) -> "MenuScreen":
        sys.stdout.write(ALT_SCREEN + CLEAR_SCREEN + CSI + "H")
        sys.stdout.flush()
        return self

    def __exit__(self, *_: object) -> None:
        sys.stdout.write(RESET + MAIN_SCREEN)
        sys.stdout.flush()


class Terminal:
    def __init__(self) -> None:
        self.fd = sys.stdin.fileno()
        self.original: list[int] | None = None

    def __enter__(self) -> "Terminal":
        if not sys.stdin.isatty() or not sys.stdout.isatty():
            raise RuntimeError("The player must be run in an interactive terminal.")
        self.original = termios.tcgetattr(self.fd)
        tty.setcbreak(self.fd)
        sys.stdout.write(ALT_SCREEN + HIDE_CURSOR + CLEAR_SCREEN + CSI + "H")
        sys.stdout.flush()
        return self

    def __exit__(self, *_: object) -> None:
        if self.original is not None:
            termios.tcsetattr(self.fd, termios.TCSADRAIN, self.original)
        # Disable synchronized output defensively in case a previous run was
        # interrupted while the terminal was buffering a frame.
        sys.stdout.write(CSI + "?2026l" + RESET + SHOW_CURSOR + MAIN_SCREEN)
        sys.stdout.flush()

    def key(self) -> str | None:
        if not select.select([self.fd], [], [], 0)[0]:
            return None
        data = os.read(self.fd, 8).decode(errors="ignore")
        if data.startswith("\x1b[D"):
            return "left"
        if data.startswith("\x1b[C"):
            return "right"
        return data[:1]


class Player:
    def __init__(
        self,
        source: str,
        info: VideoInfo,
        no_audio: bool,
        quality: str,
        renderer: str,
        audio_source: str | None = None,
    ) -> None:
        self.source = source
        self.audio_source = audio_source or source
        self.info = info
        self.no_audio = no_audio
        self.quality = quality
        self.renderer = "kitty" if renderer == "auto" and kitty_available() else renderer
        if self.renderer == "auto":
            self.renderer = "text"
        if self.renderer == "kitty" and not kitty_available():
            raise RuntimeError(
                "Kitty rendering requires running term-tv inside a Kitty terminal."
            )
        self.frame_rate = min(info.fps, QUALITY_PROFILES[quality].fps)
        self.video: subprocess.Popen[bytes] | None = None
        self.audio: subprocess.Popen[bytes] | None = None
        self.position = 0.0
        self.frame_index = 0
        self.started_at = 0.0
        self.paused_at: float | None = None
        self.width = 0
        self.height = 0
        self.kitty_initialized = False
        self.kitty_active_image = 1

    def dimensions(self) -> tuple[int, int]:
        terminal = shutil.get_terminal_size((80, 24))
        profile = QUALITY_PROFILES[self.quality]
        if self.renderer == "kitty":
            max_width = {"fast": 480, "balanced": 640, "high": 960}[self.quality]
            max_height = max(2, int(max_width * self.info.height / self.info.width))
            return max_width, max_height - max_height % 2
        pixels_per_cell = 2 if profile.renderer == "quadrant" else 1
        # Leave the final terminal column unused. Writing into that column can
        # trigger delayed auto-wrap; on the bottom row that scrolls the screen
        # and makes repeated frames look frozen in several terminal emulators.
        drawable_columns = max(2, terminal.columns - 1)
        max_width = max(
            2,
            min(
                drawable_columns * pixels_per_cell,
                profile.max_width * pixels_per_cell,
            ),
        )
        max_pixel_height = max(2, (terminal.lines - 1) * 2)
        scale = min(
            max_width / (self.info.width * pixels_per_cell),
            max_pixel_height / self.info.height,
            1,
        )
        width = max(2, int(self.info.width * scale * pixels_per_cell))
        width -= width % pixels_per_cell
        height = max(2, int(self.info.height * scale))
        height -= height % 2
        return width, height

    def video_filter(self) -> str:
        profile = QUALITY_PROFILES[self.quality]
        filters = [
            f"fps={self.frame_rate}",
            (
                f"scale={self.width}:{self.height}:"
                f"flags={profile.scaler}+accurate_rnd+full_chroma_int"
            ),
        ]
        if profile.sharpen:
            filters.append(f"unsharp=3:3:{profile.sharpen}")
        return ",".join(filters)

    def stop_processes(self) -> None:
        for process in (self.video, self.audio):
            if process is not None and process.poll() is None:
                process.terminate()
                try:
                    process.wait(timeout=0.5)
                except subprocess.TimeoutExpired:
                    process.kill()
                    process.wait()
        self.video = None
        self.audio = None

    def start(self, position: float) -> None:
        self.stop_processes()
        if self.renderer == "kitty" and self.kitty_initialized:
            sys.stdout.buffer.write(kitty_delete_image(1))
            sys.stdout.buffer.write(kitty_delete_image(2))
            sys.stdout.buffer.flush()
        self.kitty_initialized = False
        self.kitty_active_image = 1
        self.position = max(0.0, min(position, self.info.duration or position))
        self.frame_index = 0
        self.width, self.height = self.dimensions()

        ffmpeg = require_program("ffmpeg")
        video_command = [
            ffmpeg,
            "-loglevel",
            "error",
            "-ss",
            str(self.position),
            "-i",
            self.source,
            "-an",
            "-vf",
            self.video_filter(),
            "-pix_fmt",
            "rgb24",
            "-f",
            "rawvideo",
            "-",
        ]
        self.video = subprocess.Popen(video_command, stdout=subprocess.PIPE)

        ffplay = shutil.which("ffplay")
        if not self.no_audio and ffplay:
            audio_command = [
                ffplay,
                "-loglevel",
                "quiet",
                "-nodisp",
                "-autoexit",
                "-ss",
                str(self.position),
                self.audio_source,
            ]
            self.audio = subprocess.Popen(
                audio_command,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        self.started_at = time.monotonic()
        self.paused_at = None

    def current_position(self) -> float:
        if self.paused_at is not None:
            elapsed = self.paused_at - self.started_at
        else:
            elapsed = time.monotonic() - self.started_at
        return self.position + max(0.0, elapsed)

    def pause(self) -> None:
        processes = [p for p in (self.video, self.audio) if p and p.poll() is None]
        if self.paused_at is None:
            self.paused_at = time.monotonic()
            for process in processes:
                process.send_signal(signal.SIGSTOP)
        else:
            paused_for = time.monotonic() - self.paused_at
            self.started_at += paused_for
            self.paused_at = None
            for process in processes:
                process.send_signal(signal.SIGCONT)

    def seek(self, offset: float) -> None:
        if self.info.duration <= 0:
            return
        self.start(max(0, self.current_position() + offset))

    def cycle_quality(self) -> None:
        index = (QUALITY_ORDER.index(self.quality) + 1) % len(QUALITY_ORDER)
        self.quality = QUALITY_ORDER[index]
        self.frame_rate = min(self.info.fps, QUALITY_PROFILES[self.quality].fps)
        position = self.current_position() if self.info.duration > 0 else 0
        self.start(position)

    def read_frame(self) -> bytes | None:
        if self.video is None or self.video.stdout is None:
            return None
        size = self.width * self.height * 3
        frame = bytearray()
        while len(frame) < size:
            chunk = self.video.stdout.read(size - len(frame))
            if not chunk:
                return None
            frame.extend(chunk)
        return bytes(frame)

    def wait_for_frame(self) -> None:
        target = self.started_at + self.frame_index / self.frame_rate
        delay = target - time.monotonic()
        if delay > 0:
            time.sleep(delay)

    def drop_late_frames(self, frame: bytes) -> bytes:
        """Discard decoded frames when rendering falls behind real time."""
        expected = int((time.monotonic() - self.started_at) * self.frame_rate)
        to_drop = min(max(0, expected - self.frame_index - 1), 8)
        for _ in range(to_drop):
            newer = self.read_frame()
            if newer is None:
                break
            frame = newer
            self.frame_index += 1
        return frame

    def status(self) -> bytes:
        current = self.current_position()
        if self.info.duration > 0:
            current = min(current, self.info.duration)
            timing = f"{format_time(current)} / {format_time(self.info.duration)}"
        else:
            timing = f"LIVE · {format_time(current)}"
        state = "PAUSED" if self.paused_at is not None else "PLAYING"
        audio = "audio" if self.audio else "silent"
        text = (
            f"{state}  {timing}  [{audio} · {self.renderer} · "
            f"{self.quality} {self.frame_rate:g}fps]"
            f"  space pause · m quality · ←/→ seek · q quit"
        )
        columns = shutil.get_terminal_size((80, 24)).columns
        width = max(1, columns - 1)
        return (RESET + ERASE_LINE + text[:width].ljust(width)).encode()

    def run(self) -> None:
        self.start(0)
        try:
            with Terminal() as terminal:
                while True:
                    key = terminal.key()
                    if key in ("q", "\x03"):
                        break
                    if key == " ":
                        self.pause()
                    elif key == "left":
                        self.seek(-5)
                    elif key == "right":
                        self.seek(5)
                    elif key == "m":
                        self.cycle_quality()

                    if self.paused_at is not None:
                        time.sleep(0.02)
                        continue

                    new_dimensions = self.dimensions()
                    if new_dimensions != (self.width, self.height):
                        position = self.current_position() if self.info.duration > 0 else 0
                        self.start(position)

                    frame = self.read_frame()
                    if frame is None:
                        break
                    frame = self.drop_late_frames(frame)
                    self.wait_for_frame()
                    terminal_size = shutil.get_terminal_size((80, 24))
                    if self.renderer == "kitty":
                        sys.stdout.buffer.write((CSI + "H").encode())
                        next_image = (
                            1
                            if not self.kitty_initialized
                            else 2 if self.kitty_active_image == 1 else 1
                        )
                        command = kitty_root_frame(
                            frame,
                            self.width,
                            self.height,
                            terminal_size.columns,
                            max(1, terminal_size.lines - 1),
                            image_id=next_image,
                        )
                        sys.stdout.buffer.write(command)
                        if self.kitty_initialized:
                            sys.stdout.buffer.write(
                                kitty_delete_image(self.kitty_active_image)
                            )
                        self.kitty_initialized = True
                        self.kitty_active_image = next_image
                        sys.stdout.buffer.write(
                            (CSI + f"{terminal_size.lines};1H").encode()
                        )
                        sys.stdout.buffer.write(self.status())
                    else:
                        # Do not wrap frames in DEC synchronized-output mode.
                        # Several otherwise capable terminals buffer this mode
                        # indefinitely, leaving a frozen image while ffplay's
                        # separate audio process continues normally.
                        text_renderer = QUALITY_PROFILES[self.quality].renderer
                        rendered = (
                            render_frame_quadrant(frame, self.width, self.height)
                            if text_renderer == "quadrant"
                            else render_frame(frame, self.width, self.height)
                        )
                        sys.stdout.buffer.write(rendered)
                        sys.stdout.buffer.write(
                            (CSI + f"{terminal_size.lines};1H").encode()
                        )
                        sys.stdout.buffer.write(self.status())
                    sys.stdout.buffer.flush()
                    self.frame_index += 1
        finally:
            self.stop_processes()
            if self.renderer == "kitty" and sys.stdout.isatty():
                sys.stdout.buffer.write(kitty_delete_image(1))
                sys.stdout.buffer.write(kitty_delete_image(2))
                sys.stdout.buffer.flush()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Play a video directly in a true-color terminal."
    )
    parser.add_argument(
        "video",
        nargs="?",
        help="video file or direct http(s) stream URL",
    )
    parser.add_argument(
        "-p",
        "--playlist",
        metavar="M3U",
        help="choose a channel from a local or http(s) M3U playlist",
    )
    parser.add_argument(
        "--tv",
        action="store_true",
        help="open the built-in free Internet TV guide",
    )
    parser.add_argument(
        "-y",
        "--youtube",
        metavar="URL_OR_SEARCH",
        help="play a YouTube URL or the first result for a search query",
    )
    parser.add_argument("--no-audio", action="store_true", help="disable audio playback")
    parser.add_argument(
        "-q",
        "--quality",
        choices=QUALITY_ORDER,
        default="balanced",
        help="rendering preset (default: balanced)",
    )
    parser.add_argument(
        "--renderer",
        choices=RENDERERS,
        default="auto",
        help="image renderer; auto uses Kitty graphics when available",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        youtube: str | None = args.youtube
        if args.tv:
            source = choose_from_channels(BUILT_IN_CHANNELS, "Free Internet TV")
        elif args.playlist:
            source = choose_channel(args.playlist)
        elif youtube:
            source = youtube
        elif args.video and is_youtube_url(args.video):
            youtube = args.video
            source = args.video
        elif args.video and is_url(args.video):
            source = args.video
        elif args.video:
            path = Path(args.video).expanduser().resolve()
            if not path.is_file():
                print(f"error: file not found: {path}", file=sys.stderr)
                return 2
            source = str(path)
        else:
            mode = choose_mode()
            if mode == "tv":
                source = choose_from_channels(BUILT_IN_CHANNELS, "Free Internet TV")
            elif mode == "youtube":
                youtube = choose_youtube()
                source = youtube
            else:
                source = str(choose_video())

        resolved = (
            resolve_youtube(youtube)
            if youtube is not None
            else ResolvedSource(video=source, audio=source)
        )
        info = probe(resolved.video)
        Player(
            resolved.video,
            info,
            args.no_audio,
            args.quality,
            args.renderer,
            audio_source=resolved.audio,
        ).run()
    except (
        RuntimeError,
        subprocess.CalledProcessError,
        json.JSONDecodeError,
        OSError,
    ) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    except KeyboardInterrupt:
        return 130
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
