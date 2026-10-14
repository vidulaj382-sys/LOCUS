"""Render the LOCUS logo (same geometry as the header SVG) to PNG icons for the PWA manifests."""
import pathlib
from PIL import Image, ImageDraw

OUT = pathlib.Path(__file__).resolve().parent.parent / 'icons'
S = 1024


def gradient(size):
    a, b = (0x22, 0xC3, 0xE6), (0x10, 0xB9, 0x81)
    g = Image.new('RGB', (size, size))
    px = g.load()
    for y in range(size):
        for x in range(size):
            t = (x + y) / (2 * (size - 1))
            px[x, y] = tuple(round(a[i] + (b[i] - a[i]) * t) for i in range(3))
    return g


def mark(d, scale, off, k=1.0):
    """draw the 40x40 logo mark (ring, 4 ticks, centre dot) scaled by `scale`, offset (px)"""
    u = lambda v: off + v * scale
    w = 2.6 * scale * k
    r = 9 * scale
    d.ellipse([u(20) - r, u(20) - r, u(20) + r, u(20) + r], outline='white', width=round(w))
    for x1, y1, x2, y2 in ((20, 6, 20, 13), (20, 27, 20, 34), (6, 20, 13, 20), (27, 20, 34, 20)):
        d.line([u(x1), u(y1), u(x2), u(y2)], fill='white', width=round(w))
        for cx, cy in ((x1, y1), (x2, y2)):
            d.ellipse([u(cx) - w / 2, u(cy) - w / 2, u(cx) + w / 2, u(cy) + w / 2], fill='white')
    r3 = 3 * scale
    d.ellipse([u(20) - r3, u(20) - r3, u(20) + r3, u(20) + r3], fill='white')


def icon(maskable=False, square=False):
    bg = gradient(S)
    d = ImageDraw.Draw(bg)
    if maskable:                      # full-bleed, mark kept inside the central 60% safe zone
        sc = S * 0.60 / 40
        mark(d, sc, (S - 40 * sc) / 2)
        return bg.convert('RGBA')
    sc = S / 40
    mark(d, sc, 0)
    img = bg.convert('RGBA')
    if not square:
        m = Image.new('L', (S, S), 0)
        ImageDraw.Draw(m).rounded_rectangle([0, 0, S - 1, S - 1], radius=int(S * 12 / 40), fill=255)
        img.putalpha(m)
    return img


for name, img, sizes in (('icon', icon(), (192, 512)), ('maskable', icon(maskable=True), (512,)), ('apple-touch-icon', icon(square=True), (180,)), ('favicon', icon(), (32,))):
    for s in sizes:
        fn = OUT / (f'{name}.png' if name in ('apple-touch-icon', 'favicon') else f'{name}-{s}.png')
        img.resize((s, s), Image.LANCZOS).save(fn)
        print('wrote', fn.name)
