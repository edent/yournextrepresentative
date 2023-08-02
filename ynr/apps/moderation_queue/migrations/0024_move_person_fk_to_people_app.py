# -*- coding: utf-8 -*-
# Generated by Django 1.10.8 on 2018-10-23 19:36
from __future__ import unicode_literals

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("moderation_queue", "0023_python_3_changes"),
        ("people", "0004_move_person_data"),
    ]

    operations = [
        migrations.AlterField(
            model_name="queuedimage",
            name="person",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                to="people.Person",
            ),
        )
    ]
