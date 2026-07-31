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
- [ ] `.env` 已填真实 Key，未提交到仓库
- [ ] `SECRET_KEY` 已改为随机值
- [ ] 反向代理（Nginx）已配置 HTTPS
- [ ] 数据库已备份策略
