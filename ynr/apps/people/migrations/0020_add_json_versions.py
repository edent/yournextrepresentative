# Generated by Django 2.2.16 on 2021-01-06 19:02

import django.contrib.postgres.fields.jsonb
from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("people", "0019_move_to_ballot_in_version_history")]

    operations = [
        migrations.AddField(
            model_name="person",
            name="json_versions",
            field=django.contrib.postgres.fields.jsonb.JSONField(null=True),
        )
    ]
