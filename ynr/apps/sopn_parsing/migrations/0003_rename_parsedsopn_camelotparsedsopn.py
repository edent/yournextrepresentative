# Generated by Django 4.2.9 on 2024-01-05 14:17

from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("official_documents", "0030_textractresult_analysis_status"),
        ("sopn_parsing", "0002_awstextractparsedsopn"),
    ]

    operations = [
        migrations.RenameModel(
            old_name="ParsedSOPN",
            new_name="CamelotParsedSOPN",
        ),
    ]
