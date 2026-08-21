# differentiation.json Schema Reference

加载时机：仅在编写 `differentiation.json` 且不确定 block types 或字段结构时读取。如果已有 `example_differentiation.json` 作为参考，通常不需要加载本文件。

## 顶层结构

```yaml
theme: {primary: "#…"}
shared:
  subject, grade, standard_code, standard_text    (required identity)
  duration?
  <any key>: string | block | block[] | {teacher: …, student: …, stimulus?: block[]}
documents[]:
  {id: teacher_plan|worksheet_group_a|b|c,
   audience: teacher|student, eyebrow, title, meta,
   sections[]: {heading, blocks[]}}
```

## Block types

| Type | Format | Use |
|------|--------|-----|
| `from_shared` | `{type: from_shared, key, label?}` | 引用 shared 中的内容 |
| `labeled` | `{type: labeled, label, text}` | 带标签的文本段 |
| `paragraph` | `{type: paragraph, text}` | 纯段落 |
| `callout` | `{type: callout, kind: special\|student-task\|teacher-note\|student-note, label, text}` | 突出显示块 |
| `h2`/`h3` | `{type: h2, text}` | 子标题 |
| `list` | `{type: list, label?, ordered?, items[]}` | 有序或无序列表 |
| `table` | `{type: data_table, headers[]?, rows[[]], empty_row_height_pt?}` | 数据表/填空表 |
| `fill_table` | `{type: fill_table, headers[], blank_rows, row_height_pt?}` | 全空表（学生填） |
| `number_line` | `{type: number_line, min, max, ticks?, marks[]?}` | 数轴 |
| `workspace` | `{type: workspace, size: small\|med\|large, height_pt?}` | 学生书写空间 |
| `group` | `{type: group, blocks[]}` | 组合块 |
| `columns` | `{type: columns, left[], right[]}` | 两栏布局 |
| `page_break` | `{type: page_break}` | 分页符 |
| `phase_header` | `{type: phase_header, name, minutes}` | 科学课阶段头 |
| `source_card` | `{type: source_card, title, author?, date?, origin?, excerpt}` | 来源卡片 |
| `cards` | `{type: cards, items[{title, text}]}` | 2-4 项并列卡片 |
| `checklist` | `{type: checklist, label?, items[]}` | 检查清单 |
| `fill_in` | `{type: fill_in, label?, size: short\|med\|long}` | 填空行 |

## 规则

- NEVER 在 `text` 字段中使用 Markdown 管道表、框线字符、ASCII 艺术、子弹字符(•, -)
- `workspace` 自动按年级设置大小；`height_pt` 仅在需要更多空间时设置
- 空表格行自动获得与年级匹配的最小行高
- `shared` 中的 key 可被任意文档通过 `from_shared` 引用
- 如果内容是 faceted（教师版和学生版不同），使用 `{teacher: …, student: …}` 格式
