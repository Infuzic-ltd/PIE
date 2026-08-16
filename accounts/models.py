from django.contrib.auth.models import AbstractUser
from django.db import models

PERMISSION_LIST = [
    ('dashboard',         'View Dashboard'),
    ('properties_view',   'View Properties'),
    ('properties_add',    'Add Properties'),
    ('properties_edit',   'Edit Properties'),
    ('properties_delete', 'Delete Properties'),
    ('leads_view',        'View Leads'),
    ('leads_manage',      'Manage Leads'),
    ('reports_view',      'View Reports'),
    ('team_view',         'View Team'),
]

PERMISSION_DEFAULTS = {
    'admin':   [p[0] for p in PERMISSION_LIST],
    'manager': ['dashboard', 'properties_view', 'properties_add', 'properties_edit',
                'properties_delete', 'leads_view', 'leads_manage', 'reports_view', 'team_view'],
    'agent':   ['dashboard', 'properties_view', 'properties_add', 'leads_view'],
}


class User(AbstractUser):
    ROLE_AGENT = 'agent'
    ROLE_MANAGER = 'manager'
    ROLE_ADMIN = 'admin'

    ROLE_CHOICES = [
        (ROLE_AGENT, 'Agent'),
        (ROLE_MANAGER, 'Sales Manager'),
        (ROLE_ADMIN, 'Admin'),
    ]

    BADGE_NONE = ''
    BADGE_TOP_PERFORMER = 'top_performer'
    BADGE_RISING_STAR = 'rising_star'
    BADGE_CLIENT_FAVORITE = 'client_favorite'
    BADGE_MOST_DEALS = 'most_deals'
    BADGE_VETERAN = 'veteran'
    BADGE_TEAM_PLAYER = 'team_player'

    BADGE_CHOICES = [
        (BADGE_NONE, '— No Badge —'),
        (BADGE_TOP_PERFORMER, '🏆 Top Performer'),
        (BADGE_RISING_STAR, '🌟 Rising Star'),
        (BADGE_CLIENT_FAVORITE, '❤️ Client Favorite'),
        (BADGE_MOST_DEALS, '🤝 Most Deals Closed'),
        (BADGE_VETERAN, '🎖️ Veteran Agent'),
        (BADGE_TEAM_PLAYER, '🙌 Team Player'),
    ]

    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=20, blank=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_AGENT)
    assigned_role = models.ForeignKey(
        'Role', on_delete=models.SET_NULL, null=True, blank=True, related_name='members'
    )
    photo = models.URLField(max_length=500, blank=True)
    financial_person = models.BooleanField(default=False)
    legal_person = models.BooleanField(default=False)
    badge = models.CharField(max_length=30, choices=BADGE_CHOICES, blank=True, default=BADGE_NONE)

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username', 'first_name', 'last_name']

    def get_full_name(self):
        return f'{self.first_name} {self.last_name}'.strip() or self.email

    def __str__(self):
        return self.email

    @property
    def is_crm_admin(self):
        return self.role == self.ROLE_ADMIN

    def has_crm_permission(self, perm):
        if self.role == self.ROLE_ADMIN:
            return True
        if self.assigned_role_id:
            return perm in (self.assigned_role.permissions or [])
        return perm in PERMISSION_DEFAULTS.get(self.role, [])

    def get_effective_role_name(self):
        if self.assigned_role_id:
            return self.assigned_role.name
        return self.get_role_display()


def progress_bucket_color(pct):
    """Shared red/amber/green grading for any 0-100 progress metric in the CRM."""
    if pct >= 100:
        return '#22c55e'
    if pct >= 50:
        return '#f59e0b'
    return '#ef4444'


