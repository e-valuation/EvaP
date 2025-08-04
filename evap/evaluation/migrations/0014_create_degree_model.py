from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("evaluation", "0013_rename_kind_to_type"),
    ]

    operations = [
        migrations.CreateModel(
            name="Degree",
            fields=[
                ("id", models.AutoField(serialize=False, verbose_name="ID", auto_created=True, primary_key=True)),
                ("name_de", models.CharField(max_length=1024, verbose_name="name (german)")),
                ("name_en", models.CharField(max_length=1024, verbose_name="name (english)")),
                ("order", models.IntegerField(default=0, verbose_name="degree order")),
            ],
            options={
                "ordering": ["order"],
            },
            bases=(models.Model,),
        ),
    ]
