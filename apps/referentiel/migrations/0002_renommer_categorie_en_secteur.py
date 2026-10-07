import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    """Categorie devient Secteur : renommage (les données sont conservées)."""

    dependencies = [
        ("accounts", "0002_organisation_domaines"),
        ("referentiel", "0001_initial"),
    ]

    operations = [
        migrations.RenameModel(old_name="Categorie", new_name="Secteur"),
        migrations.AlterModelOptions(
            name="secteur",
            options={
                "ordering": ["ordre", "nom"],
                "verbose_name": "secteur",
                "verbose_name_plural": "secteurs",
            },
        ),
        migrations.AlterField(
            model_name="secteur",
            name="nom",
            field=models.CharField(
                error_messages={"unique": "Un secteur porte déjà ce nom."},
                max_length=100,
                unique=True,
                verbose_name="nom",
            ),
        ),
        migrations.AlterField(
            model_name="secteur",
            name="code",
            field=models.CharField(
                error_messages={"unique": "Un secteur utilise déjà ce code."},
                max_length=30,
                unique=True,
                verbose_name="code",
            ),
        ),
        migrations.AlterField(
            model_name="secteur",
            name="actif",
            field=models.BooleanField(default=True, verbose_name="actif"),
        ),
        migrations.AlterField(
            model_name="secteur",
            name="service_par_defaut",
            field=models.ForeignKey(
                blank=True,
                help_text="Service auquel les nouveaux signalements de ce secteur sont assignés.",
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="secteurs",
                to="accounts.servicemunicipal",
                verbose_name="service par défaut",
            ),
        ),
    ]
