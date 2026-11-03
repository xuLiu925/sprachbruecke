"""生成 PWA 图标(纯 Python, 不用 PIL): 深蓝底 + 白色拱桥(语言之桥)。
输出到 static/icons/: icon-192.png、icon-512.png(圆角)、maskable-512.png(满底, 图案缩进安全区)、
apple-touch-icon.png(180, 满底, 苹果自己切圆角)。改了图案重跑: python tools/make_icons.py
"""
import math
import os
import struct
import zlib

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "static", "icons")
BG = (0x1f, 0x4e, 0x78)
FG = (255, 255, 255)
SS = 4   # 每个像素 4×4 个采样点, 边缘抗锯齿

# 拱桥(坐标 0–1): 拱圈、桥面、吊杆、桥墩
CX, DECK, RX, RY, ARCH_W = 0.5, 0.62, 0.30, 0.30, 0.055


def bridge(x, y):
    if 0.14 <= x <= 0.86 and DECK <= y <= DECK + 0.06:                    # 桥面
        return True
    if (0.20 <= x <= 0.26 or 0.74 <= x <= 0.80) and DECK + 0.06 <= y <= 0.80:  # 桥墩
        return True
    if y <= DECK + 0.001:
        d = math.hypot((x - CX) / RX, (y - DECK) / RY)                    # 拱圈: 椭圆环的上半
        if 1 - ARCH_W / RX <= d <= 1:
            return True
        for hx in (0.38, 0.5, 0.62):                                      # 吊杆
            if abs(x - hx) <= 0.012 and d <= 1:
                return True
    return False


def in_rounded(x, y, r):
    cx, cy = min(max(x, r), 1 - r), min(max(y, r), 1 - r)
    return math.hypot(x - cx, y - cy) <= r


def render(size, radius=0.0, scale=1.0):
    rows = []
    for py in range(size):
        row = bytearray([0])   # 每行开头的过滤类型
        for px in range(size):
            bg = fg = 0
            for sy in range(SS):
                for sx in range(SS):
                    x = (px + (sx + 0.5) / SS) / size
                    y = (py + (sy + 0.5) / SS) / size
                    if radius and not in_rounded(x, y, radius):
                        continue
                    bg += 1
                    if bridge(0.5 + (x - 0.5) / scale, 0.5 + (y - 0.5) / scale):
                        fg += 1
            n = SS * SS
            if bg == 0:
                row += bytes(4)
                continue
            t = fg / bg
            row += bytes(round(BG[i] * (1 - t) + FG[i] * t) for i in range(3)) + bytes([round(255 * bg / n)])
        rows.append(bytes(row))
    return png(size, b"".join(rows))


def png(size, raw):
    def chunk(kind, data):
        return struct.pack(">I", len(data)) + kind + data + struct.pack(">I", zlib.crc32(kind + data) & 0xffffffff)
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", size, size, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def main():
    os.makedirs(OUT, exist_ok=True)
    for name, size, radius, scale in (("icon-192.png", 192, 0.22, 1.0), ("icon-512.png", 512, 0.22, 1.0),
                                      ("maskable-512.png", 512, 0, 0.8), ("apple-touch-icon.png", 180, 0, 0.9)):
        with open(os.path.join(OUT, name), "wb") as f:
            f.write(render(size, radius, scale))
        print(name)


if __name__ == "__main__":
    main()
