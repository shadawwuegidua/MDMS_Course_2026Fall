"""Pure business-rule tests. No database or HTTP server is needed."""

import copy
import unittest

from logic import (
    ValidationError, build_statistics, next_question_id, normalize_questions,
    validate_answer, validate_submission,
)


def question(question_id="q1", kind="single", required=True, validation=None, rules=None):
    return {"id": question_id, "title": question_id, "type": kind,
            "required": required,
            "options": [{"id": "a", "text": "A"}, {"id": "b", "text": "B"}, {"id": "c", "text": "C"}]
            if kind in {"single", "multiple"} else [],
            "validation": validation or {}, "rules": rules or []}


class QuestionDefinitionTests(unittest.TestCase):
    def test_empty_draft(self):
        self.assertEqual(normalize_questions([]), [])

    def test_generated_ids_are_returned_and_preserved(self):
        raw = question()
        del raw["id"]
        del raw["options"][0]["id"]
        normalized = normalize_questions([raw])
        self.assertTrue(normalized[0]["id"].startswith("q_"))
        self.assertTrue(normalized[0]["options"][0]["id"].startswith("opt_"))
        self.assertEqual(normalize_questions(normalized), normalized)
        self.assertNotIn("id", raw)

    def test_duplicate_question_and_option_ids(self):
        with self.assertRaises(ValidationError):
            normalize_questions([question(), question()])
        raw = question()
        raw["options"][1]["id"] = "a"
        with self.assertRaises(ValidationError):
            normalize_questions([raw])

    def test_invalid_types_and_inconsistent_ranges(self):
        invalid = [question(kind="unknown"),
                   question(kind="multiple", validation={"min_choices": 3, "max_choices": 2}),
                   question(kind="multiple", validation={"min_choices": 4}),
                   question(kind="text", validation={"min_length": -1}),
                   question(kind="number", validation={"min_value": 10, "max_value": 1}),
                   question(kind="number", validation={"min_value": 1.2, "max_value": 1.8, "integer_only": True})]
        for raw in invalid:
            with self.subTest(raw=raw), self.assertRaises(ValidationError):
                normalize_questions([raw])

    def test_rejects_backward_unknown_and_wrong_type_rules(self):
        for target, operator, value in [("q1", "eq", "a"), ("missing", "eq", "a"),
                                        ("q2", "contains", "a"), ("q2", "eq", "missing")]:
            with self.subTest(target=target, operator=operator, value=value), self.assertRaises(ValidationError):
                normalize_questions([question(rules=[{"operator": operator, "value": value, "target_id": target}]), question("q2")])

    def test_rejects_malformed_definition_values(self):
        values = [None, {}, "text", [None], [question(kind="text", rules=[{}])]]
        for raw in values:
            with self.subTest(raw=raw), self.assertRaises(ValidationError):
                normalize_questions(raw)

    def test_relevant_validation_and_string_numbers(self):
        raw = question(kind="number", validation={"min_value": "0", "max_value": "120", "integer_only": True, "max_choices": 2})
        normalized = normalize_questions([raw])[0]
        self.assertEqual(normalized["validation"], {"min_value": 0, "max_value": 120, "integer_only": True})

    def test_required_zero_maximum_is_rejected_but_optional_can_be_blank(self):
        for kind, field in [("multiple", "max_choices"), ("text", "max_length")]:
            with self.subTest(kind=kind):
                with self.assertRaises(ValidationError) as raised:
                    normalize_questions([question(kind=kind, validation={field: 0})])
                self.assertEqual(raised.exception.question_id, "q1")
                optional = normalize_questions([
                    question(kind=kind, required=False, validation={field: 0})])[0]
                self.assertEqual(optional["validation"][field], 0)
                self.assertIsNone(validate_answer(optional, None))


class AnswerTests(unittest.TestCase):
    def test_required_and_optional_empty(self):
        for value in [None, "", "  ", []]:
            with self.subTest(value=value), self.assertRaises(ValidationError):
                validate_answer(question(), value)
            self.assertIsNone(validate_answer(question(required=False), value))

    def test_single_rejects_unknown_or_wrong_shape(self):
        self.assertEqual(validate_answer(question(), "b"), "b")
        for value in ["z", ["a"], 0, True]:
            with self.subTest(value=value), self.assertRaises(ValidationError):
                validate_answer(question(), value)

    def test_multiple_exact_count_duplicates_and_unknown(self):
        raw = question(kind="multiple", validation={"min_choices": 2, "max_choices": 2})
        self.assertEqual(validate_answer(raw, ["b", "a"]), ["a", "b"])
        for value in [["a"], ["a", "b", "c"], ["a", "a"], ["a", "z"], "a", [False]]:
            with self.subTest(value=value), self.assertRaises(ValidationError):
                validate_answer(raw, value)

    def test_unicode_text_length_and_trim(self):
        raw = question(kind="text", validation={"min_length": 2, "max_length": 3})
        self.assertEqual(validate_answer(raw, " 中文 "), "中文")
        self.assertEqual(validate_answer(raw, "学习好"), "学习好")
        for value in ["中", "当代数据库", 12]:
            with self.subTest(value=value), self.assertRaises(ValidationError):
                validate_answer(raw, value)

    def test_numeric_bounds_integer_and_normalization(self):
        raw = question(kind="number", validation={"min_value": 0, "max_value": 120, "integer_only": True})
        self.assertEqual(validate_answer(raw, "20.0"), 20)
        self.assertEqual(validate_answer(raw, "0"), 0)
        self.assertEqual(validate_answer(raw, 120), 120)
        for value in ["-1", 121, "1.5", True, {}, "abc", "NaN", "Infinity", float("inf"), 2**63]:
            with self.subTest(value=value), self.assertRaises(ValidationError):
                validate_answer(raw, value)

    def test_optional_blank_bypasses_minimum(self):
        raw = question(kind="text", required=False, validation={"min_length": 3})
        self.assertIsNone(validate_answer(raw, ""))
        with self.assertRaises(ValidationError):
            validate_answer(raw, "a")

    def test_finite_decimal_number(self):
        self.assertAlmostEqual(validate_answer(question(kind="number"), "1.25"), 1.25)
        for value in ["1e9999", "1e-9999"]:
            with self.subTest(value=value), self.assertRaises(ValidationError):
                validate_answer(question(kind="number"), value)


