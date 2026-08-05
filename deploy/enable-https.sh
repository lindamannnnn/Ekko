#!/usr/bin/env bash
#
# 课评系统 · 一键开启 HTTPS（Let's Encrypt 免费证书，自动续期）
#
# 前置条件（缺一不可，否则申请必失败）：
#   1. 域名已解析到本机公网 IP（A 记录）
#   2. 国内服务器：域名已完成 ICP 备案（否则 80 端口被运营商拦截）
#   3. 腾讯云防火墙已放行 80 和 443
#   4. 已执行过 setup-nginx.sh
#
# 用法：
#   bash enable-https.sh your-domain.com your-email@example.com
#
set -euo pipefail

DOMAIN="${1:-}"
EMAIL="${2:-}"

c_green() { printf '\033[1;32m%s\033[0m\n' "$*"; }
c_yellow(){ printf '\033[1;33m%s\033[0m\n' "$*"; }
c_blue()  { printf '\033[1;34m%s\033[0m\n' "$*"; }
die()     { printf '\033[1;31m✗ %s\033[0m\n' "$*"; exit 1; }

[ "$(id -u)" -eq 0 ] || die "请用 root 执行：sudo bash $0 域名 邮箱"
[ -n "$DOMAIN" ] || die "用法：bash $0 your-domain.com your-email@example.com"
[ -n "$EMAIL" ]  || die "需要邮箱（证书到期前 Let's Encrypt 会发提醒）"

# ---------- 前置校验：先确认解析真的指到本机 ----------
c_blue "━━━ 检查域名解析 ━━━"
apt-get install -y -qq dnsutils >/dev/null 2>&1 || true
PUBIP=$(curl -fsS --max-time 8 https://api.ipify.org 2>/dev/null || echo "")
RESOLVED=$(dig +short "$DOMAIN" @223.5.5.5 2>/dev/null | tail -1)

echo "  本机公网 IP ： ${PUBIP:-未知}"
echo "  域名解析到  ： ${RESOLVED:-未解析}"

if [ -z "$RESOLVED" ]; then
  die "域名 $DOMAIN 尚未解析。请到腾讯云『域名管理 → 解析』添加 A 记录指向 $PUBIP，等 10 分钟后重试"
fi
if [ -n "$PUBIP" ] && [ "$RESOLVED" != "$PUBIP" ]; then
  c_yellow "  ⚠ 解析 IP 与本机不一致，证书申请可能失败"
  read -rp "  仍要继续吗？(y/N) " go
  [ "$go" = "y" ] || exit 1
else
  c_green "  ✓ 解析正确"
fi

# ---------- 装 certbot ----------
c_blue "━━━ 安装 certbot ━━━"
if ! command -v certbot >/dev/null 2>&1; then
  apt-get update -qq
  apt-get install -y -qq certbot python3-certbot-nginx
fi
c_green "  ✓ certbot 就绪"

# ---------- 确保 nginx 里有这个域名 ----------
if ! grep -q "$DOMAIN" /etc/nginx/sites-available/ekko 2>/dev/null; then
  c_yellow "  nginx 配置里还没有该域名，正在更新..."
  bash "$(dirname "$0")/setup-nginx.sh" "$DOMAIN"
fi

# ---------- 申请证书 ----------
c_blue "━━━ 申请证书并自动改写 nginx ━━━"
certbot --nginx \
  -d "$DOMAIN" \
  --non-interactive \
  --agree-tos \
  --email "$EMAIL" \
  --redirect \
  || die "证书申请失败。排查顺序：
  1) 80 端口是否放行（腾讯云防火墙 + ufw）
  2) 国内服务器域名是否已备案（未备案 80 端口被拦，certbot 必失败）
  3) 解析是否生效：dig +short $DOMAIN
  4) 看详细日志：cat /var/log/letsencrypt/letsencrypt.log"

# ---------- 加固 HTTPS 头 ----------
c_blue "━━━ 追加安全响应头 ━━━"
CONF=/etc/nginx/sites-available/ekko
if ! grep -q 'Strict-Transport-Security' "$CONF"; then
  # 插到 443 server 块内（certbot 已生成 listen 443 行）
  sed -i '/listen 443 ssl/a\    add_header Strict-Transport-Security "max-age=31536000" always;\n    add_header X-Content-Type-Options "nosniff" always;\n    add_header X-Frame-Options "SAMEORIGIN" always;\n    add_header Referrer-Policy "strict-origin-when-cross-origin" always;' "$CONF"
  nginx -t && systemctl reload nginx
  c_green "  ✓ 已加 HSTS / nosniff / 防点击劫持"
fi

# ---------- 自动续期 ----------
c_blue "━━━ 配置自动续期 ━━━"
systemctl enable --now certbot.timer >/dev/null 2>&1 || true
certbot renew --dry-run >/dev/null 2>&1 \
  && c_green "  ✓ 续期演练通过，证书到期前会自动更新" \
  || c_yellow "  ⚠ 续期演练未通过，请留意到期提醒邮件"

echo
c_green "════════════════════════════════════════════"
c_green "  HTTPS 已启用"
c_green "════════════════════════════════════════════"
echo
echo "  访问地址： https://${DOMAIN}"
echo "  HTTP 会自动跳转到 HTTPS"
echo "  证书有效期 90 天，到期自动续期"
echo
c_yellow "  ⚠ 确认腾讯云防火墙已放行 443 端口"
echo
