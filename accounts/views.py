from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.db.models import Q
import cloudinary.uploader
from .forms import SignupForm, LoginForm, PropertyForm
from .models import Property, PropertyImage


def _upload_images(request_files, prop):
    """Upload files to Cloudinary and create PropertyImage records."""
    files = request_files.getlist('images')
    already_has_primary = prop.images.filter(is_primary=True).exists()
    for i, f in enumerate(files):
        result = cloudinary.uploader.upload(
            f,
            folder='pie-crm',
            resource_type='image',
        )
        is_primary = (i == 0) and not already_has_primary
        PropertyImage.objects.create(
            property=prop,
            image=result['secure_url'],
            is_primary=is_primary,
        )


def login_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    form = LoginForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        login(request, form.get_user())
        return redirect(request.GET.get('next', 'dashboard'))
    return render(request, 'accounts/login.html', {'form': form})


def signup_view(request):
    if request.user.is_authenticated:
        return redirect('dashboard')
    form = SignupForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        return redirect('login')
    return render(request, 'accounts/signup.html', {'form': form})


def logout_view(request):
    logout(request)
    return redirect('login')


@login_required
def dashboard_view(request):
    return render(request, 'accounts/dashboard.html', {'user': request.user})


# ── Properties ────────────────────────────────────────────────────────────────

@login_required
def property_list(request):
    qs = Property.objects.prefetch_related('images').all()

    q = request.GET.get('q', '').strip()
    status = request.GET.get('status', '')
    ptype = request.GET.get('type', '')
    city = request.GET.get('city', '')
    location = request.GET.get('location', '')

    if q:
        qs = qs.filter(Q(title__icontains=q) | Q(city__icontains=q) | Q(location__icontains=q))
    if status:
        qs = qs.filter(status=status)
    if ptype:
        qs = qs.filter(property_type=ptype)
    if city:
        qs = qs.filter(city__icontains=city)
    if location:
        qs = qs.filter(location__icontains=location)

    total = Property.objects.count()
    active = Property.objects.filter(status=Property.STATUS_ACTIVE).count()
    sold = Property.objects.filter(status=Property.STATUS_SOLD).count()
    inactive = Property.objects.filter(status=Property.STATUS_INACTIVE).count()

    return render(request, 'accounts/property_listing.html', {
        'properties': qs,
        'total': total,
        'active': active,
        'sold': sold,
        'inactive': inactive,
        'filters': {'q': q, 'status': status, 'type': ptype, 'city': city, 'location': location},
    })


@login_required
def property_create(request):
    form = PropertyForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        prop = form.save(commit=False)
        prop.created_by = request.user
        prop.save()
        _upload_images(request.FILES, prop)
        return redirect('property_view', pk=prop.pk)
    return render(request, 'accounts/property_create.html', {'form': form})


@login_required
def property_view(request, pk):
    prop = get_object_or_404(Property.objects.prefetch_related('images'), pk=pk)
    return render(request, 'accounts/property_view.html', {'property': prop})


@login_required
def property_update(request, pk):
    prop = get_object_or_404(Property, pk=pk)
    form = PropertyForm(request.POST or None, instance=prop)
    if request.method == 'POST' and form.is_valid():
        form.save()
        _upload_images(request.FILES, prop)
        return redirect('property_view', pk=prop.pk)
    return render(request, 'accounts/property_update.html', {'form': form, 'property': prop})


@login_required
def property_delete(request, pk):
    prop = get_object_or_404(Property, pk=pk)
    if request.method == 'POST':
        prop.delete()
        return redirect('property_list')
    return render(request, 'accounts/property_confirm_delete.html', {'property': prop})


@login_required
def property_set_status(request, pk):
    if request.method == 'POST':
        prop = get_object_or_404(Property, pk=pk)
        new_status = request.POST.get('status')
        if new_status in (Property.STATUS_ACTIVE, Property.STATUS_INACTIVE, Property.STATUS_SOLD):
            prop.status = new_status
            prop.save()
    return redirect(request.POST.get('next', 'property_list'))


@login_required
def property_image_delete(request, pk):
    img = get_object_or_404(PropertyImage, pk=pk)
    prop_pk = img.property.pk
    if request.method == 'POST':
        img.delete()
    return redirect('property_update', pk=prop_pk)
