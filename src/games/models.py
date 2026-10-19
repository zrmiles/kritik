from django.db import models
from django.db.models import Avg, BooleanField, Count, Exists, OuterRef, Q, Value


class GameQuerySet(models.QuerySet):
    def with_review_stats(self):
        return self.annotate(
            average_rating=Avg("reviews__score"),
            review_count=Count("reviews", distinct=True),
        )

    def with_saved_status(self, user):
        if not user.is_authenticated:
            return self.annotate(is_saved=Value(False, output_field=BooleanField()))
        saved_games = user.saved_games.filter(game_id=OuterRef("pk"))
        return self.annotate(is_saved=Exists(saved_games))


class Genre(models.Model):
    slug = models.SlugField(unique=True)
    name = models.CharField(max_length=100, unique=True)

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return self.name


class Platform(models.Model):
    slug = models.SlugField(unique=True)
    name = models.CharField(max_length=100, unique=True)

    class Meta:
        ordering = ("name",)

    def __str__(self):
        return self.name


class Game(models.Model):
    class DataSource(models.TextChoices):
        MANUAL = "manual", "Вручную"
        RAWG = "rawg", "RAWG"

    slug = models.SlugField(unique=True)
    title = models.CharField(max_length=200, db_index=True)
    # SQLite сравнивает без учёта регистра только латиницу, поэтому ищем по заранее приведённому названию.
    search_title = models.CharField(max_length=200, db_index=True, editable=False, default="")
    description = models.TextField(blank=True)
    release_date = models.DateField(null=True, blank=True)
    cover_url = models.URLField(blank=True)
    poster_theme = models.SlugField(blank=True)
    genres = models.ManyToManyField(Genre, related_name="games")
    platforms = models.ManyToManyField(Platform, related_name="games")
    data_source = models.CharField(max_length=20, choices=DataSource.choices, default=DataSource.MANUAL)
    # NULL, а не "": уникальность (источник, внешний id) проверяется только у импортированных игр.
    external_id = models.CharField(max_length=100, null=True, blank=True)  # noqa: DJ001
    source_url = models.URLField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = GameQuerySet.as_manager()

    class Meta:
        ordering = ("title",)
        constraints = [
            models.UniqueConstraint(
                fields=("data_source", "external_id"),
                condition=Q(external_id__isnull=False),
                name="unique_game_external_source_id",
            )
        ]

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        self.search_title = self.title.casefold()
        update_fields = kwargs.get("update_fields")
        if update_fields is not None and "title" in update_fields:
            kwargs["update_fields"] = {*update_fields, "search_title"}
        super().save(*args, **kwargs)


class ImportRun(models.Model):
    """Журнал запусков импорта: ошибки провайдера видны в админке."""

    class Status(models.TextChoices):
        RUNNING = "running", "Выполняется"
        SUCCESS = "success", "Успешно"
        FAILED = "failed", "Ошибка"

    source = models.CharField(max_length=20, choices=Game.DataSource.choices, default=Game.DataSource.RAWG)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.RUNNING)
    parameters = models.JSONField(default=dict, blank=True)
    created_count = models.PositiveIntegerField(default=0)
    updated_count = models.PositiveIntegerField(default=0)
    error = models.TextField(blank=True)
    started_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ("-started_at",)

    def __str__(self):
        return f"{self.get_source_display()} · {self.started_at:%Y-%m-%d %H:%M} · {self.get_status_display()}"
