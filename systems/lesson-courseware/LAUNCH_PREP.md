# 上线前准备交接文档（系统 B · 教案→课件）

> 给下一位接手上线准备工作的 AI。读完这份 + `HANDOVER.md` + `TECH_DESIGN.md` 三份，即可上手。
>
> 更新日期：2026-08-15

---

## 0. 三份文档的分工（先读这个）

| 文档 | 内容 | 什么时候读 |
|---|---|---|
| **本文件 `LAUNCH_PREP.md`** | 上线前要做的具体任务清单 + 当前状态 + 边界 | 接手即读 |
| `HANDOVER.md` | 两套系统全局、文件地图、历史修复、红线 | 同上 |
| `TECH_DESIGN.md` | 生成式技术路径的架构与经验（原料 vs 成品、三科专家 agent） | 改引擎前必读 |

---

## 1. 一句话背景

**系统 B（本目录 `lesson-courseware/`）是一个「教案 + 课件」生成系统，当前处于开发完成、尚未上线部署的状态。** 用户要换一个 AI 来做上线前的准备。

**系统 A（`class-review-system/`，课评系统）是已上线生产系统，绝对不要动。** 详见红线。

---

## 2. 当前状态（已核实，勿重复劳动）

以下都已在本机验证过，接手时先确认而不是重做：

| 项 | 状态 | 证据 |
|---|---|---|
| 引擎 | **唯一 v3**（确定性引擎 + 免费模型 + 自审闭环），v2/v1 旧引擎已删除 | `orchestrator.py` 默认 `"v3"`；`app.py` 表单只有 v3 |
| KB 稳定性 | 515 条全绿 | `CRASH=0 / KB_BLOCK=0 / ZERO_PAGE=0 / RAW_IMB=0 / OUT_IMB=0 / ADAPT_IMB=0`（SINGLE_ELL 良性） |
| 三科门禁 | 确定性门禁已落地，命中即 `blocked` | `courseware_engine/experts.py` + `reviewer.py` |
| 升级 API 路径 | 已留口 | `app.py` 表单「模型配置」折叠区（`AI_BASE_URL`/`AI_MODEL`/`AI_API_KEY`） |
| 端到端 | 表单→教案→课件→放映全链路通 | `orchestrator.run()` 返回 `review{blocked,hard,soft,expert}`，前端按 `blocked` 显示横幅 |
| 免费模型 | GLM-4-Flash，配置在 `.env` | `.env` 有 `AI_API_KEY`/`AI_BASE_URL`/`AI_MODEL` 三键 |

---

## 3. 上线前准备清单（按优先级，逐条做）

### P0 —— 上线前必做

#### ① 补 `requirements.txt`（当前缺失，硬缺口）
系统 B 目前**没有依赖清单**。实际第三方依赖只有 5 个，其余全是标准库（LLM 客户端用 `urllib.request`，不依赖 requests/openai）：

```
Flask==3.1.3
python-dotenv
pypinyin==0.55.0
strokes==0.0.1
eng_to_ipa==0.0.2
```

> 后三个（pypinyin/strokes/eng_to_ipa）在 `kb_adapter.py` 里是函数内 `try import`，装不上会**降级**（拼音/笔画/音标缺失）而不会崩——但上线前必须确认装上了，否则生字词/音标质量掉一档。

**验证**：`python -c "import flask, dotenv, pypinyin, strokes, eng_to_ipa"` 无报错。

#### ② 复跑稳定性闸门
```powershell
$env:PYTHONIOENCODING='utf-8'
& "C:\Users\kass\.workbuddy\binaries\python\versions\3.13.12\python.exe" "E:\001\lesson-courseware\tools\stress_all.py"
```
**通过标准**：`CRASH / KB_BLOCK / ZERO_PAGE / RAW_IMB / OUT_IMB / ADAPT_IMB` 全为 0（SINGLE_ELL 忽略）。

#### ③ 随机采样 + 教师 AGENT 盲评（上线前最后一道回归）
这是历史上最有效暴露长尾缺陷的手段（换新随机种子每次都能暴露上一批没覆盖的问题）。步骤：
1. 换一个**新的随机种子**，随机抽 12 课（语/数/英各 4、跨年级），跑完整 v3 链路生成 HTML。
2. 用 **AGENT 工具模拟教师盲评**（经验：用主线程单 AGENT，并行子 AGENT 易返回空）。
3. 评测维度：直接可讲性、跨课串课风险、练习≠作业、例题答案正确、诗词版式、exercises 真实题。
4. **通过标准**：0「不可用」。
5. 每发现一个缺陷，**修根因**（不是只修样本），修完重跑第 ② 步闸门。

参考脚本：`tools/eval_sample.py`（随机采样生成）、`tools/gen_lesson.py`（单课跑全链路）。

#### ④ 本地端到端验证网页
```powershell
$env:PYTHONIOENCODING='utf-8'
& "C:\Users\kass\.workbuddy\binaries\python\versions\3.13.12\python.exe" "E:\001\lesson-courseware\app.py"
```
浏览器开 `http://127.0.0.1:5057`，确认：填表→生成→双预览（教案+课件 iframe）→ lesson.json 下载→门禁未过时出红色横幅→「模型配置」折叠区可展开。

#### ⑤ 生产配置决策（**用户已拍板：都不动**，勿擅自做）
- **部署形态**：系统 B 保持本地 Flask 开发态（`127.0.0.1:5057`），**不部署**。是否上线部署、部署到哪，留待用户后续另行指示，不要自行决定。
- **模型**：保持免费 GLM-4-Flash，**不切模型**。升级 API 路径（表单「模型配置」）已留，改不改由用户后续定。
- **安全**：保持现状，**不改** `SECRET_KEY`/`debug`/`.env`（留待真正部署时再处理）。

