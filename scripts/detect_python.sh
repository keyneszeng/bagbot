#!/usr/bin/env bash
# Print the name of the first Python >= 3.10 found in PATH.
# Exit 1 with actionable guidance if none is found.
set -uo pipefail

for p in python3.13 python3.12 python3.11 python3.10 python3; do
  command -v "$p" >/dev/null 2>&1 || continue
  v="$("$p" -c 'import sys; print("%d.%d" % sys.version_info[:2])' 2>/dev/null)" || continue
  major="${v%%.*}"
  minor="${v##*.}"
  if [[ "$major" == "3" && "$minor" -ge 10 ]] 2>/dev/null; then
    echo "$p"
    exit 0
  fi
done

echo "✗ No Python >= 3.10 found in PATH." >&2
echo "  BagBot needs Python 3.10+. Options:" >&2
echo "    brew install python@3.12" >&2
echo "    pip install uv && uv venv .venv --python 3.12" >&2
echo "  Or point make at one you already have:" >&2
echo "    make install PYTHON=python3.12" >&2
exit 1
