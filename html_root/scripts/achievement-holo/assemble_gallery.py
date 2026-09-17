"""Assemble a multi-card holographic gallery after the RuiC pipeline completes."""
from __future__ import annotations

import json
import shutil
from pathlib import Path

HTML_ROOT = Path(__file__).resolve().parents[2]
ROOT = Path(__file__).resolve().parent
CARDS = HTML_ROOT / "static" / "assets" / "achievement-cards" / "layers"
WEB = HTML_ROOT / "static" / "achievement-holo"


GALLERY_PATCH_JS = r"""
/* === Achievement gallery extensions === */
(function () {
  const listEl = document.getElementById("card-list");
  const finishSel = document.getElementById("finish");
  if (!listEl) return;

  let catalog = [];
  let currentId = null;
  let swapping = false;

  const tierToFinish = { pearl: "pearl", silver: "silver", gold: "gold" };

  async function loadCatalog() {
    const res = await fetch("./gallery-manifest.json");
    if (!res.ok) throw new Error("gallery-manifest missing");
    catalog = await res.json();
    listEl.innerHTML = "";
    catalog.forEach((card, idx) => {
      const btn = document.createElement("button");
      btn.type = "button";
      btn.className = "card-chip";
      btn.dataset.id = card.id;
      btn.innerHTML =
        '<span class="card-chip-edition">' +
        (card.edition || "") +
        '</span><span class="card-chip-title">' +
        (card.title || card.id) +
        '</span><span class="card-chip-tier">' +
        (card.tier || "pearl") +
        "</span>";
      btn.addEventListener("click", () => selectCard(card.id));
      listEl.appendChild(btn);
      if (idx === 0) currentId = card.id;
    });
  }

  function markActive(id) {
    listEl.querySelectorAll(".card-chip").forEach((el) => {
      el.classList.toggle("active", el.dataset.id === id);
    });
  }

  async function selectCard(id) {
    if (!window.__holo || !window.__holo.ready || swapping) return;
    if (id === currentId) return;
    const card = catalog.find((c) => c.id === id);
    if (!card) return;
    swapping = true;
    const loading = document.getElementById("loading");
    if (loading) {
      loading.hidden = false;
      loading.querySelector("span:last-child").textContent = "切换卡面…";
    }
    try {
      const cfgRes = await fetch(card.config);
      const cfg = await cfgRes.json();
      const loader = new THREE.TextureLoader();
      const names = ["subject", "background", "text", "lineart"];
      const paths = names.map((n) => cfg.assets[n].replace("./", card.base));
      const textures = await Promise.all(paths.map((p) => loader.loadAsync(p)));
      textures.forEach((t) => {
        t.colorSpace = THREE.NoColorSpace;
        t.anisotropy = Math.min(
          8,
          window.__holo.renderer.capabilities.getMaxAnisotropy(),
        );
        t.needsUpdate = true;
      });
      const u = window.__holo.uniforms;
      const old = [u.tSubject.value, u.tBackground.value, u.tText.value, u.tLine.value];
      u.tSubject.value = textures[0];
      u.tBackground.value = textures[1];
      u.tText.value = textures[2];
      u.tLine.value = textures[3];
      u.uHasLine.value = 1;
      const p = cfg.parameters || {};
      u.uFoil.value = p.foil ?? 0.52;
      u.uScale.value = p.subjectScale ?? 1.25;
      u.uDepth.value = p.subjectDepth ?? 0.28;
      u.uBgDepth.value = p.backgroundDepth ?? -0.2;
      old.forEach((t) => t && t.dispose && t.dispose());

      document.title = cfg.title + " · 智算星云";
      for (const [domId, key] of [
        ["card-title", "title"],
        ["subtitle", "subtitle"],
        ["description", "description"],
        ["edition", "edition"],
        ["about-description", "description"],
        ["about-edition", "edition"],
      ]) {
        const el = document.getElementById(domId);
        if (el) el.textContent = cfg[key] || "";
      }
      const aboutTitle = document.getElementById("about-title");
      if (aboutTitle)
        aboutTitle.textContent = [cfg.subtitle, cfg.title]
          .filter(Boolean)
          .join(" / ");

      const foil = document.getElementById("foil");
      if (foil) foil.value = String(Math.round((p.foil ?? 0.52) * 100));
      if (finishSel) {
        const fin = tierToFinish[cfg.tier || cfg.defaultFinish || "pearl"] || "pearl";
        finishSel.value = fin;
        finishSel.dispatchEvent(new Event("change"));
      }
      currentId = id;
      markActive(id);
      if (window.__holo.notice)
        window.__holo.notice("已切换：" + (cfg.title || id));
    } catch (err) {
      console.error(err);
      alert("切卡失败：" + (err && err.message ? err.message : err));
    } finally {
      if (loading) loading.hidden = true;
      swapping = false;
    }
  }

  window.__achievementGallery = { selectCard, loadCatalog };

  function boot() {
    const tryBind = () => {
      if (window.__holo && window.__holo.ready) {
        loadCatalog()
          .then(() => markActive(currentId))
          .catch(console.error);
        return;
      }
      setTimeout(tryBind, 200);
    };
    tryBind();
  }
  if (document.readyState === "loading")
    document.addEventListener("DOMContentLoaded", boot);
  else boot();
})();
"""

