from django.db import IntegrityError, transaction
from rest_framework import serializers

from games.models import Game

from .models import Review

DUPLICATE_REVIEW = "Вы уже оставили рецензию на эту игру."


class ReviewSerializer(serializers.ModelSerializer):
    author = serializers.CharField(source="author.public_name", read_only=True)
    is_owner = serializers.SerializerMethodField()
    game_id = serializers.PrimaryKeyRelatedField(
        source="game",
        queryset=Game.objects.all(),
        write_only=True,
        required=False,
    )

    class Meta:
        model = Review
        fields = (
            "id",
            "game_id",
            "author",
            "is_owner",
            "score",
            "text",
            "created_at",
            "updated_at",
        )
        read_only_fields = ("created_at", "updated_at")
        extra_kwargs = {
            "score": {"required": False},
            "text": {"required": False},
        }

    def get_is_owner(self, review):
        request = self.context.get("request")
        return bool(request and request.user.is_authenticated and review.author_id == request.user.id)

    def validate(self, attrs):
        if self.instance is None:
            missing = {}
            if "game" not in attrs:
                missing["game_id"] = "Это поле обязательно."
            if "score" not in attrs:
                missing["score"] = "Это поле обязательно."
            if "text" not in attrs:
                missing["text"] = "Это поле обязательно."
            if missing:
                raise serializers.ValidationError(missing)

            request = self.context["request"]
            if Review.objects.filter(author=request.user, game=attrs["game"]).exists():
                raise serializers.ValidationError({"game_id": DUPLICATE_REVIEW})
        elif "game" in attrs and attrs["game"] != self.instance.game:
            raise serializers.ValidationError({"game_id": "Игру существующей рецензии изменить нельзя."})
        return attrs

    def create(self, validated_data):
        # US-5, FR-4: проверка в validate() не спасает от двух одновременных запросов,
        # поэтому нарушение уникальности (author, game) в БД тоже отдаётся как 400, а не 500.
        try:
            with transaction.atomic():
                return Review.objects.create(author=self.context["request"].user, **validated_data)
        except IntegrityError as exc:
            raise serializers.ValidationError({"game_id": [DUPLICATE_REVIEW]}) from exc


class ReviewGameSerializer(serializers.ModelSerializer):
    class Meta:
        model = Game
        fields = ("id", "title", "cover_url", "poster_theme", "release_date")


class MyReviewSerializer(ReviewSerializer):
    game = ReviewGameSerializer(read_only=True)

    class Meta(ReviewSerializer.Meta):
        fields = (*ReviewSerializer.Meta.fields, "game")
