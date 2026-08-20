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

### Changed
- 请假课评行为：点击「请假」后直接写入 `content = "请假"` 且不调用 AI；再次生成仍返回「请假」。
- 用户 API KEY 文案统一：账号页与课前备课页从「课前备课 API KEY」改为「AI API KEY」。
- AI 客户端代理策略：默认直连，仅当 `.env` 设 `AI_PROXY` 时才走代理。

### Fixed
- 用户自定义 API KEY 对课评生成不生效（此前仅课前备课使用）。
- 课前备课内容生成丢失多行代码块、缩进、语言标记污染 bullet 等问题。
- 请假状态下编辑器「已完成」计数未包含 leave。

### Security
- API 密钥从明文存储改为环境变量 / 用户数据库字段方式。
- 添加 .gitignore 保护 .env 文件与上传目录。
- CSRF 全局开启，reviews 纯 JSON API 蓝图豁免并由 `@login_required` 鉴权。

## [0.1.0] - 2026-03-25

### Added
- 项目初始版本
- 基础 Flask Web 应用
- 学生档案管理功能
- 课程文件管理
