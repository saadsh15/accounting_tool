from django.db import migrations, models


def processed_to_status(apps, schema_editor):
    """Statements already extracted are DONE; anything else never ran."""
    Statement = apps.get_model('accounting', 'Statement')
    Statement.objects.filter(processed=True).update(status='done')
    Statement.objects.filter(processed=False).update(status='pending')


def status_to_processed(apps, schema_editor):
    Statement = apps.get_model('accounting', 'Statement')
    Statement.objects.filter(status='done').update(processed=True)
    Statement.objects.exclude(status='done').update(processed=False)


class Migration(migrations.Migration):

    dependencies = [
        ('accounting', '0002_initial'),
    ]

    # Order matters: the new fields must exist before the backfill can read
    # `processed`, and `processed` must survive until the backfill is done.
    operations = [
        migrations.AddField(
            model_name='statement',
            name='error_message',
            field=models.TextField(blank=True),
        ),
        migrations.AddField(
            model_name='statement',
            name='status',
            field=models.CharField(
                choices=[('pending', 'Pending'), ('processing', 'Processing'), ('done', 'Done'), ('failed', 'Failed')],
                default='pending',
                max_length=20,
            ),
        ),
        migrations.AddField(
            model_name='statement',
            name='transactions_found',
            field=models.PositiveIntegerField(default=0),
        ),
        migrations.RunPython(processed_to_status, status_to_processed),
        migrations.RemoveField(
            model_name='statement',
            name='processed',
        ),
    ]
