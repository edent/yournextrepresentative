# -*- coding: utf-8 -*-
# Generated by Django 1.10.8 on 2018-10-03 18:31
from __future__ import unicode_literals

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [("popolo", "0023_remove_area_model")]

    operations = [migrations.RemoveField(model_name="person", name="image")]
