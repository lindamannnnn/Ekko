# 课评系统 · 端到端自审报告

| 项 | 内容 |
|---|---|
| 日期 | 2026-07-31 |
| 环境 | Flask test_client（`TESTING=True`、`WTF_CSRF_ENABLED=False`），SQLite，智谱 GLM-4-Flash 真实 API |
| 自审轮次 | 11 轮（R1–R11），跑 3 个完整周期 |
| 覆盖 | 注册/登录/鉴权、建班/类型、加学生、课件解析、AI 生成+脱敏、编辑/确认/请假、横向去重、阶段总结、导出/卡片/档案、多租户隔离 |
| 结论 | **首轮 4 high / 2 medium / 3 low → 末轮 0 / 0 / 0，全部问题已修复并回归通过** |

---

## 一、自审方法

用 `tools/audit.py` 通过 Flask `test_client(use_cookies=True)` 模拟一位真实老师（用户 A）从注册到归档的完整操作链路，并额外引入用户 B 做越权隔离测试。所有 AI 生成/阶段总结均调用真实智谱 GLM-4-Flash，以暴露真实链路问题（脱敏、文本抽取、异常分支等）。每轮对返回状态码、落库数据、文本长度、跨用户访问等进行断言，命中即记为一条 finding（按 high/medium/low 分级）。

> 说明：自审脚本本身也发现并修正了 2 处测试夹具问题（文件上传元组顺序、二进制响应按 UTF-8 解码导致的误报），这些属于测试工具缺陷，已在「修复清单」中标注。

---

## 二、三轮迭代对比

| 周期 | high | medium | low | 备注 |
|---|---|---|---|---|
| 第 1 轮（初跑） | 4 | 2 | 3 | 导出/档案崩溃、脱敏失效、类型未校验、重名/空名单/空确认 |
| 第 2 轮（修 4 项后） | 0 | 1 | 3 | 导出与脱敏已修复；类型未校验、重名、空名单、空确认仍待修 |
| **第 3 轮（全修后）** | **0** | **0** | **0** | **全链路 11 轮通过** |

---

## 三、发现的问题与修复（按严重度）

### 🔴 High

#### H1. 学生档案页崩溃（`UndefinedError: 'Review' object has no attribute 'lesson'`）
- **现象**：`GET /students/<id>` 返回 500；模板 `archive.html` 访问 `r.lesson.title`，但 `Review` 模型只有 `lesson_id` 字段，无 `lesson` 关系。
- **根因**：模板依赖一个不存在的 ORM 关系。
- **修复**：在 `models/lesson.py` 的 `Review` 上新增
  ```python
  lesson = db.relationship("Lesson", foreign_keys=[lesson_id], lazy="joined")
  ```
- **验证**：第 2 轮起 `student archive -> 200`。

#### H2. 导出 PDF 崩溃（`AttributeError: 'NoneType' object has no attribute 'content'`）
- **现象**：`GET /export-pdf/<class_id>` 500；当班级里有「已报名但还没有任何课评」的学生时，`rev_map.get(s.id)` 为 `None`，仍对其取 `.content`。
- **根因**：导出循环未对缺失课评的学员做空值保护。
- **修复**（`reports/routes.py`）：
  ```python
  r = rev_map.get(s.id)
  content = (r.content or '（待生成）') if r else '（待生成）'
  ```
- **验证**：第 2 轮起 `export-pdf -> 200`，字节数正常。

#### H3. 脱敏失效：AI 原稿含未成年人真实姓名
- **现象**：R6 生成后，`ai_raw` 中出现 `小明` 等真实姓名（应为 `{{STU}}` 占位符）。
- **根因**：`reviews/routes.py` 在组装 prompt 时，仅对学生姓名/昵称/同学名做了脱敏，**课件正文（`cw_text`）未脱敏**就直接传给大模型；而测试课件里恰好写了「小明主动举手回答问题」，模型把真实姓名原样回写。
- **修复**：在生成前对课件文本脱敏（与历史稿、风格样本一致）：
  ```python
  red = Redactor(student.name, student.preferred_name)
  cw_text = red.redact(cw_text) if cw_text else ""
  ```
  同样作用于去重重写函数 `_regenerate_with_reference`。
- **验证**：第 2 轮起 R6 不再出现「脱敏失效」finding（high 计数归零）。

> 备注：`export-xlsx` 在第 1 轮被记为 RAISED，但**根因是测试夹具误报**——xlsx 是二进制响应，自审脚本错误地用 `get_data(as_text=True)` 解码导致 `UnicodeDecodeError`。应用本身正常，第 2 轮修正夹具后 `export-xlsx -> 200`。

### 🟡 Medium

