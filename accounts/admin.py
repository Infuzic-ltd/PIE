from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from .models import (
    User, Property, PropertyImage, PropertyDocument, PropertyActivity,
    Customer, Block, BlockRequiredDocument,
    Lead, LeadActivity, LeadDocument, LeadPayment,
    Role, PushSubscription, Notification, AgentTarget,
    PropertySubmission, PropertySubmissionImage, SiteSettings,
)


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ('email', 'first_name', 'last_name', 'role', 'assigned_role', 'is_active', 'is_staff')
    list_filter = ('role', 'assigned_role', 'is_active', 'is_staff', 'affiliate_status')
    search_fields = ('email', 'first_name', 'last_name', 'phone')
    ordering = ('email',)
    autocomplete_fields = ('assigned_role', 'invited_by')
    fieldsets = BaseUserAdmin.fieldsets + (
        ('CRM Profile', {'fields': ('phone', 'photo', 'role', 'assigned_role', 'badge', 'financial_person', 'legal_person')}),
        ('Affiliate', {'fields': ('invited_by', 'affiliate_status')}),
    )


# ── Properties ──────────────────────────────────────────────────────────────

class PropertyImageInline(admin.TabularInline):
    model = PropertyImage
    extra = 0
    fields = ('image', 'is_primary')


class PropertyDocumentInline(admin.TabularInline):
    model = PropertyDocument
    extra = 0
    fields = ('document_type', 'title', 'file_url', 'uploaded_by', 'created_at')
    readonly_fields = ('created_at',)


class PropertyActivityInline(admin.TabularInline):
    model = PropertyActivity
    extra = 0
    fields = ('activity_type', 'description', 'created_by', 'created_at')
    readonly_fields = ('activity_type', 'description', 'created_by', 'created_at')
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


@admin.register(Property)
class PropertyAdmin(admin.ModelAdmin):
    list_display = (
        'title', 'property_type', 'listing_type', 'status', 'city', 'price_display',
        'block', 'created_by', 'show_on_website', 'created_at',
    )
    list_filter = ('status', 'property_type', 'listing_type', 'badge', 'city', 'show_on_website', 'show_to_affiliates')
    search_fields = ('title', 'city', 'location', 'address')
    date_hierarchy = 'created_at'
    autocomplete_fields = ('block', 'customer', 'created_by')
    readonly_fields = ('created_at', 'updated_at')
    inlines = [PropertyImageInline, PropertyDocumentInline, PropertyActivityInline]


@admin.register(PropertyImage)
class PropertyImageAdmin(admin.ModelAdmin):
    list_display = ('property', 'is_primary', 'uploaded_at')
    list_filter = ('is_primary',)
    search_fields = ('property__title',)
    autocomplete_fields = ('property',)


@admin.register(PropertyDocument)
class PropertyDocumentAdmin(admin.ModelAdmin):
    list_display = ('title', 'property', 'document_type', 'uploaded_by', 'created_at')
    list_filter = ('document_type',)
    search_fields = ('title', 'property__title')
    autocomplete_fields = ('property', 'uploaded_by')
    readonly_fields = ('created_at',)


@admin.register(PropertyActivity)
class PropertyActivityAdmin(admin.ModelAdmin):
    list_display = ('property', 'activity_type', 'created_by', 'created_at')
    list_filter = ('activity_type',)
    search_fields = ('property__title', 'description')
    autocomplete_fields = ('property', 'created_by')
    readonly_fields = ('property', 'activity_type', 'description', 'created_by', 'created_at')

    def has_add_permission(self, request):
        return False


# ── Customers ───────────────────────────────────────────────────────────────

@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ('name', 'phone', 'email', 'customer_type', 'budget_display', 'created_by', 'created_at')
    list_filter = ('customer_type', 'marital_status', 'residency_status', 'monthly_income_range')
    search_fields = ('name', 'phone', 'email', 'cnic')
    date_hierarchy = 'created_at'
    autocomplete_fields = ('created_by',)
    filter_horizontal = ('interested_in',)
    readonly_fields = ('created_at', 'updated_at')


# ── Blocks ──────────────────────────────────────────────────────────────────

class BlockRequiredDocumentInline(admin.TabularInline):
    model = BlockRequiredDocument
    extra = 0
    fields = ('name',)


@admin.register(Block)
class BlockAdmin(admin.ModelAdmin):
    list_display = ('name',)
    search_fields = ('name',)
    inlines = [BlockRequiredDocumentInline]


@admin.register(BlockRequiredDocument)
class BlockRequiredDocumentAdmin(admin.ModelAdmin):
    list_display = ('name', 'block', 'created_at')
    list_filter = ('block',)
    search_fields = ('name', 'block__name')
    autocomplete_fields = ('block',)


# ── Leads ───────────────────────────────────────────────────────────────────

class LeadActivityInline(admin.TabularInline):
    model = LeadActivity
    extra = 0
    fields = ('activity_type', 'description', 'created_by', 'created_at')
    readonly_fields = ('activity_type', 'description', 'created_by', 'created_at')
    can_delete = False

    def has_add_permission(self, request, obj=None):
        return False


class LeadDocumentInline(admin.TabularInline):
    model = LeadDocument
    extra = 0
    fields = ('document_type', 'title', 'file_url', 'amount', 'requirement', 'uploaded_by', 'created_at')
    readonly_fields = ('created_at',)


