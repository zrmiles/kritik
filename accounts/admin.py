from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (("Профиль", {"fields": ("display_name",)}),)
    add_fieldsets = UserAdmin.add_fieldsets + (("Профиль", {"fields": ("display_name",)}),)
