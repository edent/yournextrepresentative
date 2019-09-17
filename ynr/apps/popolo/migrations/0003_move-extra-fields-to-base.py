# Generated by Django 1.9.13 on 2018-05-18 10:17


import django.core.validators
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("candidates", "0044_remove_membership_fk_to_election"),
        ("popolo", "0002_update_models_from_upstream"),
    ]

    operations = [
        migrations.AddField(
            model_name="membership",
            name="elected",
            field=models.NullBooleanField(),
        ),
        migrations.AddField(
            model_name="membership",
            name="party_list_position",
            field=models.IntegerField(null=True),
        ),
        migrations.AddField(
            model_name="membership",
            name="post_election",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                to="candidates.PostExtraElection",
            ),
        ),
    ]