class Customer(models.Model):
    TYPE_SELLER = 'seller'
    TYPE_BUYER = 'buyer'
    TYPE_LANDLORD = 'landlord'
    TYPE_TENANT = 'tenant'

    CUSTOMER_TYPE_CHOICES = [
        (TYPE_SELLER, 'Seller'),
        (TYPE_BUYER, 'Buyer'),
        (TYPE_LANDLORD, 'Landlord'),
        (TYPE_TENANT, 'Tenant'),
    ]

    MARITAL_SINGLE = 'single'
    MARITAL_MARRIED = 'married'
    MARITAL_DIVORCED = 'divorced'
    MARITAL_WIDOWED = 'widowed'

    MARITAL_STATUS_CHOICES = [
        (MARITAL_SINGLE, 'Single'),
        (MARITAL_MARRIED, 'Married'),
        (MARITAL_DIVORCED, 'Divorced'),
        (MARITAL_WIDOWED, 'Widowed'),
    ]

    RESIDENCY_RESIDENT = 'resident'
    RESIDENCY_OVERSEAS = 'overseas'
    RESIDENCY_FOREIGN = 'foreign'

    RESIDENCY_CHOICES = [
        (RESIDENCY_RESIDENT, 'Resident Pakistani'),
        (RESIDENCY_OVERSEAS, 'Overseas Pakistani'),
        (RESIDENCY_FOREIGN, 'Foreign National'),
    ]

    INCOME_CHOICES = [
        ('below_100k', 'Below PKR 100,000/month'),
        ('100k_300k', 'PKR 100,000 – 300,000/month'),
        ('300k_500k', 'PKR 300,000 – 500,000/month'),
        ('500k_1m', 'PKR 500,000 – 1,000,000/month'),
        ('above_1m', 'Above PKR 1,000,000/month'),
    ]

    name = models.CharField(max_length=150)
    phone = models.CharField(max_length=20)
    email = models.EmailField(blank=True)
    cnic = models.CharField(max_length=20, blank=True, verbose_name='CNIC')
    address = models.TextField(blank=True)
    customer_type = models.CharField(
        max_length=20, choices=CUSTOMER_TYPE_CHOICES, default=TYPE_BUYER
    )
    budget = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    interested_in = models.ManyToManyField(
        'Property', blank=True, related_name='interested_customers'
    )

    # ── Demographic & lifestyle detail — used for marketing segmentation, not
    # required for basic CRM use, hence all blank=True/null=True. ──────────────
    occupation = models.CharField(max_length=150, blank=True)
    company_name = models.CharField(max_length=150, blank=True, verbose_name='Company / Employer')
    marital_status = models.CharField(max_length=20, choices=MARITAL_STATUS_CHOICES, blank=True)
    residency_status = models.CharField(max_length=20, choices=RESIDENCY_CHOICES, blank=True)
    monthly_income_range = models.CharField(max_length=20, choices=INCOME_CHOICES, blank=True)
    children = models.JSONField(
        default=list, blank=True,
        help_text='List of children — name, age, school, and class/grade.',
    )
    club_membership = models.CharField(
        max_length=255, blank=True,
        help_text='e.g. Karachi Gymkhana, DHA Country & Golf Club, Sindh Club…',
    )
    vehicles = models.JSONField(
        default=list, blank=True,
        help_text='List of vehicles owned — type, make, model, and year.',
    )
    referral_source = models.CharField(max_length=150, blank=True, help_text='How did they hear about us?')
    social_media_handle = models.CharField(
        max_length=150, blank=True,
        help_text='Instagram/Facebook handle or profile link — useful for retargeting.',
    )

    notes = models.TextField(blank=True)
    created_by = models.ForeignKey(
        'User', on_delete=models.SET_NULL, null=True, related_name='customers'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return f'{self.name} ({self.phone})'

    @property
    def is_supply_side(self):
        return self.customer_type in (self.TYPE_SELLER, self.TYPE_LANDLORD)

    @property
    def is_demand_side(self):
        return self.customer_type in (self.TYPE_BUYER, self.TYPE_TENANT)

    def budget_display(self):
        if not self.budget:
            return None
        crore = self.budget / 10_000_000
        if crore >= 1:
            return f'PKR {crore:.2f} Cr'
        lakh = self.budget / 100_000
        return f'PKR {lakh:.2f} L'

    def vehicles_summary(self):
        if not self.vehicles:
            return None
        counts = {}
        for v in self.vehicles:
            label = (v.get('type') or 'Vehicle').strip() or 'Vehicle'
            counts[label] = counts.get(label, 0) + 1
        return ', '.join(f'{n} {label}{"s" if n != 1 else ""}' for label, n in counts.items())

    def profile_completeness(self):
        """How much marketing-useful detail is on file for this customer — used to
        prompt agents to enrich profiles, not a required/gating metric."""
        checks = [
            bool(self.email),
            bool(self.cnic),
            bool(self.address),
            bool(self.budget),
            bool(self.occupation),
            bool(self.company_name),
            bool(self.marital_status),
            bool(self.residency_status),
            bool(self.monthly_income_range),
            bool(self.club_membership),
            bool(self.referral_source),
            bool(self.social_media_handle),
            bool(self.children),
            bool(self.vehicles),
            bool(self.notes),
        ]
        total = len(checks)
        done = sum(1 for c in checks if c)
        return {'done': done, 'total': total, 'pct': int(done * 100 / total) if total else 0}

    def profile_completeness_pct(self):
        return self.profile_completeness()['pct']

    def profile_completeness_color(self):
        return progress_bucket_color(self.profile_completeness_pct())


class Block(models.Model):
    name = models.CharField(max_length=50, unique=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class BlockRequiredDocument(models.Model):
    block = models.ForeignKey(Block, on_delete=models.CASCADE, related_name='required_documents')
    name = models.CharField(max_length=150)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']
        unique_together = ('block', 'name')

    def __str__(self):
        return f'{self.name} ({self.block.name})'


class Lead(models.Model):
    STATUS_RECEIVED = 'received'
    STATUS_ASSIGNED = 'assigned'
    STATUS_CONTACTED = 'contacted'
    STATUS_PROPERTY_SHARED = 'property_shared'
    STATUS_FOLLOW_UP = 'follow_up'
    STATUS_VISIT_SCHEDULED = 'visit_scheduled'
    STATUS_NEGOTIATION = 'negotiation'
    STATUS_BOOKING_CONFIRMED = 'booking_confirmed'
    STATUS_DOCUMENTATION = 'documentation'
    STATUS_PAYMENT_TRACKING = 'payment_tracking'
    STATUS_POSSESSION_COMPLETE = 'possession_complete'
    STATUS_DEAL_CLOSED = 'deal_closed'
    STATUS_DEAL_LOST = 'deal_lost'

    # Sequential pipeline order — everything except the "deal_lost" branch, which can be
    # reached from any active stage rather than being a step in the normal sequence.
    STATUS_ORDER = [
        STATUS_RECEIVED,
        STATUS_ASSIGNED,
        STATUS_CONTACTED,
        STATUS_PROPERTY_SHARED,
        STATUS_FOLLOW_UP,
        STATUS_VISIT_SCHEDULED,
        STATUS_NEGOTIATION,
        STATUS_BOOKING_CONFIRMED,
        STATUS_DOCUMENTATION,
        STATUS_PAYMENT_TRACKING,
        STATUS_POSSESSION_COMPLETE,
        STATUS_DEAL_CLOSED,
    ]

    STATUS_CHOICES = [
        (STATUS_RECEIVED, 'Lead Received'),
        (STATUS_ASSIGNED, 'Lead Assigned'),
        (STATUS_CONTACTED, 'Contacted'),
        (STATUS_PROPERTY_SHARED, 'Property Shared'),
        (STATUS_FOLLOW_UP, 'Follow Up'),
        (STATUS_VISIT_SCHEDULED, 'Visit Scheduled'),
        (STATUS_NEGOTIATION, 'Negotiation'),
        (STATUS_BOOKING_CONFIRMED, 'Booking Confirmation'),
        (STATUS_DOCUMENTATION, 'Documentation'),
        (STATUS_PAYMENT_TRACKING, 'Payment Tracking'),
        (STATUS_POSSESSION_COMPLETE, 'Possession Complete'),
        (STATUS_DEAL_CLOSED, 'Deal Closed'),
        (STATUS_DEAL_LOST, 'Deal Lost'),
    ]

    STATUS_COLORS = {
        STATUS_RECEIVED: '#3b82f6',
        STATUS_ASSIGNED: '#6366f1',
        STATUS_CONTACTED: '#f59e0b',
        STATUS_PROPERTY_SHARED: '#0ea5e9',
        STATUS_FOLLOW_UP: '#f97316',
        STATUS_VISIT_SCHEDULED: '#a855f7',
        STATUS_NEGOTIATION: '#06b6d4',
        STATUS_BOOKING_CONFIRMED: '#ec4899',
        STATUS_DOCUMENTATION: '#8b5cf6',
        STATUS_PAYMENT_TRACKING: '#14b8a6',
        STATUS_POSSESSION_COMPLETE: '#22c55e',
        STATUS_DEAL_CLOSED: '#059669',
        STATUS_DEAL_LOST: '#ef4444',
    }

    STATUS_ICONS = {
        STATUS_RECEIVED: '📥',
        STATUS_ASSIGNED: '🧑‍💼',
        STATUS_CONTACTED: '📞',
        STATUS_PROPERTY_SHARED: '🏠',
        STATUS_FOLLOW_UP: '🔁',
        STATUS_VISIT_SCHEDULED: '📅',
        STATUS_NEGOTIATION: '🤝',
        STATUS_BOOKING_CONFIRMED: '💰',
        STATUS_DOCUMENTATION: '📄',
        STATUS_PAYMENT_TRACKING: '💳',
        STATUS_POSSESSION_COMPLETE: '🔑',
        STATUS_DEAL_CLOSED: '🏆',
        STATUS_DEAL_LOST: '❌',
    }

    TYPE_BUYER = 'buyer'
    TYPE_SELLER = 'seller'
    TYPE_INVESTOR = 'investor'
    TYPE_TENANT = 'tenant'

    TYPE_CHOICES = [
        (TYPE_BUYER, 'Buyer'),
        (TYPE_SELLER, 'Seller'),
        (TYPE_INVESTOR, 'Investor'),
        (TYPE_TENANT, 'Tenant'),
    ]

    SOURCE_CHOICES = [
        ('website', 'Website'),
        ('whatsapp', 'WhatsApp'),
        ('referral', 'Referral'),
        ('property_listing', 'Property Portals'),
        ('walk_in', 'Walk-in'),
        ('phone_call', 'Phone Call'),
        ('social_media', 'Social Media'),
        ('other', 'Other'),
    ]

    INTEREST_CHOICES = [
        ('apartment', 'Apartment'),
        ('house', 'House'),
        ('plot', 'Plot'),
        ('commercial', 'Commercial'),
    ]

    SCORE_HOT = 'hot'
    SCORE_WARM = 'warm'
    SCORE_COLD = 'cold'

    SCORE_CHOICES = [
        (SCORE_HOT, 'Hot'),
        (SCORE_WARM, 'Warm'),
        (SCORE_COLD, 'Cold'),
    ]

    SCORE_COLORS = {
        SCORE_HOT: '#ef4444',
        SCORE_WARM: '#f97316',
        SCORE_COLD: '#22c55e',
    }

    SCORE_ICONS = {
        SCORE_HOT: '🔴',
        SCORE_WARM: '🟠',
        SCORE_COLD: '🟢',
    }

    full_name = models.CharField(max_length=150)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=20)
    alternate_phone = models.CharField(max_length=20, blank=True)
    lead_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default=TYPE_BUYER)
    source = models.CharField(max_length=30, choices=SOURCE_CHOICES, default='website')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_RECEIVED)
    interested_in = models.JSONField(default=list, blank=True)
    area_preferences = models.CharField(max_length=500, blank=True)
    budget_min = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    budget_max = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    bedrooms_min = models.SmallIntegerField(null=True, blank=True)
    bedrooms_max = models.SmallIntegerField(null=True, blank=True)
    bathrooms_min = models.SmallIntegerField(null=True, blank=True)
    bathrooms_max = models.SmallIntegerField(null=True, blank=True)
    area_sqft_min = models.IntegerField(null=True, blank=True)
    area_sqft_max = models.IntegerField(null=True, blank=True)
    other_requirements = models.TextField(blank=True)
    booking_amount = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    deal_amount = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True,
        help_text='Total sale/deal amount. Locked once set — required before payments can be recorded.',
    )
    commission_amount = models.DecimalField(
        max_digits=14, decimal_places=2, null=True, blank=True,
        help_text='Total real estate commission owed on this deal. Locked once set.',
    )
    property = models.ForeignKey(
        'Property', on_delete=models.SET_NULL, null=True, blank=True, related_name='leads',
        help_text='The property this lead is negotiating on.',
    )
    notes = models.TextField(blank=True)
    follow_up_date = models.DateTimeField(null=True, blank=True)
    last_contacted = models.DateTimeField(null=True, blank=True)
    visit_scheduled_at = models.DateTimeField(null=True, blank=True)
    lost_reason = models.TextField(blank=True)
    lead_score = models.CharField(
        max_length=10, choices=SCORE_CHOICES, default=SCORE_COLD,
        help_text='Auto-calculated from requirement completeness and engagement signals on every save.',
    )
    assigned_to = models.ForeignKey(
        'User', on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_leads'
    )
    collaborators = models.ManyToManyField(
        'User', blank=True, related_name='collab_leads',
        help_text='Additional agents working on this lead alongside the primary assigned agent.',
    )
    created_by = models.ForeignKey(
        'User', on_delete=models.SET_NULL, null=True, related_name='created_leads'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.full_name} ({self.get_lead_type_display()})'

    def initials(self):
        parts = self.full_name.split()
        if len(parts) >= 2:
            return (parts[0][0] + parts[-1][0]).upper()
        return self.full_name[:2].upper() if self.full_name else 'LD'

    def status_color(self):
        return self.STATUS_COLORS.get(self.status, '#6b7280')

    def score_color(self):
        return self.SCORE_COLORS.get(self.lead_score, '#6b7280')

    def score_icon(self):
        return self.SCORE_ICONS.get(self.lead_score, '')

    def status_step_index(self):
        """Position in the sequential pipeline (STATUS_ORDER), or -1 for the deal_lost branch."""
        try:
            return self.STATUS_ORDER.index(self.status)
        except ValueError:
            return -1

    def is_lost(self):
        return self.status == self.STATUS_DEAL_LOST

    def calculate_lead_score(self):
        """Starter rule: requirement completeness + pipeline engagement. Retune thresholds as needed."""
        if self.status == self.STATUS_DEAL_LOST:
            return self.SCORE_COLD

        points = 0
        if self.budget_min or self.budget_max:
            points += 1
        if self.interested_in:
            points += 1
        if self.area_preferences:
            points += 1
        if self.bedrooms_min or self.bathrooms_min:
            points += 1
        if self.follow_up_date:
            points += 1

        step = self.status_step_index()
        if step >= self.STATUS_ORDER.index(self.STATUS_FOLLOW_UP):
            points += 2
        if step >= self.STATUS_ORDER.index(self.STATUS_NEGOTIATION):
            points += 4

        if points >= 5:
            return self.SCORE_HOT
        if points >= 2:
            return self.SCORE_WARM
        return self.SCORE_COLD

    def save(self, *args, **kwargs):
        self.lead_score = self.calculate_lead_score()
        super().save(*args, **kwargs)

    def budget_display(self):
        def fmt(v):
            v = float(v)
            if v >= 10_000_000:
                return f'PKR {v/10_000_000:.1f} Cr'
            return f'PKR {v/100_000:.1f} L'
        if self.budget_min and self.budget_max:
            return f'{fmt(self.budget_min)} – {fmt(self.budget_max)}'
        if self.budget_max:
            return f'Up to {fmt(self.budget_max)}'
        if self.budget_min:
            return f'From {fmt(self.budget_min)}'
        return None

    def get_recommended_properties(self, limit=5):
        qs = Property.objects.filter(status='active').prefetch_related('images').select_related('created_by')
        if self.interested_in:
            qs = qs.filter(property_type__in=self.interested_in)
        if self.budget_max:
            qs = qs.filter(price__lte=float(self.budget_max) * 1.25)
        if self.budget_min:
            qs = qs.filter(price__gte=float(self.budget_min) * 0.75)
        if self.bedrooms_min:
            qs = qs.filter(bedrooms__gte=self.bedrooms_min)
        if self.bedrooms_max:
            qs = qs.filter(bedrooms__lte=self.bedrooms_max + 1)
        props = list(qs[:limit])
        for p in props:
            p.match_pct = self.match_score(p)
        return props

    def match_score(self, prop):
        score, total = 0, 0
        if self.interested_in:
            total += 30
            if prop.property_type in self.interested_in:
                score += 30
        if self.budget_min or self.budget_max:
            total += 25
            p = float(prop.price)
            lo = float(self.budget_min) if self.budget_min else 0
            hi = float(self.budget_max) if self.budget_max else float('inf')
            if lo <= p <= hi:
                score += 25
            elif p <= hi * 1.1:
                score += 12
        if self.bedrooms_min is not None:
            total += 20
            if prop.bedrooms and prop.bedrooms >= self.bedrooms_min:
                score += 20
        if self.area_preferences:
            total += 25
            prefs = [x.strip().lower() for x in self.area_preferences.split(',') if x.strip()]
            loc = (prop.location + ' ' + prop.city).lower()
            if any(p in loc for p in prefs):
                score += 25
        if total == 0:
            return 80
        return min(int(score * 100 / total), 98)

    def required_documents_qs(self, prop=None):
        prop = prop if prop is not None else self.property
        if prop and prop.block_id:
            return prop.block.required_documents.all()
        return BlockRequiredDocument.objects.none()

    def missing_required_documents(self, prop=None):
        required = list(self.required_documents_qs(prop))
        if not required or not self.pk:
            return required
        fulfilled_ids = set(
            self.documents.exclude(requirement_id__isnull=True).values_list('requirement_id', flat=True)
        )
        return [r for r in required if r.pk not in fulfilled_ids]

    def document_progress(self):
        required = list(self.required_documents_qs())
        if not required:
            return None
        total = len(required)
        missing = len(self.missing_required_documents())
        done = total - missing
        return {
            'done': done,
            'total': total,
            'pct': int(done * 100 / total),
        }

    def document_progress_color(self):
        progress = self.document_progress()
        if progress is None:
            return None
        return progress_bucket_color(progress['pct'])

    def documents_complete(self, prop=None):
        return len(self.missing_required_documents(prop)) == 0

    def deal_financials_set(self):
        return self.deal_amount is not None and self.commission_amount is not None

    def payments_complete(self):
        """True only once the deal financials are locked in AND both the deal amount
        and commission have been paid off in full — gates Possession Complete onward."""
        if not self.deal_financials_set():
            return False
        return self.deal_remaining() <= 0 and self.commission_remaining() <= 0

    def total_paid(self):
        return self.payments.aggregate(total=models.Sum('amount'))['total'] or 0

    def deal_paid_total(self):
        return self.payments.filter(payment_against=LeadPayment.AGAINST_DEAL).aggregate(
            total=models.Sum('amount'))['total'] or 0

    def commission_paid_total(self):
        return self.payments.filter(payment_against=LeadPayment.AGAINST_COMMISSION).aggregate(
            total=models.Sum('amount'))['total'] or 0

    def deal_remaining(self):
        if self.deal_amount is None:
            return None
        return max(self.deal_amount - self.deal_paid_total(), 0)

    def commission_remaining(self):
        if self.commission_amount is None:
            return None
        return max(self.commission_amount - self.commission_paid_total(), 0)

    def deal_paid_pct(self):
        if not self.deal_amount:
            return 0
        return min(int(self.deal_paid_total() * 100 / self.deal_amount), 100)

    def commission_paid_pct(self):
        if not self.commission_amount:
            return 0
        return min(int(self.commission_paid_total() * 100 / self.commission_amount), 100)

    def deal_progress_color(self):
        return progress_bucket_color(self.deal_paid_pct())

    def commission_progress_color(self):
        return progress_bucket_color(self.commission_paid_pct())


