# 项目交接文档

> 本文档用于将项目交接给新的 AI 助手。阅读本文档前，**必须先理解一个核心前提**：本项目包含**两套完全独立的系统**，代码、数据、部署环境互不耦合，绝不可混淆。
>
> 更新日期：2026-08-15

---

## 〇、文档索引（接手先读这里）

本仓库交接文档共三份，分工如下：

| 文档 | 内容 | 接手时的阅读顺序 |
|------|------|------------------|
| **`LAUNCH_PREP.md`** | **上线前准备清单**：P0/P1/P2 任务、当前状态核实表、红线、已知边界、前 30 分钟上手顺序 | **① 先读**（如果任务是做上线准备） |
| **`HANDOVER.md`**（本文件） | 两套系统全局、系统 A/B 详情、文件地图、历史修复、运行速查、红线、QA | ② 读第 1、3 节 |
| **`TECH_DESIGN.md`** | 生成式技术路径的架构与经验（原料 vs 成品、三科专家 agent、免费做到顶+升级路径） | ③ 改引擎前必读 |

> 如果下一位 AI 的任务是「**上线之前做准备**」，直接以 `LAUNCH_PREP.md` 为主入口，本文件和 `TECH_DESIGN.md` 作背景补充。

---

## 一、项目总览

| 系统 | 名称 | 状态 | 代码目录 | 部署状态 |
|------|------|------|----------|----------|
| **系统 A** | Ekko 课评系统 | **已上线，生产运行中** | `E:/001/class-review-system/` | 已部署 |
| **系统 B** | 教案→课件系统 | **开发中，未上线** | `E:/001/lesson-courseware/` | 未部署 |

**红线**：系统 A 是已完成的生产系统，任何改动（尤其 web 代码、部署配置）必须先征得用户同意，绝不要擅自修改或重建部署。系统 B 是当前开发对象，所有新增开发和改动都在此目录下。

---

## 二、系统 A：Ekko 课评系统（已完成，生产环境）

### 2.1 基本信息
- **服务器**：`101.133.139.175`（Ubuntu 24.04）
- **容器名**：`ekko-web`
- **对外域名**：`ekkosys.cn`（含 `www.ekkosys.cn`）
- **HTTPS**：certbot + Let's Encrypt，已配置自动续期
- **部署方式**：`scp` 传文件 + `docker compose up -d --build`（static/templates 烘焙进镜像）
- **SSH Key**：`C:/Users/kass/.ssh/id_ed25519_ekko`

### 2.2 核心功能
- 教师注册/登录（Flask-Login + SMTP 邮箱验证）
- 班级管理（CRUD，多租户隔离）
- AI 课评生成（基于学生表现数据，GLM-4-Flash 模型）
- 课评卡片导出（html2canvas 生成图片，4 套学科模板）
- 后台管理（账号/班级/AI 用量看板）

### 2.3 关键文件
| 文件 | 说明 |
|------|------|
| `app.py` | Flask 主应用（含所有蓝图） |
| `src/models.py` | SQLAlchemy ORM + Alembic 迁移 |
| `src/repositories/` | 数据访问层（多租户隔离） |
| `src/prompts/` | 各学科课评生成 prompt 模板 |
| `templates/cards/` | 课评卡片 HTML 模板（4 套：academic/work/skill/general） |
| `src/web/` | 已被删除的孤儿模块（确认不存在） |
| `_gen_plans.py` / `_lessonplan_test.py` | **早期手搓脚本，属于课评系统的历史遗留，与系统 B 无关** |

### 2.4 术语约定
- 用户口中的「**大厅**」= **班级列表页** `/classes`，不是欢迎首页。

### 2.5 修改红线
- **不要**修改课评系统的 web 代码（`app.py`、模板、`prompts` 等），除非用户明确说"改这个"。
- **不要**重建部署，除非用户说"现在部署"。
- 正确节奏：本地改 → 本地预览 → 攒够一批 → 用户说"可以部署了" → 一次性 `scp` + `docker compose up -d --build`。

