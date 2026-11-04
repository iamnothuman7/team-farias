"""Popula o banco com dados de demonstração do Team Farias.

Uso:
    python manage.py seed_demo            # cria apenas se ainda não existir
    python manage.py seed_demo --reset    # apaga os dados do projeto e recria
"""

from __future__ import annotations

import random
from datetime import date, datetime, time, timedelta
from decimal import Decimal

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone
from django.utils.crypto import get_random_string

from accounts.models import Guardian, Student, User
from billing.models import Invoice, Payment, Plan, due_date_for
from school.models import (
    Announcement,
    Attendance,
    ClassGroup,
    Enrollment,
    PointEntry,
    PointRule,
    ScheduleSlot,
    Session,
    Venue,
)

PASSWORD = get_random_string(24)

STUDENTS = [
    ("Ana Sofia", "Almeida", "ana.almeida", 2, "intermediario", 16, "levantamento"),
    ("João Pedro", "Lima", "joao.lima", 3, "avancado", 17, "bloqueio"),
    ("Maria Clara", "Souza", "maria.souza", 0, "iniciante", 14, "defesa"),
    ("Pedro Henrique", "Rocha", "pedro.rocha", 3, "avancado", 17, "ataque"),
    ("Luiza", "Ferreira", "luiza.ferreira", 2, "intermediario", 15, "defesa"),
    ("Gabriel", "Nunes", "gabriel.nunes", 1, "iniciante", 12, "levantamento"),
    ("Beatriz", "Castro", "beatriz.castro", 5, "intermediario", 22, "bloqueio"),
    ("Rafael", "Moura", "rafael.moura", 4, "iniciante", 28, "defesa"),
    ("Isabela", "Prado", "isabela.prado", 0, "iniciante", 15, "ataque"),
    ("Thiago", "Bezerra", "thiago.bezerra", 2, "intermediario", 16, "bloqueio"),
    ("Camila", "Andrade", "camila.andrade", 5, "intermediario", 24, "defesa"),
    ("Lucas", "Vieira", "lucas.vieira", 3, "avancado", 18, "levantamento"),
    ("Manuela", "Torres", "manuela.torres", 1, "iniciante", 11, "defesa"),
    ("Vinícius", "Braga", "vinicius.braga", 4, "iniciante", 31, "ataque"),
    ("Heloísa", "Martins", "heloisa.martins", 0, "iniciante", 13, "levantamento"),
    ("Arthur", "Queiroz", "arthur.queiroz", 1, "iniciante", 12, "bloqueio"),
    ("Larissa", "Pontes", "larissa.pontes", 5, "intermediario", 26, "ataque"),
    ("Davi", "Fontenele", "davi.fontenele", 4, "iniciante", 23, "defesa"),
]

GUARDIANS = [
    ("Cláudia Almeida", "(85) 98811-2043", "claudia.almeida@email.com"),
    ("Marcos Souza", "(85) 99642-7710", "marcos.souza@email.com"),
    ("Renata Ferreira", "(85) 98120-5544", "renata.ferreira@email.com"),
    ("Paulo Nunes", "(85) 99733-1188", "paulo.nunes@email.com"),
    ("Adriana Prado", "(85) 98455-9032", "adriana.prado@email.com"),
    ("Sérgio Torres", "(85) 99901-6644", "sergio.torres@email.com"),
    ("Luciana Martins", "(85) 98217-3390", "luciana.martins@email.com"),
    ("Rogério Queiroz", "(85) 99655-8123", "rogerio.queiroz@email.com"),
    ("Débora Ramos", "(85) 98144-2277", "debora.ramos@email.com"),
]

