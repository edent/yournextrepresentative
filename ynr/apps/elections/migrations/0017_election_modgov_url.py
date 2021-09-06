# Generated by Django 2.2.18 on 2021-05-05 14:40

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [("elections", "0016_positive_int_field")]

    operations = [
        migrations.AddField(
            model_name="election",
            name="modgov_url",
            field=models.URLField(
                blank=True,
                help_text="Used to store a possible ModGov url that can be used to scrape information for this election",
                null=True,
            ),
        )
    ]