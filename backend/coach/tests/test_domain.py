import unittest
from decimal import Decimal

from backend.coach.domain.feedback import RecommendationFeedback
from backend.coach.domain.llm_log import LLMRequestLog
from backend.coach.domain.recommendation import AIRecommendation


class RecommendationFeedbackTests(unittest.TestCase):
    def setUp(self):
        self.fb = RecommendationFeedback(rating=5, comment="Great insight!")

    def test_initialization_and_getters(self):
        self.assertEqual(self.fb.get_rating(), 5)
        self.assertEqual(self.fb.get_comment(), "Great insight!")

    def test_validate(self):
        self.assertTrue(self.fb.validate())
        self.fb.set_rating(1)
        self.assertTrue(self.fb.validate())

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
            model="gpt-4o",
            latency_ms=250,
            success=True,
        )

    def test_initialization_and_defaults(self):
        self.assertEqual(self.log.get_model(), "gpt-4o")
        self.assertEqual(self.log.get_latency_ms(), 250)
        self.assertTrue(self.log.get_success())
        self.assertIsNotNone(self.log.get_recorded_at())

    def test_record_no_arguments(self):
        old_time = self.log.get_recorded_at()
        self.log.record()
        self.assertIsNotNone(self.log.get_recorded_at())

    def test_record_with_arguments(self):
        self.log.record(latency_ms=450, success=False)
        self.assertEqual(self.log.get_latency_ms(), 450)
        self.assertFalse(self.log.get_success())

    def test_validation(self):
        with self.assertRaises(ValueError):
            self.log.set_model("")
        with self.assertRaises(ValueError):
            self.log.set_latency_ms(-10)
        with self.assertRaises(TypeError):
            self.log.set_success("true")


class AIRecommendationTests(unittest.TestCase):
    def setUp(self):
        self.rec = AIRecommendation(
            title="Pre-cool during off-peak",
            saving_kwh=Decimal("120.5"),
            source="LLM",
        )

    def test_initialization_and_getters(self):
        self.assertEqual(self.rec.get_title(), "Pre-cool during off-peak")
        self.assertEqual(self.rec.get_saving_kwh(), Decimal("120.5"))
        self.assertEqual(self.rec.get_source(), "LLM")
        self.assertEqual(self.rec.get_status(), "NEW")
        self.assertEqual(self.rec.get_feedbacks(), [])

    def test_accept(self):
        self.assertEqual(self.rec.get_status(), "NEW")
        self.rec.accept()
        self.assertEqual(self.rec.get_status(), "ACCEPTED")

    def test_dismiss(self):
        self.assertEqual(self.rec.get_status(), "NEW")
        self.rec.dismiss()
        self.assertEqual(self.rec.get_status(), "DISMISSED")

    def test_saving_kwh_decimal_handling(self):
        self.rec.set_saving_kwh(50)
        self.assertEqual(self.rec.get_saving_kwh(), Decimal("50"))

        self.rec.set_saving_kwh(75.25)
        self.assertEqual(self.rec.get_saving_kwh(), Decimal("75.25"))

        self.rec.set_saving_kwh("100.50")
        self.assertEqual(self.rec.get_saving_kwh(), Decimal("100.50"))

        with self.assertRaises(ValueError):
            self.rec.set_saving_kwh(-5.0)

        with self.assertRaises(TypeError):
            self.rec.set_saving_kwh([10])

    def test_source_validation(self):
        self.rec.set_source("rules")
        self.assertEqual(self.rec.get_source(), "rules")
        self.rec.set_source("llm")
        self.assertEqual(self.rec.get_source(), "LLM")

        with self.assertRaises(ValueError):
            self.rec.set_source("external_api")

    def test_feedbacks_composition(self):
        fb1 = RecommendationFeedback(rating=5, comment="Very helpful")
        fb2 = RecommendationFeedback(rating=4, comment="Good advice")
        self.rec.add_feedback(fb1)
        self.rec.add_feedback(fb2)

        feedbacks = self.rec.get_feedbacks()
        self.assertEqual(len(feedbacks), 2)
        self.assertEqual(feedbacks[0].get_rating(), 5)
        self.assertEqual(feedbacks[1].get_rating(), 4)

        with self.assertRaises(TypeError):
            self.rec.add_feedback("Not a feedback object")


if __name__ == "__main__":
    unittest.main()
