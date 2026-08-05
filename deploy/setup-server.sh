#!/usr/bin/env bash
#
# 课评系统 · 腾讯云服务器一键部署脚本
#
# 用法（在服务器上以 root 执行）：
#   bash setup-server.sh
#
# 做的事：装 Docker → 配腾讯云镜像加速 → 拉代码 → 生成随机密钥 → 起服务
# 适用：Ubuntu 22.04 / 24.04、Debian 12（腾讯云轻量应用服务器常见镜像）
#
set -euo pipefail

REPO_URL="${REPO_URL:-https://github.com/lindamannnnn/Ekko.git}"
APP_DIR="${APP_DIR:-/opt/ekko}"

# ---------- 输出美化 ----------
c_blue()  { printf '\033[1;34m%s\033[0m\n' "$*"; }
c_green() { printf '\033[1;32m%s\033[0m\n' "$*"; }
c_yellow(){ printf '\033[1;33m%s\033[0m\n' "$*"; }
c_red()   { printf '\033[1;31m%s\033[0m\n' "$*"; }
step()    { echo; c_blue "━━━ $* ━━━"; }
die()     { c_red "✗ $*"; exit 1; }

[ "$(id -u)" -eq 0 ] || die "请用 root 执行：sudo bash $0"

# ---------- 0. 环境体检 ----------
step "0/7 环境体检"
. /etc/os-release 2>/dev/null || die "无法识别系统版本"
echo "  系统：$PRETTY_NAME"
echo "  内存：$(free -m | awk '/^Mem:/{print $2}') MB"
echo "  磁盘可用：$(df -h / | awk 'NR==2{print $4}')"

MEM_MB=$(free -m | awk '/^Mem:/{print $2}')
if [ "$MEM_MB" -lt 1800 ]; then
  c_yellow "  ⚠ 内存不足 2G，构建镜像可能 OOM。脚本稍后会自动加 swap。"
fi

# 2G 内存构建 Python 镜像容易 OOM，加 2G swap 兜底
if [ "$(swapon --show | wc -l)" -eq 0 ]; then
  step "0.5/7 创建 2G swap（防止构建时内存不足）"
  fallocate -l 2G /swapfile 2>/dev/null || dd if=/dev/zero of=/swapfile bs=1M count=2048
  chmod 600 /swapfile && mkswap /swapfile >/dev/null && swapon /swapfile
  grep -q '/swapfile' /etc/fstab || echo '/swapfile none swap sw 0 0' >> /etc/fstab
  c_green "  ✓ swap 已启用"
fi

# ---------- 1. 装 Docker ----------
step "1/7 安装 Docker"
if command -v docker >/dev/null 2>&1; then
  c_green "  ✓ Docker 已安装：$(docker --version)"
else
  echo "  正在安装（走腾讯云内网源，很快）..."
  apt-get update -qq
  apt-get install -y -qq ca-certificates curl gnupg lsb-release >/dev/null

  # 腾讯云内网 apt 源装 docker.io，比官方源稳定得多
  apt-get install -y -qq docker.io docker-compose-v2 >/dev/null 2>&1 || {
    c_yellow "  内网源不可用，改用官方脚本..."
    curl -fsSL https://get.docker.com | sh
  }
  systemctl enable --now docker
  c_green "  ✓ Docker 安装完成"
fi

# 兼容 docker compose / docker-compose 两种命令
if docker compose version >/dev/null 2>&1; then
  DC="docker compose"
elif command -v docker-compose >/dev/null 2>&1; then
  DC="docker-compose"
else
  apt-get install -y -qq docker-compose-v2 >/dev/null 2>&1 && DC="docker compose" \
    || die "docker compose 安装失败，请手动安装"
fi
echo "  compose 命令：$DC"

# ---------- 2. 配镜像加速（关键！否则拉 python:3.13-slim 会超时）----------
step "2/7 配置容器镜像加速"
mkdir -p /etc/docker
if ! grep -q 'registry-mirrors' /etc/docker/daemon.json 2>/dev/null; then
  cat > /etc/docker/daemon.json <<'JSON'
{
  "registry-mirrors": [
    "https://mirror.ccs.tencentyun.com",
    "https://docker.m.daocloud.io"
  ],
  "log-driver": "json-file",
  "log-opts": { "max-size": "10m", "max-file": "3" }
}
JSON
  systemctl restart docker
  c_green "  ✓ 已配置腾讯云内网镜像源（mirror.ccs.tencentyun.com）"
