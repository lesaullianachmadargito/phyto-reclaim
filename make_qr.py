# -*- coding: utf-8 -*-
"""Generate a labelled QR code for any URL.

    python make_qr.py                                  # auto-detect the LAN URL
    python make_qr.py https://phyto.streamlit.app      # any URL you give it
    python make_qr.py https://... --label "Scan to open the live model"

Output: a PNG sized for a slide or a printed poster.

IMPORTANT — read before printing anything.
A 192.168.x.x address only works on the same WiFi as this laptop, and DHCP can
change it. It is fine as a same-room fallback, useless as a permanent link.
For a link that works anywhere, deploy to Streamlit Community Cloud first
(see README.md) and pass that URL to this script instead.
"""
import argparse
import socket
import sys

import qrcode
from qrcode.constants import ERROR_CORRECT_H
from PIL import Image, ImageDraw, ImageFont

NAVY = (23, 54, 93)
GREY = (110, 123, 128)
WHITE = (255, 255, 255)


def lan_url(port=8501):
    """Best guess at this machine's LAN address, the way Streamlit reports it."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))       # no packet is sent; this just picks a route
        ip = s.getsockname()[0]
    except Exception:
        ip = "127.0.0.1"
    finally:
        s.close()
    return f"http://{ip}:{port}"


def _font(size, bold=False):
    for name in (("segoeuib.ttf", "arialbd.ttf") if bold else ("segoeui.ttf", "arial.ttf")):
        try:
            return ImageFont.truetype(name, size)
        except OSError:
            continue
    return ImageFont.load_default()


def build(url, title, subtitle, box=14, margin=64):
    qr = qrcode.QRCode(version=None, error_correction=ERROR_CORRECT_H,
                       box_size=box, border=2)
    qr.add_data(url)
    qr.make(fit=True)
    code = qr.make_image(fill_color=NAVY, back_color=WHITE).convert("RGB")

    width = code.width + margin * 2

    def fit(text, start, bold=False, pad=24):
        """Largest font size at which `text` still fits the canvas width."""
        probe = Image.new("RGB", (10, 10))
        dd = ImageDraw.Draw(probe)
        size = start
        while size > 10:
            f = _font(size, bold)
            if dd.textlength(text, font=f) <= width - pad * 2:
                return f
            size -= 2
        return _font(10, bold)

    f_title = fit(title, 46, bold=True) if title else None
    f_url = fit(url, 30)
    f_sub = fit(subtitle, 24) if subtitle else None
    head = 92 if title else 0
    foot = 118

    canvas = Image.new("RGB", (width, code.height + margin * 2 + head + foot), WHITE)
    d = ImageDraw.Draw(canvas)
    cx = canvas.width // 2

    if title:
        d.text((cx, margin + 26), title, font=f_title, fill=NAVY, anchor="mm")
    canvas.paste(code, (margin, margin + head))

    y = margin + head + code.height + 34
    d.text((cx, y), url, font=f_url, fill=NAVY, anchor="mm")
    if subtitle:
        d.text((cx, y + 44), subtitle, font=f_sub, fill=GREY, anchor="mm")
    return canvas


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("url", nargs="?", default=None,
                    help="URL to encode (default: this machine's LAN address)")
    ap.add_argument("--port", type=int, default=8501)
    ap.add_argument("--title", default="PHYTO-RECLAIM live model")
    ap.add_argument("--label", default=None, help="small line under the URL")
    ap.add_argument("--out", default="qr.png")
    args = ap.parse_args()

    url = args.url or lan_url(args.port)
    private = url.startswith(("http://192.168.", "http://10.", "http://172.",
                              "http://127.", "http://localhost"))
    subtitle = args.label
    if subtitle is None:
        subtitle = ("Works only on this WiFi network" if private
                    else "Scan to open in any browser")

    img = build(url, args.title, subtitle)
    img.save(args.out)
    print(f"Saved: {args.out}  ({img.width}x{img.height} px)")
    print(f"Encodes: {url}")
    if private:
        print()
        print("WARNING: this is a private LAN address.")
        print("  - it only resolves on the same WiFi as this laptop")
        print("  - the laptop must be running the app at that moment")
        print("  - DHCP can hand out a different address next time you connect")
        print("  - many venue networks block device-to-device traffic entirely")
        print("For a link that works anywhere, deploy first and re-run this")
        print("script with the public URL.")
