# -*- coding: utf-8 -*-
# Generated by Django 1.10.8 on 2018-08-14 16:59
from __future__ import unicode_literals

import django.core.validators
import django.db.models.deletion
from django.db import migrations, models

import popolo.behaviors.models


class Migration(migrations.Migration):

    dependencies = [("popolo", "0006_membership_unique_together")]

    operations = [
        migrations.AlterField(
            model_name="area",
            name="end_date",
            field=models.CharField(
                blank=True,
                help_text="The date when the validity of the item ends",
                max_length=10,
                null=True,
                validators=[
                    django.core.validators.RegexValidator(
                        message="Date has wrong format",
                        regex="^[0-9]{4}(-[0-9]{2}){0,2}$",
                    ),
                    popolo.behaviors.models.validate_partial_date,
                ],
                verbose_name="end date",
            ),
        ),
        migrations.AlterField(
            model_name="area",
            name="start_date",
            field=models.CharField(
                blank=True,
                help_text="The date when the validity of the item starts",
                max_length=10,
                null=True,
                validators=[
                    django.core.validators.RegexValidator(
                        message="Date has wrong format",
                        regex="^[0-9]{4}(-[0-9]{2}){0,2}$",
                    ),
                    popolo.behaviors.models.validate_partial_date,
                ],
                verbose_name="start date",
            ),
        ),
        migrations.AlterField(
            model_name="contactdetail",
            name="contact_type",
            field=models.CharField(
                choices=[
                    ("ADDRESS", "Address"),
                    ("EMAIL", "Email"),
                    ("URL", "Url"),
                    ("MAIL", "Snail mail"),
                    ("TWITTER", "Twitter"),
                    ("FACEBOOK", "Facebook"),
                    ("PHONE", "Telephone"),
                    ("MOBILE", "Mobile"),
                    ("TEXT", "Text"),
                    ("VOICE", "Voice"),
                    ("FAX", "Fax"),
                    ("CELL", "Cell"),
                    ("VIDEO", "Video"),
                    ("PAGER", "Pager"),
                    ("TEXTPHONE", "Textphone"),
                ],
                help_text="A type of medium, e.g. 'fax' or 'email'",
                max_length=12,
                verbose_name="type",
            ),
        ),
        migrations.AlterField(
            model_name="contactdetail",
            name="end_date",
            field=models.CharField(
                blank=True,
                help_text="The date when the validity of the item ends",
                max_length=10,
                null=True,
                validators=[
                    django.core.validators.RegexValidator(
                        message="Date has wrong format",
                        regex="^[0-9]{4}(-[0-9]{2}){0,2}$",
                    ),
                    popolo.behaviors.models.validate_partial_date,
                ],
                verbose_name="end date",
            ),
        ),
        migrations.AlterField(
            model_name="contactdetail",
            name="start_date",
            field=models.CharField(
                blank=True,
                help_text="The date when the validity of the item starts",
                max_length=10,
                null=True,
                validators=[
                    django.core.validators.RegexValidator(
                        message="Date has wrong format",
                        regex="^[0-9]{4}(-[0-9]{2}){0,2}$",
                    ),
                    popolo.behaviors.models.validate_partial_date,
                ],
                verbose_name="start date",
            ),
        ),
        migrations.AlterField(
            model_name="membership",
            name="end_date",
            field=models.CharField(
                blank=True,
                help_text="The date when the validity of the item ends",
                max_length=10,
                null=True,
                validators=[
                    django.core.validators.RegexValidator(
                        message="Date has wrong format",
                        regex="^[0-9]{4}(-[0-9]{2}){0,2}$",
                    ),
                    popolo.behaviors.models.validate_partial_date,
                ],
                verbose_name="end date",
            ),
        ),
        migrations.AlterField(
            model_name="membership",
            name="post_election",
            field=models.ForeignKey(
                on_delete=django.db.models.deletion.CASCADE,
                to="candidates.PostExtraElection",
            ),
        ),
        migrations.AlterField(
            model_name="membership",
            name="start_date",
            field=models.CharField(
                blank=True,
                help_text="The date when the validity of the item starts",
                max_length=10,
                null=True,
                validators=[
                    django.core.validators.RegexValidator(
                        message="Date has wrong format",
                        regex="^[0-9]{4}(-[0-9]{2}){0,2}$",
                    ),
                    popolo.behaviors.models.validate_partial_date,
                ],
                verbose_name="start date",
            ),
        ),
        migrations.AlterField(
            model_name="organization",
            name="dissolution_date",
            field=models.CharField(
                blank=True,
                help_text="A date of dissolution",
                max_length=10,
                null=True,
                validators=[
                    django.core.validators.RegexValidator(
                        code="invalid_dissolution_date",
                        message="dissolution date must follow the given pattern: ^[0-9]{4}(-[0-9]{2}){0,2}$",
                        regex="^[0-9]{4}(-[0-9]{2}){0,2}$",
                    )
                ],
                verbose_name="dissolution date",
            ),
        ),
        migrations.AlterField(
            model_name="organization",
            name="end_date",
            field=models.CharField(
                blank=True,
                help_text="The date when the validity of the item ends",
                max_length=10,
                null=True,
                validators=[
                    django.core.validators.RegexValidator(
                        message="Date has wrong format",
                        regex="^[0-9]{4}(-[0-9]{2}){0,2}$",
                    ),
                    popolo.behaviors.models.validate_partial_date,
                ],
                verbose_name="end date",
            ),
        ),
        migrations.AlterField(
            model_name="organization",
            name="founding_date",
            field=models.CharField(
                blank=True,
                help_text="A date of founding",
                max_length=10,
                null=True,
                validators=[
                    django.core.validators.RegexValidator(
                        code="invalid_founding_date",
                        message="founding date must follow the given pattern: ^[0-9]{4}(-[0-9]{2}){0,2}$",
                        regex="^[0-9]{4}(-[0-9]{2}){0,2}$",
                    )
                ],
                verbose_name="founding date",
            ),
        ),
        migrations.AlterField(
            model_name="organization",
            name="start_date",
            field=models.CharField(
                blank=True,
                help_text="The date when the validity of the item starts",
                max_length=10,
                null=True,
                validators=[
                    django.core.validators.RegexValidator(
                        message="Date has wrong format",
                        regex="^[0-9]{4}(-[0-9]{2}){0,2}$",
                    ),
                    popolo.behaviors.models.validate_partial_date,
                ],
                verbose_name="start date",
            ),
        ),
        migrations.AlterField(
            model_name="othername",
            name="end_date",
            field=models.CharField(
                blank=True,
                help_text="The date when the validity of the item ends",
                max_length=10,
                null=True,
                validators=[
                    django.core.validators.RegexValidator(
                        message="Date has wrong format",
                        regex="^[0-9]{4}(-[0-9]{2}){0,2}$",
                    ),
                    popolo.behaviors.models.validate_partial_date,
                ],
                verbose_name="end date",
            ),
        ),
        migrations.AlterField(
            model_name="othername",
            name="start_date",
            field=models.CharField(
                blank=True,
                help_text="The date when the validity of the item starts",
                max_length=10,
                null=True,
                validators=[
                    django.core.validators.RegexValidator(
                        message="Date has wrong format",
                        regex="^[0-9]{4}(-[0-9]{2}){0,2}$",
                    ),
                    popolo.behaviors.models.validate_partial_date,
                ],
                verbose_name="start date",
            ),
        ),
        migrations.AlterField(
            model_name="person",
            name="end_date",
            field=models.CharField(
                blank=True,
                help_text="The date when the validity of the item ends",
                max_length=10,
                null=True,
                validators=[
                    django.core.validators.RegexValidator(
                        message="Date has wrong format",
                        regex="^[0-9]{4}(-[0-9]{2}){0,2}$",
                    ),
                    popolo.behaviors.models.validate_partial_date,
                ],
                verbose_name="end date",
            ),
        ),
        migrations.AlterField(
            model_name="person",
            name="start_date",
            field=models.CharField(
                blank=True,
                help_text="The date when the validity of the item starts",
                max_length=10,
                null=True,
                validators=[
                    django.core.validators.RegexValidator(
                        message="Date has wrong format",
                        regex="^[0-9]{4}(-[0-9]{2}){0,2}$",
                    ),
                    popolo.behaviors.models.validate_partial_date,
                ],
                verbose_name="start date",
            ),
        ),
        migrations.AlterField(
            model_name="post",
            name="end_date",
            field=models.CharField(
                blank=True,
                help_text="The date when the validity of the item ends",
                max_length=10,
                null=True,
                validators=[
                    django.core.validators.RegexValidator(
                        message="Date has wrong format",
                        regex="^[0-9]{4}(-[0-9]{2}){0,2}$",
                    ),
                    popolo.behaviors.models.validate_partial_date,
                ],
                verbose_name="end date",
            ),
        ),
        migrations.AlterField(
            model_name="post",
            name="start_date",
            field=models.CharField(
                blank=True,
                help_text="The date when the validity of the item starts",
                max_length=10,
                null=True,
                validators=[
                    django.core.validators.RegexValidator(
                        message="Date has wrong format",
                        regex="^[0-9]{4}(-[0-9]{2}){0,2}$",
                    ),
                    popolo.behaviors.models.validate_partial_date,
                ],
                verbose_name="start date",
            ),
        ),
    ]
