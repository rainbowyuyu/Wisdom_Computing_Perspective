"""Reject explicit batches, without confusing one problem's subquestions/matrices."""
import re

SINGLE_PROBLEM_MESSAGE = '每次请只提交一道完整题目。请裁剪到一道题，保留题干、图形和该题的小问后再试。'


def multiple_problems(text):
    text = str(text or '')
    if len(re.findall(r'第[一二三四五六七八九十\d]+题', text)) >= 2: return True
    # Parenthesized labels (1)/(2), simultaneous equations and decimal numbers
    # are deliberately not treated as independent questions.
    return len(re.findall(r'^\s*\d{1,3}[.．、]\s*(?=[^\d\s])', text, re.M)) >= 2
