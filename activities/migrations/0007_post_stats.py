# Generated by Django 4.1.4 on 2022-12-31 20:41

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("activities", "0006_fanout_subject_identity_alter_fanout_type"),
    ]

    operations = [
        migrations.AddField(
            model_name="post",
            name="stats",
            field=models.JSONField(blank=True, null=True),
        ),
    ]
