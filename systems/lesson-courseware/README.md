# lesson-courseware · 教案 → 课件生成系统（系统 B）

> 输入一份教案（或「学科 / 年级 / 课题」），产出**能直接上讲台讲授**的单文件 HTML 课件。
> 核心思路：**知识库 grounded + 确定性内容骨架 + 可选的免费 / 强模型 LLM 层**，把「作者错、算错数、套错模板」这类致命硬伤从机制上压到最低。

---

## 系统总览：一条主线 + 一个非学科分支

系统 B 只做一件事——**把「教案 / 教学内容」变成能直接上讲台的单文件 HTML 课件**——但面向两类输入来源：

| 模式 | 输入来源 | 生成链路 | 入口 |
|---|---|---|---|
| **主线（学科）** | 用户给「学科 / 年级 / 课题」，由 K12 skill **自动生成**学科教案 | K12 生成教案 → adapter → 课件引擎 → 渲染 | `app.py`（:5057）/ `tools/gen_lesson.py` |
| **分支 `content-upload/`（非学科）** | 用户**自己上传**任意内容（培训 / 辅导班 / 讲义），跳过学科生成 | ingest → moderate → segment → render（11 风格） | `content-upload/app.py`（:5000） |

两者**共用「教案 → 课件」的底层目标与渲染思路**，差异只在「教案从哪来」：主线由系统生成学科教案，分支直接接收用户内容、不设学科前提。分支是独立子目录，自带 `pipeline/` + `styles/`，**不改动主线生成逻辑**（详见文末红线）。完整分支说明见 [`content-upload/README.md`](content-upload/README.md)。

> 关于「系统 C」：原规划的独立仓库「系统 C（内容上传功能）」已**作为本分支并入系统 B**，不再是独立项目；下文「分支」即原系统 C。

---

## ⚠️ 仓库归并说明（2026-09-01 更新）

本系统 B 已**并入 Ekko 主仓库**（`class-review-system`）的 `systems/lesson-courseware/` 子目录，不再维护独立的 `kjsys` 仓库。

- **系统 A（Ekko 课评系统）**：`class-review-system/` 根目录，已上线生产环境
- **系统 B（本目录）**：`class-review-system/systems/lesson-courseware/`，与系统 A 同仓库但**代码完全解耦**
- 两个系统部署在同一台服务器的不同 Docker 容器（`ekko-web:5000` 课评 + `ekko-courseware:5001` 课件），但共享同一份 lesson-courseware 代码。**改动本目录任何文件，两个容器都需要重建**。

---

## 分支 `content-upload/`（非学科）— 详见 [`content-upload/README.md`](content-upload/README.md)

上文「系统总览」已说明：它是系统 B 在**非学科场景**下的分支，接收用户上传内容、跳过学科生成，由同一套「课件生成平台」产出 11 风格单文件 HTML 课件。以下主线内容（双路径、专家机制、评测）仅适用于**学科主线**；分支的技术细节、风格表、运行方式见其独立 README。

**分支最新进展（2026-09-01）**：
- 修复了无围栏 C++ 代码块识别（启发式 `_looks_like_code`），代码教学内容不再丢失
- 修复了规则切页的章节层级识别（汉字数字 + 严格递增阿拉伯数字），空标题自动合并
- 11 风格全部通过真实 C++ 教案验证（4 页结构清晰，代码块完整保留）

---

## 它解决什么问题

老师手里有教案，但把教案变成「孩子能听懂、老师能流畅讲完」的课件很费时间。本系统把这条链路做成端到端的脚本化流水线：

