# Generated by Django 4.1.4 on 2022-12-12 15:55

from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("users", "0003_identity_followers_etc"),
    ]

    operations = [
        migrations.AddField(
            model_name="identity",
            name="visible_follows",
            field=models.BooleanField(default=True),
        ),
    ]
