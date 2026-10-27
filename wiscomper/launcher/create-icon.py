"""Rebuild launcher artwork from the original website logo; optional build step."""
import io
from pathlib import Path

from PIL import Image
from playwright.sync_api import sync_playwright

root = Path(__file__).resolve().parent.parent
svg = (root / "web/assets/wisdom-logo.svg").read_text(encoding="utf-8")
with sync_playwright() as p:
    browser = p.chromium.launch(channel="msedge")
    page = browser.new_page(viewport={"width": 512, "height": 512}, device_scale_factor=1)
    page.set_content("<style>html,body{margin:0;background:transparent}svg{width:512px;height:512px;display:block}</style>" + svg)
    png = page.screenshot(omit_background=True)
    browser.close()
image = Image.open(io.BytesIO(png)).convert("RGBA")
image.save(root / "launcher/wisdom-logo.png")
image.save(root / "launcher/wisdom-logo.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print("Created launcher logo PNG and ICO from the original SVG.")
