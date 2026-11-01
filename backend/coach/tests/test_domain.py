import unittest

from backend.coach.domain.feedback import RecommendationFeedback
from backend.coach.domain.llm_log import LLMRequestLog
from backend.coach.domain.recommendation import AIRecommendation


class RecommendationFeedbackTests(unittest.TestCase):
    def setUp(self):
        self.fb = RecommendationFeedback(feedback_id=1, rating=5, comment="Great insight!")

    def test_initialization_and_getters(self):
        self.assertEqual(self.fb.get_id(), 1)
        self.assertEqual(self.fb.get_rating(), 5)
        self.assertEqual(self.fb.get_comment(), "Great insight!")
        self.assertIsNotNone(self.fb.get_created_at())

    def test_is_positive(self):
        self.assertTrue(self.fb.is_positive())
        self.fb.set_rating(4)
        self.assertTrue(self.fb.is_positive())
        self.fb.set_rating(3)
        self.assertFalse(self.fb.is_positive())
        self.fb.set_rating(1)
        self.assertFalse(self.fb.is_positive())

    def test_rating_validation(self):
        with self.assertRaises(ValueError):
            self.fb.set_rating(0)
        with self.assertRaises(ValueError):
            self.fb.set_rating(6)
        with self.assertRaises(TypeError):
            self.fb.set_rating("5")

    def test_comment_setter(self):
        self.fb.set_comment("  Trimmed comment  ")
        self.assertEqual(self.fb.get_comment(), "Trimmed comment")
        self.fb.set_comment(None)
        self.assertEqual(self.fb.get_comment(), "")
        with self.assertRaises(TypeError):
            self.fb.set_comment(12345)


class LLMRequestLogTests(unittest.TestCase):
    def setUp(self):
        self.log = LLMRequestLog(
            log_id=101,
            model_name="gemini-1.5-pro",
            prompt_hash="abc123hash",
        )

    def test_initialization_and_defaults(self):
        self.assertEqual(self.log.get_id(), 101)
        self.assertEqual(self.log.get_model_name(), "gemini-1.5-pro")
        self.assertEqual(self.log.get_prompt_hash(), "abc123hash")
        self.assertEqual(self.log.get_tokens_used(), 0)
        self.assertEqual(self.log.get_latency_ms(), 0)
        self.assertEqual(self.log.get_status(), "PENDING")
        self.assertIsNotNone(self.log.get_created_at())

    def test_record_with_positional_arguments(self):
        self.log.record(tokens_used=240, latency_ms=450, status="SUCCESS")
        self.assertEqual(self.log.get_tokens_used(), 240)
        self.assertEqual(self.log.get_latency_ms(), 450)
        self.assertEqual(self.log.get_status(), "SUCCESS")

    def test_record_with_dict(self):
        self.log.record({"tokens_used": 180, "latency_ms": 310, "status": "SUCCESS"})
        self.assertEqual(self.log.get_tokens_used(), 180)
        self.assertEqual(self.log.get_latency_ms(), 310)
        self.assertEqual(self.log.get_status(), "SUCCESS")

    def test_validation(self):
        with self.assertRaises(ValueError):
            self.log.set_model_name("")
        with self.assertRaises(ValueError):
            self.log.set_prompt_hash("")
        with self.assertRaises(ValueError):
            self.log.set_tokens_used(-5)
        with self.assertRaises(ValueError):
            self.log.set_latency_ms(-10)
        with self.assertRaises(ValueError):
            self.log.set_status("UNKNOWN_STATUS")


class AIRecommendationTests(unittest.TestCase):
    def setUp(self):
        self.rec = AIRecommendation(
            recommendation_id=1,
            title="Pre-cool during off-peak",
            description="Shift HVAC load 1 hour earlier to leverage lower electricity tariffs.",
            category="HVAC",
            est_saving_kwh=120.5,
            est_saving_pct=15.0,
            priority="HIGH",
        )

    def test_initialization_and_getters(self):
        self.assertEqual(self.rec.get_id(), 1)
        self.assertEqual(self.rec.get_title(), "Pre-cool during off-peak")
        self.assertEqual(self.rec.get_category(), "HVAC")
        self.assertEqual(self.rec.get_est_saving_kwh(), 120.5)
        self.assertEqual(self.rec.get_est_saving_pct(), 15.0)
        self.assertEqual(self.rec.get_priority(), "HIGH")
        self.assertEqual(self.rec.get_status(), "NEW")
        self.assertFalse(self.rec.get_is_fallback())
        self.assertEqual(self.rec.get_feedbacks(), [])
        self.assertIsNone(self.rec.get_llm_log())

    def test_set_status(self):
        self.rec.set_status("ACCEPTED")
        self.assertEqual(self.rec.get_status(), "ACCEPTED")
        self.rec.set_status("IMPLEMENTED")
        self.assertEqual(self.rec.get_status(), "IMPLEMENTED")
        with self.assertRaises(ValueError):
            self.rec.set_status("INVALID_STATUS")

    def test_validation(self):
        with self.assertRaises(ValueError):
            self.rec.set_title("")
        with self.assertRaises(ValueError):
            self.rec.set_description("")
        with self.assertRaises(ValueError):
            self.rec.set_category("")
        with self.assertRaises(ValueError):
            self.rec.set_est_saving_kwh(-1.0)
        with self.assertRaises(ValueError):
            self.rec.set_est_saving_pct(105.0)
        with self.assertRaises(ValueError):
            self.rec.set_priority("URGENT")

    def test_feedbacks_composition(self):
        fb1 = RecommendationFeedback(1, 5, "Excellent suggestion")
        fb2 = RecommendationFeedback(2, 3, "Moderate improvement")
        self.rec.add_feedback(fb1)
        self.rec.add_feedback(fb2)

        feedbacks = self.rec.get_feedbacks()
        self.assertEqual(len(feedbacks), 2)
        self.assertEqual(self.rec.average_feedback_rating(), 4.0)

        with self.assertRaises(TypeError):
            self.rec.add_feedback("Not a feedback object")

    def test_llm_log_association(self):
        log = LLMRequestLog(1, "gpt-4o", "hash999")
        self.rec.set_llm_log(log)
        self.assertEqual(self.rec.get_llm_log(), log)

        with self.assertRaises(TypeError):
            self.rec.set_llm_log("not_a_log")

    def test_is_actionable(self):
        self.assertTrue(self.rec.is_actionable())
        self.rec.set_status("ACCEPTED")
        self.assertTrue(self.rec.is_actionable())
        self.rec.set_status("DISMISSED")
        self.assertFalse(self.rec.is_actionable())
        self.rec.set_status("IMPLEMENTED")
        self.assertFalse(self.rec.is_actionable())


if __name__ == "__main__":
    unittest.main()
