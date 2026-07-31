#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
针对编程的小学生的用户画像skill - 通过20轮提问来创建用户的画像
"""

import yaml
from pathlib import Path


class ProgrammingStudentProfileSkill:
    """编程小学生用户画像创建工具"""

    def __init__(self, config_path: str = None):
        if config_path is None:
            # 尝试从项目根目录加载配置文件
            base_dir = Path(__file__).parent.parent.parent
            config_path = base_dir / "config.yaml"
        else:
            config_path = Path(config_path)

        with open(config_path, 'r', encoding='utf-8') as f:
            self.config = yaml.safe_load(f)

        # 20轮提问的问题列表，包含4个选项
        self.questions = [
            {
                "question": "1. 孩子今年几岁？",
                "options": ["6-7岁", "8-9岁", "10-11岁", "12岁以上"]
            },
            {
                "question": "2. 孩子接触编程多久了？",
                "options": ["3个月以内", "3-6个月", "6-12个月", "1年以上"]
            },
            {
                "question": "3. 孩子每周编程学习的时间是多少？",
                "options": ["1-2小时", "3-5小时", "6-10小时", "10小时以上"]
            },
            {
                "question": "4. 孩子对编程的兴趣如何？",
                "options": ["不感兴趣", "一般", "比较感兴趣", "非常感兴趣"]
            },
            {
                "question": "5. 孩子最喜欢编程中的哪个部分？",
                "options": ["编写代码", "调试程序", "设计游戏", "做项目"]
            },
            {
                "question": "6. 孩子最不喜欢编程中的哪个部分？",
                "options": ["编写代码", "调试程序", "设计游戏", "做项目"]
            },
            {
                "question": "7. 孩子在学习编程时注意力能保持多久？",
                "options": ["15分钟以内", "15-30分钟", "30-45分钟", "45分钟以上"]
            },
            {
                "question": "8. 孩子在遇到困难时通常会怎么做？",
                "options": ["立即放弃", "尝试一下就放弃", "尝试多次后求助", "坚持直到解决"]
            },
            {
                "question": "9. 孩子喜欢独立解决问题还是需要帮助？",
                "options": ["完全独立", "大部分独立", "需要一些帮助", "需要大量帮助"]
            },
            {
                "question": "10. 孩子喜欢和其他小朋友一起学习编程吗？",
                "options": ["不喜欢", "一般", "比较喜欢", "非常喜欢"]
            },
            {
                "question": "11. 孩子对游戏化编程更感兴趣还是对实用项目更感兴趣？",
                "options": ["只喜欢游戏化编程", "更喜欢游戏化编程", "更喜欢实用项目", "只喜欢实用项目"]
            },
            {
                "question": "12. 孩子喜欢什么类型的游戏或动画？",
                "options": ["益智游戏", "动作游戏", "角色扮演游戏", "动画电影"]
            },
            {
                "question": "13. 孩子平时喜欢看什么类型的书？",
                "options": ["童话/寓言", "科普/科学", "冒险/故事", "不喜欢看书"]
            },
            {
                "question": "14. 孩子在学习编程时会主动探索新的内容吗？",
                "options": ["不会", "偶尔会", "经常会", "总是会"]
            },
            {
                "question": "15. 孩子对编程的耐心如何？",
                "options": ["耐心较差", "耐心一般", "比较有耐心", "非常有耐心"]
            },
            {
                "question": "16. 孩子在完成一个项目后会感到自豪吗？",
                "options": ["不会", "有点", "比较自豪", "非常自豪"]
            },
            {
                "question": "17. 孩子对数学、科学或艺术哪个更感兴趣？",
                "options": ["数学", "科学", "艺术", "都不感兴趣"]
            },
            {
                "question": "18. 孩子平时是如何解决学习上的问题的？",
                "options": ["直接问家长", "查资料", "自己思考", "放弃"]
            },
            {
                "question": "19. 孩子对电子产品的使用有什么限制？",
                "options": ["没有限制", "有限制但不严", "限制较多", "限制严格"]
            },
            {
                "question": "20. 家长希望孩子通过编程学习获得什么？",
                "options": ["逻辑思维", "创造力", "解决问题能力", "职业发展"]
            }
        ]

        # 问题分类
        self.categories = {
            "基本信息": [0, 1, 2],
            "兴趣与动机": [3, 4, 5, 16],
            "学习行为": [6, 7, 8, 9, 14, 15],
            "学习风格": [10, 11, 12, 13],
            "家庭与环境": [17, 18, 19, 20]
        }

    def create_profile(self) -> dict:
        """创建学生画像"""
        profile = {
            "基本信息": {},
            "兴趣与动机": {},
            "学习行为": {},
            "学习风格": {},
            "家庭与环境": {},
            "综合分析": {}
        }

        # 收集答案
        answers = []
        for i, question_data in enumerate(self.questions):
            question_text = question_data["question"]
            options = question_data["options"]

            print(f"\n{question_text}")
            for j, option in enumerate(options, 1):
                print(f"  {j}. {option}")

            while True:
                try:
                    choice = input("请选择选项（1-4）：").strip()
                    choice_index = int(choice) - 1
                    if 0 <= choice_index < len(options):
                        answer = options[choice_index]
                        answers.append(answer)
                        break
                    else:
                        print("请输入1-4之间的数字！")
                except ValueError:
                    print("请输入有效的数字！")

        # 分类处理答案
        for category, indexes in self.categories.items():
            for index in indexes:
                question_data = self.questions[index]
                question_text = question_data["question"]
                answer = answers[index]
                profile[category][question_text] = answer

        # 综合分析
        self.analyze_profile(profile)

        return profile

    def analyze_profile(self, profile: dict):
        """综合分析学生信息"""
        # 根据年龄分组
        age_str = profile["基本信息"]["1. 孩子今年几岁？"]
        if age_str.isdigit():
            age = int(age_str)
            if age <= 8:
                profile["综合分析"]["年龄段"] = "6-8岁"
                profile["综合分析"]["认知发展阶段"] = "具体形象思维为主，抽象逻辑思维萌芽"
                profile["综合分析"]["学习建议"] = "适合图形化编程，注重游戏化教学，保持教学时长在15-20分钟"
            elif age <= 11:
                profile["综合分析"]["年龄段"] = "9-11岁"
                profile["综合分析"]["认知发展阶段"] = "具备抽象推理能力，但仍需具体例子支撑"
                profile["综合分析"]["学习建议"] = "可以开始接触基础逻辑，引导系统调试，培养合作意识"
            else:
                profile["综合分析"]["年龄段"] = "12-14岁"
                profile["综合分析"]["认知发展阶段"] = "抽象思维建立，能够理解复杂逻辑关系"
                profile["综合分析"]["学习建议"] = "可以深入学习算法和数据结构，鼓励独立项目开发"

        # 学习动机分析
        interest_score = profile["兴趣与动机"]["4. 孩子对编程的兴趣如何（1-10分）？"]
        if interest_score.isdigit() and int(interest_score) >= 8:
            profile["综合分析"]["学习动机"] = "高动机"
            profile["综合分析"]["动机建议"] = "鼓励探索新领域，提供挑战性项目"
        elif interest_score.isdigit() and int(interest_score) >= 5:
            profile["综合分析"]["学习动机"] = "中等动机"
            profile["综合分析"]["动机建议"] = "通过兴趣点设计课程，保持学习多样性"
        else:
            profile["综合分析"]["学习动机"] = "低动机"
            profile["综合分析"]["动机建议"] = "寻找孩子的兴趣结合点，使用游戏化教学方法"

    def save_profile(self, profile: dict, filename: str) -> str:
        """保存学生画像"""
        profile_dir = Path(self.config['paths']['students'])
        profile_dir.mkdir(parents=True, exist_ok=True)

        output_path = profile_dir / filename
        with open(output_path, 'w', encoding='utf-8') as f:
            yaml.dump(profile, f, ensure_ascii=False, default_flow_style=False, allow_unicode=True)

        return str(output_path)

    def load_profile(self, filename: str) -> dict:
        """加载学生画像"""
        profile_dir = Path(self.config['paths']['students'])
        profile_path = profile_dir / filename

        if profile_path.exists():
            with open(profile_path, 'r', encoding='utf-8') as f:
                return yaml.safe_load(f)
        else:
            return None

    def generate_report(self, profile: dict) -> str:
        """生成学生画像报告"""
        report = []

        report.append("## 学生编程用户画像报告")
        report.append("")

        for category in profile:
            if category == "综合分析":
                continue

            report.append(f"### {category}")

            for question, answer in profile[category].items():
                report.append(f"- {question}")
                report.append(f"  {answer}")

            report.append("")

        report.append("### 综合分析")

        for key, value in profile["综合分析"].items():
            report.append(f"- {key}")
            report.append(f"  {value}")

        report.append("")

        # 根据年龄段提供参考资料
        if "年龄段" in profile["综合分析"]:
            report.append("### 参考资料")

            try:
                age_file = Path(self.config['paths']['references']) / "age-psychology" / f"{profile['综合分析']['年龄段']}-编程学习特点.md"

                if age_file.exists():
                    with open(age_file, 'r', encoding='utf-8') as f:
                        report.append("#### 年龄段学习特点")
                        report.append(f.read())

            except Exception:
                pass

        return "\n".join(report)


def main():
    """主函数"""
    print("=" * 50)
    print("编程小学生用户画像创建工具")
    print("=" * 50)

    skill = ProgrammingStudentProfileSkill()

    # 收集学生信息
    profile = skill.create_profile()

    # 输入学生姓名
    student_name = input("\n请输入学生姓名：").strip()

    # 保存学生画像
    profile_path = skill.save_profile(profile, f"{student_name}_profile.yaml")

    # 生成报告
    report = skill.generate_report(profile)

    # 保存报告
    report_path = Path(skill.config['paths']['students']) / f"{student_name}_profile.md"

    with open(report_path, 'w', encoding='utf-8') as f:
        f.write(report)

    print(f"\n学生画像创建完成！")
    print(f"画像文件已保存到：{profile_path}")
    print(f"报告文件已保存到：{report_path}")

    # 预览报告
    print("\n--- 报告预览 ---")
    print(report)


if __name__ == "__main__":
    main()