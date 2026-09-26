from rest_framework import serializers

from games.models import Game
from games.serializers import GameSerializer

from .models import SavedGame


class SavedGameSerializer(serializers.ModelSerializer):
    game = serializers.SerializerMethodField()

    class Meta:
        model = SavedGame
        fields = ("game", "created_at")

    def get_game(self, saved_game):
        game = saved_game.game
        game.average_rating = getattr(saved_game, "average_rating", None)
        game.review_count = getattr(saved_game, "review_count", 0)
        game.is_saved = True
        return GameSerializer(game, context=self.context).data


class SavedGameCreateSerializer(serializers.Serializer):
    game_id = serializers.PrimaryKeyRelatedField(source="game", queryset=Game.objects.all())

    def validate_game_id(self, game):
        request = self.context["request"]
        if SavedGame.objects.filter(user=request.user, game=game).exists():
            raise serializers.ValidationError("Игра уже находится в вашем списке.")
        return game

    def create(self, validated_data):
        return SavedGame.objects.create(user=self.context["request"].user, **validated_data)

    def to_representation(self, instance):
        return SavedGameSerializer(instance, context=self.context).data
