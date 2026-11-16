from django.conf import settings
from django.db import models


class SavedGame(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="saved_games")
    game = models.ForeignKey("games.Game", on_delete=models.CASCADE, related_name="saved_by")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ("-created_at",)
        constraints = [models.UniqueConstraint(fields=("user", "game"), name="unique_saved_game_user_game")]
        indexes = [models.Index(fields=("user", "-created_at"), name="saved_user_created_idx")]

    def __str__(self):
        return f"{self.user} — {self.game}"
