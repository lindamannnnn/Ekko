# 课评自动生成系统

一个面向**少儿培训机构**的多租户 Web 系统：老师建好「班级 → 学生 → 课次」并上传课件后，系统用 AI 自动生成结构统一的课后评价，经老师编辑确认，可导出 Excel / PDF、生成家长群分享卡片、发送提醒。

---

## 功能特点

- 🏫 **多班级管理**：班级、学生、课次全周期管理，支持归档/删除。
- 📚 **课件上传与解析**：支持 `txt / pptx / docx / pdf`，自动抽取文字与教学目标，喂给 AI。
- 🤖 **AI 课评生成**：结合课件知识点 + 学生基本信息 + 本班优秀课评范例，生成草稿。
- 📝 **两段式课评结构**（系统硬约束）：
  - **段① 课堂内容总结** —— 本节课知识点，编号列表，纯内容不夹评价；
  - **段② 课后评价** —— 写给家长/孩子的评价，首句点名学生昵称，末尾含家庭建议。
- ✏️ **可视化编辑器**：课程目标、当节课表现要点、知识点（AI 辅助提取）、优秀范例一键参考。
- ✅ **状态流转**：草稿 → 确认 → 已发布；支持请假、撤回、删除、历史查看。
- 📤 **多形态导出**：Excel 汇总、PDF 报告、家长群分享卡片（图片）、微信/邮件提醒。
- 🔐 **账号与安全**：邮箱注册 + 验证、找回密码、密码 bcrypt 哈希、CSRF 防护、登录限流、上传文件魔数校验。
- 🛠️ **平台总后台**（仅超管）：用户 / 班级 / 课件 / 课评 统一管理。

---

## 技术栈

- **后端**：Python 3.11+ · Flask 3.x · Jinja2
- **数据库**：SQLite（WAL）+ SQLAlchemy 2.x + Flask-Migrate
- **鉴权**：Flask-Login · bcrypt · Flask-WTF（CSRF）
- **AI**：OpenAI 兼容接口（默认智谱 GLM-4-Flash）
- **解析/导出**：pdfplumber · python-pptx · python-docx · openpyxl · reportlab · Pillow
- **部署**：Docker / 本地 Flask（建议生产换 waitress/gunicorn + Nginx + HTTPS）

---

## 目录结构（精简）

```
class-review-system/
├── app.py / run.py          # 应用工厂 + 启动入口
├── src/
│   ├── models/              # 数据模型（User/Klass/Student/Lesson/Review/...）
│   ├── main/ auth/ classes/ lessons/ reviews/ students/ cards/ reports/ admin/   # 蓝图
│   ├── ai/                  # 课评生成链路（prompt / guard / normalize / redact / scorer）
│   ├── parsers/             # 课件文本解析
│   ├── security/            # 上传校验 + 登录限流
│   └── services/            # 去重 / 学期总结
├── templates/ static/       # 前端
├── uploads/ instance/       # 上传文件 / SQLite 库（不入库）
├── seeds/ migrations/       # 学科预置 / 数据库迁移
├── tools/ reports/ docs/    # 脚本 / 报告 / 样例
├── .env .env.example        # 环境变量（密钥不入库）
├── requirements.txt Dockerfile docker-compose.yml
├── DEPLOY.md CLAUDE.md      # 部署文档 / 架构索引（开发者）
└── README.md
```

---

## 快速开始（本地开发）

```bash
# 1. 准备 Python venv（推荐项目自带 .venv）
.venv/Scripts/python.exe -m pip install -r requirements.txt

# 2. 配置环境变量
cp .env.example .env
# 至少填入 AI_API_KEY；SECRET_KEY / ADMIN_PASSWORD 留空则本地随机（仅开发）

# 3. 建库 + 预置学科
flask db upgrade
flask seed

# 4. 启动
python run.py          # 访问 http://127.0.0.1:5000
```

> 未配置 SMTP 时，邮件类功能进入 dev 模式（控制台打印链接，不真发信）。

---

## 使用流程（老师视角）

1. **注册 / 登录**：邮箱注册并验证。
2. **建班级**：选择学科类型（coding/art/dance/...），填班级名与时间。
3. **加学生**：录入姓名与昵称（课评里点名用昵称）。
4. **建课次 + 上传课件**：上传 `pptx/docx/pdf/txt`，系统抽取知识点与目标。
5. **生成课评**：进入编辑器点「生成」，AI 给出两段式草稿（段①知识点 / 段②评价）。
6. **编辑 / 设优秀范例**：修改要点；满意的课评可一键设为本班「优秀范例」，下次全班参考。
7. **确认发布**：状态转「已确认」。
8. **导出 / 分享**：Excel / PDF / 卡片图片 / 家长提醒。

---

## 配置说明（`.env`）

| 变量 | 说明 | 默认 |
|---|---|---|
| `AI_API_KEY` | AI 模型 Key（必填） | 无 |
| `AI_BASE_URL` | OpenAI 兼容接口地址 | `https://open.bigmodel.cn/api/paas/v4` |
| `AI_MODEL` | 模型名 | `glm-4-flash` |
| `SECRET_KEY` | 会话签名密钥；生产必须固定随机串 | 留空则本地随机（重启失效） |
| `ADMIN_EMAIL` / `ADMIN_PASSWORD` | 平台超管凭据 | 留空则随机密码（打日志） |
| `MAIL_*` | SMTP 发信（可选） | 空则 dev 模式 |
| `DATABASE_URL` | 数据库地址 | `sqlite:///instance/app.db` |
| `PORT` / `HOST` | 监听地址 | 5000 / 127.0.0.1 |

---

## 安全说明

**已实现**：CSRF 全局开启（reviews 纯 API 豁免）、密码 bcrypt 哈希、登录失败限流、上传文件扩展名 + **文件头魔数**双校验、解析文本长度上限（防炸弹）、上传目录不对外托管、多租户数据隔离、`.env` 不入库。

**上线前仍建议**（详见 `DEPLOY.md`）：换 waitress/gunicorn + Nginx HTTPS、固定 `SECRET_KEY` 与 `ADMIN_PASSWORD` 环境变量、数据库定期备份、多实例时限流换 Redis。

---

## 部署

见 [`DEPLOY.md`](DEPLOY.md)：本地运行、Docker 部署、生产检查清单。

## 开发者

架构与代码索引见 [`CLAUDE.md`](CLAUDE.md)。

## 许可证

MIT License
