"""Gera a imagem de compartilhamento (Open Graph) do site."""

from pathlib import Path

from playwright.sync_api import sync_playwright

HTML = """
<!doctype html>
<html lang="pt-BR">
<head>
<meta charset="utf-8">
<style>
  @font-face {
    font-family: "Archivo";
    src: url("http://127.0.0.1:8000/static/fonts/archivo-latin.woff2") format("woff2");
    font-weight: 100 900;
    font-style: normal;
    font-stretch: 62% 125%;
  }
  @font-face {
    font-family: "Archivo";
    src: url("http://127.0.0.1:8000/static/fonts/archivo-it-latin.woff2") format("woff2");
    font-weight: 100 900;
    font-style: italic;
    font-stretch: 62% 125%;
  }
  @font-face {
    font-family: "Jakarta";
    src: url("http://127.0.0.1:8000/static/fonts/jakarta-latin.woff2") format("woff2");
    font-weight: 400 800;
  }
  * { box-sizing: border-box; margin: 0; }
  body {
    width: 1200px; height: 630px; overflow: hidden;
    background:
      radial-gradient(900px 600px at 88% 8%, rgba(139, 47, 224, .45), transparent 62%),
      radial-gradient(700px 500px at 6% 96%, rgba(84, 20, 150, .38), transparent 65%),
      #07010e;
    color: #f5efff; font-family: "Jakarta", sans-serif;
    display: grid; grid-template-columns: 1.05fr .95fr; align-items: center;
    padding: 64px 72px; position: relative;
  }
  .lines {
    position: absolute; inset: 0;
    background-image:
      linear-gradient(rgba(255,255,255,.05) 1px, transparent 1px),
      linear-gradient(90deg, rgba(255,255,255,.05) 1px, transparent 1px);
    background-size: 72px 72px;
    mask-image: radial-gradient(circle at 70% 45%, #000 10%, transparent 72%);
  }
  .eyebrow {
    font-size: 15px; letter-spacing: .24em; text-transform: uppercase;
    color: #bd93ff; font-weight: 700; display: flex; align-items: center; gap: 10px;
  }
  .dot { width: 8px; height: 8px; border-radius: 50%; background: #52e0a0; box-shadow: 0 0 0 5px rgba(82,224,160,.16); }
  h1 {
    font-family: "Archivo", sans-serif; font-weight: 800; font-stretch: 98%;
    font-size: 62px; line-height: .98; letter-spacing: -.035em; margin: 22px 0 0;
  }
  h1 em {
    font-style: italic;
    background: linear-gradient(100deg, #fff 0%, #e6d4ff 40%, #b884ff 100%);
    -webkit-background-clip: text; background-clip: text; color: transparent;
  }
  .lead { margin-top: 22px; font-size: 20px; line-height: 1.5; color: #a899c2; max-width: 30ch; }
  .meta { position: absolute; left: 72px; bottom: 54px; display: flex; gap: 26px; font-size: 15px; color: #7d6f96; }
  .meta b { color: #dcc4ff; font-weight: 600; }
  .brand { font-family: "Archivo", sans-serif; font-weight: 850; letter-spacing: .04em; font-size: 15px; color: #fff; margin-top: 34px; }
  .brand span { color: #7d6f96; display: block; letter-spacing: .3em; font-size: 10px; margin-top: 4px; font-family: "Jakarta"; }
  .crest { position: relative; display: grid; place-items: center; }
  .crest::before {
    content: ""; position: absolute; width: 520px; height: 520px; border-radius: 50%;
    background: radial-gradient(circle, rgba(164,92,255,.5), transparent 65%); filter: blur(20px);
  }
  .crest img { position: relative; width: 560px; filter: drop-shadow(0 30px 60px rgba(0,0,0,.55)); }
  .ring { position: absolute; width: 500px; height: 500px; border: 1px dashed rgba(255,255,255,.14); border-radius: 50%; }
</style>
</head>
<body>
  <div class="lines"></div>
  <div>
    <div class="eyebrow"><span class="dot"></span> Escolinha de vôlei de praia</div>
    <h1>A escolinha<br>organizada.<br><em>O time mais<br>conectado.</em></h1>
    <p class="lead">Matrícula, treinos, pontos e mensalidades em um só lugar.</p>
  </div>
  <div class="crest">
    <span class="ring"></span>
    <img src="http://127.0.0.1:8000/static/img/logo.png" alt="">
  </div>
  <div class="meta"><span><b>Team Farias</b> · Vôlei de Praia</span><span>Fortaleza/CE</span><span>Matrícula on-line</span></div>
</body>
</html>
"""


def main() -> None:
    out = Path("static/img/og-image.png")
    with sync_playwright() as p:
        browser = p.chromium.launch(channel="chrome", headless=True)
        page = browser.new_page(viewport={"width": 1200, "height": 630}, device_scale_factor=1)
        page.set_content(HTML, wait_until="networkidle")
        page.evaluate("document.fonts.ready")
        page.wait_for_timeout(400)
        page.screenshot(path=str(out))
        browser.close()
    print(f"ok {out} ({out.stat().st_size} bytes)")


if __name__ == "__main__":
    main()
