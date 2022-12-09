# Generated by Django 4.1.3 on 2022-12-02 10:54

from django.db import migrations, models
import django.db.models.deletion
import django_extensions.db.fields


class Migration(migrations.Migration):

    dependencies = [
        ("parties", "0017_alter_party_ec_id"),
    ]

    operations = [
        migrations.CreateModel(
            name="PartySpending",
            fields=[
                (
                    "created",
                    django_extensions.db.fields.CreationDateTimeField(
                        auto_now_add=True, verbose_name="created"
                    ),
                ),
                (
                    "modified",
                    django_extensions.db.fields.ModificationDateTimeField(
                        auto_now=True, verbose_name="modified"
                    ),
                ),
                (
                    "ec_id",
                    models.CharField(
                        max_length=15, primary_key=True, serialize=False
                    ),
                ),
                ("raw_data", models.JSONField()),
                (
                    "party",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="parties.party",
                    ),
                ),
            ],
            options={
                "get_latest_by": "modified",
                "abstract": False,
            },
        ),
    ]
