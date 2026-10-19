from django.contrib import admin

from .models import Review


@admin.register(Review)
class ReviewAdmin(admin.ModelAdmin):
    list_display = ("game", "author", "score", "created_at")
    list_filter = ("score", "created_at")
    search_fields = ("game__title", "author__username", "text")
