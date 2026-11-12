from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ('products', '0001_initial'),
    ]

    operations = [
        migrations.CreateModel(
            name='InventoryReservation',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('order_id', models.CharField(max_length=255)),
                ('quantity', models.PositiveIntegerField()),
                ('status', models.CharField(choices=[('reserved', 'Reserved'), ('released', 'Released')], default='reserved', max_length=20)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('released_at', models.DateTimeField(blank=True, null=True)),
                ('product', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='reservations', to='products.product')),
            ],
        ),
        migrations.AddConstraint(
            model_name='inventoryreservation',
            constraint=models.UniqueConstraint(fields=('product', 'order_id'), name='unique_product_order_reservation'),
        ),
        migrations.AddIndex(
            model_name='inventoryreservation',
            index=models.Index(fields=['order_id', 'status'], name='products_in_order_i_6d93c0_idx'),
        ),
        migrations.AddIndex(
            model_name='inventoryreservation',
            index=models.Index(fields=['product', 'status'], name='products_in_product_4d4d83_idx'),
        ),
    ]
