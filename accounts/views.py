import json
import re
from decimal import Decimal, InvalidOperation
from urllib.parse import quote
from functools import wraps
from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth import login, logout
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.http import JsonResponse, HttpResponseForbidden
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST
from django.db.models import Q, Sum, Count
from django.conf import settings
from django.urls import reverse
from django.utils import timezone
from django.utils.dateparse import parse_datetime, parse_date
import cloudinary.uploader
from pywebpush import webpush, WebPushException
from py_vapid import Vapid01
from .forms import SignupForm, LoginForm, PropertyForm, CustomerForm, BlockForm, TeamMemberCreateForm, TeamMemberUpdateForm, RoleForm, LeadForm, LeadDocumentForm
from .models import Property, PropertyImage, PropertyDocument, PropertyActivity, PushSubscription, Notification, Role, User, Customer, Block, BlockRequiredDocument, Lead, LeadActivity, LeadDocument, LeadPayment, AgentTarget, PropertySubmission, PropertySubmissionImage


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
    Notification.objects.bulk_create([
        Notification(recipient=u, title=title, body=body, url=url)
        for u in User.objects.filter(is_active=True)
    ])
    for sub in PushSubscription.objects.select_related('user').all():
        _send_push(sub, title, body, url)  # errors are swallowed per-subscription


def notify_user(user, title, body, url='/'):
    Notification.objects.create(recipient=user, title=title, body=body, url=url)
    for sub in PushSubscription.objects.filter(user=user):
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


def website_homepage(request):
    return render(request, 'website/homepage.html')


def website_about(request):
    return render(request, 'website/about.html')


def website_services(request):
    return render(request, 'website/services.html')


def website_properties(request):
    return render(request, 'website/properties.html')


def website_contact(request):
    return render(request, 'website/contact.html')


def website_listing(request):
    return render(request, 'website/listing.html', {
        'property_type_choices': Property.PROPERTY_TYPE_CHOICES,
        'listing_type_choices': Property.LISTING_TYPE_CHOICES,
        'area_unit_choices': Property.AREA_UNIT_CHOICES,
        'blocks': Block.objects.all(),
    })


@require_POST
def submit_property_listing(request):
    """Public endpoint behind the 'List My Property' / 'Property Evaluation' form —
    creates a PropertySubmission for CRM staff to triage. No login required."""
    submission_type = request.POST.get('submission_type', PropertySubmission.TYPE_LISTING)
    if submission_type not in dict(PropertySubmission.TYPE_CHOICES):
        submission_type = PropertySubmission.TYPE_LISTING

    full_name = request.POST.get('full_name', '').strip()
    phone = request.POST.get('phone', '').strip()
    city = request.POST.get('city', '').strip()
    property_type = request.POST.get('property_type', '').strip()

    errors = {}
    if not full_name:
        errors['full_name'] = 'Your name is required.'
    if not phone:
        errors['phone'] = 'A contact phone number is required.'
    if not city:
        errors['city'] = 'City is required.'
    if property_type not in dict(Property.PROPERTY_TYPE_CHOICES):
        errors['property_type'] = 'Select a valid property type.'
    if errors:
        return JsonResponse({'ok': False, 'errors': errors}, status=400)

    purpose = request.POST.get('purpose', '').strip()
    if purpose not in dict(Property.LISTING_TYPE_CHOICES):
        purpose = ''

    area_unit = request.POST.get('area_unit', Property.UNIT_MARLA).strip()
    if area_unit not in dict(Property.AREA_UNIT_CHOICES):
        area_unit = Property.UNIT_MARLA

    submission = PropertySubmission.objects.create(
        submission_type=submission_type,
        property_type=property_type,
        purpose=purpose,
        bedrooms=_int_or_none(request.POST.get('bedrooms')),
        bathrooms=_int_or_none(request.POST.get('bathrooms')),
        area_size=_decimal_or_none(request.POST.get('area_size')),
        area_unit=area_unit,
        city=city,
        location=request.POST.get('location', '').strip(),
        description=request.POST.get('description', '').strip(),
        asking_price=_decimal_or_none(request.POST.get('asking_price')),
        full_name=full_name,
        phone=phone,
        email=request.POST.get('email', '').strip(),
    )

    for f in request.FILES.getlist('images')[:10]:
        if not f.content_type.startswith('image/'):
            continue
        result = cloudinary.uploader.upload(f, folder='pie-website/submissions', resource_type='image')
        PropertySubmissionImage.objects.create(submission=submission, image_url=result['secure_url'])

    return JsonResponse({'ok': True, 'reference': submission.reference_code()}, status=201)


def lead_api_docs(request):
    return render(request, 'website/lead_api_docs.html')


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


def _pkr_millions(value):
    return f'PKR {float(value or 0) / 1_000_000:.1f}M'


def _agent_performance(year, month):
    """Build a revenue-ranked performance list for every active agent for a given month."""
    agents = User.objects.filter(role=User.ROLE_AGENT, is_active=True).order_by('first_name', 'last_name')
    targets = {t.agent_id: t for t in AgentTarget.objects.filter(year=year, month=month)}
    sold_qs = (
        Property.objects.filter(status=Property.STATUS_SOLD, sold_at__year=year, sold_at__month=month)
        .values('created_by')
        .annotate(deals=Count('id'), revenue=Sum('price'))
    )
    sold_map = {row['created_by']: row for row in sold_qs if row['created_by'] is not None}

    rows = []
    for agent in agents:
        target = targets.get(agent.pk)
        sold = sold_map.get(agent.pk, {})
        deals_actual = sold.get('deals', 0)
        revenue_actual = sold.get('revenue') or 0
        deals_target = target.deals_target if target else 0
        revenue_target = target.revenue_target if target else Decimal('0')
        pct = int(min(float(revenue_actual) / float(revenue_target) * 100, 100)) if revenue_target else (100 if revenue_actual else 0)
        rows.append({
            'agent': agent,
            'deals_actual': deals_actual,
            'revenue_actual': revenue_actual,
            'revenue_actual_display': _pkr_millions(revenue_actual),
            'deals_target': deals_target,
            'revenue_target': revenue_target,
            'revenue_target_display': _pkr_millions(revenue_target),
            'pct': pct,
        })
    rows.sort(key=lambda r: r['revenue_actual'], reverse=True)
    return rows


@login_required
def dashboard_view(request):
    today = timezone.localdate()
    performance = _agent_performance(today.year, today.month)
    return render(request, 'accounts/dashboard.html', {
        'user': request.user,
        'vapid_public_key': settings.VAPID_PUBLIC_KEY,
        'agent_performance': performance[:5],
    })


@login_required
def agent_performance_list(request):
    today = timezone.localdate()
    try:
        year = int(request.GET.get('year', today.year))
        month = int(request.GET.get('month', today.month))
    except ValueError:
        year, month = today.year, today.month
    if month < 1 or month > 12:
        month = today.month
    performance = _agent_performance(year, month)
    return render(request, 'accounts/agent_performance.html', {
        'performance': performance,
        'year': year,
        'month': month,
        'month_label': AgentTarget.MONTH_NAMES[month],
        'month_choices': list(enumerate(AgentTarget.MONTH_NAMES))[1:],
        'year_choices': range(today.year - 2, today.year + 2),
    })


