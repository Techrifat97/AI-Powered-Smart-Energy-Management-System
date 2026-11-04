class RecommendationFeedback:
    """
    Represents user feedback on an AI energy recommendation.

    Attributes:
        rating: int (1-5)
        comment: str
    """

    MIN_RATING = 1
    MAX_RATING = 5

    def __init__(self, rating: int, comment: str = "", feedback_id=None):
        self.id = feedback_id
        self.rating = None
        self.comment = ""

        self.set_rating(rating)
        self.set_comment(comment)

    # --- Getters ---
    def get_id(self):
        return self.id

    def get_rating(self) -> int:
        return self.rating

    def get_comment(self) -> str:
        return self.comment

    # --- Setters / Encapsulation ---
    def set_rating(self, new_rating: int) -> None:
        if not isinstance(new_rating, int):
            raise TypeError("Rating must be an integer")
        if new_rating < RecommendationFeedback.MIN_RATING or new_rating > RecommendationFeedback.MAX_RATING:
            raise ValueError(
                f"Rating must be between {RecommendationFeedback.MIN_RATING} and {RecommendationFeedback.MAX_RATING}"
            )
        self.rating = new_rating

    def set_comment(self, new_comment: str) -> None:
        if new_comment is None:
            self.comment = ""
        elif not isinstance(new_comment, str):
            raise TypeError("Comment must be a string")
        else:
            self.comment = new_comment.strip()

    # --- Domain Methods ---
    def validate(self) -> bool:
        """
        Validates the feedback entity.
        Returns True if rating is an integer within 1-5 and comment is a string.
        """
        if not isinstance(self.rating, int):
            return False
        if not (RecommendationFeedback.MIN_RATING <= self.rating <= RecommendationFeedback.MAX_RATING):
            return False
        if not isinstance(self.comment, str):
            return False
        return True