```
学科 / 年级 / 课题（或 K12 lesson.json）
        │
        ▼
  ┌─────────────────────────────────────────────────────────┐
  │  Orchestrator 编排（orchestrator.run）                     │
  │                                                          │
  │  ① K12 教案生成（k12_generate.py）                          │
  │     · 课标 grounding：runtime 读 k12-lesson-planning         │
  │       SKILL 的 curriculum/<学科>.md，锁定学段内容要求        │
  │     · 输出 lesson.json（shared + documents[lesson_plan]）  │
  │                                                          │
  │  ② Adapter（k12_adapter.py）                              │
  │     · lesson.json → 课件端 form["plan"] 4 字段               │
  │       (objectives/keypoints/practice/process)              │
  │                                                          │
  │  ③ KB 检索 grounding（courseware_engine/kb.py）              │
  │     · vendor/kb/<学科>/<年级>_<课题>.json 命中课题级教材原文   │
  │                                                          │
  │  ④ 强 / 弱模型分离路径（按 client.is_strong() 自动分流）       │
  │     ┌────────────────────────┬────────────────────────┐    │
  │     │ 弱模型（GLM-4-Flash）    │ 强模型（用户表单填 API） │    │
  │     │ enrich_chinese 富化     │ strong_gen 一次大调用   │    │
  │     │  ↓                      │  ↓                     │    │
  │     │ auto_kb 确定性引擎       │ content_to_segments    │    │
  │     │  ↓                      │ 确定性程序映射          │    │
  │     │ teach_expand 专家协议展开 │                        │    │
  │     │  ↓                      │                        │    │
  │     │ expand_with_review      │ 跳过自审闭环            │    │
  │     │   专家自审闭环（×2 重试） │ （强模型输出已稳定）      │    │
  │     └────────────────────────┴────────────────────────┘    │
  │                                                          │
  │  ⑤ content_fill → validate_deck（确定性硬伤门禁）           │
  │     → llm_review（语义 soft）→ build_deck → out/*.html    │
  └─────────────────────────────────────────────────────────┘
        │
        ▼
   单文件 HTML 课件（out/course_*.html，可投屏 / 发学生）
```

**「能直接上课」的定义**：老师拿到这份课件，能直接在课堂上使用、流畅地把这节课知识点讲完。课件只做「内容骨架」，讲解话术由老师自己发挥。

---

## 完整思维链：主线（学科）与分支（非学科）

系统 B 的两条链路都是「**输入 → 一串确定性 / LLM 步骤 → 单文件 HTML 课件**」的形状，但每一步的输入、决策与兜底不同。下面把两条链从入口到出片逐步拆开，**◆ 标决策点**，并注明兜底 / 失败处理。

### 主线（学科）思维链 · `orchestrator.run`

> 上节「它解决什么问题」的 ASCII 图是简化版；这里展开**每一步 + 决策点**。

```
入口：网页表单 / CLI（subject, grade, topic, duration）
        │
        ▼
① 环境 & 模型路由
   · load_env() 读 .env（默认免费弱模型 GLM-4-Flash）
   · ◆ 表单填了 AI_BASE_URL / AI_MODEL / AI_API_KEY → 覆盖 .env（用户自带强模型）
   · make_client() → 统一 LLM 客户端（代理 / 指数退避重试 / is_strong() 判定）
        │
        ▼
② K12 教案生成（k12_generate.generate_lesson）
   · 脚本化调用 k12-lesson-planning SKILL 课标库（curriculum/<学科>.md）做 grounding
   · 输出 lesson.json → 落盘 lesson_*.json / lesson_*.html
        │
        ▼
③ Adapter（k12_adapter.k12_lesson_to_form）
   · lesson.json → 课件端 form["plan"]（objectives / keypoints / practice / process）
        │
        ▼
④ 课件引擎 v3（唯一路径）
   · retrieve_kb(form_cw) → 命中课题级教材原文
       ◆ 未命中 → RuntimeError「KB 未命中该课题」（硬失败，不出片）
   · ◆ 强 / 弱分流（client.is_strong()）
       ├─【强模型路径】
       │    · 派生 subject_cat / stage / lesson_type
       │    · strong_gen.generate_content(kb, client, max_attempts=4) → 一次大调用产出教学语义
       │         ◆ 返回 None → RuntimeError（强模型未产出有效内容）
       │    · content_to_segments(lc, kb) → 程序确定性映射成 typed slides（杜绝键名漂移）
       └─【弱模型路径 · GLM-4-Flash】
            · enrich_chinese(kb) → 富化译文 / 赏析 / 作者背景
            · auto_kb(kb) → 确定性引擎生成 segments（读富化字段，不靠模型吐结构）
            · expand_with_review(kb, client, max_retry=2) → 教学专家协议展开 → LLM 专家审核
                 → 不达标打回重生成（最多重试 2 次）
   · 配色：按 topic 哈希从 3 套衬线调色板选 1（确定性，非随机）
        │
        ▼
⑤ 硬伤门禁 & 渲染
   · content_fill(kb) → pages
   · validate_deck(pages, kb) → 确定性硬伤门禁
       （无例题 / 分层同题 / 截断 / 模板套话 / 品析三要素缺 / 核心句型缺）
       ◆ 命中确定性硬伤 → review_info.blocked=True（标记 blocked，阻断出片，需人工/修 KB/修引擎）
   · review_report(kb) → 确定性门禁结论（必跑）
   · ◆ 弱模型路径额外跑 llm_review(kb)（语义 soft 审核，不阻断）；强模型路径跳过（已达标，省 token）
   · build_deck(pages, recipe, identity, title, meta) → 单文件 HTML 课件
        │
        ▼
⑥ 落盘 course_*.html → 返回 {lesson_json, lesson_html, course_html, slides_count, review}
```

