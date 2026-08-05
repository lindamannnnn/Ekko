# 课评自动生成系统 — 项目结构索引（CLAUDE.md）

> 本文档是给 AI 协作者 / 开发者看的**真实架构索引**。任何涉及代码改动、加功能、做诊断前先读它。
> 旧版文档（截至 2026-05 的 OJ/Kimi/Kitten 文件目录架构）已完全废弃，本文件为准。

---

## 1. 项目概览

**通用少儿培训机构课评系统**：多租户（按 `user_id` 隔离）的 Web 应用，帮助机构老师在教务系统中为每个学生每节课自动生成课后评价。

- 老师建立「班级 → 学生 → 课次」，上传课件（txt/pptx/docx/pdf）；
- 后端用 AI 模型（默认智谱 **GLM-4-Flash**，OpenAI 兼容接口）结合「课件知识点 + 学生基本信息 + 本班优秀课评范例」生成草稿；
- 课评经老师编辑、确认后，可导出 Excel/PDF、生成家长群分享卡片、发送提醒。
- 支持多学段/多学科（coding/art/dance/sports/calligraphy/english/tutoring 等由 `class_type_presets` 预置）。

**核心约束（贯穿全项目）**：课评必须是**严格两段式**——
- 段①【课堂内容总结】= 纯本节课知识点，**直接以「1.」开头的编号列表**，禁止称呼/评价/引导语；
- 段②【课后评价】= 写给家长/孩子的评价，**首句必须点名学生昵称**，严禁在中间再夹一整段知识点。
- 该结构由 prompt 铁律 + 后端确定性兜底（`output_guard` / `review_normalize`）双重保证，因为弱模型对长 prompt 多约束依从度低。

---

## 2. 技术栈

| 层 | 选型 |
|---|---|
| 后端 | Python 3.11+ ，Flask 3.x + Jinja2 |
| 数据库 | SQLite（WAL 模式），SQLAlchemy 2.x + Flask-Migrate（alembic，render_as_batch=True） |
| 鉴权 | Flask-Login（会话） + bcrypt 密码哈希 + Flask-WTF（CSRF，全局开启） |
| AI 调用 | requests → OpenAI 兼容接口（`AI_BASE_URL` / `AI_MODEL` / `AI_API_KEY`），默认智谱 GLM-4-Flash |
| 课件解析 | pdfplumber / python-pptx / python-docx |
| 导出 | openpyxl（Excel）、reportlab（PDF）、Pillow（卡片图片） |
| 配置 | python-dotenv（`.env`）+ 可选 `app_config.py` 覆盖 |
| 部署 | 开发：Flask dev server；生产：Docker（见 DEPLOY.md，建议换 waitress/gunicorn + Nginx） |

---

## 3. 目录结构（真实）

```
class-review-system/
├── app.py                      # 应用工厂 create_app()：扩展初始化、配置、蓝图注册、SECRET_KEY/CSRF、管理员种子、health
├── run.py                      # 启动入口（调 create_app，可选 app_config.py 覆盖，TEMPLATES_AUTO_RELOAD）
├── extensions.py               # db / migrate / login_manager 等扩展单例
├── seeds/                     # load_class_type_presets() — 学科/机构类型预置
├── migrations/                # Flask-Migrate 迁移脚本（render_as_batch=True，兼容 SQLite 改列）
├── src/
│   ├── models/                # 数据模型（见 §5）
│   │   ├── user.py            # User / ApiCredential / DailyUsage / GenerationLog
│   │   ├── class_student.py   # Klass / Student / Enrollment
│   │   ├── lesson.py          # Lesson / Courseware / Review / TermSummary / StyleSample
│   │   ├── class_type_preset.py
│   │   └── base.py            # UUIDMixin / TenantMixin / SoftDeleteMixin 等基类
│   ├── main/                  # 蓝图 main_bp：首页 /
│   ├── auth/                  # 蓝图 auth_bp (url_prefix /auth)：注册/登录/邮箱验证/找回密码；providers.py 密码哈希；decorators.py admin_required
│   ├── classes/               # 蓝图 classes_bp (/classes)：班级 CRUD、学生、上传课件、优秀课评范例
│   ├── lessons/               # 蓝图 lessons_bp (/lessons)：课次详情、课件关联
│   ├── reviews/               # 蓝图 reviews_bp (/reviews)：课评编辑器、生成/保存/确认/请假/删除/历史；**整体豁免 CSRF**
│   ├── students/              # 蓝图 students_bp (/students)：学生详情、期末总结
│   ├── cards/                 # 蓝图 card_bp (/cards)：课评分享卡片预览
│   ├── reports/               # 蓝图 reports_bp (/reports)：导出 xlsx/pdf、家长提醒
│   ├── admin/                 # 蓝图 admin_bp (/admin)：平台总后台（仅超管），用户/班级/课件/课评管理
│   ├── ai/                    # AI 课评生成链路（见 §6）
│   ├── parsers/               # 课件文本解析（core.py：extract_text / extract_objectives）
│   ├── security/              # 安全加固（见 §7）
│   ├── services/              # dedup.py（去重）/ summary_builder.py（学期总结）
│   └── utils/                 # 工具（init_data 等）
├── templates/                 # 33 个 Jinja2 模板（base.html + 各蓝图页面）
├── static/                    # CSS/JS/图片
├── uploads/                   # 上传课件落盘目录（**不对外静态托管**，仅后端解析用）
├── instance/app.db            # SQLite 数据库（WAL）
├── tools/                     # 验证/调试/一次性脚本（test_guard.py 等）；多数带 _ 前缀为临时调试
├── reports/                   # 项目级报告输出（体检/安全加固/等）
├── docs/                      # 课评样例、模板迭代成果
├── .env / .env.example        # 环境变量（密钥不入库）
├── requirements.txt
├── Dockerfile / docker-compose.yml
├── DEPLOY.md / README.md / CLAUDE.md
└── CHANGELOG.md / CONTRIBUTING.md / LICENSE
```

