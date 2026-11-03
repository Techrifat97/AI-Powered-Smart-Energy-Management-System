import unittest
from abc import ABC

from backend.streaming.processor import CompositeProcessor, StreamProcessor


class DummyUpperTransformer(StreamProcessor):
    """Concrete test processor that transforms category to uppercase."""

    def process(self, event: dict) -> dict | None:
        if not isinstance(event, dict):
            return None
        res = dict(event)
        res["category"] = res.get("category", "").upper()
        return res


class DummyTaggingProcessor(StreamProcessor):
    """Concrete test processor that appends a processed tag."""

    def process(self, event: dict) -> dict | None:
        if not isinstance(event, dict):
            return None
        res = dict(event)
        res["tagged"] = True
        return res


class DummyDroppingProcessor(StreamProcessor):
    """Concrete test processor that drops all events."""

    def process(self, event: dict) -> dict | None:
        return None


class TestStreamProcessor(unittest.TestCase):

    def test_abstract_class_cannot_be_instantiated(self):
        """Verify that StreamProcessor cannot be instantiated directly."""
        with self.assertRaises(TypeError):
            StreamProcessor()

    def test_unimplemented_process_raises_type_error(self):
        """Verify that a subclass without process() implementation cannot be instantiated."""
        class IncompleteProcessor(StreamProcessor):
            pass

        with self.assertRaises(TypeError):
            IncompleteProcessor()

    def test_polymorphism_and_concrete_subclass(self):
        """Verify that a concrete subclass implements process() polymorphically."""
        processor = DummyUpperTransformer()
        self.assertIsInstance(processor, StreamProcessor)

        event = {"meter_id": 1, "category": "hvac"}
        processed = processor.process(event)
        self.assertEqual(processed["category"], "HVAC")

    def test_pipe_operator_composition(self):
        """Verify that p1 | p2 creates a CompositeProcessor with ordered stages."""
        p1 = DummyUpperTransformer()
        p2 = DummyTaggingProcessor()

        pipeline = p1 | p2
        self.assertIsInstance(pipeline, CompositeProcessor)
        self.assertIsInstance(pipeline, StreamProcessor)
        self.assertEqual(len(pipeline.get_stages()), 2)

    def test_multiple_pipe_chaining(self):
        """Verify that p1 | p2 | p3 flattens into a single CompositeProcessor."""
        p1 = DummyUpperTransformer()
        p2 = DummyTaggingProcessor()
        p3 = DummyUpperTransformer()

        pipeline = p1 | p2 | p3
        self.assertEqual(len(pipeline.get_stages()), 3)

    def test_composite_processor_execution(self):
        """Verify sequential event flow through a composite pipeline."""
        p1 = DummyUpperTransformer()
        p2 = DummyTaggingProcessor()
        pipeline = p1 | p2

        event = {"meter_id": 1, "category": "solar"}
        result = pipeline.process(event)

        self.assertEqual(result["category"], "SOLAR")
        self.assertTrue(result["tagged"])

    def test_composite_processor_short_circuits_on_none(self):
        """Verify that when an intermediate stage filters out an event (returns None), pipeline returns None."""
        p1 = DummyDroppingProcessor()
        p2 = DummyTaggingProcessor()
        pipeline = p1 | p2

        event = {"meter_id": 1, "category": "solar"}
        result = pipeline.process(event)
        self.assertIsNone(result)

    def test_pipe_with_invalid_type_raises_type_error(self):
        """Verify that piping with a non-StreamProcessor raises TypeError."""
        p = DummyUpperTransformer()
        with self.assertRaises(TypeError):
            _ = p | "not_a_processor"

    def test_process_stream_generator(self):
        """Verify process_stream yields only non-filtered processed events."""
        p = DummyUpperTransformer()
        events = [
            {"meter_id": 1, "category": "hvac"},
            {"meter_id": 2, "category": "battery"},
        ]
        results = list(p.process_stream(events))
        self.assertEqual(len(results), 2)
        self.assertEqual(results[0]["category"], "HVAC")
        self.assertEqual(results[1]["category"], "BATTERY")


if __name__ == "__main__":
    unittest.main()
