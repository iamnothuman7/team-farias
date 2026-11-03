#!/usr/bin/env bash
# Uso: bash release.sh /caminho/release.tar.gz COMMIT SHA256
set -euo pipefail
umask 027
base=/var/www/apps/teamfarias
archive=${1:?Informe o arquivo gerado por git archive}
commit=${2:?Informe o commit completo testado e enviado ao GitHub}
checksum=${3:?Informe o SHA256 do arquivo}
[[ "$commit" =~ ^[0-9a-f]{40}$ ]] || exit 2
[[ "$checksum" =~ ^[0-9a-f]{64}$ ]] || exit 2
printf '%s  %s\n' "$checksum" "$archive" | sha256sum --check --status
test -f "$base/shared/.env"
release="$base/releases/$(date -u +%Y%m%d-%H%M%S)-${commit:0:12}"
test ! -e "$release"
mkdir -m 751 "$release"
# Arquivo produzido pelo Git; rejeita membros fora da release antes de extrair.
python3 - "$archive" <<'PY'
import sys, tarfile
from pathlib import PurePosixPath
with tarfile.open(sys.argv[1]) as archive:
    for item in archive.getmembers():
        path = PurePosixPath(item.name)
        if path.is_absolute() or '..' in path.parts or item.issym() or item.islnk() or item.isdev():
            raise SystemExit('Membro de arquivo não permitido.')
PY
tar -xzf "$archive" -C "$release" --no-same-owner
chmod -R a+rX "$release"
printf '%s\n' "$commit" > "$release/REVISION"
python3 -m venv "$release/.venv"
"$release/.venv/bin/pip" install --disable-pip-version-check -r "$release/requirements.txt"
chmod -R a+rX "$release/.venv"
(
    set -a
    source "$base/shared/.env"
    set +a
    cd "$release"
    "$release/.venv/bin/python" manage.py check
    "$release/.venv/bin/python" manage.py makemigrations --check --dry-run
    # Primeiro deploy também tem backup; banco inicialmente vazio.
    if [ -e "$base/current" ]; then bash "$base/current/deploy/backup.sh"; fi
    "$release/.venv/bin/python" manage.py migrate --noinput
    DJANGO_STATIC_ROOT="$release/staticfiles" "$release/.venv/bin/python" manage.py collectstatic --noinput
)
chmod -R a+rX "$release/staticfiles"
# Preserva arquivos com hash de releases anteriores para rollback e clientes antigos.
cp -a "$release/staticfiles/." "$base/shared/staticfiles/"
if [ -e "$base/current" ]; then
    ln -sfn "$(readlink -f "$base/current")" "$base/previous"
fi
ln -s "$release" "$base/current.next"
mv -Tf "$base/current.next" "$base/current"
ln -sfn "$base/current/.venv" "$base/venv"
printf 'Release preparada: %s\nCommit: %s\n' "$release" "$commit"
# Reinício é separado para permitir nginx -t e systemd-analyze verify antes de ativar.