@admin_required
@require_POST
def set_agent_target(request):
    agent = get_object_or_404(User, pk=request.POST.get('agent_id'), role=User.ROLE_AGENT)
    try:
        year = int(request.POST.get('year'))
        month = int(request.POST.get('month'))
    except (TypeError, ValueError):
        return redirect('agent_performance')
    try:
        deals_target = int(request.POST.get('deals_target') or 0)
    except ValueError:
        deals_target = 0
    try:
        revenue_target = Decimal(request.POST.get('revenue_target') or 0)
    except InvalidOperation:
        revenue_target = Decimal('0')
    AgentTarget.objects.update_or_create(
        agent=agent, year=year, month=month,
        defaults={'deals_target': deals_target, 'revenue_target': revenue_target, 'set_by': request.user},
    )
    return redirect(f"{reverse('agent_performance')}?year={year}&month={month}")


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
    form = PropertyForm(request.POST or None, user=request.user)
    if request.method == 'POST' and form.is_valid():
        prop = form.save(commit=False)
        prop.created_by = request.user
        prop.save()
        _upload_images(request.FILES, prop)
        PropertyActivity.objects.create(
            property=prop,
            activity_type=PropertyActivity.TYPE_CREATED,
            description=f'Property listed by {request.user.get_full_name() or request.user.email}.',
            created_by=request.user,
        )
        return redirect('property_view', pk=prop.pk)
    return render(request, 'accounts/property_create.html', {
        'form': form,
        'blocks': Block.objects.all(),
    })


@login_required
def property_view(request, pk):
    prop = get_object_or_404(
        Property.objects.prefetch_related('images', 'documents', 'activities__created_by').select_related('customer', 'created_by', 'block'),
        pk=pk,
    )
    can_see_customer = request.user.is_crm_admin or request.user == prop.created_by
    return render(request, 'accounts/property_view.html', {
        'property': prop,
        'can_see_customer': can_see_customer,
    })


@login_required
def property_update(request, pk):
    prop = get_object_or_404(
        Property.objects.prefetch_related('images', 'documents'), pk=pk,
    )
    old_status = prop.status
    form = PropertyForm(request.POST or None, instance=prop, user=request.user)
    if request.method == 'POST' and form.is_valid():
        form.save()
        if prop.status == Property.STATUS_SOLD and old_status != Property.STATUS_SOLD:
            prop.sold_at = timezone.now()
            prop.save(update_fields=['sold_at'])
        _upload_images(request.FILES, prop)
        PropertyActivity.objects.create(
            property=prop,
            activity_type=PropertyActivity.TYPE_UPDATED,
            description=f'Property details updated by {request.user.get_full_name() or request.user.email}.',
            created_by=request.user,
        )
        return redirect('property_view', pk=prop.pk)
    return render(request, 'accounts/property_update.html', {
        'form': form,
        'property': prop,
        'blocks': Block.objects.all(),
    })


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
        if new_status in (Property.STATUS_ACTIVE, Property.STATUS_INACTIVE, Property.STATUS_SOLD) and new_status != prop.status:
            old_display = prop.get_status_display()
            prop.status = new_status
            if new_status == Property.STATUS_SOLD:
                prop.sold_at = timezone.now()
            prop.save()
            PropertyActivity.objects.create(
                property=prop,
                activity_type=PropertyActivity.TYPE_STATUS,
                description=f'Status changed from {old_display} to {prop.get_status_display()} by {request.user.get_full_name() or request.user.email}.',
                created_by=request.user,
            )
    return redirect(request.POST.get('next', 'property_list'))


@login_required
def property_image_delete(request, pk):
    img = get_object_or_404(PropertyImage, pk=pk)
    prop_pk = img.property.pk
    if request.method == 'POST':
        img.delete()
    next_url = request.GET.get('next') or request.POST.get('next')
    return redirect(next_url) if next_url else redirect('property_update', pk=prop_pk)


@login_required
@require_POST
def property_add_document(request, pk):
    prop = get_object_or_404(Property, pk=pk)
    title = request.POST.get('title', '').strip()
    doc_type = request.POST.get('document_type') or PropertyDocument.TYPE_OTHER
    f = request.FILES.get('file')
    if title and f:
        result = cloudinary.uploader.upload(f, folder='pie-crm/documents', resource_type='auto')
        doc = PropertyDocument.objects.create(
            property=prop,
            document_type=doc_type,
            title=title,
            file_url=result['secure_url'],
            uploaded_by=request.user,
        )
        PropertyActivity.objects.create(
            property=prop,
            activity_type=PropertyActivity.TYPE_DOCUMENT,
            description=f'{doc.get_document_type_display()} "{doc.title}" uploaded by {request.user.get_full_name() or request.user.email}.',
            created_by=request.user,
        )
    next_url = request.GET.get('next') or request.POST.get('next')
    return redirect(next_url) if next_url else redirect('property_update', pk=prop.pk)


@login_required
@require_POST
def property_document_delete(request, pk):
    doc = get_object_or_404(PropertyDocument, pk=pk)
    prop = doc.property
    title = doc.title
    doc.delete()
    PropertyActivity.objects.create(
        property=prop,
        activity_type=PropertyActivity.TYPE_DOCUMENT,
        description=f'Document "{title}" removed by {request.user.get_full_name() or request.user.email}.',
        created_by=request.user,
    )
    next_url = request.GET.get('next') or request.POST.get('next')
    return redirect(next_url) if next_url else redirect('property_update', pk=prop.pk)


# ── Property Submissions (website "List My Property" / "Property Evaluation") ──

@login_required
def property_submission_list(request):
    qs = PropertySubmission.objects.select_related('assigned_to', 'converted_property').all()

    q = request.GET.get('q', '').strip()
    status = request.GET.get('status', '')
    submission_type = request.GET.get('type', '')

    if q:
        qs = qs.filter(Q(full_name__icontains=q) | Q(phone__icontains=q) | Q(city__icontains=q))
    if status:
        qs = qs.filter(status=status)
    if submission_type:
        qs = qs.filter(submission_type=submission_type)

    total = PropertySubmission.objects.count()
    pending = PropertySubmission.objects.filter(status=PropertySubmission.STATUS_PENDING).count()
    listed = PropertySubmission.objects.filter(status=PropertySubmission.STATUS_LISTED).count()
    evaluations = PropertySubmission.objects.filter(submission_type=PropertySubmission.TYPE_EVALUATION).count()

    return render(request, 'accounts/property_submissions.html', {
        'submissions': qs,
        'total': total,
        'pending': pending,
        'listed': listed,
        'evaluations': evaluations,
        'filters': {'q': q, 'status': status, 'type': submission_type},
    })


@login_required
def property_submission_detail(request, pk):
    submission = get_object_or_404(
        PropertySubmission.objects.select_related('assigned_to', 'converted_property').prefetch_related('images'),
        pk=pk,
    )
    return render(request, 'accounts/property_submission_detail.html', {
        'submission': submission,
        'agents': User.objects.filter(is_active=True),
    })