#### M1. 班级类型 `type_code` 未校验
- **现象**：提交 `type_code=nonexistent_type` 也能建班成功，`preset=None`，后续 AI 生成退化为通用模板、UI 无维度/标签。
- **修复**（`classes/routes.py` 的 `new()`）：建班前校验类型码是否存在于 `class_type_presets`：
  ```python
  if ClassTypePreset.query.filter_by(code=type_code).first() is None:
      flash("班级类型无效，请从列表中选择", "error")
      return render_template("classes/new.html", presets=presets)
  ```
- **验证**：第 3 轮非法类型不再建班。

### 🟢 Low

#### L1. 允许重名学生
- **现象**：同一用户下重复添加同名学员会建出多条 `Student` 记录，且会重复生成课评。
- **修复**（`add_students`）：复用同名已存在学员，并对「学员×班级」报名做去重，避免重复 `Enrollment`。
- **验证**：第 3 轮重复添加 `小明` 不再产生第 2 条学员记录。

#### L2. 空名单误加学生（测试夹具误报）
- **现象**：自审脚本第 1 轮报「提交空白名单仍新增学生」。
- **根因**：**应用本身已正确处理**（按 `n.strip()` 过滤空行），是测试脚本用了一个陈旧的 `before` 计数比对导致误报。
- **修复**：测试脚本改为在提交前实时取一次计数再比对。应用无需改动。
- **验证**：第 3 轮不再误报。

#### L3. 允许确认空课评
- **现象**：`content` 为空仍可 `confirm` 成 `confirmed`，家长端可能收到空白反馈。
- **修复**（`reviews/routes.py` 的 `confirm()`）：
  ```python
  if not (review.content or "").strip():
      return jsonify({"ok": False, "error": "课评内容为空，无法确认"}), 400
  ```
- **验证**：第 3 轮空内容确认被拒绝（status 不变为 confirmed）。

---

## 四、完整 11 轮结果明细（第 3 轮 / 末轮）

| 轮 | 场景 | 关键断言 | 结果 |
|---|---|---|---|
| R1 | 注册 + 校验 | 合法注册落库；弱密码(123)被拦；重复邮箱 302 | ✅ |
| R2 | 登录 + 未登录保护 | 未登录跳 302；合法登录 302；登出后错误密码 200 | ✅ |
| R3 | 建班 + 类型校验 | 合法 coding 建班；空名/非法 type_code 被拒 | ✅ |
| R4 | 加学生 + 重名 | 加 3 人成功；重名复用不新增；空白名单不新增 | ✅ |
| R5 | 课件解析 | txt 抽取 80 字；.exe 被拒（不挂课件）；粘贴文本可用 | ✅ |
| R6 | AI 生成 + 脱敏 | 4 份生成 ok，字数 207–331；`ai_raw` 无真实姓名 | ✅ |
| R7 | 编辑/确认/请假 | 保存生效、确认生效、空确认被拒、还原/请假 200 | ✅ |
| R8 | 横向去重 | dedup 200，无异常 | ✅ |
| R9 | 阶段总结 | 真实 API 产出 730 字；空素材 200 不崩 | ✅ |
| R10 | 导出/卡片/档案 | xlsx 200(5.6KB)、pdf 200(1.8KB)、卡片 200、档案 200、归档 302 | ✅ |
| R11 | 多租户隔离 | 用户 B 访问 A 的班级/课评均 404 | ✅ |

---

## 五、遗留风险与后续建议

1. **跨班姓名残留（极小概率）**：脱敏器仅认知「当前学员 + 本班同学」。`history/style` 样本与课件若提到**非本班**的第三方学员姓名，当前不会被替换为占位符，理论上仍可能经大模型回写。建议后续把「所有已知学员姓名」注入 Redactor 的 peer 列表（或全局姓名表）做兜底替换。
2. **重名防护停留在应用层**：目前靠 `add_students` 逻辑去重，未在库表加 `UNIQUE(user_id, name)` 约束。高并发或未来批量导入时仍可能穿透，建议补唯一约束迁移。
3. **导出性能**：大班级（数百学员）的 PDF/Excel 为同步生成，建议后续改为异步任务 + 进度提示。
4. **测试覆盖**：自审脚本已覆盖核心链路，建议沉淀为 CI 冒烟用例（mock LLM 密钥即可跑，无需真实调用）。

---

## 六、修复代码清单

| 文件 | 改动 |
|---|---|
| `src/models/lesson.py` | `Review` 新增 `lesson` ORM 关系（修复档案页） |
| `src/reviews/routes.py` | 生成前对 `cw_text` 脱敏（修复 H3）；`confirm()` 拦截空内容（修复 L3） |
| `src/reports/routes.py` | `export_pdf` 对缺失课评做空值保护（修复 H2） |
| `src/classes/routes.py` | `new()` 校验 `type_code`（修复 M1）；`add_students` 复用学员 + 报名去重（修复 L1） |
| `tools/audit.py` | `req()` 对二进制响应不再按 UTF-8 解码（修正 xlsx 误报）；R4 空名单计数修正（修正 L2 误报） |

---

*自审脚本：`tools/audit.py` · 机器可读结果：`tools/audit_findings.json`*
