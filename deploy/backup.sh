#!/usr/bin/env bash
set -euo pipefail
umask 077
base=/var/www/apps/teamfarias
commit=$(cat "$base/current/REVISION")
stamp=$(date -u +%Y%m%d-%H%M%S)
destination="$base/shared/backups/${stamp}-${commit:0:12}"
mkdir -m 700 "$destination"
runuser -u postgres -- pg_dump -Fc teamfarias_prod > "$destination/database.dump"
tar -czf "$destination/media.tar.gz" -C "$base/shared" media
cp "$base/shared/.env" "$destination/environment"
printf '%s\n' "$commit" > "$destination/REVISION"
sha256sum "$destination/database.dump" "$destination/media.tar.gz" > "$destination/SHA256SUMS"
printf 'Backup Team Farias: %s\n' "$destination"
