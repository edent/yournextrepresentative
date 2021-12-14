# Generated by Django 3.2.10 on 2021-12-14 17:21

from django.db import migrations, models
import django.db.models.deletion
import django_extensions.db.fields
import official_documents.models


class Migration(migrations.Migration):

    initial = True

    dependencies = [("candidates", "0001_initial")]

    operations = [
        migrations.CreateModel(
            name="OfficialDocument",
            fields=[
                (
                    "id",
                    models.AutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "created",
                    django_extensions.db.fields.CreationDateTimeField(
                        auto_now_add=True, verbose_name="created"
                    ),
                ),
                (
                    "modified",
                    django_extensions.db.fields.ModificationDateTimeField(
                        auto_now=True, verbose_name="modified"
                    ),
                ),
                (
                    "document_type",
                    models.CharField(
                        choices=[("Nomination paper", "Nomination paper")],
                        max_length=100,
                    ),
                ),
                (
                    "uploaded_file",
                    models.FileField(
                        max_length=800,
                        upload_to=official_documents.models.document_file_name,
                    ),
                ),
                (
                    "source_url",
                    models.URLField(
                        help_text="The page that links to this document",
                        max_length=1000,
                    ),
                ),
                (
                    "relevant_pages",
                    models.CharField(
                        max_length=50,
                        null=True,
                        verbose_name="The pages containing information about this ballot",
                    ),
                ),
                (
                    "ballot",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        to="candidates.ballot",
                    ),
                ),
            ],
            options={"get_latest_by": "modified"},
        )
    ]