> ⚠️ **蓝图名 ≠ 目录名**：`main_bp` 在 `main/`，`auth_bp` 在 `auth/`，`classes_bp` 在 `classes/`，`lessons_bp` 在 `lessons/`，`reviews_bp` 在 `reviews/`，`students_bp` 在 `students/`，`card_bp` 在 `cards/`，`reports_bp` 在 `reports/`，`admin_bp` 在 `admin/`。导入时用对应蓝图实例名。

---

## 4. 应用工厂与全局配置（app.py）

`create_app()` 关键行为：
- `load_dotenv()` 载入 `.env`；把 `src/` 加入 sys.path。
- **SECRET_KEY**：优先 `os.environ['SECRET_KEY']`，未设置则 `secrets.token_hex(32)` 本地随机并打告警（仅适合本地，重启即失效）。
- **WTF_CSRF_ENABLED = True**（全局开启）。`reviews_bp` 为纯 JSON API，已在工厂里 `csrf.exempt(reviews_bp)`；其鉴权由 `@login_required` 保证。
- SQLite 连接：`connect_args={"timeout":15}`；WAL + busy_timeout=15s + foreign_keys=ON（`_configure_sqlite_pragmas`）。
- 所有 HTML 响应加 `no-store` 头，避免浏览器缓存旧模板。
- 启动时 `db.create_all()`，幂等载入 `class_type_presets`，补 `users.is_superuser` 列、`coursewares.created_at/uploaded_by` 列；按 `ADMIN_EMAIL` / `ADMIN_PASSWORD` 种超管（缺省随机密码并打日志）。
- 提供 `/health` 与 `flask seed` CLI。

---

## 5. 数据模型（src/models）

| 模型 | 表 | 说明 |
|---|---|---|
| `User` | users | 租户根；邮箱/密码哈希/邮箱验证/`is_superuser`；含 `ApiCredential`、`DailyUsage`、`GenerationLog` |
| `ApiCredential` | api_credentials | 用户自带 Token（Fernet 加解密） |
| `DailyUsage` | daily_usage | 每日 AI 调用量（限流/计费） |
| `GenerationLog` | generation_logs | 生成日志 |
| `Klass` | classes | 班级（TenantMixin + SoftDelete）；含 `type_code`（学科）、`type_name_custom`、时间 |
| `Student` | students | 学生（含 `name` / `preferred_name` 昵称 / 基本信息字段） |
| `Enrollment` | enrollments | 班级-学生关联 |
| `Lesson` | lessons | 课次（关联班级、课件、知识点、目标） |
| `Courseware` | coursewares | 上传课件（路径、解析文本、提取目标、`created_at`/`uploaded_by`） |
| `Review` | reviews | 课评（content、status: pending/draft/confirmed/leave/failed、ai_raw、redacted 等） |
| `TermSummary` | term_summaries | 学期/阶段总结 |
| `StyleSample` | style_samples | 教师课评风格样本 |
| `ClassTypePreset` | class_type_presets | 学科/机构类型预置（含 AI 生成要点、结构骨架） |

多租户通过 `TenantMixin` 注入 `user_id` 并在查询层强制过滤；软删除走 `SoftDeleteMixin`。

---

## 6. AI 课评生成链路（src/ai/）

```
lessons/classes 上传课件 → parsers.core.extract_text → 存 Courseware
        ↓
reviews 蓝图 _generate_for(review)
        ↓
prompt_builder.build_messages(review)   # 三段式指令 + 学科模板 + 优秀范例 + 两段式铁律
        ↓
llm_client / channel  →  GLM-4-Flash（OpenAI 兼容）
        ↓
output_guard.check_output / patch_output   # 校验+确定性兜底修正（防误判/补称呼）
        ↓
review_normalize.normalize_paragraphs / cap_length  # 强制两段式 + 字数上限（保头保尾）
        ↓
redact.Redactor  # 真实姓名/昵称脱敏（按学生 preferred_name 规则）
        ↓
落库 Review.content（2 段 + 1 空行）
```

