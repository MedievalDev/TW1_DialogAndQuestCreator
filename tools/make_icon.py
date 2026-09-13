"""Draw the program icon (questforge2/assets/icon.png and icon.ico).

Own artwork, no game data: a dark rounded tile with a small gold node graph
(entry node, two dialog nodes, curved edges). Needs Pillow; the tool itself
does not.

    py -3.12 tools/make_icon.py
"""

import os

from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
OUT = os.path.join(os.path.dirname(HERE), 'questforge2', 'assets')

BG = (20, 17, 14, 255)
PANEL = (28, 24, 19, 255)
LINE = (53, 47, 38, 255)
GOLD = (210, 160, 68, 255)
GOLD_HI = (227, 180, 92, 255)
GREEN = (67, 181, 99, 255)
BLUE = (108, 160, 224, 255)


def bezier(p0, p1, p2, p3, steps=40):
    pts = []
    for i in range(steps + 1):
        t = i / steps
        u = 1 - t
        x = u ** 3 * p0[0] + 3 * u * u * t * p1[0] + 3 * u * t * t * p2[0] + t ** 3 * p3[0]
        y = u ** 3 * p0[1] + 3 * u * u * t * p1[1] + 3 * u * t * t * p2[1] + t ** 3 * p3[1]
        pts.append((x, y))
    return pts


def draw(size=1024):
    s = size / 256
    img = Image.new('RGBA', (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    d.rounded_rectangle([8 * s, 8 * s, 248 * s, 248 * s], radius=44 * s,
                        fill=BG, outline=GOLD, width=int(7 * s))
    # edges
    for a, b in (((78, 128), (150, 78)), ((78, 128), (150, 178))):
        (x0, y0), (x3, y3) = a, b
        pts = bezier((x0 * s, y0 * s), ((x0 + 40) * s, y0 * s),
                     ((x3 - 40) * s, y3 * s), (x3 * s, y3 * s))
        d.line(pts, fill=GOLD_HI, width=int(7 * s), joint='curve')
    # entry node (pill)
    d.rounded_rectangle([26 * s, 108 * s, 90 * s, 148 * s], radius=20 * s,
                        fill=(29, 58, 38, 255), outline=GREEN, width=int(5 * s))
    # dialog nodes: body + coloured header
    for (x, y, col) in ((142, 50, GOLD), (142, 150, BLUE)):
        d.rounded_rectangle([x * s, y * s, (x + 88) * s, (y + 56) * s],
                            radius=12 * s, fill=PANEL, outline=LINE,
                            width=int(3 * s))
        d.rounded_rectangle([x * s, y * s, (x + 88) * s, (y + 20) * s],
                            radius=12 * s, fill=col)
        d.rectangle([x * s, (y + 10) * s, (x + 88) * s, (y + 20) * s], fill=col)
        for k in range(2):
            ly = (y + 30 + k * 12) * s
            d.rounded_rectangle([(x + 10) * s, ly, (x + 70 - k * 18) * s,
                                 ly + 5 * s], radius=2 * s,
                                fill=(236, 231, 219, 220))
    # ports
    for (x, y) in ((90, 128), (142, 78), (142, 178)):
        r = 8 * s
        d.ellipse([x * s - r, y * s - r, x * s + r, y * s + r], fill=GOLD_HI,
                  outline=BG, width=int(3 * s))
    return img


def main():
    os.makedirs(OUT, exist_ok=True)
    big = draw(1024)
    png = big.resize((256, 256), Image.LANCZOS)
    png.save(os.path.join(OUT, 'icon.png'))
    big.resize((64, 64), Image.LANCZOS).save(os.path.join(OUT, 'icon64.png'))
    png.save(os.path.join(OUT, 'icon.ico'),
             sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64),
                    (128, 128), (256, 256)])
    print('written to', OUT)


if __name__ == '__main__':
    main()
