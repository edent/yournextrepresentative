# -*- coding: utf-8 -*-
# Generated by Django 1.10.8 on 2018-08-14 17:04
from __future__ import unicode_literals

from django.db import migrations


def add_extra_fields_to_base(apps, schema_editor):
    Person = apps.get_model("popolo", "Person")
    PersonExtra = apps.get_model("candidates", "PersonExtra")
    ContentType = apps.get_model("contenttypes", "ContentType")
    Image = apps.get_model("images", "Image")

    old_to_new_map = {}

    # First, delete any Membership objects with no extra
    Person.objects.filter(extra=None).delete()

    for base in Person.objects.all().select_related("extra"):
        old_to_new_map[base.extra.pk] = base.pk
        base.versions = base.extra.versions
        base.save()
        for election in base.extra.not_standing.all():
            base.not_standing.add(election)

    # Update the content type ID for the images generic relation
    pe_content_type_id = ContentType.objects.get_for_model(PersonExtra).pk
    p_content_type_id = ContentType.objects.get_for_model(Person).pk
    Image.objects.filter(content_type_id=pe_content_type_id).update(
        content_type_id=p_content_type_id
    )
    images = Image.objects.filter(content_type_id=p_content_type_id)
    for image in images:
        if image.object_id in old_to_new_map:
            image.object_id = old_to_new_map[image.object_id]
            image.save()


class Migration(migrations.Migration):

    dependencies = [("popolo", "0008_add_person_extra_fields")]

    operations = [
        migrations.RunPython(
            add_extra_fields_to_base, migrations.RunPython.noop
        )
    ]
