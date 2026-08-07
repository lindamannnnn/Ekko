# Changelog

所有重要的变更都将记录在此文件中。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)，
并且本项目遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [1.0.0] - 2026-08-07

### Added
- 初始项目架构搭建
- 支持 Kitten、C++、AI 三种课程类型的课评生成
- Web界面简化设计（选择课程→输入表现→生成课评→保存）
- 学生档案使用 Markdown + YAML 格式存储
- AI 课评生成（Kimi API）
- 30名学生档案（AICODE01, AICODE03, CSP01, CSP04, K2, K4）
- 122个课程文件（C++ 26 + Kitten 96）
- 课评卡片图片（家长群分享图）：4 套学科模板（skill/academic/work/general），手账温暖风设计，一键 html2canvas 导出
- 卡片 AI 亮点标签：老师未选正向标签时，AI 在生成课评时顺手产出 2-3 个短语亮点，卡片优先采用；缺失时规则提取兜底
- 新手引导 tour：首次使用分步引导（创建班级→加学生→…），POST 提交流程也能保留引导链
- 班级创建健壮性：同名班级预拦截 + IntegrityError 兜底，避免 500

### Changed
- API 从 Claude 迁移至 Kimi (Moonshot)
- API 密钥管理改为环境变量 + .env 文件方式
- 课评直接保存到学生档案，不再使用 output/ 目录
- 清理重复课程文件（CSP04 删除12个重复文件）
- 登录后首屏改为班级列表页（「大厅」= 班级列表 `/classes`），移除欢迎首页
- 班级创建失败时可回显已填表单并给出友好报错
- 课评生成 Prompt 补充正向行为硬约束（减少转折句稀释正向标签）

### Removed
- output/ 目录（课评直接保存到学生档案）
- Python 缓存文件 (__pycache__)
- 测试文件 (debug_prompt.py, test_*.py)
- 临时数据文件 (student_answers.json, web.log)
- 重复的课程文件
- templates/index.html（欢迎首页，登录后直接进班级列表）

### Security
- API 密钥从明文存储改为环境变量方式
- 添加 .gitignore 保护 .env 文件
- config.yaml 使用占位符 ${KIMI_API_KEY}

## [0.1.0] - 2026-03-25

### Added
- 项目初始版本
- 基础 Flask Web 应用
- 学生档案管理功能
- 课程文件管理
