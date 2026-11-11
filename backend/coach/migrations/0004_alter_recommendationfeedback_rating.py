import django.core.validators
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('coach', '0003_alter_consumptionforecast_confidence_lower_kwh_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='recommendationfeedback',
            name='rating',
            field=models.IntegerField(
                default=5,
                help_text='Rating from 1 (poor) to 5 (excellent)',
                validators=[
                    django.core.validators.MinValueValidator(1),
                    django.core.validators.MaxValueValidator(5),
                ],
            ),
        ),
    ]

