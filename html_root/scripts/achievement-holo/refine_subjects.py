"""Tighten subject alpha: remove dark studio/grid backdrop more aggressively."""
from __future__ import annotations

import json
from pathlib import Path

import numpy as np
from PIL import Image, ImageFilter

ROOT = Path(__file__).resolve().parents[1]
W, H = 1024, 1536


def refine(path: Path) -> None:
    im = Image.open(path).convert("RGBA")
    arr = np.asarray(im).astype(np.float32)
    rgb = arr[..., :3]
    a = arr[..., 3] / 255.0
    lum = 0.2126 * rgb[..., 0] + 0.7152 * rgb[..., 1] + 0.0722 * rgb[..., 2]
    chroma = rgb.max(axis=2) - rgb.min(axis=2)
    # Keep bright / colorful content; kill dark grid.
    keep = np.clip((lum - 18.0) / 40.0, 0, 1)
    keep = np.maximum(keep, np.clip((chroma - 18.0) / 50.0, 0, 1))
    # Prefer existing alpha if already sparse.
    if (a < 0.1).mean() > 0.25:
        keep = np.minimum(keep + 0.15, 1.0) * a
    out = arr.copy()
    out[..., 3] = (keep * 255).astype(np.uint8)
    Image.fromarray(out.astype(np.uint8), "RGBA").save(path)


def remake_lineart(subject_path: Path, line_path: Path) -> None:
    from prepare_all_cards import make_lineart

    sub = Image.open(subject_path).convert("RGBA")
    make_lineart(sub).save(line_path)


def main() -> None:
    catalog = json.loads((ROOT / "catalog.json").read_text(encoding="utf-8-sig"))
    for card in catalog["cards"]:
        assets = ROOT / "cards" / card["id"] / "assets"
        refine(assets / "subject.png")
        remake_lineart(assets / "subject.png", assets / "lineart.png")
        print("refined", card["id"])
    # Reseed root
    first = catalog["cards"][0]["id"]
    src = ROOT / "cards" / first / "assets"
    for name in ("subject", "lineart"):
        (ROOT / "assets" / f"{name}.png").write_bytes((src / f"{name}.png").read_bytes())


if __name__ == "__main__":
    main()
