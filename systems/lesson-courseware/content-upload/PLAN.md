# 功能计划：用户上传内容 → 漂亮 HTML 课件（v3）

> 状态：**规划中**（仅文档，未写代码）。本计划独立于已冻结的系统 A / 系统 B 代码仓库。
> 本版依据用户 5 项决策（2026-08-17）重做：**不为用户内容负责 · 内容类型不限 · 只把上传物做成好看的 HTML PPT · 优先复用 GitHub / 市场现成 skill · 加合规兜底**。

---

## 0. 已确认的 5 项决策（来自用户）

| # | 问题 | 决策 |
|---|---|---|
| Q1 | 风格是否只有 2 种？ | ❌ 否。已调研到 **10 种风格**，来源跨多个 skill + GitHub 开源主题，见 §3。 |
| Q2 | 解析层用哪个？ | ✅ 推荐：**`markitdown-skill`**（PDF/Word/PPT/图片OCR/音频 → 文本，通吃所有格式）。 |
| Q3 | 切页/分段用什么模型？ | ✅ **我们免费的那个 API**（系统 B 同款 GLM-4-Flash，OpenAI 兼容）。 |
| Q4 | 代码放哪？ | ✅ **独立新目录** `E:/001/content-upload-feature/`，与系统 A/B 红线彻底隔离。 |
| Q5 | 要不要内容合规兜底？ | ✅ **需要**。平台合规义务（拦截违法/敏感内容），与"不为内容负责"不冲突。 |

---

## 1. 功能定义（三个硬约束）

1. **不为用户内容负责**：不改写原话、不核验事实、不判断超纲/对错。上传啥就排啥。
2. **内容类型不限**：学科教材、辅导班讲义、培训机构课程、企业内训……任意文本/文档都行。
3. **只做漂亮 HTML PPT**：产出 = 单文件 `index.html`（可翻页、可离线、浏览器打开即用）。

> 与系统 B 的刻意区分：系统 B 的 `class-course-content` 做"知识库 grounding + 事实核验 + 能上讲台讲授"；**本功能明确不做这些**，纯排版美化。

---

## 2. 调研结论（GitHub / 市场现成资源，不用造轮子）

### 2.1 渲染层（直接复用）
| Skill | 状态 | 能力 | 用途 |
|---|---|---|---|
| **guizang-ppt-skill** | 已装 | 单文件 HTML 横向翻页 PPT，自带 2 套高颜值视觉 + 版式库 + 动效 | **核心渲染引擎**（风格 1/2，并可挂更多主题 CSS） |
| **primary-chinese-courseware** | 已装 | 中国风水墨视觉（低/中/高段切换），单文件 HTML | 抽成通用"水墨主题"（风格 3） |
| **teaching-courseware-maker** | 已装 | frontend-dev 设计风（非对称+单一强调色+内联SVG+无占位图），单文件 HTML | 开发者极简风（风格 4） |
| **frontend-dev** | 已装 | 顶级 UI 设计 + 电影级动效 + AI 生图 | 暗色玻璃拟态等 bespoke 风（风格 7）兜底引擎 |
| **alice-ppt-generator** | 市场可装 | 万得 Alice 幻灯片 CLI：标题/目录/章节/图文/结论，专业商务风 | 商务风灵感（风格 10） |

### 2.2 解析层（直接复用）
- **markitdown-skill**（市场可装）：PDF / Word / PPT / Excel / 图片OCR / 音频 → 纯文本。覆盖"内容不限"的全部输入格式。

### 2.3 GitHub 开源视觉灵感（只借鉴主题 CSS，不整包引入）
- **reveal.js** 11 套官方主题：black / white / league / sky / moon / **dracula** / beige / blood / night / **serif** / simple
- **Slidev** 社区主题：**apple-basic**（苹果极简）/ **brutalist**（复古工业）/ seriph（简洁大气）
- **Oh My PPT**（`arcsin1/oh-my-ppt`，MIT）：docx/txt/md → AI → 漂亮 HTML 幻灯片（Electron 桌面应用，整包集成过重，仅借鉴"多风格切换"思路）

