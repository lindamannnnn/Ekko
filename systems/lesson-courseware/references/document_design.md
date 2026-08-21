# 文档设计规范

加载时机：第五步编写 `lesson.json` 前读取（仅当不熟悉 block types 或 JSON 结构时）。

## JSON 架构

- `shared` 是内容注册表——课时身份 + 跨页内容（问题、史料、词汇、课堂小测等）
- key 的值类型：字符串 | block | block[] | `{teacher, student, stimulus}`（分面对象）
  - 学生文档只渲染 `student` 分面；`null` = 口头任务
  - 教师文档渲染 `teacher` 分面，然后用"学生看到"标签展示 `student` 分面
- `documents[]` 每个条目：`{id, audience, eyebrow, title, sections[{heading, blocks[]}]}`
  - 可选：`cover`（封面信息）、`color`（首行底色）、`header` / `footer`
- 页面间共享内容用 `{"type": "from_shared", "key": …}` 引用
- 同一字段出现多次的内容先注册到 shared 再跨文档引用

### 必需文档

| id | audience | 说明 |
|----|----------|------|
| `lesson_plan` | 教师 | 教案（学科环节结构 + 板书 + 常见错误 + 观察点） |
| `observation_template` | 教师 | 听课记录表（核心素养观测点 + 典型错例 + 课堂小测分类） |
| `student_materials` | 学生 | 学习任务单（仅当学生有印刷页时） |

## 密度规则

- `paragraph` 或 `labeled` 块最多 3 句。更长 → 拆分为子弹列表或 data_table
- 子弹列表每项 ≤ ~15 字，不用分号连接从句
- 平行内容（同行异层/同层异组）用 `data_table` 块，不用三个段落
- `callout` 仅用于教师不可错过的关键提示（每页面 ≤ 2 个）
- 课标原文全文只引用一次，其余用代码+要旨（≤ 10 字）
- 连续 prose 超过半页时必须重构（拆表/拆子弹/分节）

## 常用 Block Types

| type | 用途 | 关键字段 |
|------|------|----------|
| `paragraph` | 正文段 | `text` |
| `labeled` | 标签+正文 | `label`, `text` |
| `callout` | 高亮提示 | `kind`, `text` |
| `h2` / `h3` | 小节标题 | `text` |
| `list` | 子弹列表 | `items[]` |
| `data_table` | 表格数据 | `headers[]`, `rows[][]` |
| `phase_header` | 课时阶段标题 | `name`, `minutes` |
| `from_shared` | 跨页引用 | `key` |
| `page_break` | 分页 | — |
| `group` | 块组（横向排列） | `blocks[]` |
| `columns` | 双栏 | `left[]`, `right[]` |
| `workspace` | 书写空间 | `height_pt` |
| `cards` | 卡片式展示 | `items[]` |
| `fill_table` | 填空表格 | `headers[]`, `rows[][]` |
| `number_line` | 数轴 | `min`, `max`, `marks[]` |
| `source_card` | 资料卡片 | `text` |
| `answer_box` | 答案框 | `label` |

## 一致性要求

- 材料清单与教学环节精确一致：每件被使用的物品都在清单里
- 学生任务的措辞在教案"学生看到"处和练习单上**完全相同**
- 答案空间与问题匹配：行数对应答案数，每格有明确提示
- 修改 shared 后自动传播；修改单文档后在该文档 sections 中完成

## 内置工具限制

- 渲染器无法绘制图片——教师展示内容写在教案 Materials 中
- 渲染器无算术能力——验证每道计算题（答案+示例+定量链条）
- 渲染器按 `audience` 过滤：学生页只输出 `student` 分面；教师页输出全部
