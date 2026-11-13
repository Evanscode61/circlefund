from django.contrib import admin

# Register your models here.

from django.contrib import admin

from .models import Group, Membership


@admin.register(Group)
class GroupAdmin(admin.ModelAdmin):
    list_display = ("name", "group_type", "status", "currency", "town", "created_by", "date_created")
    list_filter = ("group_type", "status", "currency")
    search_fields = ("name", "slug", "registration_number", "email", "phone_number")
    readonly_fields = ("slug", "created_by", "member_number_seq", "date_created", "updated_at")
    list_select_related = ("created_by",)

    def save_model(self, request, obj, form, change):
        if not change:
            obj.created_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(Membership)
class MembershipAdmin(admin.ModelAdmin):
    list_display = ("user", "group", "member_number", "role", "status", "joined_at")
    list_filter = ("status", "group")
    search_fields = ("user__username", "user__phone", "member_number", "group__name")
    raw_id_fields = ("user", "invited_by")
    readonly_fields = ("member_number", "date_created", "updated_at")
    list_select_related = ("user", "group", "role")

    def save_model(self, request, obj, form, change):
        if not obj.member_number:
            obj.member_number = obj.group.next_member_number()
        super().save_model(request, obj, form, change)
