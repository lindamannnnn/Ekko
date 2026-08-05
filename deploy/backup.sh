#!/usr/bin/env bash
#
# 课评系统 · 数据备份
#
# SQLite 是单文件数据库，服务器一挂或误删就全没了，务必定期备份。
# 用 sqlite3 的 .backup 命令做热备份（直接 cp 在写入瞬间可能拷到损坏文件）。
#
# 用法：
#   bash backup.sh              # 备份到 /opt/ekko-backups
#   bash backup.sh /mnt/disk    # 备份到指定目录
#
# 建议加到 crontab 每天凌晨 3 点自动跑：
#   crontab -e
#   0 3 * * * bash /opt/ekko/deploy/backup.sh >> /var/log/ekko-backup.log 2>&1
#
set -euo pipefail

APP_DIR="${APP_DIR:-/opt/ekko}"
BACKUP_DIR="${1:-/opt/ekko-backups}"
KEEP_DAYS="${KEEP_DAYS:-30}"
TS=$(date '+%Y%m%d_%H%M%S')

c_green() { printf '\033[1;32m%s\033[0m\n' "$*"; }
c_yellow(){ printf '\033[1;33m%s\033[0m\n' "$*"; }
die()     { printf '\033[1;31m✗ %s\033[0m\n' "$*"; exit 1; }

DB="$APP_DIR/instance/app.db"
[ -f "$DB" ] || die "数据库不存在：$DB"

mkdir -p "$BACKUP_DIR"

command -v sqlite3 >/dev/null 2>&1 || apt-get install -y -qq sqlite3

# 1) 数据库热备份
OUT="$BACKUP_DIR/app_${TS}.db"
sqlite3 "$DB" ".backup '$OUT'" || die "数据库备份失败"

# 2) 上传文件 + 配置一起打包
TAR="$BACKUP_DIR/ekko_${TS}.tar.gz"
tar czf "$TAR" \
  -C "$APP_DIR" \
  --transform "s|^app_${TS}.db|app.db|" \
  uploads .env 2>/dev/null || true
# 把刚才的 db 也塞进同一个包，方便整体恢复
tar rf "${TAR%.gz}" -C "$BACKUP_DIR" "app_${TS}.db" 2>/dev/null || true

gzip -f "${TAR%.gz}" 2>/dev/null || true
rm -f "$OUT"

SIZE=$(du -h "$TAR" 2>/dev/null | cut -f1 || echo "?")
c_green "✓ 备份完成：$TAR ($SIZE)"

# 3) 清理过期备份
DELETED=$(find "$BACKUP_DIR" -name 'ekko_*.tar.gz' -mtime "+$KEEP_DAYS" -print -delete | wc -l)
[ "$DELETED" -gt 0 ] && c_yellow "  已清理 $DELETED 个超过 ${KEEP_DAYS} 天的旧备份"

echo
echo "  现有备份："
ls -lh "$BACKUP_DIR"/ekko_*.tar.gz 2>/dev/null | tail -5 | awk '{print "    " $9 "  " $5}'
echo
c_yellow "  ⚠ 强烈建议把备份同步到异地（服务器整机故障时才有用）："
echo "     腾讯云 COS： coscmd upload $TAR /backups/"
echo "     或本地拉取： scp root@服务器IP:$TAR ./"
