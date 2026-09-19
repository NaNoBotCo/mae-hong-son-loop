#!/bin/bash
# Build the public site into docs/ — the directory GitHub Pages serves.
#
# The canonical host comes from docs/CNAME when a domain is attached, and falls back to
# the GitHub Pages address. To attach a domain later:  CNAME=example.com ./publish.sh
set -euo pipefail
cd "$(dirname "$0")"

DOMAIN="${CNAME:-$(head -1 docs/CNAME 2>/dev/null || true)}"
if [ -n "$DOMAIN" ]; then SITE_URL="https://$DOMAIN"
else SITE_URL="https://nanobotco.github.io/mae-hong-son-loop"; fi

export PYTHONUTF8=1

STYLE="$HOME/.claude/bin/stylecheck.py"
if [ -f "$STYLE" ]; then
  python3 "$STYLE" tools data schema README.md NOTICE.txt notes || {
    echo "REFUSED: style. See ~/.claude/STYLE.md"; exit 4; }
fi

python3 tools/validate.py
python3 tools/curves.py
SITE_URL="$SITE_URL" python3 tools/build.py
SITE_URL="$SITE_URL" python3 tools/site.py

rm -rf docs
mkdir -p docs
cp -R build/site/ docs/
touch docs/.nojekyll                      # so /api/ and dot-files are served as-is
[ -n "$DOMAIN" ] && echo "$DOMAIN" > docs/CNAME

# nothing that names this machine may be published
if grep -rl "/Users/" docs >/dev/null 2>&1; then
  echo "REFUSED: host paths found in docs/"; exit 2
fi
echo "docs/ built for $SITE_URL — $(find docs -name '*.html' | wc -l | tr -d ' ') pages, $(du -sh docs | cut -f1)"