class LeadActivity(models.Model):
    TYPE_CREATED = 'created'
    TYPE_STATUS = 'status_change'
    TYPE_NOTE = 'note'
    TYPE_DOCUMENT = 'document'
    TYPE_PROPERTY = 'property'
    TYPE_TOKEN = 'token'
    TYPE_FOLLOW_UP = 'follow_up'
    TYPE_CONTACTED = 'contacted'
    TYPE_COLLABORATOR = 'collaborator'
    TYPE_VISIT = 'visit'
    TYPE_PAYMENT = 'payment'

    TYPE_CHOICES = [
        (TYPE_CREATED, 'Lead Created'),
        (TYPE_STATUS, 'Status Changed'),
        (TYPE_NOTE, 'Note Added'),
        (TYPE_DOCUMENT, 'Document Added'),
        (TYPE_PROPERTY, 'Property Shown'),
        (TYPE_TOKEN, 'Token Recorded'),
        (TYPE_FOLLOW_UP, 'Follow-up Scheduled'),
        (TYPE_CONTACTED, 'Contacted'),
        (TYPE_COLLABORATOR, 'Collaborator Updated'),
        (TYPE_VISIT, 'Site Visit Scheduled'),
        (TYPE_PAYMENT, 'Payment Recorded'),
    ]

    TYPE_ICONS = {
        TYPE_CREATED: '🎯',
        TYPE_STATUS: '🔄',
        TYPE_NOTE: '📝',
        TYPE_DOCUMENT: '📎',
        TYPE_PROPERTY: '🏠',
        TYPE_TOKEN: '💰',
        TYPE_FOLLOW_UP: '📅',
        TYPE_CONTACTED: '📞',
        TYPE_COLLABORATOR: '👥',
        TYPE_VISIT: '📅',
        TYPE_PAYMENT: '💳',
    }

    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name='activities')
    activity_type = models.CharField(max_length=30, choices=TYPE_CHOICES)
    description = models.TextField()
    created_by = models.ForeignKey('User', on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.lead} – {self.get_activity_type_display()}'


