from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import User, Property, PropertyImage


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ('email', 'first_name', 'last_name', 'role', 'is_active')
    list_filter = ('role', 'is_active')
    search_fields = ('email', 'first_name', 'last_name')
    ordering = ('email',)
    fieldsets = BaseUserAdmin.fieldsets + (
        ('CRM Profile', {'fields': ('phone', 'role')}),
    )


class PropertyImageInline(admin.TabularInline):
    model = PropertyImage
    extra = 0
    fields = ('image', 'is_primary')


@admin.register(Property)
class PropertyAdmin(admin.ModelAdmin):
    list_display = ('title', 'property_type', 'status', 'city', 'price', 'created_by', 'created_at')
    list_filter = ('status', 'property_type', 'listing_type', 'city')
    search_fields = ('title', 'city', 'location', 'address')
    readonly_fields = ('created_at', 'updated_at')
    inlines = [PropertyImageInline]


@admin.register(PropertyImage)
class PropertyImageAdmin(admin.ModelAdmin):
    list_display = ('property', 'is_primary', 'uploaded_at')
