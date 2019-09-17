# Generated by Django 1.9.13 on 2018-03-23 13:49


import django.db.models.deletion
from django.db import migrations, models


def populate_post_election_from_membership(apps, schema_editor):
    PostExtraElection = apps.get_model("candidates", "PostExtraElection")
    MembershipExtra = apps.get_model("candidates", "MembershipExtra")
    qs = MembershipExtra.objects.filter(post_election=None).select_related(
        "base__post__extra"
    )
    for me in qs:
        # Get the PostExtraElection
        pee = PostExtraElection.objects.get(
            postextra=me.base.post.extra, election=me.election
        )
        me.post_election = pee
        me.save()


def do_nothing(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("candidates", "0039_create_ballot_paper_ids_and_set_unique")
    ]

    operations = [
        migrations.AddField(
            model_name="membershipextra",
            name="post_election",
            field=models.ForeignKey(
                null=True,
                on_delete=django.db.models.deletion.CASCADE,
                to="candidates.PostExtraElection",
            ),
        ),
        migrations.RunPython(
            populate_post_election_from_membership, do_nothing
        ),
    ]
