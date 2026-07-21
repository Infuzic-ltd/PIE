import json
import re
from urllib.parse import quote
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
from .forms import SignupForm, LoginForm, PropertyForm, CustomerForm, BlockForm, TeamMemberCreateForm, TeamMemberUpdateForm, RoleForm, LeadForm, LeadDocumentForm
from .models import Property, PropertyImage, PushSubscription, Role, User, Customer, Block, Lead, LeadActivity, LeadDocument


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
    form = PropertyForm(request.POST or None, user=request.user)
    if request.method == 'POST' and form.is_valid():
        prop = form.save(commit=False)
        prop.created_by = request.user
        prop.save()
        _upload_images(request.FILES, prop)
        return redirect('property_view', pk=prop.pk)
    return render(request, 'accounts/property_create.html', {
        'form': form,
        'blocks': Block.objects.all(),
    })


@login_required
def property_view(request, pk):
    prop = get_object_or_404(
        Property.objects.prefetch_related('images').select_related('customer', 'created_by', 'block'),
        pk=pk,
    )
    can_see_customer = request.user.is_crm_admin or request.user == prop.created_by
    return render(request, 'accounts/property_view.html', {
        'property': prop,
        'can_see_customer': can_see_customer,
    })


@login_required
def property_update(request, pk):
    prop = get_object_or_404(Property, pk=pk)
    form = PropertyForm(request.POST or None, instance=prop, user=request.user)
    if request.method == 'POST' and form.is_valid():
        form.save()
        _upload_images(request.FILES, prop)
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


@login_required
def customer_create(request):
    form = CustomerForm(request.POST or None, user=request.user)
    if request.method == 'POST' and form.is_valid():
        customer = form.save(commit=False)
        customer.created_by = request.user
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
        form.save()
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
    blocks = Block.objects.all()
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


# ── Lead Management ────────────────────────────────────────────────────────────

def _lead_qs(request):
    if request.user.is_crm_admin:
        return Lead.objects.select_related('assigned_to', 'created_by')
    return Lead.objects.filter(
        Q(created_by=request.user) | Q(assigned_to=request.user)
    ).select_related('assigned_to', 'created_by')


@login_required
def lead_list(request):
    qs = _lead_qs(request)

    status_filter = request.GET.get('status', '')
    source_filter = request.GET.get('source', '')
    type_filter = request.GET.get('lead_type', '')
    agent_filter = request.GET.get('agent', '')
    search = request.GET.get('q', '').strip()

    if status_filter:
        qs = qs.filter(status=status_filter)
    if source_filter:
        qs = qs.filter(source=source_filter)
    if type_filter:
        qs = qs.filter(lead_type=type_filter)
    if agent_filter and request.user.is_crm_admin:
        qs = qs.filter(assigned_to_id=agent_filter)
    if search:
        qs = qs.filter(
            Q(full_name__icontains=search) |
            Q(email__icontains=search) |
            Q(phone__icontains=search)
        )

    base_qs = _lead_qs(request)
    kpis = {
        'total': base_qs.count(),
        'new': base_qs.filter(status='new').count(),
        'contacted': base_qs.filter(status='contacted').count(),
        'qualified': base_qs.filter(status='qualified').count(),
        'converted': base_qs.filter(status='converted').count(),
    }

    agents = User.objects.filter(is_active=True) if request.user.is_crm_admin else None

    return render(request, 'accounts/leads.html', {
        'leads': qs,
        'kpis': kpis,
        'agents': agents,
        'status_choices': Lead.STATUS_CHOICES,
        'source_choices': Lead.SOURCE_CHOICES,
        'type_choices': Lead.TYPE_CHOICES,
        'filters': {
            'status': status_filter,
            'source': source_filter,
            'lead_type': type_filter,
            'agent': agent_filter,
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
        raw = request.POST.getlist('interested_in')
        lead.interested_in = raw
        lead.save()
        LeadActivity.objects.create(
            lead=lead,
            activity_type=LeadActivity.TYPE_CREATED,
            description=f'Lead created by {request.user.get_full_name() or request.user.email}.',
            created_by=request.user,
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
    documents = lead.documents.select_related('uploaded_by').order_by('-created_at')
    doc_form = LeadDocumentForm()

    # Build WhatsApp share URL for top-5 recommended properties
    whatsapp_url = ''
    if lead.phone and recommendations:
        lines = [f"Hi {lead.full_name}! \U0001f44b Here are top properties from PIE Real Estate matching your requirements:\n"]
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
        # Normalize phone for wa.me (strip non-digits, add 92 prefix if starts with 0)
        digits = re.sub(r'\D', '', lead.phone)
        if digits.startswith('0') and len(digits) == 11:
            digits = '92' + digits[1:]
        whatsapp_url = f"https://wa.me/{digits}?text={quote(message)}"

    return render(request, 'accounts/lead_detail.html', {
        'lead': lead,
        'recommendations': recommendations,
        'activities': activities,
        'documents': documents,
        'doc_form': doc_form,
        'status_choices': Lead.STATUS_CHOICES,
        'can_edit': request.user.is_crm_admin or request.user == lead.created_by or request.user == lead.assigned_to,
        'whatsapp_url': whatsapp_url,
    })


@login_required
def lead_update(request, pk):
    lead = get_object_or_404(_lead_qs(request), pk=pk)
    old_status = lead.status
    form = LeadForm(request.POST or None, instance=lead, user=request.user)
    if request.method == 'POST' and form.is_valid():
        updated = form.save(commit=False)
        raw = request.POST.getlist('interested_in')
        updated.interested_in = raw
        updated.save()
        if updated.status != old_status:
            LeadActivity.objects.create(
                lead=updated,
                activity_type=LeadActivity.TYPE_STATUS,
                description=f'Status changed from {old_status.replace("_", " ").title()} to {updated.get_status_display()}.',
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


@login_required
@require_POST
def lead_add_document(request, pk):
    lead = get_object_or_404(_lead_qs(request), pk=pk)
    form = LeadDocumentForm(request.POST)
    if form.is_valid():
        doc = form.save(commit=False)
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
            lead.token_amount = doc.amount
            lead.save(update_fields=['token_amount'])
    return redirect('lead_detail', pk=pk)


@login_required
@require_POST
def lead_status_update(request, pk):
    lead = get_object_or_404(_lead_qs(request), pk=pk)
    new_status = request.POST.get('status', '')
    valid = [s for s, _ in Lead.STATUS_CHOICES]
    if new_status in valid and new_status != lead.status:
        old = lead.get_status_display()
        lead.status = new_status
        lead.save(update_fields=['status', 'updated_at'])
        LeadActivity.objects.create(
            lead=lead,
            activity_type=LeadActivity.TYPE_STATUS,
            description=f'Status changed from {old} to {lead.get_status_display()}.',
            created_by=request.user,
        )
        if request.headers.get('X-Requested-With') == 'XMLHttpRequest':
            return JsonResponse({'ok': True, 'status': lead.status, 'label': lead.get_status_display(), 'color': lead.status_color()})
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
