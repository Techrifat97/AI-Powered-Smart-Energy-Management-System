from datetime import datetime


class RecommendationFeedback:
    """
    Represents user feedback on a generated energy recommendation.
    Encapsulates rating, comments, and sentiment evaluation.
    """

    MIN_RATING = 1
    MAX_RATING = 5
    POSITIVE_THRESHOLD = 4

    def __init__(self, feedback_id, rating, comment=""):
        self.id = feedback_id
        self.rating = None
        self.comment = ""
        self.created_at = datetime.now()

        self.set_rating(rating)
        self.set_comment(comment)

    # --- Getters ---
    def get_id(self):
        return self.id

    def get_rating(self):
        return self.rating

    def get_comment(self):
        return self.comment

    def get_created_at(self):
        return self.created_at

    # --- Setters / Encapsulation ---
    def set_rating(self, new_rating):
        if not isinstance(new_rating, int):
            raise TypeError("Rating must be an integer")
        if new_rating < RecommendationFeedback.MIN_RATING or new_rating > RecommendationFeedback.MAX_RATING:
            raise ValueError(
                f"Rating must be between {RecommendationFeedback.MIN_RATING} and {RecommendationFeedback.MAX_RATING}"
            )
        self.rating = new_rating

    def set_comment(self, new_comment):
        if new_comment is None:
            self.comment = ""
        elif not isinstance(new_comment, str):
            raise TypeError("Comment must be a string")
        else:
            self.comment = new_comment.strip()

    # --- Domain Methods ---
    def is_positive(self):
        """Returns True if the rating is 4 or 5, otherwise False."""
        return self.rating >= RecommendationFeedback.POSITIVE_THRESHOLD

