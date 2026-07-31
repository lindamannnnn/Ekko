"""姓名脱敏与还原。

发送 AI 前把学生姓名/昵称/同学姓名替换成占位符，返回后还原。
一举三得：① 未成年人信息合规 ② 防止 AI 玩谐音梗 ③ 主管问责有说法。
few-shot 样本同样需要脱敏，避免 AI 套用样本里的真名。
"""
import re

# 占位符约定
STU = "{{STU}}"           # 当前学生本名
STU_NICK = "{{STU_NICK}}" # 当前学生昵称
PEER_TPL = "{{PEER_{}}}}"  # 同学姓名，n 从 1 递增


class Redactor:
    def __init__(self, student_name, student_nick=None, peer_names=None):
        self.student_name = student_name or ""
        self.student_nick = student_nick or ""
        self.peers = [p for p in (peer_names or []) if p and p != self.student_name]
        self._map = {}   # 真名 -> 占位符
        self._inv = {}   # 占位符 -> 真名

    def _register(self, real, placeholder):
        self._map[real] = placeholder
        self._inv[placeholder] = real

    def redact(self, text: str) -> str:
        if not text:
            return text
        out = text
        # 先注册，按长度从长到短替换，避免短名误伤长名子串
        # 同学姓名
        for i, p in enumerate(self.peers, start=1):
            self._register(p, PEER_TPL.format(i))
        # 本人：先昵称后本名（昵称通常更短，避免本名是其子串时冲突）
        if self.student_nick and self.student_nick != self.student_name:
            self._register(self.student_nick, STU_NICK)
        if self.student_name:
            self._register(self.student_name, STU)

        for real in sorted(self._map.keys(), key=len, reverse=True):
            out = out.replace(real, self._map[real])
        return out

    def restore(self, text: str) -> str:
        if not text:
            return text
        out = text
        # 还原同样按占位符长度从长到短
        for ph in sorted(self._inv.keys(), key=len, reverse=True):
            out = out.replace(ph, self._inv[ph])
        return out


def redact_student_text(text, student_name, student_nick=None, peer_names=None):
    return Redactor(student_name, student_nick, peer_names).redact(text)


def restore_student_text(text, student_name, student_nick=None, peer_names=None):
    # 还原时占位符映射与脱敏一致
    return Redactor(student_name, student_nick, peer_names).restore(text)