@login_required
@require_POST
def property_submission_update(request, pk):
    submission = get_object_or_404(PropertySubmission, pk=pk)
    status = request.POST.get('status', '').strip()
    if status in dict(PropertySubmission.STATUS_CHOICES):
        submission.status = status
    submission.internal_notes = request.POST.get('internal_notes', '').strip()
    agent_id = request.POST.get('assigned_to', '').strip()
    submission.assigned_to = User.objects.filter(pk=agent_id).first() if agent_id else None
    submission.save()
    messages.success(request, 'Submission updated.')
    return redirect('property_submission_detail', pk=pk)


@login_required
def property_submission_convert(request, pk):
    submission = get_object_or_404(PropertySubmission.objects.prefetch_related('images'), pk=pk)
    if submission.converted_property_id:
        return redirect('property_view', pk=submission.converted_property_id)

    initial = {
        'title': f'{submission.get_property_type_display()} in {submission.location or submission.city}',
        'property_type': submission.property_type,
        'listing_type': submission.purpose or Property.LISTING_SALE,
        'price': submission.asking_price,
        'area_size': submission.area_size,
        'area_unit': submission.area_unit,
        'bedrooms': submission.bedrooms,
        'bathrooms': submission.bathrooms,
        'city': submission.city,
        'location': submission.location,
        'address': submission.location or submission.city,
        'description': submission.description,
    }
    form = PropertyForm(request.POST or None, initial=initial, user=request.user)

    if request.method == 'POST' and form.is_valid():
        prop = form.save(commit=False)
        prop.created_by = request.user
        prop.save()
        for img in submission.images.all():
            PropertyImage.objects.create(property=prop, image=img.image_url, is_primary=not prop.images.exists())
        _upload_images(request.FILES, prop)
        submission.converted_property = prop
        submission.status = PropertySubmission.STATUS_LISTED
        submission.save(update_fields=['converted_property', 'status', 'updated_at'])
        PropertyActivity.objects.create(
            property=prop,
            activity_type=PropertyActivity.TYPE_CREATED,
            description=f'Property created from submission {submission.reference_code()} by {request.user.get_full_name() or request.user.email}.',
            created_by=request.user,
        )
        messages.success(request, f'Property created and listed from submission {submission.reference_code()}.')
        return redirect('property_view', pk=prop.pk)

    return render(request, 'accounts/property_submission_convert.html', {
        'form': form,
        'submission': submission,
        'blocks': Block.objects.all(),
    })


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
        ok, err = _send_push(sub, 'PIE Real Estate', 'Test notification works! ✓', '/crm/dashboard/')
        if ok:
            sent += 1
        elif err:
            errors.append(err)
    if sent == 0:
        return JsonResponse({'error': errors[0] if errors else 'send failed'}, status=500)
    return JsonResponse({'status': 'sent', 'count': sent})


# ── Notifications ────────────────────────────────────────────────────────────

@login_required
def notifications_list(request):
    notifications = request.user.notifications.all()
    return render(request, 'accounts/notifications.html', {'notifications': notifications})


@login_required
def notification_open(request, pk):
    notif = get_object_or_404(Notification, pk=pk, recipient=request.user)
    if not notif.is_read:
        notif.is_read = True
        notif.save(update_fields=['is_read'])
    return redirect(notif.url or 'dashboard')


@login_required
@require_POST
def notifications_mark_all_read(request):
    request.user.notifications.filter(is_read=False).update(is_read=True)
    next_url = request.POST.get('next') or request.META.get('HTTP_REFERER') or reverse('dashboard')
    return redirect(next_url)


@login_required
def notifications_feed(request):
    """Polled by the notification bell widget on every authenticated page."""
    notifications = request.user.notifications.all()[:10]
    return JsonResponse({
        'unread_count': request.user.notifications.filter(is_read=False).count(),
        'notifications': [
            {
                'id': n.pk,
                'title': n.title,
                'body': n.body,
                'url': n.url or reverse('dashboard'),
                'is_read': n.is_read,
                'created_at': n.created_at.isoformat(),
            }
            for n in notifications
        ],
    })


# ── Customers ─────────────────────────────────────────────────────────────────

@login_required
def customer_list(request):
    if request.user.is_crm_admin:
        customers = Customer.objects.select_related('created_by').all()
    else:
        customers = Customer.objects.filter(created_by=request.user)
    return render(request, 'accounts/customers.html', {'customers': customers})


@login_required
def customer_detail(request, pk):
    if request.user.is_crm_admin:
        customer = get_object_or_404(
            Customer.objects.select_related('created_by').prefetch_related(
                'properties__images', 'interested_in__images'
            ),
            pk=pk,
        )
    else:
        customer = get_object_or_404(
            Customer.objects.select_related('created_by').prefetch_related(
                'properties__images', 'interested_in__images'
            ),
            pk=pk, created_by=request.user,
        )
    return render(request, 'accounts/customer_detail.html', {'customer': customer})


def _parse_children_json(request):
    """The dynamic children editor in customer_form.html serializes its rows into a
    hidden 'children_json' input — parse and sanitize it into a plain list of dicts."""
    try:
        raw = json.loads(request.POST.get('children_json') or '[]')
    except (ValueError, TypeError):
        return []
    if not isinstance(raw, list):
        return []
    children = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        name = str(item.get('name') or '').strip()[:100]
        if not name:
            continue
        children.append({
            'name': name,
            'age': str(item.get('age') or '').strip()[:10],
            'school': str(item.get('school') or '').strip()[:150],
            'class_grade': str(item.get('class_grade') or '').strip()[:50],
        })
    return children


def _parse_vehicles_json(request):
    """The dynamic vehicles editor in customer_form.html serializes its rows into a
    hidden 'vehicles_json' input — parse and sanitize it into a plain list of dicts."""
    try:
        raw = json.loads(request.POST.get('vehicles_json') or '[]')
    except (ValueError, TypeError):
        return []
    if not isinstance(raw, list):
        return []
    vehicles = []
    for item in raw:
        if not isinstance(item, dict):
            continue
        vtype = str(item.get('type') or '').strip()[:30]
        if not vtype:
            continue
        vehicles.append({
            'type': vtype,
            'make': str(item.get('make') or '').strip()[:50],
            'model': str(item.get('model') or '').strip()[:50],
            'year': str(item.get('year') or '').strip()[:10],
        })
    return vehicles


@login_required
def customer_create(request):
    form = CustomerForm(request.POST or None, user=request.user)
    if request.method == 'POST' and form.is_valid():
        customer = form.save(commit=False)
        customer.created_by = request.user
        customer.children = _parse_children_json(request)
        customer.vehicles = _parse_vehicles_json(request)
        customer.save()
        form.save_m2m()
        next_url = request.GET.get('next')
        if next_url:
            return redirect(next_url)
        return redirect('customer_detail', pk=customer.pk)
    return render(request, 'accounts/customer_form.html', {'form': form, 'action': 'Add Customer'})


@login_required
def customer_update(request, pk):
    if request.user.is_crm_admin:
        customer = get_object_or_404(Customer, pk=pk)
    else:
        customer = get_object_or_404(Customer, pk=pk, created_by=request.user)
    form = CustomerForm(request.POST or None, instance=customer, user=request.user)
    if request.method == 'POST' and form.is_valid():
        customer = form.save(commit=False)
        customer.children = _parse_children_json(request)
        customer.vehicles = _parse_vehicles_json(request)
        customer.save()
        form.save_m2m()
        return redirect('customer_detail', pk=customer.pk)
    return render(request, 'accounts/customer_form.html', {'form': form, 'customer': customer, 'action': 'Edit Customer'})


