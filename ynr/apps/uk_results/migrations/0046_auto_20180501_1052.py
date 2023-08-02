# Generated by Django 1.9.13 on 2018-05-01 09:52


import django.contrib.postgres.fields.jsonb
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("uk_results", "0045_auto_20180424_2150")]

    operations = [
        migrations.AddField(
            model_name="resultset",
            name="versions",
            field=django.contrib.postgres.fields.jsonb.JSONField(default=list),
        ),
        migrations.AlterField(
            model_name="resultset",
            name="num_spoilt_ballots",
            field=models.IntegerField(null=True, verbose_name="Spoilt Ballots"),
        ),
        migrations.AlterField(
            model_name="resultset",
            name="num_turnout_reported",
            field=models.IntegerField(
                null=True, verbose_name="Reported Turnout"
            ),
        ),
    ]
