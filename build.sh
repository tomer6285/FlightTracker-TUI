#!/usr/bin/env bash
# Build a native TUI executable. Run on each target OS/architecture separately.
set -euo pipefail

# Adapted from the Dion build script: package an onedir bundle in a
# self-caching Bash launcher, avoiding extraction on every launch.
case "${1:-}" in
    -h | --help)
        cat <<'EOF'
Usage: ./build.sh

Build dist/flighttracker, a self-caching Linux/macOS executable.
Requires Python with venv support, Bash, and tar. Build on the target OS/CPU.
Set PYTHON to choose the build interpreter, e.g. PYTHON=python3.12 ./build.sh.
EOF
        exit 0
        ;;
    '') ;;
    *) printf 'Usage: ./build.sh\n' >&2; exit 2 ;;
esac
if [[ $# -gt 1 ]]; then
    printf 'Usage: ./build.sh\n' >&2
    exit 2
fi
case "$(uname -s)" in
    Linux | Darwin) ;;
    *) printf 'This self-caching Bash launcher supports Linux and macOS.\n' >&2; exit 1 ;;
esac

printf 'Building FlightTracker-TUI standalone executable...\n'

project_dir=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)
cd -- "$project_dir"

build_python=${PYTHON:-python3}
if ! command -v "$build_python" >/dev/null 2>&1; then
    printf 'Python interpreter not found: %s\n' "$build_python" >&2
    exit 1
fi

"$build_python" -m venv build/venv
venv_python="$project_dir/build/venv/bin/python"

# platformdirs must be available directly; frozen apps cannot rely on pip's
# vendored fallback in setup/configuration.py.
"$venv_python" -m pip install --upgrade pip
"$venv_python" -m pip install \
    'pyinstaller>=6.16,<7' platformdirs \
    -r platforms/tui/requirements.txt

args=(
    --onedir
    --name flighttracker
    --console
    --noconfirm
    --clean
    --noupx
    --distpath build/pyi_dist
    --workpath build/pyi_build
    --specpath build/spec
    --paths "$project_dir"
    # The panel factory and provider registry import these dynamically.
    --hidden-import display.rgbpanel_tui
    --collect-submodules utilities.lookups
    # Preserve resource paths relative to each module's __file__.
    --collect-data scenes
    --collect-data web
    --add-data "$project_dir/fonts:fonts"
    --add-data "$project_dir/assets/splash.bmp:assets"
    --add-data "$project_dir/assets/airlines/airline_logos_16:assets/airlines/airline_logos_16"
    --add-data "$project_dir/LICENSE.md:."
    # This executable targets the terminal; hardware/simulator drivers remain
    # available when running the source with their optional dependencies.
    --exclude-module display.rgbpanel_rgbmatrix
    --exclude-module display.rgbpanel_piomatter
    --exclude-module display.rgbpanel_simulator
    --exclude-module pygame
)
for airport_data in "$project_dir"/assets/*.json; do
    args+=(--add-data "$airport_data:assets")
done

"$venv_python" -m PyInstaller "${args[@]}" "$project_dir/flight-tracker.py"

printf 'Creating self-caching executable...\n'
mkdir -p dist
bundle_archive="$project_dir/build/flighttracker_bundle.tar.gz"
tar -czf "$bundle_archive" -C build/pyi_dist/flighttracker .
# Python is already required at build time, so no platform-specific hash tool
# is needed. The generated launcher does not require Python to be installed.
bundle_hash=$("$venv_python" -c \
    'import hashlib, sys; print(hashlib.sha256(open(sys.argv[1], "rb").read()).hexdigest())' \
    "$bundle_archive")

# Write a temporary output so a failed build does not replace a working one.
launcher=$(mktemp "$project_dir/dist/.flighttracker.XXXXXXXX")
trap 'rm -f -- "$launcher"' EXIT
printf '#!/usr/bin/env bash\nBUNDLE_HASH=%s\n' "$bundle_hash" > "$launcher"
cat >> "$launcher" <<'EOF'
set -euo pipefail

if [[ -n "${XDG_CACHE_HOME:-}" ]]; then
    cache_base="$XDG_CACHE_HOME/flighttracker"
elif [[ "$(uname -s)" == Darwin ]]; then
    cache_base="$HOME/Library/Caches/flighttracker"
else
    cache_base="$HOME/.cache/flighttracker"
fi

cache_dir="$cache_base/$BUNDLE_HASH"
app_bin="$cache_dir/flighttracker"

if [[ ! -x "$app_bin" ]]; then
    mkdir -p -- "$cache_base"
    # Extract completely before publishing the cache, so an interrupted first
    # launch cannot leave an executable alongside only partially unpacked data.
    staging=$(mktemp -d "$cache_base/.extract.XXXXXXXX")
    trap 'rm -rf -- "$staging"' EXIT
    payload_line=$(awk '/^__FLIGHTTRACKER_PAYLOAD_BELOW__$/ {print NR + 1; exit}' "$0")
    tail -n "+$payload_line" "$0" | tar -xzf - -C "$staging"
    if [[ ! -x "$staging/flighttracker" ]]; then
        printf 'FlightTracker bundle extraction failed.\n' >&2
        exit 1
    fi
    # Another launch may have completed extraction while this one unpacked.
    if [[ ! -x "$app_bin" ]]; then
        mv -- "$staging" "$cache_dir"
    fi
    if [[ -d "$staging" ]]; then
        rm -rf -- "$staging"
    fi
    trap - EXIT
fi

exec "$app_bin" "$@"
__FLIGHTTRACKER_PAYLOAD_BELOW__
EOF
cat "$bundle_archive" >> "$launcher"
chmod +x "$launcher"
mv -f -- "$launcher" "$project_dir/dist/flighttracker"
trap - EXIT

printf '\nBuild complete: %s/dist/flighttracker\n' "$project_dir"
printf 'Install for your user: mkdir -p ~/.local/bin && cp dist/flighttracker ~/.local/bin/\n'