GALLERY_CSS = r"""
:root {
  --gallery-ink: #e8eef8;
  --gallery-muted: #8fa0b8;
  --gallery-line: rgba(148, 163, 184, 0.28);
  --gallery-accent: #5eead4;
  --gallery-bg: #0b1220;
}
body {
  background: radial-gradient(1200px 800px at 20% -10%, #1a2a44, transparent),
    radial-gradient(900px 700px at 100% 0%, #123048, transparent),
    var(--gallery-bg) !important;
  color: var(--gallery-ink);
}
.masthead,
.panel,
.tools,
.stage-note {
  color: var(--gallery-ink);
}
.wordmark-cn { color: #f8fafc; }
.wordmark-en, .collection-label, .stage-note { color: var(--gallery-muted); }
.gallery-shell {
  display: grid;
  grid-template-columns: minmax(220px, 280px) 1fr;
  gap: 1rem;
  width: min(1200px, 100%);
  margin: 0 auto;
  padding: 0 1rem 2rem;
  align-items: start;
}
.card-rail {
  border: 1px solid var(--gallery-line);
  border-radius: 16px;
  background: rgba(15, 23, 42, 0.72);
  backdrop-filter: blur(10px);
  padding: 0.85rem;
  max-height: calc(100vh - 120px);
  overflow: auto;
  position: sticky;
  top: 84px;
}
.card-rail h2 {
  margin: 0 0 0.75rem;
  font-size: 0.95rem;
  letter-spacing: 0.08em;
  text-transform: uppercase;
  color: var(--gallery-accent);
  font-weight: 600;
}
.card-rail p {
  margin: 0 0 0.85rem;
  font-size: 0.82rem;
  color: var(--gallery-muted);
  line-height: 1.45;
}
#card-list {
  display: flex;
  flex-direction: column;
  gap: 0.45rem;
}
.card-chip {
  appearance: none;
  border: 1px solid var(--gallery-line);
  background: rgba(30, 41, 59, 0.7);
  color: inherit;
  border-radius: 12px;
  padding: 0.65rem 0.75rem;
  text-align: left;
  cursor: pointer;
  display: grid;
  gap: 0.15rem;
  transition: border-color 0.2s ease, transform 0.2s ease, background 0.2s ease;
}
.card-chip:hover {
  border-color: rgba(94, 234, 212, 0.55);
  transform: translateY(-1px);
}
.card-chip.active {
  border-color: var(--gallery-accent);
  background: linear-gradient(135deg, rgba(20, 80, 90, 0.55), rgba(30, 41, 59, 0.85));
  box-shadow: 0 0 0 1px rgba(94, 234, 212, 0.2);
}
.card-chip-edition {
  font-size: 0.68rem;
  letter-spacing: 0.12em;
  color: var(--gallery-muted);
}
.card-chip-title {
  font-size: 0.95rem;
  font-weight: 600;
}
.card-chip-tier {
  font-size: 0.72rem;
  text-transform: uppercase;
  letter-spacing: 0.08em;
  color: var(--gallery-accent);
}
.gallery-main .gallery {
  min-height: 70vh;
}
@media (max-width: 900px) {
  .gallery-shell {
    grid-template-columns: 1fr;
  }
  .card-rail {
    position: static;
    max-height: none;
  }
  #card-list {
    display: grid;
    grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  }
}
"""


