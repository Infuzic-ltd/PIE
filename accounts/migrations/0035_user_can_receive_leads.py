from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0034_whatsapp_message_lead_and_notify'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='can_receive_leads',
            field=models.BooleanField(default=True, help_text='When off, leads cannot be assigned to this user (manually, by auto-assign, or via the API).', verbose_name='Assign Leads'),
        ),
    ]
