# 内容上传分支（content-upload）— 系统 B 的非学科分支

> 本分支即原规划的独立仓库「**系统 C（内容上传功能）**」，已并入系统 B 仓库（不再独立）。下文统称「本分支」。

把用户上传的任意课程内容（学科 / 辅导班 / 培训机构材料均可）做成一份**好看、可直接翻页、完全离线的单文件 HTML 课件**。

> **定位**
> - 我们**不为用户内容负责**，只把上传物做成好看的 HTML PPT。内容类型不限。
> - **但**：用户上传内容里残留的 markdown 格式符号（`#` / `##` / `###`、`-` / `*` / `+` / `•` / `·`、`>`、列表序号 `：` 等）**默认会被清洗掉**，不会原样带进课件。即使用户口头说"不要管格式"，落到这种场景仍默认剥标记——这是已确认的硬约束。

---

## 流水线（4 层）

```
入口：网页（上传文件 / 粘贴文本）+ 选风格 + 标题
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

> 主线（学科）的完整思维链见系统 B 总文档 [`../README.md`](../README.md) 的「完整思维链」章节；本分支不生成学科教案、无 KB grounding，差异仅在输入来源。

- **ingest** (`pipeline/ingest.py`)：用 `markitdown` 通吃 docx/pptx/pdf/html/txt/md；`.md` 直接按纯文本读（标题标记不丢）；无 markitdown 时降级纯文本。
- **moderate** (`pipeline/moderate.py`)：规则词表（违禁品 / 赌博诈骗 / 色情 / 暴力恐怖 / 政治敏感红线如港独台独藏独疆独等）命中即拦截；可选 `use_api` 走免费模型二分类（默认关）。
- **segment** (`pipeline/segment.py`)：优先免费 API（弱模型 GLM-4-Flash，prompt 强制「只分段、保留原词、不新增不润色」），无 key / 失败走规则降级（按 `#` 标题层级 / 标题正则 / 空行分段）。
  - **markdown 标记清洗（关键兜底）**：无论 LLM 还是规则切页，每个 bullet 都会**先按 `\n` 拆行、再逐行 `_clean_line`**，剥掉行首残留的 `#`/`-`/`*`/`+`/`•`/`·`/`>`/`:`/`.` 任意顺序连写（`### ### 嵌套`、`- - - 三连`、`### > - foo` 都能剥干净）；`-`/`*` 列表标记也被一并清除。
- **render** (`render.py` + `styles/*.css`)：单文件 HTML，横向 scroll-snap 翻页，支持键盘(←→/空格/Home/End)、触摸滑动、点击左右半屏、进度条，**完全离线无 CDN**（字体用系统 CJK 栈）。

### 11 套风格（含默认）
| id | 名称 | 调性 |
|---|---|---|
| `graffiti` ⭐默认 | 像素游戏·街机风 | 亮白卡叠彩色深底(navy/玫红/青蓝轮换) + 金强调 + 像素网格 + emoji 标题锚点 |
| `magazine` | 电子杂志·电子墨水 | 衬线 + 暖纸 + 赭石 |
| `swiss` | 瑞士国际主义 | 无衬线 + 网格 + IKB/柠檬黄/安全橙 |
| `ink` | 水墨中国风 | 宣纸 + 墨色 + 印章红 |
| `devblue` | 开发者极简蓝 | 单一蓝 + 琥珀，非对称 |
| `apple` | 苹果极简 | 系统字体 + 大量留白 |
| `brutalist` | 复古工业 | 等宽 + 粗黑边框 + 高对比 |
| `glass` | 暗色玻璃拟态 | 暗渐变 + 毛玻璃卡 + 霓虹 |
| `dracula` | 霓虹暗夜 | dracula 配色 + 发光文字 |
| `serif` | 极简衬线 | 经典衬线 + 细分割线 |
| `business` | 商务专业 | 藏青 + 金，企业感 |

- **默认风格**：`graffiti`（源自用户桌面的《涂鸦PK（一）》课件，已逐条对照还原为"亮白卡 + 彩色背景节奏 + emoji 锚点"）。`render.STYLES` 首位、`app.py` 网页默认选中项都是它；不指定风格即走这套。
- **emoji 规则**：仅在 `graffiti` 生效——`render.py` 的 `_with_emoji()` 按标题语义自动配 emoji 锚点（⚡对比 / 🪜方法 / 🖼️壁纸 / 🎮资料 / 💻代码 / 🏆总结 / 📝作业 / 🦞封面…），**正文文字一字不改**。其它 10 套风格完全不带 emoji。
- 风格设计规范：`out/style_design_graffiti.md`（色彩 / 字体 / 版式 / 组件 / 动效 / 导航 / 落地取舍 / emoji 规则 九节）。

---

## 运行