class LeadDocument(models.Model):
    TYPE_PAYMENT_SLIP = 'payment_slip'
    TYPE_INVOICE = 'invoice'
    TYPE_AGREEMENT = 'agreement'
    TYPE_TOKEN_RECEIPT = 'token_receipt'
    TYPE_OTHER = 'other'

    TYPE_CHOICES = [
        (TYPE_PAYMENT_SLIP, 'Payment Slip'),
        (TYPE_INVOICE, 'Invoice'),
        (TYPE_AGREEMENT, 'Agreement'),
        (TYPE_TOKEN_RECEIPT, 'Token Receipt'),
        (TYPE_OTHER, 'Other'),
    ]

    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name='documents')
    document_type = models.CharField(max_length=20, choices=TYPE_CHOICES)
    title = models.CharField(max_length=200)
    file_url = models.URLField(blank=True)
    amount = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    notes = models.TextField(blank=True)
    requirement = models.ForeignKey(
        'BlockRequiredDocument', on_delete=models.SET_NULL, null=True, blank=True,
        related_name='lead_documents',
        help_text='The block-mandated document requirement this document satisfies, if any.',
    )
    uploaded_by = models.ForeignKey('User', on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def amount_display(self):
        if not self.amount:
            return None
        v = float(self.amount)
        if v >= 10_000_000:
            return f'PKR {v/10_000_000:.2f} Cr'
        return f'PKR {v/100_000:.2f} L'


class LeadPayment(models.Model):
    """A single installment recorded against a lead's Payment Tracking stage —
    e.g. the buyer paying the seller in parts after documentation is complete."""
    METHOD_CASH = 'cash'
    METHOD_ONLINE = 'online'
    METHOD_PAY_ORDER = 'pay_order'
    METHOD_CHEQUE = 'cheque'

    METHOD_CHOICES = [
        (METHOD_CASH, 'Cash'),
        (METHOD_ONLINE, 'Online Transfer'),
        (METHOD_PAY_ORDER, 'Pay Order'),
        (METHOD_CHEQUE, 'Cheque'),
    ]

    # Payment methods that settle via a traceable instrument/transaction rather than
    # handed-over cash, so a reference number is required for an auditable record.
    METHODS_REQUIRING_REFERENCE = {METHOD_ONLINE, METHOD_PAY_ORDER, METHOD_CHEQUE}

    AGAINST_DEAL = 'deal'
    AGAINST_COMMISSION = 'commission'

    AGAINST_CHOICES = [
        (AGAINST_DEAL, 'Deal Amount'),
        (AGAINST_COMMISSION, 'Real Estate Commission'),
    ]

    lead = models.ForeignKey(Lead, on_delete=models.CASCADE, related_name='payments')
    amount = models.DecimalField(max_digits=14, decimal_places=2)
    paid_on = models.DateField()
    payment_method = models.CharField(max_length=20, choices=METHOD_CHOICES, default=METHOD_CASH)
    payment_against = models.CharField(max_length=20, choices=AGAINST_CHOICES, default=AGAINST_DEAL)
    reference_number = models.CharField(
        max_length=100, blank=True,
        help_text='Transaction ID (online) or cheque/pay order number — required for non-cash methods.',
    )
    note = models.CharField(max_length=255, blank=True)
    recorded_by = models.ForeignKey('User', on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-paid_on', '-created_at']

    def __str__(self):
        return f'{self.lead} — PKR {self.amount} on {self.paid_on}'

    def amount_display(self):
        v = float(self.amount)
        if v >= 10_000_000:
            return f'PKR {v/10_000_000:.2f} Cr'
        return f'PKR {v/100_000:.2f} L'


AMENITY_LIST = [
    'Parking', 'Generator', 'Electricity Backup', 'Lift', 'CCTV',
    'Study Room', 'Security', 'Fire Fighting System', 'Central Heating',
    'Gym', 'Furnished', 'Air Conditioning', 'Swimming Pool',
    'Servant Quarter', 'Lawn',
]


class Property(models.Model):
    TYPE_APARTMENT = 'apartment'
    TYPE_HOUSE = 'house'
    TYPE_COMMERCIAL = 'commercial'
    TYPE_PLOT = 'plot'

    PROPERTY_TYPE_CHOICES = [
        (TYPE_APARTMENT, 'Apartment'),
        (TYPE_HOUSE, 'House'),
        (TYPE_COMMERCIAL, 'Commercial'),
        (TYPE_PLOT, 'Plot'),
    ]

    LISTING_SALE = 'sale'
    LISTING_RENT = 'rent'

    LISTING_TYPE_CHOICES = [
        (LISTING_SALE, 'Sale'),
        (LISTING_RENT, 'Rent'),
    ]

    STATUS_ACTIVE = 'active'
    STATUS_INACTIVE = 'inactive'
    STATUS_SOLD = 'sold'

    STATUS_CHOICES = [
        (STATUS_ACTIVE, 'Active'),
        (STATUS_INACTIVE, 'Inactive'),
        (STATUS_SOLD, 'Sold / Closed'),
    ]

    UNIT_SQFT = 'sqft'
    UNIT_SQYD = 'sqyd'
    UNIT_MARLA = 'marla'
    UNIT_KANAL = 'kanal'

    AREA_UNIT_CHOICES = [
        (UNIT_SQFT, 'Sq. Ft'),
        (UNIT_SQYD, 'Sq. Yd'),
        (UNIT_MARLA, 'Marla'),
        (UNIT_KANAL, 'Kanal'),
    ]

    BEDROOM_CHOICES = [(i, str(i)) for i in range(1, 10)] + [(10, '10+')]

    BADGE_NONE = ''
    BADGE_HOT = 'hot'
    BADGE_FEATURED = 'featured'
    BADGE_NEW = 'new'
    BADGE_PRICE_REDUCED = 'price_reduced'
    BADGE_BEST_VALUE = 'best_value'
    BADGE_EXCLUSIVE = 'exclusive'

    BADGE_CHOICES = [
        (BADGE_NONE, '— No Badge —'),
        (BADGE_HOT, '🔥 Hot'),
        (BADGE_FEATURED, '⭐ Featured'),
        (BADGE_NEW, '🆕 New'),
        (BADGE_PRICE_REDUCED, '💰 Price Reduced'),
        (BADGE_BEST_VALUE, '💎 Best Value'),
        (BADGE_EXCLUSIVE, '👑 Exclusive'),
    ]

    title = models.CharField(max_length=255)
    property_type = models.CharField(max_length=20, choices=PROPERTY_TYPE_CHOICES)
    listing_type = models.CharField(max_length=10, choices=LISTING_TYPE_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_ACTIVE)
    show_on_website = models.BooleanField(default=True)
    badge = models.CharField(max_length=20, choices=BADGE_CHOICES, blank=True, default=BADGE_NONE)
    price = models.DecimalField(max_digits=14, decimal_places=2)
    area_size = models.DecimalField(max_digits=10, decimal_places=2)
    area_unit = models.CharField(max_length=10, choices=AREA_UNIT_CHOICES, default=UNIT_SQFT)
    bedrooms = models.PositiveSmallIntegerField(null=True, blank=True)
    bathrooms = models.PositiveSmallIntegerField(null=True, blank=True)
    floor = models.CharField(max_length=50, blank=True)
    city = models.CharField(max_length=100)
    location = models.CharField(max_length=200)
    address = models.TextField()
    description = models.TextField()
    amenities = models.JSONField(default=list, blank=True)
    block = models.ForeignKey(
        'Block', on_delete=models.SET_NULL, null=True, blank=True, related_name='properties'
    )
    customer = models.ForeignKey(
        'Customer', on_delete=models.SET_NULL, null=True, blank=True, related_name='properties'
    )
    created_by = models.ForeignKey(
        'User', on_delete=models.SET_NULL, null=True, related_name='properties'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    sold_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name_plural = 'Properties'

    def __str__(self):
        return self.title

    @property
    def property_id(self):
        return f'PROP-{self.pk:04d}'

    def get_primary_image(self):
        return self.images.filter(is_primary=True).first() or self.images.first()

    def price_display(self):
        crore = self.price / 10_000_000
        if crore >= 1:
            return f'PKR {crore:.2f} Cr'
        lakh = self.price / 100_000
        return f'PKR {lakh:.2f} L'

    def size_display(self):
        size = int(self.area_size) if self.area_size == int(self.area_size) else self.area_size
        return f'{size:,} {self.get_area_unit_display()}'


class Role(models.Model):
    name = models.CharField(max_length=50, unique=True)
    description = models.TextField(blank=True)
    permissions = models.JSONField(default=list)
    is_system = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name

    def has_permission(self, perm):
        return perm in (self.permissions or [])

    def permission_labels(self):
        label_map = dict(PERMISSION_LIST)
        return [label_map[p] for p in (self.permissions or []) if p in label_map]


class PushSubscription(models.Model):
    user = models.ForeignKey('User', on_delete=models.CASCADE, related_name='push_subscriptions')
    endpoint = models.TextField(unique=True)
    p256dh = models.TextField()
    auth = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'{self.user.email} — push'


class Notification(models.Model):
    recipient = models.ForeignKey('User', on_delete=models.CASCADE, related_name='notifications')
    title = models.CharField(max_length=200)
    body = models.CharField(max_length=500, blank=True)
    url = models.CharField(max_length=300, blank=True)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.recipient.email} — {self.title}'


class PropertyImage(models.Model):
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='images')
    image = models.URLField(max_length=500)
    is_primary = models.BooleanField(default=False)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-is_primary', 'uploaded_at']

    def __str__(self):
        return f'Image for {self.property.title}'


class PropertyDocument(models.Model):
    TYPE_TITLE_DEED = 'title_deed'
    TYPE_AGREEMENT = 'agreement'
    TYPE_NOC = 'noc'
    TYPE_TAX_CERTIFICATE = 'tax_certificate'
    TYPE_FLOOR_PLAN = 'floor_plan'
    TYPE_OTHER = 'other'

    TYPE_CHOICES = [
        (TYPE_TITLE_DEED, 'Title Deed'),
        (TYPE_AGREEMENT, 'Agreement'),
        (TYPE_NOC, 'NOC'),
        (TYPE_TAX_CERTIFICATE, 'Tax Certificate'),
        (TYPE_FLOOR_PLAN, 'Floor Plan'),
        (TYPE_OTHER, 'Other'),
    ]

    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='documents')
    document_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default=TYPE_OTHER)
    title = models.CharField(max_length=200)
    file_url = models.URLField(max_length=500)
    uploaded_by = models.ForeignKey('User', on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.title} ({self.property.title})'


