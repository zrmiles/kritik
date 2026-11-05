from django.db.models import Count
from rest_framework import serializers

from .models import Game, Genre, Platform


class GenreSerializer(serializers.ModelSerializer):
    class Meta:
        model = Genre
        fields = ("slug", "name")


class PlatformSerializer(serializers.ModelSerializer):
    class Meta:
        model = Platform
        fields = ("slug", "name")


class GameSerializer(serializers.ModelSerializer):
    genres = GenreSerializer(many=True, read_only=True)
    platforms = PlatformSerializer(many=True, read_only=True)
    average_rating = serializers.DecimalField(max_digits=4, decimal_places=2, read_only=True, allow_null=True)
    review_count = serializers.IntegerField(read_only=True)
    is_saved = serializers.BooleanField(read_only=True)

    class Meta:
        model = Game
        fields = (
            "id",
            "slug",
            "title",
            "description",
            "release_date",
            "cover_url",
            "poster_theme",
            "genres",
            "platforms",
            "data_source",
            "source_url",
            "average_rating",
            "review_count",
            "is_saved",
        )


class GameDetailSerializer(GameSerializer):
    score_distribution = serializers.SerializerMethodField()

    class Meta(GameSerializer.Meta):
        fields = (*GameSerializer.Meta.fields, "score_distribution")

    def get_score_distribution(self, game):
        """Количество оценок 1…10 — для гистограммы на странице игры."""
        counts = dict(game.reviews.values_list("score").annotate(total=Count("id")))
        return [counts.get(score, 0) for score in range(1, 11)]
