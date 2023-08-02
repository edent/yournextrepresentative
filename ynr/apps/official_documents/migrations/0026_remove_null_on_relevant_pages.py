# Generated by Django 3.2.10 on 2022-01-10 12:20

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("official_documents", "0025_rename_post_election_fk_to_ballot")
    ]

    operations = [
        migrations.AlterField(
            model_name="officialdocument",
            name="relevant_pages",
            field=models.CharField(
                default="",
                max_length=50,
                verbose_name="The pages containing information about this ballot",
            ),
        )
    ]