@login_required
def customer_delete(request, pk):
    if request.user.is_crm_admin:
        customer = get_object_or_404(Customer, pk=pk)
    else:
        customer = get_object_or_404(Customer, pk=pk, created_by=request.user)
    if request.method == 'POST':
        customer.delete()
        return redirect('customer_list')
    return render(request, 'accounts/customer_confirm_delete.html', {'customer': customer})


# ── Block management ──────────────────────────────────────────────────────────

@admin_required
def block_list(request):
    form = BlockForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        form.save()
        return redirect('block_list')
    blocks = Block.objects.prefetch_related('required_documents')
    return render(request, 'accounts/blocks.html', {'blocks': blocks, 'form': form})


@admin_required
def block_delete(request, pk):
    block = get_object_or_404(Block, pk=pk)
    if request.method == 'POST':
        block.delete()
    return redirect('block_list')


@admin_required
def block_create_ajax(request):
    if request.method != 'POST':
        return JsonResponse({'error': 'Method not allowed.'}, status=405)
    name = request.POST.get('name', '').strip()
    if not name:
        return JsonResponse({'error': 'Block name is required.'}, status=400)
    if Block.objects.filter(name__iexact=name).exists():
        return JsonResponse({'error': f'"{name}" already exists.'}, status=400)
    block = Block.objects.create(name=name)
    return JsonResponse({'id': block.pk, 'name': block.name})


@admin_required
@require_POST
def block_required_document_add(request, pk):
    block = get_object_or_404(Block, pk=pk)
    name = request.POST.get('name', '').strip()
    if name:
        BlockRequiredDocument.objects.get_or_create(block=block, name=name)
    return redirect('block_list')


@admin_required
@require_POST
def block_required_document_delete(request, pk):
    doc = get_object_or_404(BlockRequiredDocument, pk=pk)
    doc.delete()
    return redirect('block_list')


# ── Lead Management ────────────────────────────────────────────────────────────

def _auto_assign_agent():
    """Equal-distribution assignment: the active agent with the fewest currently-assigned leads."""
    return (
        User.objects.filter(role=User.ROLE_AGENT, is_active=True)
        .annotate(lead_count=Count('assigned_leads'))
        .order_by('lead_count', 'id')
        .first()
    )


def _lead_qs(request):
    if request.user.is_crm_admin:
        return Lead.objects.select_related('assigned_to', 'created_by').prefetch_related('collaborators')
    return Lead.objects.filter(
        Q(created_by=request.user) | Q(assigned_to=request.user) | Q(collaborators=request.user)
    ).distinct().select_related('assigned_to', 'created_by').prefetch_related('collaborators')


def _build_whatsapp_share_url(request, lead, recommendations, note=None):
    """WhatsApp deep link sharing the lead's top matching properties, or '' if there's nothing to share."""
    if not (lead.phone and recommendations):
        return ''
    lines = [f"Hi {lead.full_name}! \U0001f44b Here are top properties from PIE Real Estate matching your requirements:\n"]
    if note:
        lines.append(note)
    for i, prop in enumerate(recommendations, 1):
        prop_url = request.build_absolute_uri(f'/properties/{prop.pk}/')
        price = f"PKR {prop.price:,.0f}" if prop.price else 'Price on request'
        details = f"  \U0001f4cd {prop.location}, {prop.city}\n  \U0001f4b0 {price}"
        if prop.bedrooms:
            details += f"\n  \U0001f6cf {prop.bedrooms} Bed"
        if prop.bathrooms:
            details += f" · \U0001f6bf {prop.bathrooms} Bath"
        if hasattr(prop, 'match_pct'):
            details += f"\n  ✓ {prop.match_pct}% match"
        details += f"\n  \U0001f517 {prop_url}"
        lines.append(f"*{i}. {prop.title}*\n{details}")
    lines.append("\nReady to schedule a viewing? Contact us anytime. — PIE Real Estate")
    message = "\n\n".join(lines)
    digits = _normalize_phone_digits(lead.phone)
    return f"https://wa.me/{digits}?text={quote(message)}"


def _advance_status(lead, target_status, user, note=None):
    """Move a lead forward to target_status only if it isn't already there or past it —
    used by auto-transitions so they never downgrade a lead that's already further along."""
    target_index = Lead.STATUS_ORDER.index(target_status)
    if lead.status_step_index() != -1 and lead.status_step_index() >= target_index:
        return
    old = lead.get_status_display()
    lead.status = target_status
    lead.save(update_fields=['status', 'lead_score', 'updated_at'])
    LeadActivity.objects.create(
        lead=lead,
        activity_type=LeadActivity.TYPE_STATUS,
        description=note or f'Status changed from {old} to {lead.get_status_display()}.',
        created_by=user,
    )


@login_required
def lead_list(request):
    qs = _lead_qs(request)

    status_filter = request.GET.get('status', '')
    source_filter = request.GET.get('source', '')
    type_filter = request.GET.get('lead_type', '')
    agent_filter = request.GET.get('agent', '')
    score_filter = request.GET.get('lead_score', '')
    search = request.GET.get('q', '').strip()

    if status_filter:
        qs = qs.filter(status=status_filter)
    if source_filter:
        qs = qs.filter(source=source_filter)
    if type_filter:
        qs = qs.filter(lead_type=type_filter)
    if agent_filter and request.user.is_crm_admin:
        qs = qs.filter(assigned_to_id=agent_filter)
    if score_filter:
        qs = qs.filter(lead_score=score_filter)
    if search:
        qs = qs.filter(
            Q(full_name__icontains=search) |
            Q(email__icontains=search) |
            Q(phone__icontains=search)
        )

    base_qs = _lead_qs(request)
    kpis = {
        'total': base_qs.count(),
        'received': base_qs.filter(status=Lead.STATUS_RECEIVED).count(),
        'contacted': base_qs.filter(status=Lead.STATUS_CONTACTED).count(),
        'negotiation': base_qs.filter(status=Lead.STATUS_NEGOTIATION).count(),
        'deal_closed': base_qs.filter(status=Lead.STATUS_DEAL_CLOSED).count(),
    }

    agents = User.objects.filter(is_active=True) if request.user.is_crm_admin else None

    return render(request, 'accounts/leads.html', {
        'leads': qs,
        'kpis': kpis,
        'agents': agents,
        'status_choices': Lead.STATUS_CHOICES,
        'source_choices': Lead.SOURCE_CHOICES,
        'type_choices': Lead.TYPE_CHOICES,
        'score_choices': Lead.SCORE_CHOICES,
        'filters': {
            'status': status_filter,
            'source': source_filter,
            'lead_type': type_filter,
            'agent': agent_filter,
            'lead_score': score_filter,
            'q': search,
        },
    })


