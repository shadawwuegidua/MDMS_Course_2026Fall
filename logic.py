"""Question definitions, answer checking, branching and result statistics.

These functions do not access MongoDB or Flask.  The server uses the same rules
for a single-question preview and for the final submission.
"""

import math
import re
import secrets
from decimal import Decimal, InvalidOperation


QUESTION_TYPES = {"single", "multiple", "text", "number"}
IDENTIFIER = re.compile(r"^[A-Za-z0-9_-]{1,64}$")
INT64_MIN = -(2**63)
INT64_MAX = 2**63 - 1


class ValidationError(ValueError):
    def __init__(self, message, question_id=None):
        super().__init__(message)
        self.question_id = question_id


def _fail(message, question_id=None):
    raise ValidationError(message, question_id)


def _text(value, label, question_id=None):
    if not isinstance(value, str) or not value.strip():
        _fail(f"{label}不能为空", question_id)
    text = value.strip()
    try:
        text.encode("utf-8")
    except UnicodeEncodeError:
        _fail(f"{label}包含无效字符", question_id)
    return text


def _identifier(value, prefix, question_id=None):
    if value is None or value == "":
        return prefix + secrets.token_hex(6)
    if not isinstance(value, str) or not IDENTIFIER.fullmatch(value):
        _fail("题目和选项标识只能包含字母、数字、下划线或连字符，最长64位", question_id)
    return value


def _number(value, label, question_id=None):
    """Return a finite BSON-compatible int/float without accepting booleans."""
    if isinstance(value, bool) or not isinstance(value, (str, int, float, Decimal)):
        _fail(f"{label}必须是有效数字", question_id)
    try:
        decimal = Decimal(value.strip() if isinstance(value, str) else str(value))
    except (InvalidOperation, ValueError):
        _fail(f"{label}必须是有效数字", question_id)
    if not decimal.is_finite():
        _fail(f"{label}必须是有限数字", question_id)
    if decimal == decimal.to_integral_value():
        if not INT64_MIN <= decimal <= INT64_MAX:
            _fail(f"{label}超出可保存的整数范围", question_id)
        return int(decimal)
    converted = float(decimal)
    if not math.isfinite(converted) or (converted == 0 and decimal != 0):
        _fail(f"{label}超出可保存的数字范围", question_id)
    return converted


def _integer(value, label, question_id=None):
    number = _number(value, label, question_id)
    if not isinstance(number, int) or not 0 <= number <= 2**31 - 1:
        _fail(f"{label}必须是非负整数", question_id)
    return number


def _empty(value):
    return (value is None or
            (isinstance(value, str) and not value.strip()) or
            (isinstance(value, list) and len(value) == 0))


def _normalize_validation(raw, kind, option_count, question_id):
    if raw is None:
        raw = {}
    if not isinstance(raw, dict):
        _fail("校验设置必须是对象", question_id)
    validation = {}
    fields = {
        "multiple": ("min_choices", "max_choices"),
        "text": ("min_length", "max_length"),
        "number": ("min_value", "max_value"),
    }.get(kind, ())
    for field in fields:
        value = raw.get(field)
        if value is None or value == "":
            continue
        converter = _number if kind == "number" else _integer
        validation[field] = converter(value, field, question_id)
    if fields:
        lower, upper = fields
        if lower in validation and upper in validation and validation[lower] > validation[upper]:
            _fail("最小限制不能大于最大限制", question_id)
    if kind == "multiple":
        if any(value > option_count for value in validation.values()):
            _fail("选择数量限制不能超过选项数", question_id)
    if kind == "number":
        integer_only = raw.get("integer_only", False)
        if not isinstance(integer_only, bool):
            _fail("是否必须为整数需要使用布尔值", question_id)
        validation["integer_only"] = integer_only
        if integer_only:
            lower = validation.get("min_value")
            upper = validation.get("max_value")
            if lower is not None and upper is not None and math.ceil(lower) > math.floor(upper):
                _fail("当前数值范围中不存在整数", question_id)
    return validation


