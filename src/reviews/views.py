from rest_framework.generics import CreateAPIView, ListAPIView, RetrieveUpdateDestroyAPIView
from rest_framework.permissions import AllowAny, IsAuthenticated

from .models import Review
from .serializers import MyReviewSerializer, ReviewSerializer


class GameReviewListView(ListAPIView):
    serializer_class = ReviewSerializer
    permission_classes = (AllowAny,)
    pagination_class = None

    def get_queryset(self):
        return Review.objects.filter(game_id=self.kwargs["game_id"]).select_related("author")


class ReviewCreateView(CreateAPIView):
    serializer_class = ReviewSerializer
    permission_classes = (IsAuthenticated,)


class ReviewDetailView(RetrieveUpdateDestroyAPIView):
    serializer_class = ReviewSerializer
    permission_classes = (IsAuthenticated,)
    http_method_names = ("get", "patch", "delete", "options")

    def get_queryset(self):
        return Review.objects.filter(author=self.request.user).select_related("author", "game")


class MyReviewListView(ListAPIView):
    serializer_class = MyReviewSerializer
    permission_classes = (IsAuthenticated,)
    pagination_class = None

    def get_queryset(self):
        return Review.objects.filter(author=self.request.user).select_related("author", "game")
