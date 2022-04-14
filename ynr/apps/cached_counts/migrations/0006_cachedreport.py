# Generated by Django 3.2 on 2022-04-04 20:28

import django.contrib.postgres.fields.jsonb
from django.db import migrations, models


class Migration(migrations.Migration):

    initial = True

    dependencies = [("cached_counts", "0005_delete_cachedcount")]

    operations = [
        migrations.CreateModel(
            name="CachedReport",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                ("election_date", models.DateField()),
                ("register", models.CharField(max_length=2)),
                ("report_name", models.CharField(max_length=255)),
                (
                    "report_json",
                    django.contrib.postgres.fields.jsonb.JSONField(),
                ),
            ],
        )
    ]