---

## 三、系统 B：教案→课件系统（开发中）

### 3.1 目标链路
用户填表单（学科/年级/课题） → **K12 SKILL 生成教案** → Adapter 转换 → **v3 引擎生成课件**（确定性 + 免费模型 + 自审闭环）→ **Render 渲染 HTML 课件** → 教师可直接上课使用。

核心原则：
- **教案只是输入，课件是产品**。目标不是做全能老师，而是"有教案后，用教案内容做成一份直接能上课的课件"。
- **内容只做骨架**（知识点/例题步骤/分层练习答案/错解对比/图示），不生成老师口头讲解稿、板书设计、时间分配、学情分析等。
- **两条生成路径（按模型自动切换）**：
  - 弱模型路径（默认 GLM-4-Flash）：KB 是内容作者，确定性引擎 auto_kb 生成页面骨架，弱模型只填空隙。生产路径：KB → auto_kb → teach_expand → content_fill → validate → render。
  - 强模型路径（用户传强模型 API）：教师 AGENT（strong_gen.py）一次调用输出教学语义 LessonContent，程序确定性映射成页面。生产路径：KB → generate_content → content_to_segments → content_fill → validate → render。
- **唯一引擎 v3**。旧 v2 多智能体引擎与 v1 vendor 单模板引擎已于 2026-08-15 删除。
- **升级 API 路径**：网页表单「模型配置」可填 `AI_BASE_URL`/`AI_MODEL`/`AI_API_KEY`，覆盖 `.env` 免费配置，换更强模型不改页面结构。

### 3.2 已完成模块

#### 3.2.1 知识库（KB）
- **目录**：`E:/001/lesson-courseware/vendor/kb/<学科>/`
- **数学**：98 条（2024 修订版，知识点级）
- **语文**：359 条（2024 修订版，课文级，部编版一至六年级上下册）
- **英语**：70 条（PEP 三~六年级，单元/语法级）
- **总计**：527 条 JSON，515 条有效（剔除 bundle TOC 文件）
- **检索函数**：`courseware_engine/kb.py` 的 `retrieve_kb(subject, grade, topic)`
- ** grounding 机制**：教案端与课件端**共用同一份 KB**，按 `subject+grade+topic` 命中课题级原文，生成时注入原文约束（"定义/例题/公式须与原文一致，不得引入原文未涵盖算法"）。

#### 3.2.2 课件生成引擎（courseware_engine/）
| 模块 | 文件 | 职责 |
|------|------|------|
| KB 适配器 | `kb_adapter.py` | `auto_kb(kb)`：将任意 KB 自动映射为课件 segments（确定性，零 LLM）。按学科/课型分派：`_gen_math` / `_gen_chinese_prose` / `_gen_chinese_poem_or_recog` / `_gen_english` |
| 内容填充器 | `content.py` | `content_fill()`：将 segments 填充到版式 slots，生成完整 deck |
| 校验闸门 | `validator.py` | `validate_deck()`：引号平衡、零页检测、内容完整性校验 |
| KB 编写期校验 | `kb_validator.py` | `validate_kb()`：KB 入库前的结构化校验 |
| 渲染器 | `render.py` | `render_html()` / `build_deck()`：将 deck 渲染为单文件 HTML |
| 版式库 | `layouts/` | 每个版式 = `LayoutDef`，自包含 CSS，根节点 `class="ly ly-<id>"` |
| 主题/样式 | `style.py` / `themes.py` | 多主题视觉系统 |
| LLM 工具 | `llm.py` | OpenAI 兼容 LLMClient（含代理支持） |
| 文本工具 | `textutil.py` / `util.py` | `_clip`、`_first_clause`、`_paragraphs`、`extract_json` 等共享工具 |
| KB 检索 | `kb.py` | `retrieve_kb(form)`：按 subject+grade+topic 检索教材原文 |
| 免费模型层 | `enrich_llm.py` | `enrich_chinese()`：古诗译文/意境赏析/作者背景（LLM，须在 auto_kb 之前调用） |
| 教学专家协议 | `teach_expand.py` | 三科「教学展开」固定协议：数学算理/语文品析/英语呈现·操练·应用 |
| 教育专家 agent | `experts.py` | 三科 `guide`（生成指导）+ `check`（确定性门禁）+ `review_prompt`（LLM 审核） |
| 审核层 | `reviewer.py` | `review`（确定性）/ `llm_review`（LLM）/ `expand_with_review`（生成→审核→打回闭环） |
| 强模型独立链路 | `strong_gen.py` | 教师 AGENT 一次调用输出「教学语义」`LessonContent`（目标/导入/概念/例题/分层练习/作业/小结/板书/示意图），`content_to_segments` 确定性映射成页面；三科协议 + 结构漂移归一化兜底 |
| 语义契约 | `schemas.py` 的 `LessonContent` | 教师 AGENT 输出的教学语义 schema（键名固定：objectives/lead_in/concepts/examples/diagrams/practice/summary/board/homework） |

