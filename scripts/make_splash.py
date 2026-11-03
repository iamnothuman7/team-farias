"""Gera as imagens de abertura (splash) do PWA para iPhone e iPad."""

from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

OUT = Path("static/img/splash")
OUT.mkdir(parents=True, exist_ok=True)

# (largura, altura, css_width, css_height, dpr)
SIZES = [
    (1290, 2796, 430, 932, 3),   # iPhone 15/14 Pro Max
    (1179, 2556, 393, 852, 3),   # iPhone 15/14 Pro
    (1170, 2532, 390, 844, 3),   # iPhone 14/13/12
    (1284, 2778, 428, 926, 3),   # iPhone 13/12 Pro Max
    (1125, 2436, 375, 812, 3),   # iPhone X/XS/11 Pro
    (1242, 2688, 414, 896, 3),   # iPhone XS Max/11 Pro Max
    (828, 1792, 414, 896, 2),    # iPhone XR/11
    (750, 1334, 375, 667, 2),    # iPhone SE/8
    (1242, 2208, 414, 736, 3),   # iPhone 8 Plus
    (1668, 2388, 834, 1194, 2),  # iPad Pro 11"
    (2048, 2732, 1024, 1366, 2), # iPad Pro 12.9"
]

LOGO = Image.open("static/img/logo.png").convert("RGBA")
BASE = (7, 1, 14)


def build(width: int, height: int) -> Image.Image:
    canvas = Image.new("RGB", (width, height), BASE)
    # brilho radial central
    glow = Image.new("RGB", (width, height), BASE)
    draw = ImageDraw.Draw(glow)
    radius = int(min(width, height) * 0.36)
    cx, cy = width // 2, int(height * 0.47)
    draw.ellipse([cx - radius, cy - radius, cx + radius, cy + radius], fill=(62, 16, 108))
    glow = glow.filter(ImageFilter.GaussianBlur(int(min(width, height) * 0.10)))
    canvas = Image.blend(canvas, glow, 0.55)

    # emblema central
    logo_w = int(width * (0.52 if width < height else 0.42))
    logo_h = int(logo_w * LOGO.height / LOGO.width)
    logo = LOGO.resize((logo_w, logo_h), Image.LANCZOS)
    canvas.paste(logo, ((width - logo_w) // 2, (height - logo_h) // 2), logo)

    return canvas


def main() -> None:
    for index, (width, height, css_w, css_h, dpr) in enumerate(SIZES):
        name = f"apple-splash-{css_w}x{css_h}@{dpr}x.png"
        build(width, height).save(OUT / name, optimize=True)
        print(name, f"{width}x{height}", f"dpr {dpr}")
    print("ok", len(SIZES), "splashes")


if __name__ == "__main__":
    main()
