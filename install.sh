#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
bin_dir="${HOME}/.local/bin"
launcher="${bin_dir}/term-tv"
legacy_launcher="${bin_dir}/tvp"
install_youtube=false

for argument in "$@"; do
  case "$argument" in
    --with-youtube) install_youtube=true ;;
    -h|--help)
      printf 'Usage: %s [--with-youtube]\n' "$0"
      exit 0
      ;;
    *)
      printf 'Unknown option: %s\n' "$argument" >&2
      exit 2
      ;;
  esac
done

mkdir -p "$bin_dir"
ln -sfn "${project_dir}/term_tv.py" "$launcher"
ln -sfn "${project_dir}/term_tv.py" "$legacy_launcher"
chmod +x "${project_dir}/term_tv.py"

if "$install_youtube"; then
  yt_dlp="${bin_dir}/yt-dlp"
  temporary="${yt_dlp}.download"
  url="https://github.com/yt-dlp/yt-dlp/releases/latest/download/yt-dlp"
  if command -v curl >/dev/null 2>&1; then
    curl -fL "$url" -o "$temporary"
  elif command -v wget >/dev/null 2>&1; then
    wget -O "$temporary" "$url"
  else
    printf 'Installing YouTube support requires curl or wget.\n' >&2
    exit 1
  fi
  chmod +x "$temporary"
  mv "$temporary" "$yt_dlp"
  printf 'Installed YouTube support at %s\n' "$yt_dlp"

  machine="$(uname -m)"
  system="$(uname -s)"
  case "${system}:${machine}" in
    Linux:x86_64) deno_target="x86_64-unknown-linux-gnu" ;;
    Linux:aarch64|Linux:arm64) deno_target="aarch64-unknown-linux-gnu" ;;
    Darwin:x86_64) deno_target="x86_64-apple-darwin" ;;
    Darwin:arm64|Darwin:aarch64) deno_target="aarch64-apple-darwin" ;;
    *)
      printf 'Unsupported platform for automatic Deno installation: %s %s\n' \
        "$system" "$machine" >&2
      exit 1
      ;;
  esac
  deno_archive="${bin_dir}/deno.zip"
  deno_url="https://github.com/denoland/deno/releases/latest/download/deno-${deno_target}.zip"
  if command -v curl >/dev/null 2>&1; then
    curl -fL "$deno_url" -o "$deno_archive"
  else
    wget -O "$deno_archive" "$deno_url"
  fi
  python3 -m zipfile -e "$deno_archive" "$bin_dir"
  rm "$deno_archive"
  chmod +x "${bin_dir}/deno"
  printf 'Installed Deno JavaScript runtime at %s\n' "${bin_dir}/deno"
fi

case ":${PATH}:" in
  *":${bin_dir}:"*) ;;
  *)
    profile="${HOME}/.bashrc"
    line='export PATH="$HOME/.local/bin:$PATH"'
    if ! grep -Fqx "$line" "$profile" 2>/dev/null; then
      printf '\n# User-installed command-line programs\n%s\n' "$line" >> "$profile"
    fi
    ;;
esac

printf 'Installed term-tv at %s\n' "$launcher"
printf 'Installed compatibility alias at %s\n' "$legacy_launcher"
printf 'Open a new terminal, then run: term-tv\n'
