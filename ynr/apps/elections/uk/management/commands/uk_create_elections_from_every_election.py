import requests

from django.core.management.base import BaseCommand
from django.db import transaction

from elections.models import Election

from elections.uk.every_election import EveryElectionImporter


class Command(BaseCommand):
    help = "Create posts and elections from a EveryElection"

    def handle(self, *args, **options):

        # Get all elections from EveryElection
        ee_importer = EveryElectionImporter()
        ee_importer.build_election_tree()

        with transaction.atomic():
            # Mark all elections as not current, any that are current will
            # be (re)set later
            Election.objects.update(current=False)
            for ballot_id, election_dict in ee_importer.ballot_ids.items():
                parent = ee_importer.get_parent(ballot_id)
                election_dict.get_or_create_post_election(parent=parent)
