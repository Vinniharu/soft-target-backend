#!/usr/bin/env bash
# Soft Target Backend — production deploy script.
#
# Usage (from a workstation):
#   ./scripts/deploy.sh <user>@<host>
#
# Assumptions:
#   - The target host has `uv`, PostgreSQL 16, and Nginx installed.
#   - A `softtarget` system user exists with /opt/softtarget as its home.
#   - /etc/softtarget/softtarget.env holds the production environment.
#   - The systemd unit has already been installed from scripts/systemd/.

set -euo pipefail

if [[ $# -lt 1 ]]; then
    echo "usage: $0 <user>@<host>" >&2
    exit 2
fi

REMOTE="$1"
REMOTE_DIR="/opt/softtarget"
SERVICE="softtarget.service"

echo "==> Checking local tree"
if [[ -n "$(git status --porcelain 2>/dev/null || true)" ]]; then
    echo "working tree is dirty — commit or stash before deploying" >&2
    exit 1
fi

echo "==> Syncing source to ${REMOTE}:${REMOTE_DIR}"
rsync -az --delete \
    --exclude ".git" \
    --exclude ".venv" \
    --exclude "__pycache__" \
    --exclude ".mypy_cache" \
    --exclude ".ruff_cache" \
    --exclude ".pytest_cache" \
    --exclude "var" \
    --exclude "tests" \
    ./ "${REMOTE}:${REMOTE_DIR}/"

echo "==> Installing system dependencies (if missing)"
ssh "${REMOTE}" 'sudo apt-get update -qq && sudo apt-get install -y -qq \
    libpango-1.0-0 \
    libpangoft2-1.0-0 \
    libharfbuzz0b \
    libcairo2 \
    libgdk-pixbuf-2.0-0 \
    shared-mime-info \
    fonts-dejavu'

echo "==> Installing python dependencies via uv"
ssh "${REMOTE}" "cd ${REMOTE_DIR} && sudo -u softtarget uv sync --frozen --no-dev"

echo "==> Applying migrations"
ssh "${REMOTE}" "cd ${REMOTE_DIR} && sudo -u softtarget bash -c 'set -a && source /etc/softtarget/softtarget.env && set +a && uv run alembic upgrade head'"

echo "==> Restarting ${SERVICE}"
ssh "${REMOTE}" "sudo systemctl restart ${SERVICE}"
ssh "${REMOTE}" "sudo systemctl is-active --quiet ${SERVICE}" || {
    echo "service failed to come up — check journalctl -u ${SERVICE}" >&2
    exit 1
}

echo "==> Deploy complete"
