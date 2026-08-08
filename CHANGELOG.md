# Changelog

所有重要的变更都将记录在此文件中。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)，
并且本项目遵循 [语义化版本](https://semver.org/lang/zh-CN/)。

## [Unreleased]

### Added
- 初始项目架构搭建
- 支持 Kitten、C++、AI 三种课程类型的课评生成
- Web界面简化设计（选择课程→输入表现→生成课评→保存）
- 学生档案使用 Markdown + YAML 格式存储
- AI 课评生成（Kimi API）
- 30名学生档案（AICODE01, AICODE03, CSP01, CSP04, K2, K4）
- 122个课程文件（C++ 26 + Kitten 96）

### Changed
- API 从 Claude 迁移至 Kimi (Moonshot)
- API 密钥管理改为环境变量 + .env 文件方式
- 课评直接保存到学生档案，不再使用 output/ 目录
- 清理重复课程文件（CSP04 删除12个重复文件）

### Removed
- output/ 目录（课评直接保存到学生档案）
- Python 缓存文件 (__pycache__)
- 测试文件 (debug_prompt.py, test_*.py)
- 临时数据文件 (student_answers.json, web.log)
- 重复的课程文件

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
