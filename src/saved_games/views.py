from django.db.models import Avg, Count
from rest_framework.generics import ListCreateAPIView, RetrieveDestroyAPIView
from rest_framework.permissions import IsAuthenticated

from .models import SavedGame
from .serializers import SavedGameCreateSerializer, SavedGameSerializer


class SavedGameListCreateView(ListCreateAPIView):
    permission_classes = (IsAuthenticated,)
    pagination_class = None

    def get_queryset(self):
        return (
            SavedGame.objects.filter(user=self.request.user)
            .select_related("game")
            .prefetch_related("game__genres", "game__platforms")
            .annotate(
                average_rating=Avg("game__reviews__score"),
                review_count=Count("game__reviews", distinct=True),
            )
        )

    def get_serializer_class(self):
        if self.request.method == "POST":
            return SavedGameCreateSerializer
        return SavedGameSerializer


class SavedGameDestroyView(RetrieveDestroyAPIView):
    permission_classes = (IsAuthenticated,)
    serializer_class = SavedGameSerializer
    lookup_field = "game_id"

    def get_queryset(self):
        return SavedGame.objects.filter(user=self.request.user)