@login_required
def lead_create(request):
    form = LeadForm(request.POST or None, user=request.user)
    if request.method == 'POST' and form.is_valid():
        lead = form.save(commit=False)
        lead.created_by = request.user
        if not request.user.is_crm_admin:
            lead.assigned_to = request.user
        elif not lead.assigned_to_id:
            lead.assigned_to = _auto_assign_agent()
        if lead.assigned_to_id and lead.status == Lead.STATUS_RECEIVED:
            lead.status = Lead.STATUS_ASSIGNED
        raw = request.POST.getlist('interested_in')
        lead.interested_in = raw
        lead.save()
        LeadActivity.objects.create(
            lead=lead,
            activity_type=LeadActivity.TYPE_CREATED,
            description=f'Lead created by {request.user.get_full_name() or request.user.email}.',
            created_by=request.user,
        )
        if lead.assigned_to_id and lead.assigned_to_id != request.user.id:
            notify_user(
                lead.assigned_to,
                'New Lead Assigned',
                f'{lead.full_name} has been assigned to you.',
                f'/crm/leads/{lead.pk}/',
            )
        return redirect('lead_detail', pk=lead.pk)
    return render(request, 'accounts/lead_form.html', {
        'form': form, 'lead': None,
        'interest_choices': Lead.INTEREST_CHOICES,
    })


@login_required
def lead_detail(request, pk):
    lead = get_object_or_404(_lead_qs(request), pk=pk)
    recommendations = lead.get_recommended_properties(limit=5)
    activities = lead.activities.select_related('created_by').order_by('-created_at')
    documents = lead.documents.select_related('uploaded_by', 'requirement').order_by('-created_at')
    doc_form = LeadDocumentForm(lead=lead)
    document_progress = lead.document_progress()
    missing_documents = lead.missing_required_documents()
    negotiation_properties = Property.objects.filter(status=Property.STATUS_ACTIVE).select_related('block').order_by('title')

    collaborators = lead.collaborators.all()
    is_collaborator = any(c.pk == request.user.pk for c in collaborators)
    can_manage_collaborators = request.user.is_crm_admin or request.user == lead.created_by or request.user == lead.assigned_to
    existing_agent_ids = {c.pk for c in collaborators}
    if lead.assigned_to_id:
        existing_agent_ids.add(lead.assigned_to_id)
    if lead.created_by_id:
        existing_agent_ids.add(lead.created_by_id)
    eligible_agents = (
        User.objects.filter(is_active=True).exclude(pk__in=existing_agent_ids).order_by('first_name', 'last_name')
        if can_manage_collaborators else User.objects.none()
    )

    whatsapp_url = _build_whatsapp_share_url(request, lead, recommendations)
    payments = lead.payments.select_related('recorded_by').all()
    total_paid = lead.total_paid()

    status_labels = dict(Lead.STATUS_CHOICES)
    steps = [
        {'key': key, 'label': status_labels[key], 'icon': Lead.STATUS_ICONS.get(key, '')}
        for key in Lead.STATUS_ORDER
    ]
    status_index = {key: i for i, key in enumerate(Lead.STATUS_ORDER)}

    return render(request, 'accounts/lead_detail.html', {
        'lead': lead,
        'recommendations': recommendations,
        'activities': activities,
        'documents': documents,
        'doc_form': doc_form,
        'document_progress': document_progress,
        'missing_documents': missing_documents,
        'negotiation_properties': negotiation_properties,
        'status_choices': Lead.STATUS_CHOICES,
        'can_edit': request.user.is_crm_admin or request.user == lead.created_by or request.user == lead.assigned_to or is_collaborator,
        'whatsapp_url': whatsapp_url,
        'collaborators': collaborators,
        'can_manage_collaborators': can_manage_collaborators,
        'eligible_agents': eligible_agents,
        'payments': payments,
        'total_paid': total_paid,
        'status_order': Lead.STATUS_ORDER,
        'status_step_index': lead.status_step_index(),
        'steps': steps,
        'status_index': status_index,
    })


@login_required
def lead_update(request, pk):
    lead = get_object_or_404(_lead_qs(request), pk=pk)
    old_status = lead.status
    old_status_label = lead.get_status_display()
    old_property_id = lead.property_id
    old_assigned_to_id = lead.assigned_to_id
    form = LeadForm(request.POST or None, instance=lead, user=request.user)
    if request.method == 'POST' and form.is_valid():
        updated = form.save(commit=False)
        if updated.assigned_to_id and not old_assigned_to_id and updated.status == Lead.STATUS_RECEIVED:
            updated.status = Lead.STATUS_ASSIGNED
        raw = request.POST.getlist('interested_in')
        updated.interested_in = raw
        updated.save()
        if updated.status != old_status:
            LeadActivity.objects.create(
                lead=updated,
                activity_type=LeadActivity.TYPE_STATUS,
                description=f'Status changed from {old_status_label} to {updated.get_status_display()}.',
                created_by=request.user,
            )
        if updated.assigned_to_id and updated.assigned_to_id != old_assigned_to_id:
            notify_user(
                updated.assigned_to,
                'New Lead Assigned',
                f'{updated.full_name} has been assigned to you.',
                f'/crm/leads/{updated.pk}/',
            )
        if updated.property_id and updated.property_id != old_property_id:
            LeadActivity.objects.create(
                lead=updated,
                activity_type=LeadActivity.TYPE_PROPERTY,
                description=f'Property "{updated.property.title}" linked to this lead by {request.user.get_full_name() or request.user.email}.',
                created_by=request.user,
            )
        return redirect('lead_detail', pk=lead.pk)
    return render(request, 'accounts/lead_form.html', {
        'form': form, 'lead': lead,
        'interest_choices': Lead.INTEREST_CHOICES,
    })


@login_required
def lead_delete(request, pk):
    lead = get_object_or_404(_lead_qs(request), pk=pk)
    if request.method == 'POST':
        lead.delete()
        return redirect('lead_list')
    return render(request, 'accounts/lead_confirm_delete.html', {'lead': lead})


# ── Public lead intake API ────────────────────────────────────────────────────
# Called from outside the CRM (website forms, WhatsApp bot, property portals).
# Auth is a shared secret in the X-Api-Key header (settings.LEAD_API_KEY) — there
# is no per-caller identity, just a single key. Every field except full_name and
# phone is optional. On success the lead is auto-assigned round-robin to
# whichever active agent currently has the fewest leads, and that agent is
# notified in-CRM (and via web push, if subscribed).

def _decimal_or_none(value):
    if value in (None, ''):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _int_or_none(value):
    if value in (None, ''):
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _normalize_phone_digits(raw):
    """Digits only, with a Pakistani local '0...' prefix rewritten to the '92...' country code
    so local and international formats of the same number compare equal."""
    digits = re.sub(r'\D', '', raw or '')
    if digits.startswith('0') and len(digits) == 11:
        digits = '92' + digits[1:]
    return digits


