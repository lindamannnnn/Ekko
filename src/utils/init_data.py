#!/usr/bin/env python3
"""
初始化示例数据脚本
运行此脚本可以快速创建示例班级和学生
"""
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent.parent))

from config import config

def create_student(class_name, student_name, info_data):
    """创建学生文件夹和信息文件"""
    student_dir = Path('.claude/memory/class') / class_name / student_name
    student_dir.mkdir(parents=True, exist_ok=True)

    # 创建子目录
    (student_dir / 'feedback').mkdir(exist_ok=True)
    (student_dir / 'summary').mkdir(exist_ok=True)

    # 创建 profile.md
    info_content = f"""---
name: {info_data['name']}
age: {info_data['age']}
grade: {info_data['grade']}
enrollment_date: {info_data['enrollment_date']}
personality: {info_data['personality']}
class: {class_name}
---

# 学生档案

## 家长联系方式
{info_data.get('parent_contact', '')}

## 学习特点
{info_data.get('learning_traits', '')}

# 历史评价

"""

    with open(student_dir / 'profile.md', 'w', encoding='utf-8') as f:
        f.write(info_content)

    print(f"✓ 创建学生: {class_name}/{student_name}")

def main():
    print("=" * 50)
    print("🎓 初始化示例数据")
    print("=" * 50)

    # Python基础班示例学生
    python_students = [
        {
            'name': '张三',
            'age': 10,
            'grade': '四年级',
            'enrollment_date': '2024-01-15',
            'personality': '活泼外向',
            'parent_contact': '- 妈妈: 138xxxx1234',
            'learning_traits': '- 喜欢动手实践\n- 乐于帮助同学'
        },
        {
            'name': '李四',
            'age': 9,
            'grade': '三年级',
            'enrollment_date': '2024-02-01',
            'personality': '安静内向',
            'parent_contact': '- 爸爸: 139xxxx5678',
            'learning_traits': '- 专注力强\n- 独立思考'
        },
        {
            'name': '王五',
            'age': 11,
            'grade': '五年级',
            'enrollment_date': '2024-01-10',
            'personality': '完美主义型',
            'parent_contact': '- 妈妈: 137xxxx9012',
            'learning_traits': '- 对自己要求高\n- 细节把控好'
        },
    ]

    for student in python_students:
        create_student('Python基础班', student['name'], student)

    # C++启蒙班示例学生
    cpp_students = [
        {
            'name': '小明',
            'age': 10,
            'grade': '四年级',
            'enrollment_date': '2024-01-20',
            'personality': '好胜竞争型',
            'parent_contact': '- 爸爸: 136xxxx3456',
            'learning_traits': '- 喜欢挑战难题\n- 追求排名'
        },
        {
            'name': '小红',
            'age': 11,
            'grade': '五年级',
            'enrollment_date': '2024-01-25',
            'personality': '安静内向',
            'parent_contact': '- 妈妈: 135xxxx7890',
            'learning_traits': '- 基础扎实\n- 需要更多的鼓励'
        },
    ]

    for student in cpp_students:
        create_student('C++启蒙班', student['name'], student)

    print("\n✅ 示例数据初始化完成！")
    print("可以运行 `python run.py` 启动Web界面")

if __name__ == '__main__':
    main()
