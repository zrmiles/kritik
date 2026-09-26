from django.urls import path

from .views import GameReviewListView, MyReviewListView, ReviewCreateView, ReviewDetailView

app_name = "reviews"

game_urlpatterns = [
    path("<int:game_id>/reviews/", GameReviewListView.as_view(), name="game-list"),
]

me_urlpatterns = [
    path("reviews/", MyReviewListView.as_view(), name="mine"),
]

urlpatterns = [
    path("", ReviewCreateView.as_view(), name="create"),
    path("<int:pk>/", ReviewDetailView.as_view(), name="detail"),
]