class PropertyActivity(models.Model):
    TYPE_CREATED = 'created'
    TYPE_UPDATED = 'updated'
    TYPE_STATUS = 'status_change'
    TYPE_DOCUMENT = 'document'

    TYPE_CHOICES = [
        (TYPE_CREATED, 'Property Created'),
        (TYPE_UPDATED, 'Details Updated'),
        (TYPE_STATUS, 'Status Changed'),
        (TYPE_DOCUMENT, 'Document Added'),
    ]

    TYPE_ICONS = {
        TYPE_CREATED: '🎯',
        TYPE_UPDATED: '✏️',
        TYPE_STATUS: '🔄',
        TYPE_DOCUMENT: '📎',
    }

    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='activities')
    activity_type = models.CharField(max_length=30, choices=TYPE_CHOICES)
    description = models.TextField()
    created_by = models.ForeignKey('User', on_delete=models.SET_NULL, null=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']
        verbose_name_plural = 'Property Activities'

    def __str__(self):
        return f'{self.property} – {self.get_activity_type_display()}'


class AgentTarget(models.Model):
    MONTH_NAMES = [
        '', 'January', 'February', 'March', 'April', 'May', 'June',
        'July', 'August', 'September', 'October', 'November', 'December',
    ]

    agent = models.ForeignKey('User', on_delete=models.CASCADE, related_name='targets')
    year = models.PositiveSmallIntegerField()
    month = models.PositiveSmallIntegerField()
    deals_target = models.PositiveIntegerField(default=0)
    revenue_target = models.DecimalField(max_digits=14, decimal_places=2, default=0)
    set_by = models.ForeignKey('User', on_delete=models.SET_NULL, null=True, related_name='+')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-year', '-month']
        unique_together = ('agent', 'year', 'month')

    def __str__(self):
        return f'{self.agent} — {self.month_label()}'

    def month_label(self):
        return f'{self.MONTH_NAMES[self.month]} {self.year}'


class PropertySubmission(models.Model):
    """A property submitted via the public website — either to be listed for sale/rent,
    or just for a free market evaluation. Staff triage these in the CRM; approving one
    creates a real Property (visible on the website) and links back here via converted_property."""
    TYPE_LISTING = 'listing'
    TYPE_EVALUATION = 'evaluation'

    TYPE_CHOICES = [
        (TYPE_LISTING, 'List My Property'),
        (TYPE_EVALUATION, 'Property Evaluation'),
    ]

    STATUS_PENDING = 'pending'
    STATUS_CONTACTED = 'contacted'
    STATUS_EVALUATED = 'evaluated'
    STATUS_LISTED = 'listed'
    STATUS_REJECTED = 'rejected'

    STATUS_CHOICES = [
        (STATUS_PENDING, 'Under Review'),
        (STATUS_CONTACTED, 'Contacted'),
        (STATUS_EVALUATED, 'Evaluated'),
        (STATUS_LISTED, 'Listed'),
        (STATUS_REJECTED, 'Rejected'),
    ]

    STATUS_COLORS = {
        STATUS_PENDING: '#f59e0b',
        STATUS_CONTACTED: '#3b82f6',
        STATUS_EVALUATED: '#8b5cf6',
        STATUS_LISTED: '#22c55e',
        STATUS_REJECTED: '#ef4444',
    }

    PAYMENT_NOT_APPLICABLE = 'n/a'
    PAYMENT_PENDING = 'pending'
    PAYMENT_PAID = 'paid'
    PAYMENT_FAILED = 'failed'

    PAYMENT_STATUS_CHOICES = [
        (PAYMENT_NOT_APPLICABLE, 'Not Applicable'),
        (PAYMENT_PENDING, 'Payment Pending'),
        (PAYMENT_PAID, 'Paid'),
        (PAYMENT_FAILED, 'Payment Failed'),
    ]

    submission_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default=TYPE_LISTING)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_PENDING)

    wants_featured = models.BooleanField(default=False)
    featured_fee = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    payment_status = models.CharField(max_length=20, choices=PAYMENT_STATUS_CHOICES, default=PAYMENT_NOT_APPLICABLE)
    safepay_tracker_token = models.CharField(max_length=100, blank=True)

    property_type = models.CharField(max_length=20, choices=Property.PROPERTY_TYPE_CHOICES)
    purpose = models.CharField(max_length=10, choices=Property.LISTING_TYPE_CHOICES, blank=True)
    bedrooms = models.PositiveSmallIntegerField(null=True, blank=True)
    bathrooms = models.PositiveSmallIntegerField(null=True, blank=True)
    area_size = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    area_unit = models.CharField(max_length=10, choices=Property.AREA_UNIT_CHOICES, default=Property.UNIT_MARLA)
    city = models.CharField(max_length=100)
    location = models.CharField(max_length=200, blank=True)
    description = models.TextField(blank=True)
    asking_price = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)

    full_name = models.CharField(max_length=150)
    phone = models.CharField(max_length=20)
    email = models.EmailField(blank=True)

    assigned_to = models.ForeignKey(
        'User', on_delete=models.SET_NULL, null=True, blank=True, related_name='property_submissions'
    )
    internal_notes = models.TextField(blank=True)
    converted_property = models.OneToOneField(
        'Property', on_delete=models.SET_NULL, null=True, blank=True, related_name='source_submission'
    )

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.get_submission_type_display()} — {self.full_name} ({self.city})'

    def reference_code(self):
        return f'PIE-{self.pk:06d}'

    def status_color(self):
        return self.STATUS_COLORS.get(self.status, '#6b7280')

    def payment_status_color(self):
        return {
            self.PAYMENT_PENDING: '#f59e0b',
            self.PAYMENT_PAID: '#22c55e',
            self.PAYMENT_FAILED: '#ef4444',
        }.get(self.payment_status, '#6b7280')


class PropertySubmissionImage(models.Model):
    submission = models.ForeignKey(PropertySubmission, on_delete=models.CASCADE, related_name='images')
    image_url = models.URLField(max_length=500)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']

    def __str__(self):
        return f'Image for {self.submission}'


class SiteSettings(models.Model):
    """Singleton row (always pk=1) holding admin-configurable site-wide settings."""
    ENV_SANDBOX = 'sandbox'
    ENV_PRODUCTION = 'production'

    ENV_CHOICES = [
        (ENV_SANDBOX, 'Sandbox (Testing)'),
        (ENV_PRODUCTION, 'Production (Live)'),
    ]

    featured_listing_fee = models.DecimalField(max_digits=10, decimal_places=2, default=5000)
    safepay_environment = models.CharField(max_length=20, choices=ENV_CHOICES, default=ENV_SANDBOX)
    safepay_api_key = models.CharField(max_length=200, blank=True, help_text='Safepay Client/Public Key')
    safepay_secret_key = models.CharField(max_length=200, blank=True, help_text='Safepay Secret Key')
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return 'Site Settings'

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        pass

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    @property
    def payments_configured(self):
        return bool(self.safepay_api_key and self.safepay_secret_key)