else
  c_green "  ✓ 镜像加速已配置"
fi

# ---------- 3. 拉代码 ----------
step "3/7 获取代码"
apt-get install -y -qq git >/dev/null 2>&1 || true

if [ -f "$APP_DIR/docker-compose.yml" ]; then
  # 场景一：代码已在本地（scp 上传解压 / 之前部署过）
  if [ -d "$APP_DIR/.git" ]; then
    echo "  检测到 git 仓库，尝试拉取最新..."
    cd "$APP_DIR" && git pull --ff-only 2>/dev/null && c_green "  ✓ 已更新" \
      || c_yellow "  ⚠ 拉取失败（私有仓库需凭据），沿用当前版本"
  else
    c_green "  ✓ 检测到已上传的代码，跳过下载"
  fi
elif [ -n "${GIT_TOKEN:-}" ]; then
  # 场景二：提供了 token，克隆私有仓库
  echo "  使用 token 克隆私有仓库..."
  AUTH_URL=$(echo "$REPO_URL" | sed "s#https://#https://${GIT_TOKEN}@#")
  git clone --depth 1 "$AUTH_URL" "$APP_DIR" || die "克隆失败，请检查 token 是否有效、是否有 repo 读权限"
  # 把 token 从 remote 里洗掉，避免明文留在 .git/config
  cd "$APP_DIR" && git remote set-url origin "$REPO_URL"
  c_green "  ✓ 克隆完成（token 已从配置中清除）"
else
  # 场景三：尝试公开克隆
  echo "  尝试克隆 $REPO_URL ..."
  if ! git clone --depth 1 "$REPO_URL" "$APP_DIR" 2>/dev/null; then
    die "代码获取失败。该仓库是私有的，请三选一：

  【方案A · 推荐】本地打包上传（最简单，不依赖 GitHub）
     在你自己电脑的项目目录执行：
       git archive --format=tar.gz -o ekko.tar.gz HEAD
       scp ekko.tar.gz root@本机IP:/tmp/
     然后在服务器执行：
       mkdir -p $APP_DIR && tar xzf /tmp/ekko.tar.gz -C $APP_DIR
       bash $APP_DIR/deploy/setup-server.sh

  【方案B】用 GitHub Token（后续 git pull 更新方便）
     去 https://github.com/settings/tokens 生成 classic token，勾选 repo 权限，然后：
       GIT_TOKEN=ghp_你的token bash \$0

  【方案C】把仓库改为 Public
     仓库 Settings → 最下方 Danger Zone → Change visibility
     （注意：代码会公开可见，商业项目慎选）"
  fi
fi
cd "$APP_DIR"
c_green "  ✓ 代码就绪：$APP_DIR"

# ---------- 4. 生成 .env ----------
step "4/7 生成配置文件 .env"
if [ -f .env ]; then
  c_yellow "  .env 已存在，跳过生成（如需重置：mv .env .env.bak 后重跑）"
else
  SECRET_KEY=$(openssl rand -hex 32)
  ADMIN_PATH=$(openssl rand -hex 5)          # 后台入口随机路径
  ADMIN_GATE_KEY=$(openssl rand -hex 16)     # 后台第二道门密钥
  ADMIN_PASSWORD=$(openssl rand -base64 12 | tr -d '/+=' | head -c 14)

  echo
  c_yellow "  需要你的大模型 API Key（智谱 GLM 免费额度够用：https://open.bigmodel.cn）"
  read -rp "  请粘贴 AI_API_KEY（留空则稍后手动填 .env）: " AI_API_KEY
  read -rp "  管理员登录邮箱 [admin@local.dev]: " ADMIN_EMAIL
  ADMIN_EMAIL=${ADMIN_EMAIL:-admin@local.dev}

  cat > .env <<ENV
# ===== 自动生成于 $(date '+%F %T') =====
SECRET_KEY=${SECRET_KEY}

