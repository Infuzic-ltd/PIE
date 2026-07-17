from django.contrib.auth.models import AbstractUser
from django.db import models


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

    USERNAME_FIELD = 'email'
    REQUIRED_FIELDS = ['username', 'first_name', 'last_name']

    def get_full_name(self):
        return f'{self.first_name} {self.last_name}'.strip() or self.email

    def __str__(self):
        return self.email


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


class PropertyImage(models.Model):
    property = models.ForeignKey(Property, on_delete=models.CASCADE, related_name='images')
    image = models.URLField(max_length=500)
    is_primary = models.BooleanField(default=False)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-is_primary', 'uploaded_at']

    def __str__(self):
        return f'Image for {self.property.title}'
