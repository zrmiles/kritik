from django.contrib import admin

from .models import Game, Genre, ImportRun, Platform

admin.site.register(Genre)
admin.site.register(Platform)


@admin.register(Game)
class GameAdmin(admin.ModelAdmin):
    list_display = ("title", "release_date", "data_source", "external_id", "updated_at")
    list_filter = ("data_source", "genres", "platforms")
    search_fields = ("title", "external_id")
    prepopulated_fields = {"slug": ("title",)}
    filter_horizontal = ("genres", "platforms")


@admin.register(ImportRun)
class ImportRunAdmin(admin.ModelAdmin):
    list_display = ("started_at", "source", "status", "created_count", "updated_count", "finished_at")
    list_filter = ("status", "source")
    readonly_fields = [field.name for field in ImportRun._meta.fields]

    def has_add_permission(self, request):
        return False
