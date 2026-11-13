from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from .models import Permission, Role,User


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ("username", "phone", "first_name", "last_name", "is_phone_verified", "is_platform_admin", "is_active")
    list_filter = ("is_phone_verified", "is_platform_admin", "is_active", "is_staff")
    search_fields = ("username", "phone", "first_name", "last_name", "email", "national_id")
    ordering = ("-date_created",)
    readonly_fields = ("date_created", "updated_at", "last_login", "date_joined")

    fieldsets = UserAdmin.fieldsets + (
        ("Chama profile", {"fields": ("phone", "is_phone_verified", "national_id", "date_of_birth", "is_platform_admin")}),
        ("Record", {"fields": ("date_created", "updated_at")}),
    )

    add_fieldsets = UserAdmin.add_fieldsets + (
        ("Chama profile", {"fields": ("phone", "first_name", "last_name", "email")}),
    )

@admin.register(Permission)
class PermissionAdmin(admin.ModelAdmin):
    list_display = ("code", "description")
    search_fields = ("code", "description")

@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ("name", "group")
    list_filter = ("group",)
    search_fields = ("name", "group__name")
    filter_horizontal = ("permissions",)