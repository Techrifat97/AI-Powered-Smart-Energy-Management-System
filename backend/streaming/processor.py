from abc import ABC, abstractmethod


class StreamProcessor(ABC):
    """
    Abstract Base Class for all stream processing components in the pipeline.
    Enforces a common interface across filtering, transformation, and analysis stages.
    """

    @abstractmethod
    def process(self, event: dict) -> dict | None:
        """
        Processes a single event dictionary.

        Args:
            event (dict): An event dictionary containing meter telemetry data.

        Returns:
            dict | None: The processed/transformed event dictionary, or None if the event is filtered out.
        """
        pass

    def __or__(self, other):
        """
        Overloads the bitwise OR operator (|) to compose pipeline processing stages.

        Example:
            pipeline = filter_processor | transform_processor
        """
        if isinstance(other, StreamProcessor):
            return CompositeProcessor(self, other)
        return NotImplemented

    def process_stream(self, stream):
        """
        Convenience generator that yields processed events from an iterable stream.
        Events filtered out (returning None) are omitted.

        Args:
            stream: An iterable stream yielding event dictionaries.

        Yields:
            dict: Processed event dictionaries.
        """
        for event in stream:
            result = self.process(event)
            if result is not None:
                yield result


class CompositeProcessor(StreamProcessor):
    """
    Represents a sequential pipeline composed of multiple StreamProcessor instances.
    Created using the pipeline composition operator `|`.
    """

    def __init__(self, *stages):
        self.stages = []
        for stage in stages:
            if isinstance(stage, CompositeProcessor):
                self.stages.extend(stage.stages)
            elif isinstance(stage, StreamProcessor):
                self.stages.append(stage)
            else:
                raise TypeError(f"Expected StreamProcessor, got {type(stage).__name__}")

    def get_stages(self):
        """Returns the list of processing stages in order."""
        return list(self.stages)

    def process(self, event: dict) -> dict | None:
        """
        Pipes the event sequentially through each stage in the composite processor.
        If any stage filters the event (returns None), pipeline execution stops and None is returned.
        """
        current = event
        for stage in self.stages:
            if current is None:
                return None
            current = stage.process(current)
        return current

    def __repr__(self):
        stage_names = " | ".join(s.__class__.__name__ for s in self.stages)
        return f"CompositeProcessor({stage_names})"
