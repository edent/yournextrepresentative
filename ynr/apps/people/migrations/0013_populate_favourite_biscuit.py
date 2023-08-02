# -*- coding: utf-8 -*-
# Generated by Django 1.11.16 on 2018-11-27 08:19

from django.db import migrations
from django.db.models.functions import Length


def populate_favourite_biscuit_from_extrafieldvalue(apps, schema_editor):
    PersonExtraFieldValue = apps.get_model(
        "candidates", "PersonExtraFieldValue"
    )
    ExtraField = apps.get_model("candidates", "ExtraField")

    try:
        biscuit_field = ExtraField.objects.prefetch_related(
            "personextrafieldvalue_set"
        ).get(key="favourite_biscuits")
    except ExtraField.DoesNotExist:
        # This DB hasn't got a `favourite_biscuits` field defined,
        # so there's nothing we can do here. Just skip the rest of the migration
        return

    too_long = PersonExtraFieldValue.objects.annotate(
        value_len=Length("value")
    ).filter(field_id=biscuit_field.pk, value_len__gt=254)

    if too_long.exists():
        msg = [
            "Value is too long for the following people. "
            "Please manually fix:"
        ]
        for value_field in too_long:
            msg.append(str(value_field.person.pk))
        raise ValueError("\n".join(msg))

    for value in biscuit_field.personextrafieldvalue_set.all():
        person = value.person
        person.favourite_biscuit = value.value
        person.save()


class Migration(migrations.Migration):
    dependencies = [("people", "0012_add_person_favourite_biscuit")]

    operations = [
        migrations.RunPython(
            populate_favourite_biscuit_from_extrafieldvalue,
            migrations.RunPython.noop,
        )
    ]
