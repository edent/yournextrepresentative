# Generated by Django 1.9.13 on 2018-05-18 10:44


import django.core.validators
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("popolo", "0004_move-extra-data-to-base")]


operations = [
    migrations.AlterField(
        model_name="membership",
        name="post_election",
        field=models.ForeignKey(
            on_delete=django.db.models.deletion.CASCADE,
            to="candidates.PostExtraElection",
        ),
    )
]
