# -*- coding: utf-8 -*-
# Generated by Django 1.10.8 on 2018-10-03 18:31
from __future__ import unicode_literals

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("candidates", "0051_remove_areaextra")]

    operations = [
        migrations.AlterField(
            model_name="extrafield",
            name="type",
            field=models.CharField(
                choices=[
                    ("line", "A single line of text"),
                    ("longer-text", "One or more paragraphs of text"),
                    ("url", "A URL"),
                    ("yesno", "A Yes/No/Don't know dropdown"),
                ],
                max_length=64,
            ),
        )
    ]
