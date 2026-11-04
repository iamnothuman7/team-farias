from __future__ import annotations

import json
from datetime import date, timedelta

from django.contrib.staticfiles import finders
from django.test import TestCase
from django.urls import reverse

from accounts.models import Student, User
from school.models import Announcement, Enrollment

from .testing import make_group, make_plan


class PublicPagesTests(TestCase):
    def setUp(self):
        self.plan = make_plan()
        self.group = make_group()

    def test_home_renders_site_sections(self):
        response = self.client.get(reverse("core:home"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "A escolinha organizada.")
        self.assertContains(response, self.group.name)

    def test_home_never_lists_announcements(self):
        Announcement.objects.create(title="Notícia pública", body="Corpo", audience=Announcement.Audience.ALUNOS)
        Announcement.objects.create(title="Aviso interno", body="Corpo", audience=Announcement.Audience.INTERNO)
        response = self.client.get(reverse("core:home"))
        self.assertNotContains(response, "Notícia pública")
        self.assertNotContains(response, "Aviso interno")

    def test_news_detail_hidden_for_internal_audience(self):
        internal = Announcement.objects.create(
            title="Reunião interna", body="Pauta", audience=Announcement.Audience.INTERNO
        )
        response = self.client.get(reverse("core:news_detail", args=[internal.slug]))
        self.assertEqual(response.status_code, 404)

    def test_privacy_and_offline_pages(self):
        self.assertEqual(self.client.get(reverse("core:privacy")).status_code, 200)
        self.assertEqual(self.client.get(reverse("core:offline")).status_code, 200)

    def test_service_worker_headers(self):
        response = self.client.get("/sw.js")
        self.assertEqual(response.status_code, 200)
        self.assertIn("javascript", response["Content-Type"])
        self.assertEqual(response["Service-Worker-Allowed"], "/")
        self.assertContains(response, "tf-static")

    def test_login_page_uses_email_field(self):
        response = self.client.get(reverse("accounts:login"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'type="email"')

    def test_health_checks_database_without_caching(self):
        response = self.client.get("/health/")
        self.assertEqual(response.content, b"ok")
        self.assertIn("no-store", response["Cache-Control"])

    def test_health_returns_503_without_database_details(self):
        from unittest.mock import patch
        from django.db import DatabaseError
        with patch("core.views.connection.cursor", side_effect=DatabaseError("private connection details")):
            response = self.client.get("/health/")
        self.assertEqual(response.status_code, 503)
        self.assertEqual(response.content, b"unavailable")


class PublicEnrollmentRemovedTests(TestCase):
    def test_enroll_url_redirects_to_contact_section(self):
        response = self.client.get(reverse("core:enroll"))
        self.assertEqual(response.status_code, 302)
        self.assertTrue(response["Location"].endswith("/#contato"))

    def test_old_success_url_redirects(self):
        response = self.client.get(reverse("core:enroll_success"))
        self.assertEqual(response.status_code, 302)

    def test_home_has_no_public_enrollment_form(self):
        response = self.client.get(reverse("core:home"))
        self.assertNotContains(response, "password_confirm")
        self.assertNotContains(response, "Enviar matrícula")
        self.assertContains(response, "WhatsApp")

    def test_home_cta_points_to_whatsapp(self):
        response = self.client.get(reverse("core:home"))
        self.assertContains(response, "wa.me/")


class PwaTests(TestCase):
    def test_manifest_has_install_essentials(self):
        path = finders.find("manifest.webmanifest")
        self.assertIsNotNone(path)
        with open(path, encoding="utf-8") as handle:
            manifest = json.load(handle)

        self.assertEqual(manifest["display"], "standalone")
        self.assertTrue(manifest["start_url"].startswith("/app/"))
        sizes = {icon["sizes"] for icon in manifest["icons"]}
        self.assertIn("192x192", sizes)
        self.assertIn("512x512", sizes)
        self.assertTrue(any(icon.get("purpose") == "maskable" for icon in manifest["icons"]))
        self.assertGreaterEqual(len(manifest["screenshots"]), 2)

    def test_pages_expose_ios_meta_and_install_dialog(self):
        for url in ["/", "/entrar/"]:
            response = self.client.get(url)
            self.assertContains(response, "apple-mobile-web-app-capable")
            self.assertContains(response, "apple-touch-startup-image")
            self.assertContains(response, "manifest.webmanifest")
            self.assertContains(response, "install-dialog")


class ConfigurationTests(TestCase):
    def setUp(self):
        from .models import SiteConfiguration
        from .testing import make_admin
        self.config = SiteConfiguration.objects.create()
        self.admin = make_admin()

    def test_confirmed_contacts_and_private_prices(self):
        make_plan(fee="987.65")
        response = self.client.get("/")
        for expected in ["5588992671163", "teamfarias_", "Tianguá", "Seu plano de treino", "Valores sob consulta"]:
            self.assertContains(response, expected)
        for removed in ["987", "R$", "Fortaleza", "Beira-Mar", "mailto:", "Ana Sofia", "contato@teamfarias"]:
            self.assertNotContains(response, removed)
        self.assertContains(self.client.get("/entrar/"), "wa.me/5588992671163")

    def test_settings_requires_admin(self):
        from .testing import make_professor, make_student
        self.assertEqual(self.client.get("/painel/configuracoes/").status_code, 302)
        for user in [make_professor(), make_student().user]:
            self.client.force_login(user)
            self.assertEqual(self.client.get("/painel/configuracoes/").status_code, 403)
            self.assertEqual(self.client.post("/painel/configuracoes/", {"action": "site", "name": "Alterado"}).status_code, 403)
        self.config.refresh_from_db()
        self.assertEqual(self.config.name, "Team Farias")

    def test_settings_fields_have_unique_ids(self):
        import re
        self.client.force_login(self.admin)
        response = self.client.get("/painel/configuracoes/")
        ids = re.findall(r'\bid="([^"]+)"', response.content.decode())
        self.assertEqual(len(ids), len(set(ids)))

    def test_settings_save_and_render_without_public_pix(self):
        from django.forms.models import model_to_dict
        self.client.force_login(self.admin)
        data = model_to_dict(self.config)
        data.update(action="site", hero_title="Treine com a gente", whatsapp="5588999999999", pix="chave-privada-teste")
        response = self.client.post("/painel/configuracoes/", data, HTTP_HX_REQUEST="true", follow=True)
        self.assertEqual(response.status_code, 200)
        self.client.logout()
        response = self.client.get("/")
        self.assertContains(response, "Treine com a gente")
        self.assertContains(response, "5588999999999")
        self.assertNotContains(response, "chave-privada-teste")

    def test_settings_validation_and_sections(self):
        from dashboard.forms import SiteConfigurationForm
        from django.forms.models import model_to_dict
        data = model_to_dict(self.config)
        data.update(whatsapp="javascript:alert(1)", accent_color="red;display:none", logo_url="http://example.com/image.png")
        form = SiteConfigurationForm(data, instance=self.config)
        self.assertFalse(form.is_valid())
        self.assertTrue({"whatsapp", "accent_color", "logo_url"}.issubset(form.errors))
        self.config.show_groups = False
        self.config.show_news = False
        self.config.save()
        response = self.client.get("/")
        self.assertNotContains(response, 'id="turmas"')
        self.assertNotContains(response, 'id="noticias"')
        self.assertContains(response, 'id="plano"')

    def test_single_plan_preserves_enrollment_fee(self):
        from .testing import make_student
        from billing.models import Plan
        plan = make_plan()
        student = make_student(group=make_group(), plan=plan)
        self.client.force_login(self.admin)
        response = self.client.post(f"/painel/planos/{plan.pk}/editar/", {"is_active": "on", "name": "Plano único", "description": "", "monthly_fee": "250.00", "due_day": "10", "sessions_per_week": "2"})
        self.assertEqual(response.status_code, 302)
        self.assertEqual(Plan.objects.filter(is_active=True).count(), 1)
        self.assertEqual(str(student.active_enrollment.monthly_fee), "180.00")
        plan.refresh_from_db()
        self.assertEqual(str(plan.monthly_fee), "250.00")

    def test_database_accepts_multiple_active_plans(self):
        from billing.models import Plan
        make_plan()
        make_plan(name="Segundo plano")
        self.assertEqual(Plan.objects.filter(is_active=True).count(), 2)

    def test_private_cache_and_htmx_redirect_url(self):
        response = self.client.get("/", HTTP_HX_BOOSTED="true")
        self.assertIn("no-store", response["Cache-Control"])
        self.assertEqual(response["HX-Push-Url"], "/")
        self.client.force_login(self.admin)
        response = self.client.get("/inicio/", HTTP_HX_BOOSTED="true", follow=True)
        self.assertEqual(response["HX-Push-Url"], "/painel/")

    def test_seed_is_blocked_in_production(self):
        from django.core.management import call_command, CommandError
        with self.settings(DEBUG=False), self.assertRaises(CommandError):
            call_command("seed_demo", reset=True)


class DeploymentSettingsTests(TestCase):
    def test_https_security_headers_block_external_scripts_and_upgrade_http(self):
        response = self.client.get("/", secure=True)
        policy = response["Content-Security-Policy"]
        self.assertIn("script-src 'self'", policy)
        self.assertNotIn("'unsafe-eval'", policy)
        self.assertIn("form-action 'self'", policy)
        self.assertIn("object-src 'none'", policy)
        self.assertIn("upgrade-insecure-requests", policy)
        self.assertIn("camera=()", response["Permissions-Policy"])
        self.assertNotContains(response, "<script>")
        self.assertContains(response, '"allowEval": false')

    def test_local_http_does_not_force_resource_upgrade(self):
        response = self.client.get("/")
        self.assertNotIn("upgrade-insecure-requests", response["Content-Security-Policy"])

    def test_manifest_keeps_app_identity_and_declares_own_installation(self):
        response = self.client.get("/manifest.webmanifest", secure=True)
        self.assertEqual(response.status_code, 200)
        data = json.loads(response.content)
        self.assertEqual(data["id"], "/app/")
        self.assertEqual(data["scope"], "/")
        self.assertEqual(data["related_applications"], [{"platform": "webapp", "url": "/manifest.webmanifest", "id": "https://testserver/app/"}])
        self.assertIn("no-store", response["Cache-Control"])

    def test_shared_paths_and_hsts_can_be_configured(self):
        import json
        import os
        import subprocess
        import sys
        env = os.environ.copy()
        env.update(DJANGO_DEBUG="0", DJANGO_SECRET_KEY="test-only-" + "x" * 64,
                   DJANGO_DB_ENGINE="postgresql", DJANGO_STATIC_ROOT="/srv/teamfarias/static",
                   DJANGO_MEDIA_ROOT="/srv/teamfarias/media", DJANGO_HSTS_SECONDS="0",
                   DJANGO_HSTS_INCLUDE_SUBDOMAINS="0", DJANGO_HSTS_PRELOAD="0")
        script = "import json; from teamfarias import settings as s; print(json.dumps([str(s.STATIC_ROOT).replace(chr(92), '/'), str(s.MEDIA_ROOT).replace(chr(92), '/'), s.SECURE_HSTS_SECONDS, s.SECURE_HSTS_INCLUDE_SUBDOMAINS, s.SECURE_HSTS_PRELOAD]))"
        values = json.loads(subprocess.check_output([sys.executable, "-c", script], env=env, text=True))
        self.assertEqual(values, ["/srv/teamfarias/static", "/srv/teamfarias/media", 0, False, False])
