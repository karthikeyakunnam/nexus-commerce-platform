from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ('orders', '0002_alter_order_user_id'),
    ]

    operations = [
        migrations.AddField(
            model_name='order',
            name='idempotency_key',
            field=models.CharField(
                blank=True,
                help_text='Unique key for safely retrying checkout requests',
                max_length=255,
                null=True,
                unique=True,
            ),
        ),
    ]