> 结论：渲染与解析**全部复用现成 skill**，我们唯一要写的薄逻辑是「上传文本 → 切页（风格无关的结构化 JSON）」，以及「风格路由 → 选引擎/主题」。

---

## 3. 风格清单（10 种，跨多 skill / 开源）

| # | 风格名 | 来源 skill / 灵感 | 视觉特征 | 渲染引擎 |
|---|---|---|---|---|
| 1 | 电子杂志·电子墨水 | guizang ① | 衬线字体 + 流体背景 + 暖色调 | guizang 引擎 |
| 2 | 瑞士国际主义 | guizang ② | 无衬线 + 网格点阵 + IKB蓝/柠檬黄/柠檬绿/安全橙 | guizang 引擎 |
| 3 | 水墨中国风（低/中/高段） | primary-chinese-courseware | 宣纸墨韵 + 留白，按学段切卡通/写意/写实 | 抽成通用水墨主题 |
| 4 | 开发者极简蓝 | teaching-courseware-maker | 非对称 + 单一蓝 `#2563eb` + 琥珀 `#f59e0b` + 内联 SVG | teaching/frontend 引擎 |
| 5 | 苹果极简 | Slidev apple-basic | 大量留白 + 细字重 + 克制 | 自实现主题 CSS |
| 6 | 复古工业 brutalist | Slidev brutalist | 粗黑边框 + 高对比 + 等宽字体 | 自实现主题 CSS |
| 7 | 暗色玻璃拟态 | frontend-dev | 毛玻璃 + 霓虹光晕 + 深色底 | frontend 引擎 / 自实现 |
| 8 | 霓虹暗夜 dracula | reveal.js dracula | 紫黑底 + 亮粉/绿代码感 | 自实现主题 CSS |
| 9 | 极简衬线 serif | reveal.js serif/simple | 米白底 + 衬线 + 优雅 | 自实现主题 CSS |
| 10 | 商务专业 | alice-ppt-generator | 标题/目录/章节/图文/结论，稳重配色 | 自实现主题 CSS |

> 风格 1/2 用 guizang 引擎直接出；风格 3/4/7 抽/复用现有 skill 引擎；风格 5/6/8/9/10 以"主题 CSS 文件"形式挂在 guizang 轻引擎上（借鉴 reveal.js 的 theme CSS 机制，一个引擎 + N 套 CSS）。
> **前端呈现**：每次生成前让用户从 10 种里选 1 种（默认给"瑞士国际主义"或随机），选完再渲染。

---

## 4. 架构（4 层流水线）

```
[用户上传] 任意格式文件 / 粘贴文本
    │
    ▼
[1] 解析层  ── markitdown-skill ──► 纯文本（保留段落/标题结构）
    │
    ▼
[2] 切页层  ── 免费 API (GLM-4-Flash) ──► 结构化 slides JSON
    │            （只按语义分段：{title, bullets[]}，不改写原话、不增删事实）
    ▼
[3] 合规层  ── 敏感/违规词扫描（免费 API 或规则）── 命中则拦截并提示，不渲染
    │
    ▼
[4] 渲染层  ── 风格路由 ──► 按所选风格 dispatch 到引擎/主题 ──► 单文件 index.html
```

- **解析层**：markitdown，通吃格式。
- **切页层**：免费 API 做轻量语义分段（比纯规则"按空行/标题切"更准，且免费），输出风格无关的中间结构。
- **合规层（Q5）**：上传即扫一层违法/敏感内容（政治、色情、暴力、违禁品等），命中直接拒绝并说明原因。这是平台合规底线，不影响"不为内容负责"定位。
- **渲染层**：风格路由表（§3）→ 调对应引擎/主题 → 出 HTML。

---

## 5. 目录结构（独立新目录，不碰系统 A/B）

