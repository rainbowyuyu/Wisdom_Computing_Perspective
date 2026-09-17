"""Prepare per-card layered assets for the 智算星云成就典藏 gallery."""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps

HTML_ROOT = Path(__file__).resolve().parents[2]
ROOT = Path(__file__).resolve().parent
CARDS = HTML_ROOT / "static" / "assets" / "achievement-cards" / "layers"
SKILL = Path(r"C:\Users\zju\.cursor\skills\RuiC-card-skill")
SRC = HTML_ROOT / "static" / "assets" / "achievement-cards" / "studio"
W, H = 1024, 1536

sys.path.insert(0, str(SKILL / "scripts"))
import checkerboard_to_alpha as c2a  # noqa: E402


def category_of(card_id: str) -> str:
    if card_id == "tutorial":
        return "tutorial"
    if card_id.startswith("formulas"):
        return "formulas"
    if card_id.startswith("scripts"):
        return "scripts"
    if card_id.startswith("templates"):
        return "templates"
    return "wrongbook"


def resize_cover(im: Image.Image, size=(W, H)) -> Image.Image:
    return ImageOps.fit(im, size, method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))


def ensure_subject_alpha(im: Image.Image) -> Image.Image:
    """Convert checkerboard or near-black studio backdrop into true alpha."""
    if im.mode != "RGBA":
        rgb = im.convert("RGB")
        det = c2a.detect_checkerboard(rgb)
        if det:
            out, _ = c2a.convert_to_alpha(rgb, det)
            return out
        # Dark studio backdrop: treat near-black / very dark as transparent.
        arr = np.asarray(rgb).astype(np.float32)
        lum = 0.2126 * arr[..., 0] + 0.7152 * arr[..., 1] + 0.0722 * arr[..., 2]
        # Soft threshold so glow halos remain.
        alpha = np.clip((lum - 8.0) / 28.0, 0, 1)
        # Keep colorful pixels even if dim.
        chroma = arr.max(axis=2) - arr.min(axis=2)
        alpha = np.maximum(alpha, np.clip((chroma - 12.0) / 40.0, 0, 1))
        a = (alpha * 255).astype(np.uint8)
        rgba = np.dstack([arr.astype(np.uint8), a])
        return Image.fromarray(rgba, "RGBA")
    # Already RGBA: still strip near-black fringe if almost opaque everywhere.
    arr = np.asarray(im)
    a = arr[..., 3]
    if (a > 200).mean() > 0.92:
        rgb = arr[..., :3].astype(np.float32)
        lum = 0.2126 * rgb[..., 0] + 0.7152 * rgb[..., 1] + 0.0722 * rgb[..., 2]
        chroma = rgb.max(axis=2) - rgb.min(axis=2)
        soft = np.clip((lum - 8.0) / 28.0, 0, 1)
        soft = np.maximum(soft, np.clip((chroma - 12.0) / 40.0, 0, 1))
        arr[..., 3] = (soft * 255).astype(np.uint8)
        return Image.fromarray(arr, "RGBA")
    return im


def make_lineart(subject: Image.Image) -> Image.Image:
    """White-bg / black-contour lineart from subject silhouette + strong inner edges.

    Avoid dense FIND_EDGES noise and never bake transparency checkerboards into RGB.
    """
    rgba = subject.convert("RGBA")
    w, h = rgba.size
    alpha = np.asarray(rgba.getchannel("A")).astype(np.float32)
    mask = alpha / 255.0
    a_im = Image.fromarray(alpha.astype(np.uint8), "L")
    edges_a = np.asarray(a_im.filter(ImageFilter.FIND_EDGES)).astype(np.float32)
    gray = ImageOps.grayscale(rgba.convert("RGB"))
    edges_g = np.asarray(gray.filter(ImageFilter.FIND_EDGES)).astype(np.float32)
    silhouette = (edges_a > 40) & (mask > 0.02)
    eg = edges_g * (mask > 0.35)
    thr = float(np.percentile(eg[mask > 0.35], 92)) if (mask > 0.35).any() else 999.0
    inner = eg > max(thr, 55.0)
    line = np.zeros((h, w), dtype=np.uint8)
    line[silhouette | inner] = 255
    line_im = Image.fromarray(line, "L").filter(ImageFilter.MaxFilter(3))
    line_arr = np.asarray(line_im)
    out = np.full((h, w, 3), 255, dtype=np.uint8)
    out[line_arr > 0] = 0
    out[mask < 0.04] = 255
    return Image.fromarray(out, "RGB")


def pick_font(size: int) -> ImageFont.FreeTypeFont:
    candidates = [
        Path(r"C:\Windows\Fonts\simkai.ttf"),
        Path(r"C:\Windows\Fonts\simhei.ttf"),
        Path(r"C:\Windows\Fonts\msyh.ttc"),
        Path(r"C:\Windows\Fonts\arial.ttf"),
    ]
    for p in candidates:
        if p.is_file():
            return ImageFont.truetype(str(p), size)
    return ImageFont.load_default()