@csrf_exempt
@require_POST
def lead_api_create(request):
    if request.headers.get('X-Api-Key') != settings.LEAD_API_KEY:
        return JsonResponse({'error': 'Invalid or missing API key.'}, status=401)

    if request.content_type == 'application/json':
        try:
            data = json.loads(request.body.decode('utf-8') or '{}')
        except (json.JSONDecodeError, UnicodeDecodeError):
            return JsonResponse({'error': 'Invalid JSON body.'}, status=400)
    else:
        data = request.POST

    full_name = str(data.get('full_name') or '').strip()
    phone = str(data.get('phone') or '').strip()
    if not full_name or not phone:
        return JsonResponse({'error': 'full_name and phone are required.'}, status=400)

    valid_sources = {s for s, _ in Lead.SOURCE_CHOICES}
    source = data.get('source') or 'website'
    if source not in valid_sources:
        return JsonResponse({'error': f'Invalid source. Choices: {sorted(valid_sources)}'}, status=400)

    valid_types = {t for t, _ in Lead.TYPE_CHOICES}
    lead_type = data.get('lead_type') or Lead.TYPE_BUYER
    if lead_type not in valid_types:
        return JsonResponse({'error': f'Invalid lead_type. Choices: {sorted(valid_types)}'}, status=400)

    raw_interests = data.get('interested_in') or []
    if isinstance(raw_interests, str):
        raw_interests = [raw_interests]
    valid_interests = {i for i, _ in Lead.INTEREST_CHOICES}
    interested_in = [i for i in raw_interests if i in valid_interests]

    agent_phone = str(data.get('agent_phone') or '').strip()
    preassigned_agent = None
    if agent_phone:
        digits = _normalize_phone_digits(agent_phone)
        if len(digits) < 6:
            return JsonResponse({'error': 'agent_phone is not a valid phone number.'}, status=400)
        preassigned_agent = next(
            (u for u in User.objects.filter(role=User.ROLE_AGENT, is_active=True).exclude(phone='')
             if _normalize_phone_digits(u.phone) == digits),
            None,
        )
        if not preassigned_agent:
            return JsonResponse({'error': f'No active agent found with phone {agent_phone}.'}, status=400)

    lead = Lead(
        full_name=full_name,
        phone=phone,
        alternate_phone=str(data.get('alternate_phone') or '').strip(),
        email=str(data.get('email') or '').strip(),
        lead_type=lead_type,
        source=source,
        interested_in=interested_in,
        area_preferences=str(data.get('area_preferences') or '').strip(),
        budget_min=_decimal_or_none(data.get('budget_min')),
        budget_max=_decimal_or_none(data.get('budget_max')),
        bedrooms_min=_int_or_none(data.get('bedrooms_min')),
        bedrooms_max=_int_or_none(data.get('bedrooms_max')),
        bathrooms_min=_int_or_none(data.get('bathrooms_min')),
        bathrooms_max=_int_or_none(data.get('bathrooms_max')),
        area_sqft_min=_int_or_none(data.get('area_sqft_min')),
        area_sqft_max=_int_or_none(data.get('area_sqft_max')),
        other_requirements=str(data.get('other_requirements') or '').strip(),
        notes=str(data.get('notes') or '').strip(),
    )
    lead.assigned_to = preassigned_agent or _auto_assign_agent()
    lead.save()

    agent = lead.assigned_to
    if preassigned_agent:
        assignment_note = f' Already assigned to {agent.get_full_name()} (per agent_phone).'
    elif agent:
        assignment_note = f' Auto-assigned to {agent.get_full_name()}.'
    else:
        assignment_note = ' No active agent available to assign.'
    LeadActivity.objects.create(
        lead=lead,
        activity_type=LeadActivity.TYPE_CREATED,
        description=f'Lead received via API (source: {lead.get_source_display()}).{assignment_note}',
    )
    if agent:
        notify_user(
            agent,
            'New Lead Assigned',
            f'{lead.full_name} ({lead.get_source_display()}) has been assigned to you.',
            f'/crm/leads/{lead.pk}/',
        )

    return JsonResponse({
        'id': lead.pk,
        'full_name': lead.full_name,
        'phone': lead.phone,
        'status': lead.status,
        'lead_score': lead.lead_score,
        'assigned_agent': {
            'name': agent.get_full_name(),
            'phone': agent.phone,
            'assignment': 'explicit' if preassigned_agent else 'auto',
        } if agent else None,
    }, status=201)


@login_required
def lead_check_phone(request):
    """Reveal only whether a lead already exists for this phone number and who owns it —
    used so an agent can avoid creating a duplicate lead for a customer another agent already has."""
    raw = request.GET.get('phone', '').strip()
    digits = re.sub(r'\D', '', raw)
    if len(digits) < 6:
        return JsonResponse({'exists': False})

    found = None
    for lead in Lead.objects.select_related('assigned_to', 'created_by').all():
        for candidate in (lead.phone, lead.alternate_phone):
            if candidate and re.sub(r'\D', '', candidate) == digits:
                found = lead
                break
        if found:
            break

    if not found:
        return JsonResponse({'exists': False})

    owner = found.assigned_to or found.created_by
    can_access = (
        request.user.is_crm_admin or
        found.created_by_id == request.user.id or
        found.assigned_to_id == request.user.id or
        found.collaborators.filter(pk=request.user.id).exists()
    )
    return JsonResponse({
        'exists': True,
        'assigned_to': owner.get_full_name() if owner else 'Unassigned',
        'status': found.get_status_display(),
        'lead_id': found.pk if can_access else None,
    })


@login_required
@require_POST
def lead_add_collaborator(request, pk):
    lead = get_object_or_404(_lead_qs(request), pk=pk)
    can_manage = request.user.is_crm_admin or request.user == lead.created_by or request.user == lead.assigned_to
    if can_manage:
        agent = User.objects.filter(pk=request.POST.get('agent_id'), is_active=True).first()
        if agent and agent != lead.assigned_to:
            lead.collaborators.add(agent)
            LeadActivity.objects.create(
                lead=lead,
                activity_type=LeadActivity.TYPE_COLLABORATOR,
                description=f'{agent.get_full_name()} added as a collaborator by {request.user.get_full_name() or request.user.email}.',
                created_by=request.user,
            )
    return redirect('lead_detail', pk=pk)


@login_required
@require_POST
def lead_remove_collaborator(request, pk, user_pk):
    lead = get_object_or_404(_lead_qs(request), pk=pk)
    can_manage = request.user.is_crm_admin or request.user == lead.created_by or request.user == lead.assigned_to
    if can_manage:
        agent = get_object_or_404(User, pk=user_pk)
        lead.collaborators.remove(agent)
        LeadActivity.objects.create(
            lead=lead,
            activity_type=LeadActivity.TYPE_COLLABORATOR,
            description=f'{agent.get_full_name()} removed as a collaborator by {request.user.get_full_name() or request.user.email}.',
            created_by=request.user,
        )
    return redirect('lead_detail', pk=pk)


@login_required
@require_POST
def lead_add_note(request, pk):
    lead = get_object_or_404(_lead_qs(request), pk=pk)
    note = request.POST.get('note', '').strip()
    if note:
        LeadActivity.objects.create(
            lead=lead,
            activity_type=LeadActivity.TYPE_NOTE,
            description=note,
            created_by=request.user,
        )
    return redirect('lead_detail', pk=pk)


def _is_pdf_or_image(f):
    return f.content_type == 'application/pdf' or f.content_type.startswith('image/')


