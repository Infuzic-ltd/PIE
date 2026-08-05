from django.db import migrations

# Old status key -> new status key. Anything not listed here (there shouldn't be
# anything) falls back to 'received' so no row is left with an orphaned value.
STATUS_MAP = {
    'new': 'received',
    'contacted': 'contacted',
    'qualified': 'contacted',
    'follow_up': 'follow_up',
    'proposal': 'property_shared',
    'negotiation': 'negotiation',
    'token': 'booking_confirmed',
    'converted': 'deal_closed',
    'lost': 'deal_lost',
}

NEW_KEYS = set(STATUS_MAP.values())


def migrate_forward(apps, schema_editor):
    Lead = apps.get_model('accounts', 'Lead')
    for old_key, new_key in STATUS_MAP.items():
        if old_key != new_key:
            Lead.objects.filter(status=old_key).update(status=new_key)
    # Safety net: any value that isn't one of the new keys (shouldn't happen) becomes 'received'.
    Lead.objects.exclude(status__in=NEW_KEYS).update(status='received')


def migrate_backward(apps, schema_editor):
    Lead = apps.get_model('accounts', 'Lead')
    reverse_map = {
        'received': 'new',
        'contacted': 'contacted',
        'property_shared': 'proposal',
        'follow_up': 'follow_up',
        'negotiation': 'negotiation',
        'booking_confirmed': 'token',
        'deal_closed': 'converted',
        'deal_lost': 'lost',
    }
    for new_key, old_key in reverse_map.items():
        if old_key != new_key:
            Lead.objects.filter(status=new_key).update(status=old_key)


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0016_rename_token_amount_lead_booking_amount_and_more'),
    ]

    operations = [
        migrations.RunPython(migrate_forward, migrate_backward),
    ]
