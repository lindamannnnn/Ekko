# 课前系统（content-upload）设计文档

> 目标：把大厅的「课前」入口改造成一个完整的备课工作台，既保留系统 B 的「学科→教案+课件」能力，又保留原「内容上传→课件」能力，并提供后台可查看上传内容。

---

## 1. 整体流程

```
大厅 /portal  ──点击「课前」──▶  课前首页 /  ──▶  二选一
                                                    │
                    根据学科生成                     │                    根据内容生成
                         │                         │                         │
                         ▼                         │                         ▼
                  /subject 表单页                   │                   /content 上传页
               学科 / 年级 / 课题 / 时长 / 风格      │              上传(≤15MB) 或 粘贴
                         │                         │              安全校验 + 合规审核
                         ▼                         │                         │
              调用系统 B orchestrator              │                         ▼
              生成 lesson_plan.html                │                  /content 风格页
              生成 courseware.html                 │              选择风格 + 生成课件
                         │                         │                         │
                         └───────────┬─────────────┘                         │
                                     ▼                                       │
                           结果页 /result/<job>                               │
                   教案预览 / 课件预览 / 打包下载 / 重新生成                     │
                                     │                                       │
                                     ▼                                       │
                            后台 /admin/uploads                               │
                    查看所有上传记录、下载源文件、查看状态                      │
```

---

## 2. 页面设计

### 2.1 课前首页 `/`

视觉：沿用现有瑞士国际主义风格（白底 + 黑字 + 亮黄 #ffcc00 强调 + 网格背景 + 直角粗边框）。

布局：
- 顶部：「课前备课」大标题 + 一句副标题
- 中部：两张等宽大卡片
  - 左侧：根据学科生成
    - 标题：根据学科生成
    - 说明：选择学科、年级、课题，由系统 B 自动生成教案 + 课件
    - 按钮：开始备课 →
  - 右侧：根据内容生成
    - 标题：根据内容生成
    - 说明：上传教案、讲义或粘贴文本，生成可下载课件
    - 按钮：上传内容 →
- 底部：「风格样例」网格展示 11 种风格（**每个风格一张真实预览卡片**，名称 + 短描述 + 点击放大查看 `/style-demo/<style_id>`）

### 2.2 学科生成页 `/subject`

表单字段（必填）：
1. 学科（select）：**语文 / 数学 / 英语**（仅 3 科）
2. 年级（select）：一年级上、一年级下、…、九年级下（由前端根据学科联动）
3. 课题（select）：根据学科 + 年级从 `vendor/kb` 扫描得到课程列表（已实现的 `/courses` 接口）
4. 课时（number，默认 40，范围 15-120）
5. 风格（select）：11 种风格
6. 课件标题（input，可选，留空用课题名）

**AI 模型说明区**（放在提交按钮上方）：
- 默认使用系统内置的**弱模型**（免费、响应快，能写出完整教案和课件框架）。
- 弱模型边界：复杂推理题、跨学科整合、创意拓展容易"泛泛而谈"，偶尔出现事实偏差。
- 如果你追求更稳的事实性、更强的教学设计，可点击「升级使用自己的强模型」上传 API KEY；上传后仅保存到你的账户，学科生成会优先调用强模型。
- API KEY 字段只存数据库，页面仅显示末 4 位，可随时更新或清空。

提交后：
- 前端进入「生成中…」加载页（轮询 `/status/<job>`）
- 后端启动后台线程调用 `orchestrator.py` 生成教案 + 课件
- 完成后跳转到 `/result/<job>`

### 2.3 内容上传页 `/content`

分两步：

#### 第一步：上传 / 粘贴
- 上传框：
  - 支持拖拽
  - 限制：≤15MB
  - 格式白名单：`.txt .md .markdown .csv .html .htm .docx .pptx .pdf`
  - 实时显示已选文件名和大小
- 或粘贴文本（textarea，≤20000 字）
- 安全校验：
  - 扩展名白名单
  - 魔数校验（docx/pptx/pdf 的 ZIP/PDF 签名）
  - 文件大小上限
  - 文件名清洗（去路径、特殊字符）
- 合规审核：调用 `pipeline.moderate` 规则层，可选模型二次审核
- 提交后把原始内容存入 SQLite，返回 `content_id`，进入第二步

#### 第二步：选择风格并生成
- 显示已上传文件名 / 内容首段摘要
- 风格选择：11 种
- 课件标题（input，可选）
- 提交后走 `segment → render`，完成后到 `/result/<job>`

底部：风格样例画廊。

### 2.4 结果页 `/result/<job>`

根据 `job_type` 区分展示：

学科生成结果：
- 元数据卡片：学科 / 年级 / 课题 / 课时 / 风格
- 教案预览：iframe 加载 `/preview-lesson/<job>`
- 课件预览：iframe 或新标签打开 `/preview/<job>`
- 下载按钮：下载教案 HTML、下载课件 HTML
- 若审核门禁未过，显示「需人工复核」警告

内容生成结果：
- 元数据卡片：文件名 / 风格 / 页数
- 课件预览 + 下载按钮
- 返回重新生成

### 2.5 后台页 `/admin/uploads`

表格字段：
- ID / 时间
- 来源（学科 / 内容）
- 课题或文件名
- 文件大小
- 风格
- 状态（生成中 / 成功 / 失败 / 需复核）
- 操作：查看内容、下载课件、下载教案（学科）、删除记录

顶部提供按来源和日期筛选。

---

## 3. 数据模型

SQLite：`content-upload/uploads.db`

