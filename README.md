# 课评自动生成系统

一个帮助编程老师自动生成学生课评的工具系统。

## 功能特点

- 📊 **课堂表现录入** - 通过Web界面方便地录入每节课的学生表现
- 🤖 **AI智能生成** - 基于课堂表现、课程内容和参考资料自动生成课评
- 📚 **专业参考资料** - 内置儿童心理发展、课程常见困难等参考资料
- 📷 **配套照片** - 每份课评可配套一张照片
- 🌐 **Web界面** - 可视化操作，无需编程知识

## 目录结构

```
class-review-system/
├── data/
│   ├── courses/          # 课程内容（Markdown格式）
│   ├── students/         # 学生数据
│   │   └── 班级名/
│   │       └── 学生名/
│   │           ├── info.md           # 学生基本信息
│   │           ├── performance/      # 课堂表现记录（JSON）
│   │           │   └── 2024-03-08.json
│   │           └── reviews/          # 历史课评参考
│   │               └── 2024-03-01.md
│   └── templates/        # 课评模板
├── references/           # 参考资料库
│   ├── age-psychology/   # 年龄段心理特点
│   ├── course-difficulties/  # 课程常见困难
│   ├── learning-stages/  # 学习阶段特征
│   └── encouragement/    # 鼓励话术
├── output/               # 生成的课评
│   └── 班级名/
│       └── 学生名/
│           ├── 2024-03-08.md
│           └── 2024-03-08.jpg
├── src/
│   ├── ai/               # AI生成模块
│   └── web/              # Web界面
├── config.yaml           # 配置文件
├── requirements.txt      # Python依赖
├── run.py               # 启动脚本
└── README.md
```

## 快速开始

### 1. 安装依赖

```bash
pip install -r requirements.txt
```

### 2. 配置API密钥（可选，使用AI增强功能）

编辑 `config.yaml`，设置Claude API密钥：

```yaml
ai:
  api_key: "your-api-key-here"
```

### 3. 准备课程内容

在 `data/courses/` 目录下创建课程文件，例如：

```markdown
# Python循环结构

## 教学目标
- 理解for循环和while循环的区别
- 掌握range()函数的使用
- 能够编写简单的循环程序

## 重点难点
- 循环变量的变化规律
- 死循环的避免
```

### 4. 创建班级和学生

```bash
# 创建班级文件夹
mkdir -p "data/students/Python基础班/张三"

# 创建学生信息文件
cat > "data/students/Python基础班/张三/info.md" << 'EOF'
---
name: 张三
age: 10
grade: 四年级
enrollment_date: 2024-01-15
personality: 活泼外向
---

# 学生档案

## 家长联系方式
- 妈妈: 138xxxx1234

## 学习特点
- 喜欢通过实践学习
- 对视觉化内容吸收更好
EOF
```

### 5. 启动系统

```bash
python run.py
```

然后访问 http://127.0.0.1:5000

## 使用流程

1. **选择班级** - 首页显示所有班级
2. **录入表现** - 点击"录入表现"按钮，填写学生本节课的表现数据
3. **生成课评** - 在学生详情页点击"生成课评"
4. **上传照片** - 为课评配套上传课堂照片
5. **查看结果** - 生成的课评保存在 `output/` 目录下

## 课堂表现数据格式

```json
{
  "date": "2024-03-08",
  "course": "循环结构",
  "performance": {
    "attendance": "准时",
    "focus": 4,
    "mastery": 4,
    "completion": 5,
    "interaction": 3,
    "notes": "对for循环理解很快"
  },
  "homework": {
    "submitted": true,
    "quality": 4
  },
  "highlights": ["主动帮助同学", "提出了好问题"]
}
```

## 自定义参考资料

你可以在 `references/` 目录下添加自己的参考资料：

- `age-psychology/` - 不同年龄段学生的心理特点
- `course-difficulties/` - 不同课程的常见困难
- `encouragement/` - 针对不同性格学生的鼓励话术

## 技术栈

- **后端**: Python + Flask
- **前端**: HTML + CSS + JavaScript
- **AI**: Claude API（可选）

## 配置说明

编辑 `config.yaml` 可自定义：

- 文件路径
- AI模型参数
- Web服务端口
- 参考资料匹配规则

## 许可证

MIT License
