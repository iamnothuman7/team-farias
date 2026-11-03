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

    def test_home_lists_only_public_news(self):
        Announcement.objects.create(title="Notícia pública", body="Corpo", audience=Announcement.Audience.PUBLICO)
        Announcement.objects.create(title="Aviso interno", body="Corpo", audience=Announcement.Audience.INTERNO)
        response = self.client.get(reverse("core:home"))
        self.assertContains(response, "Notícia pública")
        self.assertNotContains(response, "Aviso interno")

    def test_news_detail_hidden_for_internal_audience(self):
        internal = Announcement.objects.create(
            title="Reunião interna", body="Pauta", audience=Announcement.Audience.INTERNO
        )
        response = self.client.get(internal.get_absolute_url())
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
