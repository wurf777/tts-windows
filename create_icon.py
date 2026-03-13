"""Generate app icon: classic monitor + yellow speech bubble."""
from PIL import Image, ImageDraw

def make_frame(size):
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    d = ImageDraw.Draw(img)
    s = size

    # --- Monitor body ---
    # Outer frame (dark gray)
    bx0, by0 = int(s * 0.05), int(s * 0.10)
    bx1, by1 = int(s * 0.80), int(s * 0.68)
    d.rounded_rectangle([bx0, by0, bx1, by1], radius=int(s * 0.06), fill=(80, 90, 105))

    # Screen (light blue)
    sx0, sy0 = bx0 + int(s * 0.05), by0 + int(s * 0.05)
    sx1, sy1 = bx1 - int(s * 0.05), by1 - int(s * 0.05)
    d.rectangle([sx0, sy0, sx1, sy1], fill=(170, 210, 235))

    # Stand neck
    nx = int(s * 0.40)
    d.rectangle([nx, by1, nx + int(s * 0.06), by1 + int(s * 0.12)], fill=(80, 90, 105))

    # Stand base
    d.rounded_rectangle(
        [int(s * 0.22), by1 + int(s * 0.12), int(s * 0.64), by1 + int(s * 0.19)],
        radius=int(s * 0.03),
        fill=(80, 90, 105),
    )

    # --- Speech bubble (yellow, top-right) ---
    bub_x0 = int(s * 0.55)
    bub_y0 = int(s * 0.02)
    bub_x1 = int(s * 0.97)
    bub_y1 = int(s * 0.48)
    d.rounded_rectangle(
        [bub_x0, bub_y0, bub_x1, bub_y1],
        radius=int(s * 0.08),
        fill=(255, 210, 50),
        outline=(200, 160, 20),
        width=max(1, int(s * 0.025)),
    )

    # Bubble tail (pointing down-left)
    tail = [
        (bub_x0 + int(s * 0.10), bub_y1 - 1),
        (bub_x0 + int(s * 0.04), bub_y1 + int(s * 0.10)),
        (bub_x0 + int(s * 0.24), bub_y1 - 1),
    ]
    d.polygon(tail, fill=(255, 210, 50))
    # Outline for tail
    d.line([tail[0], tail[1], tail[2]], fill=(200, 160, 20), width=max(1, int(s * 0.02)))

    # Dots inside bubble
    dot_y = (bub_y0 + bub_y1) // 2
    dot_r = max(2, int(s * 0.05))
    for dot_x in [
        int(s * 0.67),
        int(s * 0.76),
        int(s * 0.85),
    ]:
        d.ellipse(
            [dot_x - dot_r, dot_y - dot_r, dot_x + dot_r, dot_y + dot_r],
            fill=(80, 50, 10),
        )

    return img


sizes = [16, 24, 32, 48, 64, 128, 256]
frames = [make_frame(s) for s in sizes]
frames[0].save(
    "tts_windows.ico",
    format="ICO",
    sizes=[(s, s) for s in sizes],
    append_images=frames[1:],
)
print("Icon saved: tts_windows.ico")
