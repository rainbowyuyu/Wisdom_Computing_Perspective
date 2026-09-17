"""Fix painted checkerboard on all achievement subjects and rebuild composites."""
from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

HTML_ROOT = Path(__file__).resolve().parents[2]
ROOT = Path(__file__).resolve().parent
CARDS = HTML_ROOT / "static" / "assets" / "achievement-cards" / "layers"
WEB = HTML_ROOT / "static" / "achievement-holo"
SRC = HTML_ROOT / "static" / "assets" / "achievement-cards" / "studio"
SKILL = Path(r"C:\Users\zju\.cursor\skills\RuiC-card-skill\scripts")
HTML_ASSETS = HTML_ROOT / "static" / "assets" / "achievement-cards"
W, H = 1024, 1536

sys.path.insert(0, str(SKILL))
import checkerboard_to_alpha as c2a  # noqa: E402
sys.path.insert(0, str(ROOT))
from prepare_all_cards import make_lineart, resize_cover  # noqa: E402


def category_of(card_id: str) -> str:
    if card_id == "tutorial":
        return "tutorial"
    for prefix in ("formulas", "scripts", "templates", "wrongbook"):
        if card_id.startswith(prefix):
            return prefix
    return "tutorial"


def kill_checker_rgb(rgba: Image.Image) -> Image.Image:
    """Ensure checkerboard RGB is gone wherever alpha is low."""
    arr = np.asarray(rgba).copy()
    a = arr[..., 3].astype(np.float32) / 255.0
    # Zero RGB on transparent pixels so no gray grid leaks through premultiplied sampling.
    mask = a < 0.08
    arr[mask, :3] = 0
    arr[mask, 3] = 0
    # Soft premultiply fringe
    fringe = (a >= 0.08) & (a < 0.92)
    if fringe.any():
        for c in range(3):
            arr[..., c] = np.where(
                fringe,
                (arr[..., c].astype(np.float32) * a).astype(np.uint8),
                arr[..., c],
            )
    return Image.fromarray(arr, "RGBA")


def subject_from_source(card_id: str) -> Image.Image:
    src = SRC / f"subject-{card_id}.png"
    if not src.exists():
        raise FileNotFoundError(src)
    im = Image.open(src)
    rgb = resize_cover(im.convert("RGB"))
    det = c2a.detect_checkerboard(rgb)
    if det:
        out, report = c2a.convert_to_alpha(rgb, det)
        print(f"  {card_id}: checkerboard cell={report.get('cell')} t={report.get('transparent_fraction')}")
    else:
        # Fallback: near-white / gray studio → alpha
        arr = np.asarray(rgb).astype(np.float32)
        lum = 0.2126 * arr[..., 0] + 0.7152 * arr[..., 1] + 0.0722 * arr[..., 2]
        chroma = arr.max(2) - arr.min(2)
        # White/gray backdrop
        bg = (lum > 210) & (chroma < 18)
        # Also mid-gray checker-ish
        mid = (lum > 160) & (lum < 245) & (chroma < 12)
        alpha = np.ones((H, W), dtype=np.float32)
        alpha[bg | mid] = 0
        # Keep colorful / darker subject
        keep = (chroma > 20) | (lum < 150)
        alpha = np.where(keep, 1.0, alpha)
        soft = Image.fromarray((alpha * 255).astype(np.uint8), "L").filter(
            ImageFilter.GaussianBlur(0.6)
        )
        a = np.asarray(soft)
        out = Image.fromarray(np.dstack([arr.astype(np.uint8), a]), "RGBA")
        print(f"  {card_id}: fallback matte t={round(float((a < 16).mean()), 4)}")
    out = kill_checker_rgb(out)
    # Clear border ring to true transparent (copy — PIL arrays can be read-only)
    arr = np.asarray(out).copy()
    arr[:6, :, 3] = 0
    arr[-6:, :, 3] = 0
    arr[:, :6, 3] = 0
    arr[:, -6:, 3] = 0
    return kill_checker_rgb(Image.fromarray(arr, "RGBA"))


def composite_preview(card_dir: Path) -> Image.Image:
    bg = Image.open(card_dir / "assets" / "background.png").convert("RGBA")
    subject = Image.open(card_dir / "assets" / "subject.png").convert("RGBA")
    text = Image.open(card_dir / "assets" / "text.png").convert("RGBA")
    # Soft vignette-free compose
    out = bg.copy()
    out.alpha_composite(subject)
    out.alpha_composite(text)
    return out.convert("RGB")


def main() -> None:
    catalog = json.loads((ROOT / "catalog.json").read_text(encoding="utf-8-sig"))
    HTML_ASSETS.mkdir(parents=True, exist_ok=True)
    manifest = []

    for card in catalog["cards"]:
        cid = card["id"]
        card_dir = CARDS / cid
        assets = card_dir / "assets"
        assets.mkdir(parents=True, exist_ok=True)

        # Background from category source
        cat = category_of(cid)
        bg_src = SRC / f"bg-{cat}.png"
        bg = resize_cover(Image.open(bg_src).convert("RGB"))
        bg.save(assets / "background.png")

        subject = subject_from_source(cid)
        subject.save(assets / "subject.png")
        make_lineart(subject).save(assets / "lineart.png")
        # text.png already generated; keep if present
        if not (assets / "text.png").exists():
            from prepare_all_cards import make_text

            make_text(card).save(assets / "text.png")

        preview = composite_preview(card_dir)
        preview_path = assets / "preview.png"
        preview.save(preview_path, quality=95)

        # Site copies
        dest = HTML_ASSETS / cid
        dest.mkdir(parents=True, exist_ok=True)
        for name in ("subject", "background", "text", "lineart", "preview"):
            shutil.copy2(assets / f"{name}.png", dest / f"{name}.png")

        # Sync holo deck if present
        deck = WEB / "deck" / cid / "assets"
        if deck.exists():
            for name in ("subject", "background", "text", "lineart"):
                shutil.copy2(assets / f"{name}.png", deck / f"{name}.png")

        tier = card.get("tier", "pearl")
        manifest.append(
            {
                "id": cid,
                "label": card["label"],
                "subtitle": card.get("subtitle", ""),
                "technique": card.get("technique", ""),
                "tagline": card.get("tagline", ""),
                "edition": card.get("edition", ""),
                "tier": tier,
                "condition": card.get("condition", ""),
                "preview": f"/assets/achievement-cards/{cid}/preview.png",
                "subject": f"/assets/achievement-cards/{cid}/subject.png",
                "background": f"/assets/achievement-cards/{cid}/background.png",
                "text": f"/assets/achievement-cards/{cid}/text.png",
            }
        )
        print("fixed", cid)

    # Seed root + web assets with tutorial
    first = catalog["cards"][0]["id"]
    for name in ("subject", "background", "text", "lineart"):
        shutil.copy2(
            CARDS / first / "assets" / f"{name}.png",
            SRC / f"{name}.png",
        )
        web_assets = WEB / "assets"
        if web_assets.exists():
            shutil.copy2(
                CARDS / first / "assets" / f"{name}.png",
                web_assets / f"{name}.png",
            )

    (HTML_ASSETS / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (WEB / "gallery-manifest.json").write_text(
        json.dumps(
            [
                {
                    "id": m["id"],
                    "title": m["label"],
                    "subtitle": m["subtitle"],
                    "tier": m["tier"],
                    "edition": m["edition"],
                    "base": f"./deck/{m['id']}/",
                    "config": f"./deck/{m['id']}/card-config.json",
                }
                for m in manifest
            ],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    print("wrote", HTML_ASSETS / "manifest.json")


if __name__ == "__main__":
    main()