#### 3.2.3 核心版式（layouts/）
- `cover` — 封面
- `objectives` — 学习目标
- `lead_in` — 情境导入
- `concept` — 概念页（含 `vertical_poem` 竖排诗版）
- `poem_thinking` — 诗词笺注赏析（阕+主旨+重点词句+修辞）
- `word_grid` — 字词卡网格
- `tiers` — 分层练习/作业
- `split` — 左右分栏
- `board` — 板书结构
- `summary` — 课堂小结
- `diagram` — SVG 示意图（分数条/数轴/条形图/方格图/数位表，数学配图用）

#### 3.2.4 教案生成（k12_generate.py）
- **正式来源**：基于 `k12-lesson-planning` SKILL 的课标 references + `lesson.json` schema，脚本化固化为 `k12_generate.py` 的 `generate_lesson(form, client)`。
- **早期 stopgap**（`_gen_plans.py` / `plan_gen.py`）已于 2026-08-12 **删除**，正式链路不再有手搓脚本。
- **Adapter**：`orchestrator.py`（或独立 adapter 模块）负责将 K12 产出的 `lesson.json` 映射为 `courseware_gen` 所需的 `form["plan"]` 结构。

#### 3.2.5 稳定性验证
- **全量压测脚本**：`tools/stress_all.py`
- **当前结果**（2026-08-15，#426 修复后）：
  - `TOTAL: 515`
  - `CRASH: 0`
  - `KB_BLOCK: 0`
  - `ZERO_PAGE: 0`
  - `RAW_IMB: 0`
  - `OUT_IMB: 0`
  - `ADAPT_IMB: 0`
  - `SINGLE_ELL: 227`（良性，教材原文中的单省略号）
- **目标**：以上指标必须全为 0（SINGLE_ELL 除外）。

#### 3.2.6 已修复的发布阻断项（#420 ~ #426）
| # | 问题 | 状态 |
|---|------|------|
| #420 | poem_thinking slots 缺失导致 KB_BLOCK=47 | ✅ 已修复（陈旧产物误报） |
| #421 | 数学空壳例题 + 开发者备注泄露 | ✅ 已修复（`auto_kb` 入口全局剥离 dev-note + 重写 `_formula_example`） |
| #422 | 语文引号内截断题干（`_pick_detail` 正则缺陷） | ✅ 已修复（仅接受右边界完整词） |
| #423 | 英语半词截断（CSS `overflow:hidden`） | ✅ 已修复（全局 `overflow-wrap:break-word; word-break:break-word`） |
| #424 | 答非所问（情感题答成结构） | ✅ 已修复（`_kp_match` 语义对齐） |
| #425 | 胡萝卜先生的长胡子 册次错标 | ✅ 核查无误（2024 修订版确为三下，用户记忆为旧版） |
| #426 | 诗词内容重复（poem_thinking vs 板书/练习/小结复用同 key_points） | ✅ 已修复（board→骨架短标签、summary→固定收获清单、practice→换 framing） |