# ----- 大模型 -----
AI_API_KEY=${AI_API_KEY}
AI_BASE_URL=https://open.bigmodel.cn/api/paas/v4
AI_MODEL=glm-4-flash
AI_PROXY=

# ----- 数据库（SQLite，数据落在宿主机 ./instance）-----
DATABASE_URL=sqlite:////app/instance/app.db

# ----- 管理员 -----
ADMIN_EMAIL=${ADMIN_EMAIL}
ADMIN_PASSWORD=${ADMIN_PASSWORD}

# ----- 后台入口（随机化，防扫描）-----
ADMIN_PATH=${ADMIN_PATH}
ADMIN_GATE_KEY=${ADMIN_GATE_KEY}

# ----- 邮件（留空=不发信，验证链接打到日志）-----
MAIL_SERVER=
MAIL_PORT=587
MAIL_USE_TLS=true
MAIL_USERNAME=
MAIL_PASSWORD=
MAIL_DEFAULT_SENDER=
ENV
  chmod 600 .env

  cat > CREDENTIALS.txt <<CRED
════════════════════════════════════════════
  课评系统 · 服务器凭据（请立刻抄走并妥善保管）
  生成时间：$(date '+%F %T')
════════════════════════════════════════════
管理员邮箱  ： ${ADMIN_EMAIL}
管理员密码  ： ${ADMIN_PASSWORD}

后台入口路径： /${ADMIN_PATH}/
后台网关密钥： ${ADMIN_GATE_KEY}

登录顺序：先访问 /${ADMIN_PATH}/ → 输入网关密钥 → 再用邮箱密码登录
════════════════════════════════════════════
CRED
  chmod 600 CREDENTIALS.txt
  c_green "  ✓ .env 已生成（密钥均为随机值）"
fi

# ---------- 5. 构建并启动 ----------
step "5/7 构建镜像并启动（首次约 3-8 分钟，请耐心等）"
mkdir -p instance uploads
$DC up -d --build

# ---------- 6. 等待健康检查 ----------
step "6/7 等待服务就绪"
for i in $(seq 1 30); do
  if curl -fsS http://127.0.0.1:5000/health >/dev/null 2>&1; then
    c_green "  ✓ 服务已就绪（/health 返回正常）"
    OK=1; break
  fi
  printf '.'; sleep 3
done
echo
if [ "${OK:-0}" != "1" ]; then
  c_red "  ✗ 服务未能在 90 秒内就绪，最近日志："
  $DC logs --tail 40
  die "启动失败。常见原因：AI_API_KEY 格式错误、内存不足。可执行 '$DC logs -f' 继续排查"
fi

# ---------- 7. 完成 ----------
step "7/7 部署完成"
PUBIP=$(curl -fsS --max-time 5 https://api.ipify.org 2>/dev/null || echo "你的公网IP")
ADMIN_PATH_NOW=$(grep '^ADMIN_PATH=' .env | cut -d= -f2)

echo
c_green "════════════════════════════════════════════"
c_green "  部署成功！"
c_green "════════════════════════════════════════════"
echo
echo "  服务运行在容器内 127.0.0.1:5000"
echo
c_yellow "  ⚠ 现在还无法从外网访问，需要二选一："
echo
echo "  【方案A】装 nginx 反代（推荐，为上 HTTPS 做准备）"
echo "     bash $APP_DIR/deploy/setup-nginx.sh"
echo
echo "  【方案B】临时直接暴露 5000 端口（仅内测用）"
echo "     改 docker-compose.yml 的 ports 为 \"5000:5000\""
echo "     然后 $DC up -d"
echo "     再到腾讯云控制台『防火墙』放行 5000 端口"
echo "     访问 http://${PUBIP}:5000"
echo
c_yellow "  ⚠ 登录凭据已存在：$APP_DIR/CREDENTIALS.txt"
echo "     查看：cat $APP_DIR/CREDENTIALS.txt"
echo "     后台入口：/${ADMIN_PATH_NOW}/"
echo
echo "  常用命令："
echo "     查看日志   cd $APP_DIR && $DC logs -f"
echo "     重启       cd $APP_DIR && $DC restart"
echo "     更新代码   cd $APP_DIR && git pull && $DC up -d --build"
echo
