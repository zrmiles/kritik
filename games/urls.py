from django.urls import path

from .views import CatalogStatsView, GameDetailView, GameFiltersView, GameListView

app_name = "games"

urlpatterns = [
    path("", GameListView.as_view(), name="list"),
    path("filters/", GameFiltersView.as_view(), name="filters"),
    path("stats/", CatalogStatsView.as_view(), name="stats"),
    path("<int:pk>/", GameDetailView.as_view(), name="detail"),
]
