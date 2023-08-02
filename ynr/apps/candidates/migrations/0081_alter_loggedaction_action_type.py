# Generated by Django 3.2.12 on 2022-04-05 10:21

from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("candidates", "0080_add_person_delete_action_type")]

    operations = [
        migrations.AlterField(
            model_name="loggedaction",
            name="action_type",
            field=models.CharField(
                choices=[
                    ("entered-results-data", "Entered results"),
                    ("set-candidate-elected", "Set Candidate elected"),
                    ("set-candidate-not-elected", "Set Candidate not elected"),
                    ("person-lock", "Person locked"),
                    ("person-update", "Person updated"),
                    ("person-create", "Person created"),
                    ("person-delete", "Person deleted"),
                    ("person-other-name-create", "Person Other name created"),
                    ("person-other-name-delete", "Person Other name deleted"),
                    ("person-other-name-update", "Person Other name updated"),
                    ("person-revert", "Person reverted"),
                    ("constituency-lock", "Constituency locked"),
                    ("constituency-unlock", "Constituency unlocked"),
                    ("candidacy-create", "Candidacy created"),
                    ("candidacy-delete", "Candidacy deleted"),
                    ("photo-approve", "Photo approved"),
                    ("photo-upload", "Photo uploaded"),
                    ("photo-reject", "Photo rejected"),
                    ("photo-ignore", "Photo ignored"),
                    ("suggest-ballot-lock", "Suggested ballot lock"),
                    ("person-merge", "Person merged"),
                    ("record-council-result", "Recorded council result"),
                    ("confirm-council-result", "Confirmed council result "),
                    ("sopn-upload", "SOPN uploaded"),
                    ("record-council-control", "Recorded council control"),
                    ("confirm-council-control", "Confirmed council control"),
                    ("retract-winner", "Retracted winner"),
                    ("duplicate-suggest", "Duplicate suggested"),
                    ("change-edit-limitations", "Changed edit limitations"),
                    ("suspended-twitter-account", "Suspended Twitter account"),
                    ("deleted-parsed-raw-people", "Deleted parsed RawPeople"),
                ],
                max_length=64,
            ),
        )
    ]