- **prompt_builder.py**：`BASE_RULES`（R1–R12 铁律，含 R3 段①纯编号、R8 段②首句点名、R11 两段独立）、`subject_block`（学科要点）、`SUBJECT_OPENING`（段②首句范式）、`open_req`/`fmt_req`（段落职责硬要求）。学科模板在 `src/ai/subject_templates/*.md`。
- **llm_client.py / channel.py**：HTTP 调用封装，超时/重试。
- **output_guard.py**：`_has_numbered_summary()`（首段≥2 编号项即通过，避免裸编号列表被误判 missing_summary 触发重生成死循环）；补称呼只在**段②**内，绝不污染段①。
- **review_normalize.py**：`normalize_paragraphs`（单段兜底切分，覆盖「末项无终止标点+评价另起一行」形态）、`cap_length`（段② 保头保尾、中间删句，不切掉家庭建议+emoji）。
- **redact.py**：按学生 `preferred_name` 规则脱敏。
- **review_library.py**：读取本班优秀课评范例注入 prompt。
- **review_scorer.py**：课评质量评分（供编辑器徽章用）。
- **skill_creator.py**：用户/学生画像创建。

---

## 7. 安全模块（src/security/）

- **upload_check.py**：`validate_upload()` = 扩展名白名单 + **文件头魔数校验**（拦截 `evil.exe` 改名 `evil.pdf`）+ 大小≤10MB；`check_extracted_text()` = 解析文本 ≤1.5MB（防解析炸弹）。
  - 接入点：`classes/routes.py upload_course`、`lessons/routes.py _save_courseware`。
  - 重要前提：`uploads/` **不对外静态托管**，`send_file` 只用于内存生成的导出，已无「上传 html 触发 XSS」路径。
- **ratelimit.py**：内存级 IP 滑动窗口（60s ≤10 次）。接入 `auth.login` 与 `admin.login`。多实例部署需换 Redis。

---

## 8. 常用命令

```bash
# 安装依赖（用项目 venv）
.venv/Scripts/python.exe -m pip install -r requirements.txt

# 数据库
flask db upgrade          # 应用迁移建表
flask db migrate -m "..." # 生成迁移（改模型后）
flask seed                # 载入学科/机构类型预置

# 启动（开发）
python run.py             # http://127.0.0.1:5000
# 或
.venv/Scripts/python.exe app.py

# 关键验证脚本
.venv/Scripts/python.exe tools/test_guard.py   # output_guard 回归（含两段式结构校验）
# 全页面冒烟 + 匿名鉴权 + CSRF 验证：见 reports/ 下历史脚本或临时 _smoke.py
```

---

## 9. 开发约定与踩坑（重要）

1. **改任意 `.py` 必须 kill + 重启**（`debug=False`，无自动重载）。端口 5000；查进程 `netstat -ano | grep :5000`。
2. **SQLite 并发纪律**：WAL + busy_timeout；写事务保持极短，**绝不在事务/`@app.route` 同步路径里调 LLM**（会阻塞 + 锁库）。
3. **两段式课评结构是硬约束**：任何「改 prompt / 改模板 / 改 normalize」都要保证段①纯编号、段②首句点名，且不夹知识点。改完跑 `tools/test_guard.py` + 真实生成 5 轮。
4. **单段兜底切分**（`review_normalize._split_single_para_into_two`）必须覆盖「编号块末项无句号 + 评价另起一行」的高频形态，否则间歇产出单段融合、难复现。
5. **弱模型 + 长 prompt 多约束 → 必须在后端用确定性规则兜底**（output_guard / review_normalize），不要全靠 prompt 约束。
6. **CSRF**：`reviews` 蓝图已整体豁免；其他蓝图表单/前端 fetch 受保护。前端 `base.html`/`admin/base.html` 用 `<meta name="csrf-token">` + 全局 fetch 钩子自动带 `X-CSRFToken`。新增非 reviews 的 POST 接口若被 400，先确认是否要补 token 或豁免。
7. **多租户**：所有查询必须带 `user_id` 过滤（TenantMixin），禁止跨租户读取。
8. **`.env` 不入库**（已 gitignore）；密钥经环境变量注入生产。
9. **生产安全已加固但仍有待办**：CSRF 已开、SECRET_KEY 已走环境变量、管理员随机密码、登录限流、上传魔数校验。仍建议换 waitress/gunicorn + HTTPS、数据库备份、限流换 Redis（见 DEPLOY.md）。
10. **旧系统代码**（`data/`、`references/`、`rules/`、`skills/`、`output/` 下旧架构产物、`CLAUDE.md` 2026-05 之前版本）已废弃，勿再依赖。

---

## 10. 相关文档

- **README.md**：面向用户/老师的快速上手与功能说明。
- **DEPLOY.md**：本地运行 + Docker + 生产检查清单。
- **reports/**：历次体检、安全加固、课评结构改造的完整记录。
