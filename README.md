# term-tv

A local video player that renders entirely inside a true-color terminal. FFmpeg
decodes the video; Python converts each pair of pixels into a colored `▀`
character. If `ffplay` is available, audio plays alongside the terminal frames.

## Requirements

- Python 3.10+
- FFmpeg (`ffmpeg`, `ffprobe`, and optionally `ffplay`)
- A terminal with 24-bit color support
- Linux or macOS (the keyboard and pause controls use POSIX terminal APIs)

On Ubuntu or Debian:

```bash
sudo apt install ffmpeg
```

## Install

Run this once:

```bash
cd term-tv
./install.sh
```

Open a new terminal. You can then launch a specific file from anywhere:

```bash
term-tv ~/Videos/movie.mp4
```

Or run `term-tv` with no arguments to choose from videos in the current folder,
`~/Videos`, and `~/Downloads`.

Paths containing spaces work normally when quoted:

```bash
term-tv "My Videos/movie night.mp4"
```

Use `term-tv --no-audio movie.mp4` to play silently.

Rendering defaults to the `balanced` preset. On slower terminals or remote
connections, use:

```bash
term-tv --quality fast movie.mp4
term-tv --quality fast --tv
```

For the sharpest image on a fast terminal, use `--quality high`. It uses
24 fps Lanczos scaling, full-chroma interpolation, and RGB-aware quadrant
color reconstruction. Balanced and high provide twice the horizontal detail of
the fast renderer. Press `m` during playback to switch among the presets.

Terminal dimensions are the hard resolution limit. Widen the terminal or reduce
its font size to make more rows and columns available to the player.

### Kitty high-resolution mode

Kitty's native graphics protocol provides the sharpest output because it
displays real pixels instead of approximating them with Unicode cells:

```bash
kitty
term-tv --renderer kitty --quality high --tv
```

The default `--renderer auto` selects native graphics inside Kitty and portable
text rendering elsewhere. Native playback uses alternating image replacement
rather than Kitty's optional animation protocol.

## Internet TV

Run the built-in guide:

```bash
term-tv --tv
```

The guide includes verified free streams for PBS Kids, HappyKids, Kidoodle.TV,
Kartoon Channel, Animation+, LEGO Channel, CBS News, NBC News NOW, NHK World,
and Bloomberg TV. Running `tvp` without arguments also offers Internet TV as
the first menu option.

Play a direct HTTP or HLS stream:

```bash
term-tv "https://example.org/live/channel.m3u8"
```

Open a channel list from a local or online M3U playlist:

```bash
term-tv --playlist ~/Downloads/channels.m3u
term-tv --playlist "https://example.org/channels.m3u"
```

Only use streams and playlists that you are authorized to watch. Stream URLs
often expire or change; that is controlled by the broadcaster, not the player.

## Controls

- `Space`: pause or resume
- `Left arrow`: seek backward 5 seconds
- `Right arrow`: seek forward 5 seconds
- `m`: switch rendering quality
- `q`: quit

The image automatically fits the current terminal and redraws after a resize.
Smaller terminal windows generally play more smoothly because fewer colored
cells need to be written per frame.

## Troubleshooting

If audio plays but the image does not advance, first force the portable
renderer and lowest-bandwidth preset:

```bash
term-tv --renderer text --quality fast video.mp4
```

`term-tv` uses absolute cursor positioning and deliberately leaves the terminal's
last column unused. This prevents auto-wrap from scrolling frames off the
alternate screen. Avoid running it through a terminal multiplexer until direct
playback in the terminal works.

For a decoder-only check, run without audio:

```bash
term-tv --no-audio --renderer text --quality fast video.mp4
```
