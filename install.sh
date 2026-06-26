#!/usr/bin/env bash
set -euo pipefail

project_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
bin_dir="${HOME}/.local/bin"
launcher="${bin_dir}/term-tv"
legacy_launcher="${bin_dir}/tvp"

mkdir -p "$bin_dir"
ln -sfn "${project_dir}/term_tv.py" "$launcher"
ln -sfn "${project_dir}/term_tv.py" "$legacy_launcher"
chmod +x "${project_dir}/term_tv.py"

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
