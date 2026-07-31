from django import forms
from django.contrib.auth import authenticate
from .models import (
    User, Property, Customer, Block, BlockRequiredDocument, AMENITY_LIST, Role, PERMISSION_LIST,
    Lead, LeadDocument,
)


class SignupForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput, min_length=8)
    agree = forms.BooleanField(error_messages={'required': 'You must accept the Terms of Service.'})

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'phone', 'role', 'password']

    def save(self, commit=True):
        user = super().save(commit=False)
        user.username = self.cleaned_data['email']
        user.set_password(self.cleaned_data['password'])
        if commit:
            user.save()
        return user


class LoginForm(forms.Form):
    email = forms.EmailField()
    password = forms.CharField(widget=forms.PasswordInput)

    def __init__(self, *args, **kwargs):
        self._user = None
        super().__init__(*args, **kwargs)

    def clean(self):
        cleaned = super().clean()
        email = cleaned.get('email')
        password = cleaned.get('password')
        if email and password:
            self._user = authenticate(username=email, password=password)
            if self._user is None:
                raise forms.ValidationError('Invalid email or password.')
            if not self._user.is_active:
                raise forms.ValidationError('This account is inactive.')
        return cleaned

    def get_user(self):
        return self._user


AMENITY_CHOICES = [(a, a) for a in AMENITY_LIST]


class PropertyForm(forms.ModelForm):
    amenities = forms.MultipleChoiceField(
        choices=AMENITY_CHOICES,
        widget=forms.CheckboxSelectMultiple,
        required=False,
    )

    class Meta:
        model = Property
        exclude = ['created_by', 'created_at', 'updated_at']

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk and self.instance.amenities:
            self.initial['amenities'] = self.instance.amenities
        if user is not None:
            if user.is_crm_admin:
                self.fields['customer'].queryset = Customer.objects.all()
            else:
                self.fields['customer'].queryset = Customer.objects.filter(created_by=user)
        self.fields['customer'].required = False
        self.fields['customer'].empty_label = '— No customer linked —'
        self.fields['block'].required = False
        self.fields['block'].empty_label = '— No block —'
        for field in self.fields.values():
            field.error_messages = {'required': 'This field is required.'}

    def clean_amenities(self):
        return self.cleaned_data.get('amenities', [])


class TeamMemberCreateForm(forms.ModelForm):
    password = forms.CharField(widget=forms.PasswordInput, min_length=8, label='Password')
    assigned_role = forms.ModelChoiceField(
        queryset=Role.objects.all(), required=False,
        empty_label='— Use default role permissions —',
        label='Custom Role (optional)',
    )

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'phone', 'role', 'assigned_role', 'password']

    def save(self, commit=True):
        user = super().save(commit=False)
        user.username = self.cleaned_data['email']
        user.set_password(self.cleaned_data['password'])
        if commit:
            user.save()
        return user


class TeamMemberUpdateForm(forms.ModelForm):
    new_password = forms.CharField(
        widget=forms.PasswordInput, min_length=8, required=False,
        label='New Password', help_text='Leave blank to keep current password.',
    )
    assigned_role = forms.ModelChoiceField(
        queryset=Role.objects.all(), required=False,
        empty_label='— Use default role permissions —',
        label='Custom Role (optional)',
    )

    class Meta:
        model = User
        fields = ['first_name', 'last_name', 'email', 'phone', 'role', 'assigned_role', 'is_active']

    def save(self, commit=True):
        user = super().save(commit=False)
        new_pass = self.cleaned_data.get('new_password')
        if new_pass:
            user.set_password(new_pass)
        if commit:
            user.save()
        return user


class RoleForm(forms.ModelForm):
    permissions = forms.MultipleChoiceField(
        choices=PERMISSION_LIST,
        widget=forms.CheckboxSelectMultiple,
        required=False,
        label='Permissions',
    )

    class Meta:
        model = Role
        fields = ['name', 'description', 'permissions']

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk and self.instance.permissions:
            self.initial['permissions'] = self.instance.permissions

    def clean_permissions(self):
        return self.cleaned_data.get('permissions', [])