GROUPS = [
    {
        "name": "Iniciante Manhã",
        "category": "sub15",
        "level": "iniciante",
        "professor": 1,
        "venue": 0,
        "capacity": 16,
        "description": "Primeiros fundamentos na areia: saque, manchete e posicionamento, com ritmo leve.",
        "slots": [(1, time(7, 0), time(8, 0)), (3, time(7, 0), time(8, 0))],
    },
    {
        "name": "Iniciante Tarde",
        "category": "sub13",
        "level": "iniciante",
        "professor": 2,
        "venue": 0,
        "capacity": 14,
        "description": "Turma de base para quem está começando: coordenação, toque e jogo reduzido.",
        "slots": [(0, time(17, 0), time(18, 0)), (2, time(17, 0), time(18, 0))],
    },
    {
        "name": "Intermediário Sub-17",
        "category": "sub17",
        "level": "intermediario",
        "professor": 1,
        "venue": 1,
        "capacity": 14,
        "description": "Fundamentos com intensidade, leitura de jogo e primeiras competições internas.",
        "slots": [(1, time(18, 30), time(19, 45)), (3, time(18, 30), time(19, 45))],
    },
    {
        "name": "Avançado Competição",
        "category": "sub17",
        "level": "avancado",
        "professor": 0,
        "venue": 1,
        "capacity": 12,
        "description": "Preparação para torneios: sistema de jogo, transição e condicionamento na areia.",
        "slots": [(0, time(19, 0), time(20, 30)), (2, time(19, 0), time(20, 30)), (4, time(19, 0), time(20, 30))],
    },
    {
        "name": "Adulto Iniciante",
        "category": "adulto",
        "level": "iniciante",
        "professor": 2,
        "venue": 0,
        "capacity": 18,
        "description": "Para adultos que querem começar ou voltar a jogar, sem pressão e com boa companhia.",
        "slots": [(5, time(8, 0), time(9, 30))],
    },
    {
        "name": "Feminino Intermediário",
        "category": "adulto",
        "level": "intermediario",
        "professor": 1,
        "venue": 0,
        "capacity": 14,
        "description": "Treino feminino com foco em consistência, comunicação e jogo de dupla.",
        "slots": [(1, time(19, 15), time(20, 30)), (3, time(19, 15), time(20, 30))],
    },
]

ANNOUNCEMENTS = [
    {
        "title": "Nova grade de horários começa nesta semana",
        "kind": "noticia",
        "audience": "alunos",
        "summary": "Turmas reorganizadas por nível e dois novos horários na Arena Beira-Mar.",
        "body": (
            "A partir desta semana, o Team Farias passa a operar com uma grade reorganizada por nível. "
            "A mudança vem para deixar cada turma mais homogênea e o treino mais produtivo para todos.\n\n"
            "As turmas Iniciante Manhã e Iniciante Tarde mantêm os horários. O Intermediário Sub-17 ganhou "
            "mais 15 minutos de treino e o Avançado Competição passa a treinar três vezes por semana.\n\n"
            "Quem já está matriculado não precisa fazer nada: a equipe ajustou as turmas e o calendário "
            "já aparece atualizado na área do aluno."
        ),
        "is_pinned": True,
    },
    {
        "title": "Aulão aberto de vôlei de praia no feriado",
        "kind": "evento",
        "audience": "alunos",
        "summary": "Treino aberto para alunos e convidados, com circuito de fundamentos e jogo livre.",
        "body": (
            "No próximo feriado vamos abrir a areia para um aulão especial. Serão duas horas de circuito "
            "de fundamentos, correção técnica e jogo livre entre as turmas.\n\n"
            "Alunos podem levar um convidado. A participação conta presença e pontos extras no ranking. "
            "Inscrições na área do aluno ou direto com a equipe."
        ),
        "is_pinned": False,
    },
    {
        "title": "Ranking do mês: quem subiu na areia",
        "kind": "noticia",
        "audience": "alunos",
        "summary": "Veja quem mais pontuou no último ciclo de treinos e como funciona a pontuação.",
        "body": (
            "O ranking do Team Farias é atualizado a cada treino. Presença vale pontos, e a equipe também "
            "lança pontos de desempenho para quem se destaca em fundamento, atitude e evolução.\n\n"
            "A classificação completa fica na área do aluno, com histórico de cada ganho. As regras de "
            "pontuação são definidas pela equipe e podem mudar a cada ciclo — sempre comunicadas antes."
        ),
        "is_pinned": False,
    },
    {
        "title": "Atenção aos horários desta semana",
        "kind": "aviso",
        "audience": "alunos",
        "summary": "Quarta-feira o treino da tarde começa 30 minutos mais cedo por causa da maré.",
        "body": (
            "Nesta quarta-feira, o treino da turma Iniciante Tarde começa às 16h30 por causa da tábua de maré. "
            "As demais turmas seguem o horário normal.\n\n"
            "Quem tiver dificuldade com o ajuste, fale com a equipe pelo WhatsApp."
        ),
        "is_pinned": True,
    },
    {
        "title": "Reunião da equipe na quinta-feira",
        "kind": "aviso",
        "audience": "interno",
        "summary": "Alinhamento de planejamento do próximo ciclo, presenças e financeiro.",
        "body": (
            "Reunião interna na quinta, às 20h, para revisar o ciclo de treinos, pendências de matrícula e "
            "a situação das mensalidades do mês. Pauta no painel da equipe."
        ),
        "is_pinned": False,
    },
]


