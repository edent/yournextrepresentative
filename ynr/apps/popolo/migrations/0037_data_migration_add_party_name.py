# Generated by Django 2.2.16 on 2021-03-15 12:49

from django.db import migrations
from django.utils import timezone

REFORM_UK_EC_ID = "PP7931"
CHANGE_DATE = timezone.datetime(2021, 1, 6).date()


def add_party_names(apps, schema_editor):
    Membership = apps.get_model("popolo", "Membership")
    for membership in Membership.objects.all().select_related(
        "party", "ballot__election"
    ):
        if not membership.party:
            continue

        if (
            membership.party.ec_id == REFORM_UK_EC_ID
            and membership.ballot.election.election_date < CHANGE_DATE
        ):
            membership.party_name = "Brexit Party"
        else:
            membership.party_name = membership.party.name

        membership.save()


def remove_party_names(apps, schema_editor):
    Membership = apps.get_model("popolo", "Membership")
    Membership.objects.update(party_name="")


class Migration(migrations.Migration):
    dependencies = [("popolo", "0036_add_party_name_and_description")]

    operations = [
        migrations.RunPython(
            code=add_party_names, reverse_code=remove_party_names
        )
    ]
