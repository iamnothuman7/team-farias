#!/usr/bin/env bash
set -euo pipefail
if [ "${RENEWED_LINEAGE:-}" = /etc/letsencrypt/live/teamfarias.nabio.pro ]; then
    /usr/sbin/nginx -t
    /bin/systemctl reload nginx
fi