def normalize_questions(raw_questions):
    """Validate editable question definitions and return their canonical form."""
    if not isinstance(raw_questions, list):
        _fail("题目必须是数组")
    questions = []
    raw_rules = []
    seen_ids = set()
    for raw in raw_questions:
        if not isinstance(raw, dict):
            _fail("每道题目必须是对象")
        question_id = _identifier(raw.get("id"), "q_")
        if question_id in seen_ids:
            _fail("题目标识不能重复", question_id)
        seen_ids.add(question_id)
        kind = raw.get("type")
        if not isinstance(kind, str) or kind not in QUESTION_TYPES:
            _fail("不支持的题型", question_id)
        required = raw.get("required", False)
        if not isinstance(required, bool):
            _fail("是否必答需要使用布尔值", question_id)
        options = []
        if kind in {"single", "multiple"}:
            source_options = raw.get("options", [])
            if not isinstance(source_options, list) or len(source_options) < 2:
                _fail("选择题至少需要两个选项", question_id)
            option_ids = set()
            for option in source_options:
                if not isinstance(option, dict):
                    _fail("选项必须包含标识和文字", question_id)
                option_id = _identifier(option.get("id"), "opt_", question_id)
                if option_id in option_ids:
                    _fail("同一道题的选项标识不能重复", question_id)
                option_ids.add(option_id)
                options.append({"id": option_id, "text": _text(option.get("text"), "选项文字", question_id)})
        rules = raw.get("rules", [])
        if not isinstance(rules, list):
            _fail("跳转规则必须是数组", question_id)
        if kind == "text" and rules:
            _fail("文本填空不支持跳转规则", question_id)
        validation = _normalize_validation(raw.get("validation", {}), kind, len(options), question_id)
        if required and kind == "multiple" and validation.get("max_choices") == 0:
            _fail("必答多选题的最多选择数量不能为0", question_id)
        if required and kind == "text" and validation.get("max_length") == 0:
            _fail("必答文本题的最大长度不能为0", question_id)
        questions.append({
            "id": question_id,
            "title": _text(raw.get("title"), "题目标题", question_id),
            "type": kind,
            "required": required,
            "options": options,
            "validation": validation,
            "rules": [],
        })
        raw_rules.append(rules)

    positions = {question["id"]: index for index, question in enumerate(questions)}
    for index, question in enumerate(questions):
        question_id, kind = question["id"], question["type"]
        for rule in raw_rules[index]:
            if not isinstance(rule, dict):
                _fail("每条跳转规则必须是对象", question_id)
            operator = rule.get("operator")
            allowed = {"single": {"eq"}, "multiple": {"contains"},
                       "number": {"eq", "gt", "gte", "lt", "lte"}, "text": set()}[kind]
            if not isinstance(operator, str) or operator not in allowed:
                _fail("跳转比较方式与题型不匹配", question_id)
            target = rule.get("target_id")
            if not isinstance(target, str) or target not in positions:
                _fail("跳转目标题目不存在", question_id)
            if positions[target] <= index:
                _fail("只允许跳转到后面的题目", question_id)
            value = rule.get("value")
            if kind == "number":
                value = _number(value, "跳转比较值", question_id)
            elif not isinstance(value, str) or value not in {option["id"] for option in question["options"]}:
                _fail("跳转条件引用了不存在的选项", question_id)
            question["rules"].append({"operator": operator, "value": value, "target_id": target})
    return questions


