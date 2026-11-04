from django.db import migrations, models


def update_defaults(apps, schema_editor):
    Config = apps.get_model('core', 'SiteConfiguration')
    Config.objects.filter(plan_title='Plano único').update(plan_title='Seu plano de treino')
    Config.objects.filter(meta_description='Team Farias — vôlei de praia em Tianguá, Ceará. Plano único com valores e informações pelo WhatsApp.').update(meta_description='Team Farias — vôlei de praia em Tianguá, Ceará. Consulte planos, valores e informações pelo WhatsApp.')


class Migration(migrations.Migration):
    dependencies = [('core', '0001_initial')]
    operations = [
        migrations.AlterField(model_name='siteconfiguration', name='plan_title', field=models.CharField(default='Seu plano de treino', max_length=80, verbose_name='título da consulta de planos')),
        migrations.AlterField(model_name='siteconfiguration', name='meta_description', field=models.CharField(default='Team Farias — vôlei de praia em Tianguá, Ceará. Consulte planos, valores e informações pelo WhatsApp.', max_length=300, verbose_name='descrição para buscas')),
        migrations.RunPython(update_defaults, migrations.RunPython.noop),
    ]
