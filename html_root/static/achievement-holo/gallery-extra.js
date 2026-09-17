/* Achievement multi-card gallery — hot-swaps textures on the live holo stage. */
(function () {
  const listEl = document.getElementById("card-list");
  if (!listEl) return;

  let catalog = [];
  let currentId = null;
  let swapping = false;

  const tierToFinish = { pearl: "pearl", silver: "silver", gold: "gold" };

  function notice(message) {
    const el = document.getElementById("notice");
    if (!el) return;
    el.textContent = message;
    el.hidden = false;
    clearTimeout(notice._t);
    notice._t = setTimeout(() => {
      el.hidden = true;
    }, 2200);
  }

  function setMeta(cfg) {
    document.title = (cfg.title || "成就闪卡") + " · 智算星云";
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
    if (aboutTitle) {
      aboutTitle.textContent = [cfg.subtitle, cfg.title].filter(Boolean).join(" / ");
    }
  }

  function applyFinish(tier) {
    const fin = tierToFinish[tier] || "pearl";
    const btn = document.querySelector('[data-finish="' + fin + '"]');
    if (btn) btn.click();
  }

  function loadImage(url) {
    return new Promise((resolve, reject) => {
      const img = new Image();
      img.decoding = "async";
      img.onload = () => resolve(img);
      img.onerror = () => reject(new Error("load failed: " + url));
      img.src = url;
    });
  }

  function assignTexture(tex, img) {
    if (!tex) return;
    tex.image = img;
    tex.needsUpdate = true;
  }

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
    markActive(currentId);
  }

  function markActive(id) {
    listEl.querySelectorAll(".card-chip").forEach((el) => {
      el.classList.toggle("active", el.dataset.id === id);
    });
  }

  async function selectCard(id) {
    if (!window.__holo || !window.__holo.ready || !window.__holo.uniforms) return;
    if (swapping) return;
    if (id === currentId) {
      markActive(id);
      return;
    }
    const card = catalog.find((c) => c.id === id);
    if (!card) return;
    swapping = true;
    const loading = document.getElementById("loading");
    if (loading) {
      loading.hidden = false;
      const label = loading.querySelector("span:last-child");
      if (label) label.textContent = "切换卡面…";
    }
    try {
      const cfgRes = await fetch(card.config);
      const cfg = await cfgRes.json();
      const base = card.base;
      const paths = ["subject", "background", "text", "lineart"].map((n) =>
        (cfg.assets[n] || "./assets/" + n + ".png").replace(/^\.\//, base),
      );
      const images = await Promise.all(paths.map(loadImage));
      const u = window.__holo.uniforms;
      assignTexture(u.tSubject.value, images[0]);
      assignTexture(u.tBackground.value, images[1]);
      assignTexture(u.tText.value, images[2]);
      assignTexture(u.tLine.value, images[3]);
      if (u.uHasLine) u.uHasLine.value = 1;
      const p = cfg.parameters || {};
      if (u.uFoil) u.uFoil.value = p.foil ?? 0.52;
      if (u.uScale) u.uScale.value = p.subjectScale ?? 1.25;
      if (u.uDepth) u.uDepth.value = p.subjectDepth ?? 0.28;
      if (u.uBgDepth) u.uBgDepth.value = p.backgroundDepth ?? -0.2;
      const foil = document.getElementById("foil");
      if (foil) {
        foil.value = String(Math.round((p.foil ?? 0.52) * 100));
        foil.dispatchEvent(new Event("input"));
      }
      setMeta(cfg);
      applyFinish(cfg.tier || cfg.defaultFinish || "pearl");
      currentId = id;
      markActive(id);
      notice("已切换：" + (cfg.title || id));
    } catch (err) {
      console.error(err);
      notice("切卡失败");
    } finally {
      if (loading) loading.hidden = true;
      swapping = false;
    }
  }

  window.__achievementGallery = { selectCard, loadCatalog };

  function boot() {
    const tryBind = () => {
      if (window.__holo && window.__holo.ready) {
        loadCatalog().catch(console.error);
        return;
      }
      setTimeout(tryBind, 200);
    };
    tryBind();
  }

  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", boot);
  } else {
    boot();
  }
})();
