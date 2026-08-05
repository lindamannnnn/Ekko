#!/usr/bin/env bash
#
# 【在你自己的 Windows 电脑上运行，不是服务器】
#
# 私有仓库无法在服务器直接 clone，用这个脚本打包上传。
#
# 用法（在 Git Bash 里，项目根目录执行）：
#   bash deploy/pack-and-upload.sh 你的服务器IP
#
# 首次部署和后续更新都用它。
#
set -euo pipefail

SERVER_IP="${1:-}"
SERVER_USER="${2:-root}"
APP_DIR="/opt/ekko"

c_green() { printf '\033[1;32m%s\033[0m\n' "$*"; }
c_yellow(){ printf '\033[1;33m%s\033[0m\n' "$*"; }
c_blue()  { printf '\033[1;34m%s\033[0m\n' "$*"; }
die()     { printf '\033[1;31m✗ %s\033[0m\n' "$*"; exit 1; }

[ -n "$SERVER_IP" ] || die "用法：bash deploy/pack-and-upload.sh 服务器IP"
[ -f docker-compose.yml ] || die "请在项目根目录执行（当前目录没有 docker-compose.yml）"

# ---------- 1. 打包 ----------
c_blue "━━━ 打包代码 ━━━"

# git archive 只打包已提交的文件，天然排除 .env / .venv / instance
# （比 tar --exclude 更可靠，不会漏掉敏感文件）
if [ -n "$(git status --porcelain 2>/dev/null)" ]; then
  c_yellow "  ⚠ 有未提交的改动，这些改动不会被打包："
  git status --short | head -10
  echo
  read -rp "  要先提交吗？(y=先提交再打包 / n=只打包已提交内容) " ans
  if [ "$ans" = "y" ]; then
    git add -A && git commit -m "chore: 部署前提交" || true
  fi
fi

PKG="/tmp/ekko-$(date +%Y%m%d_%H%M%S).tar.gz"
git archive --format=tar.gz -o "$PKG" HEAD
SIZE=$(du -h "$PKG" | cut -f1)
c_green "  ✓ 打包完成：$SIZE"

# 二次确认没打包进敏感文件
if tar tzf "$PKG" | grep -qE '^\.env$|CREDENTIALS.txt|app\.db'; then
  rm -f "$PKG"
  die "打包内容包含敏感文件，已中止。请检查 .gitignore"
fi
c_green "  ✓ 已确认不含 .env / 数据库 / 凭据文件"

# ---------- 2. 上传 ----------
c_blue "━━━ 上传到 ${SERVER_USER}@${SERVER_IP} ━━━"
echo "  （会提示输入服务器密码）"
scp "$PKG" "${SERVER_USER}@${SERVER_IP}:/tmp/ekko.tar.gz" || die "上传失败，检查 IP 和网络"
c_green "  ✓ 上传完成"

# ---------- 3. 远程解压部署 ----------
c_blue "━━━ 在服务器上解压并部署 ━━━"
echo "  （会再次提示输入密码）"

ssh "${SERVER_USER}@${SERVER_IP}" bash -s <<REMOTE
set -e
mkdir -p ${APP_DIR}
tar xzf /tmp/ekko.tar.gz -C ${APP_DIR}
rm -f /tmp/ekko.tar.gz
chmod +x ${APP_DIR}/deploy/*.sh

if [ -f ${APP_DIR}/.env ]; then
    echo "检测到已有配置，执行更新..."
    cd ${APP_DIR}
    if docker compose version >/dev/null 2>&1; then
        docker compose up -d --build
    else
        docker-compose up -d --build
    fi
    echo "更新完成"
else
    echo "首次部署，请接着运行初始化脚本"
fi
REMOTE

rm -f "$PKG"

echo
c_green "════════════════════════════════════════════"
c_green "  代码已送达服务器"
c_green "════════════════════════════════════════════"
echo
c_yellow "  如果是【首次部署】，现在登录服务器执行初始化："
echo
echo "     ssh ${SERVER_USER}@${SERVER_IP}"
echo "     bash ${APP_DIR}/deploy/setup-server.sh"
echo
c_yellow "  如果是【更新代码】，已经自动重启完成，无需其他操作。"
echo
