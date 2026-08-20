# 部署文档（通用少儿培训机构课评系统）

## 本地运行
```bash
cd E:/001/class-review-system
export FLASK_APP=app:create_app
flask db upgrade      # 建表
flask seed            # 载入 8 类机构预置
python run.py         # 启动，访问 http://127.0.0.1:5000
```

## 配置 .env
复制 `.env.example` 为 `.env` 并填入：
- `AI_API_KEY`：智谱 GLM-4-Flash 的 API Key（https://open.bigmodel.cn/usercenter/apikeys 获取），作为平台默认 KEY
- `AI_BASE_URL` / `AI_MODEL`：默认 `https://open.bigmodel.cn/api/paas/v4` / `glm-4-flash`
- `MAIL_*`：发信邮箱（可选，不填则 dev 模式控制台打印链接）

### 用户自定义 API KEY（可选）
老师在「账号设置 → AI API KEY」或「课前备课 → API KEY 管理」填入自己的 OpenAI 兼容 KEY（可配 base_url / model）后：
- **课评生成**（班级编辑器一键生成 / 单人生成）
- **课前备课学科生成**
- **课前备课内容生成**
- **学生阶段总结**
- **卡片标签情感判定**
都会优先使用用户 KEY；未配置或清空时回退到平台默认 `.env` 中的 KEY。

## Docker 部署
```bash
docker compose up -d --build
# 首次需手初始化库
docker compose exec web flask db upgrade
docker compose exec web flask seed
```
访问宿主机 `http://<服务器IP>:5000`。

## 生产检查清单

### 已完成的安全加固（代码层面）
- [x] **CSRF 全局开启**（`WTF_CSRF_ENABLED=True`）；`reviews` 纯 JSON API 蓝图已豁免，其鉴权由 `@login_required` 保证；前端 `base.html`/`admin/base.html` 已加 `<meta csrf-token>` + 全局 fetch 钩子自动带 `X-CSRFToken`。
- [x] **SECRET_KEY 走环境变量**：`os.environ['SECRET_KEY']`，未设置则本地随机并打告警（仅适合本地，重启即失效）。
- [x] **管理员密码随机化**：`ADMIN_PASSWORD` 未设置时生成本地随机密码并打日志。
- [x] **登录限流**：auth 登录与后台登录加 IP 滑动窗口（60s ≤10 次，超限 429）。注意：当前为**内存级**，多实例部署需换 Redis。
- [x] **上传校验**：`src/security/upload_check.py` = 扩展名白名单 + **文件头魔数校验**（拦改名绕过）+ 大小 ≤10MB；解析文本 ≤1.5MB（防解析炸弹）。`uploads/` 目录**不对外静态托管**。
- [x] **多租户隔离**：查询层强制 `user_id` 过滤（TenantMixin）。
- [x] **`.env` 已 gitignore**，密钥不入库。

### 上线前仍需处理
- [ ] `.env` 已填真实 Key（`AI_API_KEY` 必填），且**未提交到仓库**。
- [ ] `SECRET_KEY` 已设为固定随机串（环境变量，非默认值）。
- [ ] `ADMIN_EMAIL` / `ADMIN_PASSWORD` 已固定设置（不要依赖启动随机密码）。
- [ ] 反向代理（Nginx）已配置 **HTTPS**，并关闭 Flask `debug`。
- [ ] 改用 **waitress / gunicorn** 等 WSGI 服务器替代 Flask dev server（当前 `python run.py` 仅适合开发）。
- [ ] 数据库**定期备份**策略（SQLite 单文件，建议定时 `cp` + WAL 归档）。
- [ ] 登录限流在多实例下换 **Redis** 共享计数。
- [ ] （可选）SMTP `MAIL_*` 已配置，关闭邮件 dev 模式（否则只打印链接不真发信）。
- [ ] 68 个本地改动提交入库（含旧系统清理），保留可追溯历史。

---

## 部署补充（2026-08-20 上线准备）

### 1. 用户自定义 API KEY 现已覆盖课评生成（2026-08-20）
- 此前用户填写的 `ai_api_key` 只在课前备课生效；本次修复后，课评生成、去重重写、学生阶段总结、卡片标签情感判定均会优先使用用户 KEY。
- 账号页与课前备课页的 UI 文案已同步更新为「AI API KEY」。