def patch_index(html: str) -> str:
    # Retitle and wrap stage in gallery shell with card rail.
    html = html.replace("<title>白相 · White Atelier</title>", "<title>智算星云 · 成就闪卡展台</title>")
    html = html.replace(
        '>个人典藏 <span>/</span> <span id="edition">STUDY 001</span></span',
        '>成就典藏 <span>/</span> <span id="edition">001 / 013</span></span',
    )
    html = html.replace(
        '<span class="wordmark-cn">白相<span class="brand-dot"></span></span\n'
        '        ><span class="wordmark-en">WHITE ATELIER</span></a\n'
        "      >",
        '<span class="wordmark-cn">智算星云<span class="brand-dot"></span></span'
        '><span class="wordmark-en">ACHIEVEMENT HOLO</span></a>',
    )
    # Insert rail before <main> content by replacing first <main>
    if 'class="gallery-shell"' not in html:
        html = html.replace(
            "<main>",
            """<main>
      <div class="gallery-shell">
        <aside class="card-rail" aria-label="成就卡列表">
          <h2>成就卡组</h2>
          <p>点选任意成就，展台即时切换主体、背景、线稿与文字层，并套用对应珠光 / 银箔 / 烫金质感。</p>
          <div id="card-list"></div>
        </aside>
        <div class="gallery-main">""",
            1,
        )
        html = html.replace("</main>", "        </div>\n      </div>\n    </main>", 1)
    if "gallery-extra.css" not in html:
        html = html.replace(
            '<link rel="stylesheet" href="./style.css" />',
            '<link rel="stylesheet" href="./style.css" />\n'
            '    <link rel="stylesheet" href="./gallery-extra.css" />',
        )
    if "gallery-extra.js" not in html:
        html = html.replace(
            '<script type="module" src="./app.bundle.js"></script>',
            '<script type="module" src="./app.bundle.js"></script>\n'
            '    <script type="module" src="./gallery-extra.js"></script>',
        )
    return html


def main() -> None:
    if not WEB.exists():
        raise SystemExit("web/ missing — run RuiC pipeline first")

    catalog = json.loads((ROOT / "catalog.json").read_text(encoding="utf-8-sig"))
    deck_dir = WEB / "deck"
    deck_dir.mkdir(exist_ok=True)

    # Shared GLB from pipeline
    shared_glb = WEB / "assets" / "card.glb"
    if not shared_glb.exists():
        raise SystemExit("web/assets/card.glb missing")

    manifest = []
    for card in catalog["cards"]:
        cid = card["id"]
        src = CARDS / cid
        dest = deck_dir / cid
        dest_assets = dest / "assets"
        dest_assets.mkdir(parents=True, exist_ok=True)
        for name in ("subject", "background", "text", "lineart"):
            shutil.copy2(src / "assets" / f"{name}.png", dest_assets / f"{name}.png")
        shutil.copy2(shared_glb, dest_assets / "card.glb")
        cfg = json.loads((src / "card-config.json").read_text(encoding="utf-8"))
        cfg["assets"] = {
            "model": "./assets/card.glb",
            "subject": "./assets/subject.png",
            "background": "./assets/background.png",
            "text": "./assets/text.png",
            "lineart": "./assets/lineart.png",
        }
        (dest / "card-config.json").write_text(
            json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        manifest.append(
            {
                "id": cid,
                "title": card["label"],
                "subtitle": card["subtitle"],
                "tier": card.get("tier", "pearl"),
                "edition": card.get("edition", ""),
                "base": f"./deck/{cid}/",
                "config": f"./deck/{cid}/card-config.json",
            }
        )

    (WEB / "gallery-manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    css_src = ROOT / "gallery-extra.css"
    if css_src.exists():
        shutil.copy2(css_src, WEB / "gallery-extra.css")
    else:
        (WEB / "gallery-extra.css").write_text(GALLERY_CSS, encoding="utf-8")
    src_js = ROOT / "gallery-extra.js"
    if src_js.exists():
        shutil.copy2(src_js, WEB / "gallery-extra.js")
    else:
        (WEB / "gallery-extra.js").write_text(GALLERY_PATCH_JS, encoding="utf-8")

    index = WEB / "index.html"
    index.write_text(patch_index(index.read_text(encoding="utf-8")), encoding="utf-8")

    # Ensure root web assets match first card (already from pipeline) and sync config.
    first = catalog["cards"][0]
    shutil.copy2(CARDS / first["id"] / "card-config.json", WEB / "card-config.json")
    print("gallery ready:", WEB)
    print("cards:", len(manifest))


if __name__ == "__main__":
    main()