def validate_answer(question, raw):
    """Validate one answer, including limits, and return its saved value."""
    question_id = question["id"]
    if _empty(raw):
        if question.get("required", False):
            _fail("这道题必须回答", question_id)
        return None
    kind = question["type"]
    validation = question.get("validation", {})
    option_ids = [option["id"] for option in question.get("options", [])]
    if kind == "single":
        if not isinstance(raw, str) or raw not in option_ids:
            _fail("请选择该题的一个有效选项", question_id)
        return raw
    if kind == "multiple":
        if not isinstance(raw, list) or any(not isinstance(value, str) or value not in option_ids for value in raw):
            _fail("请选择该题的有效选项", question_id)
        if len(set(raw)) != len(raw):
            _fail("不能重复选择同一个选项", question_id)
        count = len(raw)
        if count < validation.get("min_choices", 0):
            _fail(f"至少选择 {validation['min_choices']} 项", question_id)
        if count > validation.get("max_choices", len(option_ids)):
            _fail(f"最多选择 {validation['max_choices']} 项", question_id)
        return [option_id for option_id in option_ids if option_id in raw]
    if kind == "text":
        text = _text(raw, "填写内容", question_id)
        if len(text) < validation.get("min_length", 0):
            _fail(f"至少输入 {validation['min_length']} 个字符", question_id)
        if "max_length" in validation and len(text) > validation["max_length"]:
            _fail(f"最多输入 {validation['max_length']} 个字符", question_id)
        return text
    if kind == "number":
        value = _number(raw, "填写内容", question_id)
        if validation.get("integer_only", False) and not isinstance(value, int):
            _fail("请输入整数", question_id)
        if "min_value" in validation and value < validation["min_value"]:
            _fail(f"数值不能小于 {validation['min_value']}", question_id)
        if "max_value" in validation and value > validation["max_value"]:
            _fail(f"数值不能大于 {validation['max_value']}", question_id)
        return value
    _fail("不支持的题型", question_id)


def next_question_id(questions, question_id, answer):
    """Return first matching forward target, or the following question."""
    positions = {question["id"]: index for index, question in enumerate(questions)}
    if question_id not in positions:
        _fail("题目不存在", question_id)
    index = positions[question_id]
    question = questions[index]
    if answer is not None:
        for rule in question.get("rules", []):
            operator, expected = rule["operator"], rule["value"]
            matches = False
            if operator == "eq":
                matches = answer == expected
            elif operator == "contains":
                matches = isinstance(answer, list) and expected in answer
            elif operator == "gt":
                matches = answer > expected
            elif operator == "gte":
                matches = answer >= expected
            elif operator == "lt":
                matches = answer < expected
            elif operator == "lte":
                matches = answer <= expected
            if matches:
                target = rule["target_id"]
                if target not in positions or positions[target] <= index:
                    _fail("跳转目标必须是后面的题目", question_id)
                return target
    return questions[index + 1]["id"] if index + 1 < len(questions) else None


def validate_submission(questions, raw_answers):
    """Recompute the reachable path; ignored branch answers are never saved."""
    if not isinstance(raw_answers, dict):
        _fail("答案必须是对象")
    by_id = {question["id"]: question for question in questions}
    if any(question_id not in by_id for question_id in raw_answers):
        _fail("答案包含不属于该问卷的题目")
    answers = {}
    current = questions[0]["id"] if questions else None
    while current is not None:
        if current in answers:
            _fail("跳转规则形成循环", current)
        question = by_id[current]
        answer = validate_answer(question, raw_answers.get(current))
        answers[current] = answer
        current = next_question_id(questions, current, answer)
    return answers


def build_statistics(survey, responses):
    """Calculate live statistics without exposing any respondent metadata."""
    responses = list(responses)
    results = []
    for question in survey.get("questions", []):
        question_id, kind = question["id"], question["type"]
        values = [response.get("answers", {}).get(question_id) for response in responses]
        values = [value for value in values if value is not None]
        result = {"id": question_id, "title": question["title"], "type": kind,
                  "answered": len(values), "options": [], "values": [], "average": None}
        if kind in {"single", "multiple"}:
            for option in question.get("options", []):
                if kind == "single":
                    count = sum(value == option["id"] for value in values)
                else:
                    count = sum(isinstance(value, list) and option["id"] in value for value in values)
                result["options"].append({"id": option["id"], "text": option["text"], "count": count})
        else:
            result["values"] = values
            if kind == "number" and values:
                try:
                    result["average"] = math.fsum(values) / len(values)
                except OverflowError:
                    # Scale only when needed; doing it unconditionally could
                    # round very small finite values to zero before summing.
                    result["average"] = math.fsum(value / len(values) for value in values)
        results.append(result)
    return {"total_responses": len(responses), "questions": results}
