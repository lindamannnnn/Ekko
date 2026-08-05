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
- `AI_API_KEY`：智谱 GLM-4-Flash 的 API Key（https://open.bigmodel.cn/usercenter/apikeys 获取）
- `AI_BASE_URL` / `AI_MODEL`：默认 `https://open.bigmodel.cn/api/paas/v4` / `glm-4-flash`
- `MAIL_*`：发信邮箱（可选，不填则 dev 模式控制台打印链接）

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