**主线铁律**：确定性层（KB 检索、`auto_kb` / `content_to_segments` 映射、`validate_deck` 门禁、渲染）全程不动，LLM 只做「内容富化 / 展开」；结构、键名、版式由程序钉死，从根本上规避键名漂移与事实硬伤。

### 分支 content-upload（非学科）思维链 · `app.generate`

```
入口：网页（上传文件 docx/pptx/pdf/txt/md/html/csv 或 粘贴文本）+ 选风格 + 标题
        │
        ▼
① 输入 & 解析（ingest）
   · ◆ 有文件 → 校验扩展名 ∈ ALLOWED_EXT（否则「不支持的文件类型」）
   ·              markitdown 转纯文本；.md 直接按纯文本读（标题标记不丢）
   ·              落盘临时 _up_<uuid><ext>
   · ◆ 无文件但有文本 → 超长截断至 MAX_TEXT=20000 字，ingest_text()
   · ◆ 两者皆无 → 「请上传文件或粘贴文本」
   · 解析异常 → 「解析失败：…」；提取不到文本 → 「未能从内容中提取到文本」
        │
        ▼
② 合规拦截（moderate）— 规则层必开
   · 违禁品 / 赌博诈骗 / 色情 / 暴力恐怖 / 政治敏感红线（港独台独藏独疆独等）词表命中即拦截
   · ◆ 可选 use_api_mod（网页勾选）→ 免费模型二分类二次审核（默认关，省 token）
   · ◆ 命中 → 「内容未通过合规审核：<reason>」（直接返回，不出片）
        │
        ▼
③ 切页（segment）— 只分段、不改写
   · 优先免费 API（GLM-4-Flash，prompt 强制「只分段、保留原词、不新增不润色」）
   · ◆ 无 key / 失败 → 规则降级（按 # 标题层级 / 标题正则 / 空行分段）
   · 【markdown 标记清洗·兜底】每个 bullet 先按 \n 拆行、逐行 _clean_line，
     剥掉行首残留 #/-/*/+/•/·/>/:/. 任意顺序连写（### ### 嵌套、- - - 三连、### > - foo 都能剥净）；
     列表符一并清除
   · ◆ 切不出页（空） → 「切页失败：未能拆分为幻灯片」
        │
        ▼
④ 标题 & 渲染（render）
   · 标题缺省 → 取 slides[0].title（截断 24 字）
   · ◆ 风格：用户选定；未指定 → 默认 graffiti（涂鸦像素游戏风，STYLES[0]）
   · render(slides, style, title) → 单文件 HTML（横向 scroll-snap 翻页，离线无 CDN）
       - 11 风格：graffiti⭐ / magazine / swiss / ink / devblue / apple / brutalist / glass / dracula / serif / business
       - emoji 锚点：仅 graffiti 生效（按标题语义配 ⚡🪜🖼️🎮💻🏆📝🦞…），其它 10 套 0 emoji
       - 代码 < 转义为 &lt;（防 XSS / 结构破坏）
        │
        ▼
⑤ 落盘 out/<job>/index.html → 返回「在线预览 / 下载」页
```