### 3.3 待完成 / 阻塞项

#### P0 — 阻塞上线
1. **教师-AGENT 盲评**（已做三轮，结论见 TECH_DESIGN.md）
   - 随机采样 KB 跑完整链路，用 Agent 模拟教师盲评。
   - 三轮结论：多数课「需大改/不可用」，唯一「接近可上」是数学《图形的面积》。
   - 根本结论：弱模型产不出真算理/品析深度（能力天花板，非流程 bug）；确定性门禁只能消除"可程序化硬伤"，语义层靠升级模型（`AI_MODEL`）或人工补。
   - **状态**：已按用户决策「免费模型做到顶 + 留升级 API 路径」落地，不再无限重试。

2. **网页表单串联**
   - `app.py` 表单 → K12 教案 → adapter → v3 引擎 → render 端到端已打通（`orchestrator.run` 返回 review 字段，前端按 `blocked` 显示门禁横幅）。
   - 默认引擎已切 v3，模型配置（base_url/model/api_key）已暴露到表单。
   - **状态**：✅ 已打通，可本地 `python app.py` 预览。

#### P1 — 重要改进
3. **诗词词语卡（word_grid）质量**
   - 当前 `_poem_word_cards` 对 47 个诗词/词 KB 产出垃圾卡片（把"重点词句"当词、把分析句当词）。
   - 由于质量差，当前代码**不展示**诗词的词卡（只展示 poem_thinking）。
   - 如需让诗词课件也有词语卡，需重写 `_poem_word_cards` 以正确解析 `重点词句：词（释）、词（释）` 格式。

4. **K12 SKILL Agent 驱动 vs 脚本化**
   - 当前 `k12_generate.py` 是脚本化实现（基于 K12 的课标 references + prompt）。
   - 原 SKILL 是 agent 指令型（SKILL.md 定义 Step0-6 流程），理论上应由 agent 驱动产出 `lesson.json`。
   - 需评估：脚本化是否足够稳定，还是必须切回 agent 驱动？

5. **eval_report 撰写**
   - 每轮修复后应撰写 `eval_report_vN.md`，记录：修复内容、压测结果、AGENT 评测结论、上线判定。
   - 当前最新是 v6 或 v7，v8 尚未撰写（#426 修复后待补）。

#### P2 — 优化项
6. **词（ci）竖排版式**
   - 已完成 overhaul（竖排诗版 + 笺注赏析），但 AGENT 盲评中需确认教师是否认为"美观"。

7. **更多学科/年级覆盖**
   - 当前仅覆盖小学语/数/英三科。中学、高中、其他学科未开始。

### 3.4 关键文件地图