@login_required
@require_POST
def lead_add_document(request, pk):
    lead = get_object_or_404(_lead_qs(request), pk=pk)
    form = LeadDocumentForm(request.POST, lead=lead)
    f = request.FILES.get('file')
    if form.is_valid():
        if not (f and _is_pdf_or_image(f)):
            messages.error(request, 'Upload a PDF or image file for this document.')
            return redirect('lead_detail', pk=pk)
        doc = form.save(commit=False)
        result = cloudinary.uploader.upload(f, folder='pie-crm/documents', resource_type='auto')
        doc.file_url = result['secure_url']
        doc.lead = lead
        doc.uploaded_by = request.user
        doc.save()
        LeadActivity.objects.create(
            lead=lead,
            activity_type=LeadActivity.TYPE_DOCUMENT,
            description=f'{doc.get_document_type_display()} "{doc.title}" added.',
            created_by=request.user,
        )
        if doc.document_type == LeadDocument.TYPE_TOKEN_RECEIPT and doc.amount:
            lead.booking_amount = doc.amount
            lead.save(update_fields=['booking_amount', 'lead_score'])
    return redirect('lead_detail', pk=pk)


@login_required
@require_POST
def lead_status_update(request, pk):
    lead = get_object_or_404(_lead_qs(request), pk=pk)
    new_status = request.POST.get('status', '')
    valid = [s for s, _ in Lead.STATUS_CHOICES]
    is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'

    def fail(error):
        if is_ajax:
            return JsonResponse({'ok': False, 'error': error}, status=400)
        messages.error(request, error)
        return redirect('lead_detail', pk=pk)

    if new_status not in valid or new_status == lead.status:
        return redirect('lead_detail', pk=pk)

    update_fields = {'status', 'lead_score', 'updated_at'}

    # Visit Scheduled needs to know which property the visit is for.
    if new_status == Lead.STATUS_VISIT_SCHEDULED and not lead.property_id:
        prop = Property.objects.filter(pk=request.POST.get('property_id')).first()
        if not prop:
            return fail('Select the property being visited before scheduling a site visit.')
        lead.property = prop
        update_fields.add('property')
        LeadActivity.objects.create(
            lead=lead,
            activity_type=LeadActivity.TYPE_PROPERTY,
            description=f'Property "{prop.title}" linked to this lead by {request.user.get_full_name() or request.user.email}.',
            created_by=request.user,
        )

    # Deal Lost needs a reason.
    if new_status == Lead.STATUS_DEAL_LOST:
        reason = request.POST.get('lost_reason', '').strip()
        if not reason:
            return fail('Add a reason before marking this lead as Deal Lost.')
        lead.lost_reason = reason
        update_fields.add('lost_reason')

    # Anything past Documentation requires the block's mandatory documents to be complete.
    documentation_index = Lead.STATUS_ORDER.index(Lead.STATUS_DOCUMENTATION)
    target_index = Lead.STATUS_ORDER.index(new_status) if new_status in Lead.STATUS_ORDER else None
    if target_index is not None and target_index > documentation_index and not lead.documents_complete():
        missing = lead.missing_required_documents()
        names = ', '.join(d.name for d in missing)
        return fail(f"Add the required documents for this lead's property block first: {names}.")

    # Possession Complete (and beyond) requires the deal amount and commission to be fully paid.
    possession_index = Lead.STATUS_ORDER.index(Lead.STATUS_POSSESSION_COMPLETE)
    if target_index is not None and target_index >= possession_index and not lead.payments_complete():
        if not lead.deal_financials_set():
            return fail('Set the total deal amount and commission, and complete all payments, before marking possession complete.')
        return fail(
            f'Complete all payments before marking possession complete — remaining: '
            f'PKR {lead.deal_remaining():,.0f} (deal), PKR {lead.commission_remaining():,.0f} (commission).'
        )

    old = lead.get_status_display()
    is_contact_transition = new_status == Lead.STATUS_CONTACTED
    lead.status = new_status
    lead.save(update_fields=list(update_fields))
    LeadActivity.objects.create(
        lead=lead,
        activity_type=LeadActivity.TYPE_CONTACTED if is_contact_transition else LeadActivity.TYPE_STATUS,
        description=f'Status changed from {old} to {lead.get_status_display()}.',
        created_by=request.user,
    )
    if is_ajax:
        return JsonResponse({'ok': True, 'status': lead.status, 'label': lead.get_status_display(), 'color': lead.status_color()})
    return redirect('lead_detail', pk=pk)


@login_required
@require_POST
def lead_share_properties(request, pk):
    """The WhatsApp 'Send Top N' button — opens the share modal first so the agent can
    pick which properties to include and add a personal note, then opens WhatsApp with
    the resulting message, logs the share, and advances status to Property Shared."""
    lead = get_object_or_404(_lead_qs(request), pk=pk)
    recommendations = lead.get_recommended_properties(limit=5)

    selected_ids = {int(x) for x in request.POST.getlist('property_ids') if x.isdigit()}
    selected = [p for p in recommendations if p.pk in selected_ids]

    if not selected:
        messages.error(request, 'Select at least one property to share.')
        return redirect('lead_detail', pk=pk)

    note = request.POST.get('note', '').strip()
    whatsapp_url = _build_whatsapp_share_url(request, lead, selected, note=note)
    if not whatsapp_url:
        messages.error(request, 'No matching properties to share yet — add requirements to this lead first.')
        return redirect('lead_detail', pk=pk)
    count = len(selected)
    LeadActivity.objects.create(
        lead=lead,
        activity_type=LeadActivity.TYPE_PROPERTY,
        description=f'Shared {count} matching propert{"y" if count == 1 else "ies"} with the lead via WhatsApp.',
        created_by=request.user,
    )
    _advance_status(lead, Lead.STATUS_PROPERTY_SHARED, request.user)
    return redirect(whatsapp_url)


@login_required
@require_POST
def lead_auto_follow_up(request, pk):
    lead = get_object_or_404(_lead_qs(request), pk=pk)
    note = request.POST.get('note', '').strip()
    lead.follow_up_date = timezone.now()
    lead.save(update_fields=['follow_up_date', 'lead_score', 'updated_at'])
    LeadActivity.objects.create(
        lead=lead,
        activity_type=LeadActivity.TYPE_FOLLOW_UP,
        description=f'Follow-up logged by {request.user.get_full_name() or request.user.email}.' + (f' — {note}' if note else ''),
        created_by=request.user,
    )
    _advance_status(lead, Lead.STATUS_FOLLOW_UP, request.user)
    return redirect('lead_detail', pk=pk)


@login_required
@require_POST
def lead_schedule_visit(request, pk):
    lead = get_object_or_404(_lead_qs(request), pk=pk)
    raw_datetime = request.POST.get('visit_datetime', '')
    visit_dt = parse_datetime(raw_datetime)
    if not visit_dt:
        messages.error(request, 'Pick a valid date and time for the site visit.')
        return redirect('lead_detail', pk=pk)
    if timezone.is_naive(visit_dt):
        visit_dt = timezone.make_aware(visit_dt)

    prop = lead.property
    if not prop:
        prop = Property.objects.filter(pk=request.POST.get('property_id')).first()
        if not prop:
            messages.error(request, 'Select the property being visited before scheduling a site visit.')
            return redirect('lead_detail', pk=pk)
        lead.property = prop

    lead.visit_scheduled_at = visit_dt
    lead.save(update_fields=['property', 'visit_scheduled_at', 'lead_score', 'updated_at'])
    when = timezone.localtime(visit_dt).strftime('%b %d, %Y at %I:%M %p')
    LeadActivity.objects.create(
        lead=lead,
        activity_type=LeadActivity.TYPE_VISIT,
        description=f'Site visit scheduled for {when} at {prop.title}.',
        created_by=request.user,
    )
    _advance_status(lead, Lead.STATUS_VISIT_SCHEDULED, request.user)

    notify_recipients = [lead.assigned_to] if lead.assigned_to_id else []
    notify_recipients += list(lead.collaborators.all())
    for agent in notify_recipients:
        notify_user(
            agent,
            'Site Visit Scheduled',
            f'{lead.full_name} — visit for {prop.title} on {when}.',
            f'/crm/leads/{lead.pk}/',
        )
    return redirect('lead_detail', pk=pk)