**分支铁律**：不为用户内容的正确性负责，只做「合规兜底 + 分段 + 好看的离线课件」；与主线共用「内容 → 课件」目标与渲染思路，差异仅在输入来源（用户自有内容、跳过学科生成、无 KB grounding）。

---

## 强 / 弱模型分离的双路径（核心设计）

| 维度 | 弱模型路径（默认） | 强模型路径 |
|---|---|---|
| **入口** | 不填任何 API（用 `.env` 默认 GLM-4-Flash） | 网页表单「模型配置」填 `AI_BASE_URL` / `AI_MODEL` / `AI_API_KEY` |
| **判定** | `client.is_strong()` → `False` | `client.is_strong()` → `True` |
| **生成** | `enrich_chinese`（古诗译文 / 赏析 / 作者背景）→ `auto_kb`（KB → 内容骨架确定性引擎）→ `teach_expand`（数学 / 语文 / 英语专家协议展开） | `strong_gen.generate_content`：基于 KB 原料**一次调用**生成整份 segments |
| **自审闭环** | ✅ `expand_with_review`：三个教学专家展开 → LLM 审核 → 打回 → 重试（`max_retry=2`） | ❌ 跳过（强模型输出已稳定，省 token） |
| **确定性映射** | ❌ | ✅ `content_to_segments`：程序确定性映射成 typed slides（杜绝键名漂移） |
| **预期** | 免费、可用、B 类残留（串课 / 语法 / 算理） | 质量更高、token 费更贵、B 类大幅下降 |

> **设计哲学**：确定性层（KB 检索、确定性映射、`validate_deck` 硬伤门禁）不动，LLM 层只负责"内容富化"。所有结构 / 键名 / 渲染都由程序钉死，模型不直接吐 segments，从根本上解决"键名漂移"。

---

## 三个教学专家机制（真实存在，但有限制）

`courseware_engine/experts.py` 定义了 **数学 / 语文 / 英语** 三个 `SubjectExpert`，各自带 `guide` / `check` / `review_prompt` 三段人设（如「教龄 25 年特级教师」）。每次弱模型路径的生成都会经 `reviewer.py → expand_with_review → llm_review → get_expert(kb["subject_cat"])` **真实调用**对应专家做自审闭环。

**诚实说明当前限制（这是已知 B 类问题的根因，不是 bug）：**

1. 这三个专家**不是独立强模型**，而是加载在**同一个免费弱模型（GLM-4-Flash）**上的 system-prompt 人设。弱模型自身不懂的知识（如某语法点、某算理），戴专家帽也审不出来。
2. 专家语义审查的结论只进入报告的 `soft` 字段，**不阻断出片**；真正阻断的只有 `validate_deck` 的确定性硬伤。
3. `reviewer.py` 内有一道引号过滤器，会**静默丢弃没有引号的审查意见**（默认判「通过」）。
4. 自审重试上限 `max_retry=2`，超限即放弃。

→ 所以「专家机制」目前对**事实硬伤（作者错、算错数、套错模板）**形同虚设，这是弱模型天花板导致的 **B 类问题**，不是没调用专家。

---

## 当前状态与已知问题

| 类别 | 含义 | 状态 |
|---|---|---|
| **A 类** | 确定性可修的代码 / 逻辑 bug（显示错、抽取错、截断、模板错贴等） | ✅ **已全部修复并验证** |
| **B 类** | 弱模型能力上限：串课、语法硬错、算理缺失、公式错配 | ⚠️ **残留**，靠升级模型根治 |

**验证结果（2026-08-15 ~ 2026-08-17）：**

