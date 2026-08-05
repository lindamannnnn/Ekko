#!/usr/bin/env bash
#
# 课评系统 · nginx 反向代理配置（阶段一：HTTP）
#
# 用法：
#   bash setup-nginx.sh                 # 只用 IP 访问（备案期间用这个）
#   bash setup-nginx.sh your-domain.com # 已有域名且已解析
#
# 备案通过后再执行 enable-https.sh 升级为 HTTPS。
#
set -euo pipefail

DOMAIN="${1:-}"
APP_DIR="${APP_DIR:-/opt/ekko}"

c_green() { printf '\033[1;32m%s\033[0m\n' "$*"; }
c_yellow(){ printf '\033[1;33m%s\033[0m\n' "$*"; }
c_blue()  { printf '\033[1;34m%s\033[0m\n' "$*"; }
die()     { printf '\033[1;31m✗ %s\033[0m\n' "$*"; exit 1; }

[ "$(id -u)" -eq 0 ] || die "请用 root 执行：sudo bash $0"

c_blue "━━━ 安装 nginx ━━━"
if ! command -v nginx >/dev/null 2>&1; then
  apt-get update -qq && apt-get install -y -qq nginx
fi
c_green "  ✓ nginx $(nginx -v 2>&1 | grep -o '[0-9.]*')"

# server_name：有域名填域名，没有就用 _ 匹配所有（IP 直接访问）
SERVER_NAME="${DOMAIN:-_}"

c_blue "━━━ 写入站点配置 ━━━"
cat > /etc/nginx/sites-available/ekko <<NGINX
server {
    listen 80;
    listen [::]:80;
    server_name ${SERVER_NAME};

    # 课件上传（PPT/PDF 可能较大），默认 1M 会导致上传失败
    client_max_body_size 64M;

    # 大模型生成课评耗时长，超时必须放宽，否则前端收到 504
    proxy_connect_timeout 60s;
    proxy_send_timeout    300s;
    proxy_read_timeout    300s;

    # 隐藏版本号，减少指纹暴露
    server_tokens off;

    access_log /var/log/nginx/ekko.access.log;
    error_log  /var/log/nginx/ekko.error.log;

    location / {
        proxy_pass http://127.0.0.1:5000;
        proxy_http_version 1.1;

        proxy_set_header Host              \$host;
        proxy_set_header X-Real-IP         \$remote_addr;
        proxy_set_header X-Forwarded-For   \$proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto \$scheme;
        proxy_set_header Upgrade           \$http_upgrade;
        proxy_set_header Connection        "upgrade";

        proxy_buffering off;   # AI 流式输出不缓冲
    }

    # 静态文件直接由 nginx 吐，不打扰 Flask
    location /static/ {
        proxy_pass http://127.0.0.1:5000/static/;
        proxy_cache_valid 200 7d;
        expires 7d;
        add_header Cache-Control "public";
    }
}
NGINX

ln -sf /etc/nginx/sites-available/ekko /etc/nginx/sites-enabled/ekko
rm -f /etc/nginx/sites-enabled/default   # 去掉 nginx 默认欢迎页

c_blue "━━━ 校验配置 ━━━"
nginx -t || die "nginx 配置有误，请检查上方报错"

systemctl enable nginx >/dev/null 2>&1 || true
systemctl reload nginx || systemctl restart nginx
c_green "  ✓ nginx 已生效"

# 确保容器只监听回环（安全）
cd "$APP_DIR" 2>/dev/null && {
  if grep -q '^\s*-\s*"5000:5000"' docker-compose.yml 2>/dev/null; then
    c_yellow "  ⚠ 检测到容器仍在裸奔 0.0.0.0:5000，建议改回 127.0.0.1:5000:5000"
  fi
}

PUBIP=$(curl -fsS --max-time 5 https://api.ipify.org 2>/dev/null || echo "你的公网IP")

echo
c_green "════════════════════════════════════════════"
c_green "  nginx 反代配置完成"
c_green "════════════════════════════════════════════"
echo
if [ -n "$DOMAIN" ]; then
  echo "  访问地址： http://${DOMAIN}"
  echo
  c_yellow "  下一步：备案通过后升级 HTTPS"
  echo "     bash $APP_DIR/deploy/enable-https.sh ${DOMAIN} 你的邮箱@example.com"
else
  echo "  访问地址： http://${PUBIP}"
  echo
  c_yellow "  当前是 IP 访问（HTTP 明文，密码会被中间人看到，仅适合内测）"
  echo "     域名备案通过后执行："
  echo "     bash $APP_DIR/deploy/setup-nginx.sh 你的域名.com"
fi
echo
c_yellow "  ⚠ 别忘了在腾讯云控制台『防火墙』放行 80 端口（HTTPS 还需 443）"
echo
