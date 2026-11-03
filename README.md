# Team Farias — Site + Sistema de Gestão

Plataforma web (site + área do aluno + painel da equipe) para a escolinha de vôlei de praia **Team Farias**, construída em **Python + Django** a partir da proposta comercial.

> A escolinha organizada. O time mais conectado.

---

## O que está pronto

Cada entrega da proposta foi implementada no código:

| Entrega da proposta | Onde está |
| --- | --- |
| Site responsivo, instalável (PWA) | `core` + `static/manifest.webmanifest` + `templates/core/sw.js` |
| Matrícula on-line com aprovação da equipe | `core/forms.py` (`EnrollmentForm`) e `dashboard/views.py` (`painel_enrollments`) |
| Área do aluno com login individual | `templates/app/*` e views `app_*` |
| Meu perfil, turma e matrícula | `templates/app/profile.html` |
| Pontos, histórico e ranking | `dashboard/services.py` (`ranking`) + `templates/app/points.html` |
| Calendário de treinos e presenças | `month_calendar` + `templates/app/agenda.html` |
| Mensalidades, status e histórico | app `billing` + `templates/app/invoices.html` |
| Notícias e recados | modelo `Announcement` (público, alunos, interno) |
| Painel da equipe com níveis de acesso | `dashboard/decorators.py` (`staff_required`, `team_required`, `student_required`) |
| Cadastro de alunos, responsáveis e turmas | apps `accounts` e `school` |
| Agenda de aulas e registro de presença | modelo `Session` / `Attendance` + `painel_attendance` |
| Lançamento de pontos com regras e histórico | `PointRule` / `PointEntry` |
| Controle de mensalidades com baixa administrativa | `Invoice` / `Payment` |
| Comunicados para alunos e responsáveis | `templates/painel/announcement_form.html` |
| Resumo gerencial | `templates/painel/home.html` e `templates/painel/reports.html` |

---

## Stack

- **Python 3.12** + **Django 5.2**
- **SQLite** em desenvolvimento (troca simples para PostgreSQL)
- Templates Django + CSS próprio (sem framework de UI) + **JavaScript vanilla**
- **HTMX 2** (self-hosted) para navegação, formulários e filtros sem recarregar a página
- **WhiteNoise** para arquivos estáticos em produção
- **PWA**: manifest, service worker, cache offline, atalhos, splash screens e convite de instalação automático
- Fontes self-hosted (Archivo + Plus Jakarta Sans) — o site não depende de CDN

---

## Como rodar

```bash
# 1. ambiente
python -m venv .venv
# Windows: .venv\Scripts\activate
# Linux/macOS: source .venv/bin/activate
pip install -r requirements.txt

# 2. configuração
copy .env.example .env      # Windows
cp .env.example .env        # Linux/macOS

# 3. banco + dados de demonstração
python manage.py migrate
python manage.py seed_demo

# 4. servidor
python manage.py runserver
```

Acesse **http://127.0.0.1:8000**.

> Para recriar os dados de demonstração do zero: `python manage.py seed_demo --reset`

### Contas de demonstração

| Perfil | E-mail | Senha |
| --- | --- | --- |
| Administração | `farias@teamfarias.com.br` | `teamfarias123` |
| Professora | `marina@teamfarias.com.br` | `teamfarias123` |
| Aluna | `ana.almeida@aluno.teamfarias.com.br` | `teamfarias123` |
| Superusuário Django | `farias@teamfarias.com.br` | `teamfarias123` |

O painel do Django fica em `/admin/`.

---

## Acessos e permissões

| Área | Administração | Professor(a) | Aluno(a) |
| --- | --- | --- | --- |
| Site público e notícias | ✅ | ✅ | ✅ |
| Área do aluno | — | — | ✅ (somente os próprios dados) |
| Visão geral | ✅ (todas as turmas) | ✅ (somente suas turmas) | ❌ |
| Matrículas (criar e gerenciar) | ✅ | ❌ | ❌ |
| Alunos e fichas | ✅ | ✅ (suas turmas) | ❌ |
| Turmas | ✅ (criar/editar) | ✅ (consulta) | ❌ |
| Agenda e presença | ✅ | ✅ (suas turmas) | ❌ |
| Pontuação | ✅ | ✅ | ❌ |
| Financeiro | ✅ | ❌ | ❌ |
| Comunicados e relatórios | ✅ | ❌ | ❌ |

