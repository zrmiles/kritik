from django.contrib import admin
from django.urls import include, path

from reviews.urls import game_urlpatterns, me_urlpatterns

urlpatterns = [
    path("admin/", admin.site.urls),
    path("api/auth/", include("accounts.urls")),
    path("api/games/", include("games.urls")),
    path("api/games/", include((game_urlpatterns, "game_reviews"))),
    path("api/reviews/", include("reviews.urls")),
    path("api/me/", include("saved_games.urls")),
    path("api/me/", include((me_urlpatterns, "my_reviews"))),
    path("", include("frontend.urls")),
]
