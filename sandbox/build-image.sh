#!/bin/sh
# Build the guest image: Gondolin's Alpine base plus git, gh, make, and aw from this checkout.
#
# aw has no runtime dependencies, so it goes in as plain files: no network and no root to install it
# (gondolin's postBuild.commands chroot and need root; postBuild.copy does not). The modules are compiled here
# with the guest's Python: every VM starts from the image, so bytecode compiled in the guest would be thrown
# away with it, and aw would pay ~1.5 s of compiling on each start (a zipapp pays it on every call).
set -eu
guest_python=3.12 # Alpine 3.23's python3; a mismatch only makes aw slower, the bytecode is then ignored
here=$(cd "$(dirname "$0")" && pwd)
repo=$(cd "$here/.." && pwd)
build="$here/build"

rm -rf "$build"
mkdir -p "$build/aw-lib"
cp -r "$repo/src/aw" "$build/aw-lib/"
find "$build/aw-lib" -name __pycache__ -prune -exec rm -rf {} +
uv run --no-project --python "$guest_python" python -m compileall -q --invalidation-mode unchecked-hash "$build/aw-lib"
cat > "$build/aw" <<'PY'
#!/usr/bin/env python3
import sys

sys.path.insert(0, "/usr/local/lib/aw")
from aw.cli import main

sys.exit(main())
PY
chmod +x "$build/aw"

cd "$here"
npx gondolin build --config image.json --output "$build/image"
npx gondolin build --verify "$build/image"
