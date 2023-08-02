# -*- coding: utf-8 -*-
# Generated by Django 1.11.20 on 2019-03-20 11:03
from __future__ import unicode_literals

from django.db import migrations


def clean_up_lock_suggestions(apps, schema_editor):
    SuggestedPostLock = apps.get_model("moderation_queue", "SuggestedPostLock")
    SuggestedPostLock.objects.filter(
        postextraelection__election__current=False
    ).delete()


class Migration(migrations.Migration):
    dependencies = [("moderation_queue", "0024_move_person_fk_to_people_app")]

    operations = [
        migrations.RunPython(
            clean_up_lock_suggestions, migrations.RunPython.noop
        )
    ]