class BlockForm(forms.ModelForm):
    required_documents = forms.CharField(
        required=False,
        widget=forms.Textarea(attrs={'rows': 3}),
        label='Mandatory Documents',
        help_text='One document name per line, e.g. NOC, Allotment Letter, Possession Letter.',
    )

    class Meta:
        model = Block
        fields = ['name']

    def clean_required_documents(self):
        raw = self.cleaned_data.get('required_documents', '')
        names = [line.strip() for line in raw.splitlines() if line.strip()]
        seen, deduped = set(), []
        for name in names:
            key = name.lower()
            if key not in seen:
                seen.add(key)
                deduped.append(name)
        return deduped

    def save(self, commit=True):
        block = super().save(commit=commit)
        if commit:
            for name in self.cleaned_data.get('required_documents', []):
                BlockRequiredDocument.objects.get_or_create(block=block, name=name)
        return block


class CustomerForm(forms.ModelForm):
    interested_in = forms.ModelMultipleChoiceField(
        queryset=Property.objects.none(),
        required=False,
        label='Interested Properties',
        widget=forms.CheckboxSelectMultiple,
    )

    class Meta:
        model = Customer
        fields = ['name', 'phone', 'email', 'cnic', 'address', 'customer_type', 'budget', 'notes', 'interested_in']

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        if user is not None:
            if user.is_crm_admin:
                self.fields['interested_in'].queryset = Property.objects.all()
            else:
                self.fields['interested_in'].queryset = Property.objects.filter(created_by=user)
        if self.instance.pk:
            self.initial['interested_in'] = self.instance.interested_in.values_list('pk', flat=True)
        for name, field in self.fields.items():
            field.error_messages = {'required': 'This field is required.'}


class LeadForm(forms.ModelForm):
    class Meta:
        model = Lead
        fields = [
            'full_name', 'email', 'phone', 'alternate_phone',
            'lead_type', 'source', 'status', 'assigned_to',
            'interested_in', 'area_preferences',
            'budget_min', 'budget_max',
            'bedrooms_min', 'bedrooms_max',
            'bathrooms_min', 'bathrooms_max',
            'area_sqft_min', 'area_sqft_max',
            'other_requirements', 'notes', 'follow_up_date', 'property',
        ]

    def __init__(self, *args, user=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['assigned_to'].queryset = User.objects.filter(is_active=True)
        self.fields['assigned_to'].empty_label = '— Unassigned —'
        self.fields['assigned_to'].required = False
        self.fields['follow_up_date'].required = False
        self.fields['property'].queryset = Property.objects.all().select_related('block')
        self.fields['property'].empty_label = '— No property linked yet —'
        self.fields['property'].required = False
        self.fields['property'].label = 'Negotiating Property'
        if user and not user.is_crm_admin:
            del self.fields['assigned_to']

    def clean(self):
        cleaned = super().clean()
        status = cleaned.get('status')
        prop = cleaned.get('property')
        if status == Lead.STATUS_NEGOTIATION and not prop:
            self.add_error(
                'property',
                'Select the property being negotiated before moving this lead to Negotiation.',
            )
        if status == Lead.STATUS_CONVERTED:
            missing = self.instance.missing_required_documents(prop=prop)
            if missing:
                names = ', '.join(d.name for d in missing)
                self.add_error(
                    'status',
                    f"Add the required documents for this lead's property block before marking it Converted: {names}.",
                )
        return cleaned


class LeadDocumentForm(forms.ModelForm):
    class Meta:
        model = LeadDocument
        fields = ['document_type', 'title', 'amount', 'notes', 'requirement']

    def __init__(self, *args, lead=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['requirement'].required = False
        self.fields['requirement'].empty_label = '— Not a mandatory requirement —'
        self.fields['requirement'].queryset = (
            lead.required_documents_qs() if lead is not None else BlockRequiredDocument.objects.none()
        )
        self.fields['requirement'].label = 'Satisfies Requirement'
