# Ekko · 教培机构 AI 教学工作台

一个已经在生产环境跑起来的多租户 Web 系统（线上地址 `ekkosys.cn`），服务少儿培训机构的真实业务场景：老师管理「班级 → 学生 → 课次」，上传课件后由 AI 生成结构化的课后评价与课前教案/课件，经老师编辑确认后导出或分享给家长。

这不是 Demo，是从零设计、开发、部署并持续迭代的完整产品。下文的每个设计决策都来自真实用户反馈和线上排查记录。

---

## 这个项目解决什么问题

培训机构老师的重复劳动集中在两块：**课前**要逐课写教案做课件，**课后**要给每个学生写课评发给家长。一个带 8 个学生的老师，课后光写课评就要一个多小时。

系统把这两块流程化：老师只负责录入事实（今天讲了什么、学生表现标签），AI 负责把事实组织成结构化、风格统一的文字。老师始终保有最终编辑权——**AI 出草稿，人做判断**。

## 关键工程设计

### 生产级 LLM 管线，而非一次 API 调用

课评质量直接面对家长，不能容忍模型胡说。生成链路是「prompt 构造 → 生成 → 确定性校验 → 兜底修复 → 质量打分」的完整管线（`src/ai/`）：

- **输出护栏（`output_guard.py`）**：上线后全量走查发现弱模型 30/30 份课评叫错学生名字、40% 出现「亲爱的家长」群发开头。仅靠 prompt 软约束压不住，于是在生成后加了一道确定性门禁——正则+规则检出硬伤（叫错名/群发开头/缺段落/占位符泄漏），能确定性修复的直接修，修不好的如实标记给老师，**绝不静默放行**。
- **PII 脱敏（`redact.py`）**：发往 LLM 前把同班其他同学姓名替换为占位符，返回后还原；few-shot 范例同样脱敏，防止模型套用样本里的真实姓名。当前学生昵称按需明文——这是写本人课评的必要信息，属风险最小化的权衡。
- **多 KEY 轮询与成本兜底（`llm_client.py`）**：OpenAI 兼容客户端支持多 KEY 轮询，单 KEY 限流/失败自动切换；老师可在账号页填自己的 KEY 覆盖平台默认，代理策略显式可控（默认直连，避免开发机代理环境污染线上行为）。

### 业务建模与状态机

课评不是一段文本，而是一个有生命周期的实体：`pending → generating → draft → confirmed / leave / failed`。请假学生直接落库「请假」不调用 AI；同班同课次去重；满意的历史课评可一键设为本班「优秀范例」作为下次生成的 few-shot 锚点——业务规则沉淀在模型与服务层（`src/models/`、`src/services/`），而不是散落在视图里。

### 数据集成与文档解析管线

老师上传的课件格式混杂（`txt/pptx/docx/pdf`），系统统一走「格式校验 → 文本抽取 → 清洗 → 结构化」管线（`src/parsers/`），喂给下游 AI 与知识库检索。安全上做了两层防护（`src/security/upload_check.py`）：扩展名白名单之外加**文件头魔数校验**防改名绕过，对抽取文本设上限防 zip 解析炸弹；上传目录不对外托管，从路径上消除存储型 XSS。

### 知识库检索：从模糊打分到精确锚定

课前备课按「学科 + 年级 + 课题」从 975 篇教材课文知识库检索原文。初版用模糊打分（topic 互含 +100 / subject +10 / grade +5），线上实测出现五年级课题错配三年级课文的「张冠李戴」。改为**精确锚定**（学科一致 + 年级段归一化一致 + 课题精确/包含兜底，见 `systems/lesson-courseware/courseware_engine/kb.py` 的 `_grade_core`），并删掉了一条会把好结果重切页覆盖掉的渲染旁路——这个 bug 是用户拿真实课件反馈「页面重复、内容不对」后定位到的。

### 安全与多租户

CSRF 全局开启（纯 API 豁免）、密码 bcrypt 哈希、登录滑动窗口限流（`src/security/ratelimit.py`，仅计失败、成功即清零，正常用户永不被误伤）、按用户隔离数据查询、密钥全部走环境变量不入库。限流目前是单实例内存实现——代码里明确标注了多实例时需换 Redis，这是刻意的部署形态权衡。

---

## 技术栈

- **后端**：Python 3.11+ · Flask 3.x · Jinja2 · SQLAlchemy 2.x · Flask-Migrate
- **数据库**：SQLite（WAL）起步，schema 用 Alembic 迁移管理，可随时切 PostgreSQL
- **AI**：OpenAI 兼容接口（默认智谱 GLM-4-Flash，可换任意兼容端点/本地 vLLM）
- **文档解析 / 导出**：pdfplumber · python-pptx · python-docx · openpyxl · reportlab · Pillow
- **前端**：服务端渲染 + html2canvas 导出家长分享卡片（10 套可选模板，全字面色兼容截图渲染）
- **部署**：Docker Compose 单机部署 + Nginx + HTTPS，阿里云生产环境

---

## 目录结构（精简）

```
class-review-system/
├── app.py / run.py          # 应用工厂 + 启动入口
├── src/
│   ├── models/              # User / Klass / Student / Lesson / Review / PrepJob
│   ├── main/ auth/ classes/ lessons/ reviews/ students/ cards/ reports/ admin/  # 蓝图（77 个路由）
│   ├── ai/                  # LLM 管线：prompt / guard / redact / scorer / 标签分类 / 多 KEY 客户端
│   ├── parsers/             # 课件文档解析
│   ├── security/            # 上传魔数校验 + 登录限流
│   └── services/            # 去重 / 学期阶段总结
├── systems/lesson-courseware/   # 课前备课子系统（KB 检索 + 课件渲染引擎）
├── templates/ static/       # 前端
├── migrations/ seeds/       # schema 迁移 / 学科预置数据
├── docs/ reports/           # 设计文档 / 全量走查报告
├── .env.example             # 环境变量模板（密钥不入库）
├── Dockerfile docker-compose.yml
├── DEPLOY.md CHANGELOG.md CLAUDE.md
└── README.md
```

---

## 快速开始（本地开发）

```bash
# 1. 依赖
python -m venv .venv && .venv/Scripts/python.exe -m pip install -r requirements.txt

# 2. 环境变量
cp .env.example .env    # 至少填 AI_API_KEY

# 3. 建库 + 预置学科数据
flask db upgrade && flask seed

# 4. 启动
python run.py           # http://127.0.0.1:5000
```

> 未配置 SMTP 时邮件功能进入 dev 模式（链接打印到控制台，不真发信）。

## 部署

见 [`DEPLOY.md`](DEPLOY.md)：Docker 部署、生产检查清单（固定 `SECRET_KEY`、HTTPS、数据库备份、多实例时限流换 Redis）。完整变更历史见 [`CHANGELOG.md`](CHANGELOG.md)，架构索引见 [`CLAUDE.md`](CLAUDE.md)。

## 许可证

MIT License
