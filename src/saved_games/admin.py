from django.contrib import admin

from .models import SavedGame


@admin.register(SavedGame)
class SavedGameAdmin(admin.ModelAdmin):
    list_display = ("user", "game", "created_at")
    search_fields = ("user__username", "game__title")
