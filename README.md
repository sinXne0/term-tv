# term-tv

Watch local videos, HLS streams, and free Internet TV directly in a terminal.
FFmpeg handles decoding while `term-tv` renders either true-color Unicode
blocks or native Kitty graphics.

![term-tv playing a video in Kitty](docs/images/term-tv-screenshot.png)

> The screenshot demonstrates Kitty native-graphics mode. Text mode works in
> other true-color terminals but is limited by the terminal's character grid.

## Features

- Plays MP4, MKV, WebM, MOV, AVI, MPEG, and other FFmpeg-supported formats
- Plays direct HTTP/HTTPS video and HLS (`.m3u8`) streams
- Includes a built-in free Internet TV channel guide
- Loads local or remote M3U playlists
- Includes a categorized, searchable channel guide
- Plays YouTube URLs and the first result for a YouTube search
- Provides synchronized audio through `ffplay`
- Supports pause, seek, terminal resize, and live quality switching
- Offers portable true-color text rendering
- Uses native pixel graphics automatically inside Kitty
- Includes `term-web`, a terminal-only text web browser
- Has no Python package dependencies

## Requirements

- Linux or macOS
- Python 3.10 or newer
- FFmpeg tools: `ffmpeg`, `ffprobe`, and `ffplay`
- An interactive terminal with 24-bit color support
- Git, for the installation steps below

Kitty is optional, but recommended for the sharpest image.
YouTube support uses `yt-dlp` and Deno; the installer can add both without
requiring root access.

## Installation walkthrough

### 1. Install FFmpeg and Git

Ubuntu or Debian:

```bash
sudo apt update
sudo apt install ffmpeg git
```

Fedora:

```bash
sudo dnf install ffmpeg git
```

Arch Linux:

```bash
sudo pacman -S ffmpeg git
```

macOS with Homebrew:

```bash
brew install ffmpeg git
```

Verify that the required programs are available:

```bash
python3 --version
ffmpeg -version
ffplay -version
git --version
```

### 2. Clone term-tv

```bash
git clone https://github.com/sinXne0/term-tv.git
cd term-tv
```

### 3. Run the installer

```bash
./install.sh
```

To include YouTube support:

```bash
./install.sh --with-youtube
```

The installer:

- creates `~/.local/bin` when needed;
- installs the `term-tv` command as a symbolic link;
- installs the `term-web` terminal browser command;
- installs `tvp` as a compatibility alias;
- optionally installs the official `yt-dlp` and Deno standalone binaries;
- adds `~/.local/bin` to `~/.bashrc` if it is not already on `PATH`.

Reload Bash after installation:

```bash
source ~/.bashrc
```

If you use another shell, add this line to that shell's profile:

```bash
export PATH="$HOME/.local/bin:$PATH"
```

For example, Zsh users can add it to `~/.zshrc`.

### 4. Confirm the installation

```bash
term-tv --help
```

You can also start the terminal browser:

```bash
term-web
```

### 5. Play your first video

```bash
term-tv ~/Videos/movie.mp4
```

Quote paths containing spaces:

```bash
term-tv "$HOME/Videos/movie night.mp4"
```

Run the command without a path to choose a local video or open Internet TV:

```bash
term-tv
```

## Terminal web browser

`term-web` is a simple browser that renders websites as readable terminal text.
It ignores JavaScript, CSS, images, video, and tracking-heavy page behavior.
That keeps it portable and fast, but it means complex web apps will not behave
like they do in Firefox or Chrome.

Start on the built-in home page:

```bash
term-web
```

Open a URL:

```bash
term-web https://example.com
```

Search from the terminal:

```bash
term-web "open source terminal browser"
```

While browsing:

| Input | Action |
| --- | --- |
| URL or words | Open a URL or search DuckDuckGo HTML |
| Link number | Follow that numbered link |
| `j` / `k` | Scroll down or up one line |
| `d` / `u` | Page down or page up |
| `g` / `G` | Jump to top or bottom |
| `/text` | Search inside the current page |
| `n` / `N` | Move to next or previous search match |
| `mark` | Bookmark the current page |
| `marks` | Open bookmarks |
| `forms` | Check whether the current page has forms |
| `submit 1` | Submit a simple GET form by number |
| `b` | Back |
| `r` | Reload |
| `h` | Home |
| `q` | Quit |

Bookmarks are saved in:

```bash
~/.local/share/term-web/bookmarks.json
```

Form support is intentionally basic. `term-web` supports classic GET forms,
such as many search boxes. JavaScript-heavy login and checkout flows are out of
scope for this terminal-first browser.

## Getting the best image quality

### Kitty native graphics — recommended

Text characters cannot reproduce the full resolution of a video. Kitty mode
displays real pixels and is the recommended option for a sharp image.

On Ubuntu or Debian, install Kitty if it is not already available:

```bash
sudo apt install kitty
```

Open Kitty, then run:

```bash
term-tv --renderer kitty --quality high ~/Videos/movie.mp4
```

When `--renderer auto` is used, `term-tv` detects Kitty and selects native
graphics automatically.

### Portable text mode

Use text mode in terminals without Kitty graphics support:

```bash
term-tv --renderer text --quality balanced ~/Videos/movie.mp4
```

Text-mode resolution depends on terminal columns and rows. For a clearer image:

- maximize the terminal window;
- reduce the terminal font size;
- use `--quality high`;
- avoid terminal multiplexers while troubleshooting.

## Common commands

Play a local file:

