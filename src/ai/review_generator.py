#!/usr/bin/env python3
"""
课评生成器 - 按照技能流程执行
"""
import os
import re
import yaml
from pathlib import Path
from datetime import datetime

from .review_scorer import strip_markdown, evaluate_review
from oj.review_draft_generator import ReviewDraftGenerator


class ReviewGenerator:
    """课评生成器"""

    def __init__(self, config_path='config.yaml'):
        """初始化生成器"""
        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = yaml.safe_load(f)

    def _get_preferred_name(self, student_name: str) -> str:
        """生成去姓称呼：2字姓名保留原名，3字及以上去掉第一个字。"""
        if not student_name:
            return student_name
        if len(student_name) <= 2:
            return student_name
        return student_name[1:]

    def load_student_info(self, class_name: str, student_name: str) -> dict:
        """从学生档案加载学生信息"""
        student_file = Path(self.config['paths']['students']) / class_name / student_name / "profile.md"

        if not student_file.exists():
            return {}

        with open(student_file, 'r', encoding='utf-8') as f:
            content = f.read()

        # 解析 YAML frontmatter
        info = {}
        if content.startswith('---'):
            parts = content.split('---', 2)
            if len(parts) >= 2:
                try:
                    info = yaml.safe_load(parts[1])
                except:
                    pass

        return info

    def load_performance(self, class_name: str, student_name: str, date: str) -> dict:
        """加载课堂表现数据"""
        performance_file = Path(self.config['paths']['students']) / class_name / student_name / "performance" / f"{date}.json"

        if not performance_file.exists():
            return {}

        with open(performance_file, 'r', encoding='utf-8') as f:
            import json
            return json.load(f)

    def load_course_content(self, course_path: str) -> str:
        """加载课程内容 - 优先提取###课程内容，否则提取课程目标"""
        if not course_path:
            return ""

        # 支持相对路径和绝对路径
        if course_path.startswith('./') or course_path.startswith('../'):
            course_file = Path(course_path)
        else:
            course_file = Path(self.config['paths']['courses']) / course_path

        if not course_file.exists():
            return ""

        with open(course_file, 'r', encoding='utf-8') as f:
            content = f.read()

        import re

        # 1. 优先匹配 ### 课程内容
        match = re.search(r'### 课程内容\s*\n(.*?)(?=\n### |\Z)', content, re.DOTALL)
        if match:
            return match.group(1).strip()

        # 2. 尝试匹配 ## 1. 课程目标 / ### 1. 课程目标 / ## 课程目标 等
        # 支持标题后面带 emoji 或空格，如 "## 1. 课程目标 🎯"
        objective_patterns = [
            r'#{1,3}\s*1\.\s*课程目标[^\n]*\n(.*?)(?=\n#{1,3}\s|\Z)',
            r'#{1,3}\s*课程目标[^\n]*\n(.*?)(?=\n#{1,3}\s|\Z)',
            r'#{1,3}\s*教学目标[^\n]*\n(.*?)(?=\n#{1,3}\s|\Z)',
        ]
        for pattern in objective_patterns:
            match = re.search(pattern, content, re.DOTALL)
            if match:
                extracted = match.group(1).strip()
                if len(extracted) > 30:
                    return extracted

        # 3. 兜底：返回前 2000 字，避免把整个教案塞进课评
        return content[:2000].strip()

    def _load_teacher_style_examples(self, course_type: str = 'kitten') -> list:
        """加载老师风格示例"""
        try:
            style_map = {
                'kitten': 'KITTEN.md',
                'k2': 'KITTEN.md',
                'k4': 'KITTEN.md',
                'c++': 'C++.md',
                'cpp': 'C++.md',
                'csp': 'C++.md',
                'ai': 'AI.md',
                'aicode': 'AI.md',
            }
            style_file = style_map.get(course_type.lower(), 'KITTEN.md')
            style_path = Path(self.config['paths']['references']) / 'teacher-style' / style_file

            if not style_path.exists():
                print(f"DEBUG: 风格文件不存在: {style_path}")
                return []

            with open(style_path, 'r', encoding='utf-8') as f:
                content = f.read()

            # 按 "## 课评示例" 分割
            examples = []
            parts = content.split('## 课评示例')

            for part in parts[1:]:  # 跳过第一个（前面的内容）
                # 提取示例内容（到下一个 ## 或文件结束）
                lines = part.strip().split('\n')
                example_lines = []
                for line in lines:
                    if line.startswith('## '):
                        break
                    example_lines.append(line)

                if example_lines:
                    example_text = '\n'.join(example_lines).strip()
                    if example_text and len(example_text) > 50:  # 过滤太短的
                        examples.append(example_text)

            print(f"DEBUG: 从 {style_file} 加载了 {len(examples)} 个风格示例")
            return examples

        except Exception as e:
            print(f"DEBUG: 加载风格示例失败: {e}")
            return []

    # 常见 emoji Unicode 范围（较严格，避免误匹配普通符号）
    EMOJI_RANGES = [
        "\U0001F600-\U0001F64F",  # 表情符号
        "\U0001F300-\U0001F5FF",  # 符号和象形
        "\U0001F680-\U0001F6FF",  # 交通和符号
        "\U0001F1E0-\U0001F1FF",  # 旗帜
        "\U0001F900-\U0001F9FF",  # 补充符号
        "\U0001FA00-\U0001FA6F",  # 象棋等
        "\U0001FA70-\U0001FAFF",  # 符号扩展-A
    ]
    EMOJI_PATTERN = re.compile("[" + "".join(EMOJI_RANGES) + "]+", flags=re.UNICODE)

    def _count_emoji(self, text: str) -> int:
        """统计文本中 emoji 块数量"""
        return len(self.EMOJI_PATTERN.findall(text))

    def _normalize_emoji(self, text: str, min_count: int = 3, max_count: int = 5) -> str:
        """规范化文本中的 emoji 数量，确保不超过 max_count。
        超过 max_count 时，保留所有文字内容，只删除第 max_count+1 个及以后的 emoji 块；
        不足时不补充（依赖 prompt）。"""
        matches = list(self.EMOJI_PATTERN.finditer(text))
        if len(matches) <= max_count:
            return text

        # 保留所有文字，只删除超过 max_count 的 emoji 块
        result = []
        last_end = 0
        for i, match in enumerate(matches):
            # 保留当前 emoji 前的文本
            result.append(text[last_end:match.start()])
            if i < max_count:
                # 保留前 max_count 个 emoji
                result.append(match.group())
            # 否则跳过该 emoji（不追加）
            last_end = match.end()
        # 追加最后一段文本
        result.append(text[last_end:])
        return ''.join(result)

    def _expand_review_with_claude(self, student_name: str, preferred_name: str, course_name: str,
                                   objectives: list, performance_text: str,
                                   course_type: str = 'kitten', gender: str = '未知',
                                   feedback: str = '') -> str:
        """使用Kimi API扩写课评内容，根据课程类型使用不同 prompt。
        C++ 课程保持原数据驱动风格；Kitten/AI 课程使用去姓称呼、Emoji、180-350字新风格。"""
        print(f"\n{'='*60}")
        print(f"开始生成课评 - 学生: {student_name}({preferred_name}), 课程: {course_name}, 类型: {course_type}, 性别: {gender}")
        print(f"{'='*60}\n")

        import requests
        import json
        import os

        # 加载API密钥
        print("[1/6] 正在加载API密钥...")
        api_key = self._load_api_key()

        if not api_key:
            raise RuntimeError("未找到API密钥，请设置 KIMI_API_KEY 环境变量或在 .env 文件中配置")

        print(f"[OK] API密钥已加载(长度: {len(api_key)})")

        print("[2/6] 正在准备API请求数据...")

        # 处理objectives
        objectives_text = "\n".join([f"- {obj}" for obj in objectives[:4]]) if objectives else ""
        print(f"   课程目标数量: {len(objectives) if objectives else 0}")

        print("[3/6] 正在构建Prompt...")

        # 读取风格示例
        style_examples = self._load_teacher_style_examples(course_type)
        if style_examples:
            print(f"   已加载 {len(style_examples)} 个风格示例")
        else:
            print("   未找到风格示例，使用默认风格")

        # 构建风格示例文本
        examples_text = ""
        if style_examples:
            processed_examples = [example for example in style_examples[:3]]
            examples_text = "\n\n以下是参考的写作风格示例（模仿其语气、结构和用词）：\n\n" + "\n---\n".join(processed_examples)

        # 根据性别确定人称代词
        pronoun = "他" if gender == "男" else "她" if gender == "女" else "他/她"

        # 判断是否为 C++ 课程
        is_cpp = course_type.lower() in ('c++', 'csp', 'cpp')

        if is_cpp:
            # C++ 课评：数据驱动、题目可罗列，同时满足 CSP 质量评分标准
            system_prompt = f"""你是一位经验丰富的 CSP 编程老师（示例老师）。请根据提供的信息，为一名学生写一段 C++ 课后评价。

【核心要求】
1. **字数严格控制**：150-220字之间，不要过长。
2. **事实准确**：必须准确使用学生姓名、课程知识点、题目名称和数据，不编造任何未提及内容。
3. **评价平衡真实**：优点和不足的比例约为 6:4 或 7:3，不要全是表扬，也不要只批评。
4. **具体性（必须引用题目名+数据）**：
   - 涉及题目时，必须使用「题目名」格式引用，如「输出满足条件的整数5」「求零件个数」。禁止只用"第几题""这几题""等N道题"等模糊说法。
   - 必须自然融入具体数据：如"提交了X次""调试了X次""在「XX」上试了X次""除了「YY」还在WA，其他都AC了"。
5. **融入课程目标知识点**：评价中必须自然出现至少 2 个本节课知识点关键词（如循环、数组、输入输出、格式化输出、求和、计数等）。
6. **成长性**：先肯定学生的努力和优点（用"能够""完成""理解""思路清晰"等），再清晰指出改进方向（用"还需要""注意""补做""巩固"等）。
7. **可执行建议**：课后建议必须具体到题目或知识点，例如"课后补做「XXX」「YYY」""多练循环/数组相关题目""把错题重新做一遍"。
8. **家长可读性**：用亲切、口语化的语气，像跟家长反馈一样；技术术语适度，必要时用括号给出白话解释（如"WA（答案错误）""CE（编译错误）"）。
9. **风险控制**：禁止横向比较、负面标签、泄露隐私、过度承诺。禁用"最高""最快""分水岭""紧随""比XX""差异最大""不如""懒""笨""粗心""不认真""基础差"等风险词。
10. **反模板化**：这是给单个学生的课评，必须围绕该学生的具体表现写，不能写成"换个人名就能直接用"的通用套话。不同学生的课评应该有明显不同的题目引用、数据和建议。
11. **阶段测试课**：如果课程主题包含"阶段测试/复习/检测"，评价应聚焦"复习/考查情况"，不要写"今天新学了XX""本节课讲了XX"等与新授知识点矛盾的表述。
12. **用词平实具体**：禁止使用"眼睛里闪烁着求知的光芒""非常优秀""特别出色""超级棒"等夸张修饰词。
13. **必须使用正确的人称代词"{pronoun}"（学生是{gender}生）**
14. **严格参考下面提供的风格示例，模仿其语气、用词习惯和句式结构**

只输出评价段落本身，不要加标题或其他内容。{examples_text}"""

            feedback_section = f"""【上一轮问题反馈，请务必修正】
{feedback}

""" if feedback else ""

            user_prompt = f"""学生姓名：{student_name}
学生性别：{gender}（请使用"{pronoun}"作为人称代词）
课程主题：{course_name}
本节课知识点：
{objectives_text}

老师观察到的学生表现要点（含题目名、提交次数、AC/WA状态等）：
{performance_text}

{feedback_section}请按照 CSP 课评质量评分标准，为"{student_name}"写一段完整评价：
1. 严格基于用户提供的表现要点，禁止添加任何未提及的内容
2. 必须使用正确的人称代词"{pronoun}"（学生是{gender}生）
3. 字数控制在 150-220 字
4. 先肯定努力和优点，再指出不足和改进方向
5. 涉及题目时必须用「题目名」格式引用具体题目名称；绝对禁止"等N道题""这几道题"等空泛说法
6. 必须融入具体数据：如提交次数、调试次数、WA/AC状态、卡住的题目名
7. 融入至少 2 个本节课知识点关键词
8. 课后建议要具体到题目名或知识点
9. 禁止横向比较、负面标签、过度承诺等风险措辞
10. 只围绕该学生的实际表现扩写，不要写成通用模板；若课程主题为阶段测试/复习，不写"今天新学/本节课讲"等矛盾表述
11. 技术缩写如 WA/CE/AC 首次出现时建议用括号给出白话解释"""

            max_tokens = 800
        elif course_type.lower() == 'ai01':
            # AI01 保持原来的个人课评风格（去姓称呼、emoji、180-350字）
            system_prompt = f"""你是一位经验丰富、语气亲切的少儿编程老师（示例老师）。请根据提供的信息，为一名学生写一段课评评价部分。

【核心要求】
1. **每人独立课评**：这是给单个学生的课评，只围绕这位学生写，不涉及其他同学。
2. **去姓称呼**：全程称呼学生为"{preferred_name}"（只喊名字/小名），绝对禁止使用全名"{student_name}"。
3. **字数**：180-350字之间，不要太短也不要过长。
4. **Emoji**：请在评价正文中使用**恰好 4 个 emoji**，分别放在以下位置：
   - 第1个：评价开头（如"小明这节课表现很棒🌟"）
   - 第2个：优点描述部分（如"能够独立完成程序💡"）
   - 第3个：不足或待改进部分（如"最后还有几题没完成📝"）
   - 第4个：结尾鼓励部分（如"继续加油！！🚀"）
   **不要多也不要少，严禁连续堆砌 emoji**。
5. **禁止模糊"几题没完成"**：如果表现要点中没有具体题目/项目名称，绝对禁止写"还有几道题没完成""最后还有几题没来得及完成""后面有几题没做完"等模糊表述。必须直接指出具体知识点或能力上的不足（如"在变量和关系运算的综合应用上还需要再巩固""对XX知识点的理解还不够熟练"）。只有表现要点明确列出了具体未完成的题目/项目时，才能提该题目/项目的名称。
6. **结合知识点**：在评价正文中自然融入至少 3 个本节课知识点关键词（参考"本节课知识点"），让家长能感受到孩子学到了什么具体内容。
7. **结构完整**：
   - 开头：简单点出课程难度或学生整体状态，可顺带和之前的表现做个小对比（如"比上周更投入了""这次比上节课状态好一些"）
   - 中间：具体行为描述（优点 + 不足），结合本节课知识点和专业术语
   - 结尾：给一句具体可操作的课后建议 + "继续加油！！"
8. **评价平衡**：优点和不足比例约 6:4 或 7:3，不要全是表扬，也不要只批评。
9. **人称代词**：学生是{gender}生，请使用"{pronoun}"。
10. **用词平实**：禁止使用"非常优秀""特别出色""超级棒""眼睛里闪烁着求知的光芒"等夸张词。用"挺不错的""有进步""还需要注意"等平实表达。
11. **禁止编造**：严格基于老师提供的表现要点扩写，不添加未提及的内容。

只输出评价段落本身，不要加标题、课程信息等其他内容。{examples_text}"""

            user_prompt = f"""学生全名：{student_name}
去姓称呼（必须使用这个称呼，禁止使用全名）：{preferred_name}
学生性别：{gender}（请使用"{pronoun}"作为人称代词）
课程主题：{course_name}
本节课知识点：
{objectives_text}

老师观察到的学生表现要点：
{performance_text}

请按照上述要求，为"{preferred_name}"写一段课评评价：
1. 使用"{preferred_name}"称呼学生，禁止出现"{student_name}"
2. 字数控制在 180-350 字
3. 在评价正文中使用恰好 4 个 emoji，位置分别是：开头、优点部分、不足部分、结尾鼓励处
4. 优点和不足比例 6:4 或 7:3
5. 绝对禁止写"还有几道题没完成"等模糊表述；如果表现要点中没有具体题目/项目名称，应直接指出知识点或能力上的不足。只有明确列出具体未完成项时，才能提及该项名称
6. 评价中请自然提及至少 3 个本节课知识点关键词
7. 结尾给一句具体建议，并以"继续加油！！"结束
8. 严格基于提供的表现要点，禁止编造"""

            max_tokens = 1200
        elif course_type.lower() in ('ai', 'aicode'):
            # AICODE 标准课后反馈 prompt
            system_prompt = f"""你是一位经验丰富的 AICODE 课程老师（示例老师）。请根据提供的信息，为一名学生写一份课后反馈。

【核心要求】
1. **输出结构必须严格按以下六个模块**（用 Markdown 标题）：
   - 开头段落：必须说明本节课项目名称、具体任务和阶段目标，例如"本节课的主要任务是……，阶段目标是……"
   - ## 一、本节课核心收获
     - ### 1. 知识层面：孩子认识了什么项目元素 / AI 协作方法 / 工程概念
     - ### 2. 能力层面：孩子通过什么具体任务，练习了什么具体能力动作
     - ### 3. 思维层面：孩子这节课思考了什么关键问题
   - ## 二、本节课项目完成情况
   - ## 三、课堂思考与互动
   - ## 四、课堂中出现的主要问题（至少 2 个具体问题）
   - ## 五、老师课堂处理方式（至少 2 个具体处理方式）
   - ## 六、下节课安排
2. **去姓称呼**：全程称呼学生为"{preferred_name}"，绝对禁止使用全名"{student_name}"。
3. **不写空话**：禁止出现"培养了 AI 思维""提升了创造力""课堂表现不错""完成情况较好""训练了逻辑思维"等没有具体证据的抽象词。所有能力、思维描述必须落到"通过什么任务，做了什么动作"上。
4. **禁止模糊"几题没完成"**：如果表现要点中没有具体未完成项，禁止写"还有几道题没完成""最后还有几题没来得及""后面有几题没做完"等模糊表述。
5. **结合知识点**：自然融入至少 3 个本节课知识点关键词。
6. **评价平衡**：优点和不足比例约 6:4 或 7:3，不要全是表扬，也不要只批评。
7. **人称代词**：学生是{gender}生，请使用"{pronoun}"。
8. **禁止编造**：严格基于老师提供的表现要点扩写，不添加未提及内容。
9. **下节课衔接**：下节课安排必须和本节课项目产出形成具体衔接，写清楚继续推进什么。

【示例片段】
本节 AICODE 课程围绕【涂鸦 PK】项目展开。{preferred_name}本节课在已有涂鸦作品基础上，继续通过 AI 修改角色互动、碰撞反馈和 PK 规则，让作品从"静态展示"逐步变成"可以互动、可以测试、可以继续优化"的小游戏。

## 一、本节课核心收获

### 1. 知识层面：
{preferred_name}认识了角色互动、碰撞反馈、PK 规则等项目元素，知道一个作品从"能展示"变成"能玩"，需要明确的互动规则和反馈效果。

### 2. 能力层面：
{preferred_name}通过给涂鸦角色增加 PK 效果，练习了把"我想让角色打起来"这种模糊想法，表达成"两个角色碰撞后触发扣血、后退、分数变化或特效反馈"等更具体的 AI 修改需求。

### 3. 思维层面：
本节课重点引导{preferred_name}思考：什么样的作品才算真正有互动？两个角色同时出现在画面上并不等于 PK，必须有规则、反馈和结果。

## 二、本节课项目完成情况
本节课{preferred_name}完成了基础 PK 互动效果，能够让两个角色产生碰撞反馈，并尝试通过修改提示词调整互动规则。下一步可以继续加入计分、胜负判断或特效反馈。

## 三、课堂思考与互动
课堂中{preferred_name}发现角色虽然能移动，但碰撞后没有任何变化，于是提出"这样感觉不像 PK"。老师引导{pronoun}继续思考：PK 游戏至少需要什么反馈？是扣血、计分、后退，还是出现特效？{preferred_name}随后尝试补充碰撞反馈需求。

## 四、课堂中出现的主要问题
### 问题 1：需求表达不够具体
{preferred_name}一开始会直接说"帮我做得好玩一点"，但没有说明角色怎么互动、什么时候触发、出现什么反馈。

### 问题 2：测试意识不足
{preferred_name}看到 AI 生成了画面后，就认为作品完成了，但没有主动测试碰撞、计分或反馈是否真的生效。

## 五、老师课堂处理方式
1. 针对需求表达不清的问题，老师引导{preferred_name}使用"角色 + 动作 + 规则 + 效果 + 限制"的结构描述需求；
2. 针对测试意识不足的问题，老师要求{preferred_name}每次生成后都要运行测试，并回答：能不能运行？是否符合需求？如果不符合下次怎么修改？

## 六、下节课安排
下节课将继续围绕作品完善和互动效果优化展开，重点帮助{preferred_name}把项目从"能运行"推进到"更完整、更有玩法、更适合展示"。

{examples_text}"""

            user_prompt = f"""学生全名：{student_name}
去姓称呼（必须使用这个称呼，禁止使用全名）：{preferred_name}
学生性别：{gender}（请使用"{pronoun}"作为人称代词）
课程主题：{course_name}
本节课知识点：
{objectives_text}

老师观察到的学生表现要点：
{performance_text}

请严格按照上述六个模块结构，为"{preferred_name}"写一份完整的 AICODE 课后反馈。
要求：
1. 必须使用"{preferred_name}"称呼，禁止出现"{student_name}"
2. 六个模块缺一不可，每个模块都要有实质内容
3. 能力层面必须写出"通过什么任务，练习了什么动作"
4. 思维层面必须写出"孩子思考了什么具体问题"
5. 课堂思考与互动部分必须使用"学生发现/提问……，老师引导……，随后/接着学生……"的承接结构
6. 问题部分至少写 2 个具体问题
7. 老师处理方式至少写 2 条
8. 下节课安排必须具体且与本节课衔接
9. 严格基于提供的表现要点，禁止编造"""

            max_tokens = 2000
        else:
            # 通用机构类型（美术 / 音乐 / 体育 / 书法 等）
            inst = self.config.get('institution_types', {}).get(course_type.lower(), {})
            inst_label = inst.get('label', course_type) if isinstance(inst, dict) else course_type
            system_prompt = f"""你是一位经验丰富、语气亲切的{inst_label}老师（示例老师）。请根据提供的信息，为一名学生写一段课评评价部分。

【核心要求】
1. 每人独立课评：这是给单个学生的课评，只围绕这位学生写，不涉及其他同学。
2. 去姓称呼：全程称呼学生为"{preferred_name}"（只喊名字/小名），绝对禁止使用全名"{student_name}"。
3. 字数：180-350字之间，不要太短也不要过长。
4. 结合知识点：在评价正文中自然融入至少 3 个本节课知识点关键词，让家长能感受到孩子学到了什么具体内容。
5. 结构完整：开头点出课程难度或学生整体状态；中间具体行为描述（优点+不足）；结尾给一句具体可操作的课后建议。
6. 评价平衡：优点和不足比例约 6:4 或 7:3，不要全是表扬，也不要只批评。
7. 人称代词：学生是{gender}生，请使用"{pronoun}"。
8. 用词平实：用"挺不错的""有进步""还需要注意"等平实表达，禁止"非常优秀""特别出色""超级棒"等夸张词。
9. 禁止编造：严格基于老师提供的表现要点扩写，不添加未提及的内容。

只输出评价段落本身，不要加标题、课程信息等其他内容。{examples_text} """

            user_prompt = f"""学生全名：{student_name}
去姓称呼（必须使用这个称呼，禁止使用全名）：{preferred_name}
学生性别：{gender}（请使用"{pronoun}"作为人称代词）
课程主题：{course_name}
本节课知识点：
{objectives_text}

老师观察到的学生表现要点：
{performance_text}

请按照上述要求，为"{preferred_name}"写一段课评评价：
1. 使用"{preferred_name}"称呼学生，禁止出现"{student_name}"
2. 字数控制在 180-350 字
3. 优点和不足比例 6:4 或 7:3
4. 自然融入至少 3 个本节课知识点关键词
5. 结尾给一句具体建议
6. 严格基于提供的表现要点，禁止编造"""

            max_tokens = 1200
            max_tokens = 1200

        print("[4/6] 正在准备API请求...")

        # 准备请求数据（支持 .env 中的 AI_BASE_URL / AI_MODEL，与 .env.example 一致）
        api_base = os.environ.get('AI_BASE_URL', 'https://api.moonshot.cn/v1').rstrip('/')
        api_url = api_base + '/chat/completions'
        api_model = os.environ.get('AI_MODEL', 'moonshot-v1-8k')

        data = {
            "model": api_model,
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            "temperature": 0.7,
            "max_tokens": max_tokens
        }

        headers = {
            "Authorization": f"Bearer {api_key}",
            "Content-Type": "application/json"
        }

        print(f"[5/6] 正在调用Kimi API...")
        print(f"   学生: {student_name} -> 称呼: {preferred_name}")
        print(f"   课程: {course_name}")
        print(f"   类型: {course_type} ({'C++' if is_cpp else 'Kitten/AI'})")
        print(f"   性别: {gender} -> 使用'{pronoun}'")
        print(f"   模型: moonshot-v1-8k")

        # 发送请求
        response = requests.post(
            api_url,
            headers=headers,
            json=data,
            timeout=60
        )

        # 检查响应
        print(f"[6/6] 正在处理API响应...")

        if response.status_code == 200:
            result = response.json()
            content = result["choices"][0]["message"]["content"].strip()
            print(f"[OK] Kimi API生成成功，字数：{len(content)}")

            # 检查是否正确使用了人称代词
            if gender == "男" and "她" in content:
                print(f"[警告] 检测到男生使用了'她'，尝试修正...")
                content = content.replace("她", "他")
            elif gender == "女" and "他" in content and "她" not in content:
                print(f"[警告] 检测到女生使用了'他'，尝试修正...")
                content = content.replace("他", "她")

            # 非 C++ 课程规范化 emoji 数量
            if not is_cpp:
                original_emoji_count = self._count_emoji(content)
                content = self._normalize_emoji(content)
                new_emoji_count = self._count_emoji(content)
                if original_emoji_count != new_emoji_count:
                    print(f"[后处理] emoji 数量从 {original_emoji_count} 调整为 {new_emoji_count}")

            return content
        else:
            raise RuntimeError(f"Kimi API返回错误: {response.status_code} - {response.text}")

    def _load_api_key(self) -> str:
        """加载API密钥（支持.env文件和环境变量）"""
        # 从多个可能的位置查找 .env 文件
        # 1. 当前工作目录
        # 2. 项目根目录（基于本文件位置: src/ai/ -> 项目根目录）
        possible_roots = [
            Path('.'),                           # 当前工作目录
            Path(__file__).parent.parent.parent, # 项目根目录 (src/ai/ -> ../../)
        ]

        for root in possible_roots:
            env_path = root / '.env'
            if env_path.exists():
                with open(env_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        line = line.strip()
                        if (line.startswith('AI_API_KEY=') or line.startswith('KIMI_API_KEY=')) and not line.startswith('#'):
                            return line.split('=', 1)[1].strip().strip('"').strip("'")

        # 最后尝试从环境变量读取
        return os.environ.get('AI_API_KEY') or os.environ.get('KIMI_API_KEY', '')

    # ---------- C++ 课评确定性生成辅助方法 ----------
    def _extract_problem_titles_from_performance(self, performance_text: str) -> list:
        """从 performance_text 中提取引用的题目名称（支持「」、“”、" "）"""
        if not performance_text:
            return []
        titles = []
        titles.extend(re.findall(r'「([^」]{2,})」', performance_text))
        titles.extend(re.findall(r'“([^”]{2,})”', performance_text))
        titles.extend(re.findall(r'"([^"]{2,})"', performance_text))
        seen = set()
        result = []
        for t in titles:
            t = t.strip()
            if t and t not in seen:
                seen.add(t)
                result.append(t)
        return result

    def _judge_problem_status(self, title: str, performance_text: str) -> str:
        """根据题目在 performance_text 中出现的上下文判断状态"""
        patterns = [
            rf'「{re.escape(title)}」',
            rf'“{re.escape(title)}”',
            rf'"{re.escape(title)}"',
        ]
        pos = -1
        for pat in patterns:
            m = re.search(pat, performance_text)
            if m:
                pos = m.start()
                break
        if pos < 0:
            return "未做"

        # 如果题目出现在 "后面" 之后，默认属于未完成/待补做
        late_boundary = performance_text.find('后面')
        if late_boundary >= 0 and pos > late_boundary:
            return "未做"

        # 上下文窗口：向前 25 字，向后到下一个题目引用或 25 字为止，避免后面的题目状态串扰
        start = max(0, pos - 25)
        next_title = re.search(r'[「“"]', performance_text[pos + len(title):])
        if next_title:
            end = pos + len(title) + next_title.start() + 5
        else:
            end = min(len(performance_text), pos + len(title) + 25)
        ctx = performance_text[start:end]

        neg = ['没完成', '没做完', '没来得及', '未做', '未完成', '需要补', '课后补', '落下了', '没做', '没通过']
        wa = ['答案错误', '错误', 'WA', '没做对', '不对', '未通过', '错了']
        pos_kw = ['完成得', '做完了', '做对', '正确', '通过', '顺利', '挺顺', '不错', '又快又准', '做得还可以', '还可以']

        for w in neg:
            if w in ctx:
                return "未做"
        for w in wa:
            if w in ctx:
                return "WA"
        for w in pos_kw:
            if w in ctx:
                return "AC"
        if any(w in performance_text for w in ['多题没', '几题没', '后面', '没完成']):
            return "未做"
        return "AC"

    def _extract_submits_for_title(self, title: str, performance_text: str) -> int:
        """从 performance_text 中该题目附近提取提交次数"""
        patterns = [
            rf'「{re.escape(title)}」',
            rf'“{re.escape(title)}”',
            rf'"{re.escape(title)}"',
        ]
        pos = -1
        for pat in patterns:
            m = re.search(pat, performance_text)
            if m:
                pos = m.start()
                break
        if pos < 0:
            return 0

        # 向后到下一个题目引用或 40 字为止
        next_title = re.search(r'[「“"]', performance_text[pos + len(title):])
        if next_title:
            end = pos + len(title) + next_title.start() + 5
        else:
            end = min(len(performance_text), pos + len(title) + 40)
        ctx = performance_text[pos:end]

        # 匹配 "提交了5次"、"试了4次"、"5次提交"、"调试了3次"、"（4次）" 等
        m = re.search(r'(?:提交|试|调试|做了|交了)\D*(\d+)\s*次', ctx)
        if m:
            return int(m.group(1))
        m = re.search(r'(\d+)\s*次(?:提交|试|调试)', ctx)
        if m:
            return int(m.group(1))
        m = re.search(r'[(（]\s*(\d+)\s*次[)）]', ctx)
        if m:
            return int(m.group(1))
        return 0

    def _build_stat_from_performance(self, performance_text: str) -> dict:
        """把 performance_text 转成 ReviewDraftGenerator 需要的 student_stat 结构"""
        titles = self._extract_problem_titles_from_performance(performance_text)
        if not titles:
            return None
        problems = []
        total_submits = 0
        for title in titles:
            status = self._judge_problem_status(title, performance_text)
            submits = self._extract_submits_for_title(title, performance_text)
            if status == "AC" and submits == 0:
                submits = 1
            total_submits += submits
            problems.append({
                "title": title,
                "status": status,
                "submits": submits,
                "score": 100 if status == "AC" else 0,
            })
        done_count = sum(1 for p in problems if p["status"] != "未做")
        total_count = len(problems)
        all_ac = all(p["status"] == "AC" for p in problems)
        has_wa = any(p["status"] == "WA" for p in problems)
        has_unsubmitted = any(p["status"] == "未做" for p in problems)
        return {
            "problems": problems,
            "done_count": done_count,
            "total_count": total_count,
            "all_ac": all_ac,
            "has_wa": has_wa,
            "has_unsubmitted": has_unsubmitted,
            "total_submits": total_submits,
        }

    def _score_cpp_review(self, review_text: str, student_name: str, objectives: list, performance_text: str) -> dict:
        """调用 review_scorer 对 C++ 课评评分"""
        return evaluate_review(review_text, student_name, student_name, objectives, performance_text, is_cpp=True)

    def generate_review(self, class_name: str, student_name: str, date: str, course_path: str, performance_text: str) -> str:
        """生成课评的主方法"""
        print(f"\n{'='*60}")
        print(f"开始生成课评")
        print(f"班级: {class_name}, 学生: {student_name}, 日期: {date}")
        print(f"{'='*60}\n")

        # 1. 加载学生信息
        print("[1/5] 正在加载学生信息...")
        student_info = self.load_student_info(class_name, student_name)
        if student_info:
            print(f"   学生年龄: {student_info.get('age', '未知')}")
            print(f"   学生性别: {student_info.get('gender', '未知')}")
        else:
            print("   未找到学生画像信息")

        # 2. 加载课程内容
        print("[2/5] 正在加载课程内容...")
        course_content = self.load_course_content(course_path)
        if course_content:
            print(f"   课程文件已加载")
        else:
            print(f"   警告: 未找到课程文件 {course_path}")

        # 3. 确定课程类型和名称
        print("[3/5] 正在确定课程类型...")
        course_type = 'kitten'  # 默认
        course_name = course_path

        if course_path:
            path_lower = course_path.lower()
            if 'c++' in path_lower or 'csp' in path_lower:
                course_type = 'csp'
            elif 'ai' in path_lower or 'aicode' in path_lower:
                course_type = 'ai'
            elif 'kitten' in path_lower or 'k2' in path_lower or 'k4' in path_lower:
                course_type = 'kitten'

            # 从路径提取课程名称
            course_file = Path(course_path).name
            course_name = course_file.replace('.md', '')
            print(f"   课程类型: {course_type}")
            print(f"   课程名称: {course_name}")

        # 4. 生成课评
        print("[4/5] 正在生成课评内容...")
        
        # 获取学生性别
        gender = student_info.get('gender', '未知')
        
        # 提取教学目标
        objectives = []
        for line in course_content.strip().split('\n'):
            line = line.strip()
            # 支持 1. / 1、 开头的编号
            if len(line) > 2 and (line[0].isdigit() and line[1] in '.、'):
                objectives.append(line)
            # 支持 * / - 开头的列表项，去掉 Markdown 加粗标记
            elif len(line) > 2 and line[0] in '*-':
                cleaned = re.sub(r'\*\*', '', line[1:]).strip()
                # 去掉前导冒号前的标签，如 "知识目标: "
                cleaned = re.sub(r'^[^:：]*[\uff1a:]\s*', '', cleaned)
                if cleaned and len(cleaned) > 5:
                    objectives.append(cleaned)

        # 判断是否为 C++ 课程
        is_cpp = course_type.lower() in ('c++', 'csp', 'cpp')

        # AI01 班级保持原来的个人课评风格，AI03 使用 AICODE 标准班级反馈风格
        if not is_cpp and class_name and class_name.upper().startswith('AICODE01'):
            course_type = 'ai01'
            print(f"   班级 {class_name} 使用 AI01 个人课评风格")

        # 非 C++ 课程使用去姓称呼
        preferred_name = student_name if is_cpp else self._get_preferred_name(student_name)
        print(f"   称呼: {preferred_name} ({'C++保持全名' if is_cpp else '去姓称呼'})")

        expanded_review = ""
        best_review = ""
        best_score = -1

        if is_cpp:
            # C++ 课程：优先尝试从 performance_text 解析题目，用 OJ 同款模板生成
            stat = self._build_stat_from_performance(performance_text)
            if stat:
                draft_gen = ReviewDraftGenerator()
                deterministic_review = draft_gen.generate_student_review(
                    stat, student_name, objectives,
                    section_title=course_name, course_title=course_name
                )
                if deterministic_review:
                    score = self._score_cpp_review(deterministic_review, student_name, objectives, performance_text)
                    print(f"   确定性生成评分: {score['total']}")
                    if score['total'] >= 80:
                        expanded_review = deterministic_review
                    if score['total'] > best_score:
                        best_review = deterministic_review
                        best_score = score['total']

            if not expanded_review:
                # 调用AI生成，并迭代优化直到 ≥85 分
                api_key = self._load_api_key()
                if not api_key:
                    raise RuntimeError("未找到API密钥，请设置 KIMI_API_KEY 环境变量或在 .env 文件中配置")

                print("   使用AI生成（带评分迭代）...")
                feedback = ""
                for attempt in range(3):
                    expanded_review = self._expand_review_with_claude(
                        student_name, preferred_name, course_name,
                        objectives, performance_text, course_type, gender,
                        feedback=feedback
                    )
                    score = self._score_cpp_review(expanded_review, student_name, objectives, performance_text)
                    print(f"   AI 生成第 {attempt+1}/3 轮评分: {score['total']}")
                    if score['total'] > best_score:
                        best_review = expanded_review
                        best_score = score['total']
                    if score['total'] >= 85:
                        break
                    # 构建下一轮反馈
                    feedback_parts = []
                    details = score.get('details', {})
                    for dim, (s, note) in details.items():
                        if dim == '一票否决':
                            continue
                        if s < 10:
                            feedback_parts.append(f"{dim}得分{s}（{note}），需要加强")
                    if not feedback_parts:
                        feedback_parts.append("整体得分仍不足，请更严格地按照要求写：引用题目名、融入知识点、同时包含肯定与改进、给出具体课后建议。")
                    feedback = "\n".join(feedback_parts)

                expanded_review = best_review
        else:
            # 非 C++ 课程：AI 生成 + 迭代优化
            api_key = self._load_api_key()
            if not api_key:
                raise RuntimeError("未找到API密钥，请设置 KIMI_API_KEY 环境变量或在 .env 文件中配置")

            print(f"   使用AI生成（带评分迭代，course_type={course_type}）...")
            feedback = ""
            for attempt in range(3):
                expanded_review = self._expand_review_with_claude(
                    student_name, preferred_name, course_name,
                    objectives, performance_text, course_type, gender,
                    feedback=feedback
                )
                score = evaluate_review(
                    expanded_review, student_name, preferred_name,
                    objectives, performance_text, is_cpp=False,
                    course_type=course_type
                )
                print(f"   AI 生成第 {attempt+1}/3 轮评分: {score['total']}")
                if score['total'] > best_score:
                    best_review = expanded_review
                    best_score = score['total']
                if score['total'] >= 85:
                    break
                # 构建下一轮反馈
                feedback_parts = []
                details = score.get('details', {})
                for dim, (s, note) in details.items():
                    if dim == '一票否决':
                        continue
                    if s < 8:
                        feedback_parts.append(f"{dim}得分{s}（{note}），需要加强")
                if not feedback_parts:
                    feedback_parts.append("整体得分仍不足，请严格按照 AICODE 课后反馈标准六个模块写，每个模块都要有实质内容，能力/思维/问题/处理都要具体到本节课项目。")
                feedback = "\n".join(feedback_parts)

            expanded_review = best_review

        # 组装完整的课评格式
        lines = []
        lines.append(f"课程：{class_name}")
        lines.append(f"课程主题：{course_name}")
        lines.append(f"课程内容")
        if objectives:
            for i, obj in enumerate(objectives, 1):
                lines.append(f"{i}. {obj}")
        else:
            lines.append(course_content.strip())
        lines.append("")
        lines.append(expanded_review)
        # 非 C++ 课程追加老师签名，保证结构完整性
        if not is_cpp:
            lines.append("")
            lines.append("—— 示例老师")
        lines.append("")
        content = "\n".join(lines)
        # 去除 Markdown 格式符号，使网页展示更干净
        return strip_markdown(content)

    def save_review(self, class_name: str, student_name: str, date: str, content: str):
        """保存课评到feedback文件夹"""
        reviews_dir = Path(self.config['paths']['students']) / class_name / student_name / "feedback"
        reviews_dir.mkdir(parents=True, exist_ok=True)

        date_formatted = date.replace('-', '')
        reviews_path = reviews_dir / f"{date_formatted}.md"
        with open(reviews_path, 'w', encoding='utf-8') as f:
            f.write(content)

        return reviews_path


if __name__ == '__main__':
    # 测试
    generator = ReviewGenerator()
    review = generator.generate_review(
        class_name='K2示例周日0845',
        student_name='李小明',
        date='2026-05-12',
        course_path='kitten/乐学课堂/01 手抖"治疗仪".md',
        performance_text='表现很好，能够独立完成程序'
    )
    print(review)