class LeadPaymentInline(admin.TabularInline):
    model = LeadPayment
    extra = 0
    fields = ('amount', 'paid_on', 'payment_method', 'payment_against', 'reference_number', 'recorded_by')


@admin.register(Lead)
class LeadAdmin(admin.ModelAdmin):
    list_display = (
        'full_name', 'phone', 'lead_type', 'status', 'lead_score', 'source',
        'assigned_to', 'property', 'created_at',
    )
    list_filter = ('status', 'lead_type', 'source', 'lead_score')
    search_fields = ('full_name', 'phone', 'email', 'alternate_phone')
    date_hierarchy = 'created_at'
    autocomplete_fields = ('property', 'assigned_to', 'created_by')
    filter_horizontal = ('collaborators',)
    readonly_fields = ('lead_score', 'created_at', 'updated_at')
    inlines = [LeadActivityInline, LeadDocumentInline, LeadPaymentInline]


@admin.register(LeadActivity)
class LeadActivityAdmin(admin.ModelAdmin):
    list_display = ('lead', 'activity_type', 'created_by', 'created_at')
    list_filter = ('activity_type',)
    search_fields = ('lead__full_name', 'description')
    autocomplete_fields = ('lead', 'created_by')
    readonly_fields = ('lead', 'activity_type', 'description', 'created_by', 'created_at')

    def has_add_permission(self, request):
        return False


@admin.register(LeadDocument)
class LeadDocumentAdmin(admin.ModelAdmin):
    list_display = ('title', 'lead', 'document_type', 'amount', 'uploaded_by', 'created_at')
    list_filter = ('document_type',)
    search_fields = ('title', 'lead__full_name')
    autocomplete_fields = ('lead', 'requirement', 'uploaded_by')
    readonly_fields = ('created_at',)


@admin.register(LeadPayment)
class LeadPaymentAdmin(admin.ModelAdmin):
    list_display = ('lead', 'amount', 'paid_on', 'payment_method', 'payment_against', 'recorded_by')
    list_filter = ('payment_method', 'payment_against')
    search_fields = ('lead__full_name', 'reference_number', 'note')
    date_hierarchy = 'paid_on'
    autocomplete_fields = ('lead', 'recorded_by')
    readonly_fields = ('created_at',)


# ── Roles & Permissions ───────────────────────────────────────────────────────

@admin.register(Role)
class RoleAdmin(admin.ModelAdmin):
    list_display = ('name', 'system_role', 'is_system', 'member_count', 'permissions_display')
    list_filter = ('is_system', 'system_role')
    search_fields = ('name', 'description')
    readonly_fields = ('created_at',)

    def permissions_display(self, obj):
        return ', '.join(obj.permission_labels()) or '—'
    permissions_display.short_description = 'Permissions'


# ── Property Submissions ─────────────────────────────────────────────────────

class PropertySubmissionImageInline(admin.TabularInline):
    model = PropertySubmissionImage
    extra = 0
    fields = ('image_url',)


@admin.register(PropertySubmission)
class PropertySubmissionAdmin(admin.ModelAdmin):
    list_display = (
        'full_name', 'submission_type', 'status', 'city', 'payment_status',
        'evaluation_status', 'assigned_to', 'converted_property', 'created_at',
    )
    list_filter = ('submission_type', 'status', 'payment_status', 'evaluation_status', 'wants_featured')
    search_fields = ('full_name', 'phone', 'email', 'city')
    date_hierarchy = 'created_at'
    autocomplete_fields = ('assigned_to', 'evaluated_by', 'evaluation_approved_by', 'converted_property')
    readonly_fields = ('created_at', 'updated_at')
    inlines = [PropertySubmissionImageInline]


@admin.register(PropertySubmissionImage)
class PropertySubmissionImageAdmin(admin.ModelAdmin):
    list_display = ('submission', 'created_at')
    search_fields = ('submission__full_name',)
    autocomplete_fields = ('submission',)


# ── Misc ──────────────────────────────────────────────────────────────────────

@admin.register(AgentTarget)
class AgentTargetAdmin(admin.ModelAdmin):
    list_display = ('agent', 'month_label', 'deals_target', 'revenue_target', 'set_by')
    list_filter = ('year', 'month')
    search_fields = ('agent__email', 'agent__first_name', 'agent__last_name')
    autocomplete_fields = ('agent', 'set_by')
    readonly_fields = ('created_at', 'updated_at')


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('recipient', 'title', 'is_read', 'created_at')
    list_filter = ('is_read',)
    search_fields = ('title', 'body', 'recipient__email')
    autocomplete_fields = ('recipient',)
    readonly_fields = ('created_at',)


@admin.register(PushSubscription)
class PushSubscriptionAdmin(admin.ModelAdmin):
    list_display = ('user', 'created_at')
    search_fields = ('user__email', 'endpoint')
    autocomplete_fields = ('user',)
    readonly_fields = ('endpoint', 'p256dh', 'auth', 'created_at')


@admin.register(SiteSettings)
class SiteSettingsAdmin(admin.ModelAdmin):
    list_display = ('featured_listing_fee', 'safepay_environment', 'payments_configured', 'from_email', 'updated_at')
    readonly_fields = ('updated_at',)

    def has_add_permission(self, request):
        return not SiteSettings.objects.exists()

    def has_delete_permission(self, request, obj=None):
        return False