Regras aplicadas no servidor (`dashboard/decorators.py` e checagens nas views), não apenas no menu.

---

## Estrutura do projeto

```
teamfarias/            settings, urls, wsgi
core/                  site público, notícias, PWA
  management/commands/seed_demo.py
accounts/              User por e-mail, Student, Guardian
school/                turmas, horários, treinos, presença, pontos, comunicados
billing/               planos, mensalidades, pagamentos
dashboard/             área do aluno + painel da equipe
  services.py          ranking, métricas, geração de treinos e mensalidades
templates/             base pública, base do sistema, app/, painel/, partials/
static/
  css/app.css          design system + site
  css/dashboard.css    shell e componentes do sistema
  js/app.js            menu, toasts, reveal, PWA, copiar Pix
  js/dashboard.js      drawer, presença em lote, modal de pagamento
  img/                 logo tratada, ícones PWA, favicons
  fonts/               Archivo + Plus Jakarta Sans (woff2)
scripts/shoot.py       captura de telas para revisão visual
```

---

## Identidade visual

A paleta foi extraída do emblema enviado (violeta profundo, lavanda e quase-preto arroxeado):

| Token | Cor | Uso |
| --- | --- | --- |
| `--ink-950` | `#06010D` | fundo do site |
| `--violet-600` | `#8B2FE0` | cor base do emblema / botões |
| `--violet-500` | `#A45CFF` | destaques e ícones |
| `--violet-300` | `#DCC4FF` | textos de apoio sobre fundo escuro |
| `--text` | `#F5EFFF` | texto principal |

Arquivos em `static/img/`: `logo.png`, `logo.webp`, `logo-sm.webp`, ícones 192/512, máscara Android, apple-touch e favicons. O original está preservado em `assets/brand/logo-team-farias.png`.

---

## Rotas principais

| Rota | Descrição |
| --- | --- |
| `/` | Site institucional (hero, sistema, turmas, planos, notícias, contato) |
| `/matricula/` | Inscrição on-line com criação de acesso |
| `/noticias/` e `/noticias/<slug>/` | Notícias e comunicados públicos |
| `/entrar/` e `/sair/` | Login por e-mail / logout |
| `/app/` | Início do aluno |
| `/app/agenda/`, `/app/pontos/`, `/app/mensalidades/`, `/app/perfil/`, `/app/comunicados/` | Área do aluno |
| `/painel/` | Visão geral da equipe |
| `/painel/matriculas/`, `/painel/alunos/`, `/painel/turmas/` | Gestão de pessoas e turmas |
| `/painel/agenda/` | Agenda semanal + presença por treino |
| `/painel/pontos/` | Lançamento individual/coletivo + regras |
| `/painel/financeiro/` | Mensalidades, baixa e reabertura |
| `/painel/relatorios/` | Ocupação, assiduidade e receita |
| `/sw.js`, `/offline/` | Service worker e fallback offline |

---

## PWA e uso no celular

- `manifest.webmanifest` com ícones 192/512, ícone maskable, atalhos e capturas de tela.
- Ícone e splash screens do iPhone gerados com a logo; favicons **sem fundo**.
- Service worker na raiz (`Service-Worker-Allowed: /`): cache de estáticos e páginas públicas, offline em `/offline/`; área logada e painel **nunca** são cacheados.
- **Convite de instalação automático** na primeira visita (some por 7 dias em “Agora não”), com instruções específicas para iPhone, Android e desktop.
- Layout com `env(safe-area-inset-*)`, alvos de toque maiores, campos de 16px (sem zoom no iOS) e tabelas em cartões.
- Em produção, **HTTPS** libera instalação completa no Android, cache offline e atualizações automáticas.

---

## Navegação sem recarregar (HTMX)

