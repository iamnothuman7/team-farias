"""Captura telas do projeto para revisÃ£o visual.

Uso:
    python scripts/shoot.py                 # todas as telas principais
    python scripts/shoot.py home            # apenas um grupo
"""

from __future__ import annotations

import sys
from pathlib import Path

from playwright.sync_api import sync_playwright

BASE = "http://127.0.0.1:8000"
OUT = Path(".preview")
OUT.mkdir(exist_ok=True)

STUDENT = ("ana.almeida@aluno.teamfarias.com.br", "teamfarias123")
ADMIN = ("farias@teamfarias.com.br", "teamfarias123")


def login(page, credentials):
    page.goto(f"{BASE}/entrar/", wait_until="networkidle")
    page.fill("#id_username", credentials[0])
    page.fill("#id_password", credentials[1])
    page.click("button[type=submit]")
    page.wait_for_load_state("networkidle")


def shoot(page, name, path, full=True):
    page.goto(f"{BASE}{path}", wait_until="networkidle")
    page.wait_for_timeout(700)
    page.screenshot(path=str(OUT / f"{name}.png"), full_page=full)
    print(f"  ok {name}")


def main():
    only = sys.argv[1] if len(sys.argv) > 1 else "all"
    errors: list[str] = []

    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)

        # ---------------------------------------------------- desktop pÃºblico
        if only in ("all", "site"):
            ctx = browser.new_context(viewport={"width": 1440, "height": 960}, reduced_motion="reduce", device_scale_factor=1)
            page = ctx.new_page()
            page.on("console", lambda m: errors.append(f"console {m.type}: {m.text}") if m.type == "error" else None)
            page.on("response", lambda r: errors.append(f"http {r.status} {r.url}") if r.status >= 500 else None)
            shoot(page, "01-home-desktop", "/")
            shoot(page, "02-noticias", "/noticias/")
            shoot(page, "03-matricula", "/matricula/")
            shoot(page, "04-login", "/entrar/", full=False)
            ctx.close()

            # ---------------------------------------------------- mobile pÃºblico
            ctx = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True, reduced_motion="reduce")
            page = ctx.new_page()
            page.on("response", lambda r: errors.append(f"http {r.status} {r.url}") if r.status >= 500 else None)
            shoot(page, "05-home-mobile", "/")
            shoot(page, "06-matricula-mobile", "/matricula/")
            ctx.close()

        # ---------------------------------------------------- aluno
        if only in ("all", "app"):
            ctx = browser.new_context(viewport={"width": 1440, "height": 960}, reduced_motion="reduce")
            page = ctx.new_page()
            page.on("response", lambda r: errors.append(f"http {r.status} {r.url}") if r.status >= 500 else None)
            login(page, STUDENT)
            shoot(page, "10-aluno-home", "/app/")
            shoot(page, "11-aluno-pontos", "/app/pontos/")
            shoot(page, "12-aluno-agenda", "/app/agenda/")
            shoot(page, "13-aluno-mensalidades", "/app/mensalidades/")
            shoot(page, "14-aluno-perfil", "/app/perfil/")
            ctx.close()

            ctx = browser.new_context(viewport={"width": 390, "height": 844}, device_scale_factor=2, is_mobile=True, has_touch=True, reduced_motion="reduce")
            page = ctx.new_page()
            login(page, STUDENT)
            shoot(page, "15-aluno-home-mobile", "/app/")
            shoot(page, "16-aluno-agenda-mobile", "/app/agenda/")
            ctx.close()

        # ---------------------------------------------------- painel
        if only in ("all", "admin"):
            ctx = browser.new_context(viewport={"width": 1440, "height": 1000}, reduced_motion="reduce")
            page = ctx.new_page()
            page.on("console", lambda m: errors.append(f"console {m.type}: {m.text}") if m.type == "error" else None)
            page.on("response", lambda r: errors.append(f"http {r.status} {r.url}") if r.status >= 500 else None)
            login(page, ADMIN)
            shoot(page, "20-painel-home", "/painel/")
            shoot(page, "21-painel-matriculas", "/painel/matriculas/")
            shoot(page, "22-painel-alunos", "/painel/alunos/")
            shoot(page, "23-painel-turmas", "/painel/turmas/")
            shoot(page, "24-painel-agenda", "/painel/agenda/")
            shoot(page, "25-painel-pontos", "/painel/pontos/")
            shoot(page, "26-painel-financeiro", "/painel/financeiro/")
            shoot(page, "27-painel-comunicados", "/painel/comunicados/")
            shoot(page, "28-painel-relatorios", "/painel/relatorios/")
            ctx.close()

        browser.close()

    if errors:
        print("\nERROS:")
        for error in dict.fromkeys(errors):
            print(" -", error)
    else:
        print("\nSem erros de console/500.")


if __name__ == "__main__":
    main()