### 2. 请假课评行为（2026-08-20）
- 编辑器中点击「请假」后，系统直接写入 `content = "请假"` 并将状态置为 `leave`，**不再调用 AI**。
- 对 `leave` 状态再次点击「生成」会直接返回「请假」，不消耗 token。
- `leave` 状态会计入编辑器顶部「已完成」计数。

### 3. 课前备课内容生成支持代码块（2026-08-20）
- 上传内容生成课件时，标准 Markdown 围栏代码块与 `python`/`plaintext`/`scratch` 等无围栏代码块会被保留并渲染为 `<pre><code>`，保留原始缩进，避免语言标记污染 bullet。

## 部署补充（2026-08-05 上线准备）

### 1. AI 代理已修复（重要）
`src/ai/llm_client.py` 现默认**直连**大模型，不继承系统 `HTTP(S)_PROXY`，避免开发机/部署机的代理环境变量导致 AI 调用 `ProxyError 10061`。仅在需经代理访问大模型时，在 `.env` 设 `AI_PROXY=http://host:port`。`.env.example` 已增加 `AI_PROXY` 项（默认留空=直连）。

### 2. 后台门禁必须在服务器设随机值
`.env` 必须包含 `ADMIN_EMAIL` / `ADMIN_PASSWORD` / `ADMIN_PATH` / `ADMIN_GATE_KEY`（`.env.example` 已补充）。**上线务必把 `ADMIN_PATH` 和 `ADMIN_GATE_KEY` 改为服务器专属随机串**，不要使用默认值，否则后台入口可被轻易猜到。

### 3. Docker 部署修正
- `Dockerfile` 已改用 `gunicorn -w 4 -k gthread -b 0.0.0.0:5000 run:app`（替代 `python run.py` 开发服务器）。
- `docker-compose.yml` 已补全环境变量（`ADMIN_*` / `MAIL_*` / `DATABASE_URL` / `AI_PROXY`），并加健康检查。
- 用法：
  ```bash
  cp .env.example .env   # 填入真实值（SECRET_KEY/AI_API_KEY/ADMIN_* 必填）
  docker compose up -d --build
  docker compose exec web flask db upgrade
  docker compose exec web flask seed
  ```
  容器仅暴露 5000，生产请在宿主机前置 nginx 反代 + HTTPS（见下）。

### 4. 传统服务器部署（gunicorn + nginx + systemd，非 Docker）
1. 服务器装 Python 3.13，建 venv，装依赖：`pip install -r requirements.txt gunicorn`
2. 放 `.env`（SECRET_KEY 用 `python -c "import secrets;print(secrets.token_hex(32))"` 生成；AI_API_KEY/ADMIN_* 必填）
3. 初始化：`flask db upgrade && flask seed`
4. `/etc/systemd/system/ekko.service`：
   ```
   [Unit]
   Description=Ekko 课评系统
   After=network.target
   [Service]
   User=www-data
   WorkingDirectory=/opt/ekko
   Environment=FLASK_APP=app:create_app
   ExecStart=/opt/ekko/venv/bin/gunicorn -w 4 -k gthread -b 127.0.0.1:5000 run:app
   Restart=always
   [Install]
   WantedBy=multi-user.target
   ```
5. nginx 反代 + HTTPS（certbot）：
   ```
   server {
     listen 80; server_name your.domain.com;
     location /static { alias /opt/ekko/static; }
     location / {
       proxy_pass http://127.0.0.1:5000;
       proxy_set_header Host $host;
       proxy_set_header X-Real-IP $remote_addr;
       proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
       proxy_set_header X-Forwarded-Proto $scheme;
     }
   }
   ```
   然后 `certbot --nginx -d your.domain.com` 开启 HTTPS（强制 443 + HSTS）。
6. 数据库备份：定时 `cp instance/app.db instance/app.db.bak` + WAL 归档。

### 5. 多用户并发注意
- AI 调用为同步阻塞（最长 120s），gunicorn 用 `-k gthread --threads 4` 提升单 worker 并发；若量大可加 worker 数或换异步队列。
- 智谱免费 key 有 QPS 限制，多用户高频调用可能触发限流，必要时升级配额或多 key 轮询（代码已支持 channel.py 多 key）。
- SQLite 多用户写有锁，建议监控；量大迁 Postgres（`DATABASE_URL` 切换）。
