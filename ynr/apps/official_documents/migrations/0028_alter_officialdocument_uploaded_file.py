# Generated by Django 3.2.12 on 2022-04-05 10:21

import django.core.validators
import official_documents.models
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("official_documents", "0027_alter_officialdocument_source_url")
    ]

    operations = [
        migrations.AlterField(
            model_name="officialdocument",
            name="uploaded_file",
            field=models.FileField(
                max_length=800,
                upload_to=official_documents.models.document_file_name,
                validators=[
                    django.core.validators.FileExtensionValidator(
                        allowed_extensions=["pdf", "docx"]
                    )
                ],
            ),
        )
    ]
