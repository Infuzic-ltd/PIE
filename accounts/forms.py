from django import forms
from django.contrib.auth import authenticate
from .models import User, Property, AMENITY_LIST, Role, PERMISSION_LIST


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

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Pre-populate amenities from existing instance
        if self.instance.pk and self.instance.amenities:
            self.initial['amenities'] = self.instance.amenities
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
