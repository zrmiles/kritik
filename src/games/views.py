from decimal import Decimal, InvalidOperation

from django.contrib.auth import get_user_model
from django.db.models import Count, F, Max
from rest_framework.exceptions import ValidationError
from rest_framework.generics import ListAPIView, RetrieveAPIView
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from reviews.models import Review

from .models import Game, Genre, Platform
from .serializers import GameDetailSerializer, GameSerializer

SORTING = {
    "rating": (F("average_rating").desc(nulls_last=True), F("review_count").desc(), "title", "id"),
    "reviews": (F("review_count").desc(), F("average_rating").desc(nulls_last=True), "title", "id"),
    "newest": (F("release_date").desc(nulls_last=True), "title", "id"),
    "oldest": (F("release_date").asc(nulls_last=True), "title", "id"),
    "title": ("title", "id"),
}


def _slug_list(value):
    return [slug for slug in (part.strip() for part in value.split(",")) if slug]


def _int_param(params, name, low, high):
    raw = params.get(name, "").strip()
    if not raw:
        return None
    try:
        value = int(raw)
    except ValueError as exc:
        raise ValidationError({name: "Укажите целое число."}) from exc
    if not low <= value <= high:
        raise ValidationError({name: f"Допустимо значение от {low} до {high}."})
    return value


class GameQuerySetMixin:
    def get_queryset(self):
        queryset = (
            Game.objects.with_review_stats()
            .with_saved_status(self.request.user)
            .prefetch_related("genres", "platforms")
        )
        if getattr(self, "apply_filters", False):
            queryset = self.filter_queryset_params(queryset)
        return queryset

    def filter_queryset_params(self, queryset):
        """Все фильтры применяются одновременно; внутри жанров и платформ — «любой из»."""
        params = self.request.query_params

        if search := params.get("search", "").strip():
            queryset = queryset.filter(search_title__contains=search.casefold())

        # Подзапросы вместо join по M2M: иначе строки игры размножатся и исказят агрегаты.
        if genres := _slug_list(params.get("genre", "")):
            queryset = queryset.filter(pk__in=Game.objects.filter(genres__slug__in=genres).values("pk"))
        if platforms := _slug_list(params.get("platform", "")):
            queryset = queryset.filter(pk__in=Game.objects.filter(platforms__slug__in=platforms).values("pk"))

        year = _int_param(params, "year", 1950, 2100)
        year_from = _int_param(params, "year_from", 1950, 2100)
        year_to = _int_param(params, "year_to", 1950, 2100)
        if year is not None:
            queryset = queryset.filter(release_date__year=year)
        if year_from is not None and year_to is not None and year_from > year_to:
            raise ValidationError({"year_to": "Конец периода не может быть раньше начала."})
        if year_from is not None:
            queryset = queryset.filter(release_date__year__gte=year_from)
        if year_to is not None:
            queryset = queryset.filter(release_date__year__lte=year_to)

        if rating_min := params.get("rating_min", "").strip():
            try:
                rating_min = Decimal(rating_min)
            except InvalidOperation as exc:
                raise ValidationError({"rating_min": "Укажите число от 1 до 10."}) from exc
            if not Decimal(1) <= rating_min <= Decimal(10):
                raise ValidationError({"rating_min": "Укажите число от 1 до 10."})
            queryset = queryset.filter(average_rating__gte=rating_min)

        if params.get("reviewed", "").strip() in ("1", "true"):
            queryset = queryset.filter(review_count__gt=0)

        ordering = params.get("ordering", "rating")
        if ordering not in SORTING:
            raise ValidationError({"ordering": f"Допустимые значения: {', '.join(SORTING)}."})
        return queryset.order_by(*SORTING[ordering])


class GameListView(GameQuerySetMixin, ListAPIView):
    serializer_class = GameSerializer
    permission_classes = (AllowAny,)
    apply_filters = True


class GameDetailView(GameQuerySetMixin, RetrieveAPIView):
    serializer_class = GameDetailSerializer
    permission_classes = (AllowAny,)


class GameFiltersView(APIView):
    """Значения для фильтров: только то, что есть в каталоге."""

    authentication_classes = ()
    permission_classes = (AllowAny,)

    def get(self, request):
        years = Game.objects.filter(release_date__isnull=False).dates("release_date", "year", order="DESC")
        genres = Genre.objects.annotate(game_count=Count("games")).filter(game_count__gt=0)
        platforms = Platform.objects.annotate(game_count=Count("games")).filter(game_count__gt=0)
        def options(items):
            return [{"slug": item.slug, "name": item.name, "count": item.game_count} for item in items]

        return Response(
            {
                "genres": options(genres),
                "platforms": options(platforms.order_by("-game_count", "name")),
                "years": [year.year for year in years],
                "orderings": list(SORTING),
            }
        )


class CatalogStatsView(APIView):
    """Сводка для шапки сайта."""

    authentication_classes = ()
    permission_classes = (AllowAny,)

    def get(self, request):
        reviews = Review.objects.aggregate(total=Count("id"), last=Max("created_at"))
        return Response(
            {
                "games": Game.objects.count(),
                "reviews": reviews["total"],
                "critics": get_user_model().objects.filter(reviews__isnull=False).distinct().count(),
                "last_review_at": reviews["last"],
            }
        )
