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

    email = models.EmailField(unique=True)
    phone = models.CharField(max_length=20, blank=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default=ROLE_AGENT)
    assigned_role = models.ForeignKey(
        'Role', on_delete=models.SET_NULL, null=True, blank=True, related_name='members'
    )

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


class Block(models.Model):
    name = models.CharField(max_length=50, unique=True)

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class Lead(models.Model):
    STATUS_NEW = 'new'
    STATUS_CONTACTED = 'contacted'
    STATUS_QUALIFIED = 'qualified'
    STATUS_FOLLOW_UP = 'follow_up'
    STATUS_PROPOSAL = 'proposal'
    STATUS_NEGOTIATION = 'negotiation'
    STATUS_TOKEN = 'token'
    STATUS_CONVERTED = 'converted'
    STATUS_LOST = 'lost'

    STATUS_CHOICES = [
        (STATUS_NEW, 'New'),
        (STATUS_CONTACTED, 'Contacted'),
        (STATUS_QUALIFIED, 'Qualified'),
        (STATUS_FOLLOW_UP, 'Follow Up'),
        (STATUS_PROPOSAL, 'Proposal'),
        (STATUS_NEGOTIATION, 'Negotiation'),
        (STATUS_TOKEN, 'Token'),
        (STATUS_CONVERTED, 'Converted'),
        (STATUS_LOST, 'Closed Lost'),
    ]

    STATUS_COLORS = {
        STATUS_NEW: '#3b82f6',
        STATUS_CONTACTED: '#f59e0b',
        STATUS_QUALIFIED: '#10b981',
        STATUS_FOLLOW_UP: '#f97316',
        STATUS_PROPOSAL: '#8b5cf6',
        STATUS_NEGOTIATION: '#06b6d4',
        STATUS_TOKEN: '#ec4899',
        STATUS_CONVERTED: '#059669',
        STATUS_LOST: '#6b7280',
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
        ('property_listing', 'Property Listing'),
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

    full_name = models.CharField(max_length=150)
    email = models.EmailField(blank=True)
    phone = models.CharField(max_length=20)
    alternate_phone = models.CharField(max_length=20, blank=True)
    lead_type = models.CharField(max_length=20, choices=TYPE_CHOICES, default=TYPE_BUYER)
    source = models.CharField(max_length=30, choices=SOURCE_CHOICES, default='website')
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_NEW)
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
    token_amount = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)
    notes = models.TextField(blank=True)
    follow_up_date = models.DateTimeField(null=True, blank=True)
    last_contacted = models.DateTimeField(null=True, blank=True)
    assigned_to = models.ForeignKey(
        'User', on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_leads'
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


class LeadActivity(models.Model):
    TYPE_CREATED = 'created'
    TYPE_STATUS = 'status_change'
    TYPE_NOTE = 'note'
    TYPE_DOCUMENT = 'document'
    TYPE_PROPERTY = 'property'
    TYPE_TOKEN = 'token'
    TYPE_FOLLOW_UP = 'follow_up'
    TYPE_CONTACTED = 'contacted'

    TYPE_CHOICES = [
        (TYPE_CREATED, 'Lead Created'),
        (TYPE_STATUS, 'Status Changed'),
        (TYPE_NOTE, 'Note Added'),
        (TYPE_DOCUMENT, 'Document Added'),
        (TYPE_PROPERTY, 'Property Shown'),
        (TYPE_TOKEN, 'Token Recorded'),
        (TYPE_FOLLOW_UP, 'Follow-up Scheduled'),
        (TYPE_CONTACTED, 'Contacted'),
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

    title = models.CharField(max_length=255)
    property_type = models.CharField(max_length=20, choices=PROPERTY_TYPE_CHOICES)
    listing_type = models.CharField(max_length=10, choices=LISTING_TYPE_CHOICES)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default=STATUS_ACTIVE)
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


class PropertyImage(models.Model):
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='images')
    image = models.URLField(max_length=500)
    is_primary = models.BooleanField(default=False)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-is_primary', 'uploaded_at']

    def __str__(self):
        return f'Image for {self.property.title}'
