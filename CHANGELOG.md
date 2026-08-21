# Changelog

所有重要的变更都将记录在此文件中。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)，
并且本项目遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [Unreleased]

### Added
- 课前备课：按学科自动生成教案 + 课件，支持 11 种风格离线 HTML 渲染。
- 课前备课内容生成：上传任意教学内容（txt/docx/pptx/pdf）生成课件，支持代码块保留、特殊符号、无围栏代码标记。
- 用户自定义 API KEY：账号页填入 OpenAI 兼容 KEY 后，课评生成、课前备课、学生阶段总结、卡片标签情感判定均优先使用用户 KEY。
- 班级详情页快捷编辑、历史课评时间线、优秀课评范例上传。
- 课评编辑器批量生成、同班去重、状态机（pending / generating / draft / confirmed / leave / failed）。
- 家长群分享卡片生成（图片导出）。
- 平台总后台：用户 / 班级 / 课件 / 课评 / 课前备课任务管理。
- **课评图片模板选择器**：`/cards/preview/<review_id>` 页面顶部新增 2 行 × 5 列共 10 个色块按钮（01 奶油手账 / 02 极简留白 / 03 新中式卷轴 / 04 童趣贴纸 / 05 商务深蓝 / 06 森系自然 / 07 霓虹赛博 / 08 复古杂志 / 09 清新马卡龙 / 10 黑板粉笔），点击即时切换 `.rcard` 的 `theme-XX` class。选择自动持久化到 `localStorage.ekko_card_theme`，下次打开自动恢复；也支持 URL `?theme=theme-XX` 强制指定。深色主题（05/07/10）下页面底色与导出 PNG `backgroundColor` 会同步切换。
- **课评卡片 10 套模板设计稿预览页**：`/cards/gallery` 路由 + `templates/cards/gallery.html`，供浏览/对比所有模板。每套主题在基础样式上追加了装饰层（和纸胶带 / 半调网点 / 云纹 / 枝叶 / 网格光晕 / 粉笔涂鸦等），全部为字面色 + 内联 SVG data URI，html2canvas v1.4.1 兼容，DOM 不变。
- **`.env.example`**：新增 163 邮箱 SSL（端口 465）配置示例，区分 QQ 邮箱 STARTTLS（587）与 163 SSL（465）两种典型组合。

### Changed
- 请假课评行为：点击「请假」后直接写入 `content = "请假"` 且不调用 AI；再次生成仍返回「请假」。
- 用户 API KEY 文案统一：账号页与课前备课页从「课前备课 API KEY」改为「AI API KEY」。
- AI 客户端代理策略：默认直连，仅当 `.env` 设 `AI_PROXY` 时才走代理。
- **学科生成课件改用 KB 精确锚定的 v3 引擎**：`src/prep/views.py` 删除「教案 HTML → 纯文本 → 重切页 → 涂鸦风重渲染」的覆盖逻辑（该路径会把 KB 驱动的好课件拆成重复页/乱标题/生字刷屏，用户实测《拍手歌》即被这套覆盖逻辑毁掉）。学科生成的最终课件 = orchestrator 用 KB 精确锚定产出的 v3 课件（`course_*.html`），结构清晰、锚定课文原文。
- **KB 检索改精确锚定**：`systems/lesson-courseware/courseware_engine/kb.py` 的 `retrieve_kb` 废掉原「topic 互含 +100 / subject +10 / grade +5」模糊打分（曾导致五年级《分数的初步认识》错配三年级、二年级《秋天》错配三年级《秋天的雨》），改为「subject 一致 + 年级段一致 + topic 精确/包含兜底」。新增 `_grade_core()` 把「六年级（小学第三学段）/六年级上/六年级/6年级」统一抽取为「六年级」中文数字核心再比较，避免课件端 `form_cw.grade` 带学段后缀时被全过滤。
- **课标/教材标注文案**：`k12_generate.py` 的 `standard_code` 由 `课标2022·…` 改为 `课标2022年版·…`，`meta` 增加「教材：人教版2024修订」，system prompt 补「教材依据人教版2024修订版教科书」。课标（2022 年版国标）与教材（KB 内 2024 修订版教科书）分层标注，避免歧义。
- **注册验证码 dev 模式**：`src/auth/routes.py` 与 `templates/auth/register_code.html` 回滚「页面上显示 dev 验证码」的设计，恢复为「打印到服务端控制台」——避免 dev 验证码被前端可见泄露。

### Fixed
- 用户自定义 API KEY 对课评生成不生效（此前仅课前备课使用）。
- 课前备课内容生成丢失多行代码块、缩进、语言标记污染 bullet 等问题。
- 请假状态下编辑器「已完成」计数未包含 leave。
- **学科生成"张冠李戴"**：KB 检索改为精确锚定后，五年级《分数的初步认识》不再错配三年级；二年级《秋天》不再错配三年级《秋天的雨》。975 条 KB（565 单课题 + 410 bundle）全量精确可达、零异常。
- **学科生成"KB 未命中"误报**：课件端 `form_cw.grade` 来自教案 `shared`（如「六年级（小学第三学段）」），严格年级过滤会判不出而报 `RuntimeError: KB 未命中该课题`；`_grade_core` 抽取年级核心比较后修复。
- **拍手歌课件重复页/内容乱/生字刷屏**：根因是 `src/prep/views.py` 把 orchestrator 产出的 KB 驱动 v3 好课件又拿去 lesson.html→纯文本→重切页→涂鸦风重渲染并覆盖最终课件；删除该覆盖逻辑后，KB 链路产出 16 页结构清晰、锚定课文原文的正确 v3 课件。

### Security
- API 密钥从明文存储改为环境变量 / 用户数据库字段方式。
- 注册页 dev 验证码不再通过模板渲染到 HTML，仅打印服务端日志。

- 添加 .gitignore 保护 .env 文件与上传目录。
- CSRF 全局开启，reviews 纯 JSON API 蓝图豁免并由 `@login_required` 鉴权。

## [0.1.0] - 2026-03-25

### Added
- 项目初始版本
- 基础 Flask Web 应用
- 学生档案管理功能
- 课程文件管理