- 稳定性闸门 `tools/stress_all.py` 跑全量 **515** 个有效 KB：**CRASH / KB_BLOCK / ZERO_PAGE / OUT_IMB / ADAPT_IMB 全为 0**（SINGLE_ELL=240 为良性单省略号，忽略）。
- 教师-AGENT 受控盲评（同 12 课 seed 20260815 走 r2b 重生成）：**0 可直接用 / 7 需小改 / 5 不可用** —— 不可用项全部由 B 类主导。
- 强模型独立链路（`strong_gen`）已落地：协议钉死档位数组 / summary-board 键名 + 解析层归一化兜底，根治"键名漂移"。

> 详细报告见 [`eval_report.md`](./eval_report.md)。强模型提示词协议见 [`STRONG_PROMPT_DESIGN.md`](./STRONG_PROMPT_DESIGN.md)。

---

## 升级路线（根治 B 类，不动确定性层）

B 类是弱模型天花板，不是架构问题。**最小动作**：在网页表单「模型配置」填强模型（如 `deepseek-chat` / `gpt-4o` / `claude-sonnet`）的 `AI_BASE_URL` / `AI_MODEL` / `AI_API_KEY`，重跑全链路——同一套确定性层会跑在强模型上，B 类硬伤预期大幅下降。

确定性层（KB 检索、`auto_kb` / `content_to_segments` 程序映射、`validate_deck` 门禁、HTML 渲染）**完全不动**。

---

## 目录结构

```
lesson-courseware/
├── app.py                       # Flask 网页入口（表单 + 模型配置 + 双预览，端口 5057）
├── orchestrator.py              # 核心编排器：K12教案 → adapter → v3引擎 → review → render
├── k12_generate.py              # 脚本化教案生成（基于 k12-lesson-planning SKILL 课标 references）
├── k12_adapter.py               # lesson.json → 课件 form["plan"] 适配器
├── courseware_engine/           # 引擎包
│   ├── llm.py                   # OpenAI 兼容客户端（含 is_strong 判定 / 代理 / 重试）
│   ├── kb.py                    # ★ KB 检索（retrieve_kb）
│   ├── kb_adapter.py            # ★ KB → 内容骨架 确定性适配器（核心，改动必跑压测）
│   ├── content.py               # 内容填充 content_fill
│   ├── validator.py             # ★ validate_deck 确定性门禁（阻断硬伤出片）
│   ├── reviewer.py              # 专家自审闭环（expand_with_review / llm_review）
│   ├── experts.py               # 数学 / 语文 / 英语 三个教学专家人设
│   ├── enrich_llm.py            # 弱模型富化层（古诗译文 / 赏析 / 作者背景）
│   ├── teach_expand.py          # 弱模型专家协议展开（数学 / 语文 / 英语）
│   ├── strong_gen.py            # ★ 强模型独立链路（一次大调用生成 segments）
│   ├── strong_expand.py         # 强模型协议展开兜底
│   ├── kb_validator.py / validator.py
│   ├── schemas.py / render.py / style.py / themes.py / textutil.py / util.py
│   └── layouts/                 # 版式模板
├── vendor/kb/                   # ★ 知识库（527 个 JSON：数学 98 / 语文 359 / 英语 70）
├── tools/                       # 开发 / 评测工具
│   ├── gen_lesson.py            # 单课跑完整链路（CLI）
│   ├── gen_batch_strong.py      # 强模型批量生成（密钥读 KJSYS_STRONG_API_KEY 环境变量）
│   ├── stress_all.py            # 515 KB 全量稳定性压测（开发工具）
│   ├── eval_sample.py           # 随机重采样 + 生成（盲评用）
│   ├── eval_rubric.md           # 盲评方法说明
│   └── manifests/               # 评测清单与运行日志
├── out/                         # 生成产物（*.html，gitignored）
├── .env.example                 # 模型配置占位（复制为 .env 填写）
├── requirements.txt
├── HANDOVER.md                  # 内部交接文档（状态 / 流程 / 红线）
├── TECH_DESIGN.md               # 技术设计
├── LAUNCH_PREP.md               # 上线前准备清单
├── STRONG_PROMPT_DESIGN.md      # 强模型提示词协议（三科好课件页结构 + 合格标准）
└── eval_report.md               # 教师-AGENT 盲评报告
```