def make_text(card: dict) -> Image.Image:
    im = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(im)
    gold = (244, 208, 135, 255)
    cream = (255, 241, 206, 255)

    def txt(x, y, value, size, anchor="la", fill=cream, max_width=850):
        if not value:
            return
        f = pick_font(size)
        while d.textbbox((0, 0), value, font=f)[2] > max_width and size > 14:
            size -= 1
            f = pick_font(size)
        d.text(
            (x, y),
            value,
            font=f,
            fill=fill,
            anchor=anchor,
            stroke_width=2,
            stroke_fill=(16, 21, 27, 220),
        )

    txt(72, 49, card.get("subtitle", ""), 25, fill=gold)
    txt(72, 87, card.get("label", ""), 72, max_width=875)
    txt(76, 195, "智算星云 · 成就典藏", 22, fill=gold)
    d.line((70, 245, 954, 245), fill=gold, width=2)
    d.line((70, 1280, 954, 1280), fill=gold, width=2)
    txt(512, 1300, card.get("tagline", ""), 28, anchor="ma", fill=gold, max_width=900)
    txt(512, 1346, card.get("technique", ""), 48, anchor="ma", max_width=900)
    txt(72, 1467, card.get("edition", "001 / 013"), 20, fill=gold)
    finish = {"pearl": "PEARL", "silver": "SILVER", "gold": "GOLD"}.get(
        card.get("tier", "pearl"), "HOLO"
    )
    txt(950, 1467, finish, 18, anchor="ra", fill=gold, max_width=380)
    return im


def foil_for_tier(tier: str) -> float:
    return {"pearl": 0.48, "silver": 0.62, "gold": 0.78}.get(tier, 0.55)


def write_config(card_dir: Path, card: dict) -> None:
    cfg = {
        "title": card["label"],
        "subtitle": card["subtitle"],
        "technique": card["technique"],
        "tagline": card["tagline"],
        "edition": card["edition"],
        "collection": "智算星云 · 成就典藏",
        "description": card.get("condition", card.get("tagline", "")),
        "tier": card.get("tier", "pearl"),
        "achievementId": card["id"],
        "assets": {
            "model": "./assets/card.glb",
            "subject": "./assets/subject.png",
            "background": "./assets/background.png",
            "text": "./assets/text.png",
            "lineart": "./assets/lineart.png",
        },
        "parameters": {
            "subjectScale": 1.25,
            "subjectDepth": 0.28,
            "backgroundDepth": -0.2,
            "foil": foil_for_tier(card.get("tier", "pearl")),
        },
        "safeArea": {"scale": 1.12, "offset": [-0.06, -0.085]},
        "appearance": {"background": "#0b1220"},
        "defaultFinish": card.get("tier", "pearl"),
    }
    (card_dir / "card-config.json").write_text(
        json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8"
    )


def prepare_card(card: dict) -> Path:
    cid = card["id"]
    cat = category_of(cid)
    card_dir = CARDS / cid
    assets = card_dir / "assets"
    assets.mkdir(parents=True, exist_ok=True)

    bg_src = SRC / f"bg-{cat}.png"
    sub_src = SRC / f"subject-{cid}.png"
    if not bg_src.exists():
        raise FileNotFoundError(bg_src)
    if not sub_src.exists():
        raise FileNotFoundError(sub_src)

    bg = resize_cover(Image.open(bg_src).convert("RGB"))
    bg.save(assets / "background.png")

    subject = ensure_subject_alpha(resize_cover(Image.open(sub_src)))
    subject.save(assets / "subject.png")

    line = make_lineart(subject)
    line.save(assets / "lineart.png")

    text = make_text(card)
    text.save(assets / "text.png")

    write_config(card_dir, card)
    # Copy validation helper target layout expected by skill scripts.
    # Root-level assets for the active/default card are handled separately.
    print("prepared", cid, subject.mode, subject.size)
    return card_dir


def main() -> None:
    catalog = json.loads((ROOT / "catalog.json").read_text(encoding="utf-8-sig"))
    cards = catalog["cards"]
    for card in cards:
        prepare_card(card)

    # Seed project root with the first card for the Blender pipeline.
    first = cards[0]["id"]
    src = CARDS / first
    root_assets = HTML_ROOT / "static" / "assets" / "achievement-cards" / "studio"
    root_assets.mkdir(exist_ok=True)
    for name in ("subject", "background", "lineart", "text"):
        shutil.copy2(src / "assets" / f"{name}.png", root_assets / f"{name}.png")
    shutil.copy2(src / "card-config.json", ROOT / "card-config.json")
    print("seeded root from", first)


if __name__ == "__main__":
    main()