```sql
CREATE TABLE users (
    id TEXT PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    name TEXT,
    ai_api_key TEXT,            -- 用户上传的强模型 API KEY（仅前端展示最后 4 位）
    ai_base_url TEXT,
    ai_model TEXT,
    created_at TEXT NOT NULL,
    updated_at TEXT NOT NULL
);

CREATE TABLE jobs (
    id TEXT PRIMARY KEY,            -- uuid
    user_id TEXT NOT NULL,           -- 关联 users.id
    mode TEXT NOT NULL,              -- 'subject' | 'content'
    status TEXT NOT NULL DEFAULT 'pending',  -- pending/running/success/failed/review
    created_at TEXT NOT NULL,
    -- 内容模式
    filename TEXT,
    file_size INTEGER,
    original_text TEXT,
    -- 学科模式
    subject TEXT,
    grade TEXT,
    topic TEXT,
    duration INTEGER,
    -- 通用
    style TEXT,
    title TEXT,
    -- 输出
    lesson_path TEXT,
    courseware_path TEXT,
    error_msg TEXT,
    FOREIGN KEY (user_id) REFERENCES users(id)
);
```

文件存储：
- `out/<job>/index.html`：课件
- `out/<job>/lesson.html`：教案（仅学科模式）
- `out/<job>/raw.txt`：原始内容（内容模式）

---

## 4. 安全策略

1. 文件上传：
   - 扩展名白名单 + 小写化
   - 文件大小 ≤ 15MB（硬拦截）
   - 魔数校验：docx/pptx 为 ZIP 签名 `50 4B 03 04`，pdf 为 `%PDF`
   - 文件名仅保留中英文、数字、下划线、点号，重命名为 `uuid.ext`
   - 临时文件写在 `out/_tmp/`，解析后删除

2. 内容安全：
   - 规则层合规审核（`pipeline.moderate`）
   - 可选模型二次审核
   - 文本长度上限 20000 字符

3. 登录与权限：
   - 所有课前页面、后台 `/admin/uploads` **必须登录**后才能访问。
   - 登录用户只能看到自己的 jobs；`/admin/uploads` 展示当前用户的全部生成记录。
   - API KEY 与账户绑定，页面仅展示末 4 位，数据库完整存储。

---

## 5. 与系统 B 的集成

为了不破坏系统 B 主线、不 import B 代码，学科生成采用 **subprocess 调用 orchestrator CLI**：

```bash
cd E:/001/lesson-courseware
python orchestrator.py --subject 数学 --grade 五年级 --topic 分数的初步认识 --duration 40 --out E:/001/lesson-courseware/content-upload/out/<job>
```

后端线程：
- 创建 job 记录，状态 `running`
- `subprocess.run(...)` 执行 orchestrator
- 解析 stdout 得到 `lesson_*.html` 和 `course_*.html`
- 更新 job 状态为 `success` 或 `failed`

环境变量：
- 复用 `content-upload/.env` 中的 `AI_API_KEY / AI_BASE_URL / AI_MODEL`
- subprocess 通过 `env=` 传入，覆盖 orchestrator 读取 `.env` 的值

---

## 6. 风格样例

复用现有 11 种风格 `render.STYLES`：
graffiti / magazine / swiss / ink / devblue / apple / brutalist / glass / dracula / serif / business

在首页和内容页底部用网格卡片展示：
- **每个风格一张真实预览卡片**（使用 demo deck 渲染 3 页样例）
- 风格名称 + 一句话描述
- 点击卡片弹出 lightbox，放大到视口 80% 居中显示 `/style-demo/<style_id>`，支持 ESC 关闭

生成动画：
- 进入 `/generating/<job>` 后，前端播放一个**有趣的进度动画**（例如：小机器人一页一页把 PPT 拼出来、进度条 + 随机俏皮提示语）。
- 动画期间轮询 `/status/<job>`，完成后自动跳转 `/result/<job>`。

---

## 7. 路由规划

| 路由 | 方法 | 说明 |
|------|------|------|
| `/` | GET | 课前首页（二选一 + 风格样例） |
| `/subject` | GET/POST | 学科生成表单 |
| `/content` | GET/POST | 内容上传第一步 |
| `/content/<cid>/style` | GET/POST | 内容生成第二步：选风格 |
| `/generate` | POST | 兼容原上传生成接口 |
| `/status/<job>` | GET | 查询生成状态（轮询） |
| `/result/<job>` | GET | 结果展示页 |
| `/preview/<job>` | GET | 课件预览 |
| `/preview-lesson/<job>` | GET | 教案预览（学科模式） |
| `/download/<job>` | GET | 下载课件 |
| `/download-lesson/<job>` | GET | 下载教案 |
| `/admin/uploads` | GET | 当前用户的生成记录列表 |
| `/style-demo/<style_id>` | GET | 风格样例演示页 |
| `/generating/<job>` | GET | 生成中动画页 |
| `/api/user/key` | POST | 上传/更新用户自己的 API KEY |
| `/auth/login` | GET/POST | 登录页（MVP 用简单邮箱/密码） |
| `/auth/logout` | GET/POST | 登出 |

---

## 8. 已确认决策

1. 学科只保留**语文 / 数学 / 英语** 3 科。
2. 年级保持 1-9 年级上下册，由学科在 `vendor/kb` 中实际有的课程决定课题下拉。
3. 所有课前页面与后台**必须登录**，用户只能看到自己的记录。
4. 每个风格生成**真实预览卡片**，点击可放大查看。
5. 生成等待使用 `/generating/<job>` 页面，带**有趣的进度动画**和轮询，不额外发通知。
6. 学科页需向用户解释**弱模型边界**与**强模型升级**，并提供上传 API KEY 保存到用户字段的能力。
