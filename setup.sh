#!/bin/bash
set -e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
PLIST_SRC="$PROJECT_DIR/launchd/com.bathjobs.scraper.plist"
PLIST_DEST="$HOME/Library/LaunchAgents/com.bathjobs.scraper.plist"

mkdir -p "$HOME/Library/LaunchAgents"

sed "s|PROJECT_DIR|$PROJECT_DIR|g" "$PLIST_SRC" > "$PLIST_DEST"

launchctl unload "$PLIST_DEST" 2>/dev/null || true
launchctl load "$PLIST_DEST"

echo "Scheduler installed. Scraper will run at 6am and 6pm daily."
echo "To verify: launchctl list | grep bathjobs"
