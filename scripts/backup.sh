#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
BACKUP_DIR="${ROOT_DIR}/backups"
TS="$(date +"%Y%m%d-%H%M%S")"

mkdir -p "${BACKUP_DIR}"

tar --ignore-failed-read -czf "${BACKUP_DIR}/cannibal-backup-${TS}.tar.gz" \
  -C "${ROOT_DIR}" \
  cannibal.db \
  chroma \
  output.txt \
  .env

echo "Backup saved to ${BACKUP_DIR}/cannibal-backup-${TS}.tar.gz"