class Command(BaseCommand):
    help = "Cria dados de demonstração (turmas, alunos, treinos, pontos e mensalidades)."

    def add_arguments(self, parser):
        parser.add_argument("--reset", action="store_true", help="Apaga os dados do projeto antes de recriar.")

    @transaction.atomic
    def handle(self, *args, **options):
        if not settings.DEBUG:
            raise CommandError("Dados de demonstração são proibidos em produção.")
        rng = random.Random(7)
        today = timezone.localdate()

        if options["reset"]:
            self.stdout.write("Limpando dados anteriores…")
            Payment.objects.all().delete()
            Invoice.objects.all().delete()
            Attendance.objects.all().delete()
            PointEntry.objects.all().delete()
            PointRule.objects.all().delete()
            Session.objects.all().delete()
            ScheduleSlot.objects.all().delete()
            Enrollment.objects.all().delete()
            Announcement.objects.all().delete()
            ClassGroup.objects.all().delete()
            Plan.objects.all().delete()
            Venue.objects.all().delete()
            Student.objects.all().delete()
            Guardian.objects.all().delete()
            User.objects.all().delete()

        if not options["reset"] and User.objects.filter(email="farias@teamfarias.com.br").exists():
            self.stdout.write(self.style.WARNING("Dados já existem. Use --reset para recriar."))
            return

        # ----------------------------------------------------------- equipe
        admin = User.objects.create_superuser(
            email="farias@teamfarias.com.br",
            password=PASSWORD,
            first_name="Rafael",
            last_name="Farias",
            phone="(85) 99999-0101",
            role=User.Role.ADMIN,
        )
        marina = User.objects.create_user(
            email="marina@teamfarias.com.br",
            password=PASSWORD,
            first_name="Marina",
            last_name="Costa",
            phone="(85) 98888-2020",
            role=User.Role.PROFESSOR,
        )
        diego = User.objects.create_user(
            email="diego@teamfarias.com.br",
            password=PASSWORD,
            first_name="Diego",
            last_name="Alves",
            phone="(85) 98888-3030",
            role=User.Role.PROFESSOR,
        )
        professors = [admin, marina, diego]

        # ----------------------------------------------------------- estrutura
        venues = [
            Venue.objects.create(name="Arena Beira-Mar", address="Av. Beira-Mar, 2500 — Meireles, Fortaleza/CE"),
            Venue.objects.create(name="Arena Praia do Futuro", address="Av. Zezé Diogo, 4400 — Praia do Futuro, Fortaleza/CE"),
        ]
        plans = [Plan.objects.create(name="Plano único", monthly_fee=Decimal("180.00"), sessions_per_week=2, due_day=10, description="Exemplo apenas para desenvolvimento.")]

        groups = []
        for spec in GROUPS:
            group = ClassGroup.objects.create(
                name=spec["name"],
                category=spec["category"],
                level=spec["level"],
                professor=professors[spec["professor"]],
                venue=venues[spec["venue"]],
                capacity=spec["capacity"],
                description=spec["description"],
            )
            for weekday, start, end in spec["slots"]:
                ScheduleSlot.objects.create(
                    class_group=group,
                    weekday=weekday,
                    start_time=start,
                    end_time=end,
                    venue=venues[spec["venue"]],
                )
            groups.append(group)

        # ----------------------------------------------------------- alunos
        guardians = [
            Guardian.objects.create(name=name, phone=phone, email=email) for name, phone, email in GUARDIANS
        ]

        rules = {
            "presenca": PointRule.objects.create(name="Presença no treino", points=10, description="Comparecer ao treino da turma."),
            "destaque": PointRule.objects.create(name="Destaque do treino", points=20, description="Atitude e desempenho acima do esperado."),
            "evolucao": PointRule.objects.create(name="Evolução técnica", points=15, description="Progresso visível em um fundamento."),
            "evento": PointRule.objects.create(name="Participação em evento", points=30, description="Aulões, torneios internos e ações da escolinha."),
            "ajuste": PointRule.objects.create(name="Ajuste da equipe", points=-5, description="Correção manual feita pela equipe."),
        }

        students: list[Student] = []
        for index, (first, last, slug, group_index, level, age, position) in enumerate(STUDENTS):
            birth = today - timedelta(days=age * 365 + rng.randint(0, 320))
            user = User.objects.create_user(
                email=f"{slug}@aluno.teamfarias.com.br",
                password=PASSWORD,
                first_name=first,
                last_name=last,
                phone=f"(85) 9{rng.randint(7000, 9999)}-{rng.randint(1000, 9999)}",
                birth_date=birth,
                role=User.Role.ALUNO,
            )
            guardian = guardians[index % len(guardians)] if age < 18 else None
            student = Student.objects.create(
                user=user,
                guardian=guardian,
                nickname=first.split()[0] if rng.random() > 0.6 else "",
                level=level,
                status=Student.Status.ATIVO,
                position=position,
                joined_at=today - timedelta(days=rng.randint(60, 420)),
            )
            days_ago = rng.choice([2, 4, 7, 12, 18, 25, 40, 70, 120, 200, 300])
            enrollment = Enrollment.objects.create(
                student=student,
                class_group=groups[group_index],
                plan=plans[0],
                status=Enrollment.Status.ATIVA,
                monthly_fee=plans[0].monthly_fee,
                start_date=student.joined_at,
                approved_by=admin,
            )
            # enrolled_at/approved_at são auto_now_add: ajusta depois para o histórico ficar crível.
            Enrollment.objects.filter(pk=enrollment.pk).update(
                enrolled_at=timezone.now() - timedelta(days=days_ago),
                approved_at=timezone.now() - timedelta(days=days_ago - 1),
            )
            students.append(student)

        # ----------------------------------------------------------- treinos
        past_start = today - timedelta(days=8 * 7)
        future_end = today + timedelta(days=4 * 7)

        for group in groups:
            for slot in group.slots.all():
                cursor = past_start
                while cursor <= future_end:
                    if cursor.weekday() == slot.weekday:
                        is_past = cursor < today
                        canceled = rng.random() < 0.035 and is_past
                        session = Session.objects.create(
                            class_group=group,
                            date=cursor,
                            start_time=slot.start_time,
                            end_time=slot.end_time,
                            venue=slot.venue,
                            theme=rng.choice(
                                [
                                    "Saque e recepção",
                                    "Manchete e deslocamento",
                                    "Levantamento e ataque",
                                    "Bloqueio na areia",
                                    "Jogo reduzido e leitura",
                                    "Fundamentos + condicionamento",
                                    "Treino tático de dupla",
                                ]
                            ),
                            status=Session.Status.CANCELADO
                            if canceled
                            else (Session.Status.REALIZADO if is_past else Session.Status.AGENDADO),
                            canceled_reason="Chuva forte na areia" if canceled else "",
                        )
                        if is_past:
                            roster = [
                                s
                                for s in students
                                if s.enrollments.filter(status="ativa", class_group=group).exists()
                            ]
                            session_entry_ids = []
                            if not canceled:
                                for student in roster:
                                    roll = rng.random()
                                    if roll < 0.80:
                                        status = Attendance.Status.PRESENTE
                                    elif roll < 0.90:
                                        status = Attendance.Status.ATRASO
                                    elif roll < 0.97:
                                        status = Attendance.Status.FALTA
                                    else:
                                        status = Attendance.Status.JUSTIFICADA
                                    Attendance.objects.create(
                                        session=session,
                                        student=student,
                                        status=status,
                                        recorded_by=group.professor,
                                    )
                                    if status in (Attendance.Status.PRESENTE, Attendance.Status.ATRASO):
                                        entry = PointEntry.objects.create(
                                            student=student,
                                            points=rules["presenca"].points,
                                            reason=f"Presença no treino de {cursor:%d/%m}",
                                            rule=rules["presenca"],
                                            session=session,
                                            source=PointEntry.Source.PRESENCA,
                                            created_by=group.professor,
                                        )
                                        session_entry_ids.append(entry.pk)
                                if session_entry_ids:
                                    started_at = timezone.make_aware(datetime.combine(cursor, slot.start_time))
                                    PointEntry.objects.filter(id__in=session_entry_ids).update(created_at=started_at)
                    cursor += timedelta(days=1)

        # pontos de desempenho
        for student in students:
            for _ in range(rng.randint(2, 6)):
                rule = rng.choice([rules["destaque"], rules["evolucao"], rules["evento"], rules["ajuste"]])
                when = timezone.now() - timedelta(days=rng.randint(0, 55))
                entry = PointEntry.objects.create(
                    student=student,
                    points=rule.points,
                    reason=rule.name,
                    rule=rule,
                    source=PointEntry.Source.DESEMPENHO
                    if rule in (rules["destaque"], rules["evolucao"])
                    else PointEntry.Source.EVENTO
                    if rule == rules["evento"]
                    else PointEntry.Source.AJUSTE,
                    created_by=admin,
                )
                PointEntry.objects.filter(pk=entry.pk).update(created_at=when)

        # ----------------------------------------------------------- mensalidades
        def month_start(reference: date, offset: int) -> date:
            year = reference.year + (reference.month - 1 + offset) // 12
            month = (reference.month - 1 + offset) % 12 + 1
            return date(year, month, 1)

        for offset in (-2, -1, 0, 1):
            competence = month_start(today, offset)
            for student in students:
                enrollment = student.enrollments.filter(status="ativa").select_related("plan").first()
                if not enrollment:
                    continue
                due = due_date_for(competence, enrollment.plan.due_day)
                invoice = Invoice.objects.create(
                    student=student,
                    plan=enrollment.plan,
                    competence=competence,
                    amount=enrollment.monthly_fee,
                    due_date=due,
                )
                if offset == 1:
                    continue
                pay_chance = {2: 0.95, 1: 0.9, 0: 0.72}[abs(offset)]
                if rng.random() < pay_chance:
                    paid_day = min(due + timedelta(days=rng.randint(-6, 4)), today)
                    invoice.mark_paid(
                        user=admin,
                        method=rng.choice(["pix", "pix", "pix", "dinheiro", "cartao"]),
                        paid_at=paid_day,
                    )

        # ----------------------------------------------------------- comunicados
        for index, item in enumerate(ANNOUNCEMENTS):
            Announcement.objects.create(
                author=admin,
                published_at=timezone.now() - timedelta(days=index * 4 + 1),
                **item,
            )

        self.stdout.write(self.style.SUCCESS("Dados de demonstração criados."))
        self.stdout.write("")
        self.stdout.write("  Administração : farias@teamfarias.com.br / " + PASSWORD)
        self.stdout.write("  Professora    : marina@teamfarias.com.br / " + PASSWORD)
        self.stdout.write("  Aluna         : ana.almeida@aluno.teamfarias.com.br / " + PASSWORD)
        self.stdout.write("")
        self.stdout.write(
            f"  {len(students)} alunos ativos, "
            f"{Session.objects.count()} treinos, {Invoice.objects.count()} mensalidades."
        )
