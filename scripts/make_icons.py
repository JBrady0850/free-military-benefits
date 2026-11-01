"""Build the app icons (navy field, gold star, gold rule) for the web app manifest and home screens.
Run once after a design change: python scripts/make_icons.py  (needs Pillow)."""
import math
from pathlib import Path

from PIL import Image, ImageDraw

SITE = Path(__file__).resolve().parents[1] / "site"
NAVY, GOLD = (15, 39, 68, 255), (212, 160, 23, 255)


def star(draw: ImageDraw.ImageDraw, cx: float, cy: float, r: float) -> None:
    pts = []
    for i in range(10):
        ang = -math.pi / 2 + i * math.pi / 5
        rad = r if i % 2 == 0 else r * 0.40
        pts.append((cx + rad * math.cos(ang), cy + rad * math.sin(ang)))
    draw.polygon(pts, fill=GOLD)


def icon(size: int, star_frac: float, rounded: bool) -> Image.Image:
    scale = 4  # draw large, shrink for smooth edges
    s = size * scale
    img = Image.new("RGBA", (s, s), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    if rounded:
        d.rounded_rectangle([0, 0, s - 1, s - 1], radius=int(s * 0.18), fill=NAVY)
    else:
        d.rectangle([0, 0, s, s], fill=NAVY)
    star(d, s / 2, s * 0.47, s * star_frac)
    bar_w, bar_h = s * star_frac * 1.5, max(scale * 2, s * 0.035)
    d.rectangle([s / 2 - bar_w / 2, s * 0.47 + s * star_frac * 1.02, s / 2 + bar_w / 2, s * 0.47 + s * star_frac * 1.02 + bar_h], fill=GOLD)
    return img.resize((size, size), Image.LANCZOS)


def main() -> None:
    icon(192, 0.30, True).save(SITE / "icon-192.png")
    icon(512, 0.30, True).save(SITE / "icon-512.png")
    icon(512, 0.22, False).save(SITE / "icon-maskable-512.png")  # star inside the 80 percent safe zone
    icon(180, 0.28, False).save(SITE / "apple-touch-icon.png")    # iOS rounds the corners itself
    icon(32, 0.34, True).save(SITE / "favicon-32.png")
    for name in ("icon-192.png", "icon-512.png", "icon-maskable-512.png", "apple-touch-icon.png", "favicon-32.png"):
        print(name, (SITE / name).stat().st_size, "bytes")


if __name__ == "__main__":
    main()
