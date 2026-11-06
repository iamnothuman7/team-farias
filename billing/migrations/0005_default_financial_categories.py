from django.db import migrations


def create_categories(apps, schema_editor):
    category = apps.get_model("billing", "FinancialCategory")
    defaults = {
        "income": ["Receitas avulsas", "Produtos", "Eventos", "Patrocínios"],
        "expense": ["Aluguel", "Equipe", "Equipamentos", "Manutenção", "Taxas", "Outras despesas"],
    }
    for kind, names in defaults.items():
        for name in names:
            category.objects.using(schema_editor.connection.alias).get_or_create(kind=kind, name=name)


class Migration(migrations.Migration):
    dependencies = [("billing", "0004_financialcategory_financialentry_financialevent_and_more")]
    operations = [migrations.RunPython(create_categories, migrations.RunPython.noop)]
