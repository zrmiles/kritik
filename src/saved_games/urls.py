from django.urls import path

from .views import SavedGameDestroyView, SavedGameListCreateView

app_name = "saved_games"

urlpatterns = [
    path("saved-games/", SavedGameListCreateView.as_view(), name="list-create"),
    path("saved-games/<int:game_id>/", SavedGameDestroyView.as_view(), name="destroy"),
]
