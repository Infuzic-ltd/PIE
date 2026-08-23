from django.db import migrations

# Snapshot of PERMISSION_DEFAULTS at the time this migration was written — data
# migrations must not import current app code, since it can change after this
# migration is already applied to a database.
SYSTEM_ROLE_SEED = {
    'agent': ('Agent', [
        'dashboard', 'properties_view', 'properties_add', 'leads_view',
        'customers_view', 'customers_manage', 'submissions_view',
        'submissions_manage', 'affiliates_view', 'affiliates_manage',
    ]),
    'manager': ('Sales Manager', [
        'dashboard', 'properties_view', 'properties_add', 'properties_edit',
        'properties_delete', 'leads_view', 'leads_manage', 'customers_view',
        'customers_manage', 'submissions_view', 'submissions_manage',
        'affiliates_view', 'affiliates_manage', 'reports_view', 'team_view',
    ]),
}


def seed_system_roles(apps, schema_editor):
    Role = apps.get_model('accounts', 'Role')
    for system_role, (name, permissions) in SYSTEM_ROLE_SEED.items():
        if Role.objects.filter(system_role=system_role).exists():
            continue
        # A pre-existing custom role might already hold this name — Role.name is unique.
        final_name = name
        if Role.objects.filter(name=final_name).exists():
            final_name = f'{name} (System)'
        Role.objects.create(
            name=final_name, permissions=permissions, is_system=True, system_role=system_role,
        )


def unseed_system_roles(apps, schema_editor):
    Role = apps.get_model('accounts', 'Role')
    Role.objects.filter(system_role__in=list(SYSTEM_ROLE_SEED.keys())).delete()


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0028_role_system_role'),
    ]

    operations = [
        migrations.RunPython(seed_system_roles, reverse_code=unseed_system_roles),
    ]