@login_required
@require_POST
def lead_set_deal_financials(request, pk):
    """Sets the total deal amount and commission for a lead — one-time and permanent.
    Must be done before any payment can be recorded, per the client's requirement that
    these figures be locked in before partial payments start."""
    lead = get_object_or_404(_lead_qs(request), pk=pk)
    if lead.deal_financials_set():
        messages.error(request, 'Deal amount and commission are already locked for this lead.')
        return redirect('lead_detail', pk=pk)

    deal_amount = _decimal_or_none(request.POST.get('deal_amount'))
    commission_amount = _decimal_or_none(request.POST.get('commission_amount'))
    if not deal_amount or deal_amount <= 0:
        messages.error(request, 'Enter a valid total deal amount.')
        return redirect('lead_detail', pk=pk)
    if commission_amount is None or commission_amount < 0:
        messages.error(request, 'Enter a valid commission amount.')
        return redirect('lead_detail', pk=pk)

    lead.deal_amount = deal_amount
    lead.commission_amount = commission_amount
    lead.save(update_fields=['deal_amount', 'commission_amount', 'lead_score', 'updated_at'])
    LeadActivity.objects.create(
        lead=lead,
        activity_type=LeadActivity.TYPE_STATUS,
        description=(
            f'Deal amount set to PKR {deal_amount:,.0f} and commission to PKR {commission_amount:,.0f} '
            f'by {request.user.get_full_name() or request.user.email}.'
        ),
        created_by=request.user,
    )
    return redirect('lead_detail', pk=pk)


@login_required
@require_POST
def lead_add_payment(request, pk):
    lead = get_object_or_404(_lead_qs(request), pk=pk)
    if not lead.deal_financials_set():
        messages.error(request, 'Set the total deal amount and commission before recording payments.')
        return redirect('lead_detail', pk=pk)

    amount = _decimal_or_none(request.POST.get('amount'))
    paid_on = parse_date(request.POST.get('paid_on', '')) or timezone.localdate()
    note = request.POST.get('note', '').strip()
    method = request.POST.get('payment_method', LeadPayment.METHOD_CASH)
    against = request.POST.get('payment_against', LeadPayment.AGAINST_DEAL)
    reference_number = request.POST.get('reference_number', '').strip()

    if not amount or amount <= 0:
        messages.error(request, 'Enter a valid payment amount.')
        return redirect('lead_detail', pk=pk)
    if method not in dict(LeadPayment.METHOD_CHOICES):
        method = LeadPayment.METHOD_CASH
    if against not in dict(LeadPayment.AGAINST_CHOICES):
        against = LeadPayment.AGAINST_DEAL
    if method in LeadPayment.METHODS_REQUIRING_REFERENCE and not reference_number:
        messages.error(request, 'Enter a transaction ID or cheque/pay order number for this payment method.')
        return redirect('lead_detail', pk=pk)

    payment = LeadPayment.objects.create(
        lead=lead, amount=amount, paid_on=paid_on, note=note,
        payment_method=method, payment_against=against, reference_number=reference_number,
        recorded_by=request.user,
    )
    LeadActivity.objects.create(
        lead=lead,
        activity_type=LeadActivity.TYPE_PAYMENT,
        description=(
            f'Payment of PKR {amount:,.0f} ({payment.get_payment_against_display()}, '
            f'{payment.get_payment_method_display()}) recorded on {paid_on:%b %d, %Y}.'
        ) + (f' — {note}' if note else ''),
        created_by=request.user,
    )
    if lead.status == Lead.STATUS_DOCUMENTATION:
        _advance_status(lead, Lead.STATUS_PAYMENT_TRACKING, request.user)
    return redirect('lead_detail', pk=pk)


@login_required
@require_POST
def lead_mark_possession_complete(request, pk):
    lead = get_object_or_404(_lead_qs(request), pk=pk)
    if not lead.documents_complete():
        missing = lead.missing_required_documents()
        messages.error(request, f"Add the required documents first: {', '.join(d.name for d in missing)}.")
        return redirect('lead_detail', pk=pk)
    if not lead.payments_complete():
        if not lead.deal_financials_set():
            messages.error(request, 'Set the total deal amount and commission, and complete all payments, before marking possession complete.')
        else:
            messages.error(
                request,
                f'Complete all payments first — remaining: PKR {lead.deal_remaining():,.0f} (deal), '
                f'PKR {lead.commission_remaining():,.0f} (commission).',
            )
        return redirect('lead_detail', pk=pk)
    old = lead.get_status_display()
    lead.status = Lead.STATUS_POSSESSION_COMPLETE
    lead.save(update_fields=['status', 'lead_score', 'updated_at'])
    LeadActivity.objects.create(
        lead=lead,
        activity_type=LeadActivity.TYPE_STATUS,
        description=f'Status changed from {old} to {lead.get_status_display()}. Transfer & possession validated.',
        created_by=request.user,
    )
    return redirect('lead_detail', pk=pk)


@login_required
def lead_print_slip(request, pk, doc_pk):
    lead = get_object_or_404(_lead_qs(request), pk=pk)
    doc = get_object_or_404(LeadDocument, pk=doc_pk, lead=lead)
    return render(request, 'accounts/lead_payment_slip.html', {'lead': lead, 'doc': doc})


@login_required
def lead_print_invoice(request, pk):
    lead = get_object_or_404(_lead_qs(request), pk=pk)
    docs_with_amount = lead.documents.filter(amount__isnull=False).order_by('created_at')
    total = sum(float(d.amount) for d in docs_with_amount if d.amount)
    return render(request, 'accounts/lead_invoice.html', {
        'lead': lead,
        'docs_with_amount': docs_with_amount,
        'total': total,
    })


@login_required
def lead_print_payment_slip(request, pk, payment_pk):
    lead = get_object_or_404(_lead_qs(request), pk=pk)
    payment = get_object_or_404(LeadPayment, pk=payment_pk, lead=lead)
    return render(request, 'accounts/lead_payment_receipt.html', {'lead': lead, 'payment': payment})


@login_required
def lead_print_commission_invoice(request, pk):
    lead = get_object_or_404(_lead_qs(request), pk=pk)
    commission_payments = lead.payments.filter(
        payment_against=LeadPayment.AGAINST_COMMISSION
    ).order_by('paid_on', 'created_at')
    return render(request, 'accounts/lead_commission_invoice.html', {
        'lead': lead,
        'commission_payments': commission_payments,
    })