```
E:/001/lesson-courseware/
├── app.py                        # Flask web 应用（表单 + 模型配置 + 阻断横幅）
├── orchestrator.py               # 编排器：K12教案 → adapter → v3引擎 → review → render
├── k12_generate.py               # 脚本化教案生成器（基于 K12 SKILL 课标 references）
├── k12_adapter.py                # lesson.json → 课件 form["plan"]
├── tools/
│   ├── stress_all.py             # 515 KB 全量稳定性压测（开发工具）
│   ├── gen_lesson.py             # 单课跑完整链路（开发工具）
│   ├── eval_sample.py            # 随机重采样+生成（盲评用，取代旧 _gen_batch_v3.py）
│   ├── eval_rubric.md            # 盲评方法说明
│   └── manifests/                # 评测清单与运行日志
├── .env                          # AI_API_KEY / AI_BASE_URL / AI_MODEL（免费模型）
├── courseware_engine/
│   ├── kb_adapter.py             # KB → segments 自动适配器（核心，确定性）
│   ├── content.py                # segments → deck 内容填充
│   ├── validator.py              # deck 级校验闸门
│   ├── kb_validator.py           # KB 编写期校验
│   ├── render.py                 # deck → HTML 渲染
│   ├── kb.py                     # KB 检索（retrieve_kb）
│   ├── llm.py                    # LLM 客户端（标准库 urllib，无 requests 依赖）
│   ├── enrich_llm.py             # 免费模型层（古诗译文/赏析/作者背景）
│   ├── teach_expand.py           # 教学专家协议（算理/品析/呈现·操练·应用）
│   ├── experts.py                # 三科教育专家 agent（guide + check门禁 + review_prompt）
│   ├── reviewer.py               # 审核层（review/llm_review/expand_with_review闭环）
│   ├── schemas.py                # StyleRecipe / Deck / Slide 等 schema
│   ├── style.py / themes.py      # 主题与样式
│   ├── textutil.py / util.py     # 文本处理工具（extract_json/_clip 等）
│   └── layouts/                  # 版式定义目录
├── vendor/kb/
│   ├── 数学/                     # 98 条 JSON
│   ├── 语文/                     # 359 条 JSON
│   └── 英语/                     # 70 条 JSON
├── out/                          # 生成输出目录（HTML 等，测试产物已清空）
├── HANDOVER.md / TECH_DESIGN.md / LAUNCH_PREP.md   # 三份交接文档
└── LAUNCH_PREP.md                # 上线前准备清单（下一位 AI 主入口）
```

> 注：旧 v2 多智能体引擎（pipeline.py/agents/subjects/pipelines/quality/enrich）与 v1 vendor 单模板引擎（vendor/scripts/courseware_gen.py）已于 2026-08-15 删除；根目录所有 `_` 前缀临时脚本、`.log`/`.txt` 测试输出也一并清理。

### 3.5 生成流程详解

#### 阶段 1：教案生成（k12_generate.py）
```
输入：form {subject, grade, topic, duration}
  → retrieve_kb(subject, grade, topic) 命中课题级 KB
  → 将 KB 原文注入 prompt（ grounding 约束）
  → LLM 生成 lesson.json（字段：shared + documents[lesson_plan]）
  → 写入文件（如 out/<topic>/lesson.json）
```

#### 阶段 2：Adapter 转换
```
输入：lesson.json
  → adapter 将 K12 的 lesson_plan + shared 映射为 courseware_gen 的 form["plan"]
  → form["plan"] 结构：{objectives, keypoints, practice, process}
```

#### 阶段 3：课件生成（courseware_engine/）
```
输入：form {subject, grade, topic, plan, ...}
  → auto_kb(kb)          # KB → segments（确定性适配器）
  → content_fill(segments, style_recipe)  # 填充版式 slots
  → validate_deck(deck)  # 引号平衡/零页/完整性校验
  → build_deck(deck, style) → HTML 字符串
  → 写入 out/<topic>/index.html
```

#### 确定性生产路径（无 LLM）
对于已结构化 KB（`kb["segments"]` 存在），`auto_kb` 直接原样返回，全程零 LLM：
```
KB (with segments) → content_fill → validate_deck → render.build_deck → HTML
```

### 3.6 运行脚本速查

```bash
# 单课跑完整链路（生成单个课件预览）
cd /e/001/lesson-courseware
python tools/gen_lesson.py --path "vendor/kb/语文/三年级上_秋天的雨.json"

# 全量稳定性压测（515 KB）
python tools/stress_all.py

# 批量生成（随机采样，供 AGENT 盲评）
python tools/eval_sample.py

# 一键生成（CLI）
python orchestrator.py --subject 数学 --grade 五年级 --topic 分数的初步认识 --duration 40

# 启动 web 表单（本地预览）
python app.py
```

---

## 四、全局基础设施