```bash
# 1. 环境（managed python + 独立 venv，已建好）
.venv\Scripts\python.exe -m pip install markitdown==0.1.7 flask==3.1.3

# 2. 免费 API（智谱 GLM-4-Flash）
#    当前 .env 已含真实可调用 key（从系统 B 的 .env 拷贝 AI_* 四个变量，未碰系统 B 其它密钥）。
#    无 key 也能跑，切页走规则降级。
#    AI_API_KEY=...
#    AI_BASE_URL=https://open.bigmodel.cn/api/paas/v4
#    AI_MODEL=glm-4-flash

# 3. 启动 Web 服务
.venv\Scripts\python.exe app.py
# 打开 http://localhost:5000  → 上传文件 / 粘贴文本 → 选风格 → 生成 → 预览 / 下载
```

### 命令行直接生成（不启服务）
项目里这几个脚本跑的是**同一套真实流水线**（ingest → moderate → segment(LLM) → render），方便批量/测试：

| 脚本 | 用途 |
|---|---|
| `sample_gen.py` | 用一份样例内容生成 10 套示例课件 → `out/sample_<风格>.html` |
| `gen_d1.py` | 把《小龙虾启蒙营 D1 教师手册》直接分页（已不再使用，仅保留历史） |
| `gen_d1_student.py` | 把 D1 **转化为学生向内容**后生成 6 套课件 → `out/d1_student_<风格>.html` |
| `gen_random.py` | **全流程压力测试**：自写 3 套原创培训内容（刻意埋表格/`###`/代码`<`/emoji）+ 随机风格 + 11 风格全冒烟。改 seed 换随机组合 |

---

## 目录
```
content-upload/
├── app.py                 Flask 入口（上传 / 生成 / 预览 / 下载）
├── render.py              渲染核心 + 风格注册表 + emoji 锚点逻辑
├── pipeline/
│   ├── llm.py             纯标准库 OpenAI 客户端（代理+限流/超时指数退避+弱模型标志），不 import 系统 B
│   ├── ingest.py          解析层（markitdown）
│   ├── moderate.py        合规拦截
│   └── segment.py         切页层（LLM + 规则降级 + markdown 标记清洗兜底）
├── styles/                11 套主题 CSS（含 graffiti 默认）
├── sample_gen.py         示例课件
├── gen_d1.py / gen_d1_student.py / gen_random.py   各用途生成脚本
├── selftest.py            自测
├── out/                  产物（课件 HTML / 源 md / 设计规范，gitignore）
├── .env / .env.example   免费 API 配置（.env 已含真实 key）
├── PLAN.md               原功能规划（v3）
└── README.md             本文件
```

---

## 已验证（冒烟测试结论）
- ✅ 合规不误杀正常培训内容（且 港独/台独/毒品 等能拦截）
- ✅ 切页对 **表格 / `###` 子步骤 / 长文 / 多行块** 均稳定，并会按行拆开、清洗 markdown 标记
- ✅ 代码里的 `<` 符号被转义（`分数 < 60` → `分数 &lt; 60`），无 XSS / 结构破坏风险
- ✅ emoji 严格仅 `graffiti` 出现，其它风格 0 emoji 前缀
- ✅ 11 套风格均能渲染不报错；离线单文件、双击即开
- ✅ `selftest.py` 回归（4 页规则切页 + 合规 ok + 11 风格渲染）全过
- ✅ **C++ 代码教学内容完整保留**（2026-09-01 验证）：启发式识别无围栏代码块（`#include` / `int main()` / `cout <<`），11 风格全部正确渲染代码块
- ✅ **规则切页层级清晰**（2026-09-01 修复）：汉字数字章节 + 严格递增阿拉伯数字识别，空标题自动合并，不再出现 9 页混乱空壳

---

## 红线 / 边界
本分支（`content-upload/`）现位于 **Ekko 主仓库（`class-review-system/systems/lesson-courseware/content-upload/`）**，是系统 B 在**非学科场景**下的一个分支，与 B 主线（学科教案→课件）共用「课件生成平台」思路。
- **不改动系统 B 自身的生成逻辑**：`k12_generate.py` / `k12_adapter.py` / `orchestrator.py` / `courseware_engine/*` 一律不动；本分支为独立子目录，自带 `pipeline/` + `styles/`。
- **系统 A（Ekko 课评，同仓库根目录）仍独立、不触碰**。
- `pipeline/llm.py` 复刻系统 B 的纯标准库客户端，但**不 import 系统 B 任何代码**（保持分支自洽、不耦合主线）。
- 智谱 key 从系统 B `.env` 只拷 `AI_*` 四个变量到本分支 `.env`（`content-upload/.env`），不动系统 B 其它密钥。

**部署**：本分支代码随 lesson-courseware 一起被两个容器共享（`ekko-web` + `ekko-courseware`），改动后需重建两个容器。

## 已知限制 / TODO
- 上传的**纯段落、无标题**内容，规则切页粒度较粗；有 key 时 LLM 切得更细（已验证）。
- `vendor_engines/guizang_adapter.py`（接入 guizang 引擎）可选未做——当前 11 风格均由自实现引擎覆盖，guizang 适配非必需。
- 参考稿《涂鸦PK（一）》里的"对话气泡/说话气泡"式排版，引擎暂无对应 DOM 节点，暂无法还原。
