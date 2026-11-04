from django.core.management.base import BaseCommand
from school.push import dispatch


class Command(BaseCommand):
    help = "Enfileira comunicados publicados e envia notificações autorizadas."

    def handle(self, *args, **options):
        result = dispatch()
        self.stdout.write(f"configured={result['configured']} sent={result['sent']}")