```bash
term-tv ~/Videos/movie.mp4
```

Play silently:

```bash
term-tv --no-audio ~/Videos/movie.mp4
```

Use the fast preset on slower hardware or remote terminals:

```bash
term-tv --quality fast ~/Videos/movie.mp4
```

Use maximum quality:

```bash
term-tv --quality high ~/Videos/movie.mp4
```

By default, `term-tv` adapts if the terminal cannot keep up. It drops stale
frames, keeps the playback clock from drifting too far behind, and may step
down one quality preset after sustained slow rendering. To force the selected
preset:

```bash
term-tv --quality high --no-adaptive ~/Videos/movie.mp4
```

Open the built-in Internet TV guide:

```bash
term-tv --tv
```

The guide groups channels by category. At the selection prompt:

- enter a channel number to play it;
- enter `/text` to search names and categories;
- enter `c` to select a category;
- enter `a` to clear filters;
- enter `q` to cancel.

The built-in guide currently includes more than 20 free channels across kids,
animation, US and world news, business, weather, nature, documentary, comedy,
pets, and travel.

Play a YouTube URL:

```bash
term-tv --youtube "https://www.youtube.com/watch?v=VIDEO_ID"
```

YouTube URLs also work as the positional argument:

```bash
term-tv "https://youtu.be/VIDEO_ID"
```

Play the first YouTube search result:

```bash
term-tv --youtube "NASA live"
```

You can also run `term-tv`, choose `YouTube`, then enter either a URL or search
query. YouTube media is streamed directly; `term-tv` does not download a video
file.

Play a direct HTTP or HLS stream:

```bash
term-tv "https://example.org/live/channel.m3u8"
```

Open a local M3U playlist:

```bash
term-tv --playlist ~/Downloads/channels.m3u
```

Open a remote M3U playlist:

```bash
term-tv --playlist "https://example.org/channels.m3u"
```

Only play streams and playlists that you are authorized to access. Broadcasters
may change or expire stream URLs independently of `term-tv`.

## Controls

| Key | Action |
| --- | --- |
| `Space` | Pause or resume |
| `Left arrow` | Seek backward 5 seconds |
| `Right arrow` | Seek forward 5 seconds |
| `m` | Cycle through fast, balanced, and high quality |
| `b` | Go back to the previous selection screen |
| `h` | Go back to the main menu |
| `q` | Quit |

Seeking is disabled for live streams that do not report a duration.

## Quality presets

| Preset | Target frame rate | Intended use |
| --- | ---: | --- |
| `fast` | 10 fps | Slow terminals, SSH, and low CPU usage |
| `balanced` | 15 fps | Default text-mode playback |
| `high` | Up to 24 fps | Best scaling, color detail, and Kitty playback |

The high preset uses Lanczos scaling, full-chroma interpolation, sharpening,
and RGB-aware quadrant reconstruction in text mode.

Adaptive playback is enabled unless `--no-adaptive` is provided.

## Troubleshooting

### Audio plays but the picture is frozen

Stop the player, then test the portable path:

```bash
term-tv --renderer text --quality fast --no-audio ~/Videos/movie.mp4
```

Run directly in the terminal rather than through `tmux` or `screen`. If text
mode works and Kitty mode does not, confirm that the command is running inside
Kitty:

```bash
printf '%s\n' "$TERM"
```

Kitty normally reports `xterm-kitty`.

### The video lags behind the audio

Try the fast preset first:

```bash
term-tv --quality fast ~/Videos/movie.mp4
```

For the sharpest playback with less text-rendering overhead, run inside Kitty:

```bash
term-tv --renderer kitty --quality balanced ~/Videos/movie.mp4
```

If you are testing maximum quality, leave adaptive playback enabled. Use
`--no-adaptive` only when you want to benchmark or force a preset.

### The image is blurry

Use Kitty native graphics:

```bash
term-tv --renderer kitty --quality high ~/Videos/movie.mp4
```

In text mode, blur is expected when the terminal has a small character grid.
Increasing the source video's resolution cannot overcome that grid limit.

### `term-tv: command not found`

Reload the shell:

```bash
source ~/.bashrc
```

Then verify the installation path:

```bash
ls -l ~/.local/bin/term-tv
printf '%s\n' "$PATH"
```

### FFmpeg is missing

Confirm all three programs are installed:

```bash
command -v ffmpeg
command -v ffprobe
command -v ffplay
```

### YouTube support is missing

Install or refresh the official YouTube dependencies:

```bash
cd term-tv
./install.sh --with-youtube
source ~/.bashrc
```

Verify them:

```bash
yt-dlp --version
deno --version
```

YouTube changes frequently, so rerun the installer when extraction stops
working. Some age-restricted, private, paid, or region-blocked videos may still
require authentication and are not supported by the built-in resolver.

## Updating

From the cloned repository:

```bash
cd term-tv
git pull --ff-only
./install.sh --with-youtube
```

Because the installed command is a symbolic link, most source updates take
effect immediately. Running the installer again also refreshes the links.

## Uninstalling

Remove the installed commands:

```bash
rm ~/.local/bin/term-tv ~/.local/bin/tvp
```

Then remove the cloned repository if it is no longer needed.

## Development

Run the tests:

```bash
python3 -m unittest -v
```

Check syntax:

```bash
python3 -m py_compile term_tv.py test_term_tv.py
bash -n install.sh
```

The same unit tests run on Python 3.10 and 3.13 through GitHub Actions.

## License

`term-tv` is available under the [MIT License](LICENSE).