- `hx-boost` global no `<body>`: links internos, formulários, filtros, login, logout e ações do painel passam por AJAX.
- Barra de progresso no topo, View Transitions API (com respeito a `prefers-reduced-motion`) e troca de `<title>`/histórico automática.
- O `body` e o `<head>` são sincronizados a cada troca (classe do layout, `noindex`, descrição e canonical).
- Erros 403/404 são exibidos dentro da própria página; sem internet, o app cai no `/offline/`.
- Os scripts usam delegação e reinicialização após cada swap (menus, toasts, modais, presença, abas e instalação).
- **Sidebar retrátil** no desktop: rail de 84px que expande para 272px no hover/foco e sobrepõe o conteúdo sem deslocar a página. No mobile, o mesmo menu abre como drawer pelo botão do topo, com backdrop e fechamento por Esc, toque fora ou ao navegar.

---

## Testes

```bash
python manage.py test
```

51 testes cobrindo: páginas públicas, matrícula feita pela administração (duplicidade de e-mail, responsável, senha gerada, mensalidade automática), permissões por perfil, presença, pontuação individual/coletiva, baixa e reabertura de mensalidade, geração de cobranças, ranking, PWA e geração de treinos.

---

## Telas

| Celular (principal) | | |
| --- | --- | --- |
| ![Site no celular](screenshots/site-mobile.png) | ![Área do aluno no celular](screenshots/aluno-mobile.png) | ![Painel no celular](screenshots/painel-mobile.png) |
| Site institucional | Área do aluno | Painel da equipe |
| ![Instalação no iPhone](screenshots/instalar-iphone.png) | ![Login no celular](screenshots/login-mobile.png) | ![Alunos no celular](screenshots/alunos-mobile.png) |
| Instruções de instalação | Login | Alunos em cartões |

Desktop: [site](screenshots/site-desktop.png) · [painel](screenshots/painel.png) · [nova matrícula](screenshots/matricula-admin.png)

---

## Produção

1. Defina `DJANGO_DEBUG=0`, uma `DJANGO_SECRET_KEY` nova e `DJANGO_ALLOWED_HOSTS` com o domínio.
2. Rode `python manage.py collectstatic` (o manifesto com hash é ativado automaticamente fora do modo debug).
3. Sirva com Gunicorn atrás de Nginx:

```bash
gunicorn teamfarias.wsgi:application --bind 127.0.0.1:8000 --workers 3
```

4. HTTPS obrigatório (PWA, cookies seguros e `CSRF_TRUSTED_ORIGINS`).
5. Para PostgreSQL, troque o bloco `DATABASES` em `teamfarias/settings.py` por `django.db.backends.postgresql` com `psycopg[binary]`.

Checklist rápido: `python manage.py check --deploy`.

---

## Personalização

- **Contatos e endereço:** variáveis `SITE_*` no `.env` (telefone, WhatsApp com DDI, e-mail, Instagram, Pix).
- **Turmas e horários:** painel `/painel/turmas/`. Os treinos da agenda são gerados a partir dos horários fixos pelo botão **Gerar treinos**.
- **Planos e valores:** Django admin → Planos.
- **Regras de pontuação:** painel `/painel/pontos/` → Nova regra.
- **Logo:** substitua `static/img/logo.png` e `logo.webp` mantendo as proporções; os ícones PWA podem ser regerados a partir do original.

---

## Fora do escopo (conforme a proposta)

- Processamento automático de pagamentos (baixa é manual).
- Aplicativo nativo em loja (a entrega é PWA instalável).
- Domínio próprio, integrações pagas e mensagens por WhatsApp/SMS.
- Envio de e-mail transacional (o contato inicial é feito pela equipe).
- Renovações de infraestrutura são custos futuros, informados à parte.

---

## Próximos passos sugeridos

1. Validar textos, turmas, valores e contatos reais com o Team Farias.
2. Conectar um domínio e configurar HTTPS.
3. Avaliar e-mail transacional (recuperação de senha) e lembrete de mensalidade.
4. Migrar para PostgreSQL quando o volume de alunos crescer.