> **「★」标注的是核心模块**：改这些文件后必须重跑 `tools/stress_all.py`，确认全绿。

---

## 快速开始

```bash
# 1. 安装依赖
pip install -r requirements.txt

# 2. 配置模型（免费弱模型或强模型皆可）
cp .env.example .env
#   编辑 .env 填入 AI_API_KEY / AI_BASE_URL / AI_MODEL（不填则用默认免费弱模型 GLM-4-Flash）

# 3. 启动网页（本地预览表单）
python app.py
#   浏览器打开 http://127.0.0.1:5057

# 4.（可选）命令行单课生成
python tools/gen_lesson.py --subject 语文
python tools/gen_lesson.py --path vendor/kb/数学/三年级上_分数的初步认识.json

# 5.（可选）强模型批量生成（先把密钥写环境变量）
export KJSYS_STRONG_API_KEY=sk-你的真实key        # macOS / Linux
$env:KJSYS_STRONG_API_KEY = "sk-你的真实key"       # PowerShell
python tools/gen_batch_strong.py

# 6.（可选）全量稳定性压测
python tools/stress_all.py
```

> 可选依赖 `pypinyin` / `strokes` / `eng_to_ipa` 未安装时自动降级，不影响核心生成。

---

## 知识库（grounding 真相源）

- 位置：`vendor/kb/<学科>/<年级>_<课题>.json`（课题级教材原文，人教版 / 部编版 2024 修订版）。
- **教案端和课件端共用同一份 KB**：教师端用 K12 课标生成 lesson.json、课件端用 KB 检索事实 + 定义 + 例题。两端都从机制上避免超纲和事实硬伤。
- 课件生成的「作者 / 公式 / 数据」都以 KB 原文为准，从根本上规避弱模型编作者、算错数。
- 扩展方式：往 `vendor/kb/` 加 JSON 条目即可覆盖更多课题（入库即同时惠泽教案端与课件端）。

---

## 评测工具

- `tools/stress_all.py` —— 确定性稳定性闸门（零 LLM，全量 515 KB）。
- `tools/eval_sample.py` —— 随机重采样 + v3 全链路生成，产物供教师-AGENT 盲评。
- `tools/eval_rubric.md` —— 盲评维度与方法。
- `eval_report.md` —— 最近一次盲评结论与修复记录。

**红线**：任何对 `courseware_engine/kb_adapter.py` / `content.py` / `render.py` / `kb.py` 的修改后，**必须**重跑 `tools/stress_all.py`，确认 `CRASH=KB_BLOCK=ZERO_PAGE=OUT_IMB=ADAPT_IMB=0`。

---

## 关于这个仓库（GitHub）

本仓库已**并入 Ekko 主仓库**，作为 `systems/lesson-courseware/` 子目录维护：

- **主仓库地址**：`https://github.com/lindamannnnn/Ekko.git`
- **独立仓库 kjsys 已废弃**：原 `https://github.com/lindamannnnn/kjsys.git` 不再维护，所有改动都在 Ekko 仓库
- **认证**：本机已配置专用 SSH key `~/.ssh/id_ed25519_github`（与服务器生产 key `id_ed25519_ekko` 隔离），改完代码 `git push` 即可
- `.env`（含密钥）已被 `.gitignore` 排除，**不会**进入版本库
- `out/`（生成产物）已被忽略，按需本地重新生成
- `vendor/kb/`（527 篇知识库）是系统核心，**会**随仓库提交
- `__pycache__` / `*.log` / 临时调试脚本已清理

**协作注意**：硬编码密钥严禁出现在任何被提交的文件里。`tools/gen_batch_strong.py` 已改为读 `KJSYS_STRONG_API_KEY` 环境变量，是合规范式。

**部署注意**：本目录代码被服务器上两个 Docker 容器共享（`ekko-web:5000` 课评 + `ekko-courseware:5001` 课件），**任何改动都需要重建两个容器**：

```bash
cd /opt/ekko
docker compose up -d --build web courseware
```

---

## License

[MIT](./LICENSE)