import json
from functools import wraps
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.http import JsonResponse, HttpResponseForbidden
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.db.models import Q
from django.conf import settings
import cloudinary.uploader
from pywebpush import webpush, WebPushException
from py_vapid import Vapid01
from .forms import SignupForm, LoginForm, PropertyForm, TeamMemberCreateForm, TeamMemberUpdateForm, RoleForm
from .models import Property, PropertyImage, PushSubscription, Role, User


# ── Access decorators ─────────────────────────────────────────────────────────

def admin_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect('login')
        if not request.user.is_crm_admin:
            return render(request, 'accounts/403.html', status=403)
        return view_func(request, *args, **kwargs)
    return wrapper


def permission_required(perm):
    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect('login')
            if not request.user.has_crm_permission(perm):
                return render(request, 'accounts/403.html', status=403)
            return view_func(request, *args, **kwargs)
        return wrapper
    return decorator


# ── Push notification helper ──────────────────────────────────────────────────

def _get_vapid():
    pem = settings.VAPID_PRIVATE_KEY
    # Restore actual newlines if Vercel stored them as literal \n
    if '\\n' in pem:
        pem = pem.replace('\\n', '\n')
    return Vapid01.from_pem(pem.encode('utf-8'))


def _send_push(subscription, title, body, url='/'):
    try:
        vapid = _get_vapid()
        webpush(
            subscription_info={
                'endpoint': subscription.endpoint,
                'keys': {'p256dh': subscription.p256dh, 'auth': subscription.auth},
            },
            data=json.dumps({'title': title, 'body': body, 'url': url}),
            vapid_private_key=vapid,
            vapid_claims={'sub': f'mailto:{settings.VAPID_ADMIN_EMAIL}'},
        )
        return True, None
    except WebPushException as e:
        if e.response and e.response.status_code == 410:
            subscription.delete()
        return False, str(e)
    except Exception as e:
        return False, str(e)


def notify_all(title, body, url='/'):
    for sub in PushSubscription.objects.select_related('user').all():
        _send_push(sub, title, body, url)  # errors are swallowed per-subscription


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
    # Signup is closed — users are added by admin via Teams
    return redirect('login')


def logout_view(request):
    logout(request)
    return redirect('login')


@login_required
def dashboard_view(request):
    return render(request, 'accounts/dashboard.html', {
        'user': request.user,
        'vapid_public_key': settings.VAPID_PUBLIC_KEY,
    })


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


# ── Web Push ──────────────────────────────────────────────────────────────────

def service_worker(request):
    """Serve the service worker JS from a template so it can use Django variables."""
    from django.template.loader import render_to_string
    from django.http import HttpResponse
    content = render_to_string('sw.js', {}, request=request)
    return HttpResponse(content, content_type='application/javascript')


@login_required
@require_POST
def push_subscribe(request):
    try:
        data = json.loads(request.body)
        endpoint = data['endpoint']
        p256dh = data['keys']['p256dh']
        auth = data['keys']['auth']
        PushSubscription.objects.update_or_create(
            endpoint=endpoint,
            defaults={'user': request.user, 'p256dh': p256dh, 'auth': auth},
        )
        return JsonResponse({'status': 'subscribed'})
    except (KeyError, json.JSONDecodeError):
        return JsonResponse({'error': 'invalid payload'}, status=400)


@login_required
@require_POST
def push_unsubscribe(request):
    try:
        data = json.loads(request.body)
        PushSubscription.objects.filter(endpoint=data.get('endpoint', '')).delete()
        return JsonResponse({'status': 'unsubscribed'})
    except json.JSONDecodeError:
        return JsonResponse({'error': 'invalid payload'}, status=400)


# ── Team management ───────────────────────────────────────────────────────────

@admin_required
def team_list(request):
    members = User.objects.select_related('assigned_role').order_by('first_name', 'last_name')
    return render(request, 'accounts/teams.html', {'members': members})


@admin_required
def team_member_create(request):
    form = TeamMemberCreateForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        return redirect('team_list')
    return render(request, 'accounts/team_member_form.html', {'form': form, 'action': 'Add Member'})


@admin_required
def team_member_update(request, pk):
    member = get_object_or_404(User, pk=pk)
    form = TeamMemberUpdateForm(request.POST or None, instance=member)
    if request.method == 'POST' and form.is_valid():
        form.save()
        return redirect('team_list')
    return render(request, 'accounts/team_member_form.html', {
        'form': form, 'member': member, 'action': 'Edit Member',
    })


@admin_required
def team_member_delete(request, pk):
    member = get_object_or_404(User, pk=pk)
    if request.method == 'POST':
        member.delete()
        return redirect('team_list')
    return render(request, 'accounts/team_confirm_delete.html', {'member': member})


# ── Role management ───────────────────────────────────────────────────────────

@admin_required
def role_list(request):
    roles = Role.objects.prefetch_related('members').all()
    return render(request, 'accounts/roles.html', {'roles': roles})


@admin_required
def role_create(request):
    form = RoleForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        return redirect('role_list')
    return render(request, 'accounts/role_form.html', {'form': form, 'action': 'Create Role'})


@admin_required
def role_update(request, pk):
    role = get_object_or_404(Role, pk=pk)
    form = RoleForm(request.POST or None, instance=role)
    if request.method == 'POST' and form.is_valid():
        form.save()
        return redirect('role_list')
    return render(request, 'accounts/role_form.html', {
        'form': form, 'role': role, 'action': 'Edit Role',
    })


@admin_required
def role_delete(request, pk):
    role = get_object_or_404(Role, pk=pk)
    if role.is_system:
        return redirect('role_list')
    if request.method == 'POST':
        role.delete()
        return redirect('role_list')
    return render(request, 'accounts/role_confirm_delete.html', {'role': role})


# ── Web Push ──────────────────────────────────────────────────────────────────

@login_required
@require_POST
def push_test(request):
    subs = list(PushSubscription.objects.filter(user=request.user))
    if not subs:
        return JsonResponse({'error': 'no subscription found — enable notifications first'}, status=404)
    sent = 0
    errors = []
    for sub in subs:
        ok, err = _send_push(sub, 'PIE Real Estate', 'Test notification works! ✓', '/dashboard/')
        if ok:
            sent += 1
        elif err:
            errors.append(err)
    if sent == 0:
        return JsonResponse({'error': errors[0] if errors else 'send failed'}, status=500)
    return JsonResponse({'status': 'sent', 'count': sent})
