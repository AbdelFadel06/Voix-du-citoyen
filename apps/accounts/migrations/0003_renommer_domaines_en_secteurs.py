from django.db import migrations, models


class Migration(migrations.Migration):
    """Organisation.domaines devient Organisation.secteurs (les liens sont conservés)."""

    dependencies = [
        ("accounts", "0002_organisation_domaines"),
        ("referentiel", "0002_renommer_categorie_en_secteur"),
    ]

    operations = [
        migrations.RenameField(model_name="organisation", old_name="domaines", new_name="secteurs"),
        migrations.AlterField(
            model_name="organisation",
            name="secteurs",
            field=models.ManyToManyField(
                blank=True,
                related_name="organisations",
                to="referentiel.secteur",
                verbose_name="secteurs d'intervention",
            ),
        ),
    ]