class BranchingTests(unittest.TestCase):
    def make_branch(self, kind, value, operator):
        return normalize_questions([
            question("q1", kind, rules=[{"operator": operator, "value": value, "target_id": "q3"}]),
            question("q2", "text"), question("q3", "text"),
        ])

    def test_single_jump_and_skipped_required(self):
        questions = self.make_branch("single", "a", "eq")
        answers = validate_submission(questions, {"q1": "a", "q2": [], "q3": "完成"})
        self.assertEqual(answers, {"q1": "a", "q3": "完成"})
        self.assertNotIn("q2", answers)

    def test_multiple_and_numeric_jump(self):
        for kind, expected, operator, answer in [("multiple", "b", "contains", ["a", "b"]),
                                                  ("number", 18, "lt", "17")]:
            with self.subTest(kind=kind):
                questions = self.make_branch(kind, expected, operator)
                answers = validate_submission(questions, {"q1": answer, "q3": "完成"})
                self.assertNotIn("q2", answers)

    def test_default_path_and_last_question(self):
        questions = self.make_branch("single", "a", "eq")
        self.assertEqual(next_question_id(questions, "q1", "b"), "q2")
        self.assertIsNone(next_question_id(questions, "q3", "完成"))
        with self.assertRaises(ValidationError) as raised:
            validate_submission(questions, {"q1": "b", "q3": "完成"})
        self.assertEqual(raised.exception.question_id, "q2")

    def test_rule_order_and_numeric_boundaries(self):
        questions = normalize_questions([
            question("q1", "number", rules=[
                {"operator": "gte", "value": 18, "target_id": "q2"},
                {"operator": "gt", "value": 10, "target_id": "q3"}]),
            question("q2", "text"), question("q3", "text"),
        ])
        self.assertEqual(next_question_id(questions, "q1", 18), "q2")
        self.assertEqual(next_question_id(questions, "q1", 17), "q3")
        for operator, value in [("eq", 18), ("lte", 18), ("lt", 18.1), ("gt", 17.9), ("gte", 18)]:
            with self.subTest(operator=operator):
                changed = copy.deepcopy(questions)
                changed[0]["rules"] = [{"operator": operator, "value": value, "target_id": "q3"}]
                self.assertEqual(next_question_id(changed, "q1", 18), "q3")

    def test_optional_null_and_unknown_answer_rejection(self):
        questions = normalize_questions([question("q1", "text", required=False), question("q2", "text")])
        self.assertEqual(validate_submission(questions, {"q2": "完成"}), {"q1": None, "q2": "完成"})
        with self.assertRaises(ValidationError):
            validate_submission(questions, {"q2": "完成", "fake": "x"})
        with self.assertRaises(ValidationError):
            validate_submission(questions, [])


class StatisticsTests(unittest.TestCase):
    def test_counts_values_mean_and_no_identity(self):
        survey = {"questions": normalize_questions([
            question("s"), question("m", "multiple"), question("t", "text", False), question("n", "number", False)])}
        responses = [
            {"respondent_id": "secret1", "answers": {"s": "a", "m": ["a", "b"], "t": "意见一", "n": 10}},
            {"respondent_id": "secret2", "answers": {"s": "a", "m": ["b"], "t": None, "n": 20}},
            {"respondent_id": "secret3", "answers": {"s": "b", "n": None}},
        ]
        stats = build_statistics(survey, responses)
        self.assertEqual(stats["total_responses"], 3)
        single, multiple, text, numeric = stats["questions"]
        self.assertEqual(single["answered"], 3)
        self.assertEqual([x["count"] for x in single["options"]], [2, 1, 0])
        self.assertEqual(multiple["answered"], 2)
        self.assertEqual([x["count"] for x in multiple["options"]], [1, 2, 0])
        self.assertEqual(text["values"], ["意见一"])
        self.assertEqual(numeric["average"], 15)
        self.assertEqual(numeric["answered"], 2)
        self.assertNotIn("secret", str(stats))

    def test_empty_statistics(self):
        stats = build_statistics({"questions": normalize_questions([question(kind="number")])}, [])
        self.assertEqual(stats["total_responses"], 0)
        self.assertEqual(stats["questions"][0]["answered"], 0)
        self.assertIsNone(stats["questions"][0]["average"])

    def test_small_finite_values_do_not_underflow_before_averaging(self):
        stats = build_statistics({"questions": [question(kind="number")]}, [
            {"answers": {"q1": 5e-324}}, {"answers": {"q1": 5e-324}}])
        self.assertEqual(stats["questions"][0]["average"], 5e-324)


if __name__ == "__main__":
    unittest.main()
