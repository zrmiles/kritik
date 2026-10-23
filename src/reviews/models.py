from django.conf import settings
from django.core.validators import MaxLengthValidator, MaxValueValidator, MinLengthValidator, MinValueValidator
from django.db import models
from django.db.models import Q


class Review(models.Model):
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reviews")
    game = models.ForeignKey("games.Game", on_delete=models.CASCADE, related_name="reviews")
    score = models.PositiveSmallIntegerField(validators=[MinValueValidator(1), MaxValueValidator(10)])
    text = models.TextField(validators=[MinLengthValidator(10), MaxLengthValidator(500)])
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ("-created_at",)
        constraints = [
            models.UniqueConstraint(fields=("author", "game"), name="unique_review_author_game"),
            models.CheckConstraint(condition=Q(score__gte=1, score__lte=10), name="review_score_between_1_and_10"),
        ]
        indexes = [models.Index(fields=("game", "-created_at"), name="review_game_created_idx")]

    def __str__(self):
        return f"{self.author} — {self.game}: {self.score}/10"
