# OJ 数据 API 使用说明

> 本文档面向所有老师，介绍如何通过 Claude Code 快速获取学生的 OJ 做题数据（含源代码和错误详情）。

## 一句话总结

在 Claude Code 对话中输入 **"获取 CSP05-02 的OJ数据"**，系统自动调 API 拉取、分析、保存结果。

---

## 前提条件

1. 项目根目录有 `.env` 文件，包含 OJ 登录凭据：

```ini
OJ_BASE_URL=https://oj.example.com
OJ_USERNAME=你的用户名
OJ_PASSWORD=你的密码
```

2. OJ 插件 `HydroOJ-Course-Keli365` 已部署（目前已在 oj.example.com 上运行）

---

## 使用方式

### 方式1：直接对话（推荐）

在 Claude Code 中输入：

```
获取 CSP05-02 的OJ数据
```

系统自动完成：登录 OJ → 找到课程 → 找到课次 → 拉取全部学生数据 → 保存分析结果。

### 方式2：指定班级筛选

```
获取 CSP05-02 的OJ数据，只看 CSP05克力周六1600 班的
```

### 方式3：不指定课次，列出所有可选课次

```
获取 CSP05 的OJ数据
```

系统会先展示 CSP05 下所有课次列表，你选择要分析哪一个。

---

## 能获取到什么数据

对**每个学生**在**每道题**上，API 返回：

| 数据 | 说明 | 举例 |
|------|------|------|
| 完成状态 | AC=通过，WA=答案错误，RE=运行错误等 | AC |
| 分数 | 0-100 分 | 100 |
| 提交次数 | 该学生这道题总共提交了几次 | 3 |
| 源代码 | 学生提交的完整代码 | `#include <bits/stdc++.h>...` |
| 编译错误 | 代码编译失败时的错误信息 | `expected ';' after expression` |
| 测试点详情 | 每个测试点的通过/失败情况 | 测试点1: AC, 测试点2: WA |
| 提交历史 | 每次提交的变化轨迹 | 第1次WA→第2次WA→第3次AC |

### 作业包分类

数据按三个作业包分别统计：

| 作业包 | 含义 | 常见题量 |
|--------|------|----------|
| 课堂练习 | 课上完成的题 | 3-5 题 |
| 课后作业 | 课后做的题 | 2-3 题 |
| 拓展练习 | 选做的挑战题 | 5-7 题 |

---

## 数据保存在哪里

```
.claude/memory/oj/analysis/
├── CSP05-02_student_analysis.json    ← 原始数据（API 返回的完整 JSON）
└── CSP05-02_analysis.md              ← AI 分析报告（可选）
```

**重要**：数据保存后，后续生成课评时会自动读取，不需要重复获取。

---

## 手动调 API（给开发者参考）

如果不用 Claude Code，也可以直接用 Python 调 API：

```python
import httpx
from pathlib import Path

# 1. 读取凭据
env = {}
for line in Path('.env').read_text().split('\n'):
    if '=' in line and not line.startswith('#'):
        k, v = line.split('=', 1)
        env[k] = v

# 2. 登录
client = httpx.Client(base_url=env['OJ_BASE_URL'], follow_redirects=True)
client.post('/login', json={"uname": env['OJ_USERNAME'], "password": env['OJ_PASSWORD']})

# 3. 获取课程列表
r = client.get('/course/api/list')
print(r.json())

# 4. 获取课程详情（替换 {cid} 为实际课程 ID）
r = client.get(f'/course/api/detail/{cid}')
print(r.json())

# 5. 获取章节分析（替换 {cid} 和 {csid}）
r = client.get(f'/course/api/analysis/{cid}/{csid}?withHistory=true')
print(r.json())
```

### 三个 API 端点

| 端点 | 用途 | 说明 |
|------|------|------|
| `GET /course/api/list` | 课程列表 | 返回所有课程的标题、ID、人数 |
| `GET /course/api/detail/{课程ID}` | 课程详情 | 返回所有课次的标题和 ID |
| `GET /course/api/analysis/{课程ID}/{课次ID}` | 学生分析 | 返回每个学生每道题的完整数据 |

### 可选参数

| 参数 | 默认值 | 说明 |
|------|--------|------|
| `withCode` | true | 设为 false 跳过源代码，只返回状态（速度快） |
| `withHistory` | false | 设为 true 获取全部提交历史（含每次提交的代码和错误） |

---

## 常见问题

**Q：课程代码怎么填？**
A：就是 OJ 上的课程编号，比如 CSP05-02、CSP06-05。跟大纲编号可能不一样，以 OJ 实际的为准。

**Q：提示"未找到课程"怎么办？**
A：可能是阶段名不匹配。试试只说"获取 OJ 数据"，系统会列出所有可用课程让你选。

**Q：数据太多，等很久怎么办？**
A：如果班级学生多（15人以上），获取源代码会比较慢。可以加 `withCode=false` 只获取状态，速度快很多。

**Q：数据多久更新一次？**
A：每次调用 API 都是实时获取最新数据。但课评生成时会优先使用已保存的 JSON，避免重复请求。需要刷新时重新获取即可。