### 4.1 Python 运行时
- **管理版（优先使用）**：`C:/Users/kass/.workbuddy/binaries/python/versions/3.13.12/python.exe`
- **venv**：`C:/Users/kass/.workbuddy/binaries/python/envs/default/`
- 所有包安装必须通过 venv，禁止全局 `pip install`。

### 4.2 Node.js 运行时
- **管理版**：`C:/Users/kass/.workbuddy/binaries/node/versions/22.22.2/node.exe`
- **包目录**：`C:/Users/kass/.workbuddy/binaries/node/workspace/`

### 4.3 服务器（系统 A 专用）
- IP：`101.133.139.175`
- 用户：`root`
- SSH Key：`C:/Users/kass/.ssh/id_ed25519_ekko`
- 部署目录：`/opt/ekko`（或容器内 `/app`）
- Docker Compose 文件在服务器上，本地修改后通过 `scp` + `docker compose up -d --build` 更新。

---

## 五、交接注意事项

1. **两套系统绝不混淆**
   - `class-review-system/` = 课评系统（生产环境，别动）
   - `lesson-courseware/` = 教案课件系统（开发中，当前工作对象）

2. **修改系统 A 前必须问用户**
   - 课评系统的 web 代码、模板、prompt、部署配置，任何改动都需用户明确确认。

3. **系统 B 的当前优先级**
   - P0：执行教师-AGENT 盲评（随机采样 → 生成 → AGENT 评测 → 出 eval_report_v8）
   - P0：确认 web 表单端到端链路完全打通
   - P1：修复诗词词语卡（如需）
   - P1：撰写 eval_report_v8.md

4. **稳定性铁律**
   - 任何对 `kb_adapter.py` / `content.py` / `render.py` 的修改后，**必须**重跑 `tools/stress_all.py`，确认 `CRASH=KB_BLOCK=ZERO_PAGE=OUT_IMB=ADAPT_IMB=0`。

5. **知识库 grounded 原则**
   - 所有内容生成必须 grounded 在 `vendor/kb/` 的教材原文上。
   - 不得编造作者、公式、数据；计算每步必须正确；不得引入原文未涵盖算法。

6. **Memory 与 Skills**
   - 项目级 memory：`E:/001/.workbuddy/memory/YYYY-MM-DD.md`（当日工作日志）
   - 项目级长期 memory：`E:/001/.workbuddy/memory/MEMORY.md`
   - 用户级 memory：`C:/Users/kass/.workbuddy/MEMORY.md`
   - 完成实质性工作后需更新当日日志。

---

## 六、快速 QA

**Q：课评系统和教案课件系统之间有代码共享吗？**
A：没有。二者完全独立。唯一的关联是历史上有一些手搓脚本（如 `_gen_plans.py`）派生自课评系统原型，但已被删除。

**Q：教案生成器应该用 K12 SKILL 还是手搓脚本？**
A：必须用 K12 SKILL（`k12_generate.py` 是其脚本化等价实现）。早期 `_gen_plans.py` 等手搓脚本已全部删除。

**Q： poems（诗词/词）课件的词语卡为什么不显示？**
A：因为 `_poem_word_cards` 无法正确解析当前诗词 KB 的 `重点词句：…` 前缀格式，会产生垃圾卡片。当前策略是不显示诗词的词卡（只显示 poem_thinking 赏析页）。如需显示，需先修复 `_poem_word_cards`。

**Q：一个课件从表单到 HTML 的完整链路是什么？**
A：表单 → `k12_generate.py` 生成教案 → adapter 转换 → `courseware_engine`（`auto_kb` → `content_fill` → `validate_deck` → `render.build_deck`）→ 单文件 HTML。

**Q：当前 515 KB 的稳定性如何？**
A：全绿通过。CRASH=KB_BLOCK=ZERO_PAGE=OUT_IMB=ADAPT_IMB=0。唯一非零是 SINGLE_ELL=227（良性）。