### P1 —— 重要但可后置

#### ⑥ 强模型 A/B 对比（验证升级路径真的有效）
同一课题分别用免费模型和更强模型各跑一次，对比 `review.soft`（LLM 语义审核）是否显著减少。这能验证「留升级 API 路径」的决策是否成立。

#### ⑦ 诗词词语卡质量（已知历史债）
`_poem_word_cards` 对诗词 KB 产出垃圾卡片，当前策略是**不展示诗词词卡**（只展示赏析页）。如需恢复，要先修 `_poem_word_cards` 解析 `重点词句：词（释）` 格式。

#### ⑧ 课后课评串联（**用户已拍板：不动**）
工作台「课后」环节指向系统 A（课评）。当前**不做任何代码级串联**，系统 B 保持现状。是否加「课后→去课评」入口，留待用户后续指示；动系统 A 前必须先问用户。

### P2 —— 优化

- 更多学科/学段覆盖（当前仅小学语/数/英三科）。
- 写 `eval_report_v8.md`（当前最新是 v6，HANDOVER 里提到 v8 待补）。

---

## 4. 关键文件地图（只列上线准备要碰的）

```
lesson-courseware/
├── app.py                  # Flask 入口（表单 + 模型配置 + 阻断横幅）
├── orchestrator.py         # 编排器：K12教案 → adapter → v3引擎 → review → render
├── k12_generate.py         # 脚本化教案生成（基于 k12 SKILL 课标）
├── k12_adapter.py          # lesson.json → 课件 form
├── tools/
│   ├── stress_all.py       # 515 KB 全量稳定性压测（开发工具）
│   ├── gen_lesson.py       # 单课跑全链路（开发工具）
│   ├── eval_sample.py      # 随机重采样+生成（盲评用）
│   ├── eval_rubric.md      # 盲评方法说明
│   └── manifests/          # 评测清单与运行日志
├── courseware_engine/
│   ├── kb_adapter.py       # KB→segments 确定性适配器（核心，改动必跑压测）
│   ├── enrich_llm.py       # 免费模型层（古诗译文/赏析/作者背景）
│   ├── teach_expand.py     # 教学专家协议（算理/品析/呈现·操练·应用）
│   ├── experts.py          # 三科专家 agent（guide + check门禁 + review_prompt）
│   ├── reviewer.py         # 审核层（review / llm_review / expand_with_review闭环）
│   ├── kb.py               # KB 检索（retrieve_kb）
│   ├── llm.py              # LLM 客户端（标准库 urllib，无 requests 依赖）
│   ├── content.py / validator.py / render.py  # 填充/校验/渲染
│   └── layouts/            # 版式定义
├── vendor/kb/数学|语文|英语/   # 515 条教材原料 JSON
├── out/                    # 生成产物（测试产物已清空）
├── .env                    # AI_API_KEY / AI_BASE_URL / AI_MODEL（免费模型）
├── HANDOVER.md             # 全局交接
├── TECH_DESIGN.md          # 架构与经验
└── LAUNCH_PREP.md          # 本文件
```

> 旧 v2 多智能体引擎（pipeline.py/agents/subjects/pipelines/quality/enrich）与 v1 vendor 单模板引擎（vendor/scripts/courseware_gen.py）已删除，唯一引擎是 v3；根目录 `_` 前缀临时脚本、`.log`/`.txt`、`out/` 测试产物也已清理。

---

## 5. 红线（违反=事故）

1. **系统 A（`class-review-system/`）是生产系统，别动。** 改 web 代码/模板/prompt/部署配置前必须先问用户，且不要重建部署。
2. **改 `kb_adapter.py` / `content.py` / `render.py` 后必须重跑 `tools/stress_all.py`**，确认全绿。
3. **内容必须 grounded 在 `vendor/kb/` 教材原文**，不得编造作者/公式/数据。
4. **引擎只保留 v3**，不要重新引入 v2/v1。

---

## 6. 已知边界（诚实告知，别试图"自动修好"）

- **确定性门禁**只能消除「可程序化硬伤」（答案错、分层同题、截断、模板套话、核心句型缺失等）。
- **`review.soft`（LLM 语义审核）** 报的是弱模型天花板：真算理深度（循环论证）、品析手法准确度、知识性错误——**重试和 LLM 自审都兜不住**（审核 LLM 与生成 LLM 同弱模型同缺陷）。上线后这部分要么靠升级更强模型，要么靠人工补，**不要假装能自动修好**，也不要因此无限重试。

---

## 7. 接手后前 30 分钟建议顺序

1. 读本文件 + `HANDOVER.md` 第 1、3 节 + `TECH_DESIGN.md`。
2. 跑第 ② 步闸门确认现状全绿。
3. 补第 ① 步 `requirements.txt`。
4. 本地起 `app.py` 跑一遍端到端（第 ④ 步）。
5. 带着「第 ⑤ 步的三个问题」去问用户，拿到部署/模型/安全决策后再往下做。

> **注意**：第 ⑤ 步（部署/模型/安全）和第 ⑧ 步（课后串联）用户已明确「都不动」——新 AI 接手时**不要去做这两项**，只做 P0 的 ①②③④（依赖清单、压测、盲评、本地端到端验证）即可。部署、切模型、串联等属于用户后续另行下达的任务。
