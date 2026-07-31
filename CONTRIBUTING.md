# 贡献指南

感谢您对课评自动生成系统的关注！本指南将帮助您了解如何参与项目贡献。

## 开发环境设置

### 1. 克隆仓库

```bash
git clone <repository-url>
cd class-review-system
```

### 2. 创建虚拟环境

```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# 或
venv\Scripts\activate  # Windows
```

### 3. 安装依赖

```bash
pip install -r requirements.txt
```

### 4. 配置环境变量

创建 `.env` 文件：

```bash
KIMI_API_KEY=your_api_key_here
```

### 5. 启动开发服务器

```bash
python run.py
```

访问 http://127.0.0.1:5000

## 项目结构

```
class-review-system/
├── data/               # 数据文件
│   ├── courses/        # 课程文件
│   └── students/       # 学生档案
├── src/                # 源代码
│   ├── ai/            # AI生成逻辑
│   └── web/           # Web应用
├── tools/             # 工具脚本
│   ├── core/          # 核心工具
│   └── archive/       # 归档脚本
├── references/        # 参考资料
├── rules/             # 课评规则
└── skills/            # 技能定义
```

## 代码规范

### Python 代码风格

- 遵循 PEP 8 规范
- 使用 4 空格缩进
- 行长度限制 100 字符
- 函数和类添加文档字符串

### 文件命名

- Python 文件：小写字母，下划线分隔 (`review_generator.py`)
- Markdown 文件：大驼峰 (`README.md`)
- 目录：小写字母 (`tools/`, `data/`)

### 提交信息规范

使用以下格式：

```
<type>(<scope>): <subject>

<body>

<footer>
```

类型：
- `feat`: 新功能
- `fix`: 修复bug
- `docs`: 文档更新
- `style`: 代码格式调整
- `refactor`: 重构
- `test`: 测试相关
- `chore`: 构建/工具相关

示例：
```
feat(review): add support for Kitten course generation

- Add Kitten-specific prompt templates
- Update course file parser for Kitten format
- Add unit tests for new functionality
```

## 数据文件规范

### 学生档案格式

```markdown
---
name: 学生姓名
class: 班级
gender: 性别
age: 年龄
---

# 学生档案

## 基本信息
...

# 历史评价

## 2026-04-10
...
```

### 课程文件格式

```markdown
# 课程名称

## 教学目标
1. 目标一
2. 目标二
...
```

## 测试

运行测试（如果有）：

```bash
python -m pytest tests/
```

## 文档

- `README.md` - 项目概览和快速开始
- `CLAUDE.md` - 项目结构索引
- `CHANGELOG.md` - 版本历史
- `docs/` - 详细文档（如果有）

## 问题反馈

如果遇到问题，请：

1. 检查是否已安装所有依赖
2. 确认环境变量配置正确
3. 查看 `web.log` 日志文件
4. 提交 Issue 并附上错误信息

## 许可证

本项目采用 MIT 许可证 - 详见 [LICENSE](LICENSE) 文件

---

感谢您对课评自动生成系统的贡献！
