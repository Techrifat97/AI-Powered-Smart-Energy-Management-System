import unittest

from backend.coach.domain.feedback import RecommendationFeedback
from backend.coach.domain.llm_log import LLMRequestLog
from backend.coach.domain.recommendation import AIRecommendation
from backend.coach.errors import (
    CoachError,
    CoachErrorHandler,
    CoachTypeError,
    InvalidFeedbackError,
    InvalidLLMLogError,
    InvalidRecommendationError,
)


class CoachExceptionTests(unittest.TestCase):
    def test_hierarchy_keeps_builtin_compatibility(self):
        self.assertTrue(issubclass(InvalidFeedbackError, CoachError))
        self.assertTrue(issubclass(InvalidFeedbackError, ValueError))
        self.assertTrue(issubclass(CoachTypeError, TypeError))

    def test_feedback_rating_out_of_range_raises_invalid_feedback(self):
        with self.assertRaises(InvalidFeedbackError):
            RecommendationFeedback(99)

    def test_feedback_rating_wrong_type_raises_coach_type_error(self):
        with self.assertRaises(CoachTypeError):
            RecommendationFeedback("five")

    def test_llm_log_empty_model_raises_invalid_llm_log(self):
        with self.assertRaises(InvalidLLMLogError):
            LLMRequestLog("")

    def test_recommendation_empty_title_raises_invalid_recommendation(self):
        with self.assertRaises(InvalidRecommendationError):
            AIRecommendation("", 5)


class CoachErrorHandlerTests(unittest.TestCase):
    def test_safe_call_turns_error_into_result_with_code(self):
        result = CoachErrorHandler().safe_call(LLMRequestLog, "")
        self.assertFalse(result["ok"])
        self.assertEqual(result["code"], "INVALID_LLM_LOG")


if __name__ == "__main__":
    unittest.main()