```
E:/001/content-upload-feature/
├── PLAN.md                     # 本计划
├── README.md                   # 功能说明（实施后补）
├── .env.example               # 免费 API 配置占位（同系统 B 的 GLM-4-Flash）
├── requirements.txt
├── app.py                      # 上传入口 + 风格选择 UI（轻量，Flask 或纯静态+JS）
├── pipeline/
│   ├── ingest.py               # 调 markitdown 解析
│   ├── segment.py              # 调免费 API 切页（结构化 JSON）
│   ├── moderate.py             # 合规扫描（Q5）
│   └── render.py               # 风格路由 → 调引擎/主题 → 出 HTML
├── styles/                     # 自实现主题 CSS（风格 5/6/8/9/10）
│   ├── apple-minimal.css
│   ├── brutalist.css
│   ├── dracula.css
│   ├── serif-minimal.css
│   └── business.css
├── vendor_engines/             # 复用现有 skill 渲染引擎的薄适配（不修改原 skill）
│   └── guizang_adapter.py      # 调 guizang-ppt-skill 出风格1/2
└── out/                        # 生成产物（gitignore）
```

> 复用方式：**只读调用**现有 skill（guizang / primary-chinese / teaching-courseware / frontend-dev），通过它们的 Python API 或 SKILL.md 约定的脚本入口，**不复制、不修改**这些 skill 本体。新目录只放"胶水"代码与自实现主题 CSS。

---

## 6. 实施任务清单（分阶段，写代码前需用户显式解锁本目录开发）

- [ ] **阶段 0 脚手架**：建目录、`.env.example`、装 `markitdown-skill`、确认免费 API 可用。
- [ ] **阶段 1 解析**：`ingest.py` 调 markitdown，支持文件上传 + 文本粘贴，输出纯文本。
- [ ] **阶段 2 切页**：`segment.py` 调免费 API，把文本切成 `{title, bullets}` 结构化 JSON（轻 prompt，禁改写）。
- [ ] **阶段 3 合规**：`moderate.py` 敏感词/违规扫描，命中拦截 + 友好提示。
- [ ] **阶段 4 渲染-核心**：`render.py` + `guizang_adapter.py`，先打通风格 1/2（guizang 引擎）。
- [ ] **阶段 5 渲染-扩展**：接入风格 3/4/7（抽 primary-chinese / teaching 引擎）；写 `styles/` 下 5 套自实现主题 CSS（风格 5/6/8/9/10）。
- [ ] **阶段 6 前端**：`app.py` 上传页 + 10 风格选择 + 预览/下载 `index.html`。
- [ ] **阶段 7 自测**：用 3 类样本（学科讲义 / 辅导班 PDF / 机构课程 Word）各跑一遍 10 风格。

---

## 7. 待确认 / 风险

- **R1 风格 3/4/7 复用现有 skill 引擎**：需确认能否"只取视觉、不取内容逻辑"。若 skill 强绑定教学内容，则改为"借其 CSS/模板思路、自实现轻引擎"。
- **R2 alice-ppt-generator 输出格式**：它是 PPT CLI，未必出 HTML；若只能出 PPTX，则风格 10 改为自实现 HTML 主题（不影响 10 风格总数）。
- **R3 合规层粒度**：先用规则词表 + 免费 API 二分类；误杀率需实测调阈值。
- **R4 免费 API 限流**：切页 + 合规若同用 GLM-4-Flash，需控制并发/重试。

---

## 8. 与系统 A / B 红线的关系

- 本功能 **全部新建于 `E:/001/content-upload-feature/`**，不读取/不修改系统 A（`class-review-system`）、系统 B（`lesson-courseware`）的任何代码。
- 仅**只读复用**系统 B 同款免费 API 配置思路（各自独立 `.env`，不共享密钥文件）。
- 复用现有 **skill**（guizang / primary-chinese / teaching-courseware / frontend-dev / markitdown）通过既定调用契约，**不改动 skill 本体**。
