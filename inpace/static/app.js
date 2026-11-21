// inPace's page script. Everything lives inside this one function, so the script can safely run again on the same
// window (a page drawn by document.write after a form, for example) without "already declared" errors. What other
// code needs (the app windows, the Android shell, other parts of this file) is put on window.inpace… on purpose.
(function inpaceApp() {
// The live parts of the page exactly as Python drew them, before any script here changes them. Updating a part
// in place compares against this, so a part a script has changed is never overwritten (see "Fresh without
// reloading" below).
const inpacePristine = new Map([...document.querySelectorAll("[data-live][id]")].map((el) => [el.id, el.cloneNode(true)]));

// Send a form the same way pressing its button would, so [data-nav-form] forms replace the page.
function sendForm(form) {
  if (form.requestSubmit) form.requestSubmit(); else form.submit();
}

// Go to a page after a change, and always load it fresh. Going to the page you're already on, with only a
// different #section (or none), makes the browser just scroll, so the change (a new colour, something you
// bought) wouldn't show until you reloaded by hand.
function goFresh(url) {
  const next = new URL(url, location.href);
  const samePage = next.origin === location.origin && next.pathname === location.pathname && next.search === location.search;
  if (samePage && next.hash) {
    history.replaceState(history.state, "", next.href);
    location.reload();
  } else {
    location.replace(next.href);
  }
}

// Small helpers only. The app works without JavaScript too.
// Page helpers listen on the whole document (not on each element), so parts of a page that are updated in place
// keep working: a new button or field behaves exactly like the one it replaced.
document.addEventListener("change", (e) => {
  const input = e.target.closest && e.target.closest("[data-autosubmit]");
  if (!input || !input.form) return;
  if (input.tagName === "SELECT" ? input.value : input.type === "file" ? input.files.length : true) sendForm(input.form);
});
document.addEventListener("submit", (e) => {  // a button with data-busy says what's happening once its form is sent
  e.target.querySelectorAll && e.target.querySelectorAll("[data-busy]").forEach((btn) => {
    btn.disabled = true; btn.textContent = btn.dataset.busy;
  });
}, true);
document.addEventListener("click", (e) => {  // "Every day", "Weekdays" and "Weekends" on Reminders
  const btn = e.target.closest && e.target.closest("[data-days]");
  if (!btn) return;
  const on = btn.dataset.days.split(",");
  const form = btn.closest("form");
  form.querySelectorAll('input[name="days"]').forEach((box) => { box.checked = on.includes(box.value); });
  if (form._remOther) form._remOther(false);
});
document.querySelectorAll("[data-autosubmit]").forEach((input) => {
  const zone = input.closest(".drop-zone");
  if (!zone) return;
  ["dragenter", "dragover"].forEach((e) => zone.addEventListener(e, () => zone.classList.add("over")));
  ["dragleave", "drop"].forEach((e) => zone.addEventListener(e, () => zone.classList.remove("over")));
});

document.querySelectorAll("[data-copy]").forEach((btn) => {
  btn.addEventListener("click", async () => {
    const box = document.querySelector(btn.dataset.copy);
    try { await navigator.clipboard.writeText(box.value); }
    catch { box.select(); document.execCommand("copy"); }
    const old = btn.textContent;
    btn.textContent = document.documentElement.lang === "ar" ? "تم النسخ!" : "Copied!";
    setTimeout(() => (btn.textContent = old), 1800);
  });
});

// "More apps…" opens the system share menu where the window supports it (Signal, Messenger, Mail…).
if (navigator.share) {
  document.querySelectorAll("[data-share]").forEach((btn) => {
    btn.hidden = false;
    btn.addEventListener("click", () => {
      const text = document.querySelector(btn.dataset.share).value;
      navigator.share({ text }).catch(() => {});
    });
  });
}

document.querySelectorAll("[data-wordcount]").forEach((box) => {
  const need = +box.dataset.wordcount;
  const out = box.form.querySelector("[data-wordcount-out]");
  const update = () => {
    const n = box.value.trim() ? box.value.trim().split(/\s+/).length : 0;
    const of = box.dataset.of || '%s of at least %s words', ok = box.dataset.ok || '%s words ✓';
    out.textContent = n >= need ? ok.replace('%s', n) : of.replace('%s', n).replace('%s', need);
  };
  box.addEventListener("input", update);
  update();
});


// A drawn diagram with zoom and full screen: − and + (or Ctrl + mouse wheel) zoom, drag to move around when
// it's bigger than the box, "Fit" shows all of it, and full screen fills the screen (Escape or the button closes it).
function diagramBox(svgText) {
  const ar = document.documentElement.lang === "ar";
  const T = ar ? { out: "تصغير", in: "تكبير", fit: "ملاءمة", full: "ملء الشاشة", close: "إغلاق ملء الشاشة" }
               : { out: "Zoom out", in: "Zoom in", fit: "Fit", full: "Full screen", close: "Close full screen" };
  const box = document.createElement("figure");
  box.className = "diagram-box";
  box.dir = "ltr";
  box.innerHTML = `<div class="diagram-tools" role="toolbar" aria-label="${T.in} / ${T.out}">
      <button type="button" data-z="out" title="${T.out}" aria-label="${T.out}">−</button>
      <span class="diagram-zoom" aria-live="polite">100%</span>
      <button type="button" data-z="in" title="${T.in}" aria-label="${T.in}">+</button>
      <button type="button" data-z="fit">${T.fit}</button>
      <button type="button" data-z="full" class="diagram-full-btn">⛶ <span>${T.full}</span></button>
    </div><div class="diagram-view" tabindex="0"><div class="diagram-canvas">${svgText}</div></div>`;
  const view = box.querySelector(".diagram-view"), svg = box.querySelector("svg"), label = box.querySelector(".diagram-zoom");
  const vb = svg.viewBox && svg.viewBox.baseVal;
  const natW = (vb && vb.width) || svg.getBoundingClientRect().width || 600, natH = (vb && vb.height) || 400;
  svg.removeAttribute("height");
  svg.style.maxWidth = "none";
  let z = 1, fitted = true;
  const fitZoom = () => {
    const full = box.classList.contains("is-full");
    const w = (view.clientWidth || natW) - 16, h = (view.clientHeight || natH) - 16;
    return full ? Math.min(w / natW, h / natH) : Math.min(1, w / natW);
  };
  const apply = (next, keepCenter = true) => {
    const cx = view.scrollLeft + view.clientWidth / 2, cy = view.scrollTop + view.clientHeight / 2, old = z;
    z = Math.max(0.2, Math.min(6, next));
    svg.style.width = Math.round(natW * z) + "px";
    svg.style.height = Math.round(natH * z) + "px";
    label.textContent = Math.round(z * 100) + "%";
    if (keepCenter) { view.scrollLeft = cx * z / old - view.clientWidth / 2; view.scrollTop = cy * z / old - view.clientHeight / 2; }
    box.classList.toggle("zoomed", natW * z > view.clientWidth + 2 || natH * z > view.clientHeight + 2);
  };
  const fit = () => { fitted = true; apply(fitZoom(), false); view.scrollLeft = view.scrollTop = 0; };
  const setFull = (on) => {
    box.classList.toggle("is-full", on);
    document.body.classList.toggle("diagram-open", on);
    const btn = box.querySelector(".diagram-full-btn");
    btn.querySelector("span").textContent = on ? T.close : T.full;
    btn.setAttribute("aria-pressed", on ? "true" : "false");
    try {
      if (on && box.requestFullscreen && !document.fullscreenElement) box.requestFullscreen().catch(() => {});
      if (!on && document.fullscreenElement === box) document.exitFullscreen().catch(() => {});
    } catch (e) { /* the box still covers the window */ }
    requestAnimationFrame(fit);
    setTimeout(fit, 250);  // leaving the browser's full screen takes a moment: fit again once it's done
  };
  box.querySelector(".diagram-tools").addEventListener("click", (e) => {
    const b = e.target.closest("button");
    if (!b) return;
    fitted = false;
    if (b.dataset.z === "in") apply(z * 1.25);
    else if (b.dataset.z === "out") apply(z / 1.25);
    else if (b.dataset.z === "fit") fit();
    else if (b.dataset.z === "full") setFull(!box.classList.contains("is-full"));
  });
  document.addEventListener("fullscreenchange", () => {
    if (!document.fullscreenElement && box.classList.contains("is-full")) setFull(false);
    else if (fitted) setTimeout(fit, 50);
  });
  box.addEventListener("keydown", (e) => {
    if (e.key === "Escape" && box.classList.contains("is-full")) setFull(false);
    else if (e.key === "+" || e.key === "=") { fitted = false; apply(z * 1.25); }
    else if (e.key === "-") { fitted = false; apply(z / 1.25); }
    else if (e.key === "0") fit();
  });
  view.addEventListener("wheel", (e) => {
    if (!e.ctrlKey && !box.classList.contains("is-full")) return;  // plain scrolling still scrolls the lesson
    e.preventDefault();
    fitted = false;
    apply(z * (e.deltaY < 0 ? 1.12 : 1 / 1.12));
  }, { passive: false });
  let drag = null, pinch = null;  // one finger (or the mouse) drags a zoomed diagram; two fingers pinch to zoom
  const pts = new Map();
  const gap = () => { const [a, b] = [...pts.values()]; return Math.hypot(a.x - b.x, a.y - b.y) || 1; };
  view.addEventListener("pointerdown", (e) => {
    pts.set(e.pointerId, { x: e.clientX, y: e.clientY });
    if (pts.size === 2 && (box.classList.contains("is-full") || box.classList.contains("zoomed"))) {
      pinch = { d: gap(), z };
      drag = null;
      return;
    }
    if (!box.classList.contains("zoomed") || e.button !== 0) return;
    drag = { x: e.clientX, y: e.clientY, l: view.scrollLeft, t: view.scrollTop };
    try { view.setPointerCapture(e.pointerId); } catch (err) {}
    view.classList.add("dragging");
  });
  view.addEventListener("pointermove", (e) => {
    if (pts.has(e.pointerId)) pts.set(e.pointerId, { x: e.clientX, y: e.clientY });
    if (pinch && pts.size === 2) { fitted = false; apply(pinch.z * gap() / pinch.d); return; }
    if (!drag) return;
    view.scrollLeft = drag.l - (e.clientX - drag.x);
    view.scrollTop = drag.t - (e.clientY - drag.y);
  });
  const stop = (e) => {
    pts.delete(e.pointerId);
    if (pts.size < 2) pinch = null;
    drag = null;
    view.classList.remove("dragging");
  };
  view.addEventListener("pointerup", stop);
  view.addEventListener("pointercancel", stop);
  window.addEventListener("resize", () => { if (fitted) fit(); });
  requestAnimationFrame(fit);
  return box;
}

// Diagrams: code blocks marked "mermaid" are drawn as pictures. The drawing code (static/mermaid) is big (3 MB),
// and on a phone loading it and drawing froze the lesson for a second or more on every visit. So (v1.30.12):
//   - a diagram, once drawn, is kept on this device (by its text, light or dark, and the font) and shows
//     instantly next time, without loading the drawing code at all;
//   - a diagram that isn't kept yet is drawn only when you scroll near it, one at a time.
// A diagram with a mistake shows its text and a note.
(() => {
  const blocks = [...document.querySelectorAll("pre.mermaid")];
  if (!blocks.length) return;
  const VER = "10.9.8";
  const root = document.documentElement;
  const dark = root.dataset.theme === "dark" || (root.dataset.theme !== "light" && matchMedia("(prefers-color-scheme: dark)").matches);
  const font = getComputedStyle(document.body).fontFamily;
  const hash = (str) => { let h = 2166136261; for (let i = 0; i < str.length; i++) { h ^= str.charCodeAt(i); h = Math.imul(h, 16777619); } return (h >>> 0).toString(36); };
  const IDX = "inpace-dg-index", LIMIT = 2500000;  // about 2.5 MB of diagrams kept; the oldest go first
  const store = {
    get(k) { try { return localStorage.getItem("inpace-dg:" + k); } catch (e) { return null; } },
    put(k, svg) {
      try {
        let idx = JSON.parse(localStorage.getItem(IDX) || "[]").filter((x) => x.k !== k);
        idx.push({ k, n: svg.length });
        let total = idx.reduce((a, x) => a + x.n, 0);
        while (idx.length > 1 && total > LIMIT) { const old = idx.shift(); total -= old.n; localStorage.removeItem("inpace-dg:" + old.k); }
        for (;;) {
          try { localStorage.setItem("inpace-dg:" + k, svg); break; } catch (e) {  // full: make room, else give up
            if (idx.length <= 1) return;
            localStorage.removeItem("inpace-dg:" + idx.shift().k);
          }
        }
        localStorage.setItem(IDX, JSON.stringify(idx));
      } catch (e) { /* private window: draw every time, as before */ }
    },
  };
  const keyOf = (text) => hash(`${VER}|${dark ? "d" : "l"}|${font}|${text}`);
  const failed = (pre) => {
    pre.classList.add("diagram-error");
    const note = document.createElement("span");
    note.className = "diagram-note";
    note.textContent = root.lang === "ar" ? "هذا الرسم فيه خطأ، فيظهر نصه بدلًا منه." : "This diagram has a mistake, so its text shows instead.";
    pre.appendChild(note);
  };
  const todo = [];
  for (const pre of blocks) {
    const k = keyOf(pre.textContent), svg = store.get(k);
    if (svg) pre.replaceWith(diagramBox(svg)); else todo.push({ pre, k });
  }
  if (!todo.length) return;
  let ready = null, queue = Promise.resolve();
  const load = () => ready || (ready = new Promise((ok, no) => {
    const s = document.createElement("script");
    s.src = "/static/mermaid/mermaid.min.js?v=" + VER;
    s.onload = () => {
      window.mermaid.initialize({ startOnLoad: false, securityLevel: "strict", theme: dark ? "dark" : "default", fontFamily: font });
      ok(window.mermaid);
    };
    s.onerror = no;
    document.head.appendChild(s);
  }));
  const draw = ({ pre, k }) => { queue = queue.then(async () => {
    if (!pre.isConnected) return;
    try {
      const m = await load();
      const text = pre.textContent;
      await m.parse(text);
      const { svg } = await m.render("dg-" + k, text);  // the id comes from the text, so kept diagrams never clash
      pre.replaceWith(diagramBox(svg));
      store.put(k, svg);
    } catch (e) { failed(pre); }
    await new Promise((r) => setTimeout(r, 30));  // let the page breathe between diagrams
  }); };
  if (!("IntersectionObserver" in window)) { todo.forEach(draw); return; }
  const io = new IntersectionObserver((seen) => {
    for (const e of seen) if (e.isIntersecting) { io.unobserve(e.target); draw(todo.find((x) => x.pre === e.target)); }
  }, { rootMargin: "900px 0px" });
  todo.forEach((x) => io.observe(x.pre));
})();

// Pictures in a lesson open in a viewer: fit to the screen, zoom with the buttons, the mouse wheel, + and −, or two
// fingers; drag to move around; double-click (or double-tap) to zoom in or fit again; ← and → for the other pictures
// of the lesson; Escape closes it. The page behind stays where it was.
(() => {
  const imgs = [...document.querySelectorAll(".prose img")].filter((img) => !img.closest("a, .diagram-box, .code-wrap"));
  if (!imgs.length) return;
  const ar = document.documentElement.lang === "ar";
  const T = ar ? { open: "تكبير الصورة", out: "تصغير", in: "تكبير", fit: "ملاءمة الشاشة", real: "الحجم الأصلي", rot: "تدوير",
                   prev: "الصورة السابقة", next: "الصورة التالية", close: "إغلاق", orig: "فتح الصورة وحدها", of: "من" }
               : { open: "Zoom into the picture", out: "Zoom out", in: "Zoom in", fit: "Fit to screen", real: "Actual size", rot: "Rotate",
                   prev: "Previous picture", next: "Next picture", close: "Close", orig: "Open the picture on its own", of: "of" };
  const P = { out: '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5M8 11h6"/>', in: '<circle cx="11" cy="11" r="7"/><path d="m20 20-3.5-3.5M8 11h6M11 8v6"/>',
              fit: '<path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5"/>', real: '<rect x="3" y="5" width="18" height="14" rx="1"/><path d="M8 10v5M12 10v.01M12 14v.01M16 10v5"/>',
              rot: '<path d="M20 11a8 8 0 1 0-2.3 5.7"/><path d="M20 4v7h-7"/>', prev: '<path d="M15 5l-7 7 7 7"/>', next: '<path d="M9 5l7 7-7 7"/>',
              close: '<path d="M6 6l12 12M18 6 6 18"/>', orig: '<path d="M14 4h6v6M20 4l-9 9M18 14v6H4V6h6"/>' };
  const svg = (k) => `<svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.9" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${P[k]}</svg>`;
  const btn = (k) => `<button type="button" class="iv-btn" data-iv="${k}" title="${T[k]}" aria-label="${T[k]}">${svg(k)}</button>`;

  // A small button on each picture (and a click on the picture) opens the viewer.
  imgs.forEach((img, i) => {
    const holder = img.closest("figure") || img.parentElement;
    holder.classList.add("iv-holder");
    img.classList.add("iv-zoomable");
    img.addEventListener("click", () => open(i));
    const b = document.createElement("button");
    b.type = "button"; b.className = "iv-open"; b.title = T.open; b.setAttribute("aria-label", T.open); b.innerHTML = svg("fit");
    b.addEventListener("click", () => open(i));
    img.insertAdjacentElement("afterend", b);
  });

  let dlg, stage, pic, cap, label, counter, idx = 0, s = 1, fitS = 1, x = 0, y = 0, rot = 0, natW = 1, natH = 1, back = null;
  const MIN = 0.05, MAX = 8;
  function make() {
    dlg = document.createElement("div");
    dlg.className = "iv"; dlg.setAttribute("role", "dialog"); dlg.setAttribute("aria-modal", "true"); dlg.dir = "ltr";
    dlg.innerHTML = `<div class="iv-bar" role="toolbar">
        <span class="iv-count" aria-live="polite"></span>${btn("prev")}${btn("next")}
        <span class="iv-gap"></span>${btn("out")}<span class="iv-zoom" aria-live="polite">100%</span>${btn("in")}${btn("fit")}${btn("real")}${btn("rot")}
        <a class="iv-btn" data-iv="orig" target="_blank" rel="noopener" title="${T.orig}" aria-label="${T.orig}">${svg("orig")}</a>${btn("close")}
      </div><div class="iv-stage"><img class="iv-pic" alt="" draggable="false"></div><p class="iv-cap" dir="auto"></p>`;
    document.body.appendChild(dlg);
    stage = dlg.querySelector(".iv-stage"); pic = dlg.querySelector(".iv-pic"); cap = dlg.querySelector(".iv-cap");
    label = dlg.querySelector(".iv-zoom"); counter = dlg.querySelector(".iv-count");
    dlg.querySelector(".iv-bar").addEventListener("click", (e) => {
      const b = e.target.closest("[data-iv]");
      if (!b || b.dataset.iv === "orig") return;
      ({ prev: () => show(idx - 1), next: () => show(idx + 1), in: () => zoom(s * 1.25), out: () => zoom(s / 1.25),
         fit: fitNow, real: () => zoom(1), rot: () => { rot = (rot + 90) % 360; measure(); fitNow(); }, close })[b.dataset.iv]();
    });
    stage.addEventListener("wheel", (e) => {
      e.preventDefault();
      const f = Math.exp(-Math.max(-60, Math.min(60, e.deltaY)) * (e.ctrlKey ? 0.01 : 0.004));
      zoom(s * f, point(e));
    }, { passive: false });
    // One pointer drags, two pinch. A quick second click or tap zooms in where you tapped, or fits again.
    const pts = new Map();
    let drag = null, pinch = null, lastTap = 0;
    const gap = () => { const [a, b] = [...pts.values()]; return Math.hypot(a.x - b.x, a.y - b.y) || 1; };
    const mid = () => { const [a, b] = [...pts.values()]; const r = stage.getBoundingClientRect(); return { x: (a.x + b.x) / 2 - r.left, y: (a.y + b.y) / 2 - r.top }; };
    stage.addEventListener("pointerdown", (e) => {
      pts.set(e.pointerId, { x: e.clientX, y: e.clientY });
      try { stage.setPointerCapture(e.pointerId); } catch (err) {}
      if (pts.size === 2) { pinch = { d: gap(), s, m: mid(), x, y }; drag = null; return; }
      const now = Date.now();
      if (now - lastTap < 320) { lastTap = 0; s > fitS * 1.05 ? fitNow() : zoom(Math.max(fitS * 2.5, 1), point(e)); return; }
      lastTap = now;
      drag = { px: e.clientX, py: e.clientY, x, y };
      stage.classList.add("dragging");
    });
    stage.addEventListener("pointermove", (e) => {
      if (!pts.has(e.pointerId)) return;
      pts.set(e.pointerId, { x: e.clientX, y: e.clientY });
      if (pinch && pts.size === 2) {
        const m = mid(), ns = clamp(pinch.s * gap() / pinch.d);
        x = m.x - (pinch.m.x - pinch.x) * ns / pinch.s; y = m.y - (pinch.m.y - pinch.y) * ns / pinch.s; s = ns;
        place(); return;
      }
      if (drag) { x = drag.x + e.clientX - drag.px; y = drag.y + e.clientY - drag.py; place(); }
    });
    const up = (e) => { pts.delete(e.pointerId); if (pts.size < 2) pinch = null; if (!pts.size) { drag = null; stage.classList.remove("dragging"); } };
    stage.addEventListener("pointerup", up); stage.addEventListener("pointercancel", up);
    dlg.addEventListener("keydown", (e) => {
      const big = s > fitS * 1.02, step = 60;
      const k = e.key;
      if (k === "Escape") { e.preventDefault(); close(); }
      else if (k === "+" || k === "=") { e.preventDefault(); zoom(s * 1.25); }
      else if (k === "-" || k === "_") { e.preventDefault(); zoom(s / 1.25); }
      else if (k === "0") { e.preventDefault(); fitNow(); }
      else if (k === "1") { e.preventDefault(); zoom(1); }
      else if (k === "ArrowLeft" || k === "ArrowRight") {
        e.preventDefault();
        if (big) { x += k === "ArrowLeft" ? step : -step; place(); }
        else show(idx + ((k === "ArrowRight") !== ar ? 1 : -1));
      } else if ((k === "ArrowUp" || k === "ArrowDown") && big) { e.preventDefault(); y += k === "ArrowUp" ? step : -step; place(); }
      else if (k === "Tab") {  // keep the focus inside the viewer
        const f = [...dlg.querySelectorAll(".iv-btn:not([hidden]):not(:disabled)")];
        const i = f.indexOf(document.activeElement);
        e.preventDefault();
        f[(i + (e.shiftKey ? -1 : 1) + f.length) % f.length].focus();
      }
    });
    window.addEventListener("resize", () => { if (dlg.classList.contains("on")) fitNow(); });
  }
  const clamp = (v) => Math.max(MIN, Math.min(MAX, v));
  const point = (e) => { const r = stage.getBoundingClientRect(); return { x: e.clientX - r.left, y: e.clientY - r.top }; };
  // The picture's size on screen, turned.
  const box = () => (rot % 180 ? { w: natH * s, h: natW * s } : { w: natW * s, h: natH * s });
  function place() {
    const W = stage.clientWidth, H = stage.clientHeight, b = box();
    // Smaller than the screen: keep it in the middle. Bigger: don't let it slide away from the edges.
    x = b.w <= W ? (W - b.w) / 2 : Math.min(0, Math.max(W - b.w, x));
    y = b.h <= H ? (H - b.h) / 2 : Math.min(0, Math.max(H - b.h, y));
    const cx = x + b.w / 2, cy = y + b.h / 2;
    pic.style.width = natW + "px"; pic.style.height = natH + "px";
    pic.style.transform = `translate(${cx - natW / 2}px, ${cy - natH / 2}px) rotate(${rot}deg) scale(${s})`;
    label.textContent = Math.round(s * 100) + "%";
    stage.classList.toggle("big", b.w > W + 1 || b.h > H + 1);
    dlg.querySelector('[data-iv="out"]').disabled = s <= MIN;
    dlg.querySelector('[data-iv="in"]').disabled = s >= MAX;
  }
  function zoom(next, at) {
    const W = stage.clientWidth, H = stage.clientHeight;
    at = at || { x: W / 2, y: H / 2 };
    const ns = clamp(next);
    x = at.x - (at.x - x) * ns / s; y = at.y - (at.y - y) * ns / s; s = ns;
    place();
  }
  function measure() {
    const W = stage.clientWidth, H = stage.clientHeight;
    const w = rot % 180 ? natH : natW, h = rot % 180 ? natW : natH;
    fitS = Math.min(1, (W - 24) / w, (H - 24) / h);
  }
  function fitNow() { measure(); s = fitS; x = y = 0; place(); }
  function show(i) {
    idx = (i + imgs.length) % imgs.length;
    const img = imgs[idx];
    rot = 0;
    const done = () => { natW = pic.naturalWidth || img.naturalWidth || 800; natH = pic.naturalHeight || img.naturalHeight || 600; fitNow(); };
    pic.onload = done;
    pic.src = img.currentSrc || img.src;
    pic.alt = img.alt || "";
    if (pic.complete && pic.naturalWidth) done();
    const fc = img.closest("figure") && img.closest("figure").querySelector("figcaption");
    cap.textContent = (fc && fc.textContent) || img.alt || "";
    cap.hidden = !cap.textContent;
    dlg.querySelector('[data-iv="orig"]').href = pic.src;
    const many = imgs.length > 1;
    counter.textContent = many ? `${idx + 1} ${T.of} ${imgs.length}` : "";
    dlg.querySelectorAll('[data-iv="prev"], [data-iv="next"]').forEach((b) => (b.hidden = !many));
  }
  function open(i) {
    if (!dlg) make();
    back = document.activeElement;
    dlg.classList.add("on");
    document.body.classList.add("iv-open-page");
    show(i);
    dlg.querySelector('[data-iv="close"]').focus();
  }
  function close() {
    dlg.classList.remove("on");
    document.body.classList.remove("iv-open-page");
    if (back && back.focus) back.focus({ preventScroll: true });
  }
})();

// Notes on a lesson. Select some of the lesson and a "Take a note" button appears next to it (under it on touch
// screens, where the phone's own menu sits above). It saves the sentence you selected and what you write, without
// leaving the page. Sentences you took notes on are highlighted, and "Show in the lesson" scrolls back to one.
(() => {
  const prose = document.querySelector(".prose[data-notes]");
  const list = document.getElementById("note-list");
  if (!prose || !list) return;
  const ar = document.documentElement.lang === "ar";
  const T = ar ? { take: "دوّن ملاحظة", save: "احفظ الملاحظة", cancel: "إلغاء", ph: "ملاحظتك (اختيارية)", fail: "تعذّر حفظ الملاحظة. هل inPace ما زال مفتوحًا؟", saved: "حُفظت الملاحظة" }
               : { take: "Take a note", save: "Save note", cancel: "Cancel", ph: "Your note (optional)", fail: "Couldn't save the note. Is inPace still open?", saved: "Note saved" };
  const pen = '<svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M4 20h4L19 9l-4-4L4 16z"/><path d="m13.5 6.5 4 4"/></svg>';
  const touch = matchMedia("(pointer: coarse)").matches;

  const fab = document.createElement("button");
  fab.type = "button"; fab.className = "note-fab"; fab.hidden = true; fab.innerHTML = `${pen}<span>${T.take}</span>`;
  const pop = document.createElement("div");
  pop.className = "note-pop"; pop.hidden = true; pop.setAttribute("role", "dialog"); pop.setAttribute("aria-label", T.take);
  pop.innerHTML = `<blockquote dir="auto"></blockquote><textarea rows="3" dir="auto" placeholder="${T.ph}"></textarea>
    <p class="note-pop-err small" hidden></p>
    <div class="row wrap"><button type="button" class="btn primary" data-save>${T.save}</button><button type="button" class="btn ghost" data-cancel>${T.cancel}</button></div>`;
  document.body.append(fab, pop);
  const area = pop.querySelector("textarea"), err = pop.querySelector(".note-pop-err");
  let quote = "", where = null;

  const picked = () => {
    const sel = getSelection();
    if (!sel.rangeCount || sel.isCollapsed) return null;
    const r = sel.getRangeAt(0);
    if (!prose.contains(r.commonAncestorContainer)) return null;
    const text = sel.toString().replace(/\s+/g, " ").trim();
    return text.length >= 2 ? { r, text } : null;
  };
  // Next to the selection, inside the window: above it with a mouse, under it on touch screens.
  const place = (el, rect, below) => {
    const w = el.offsetWidth, h = el.offsetHeight;
    let top = below || rect.top < h + 16 ? rect.bottom + 10 : rect.top - h - 10;
    top = Math.min(top, innerHeight - h - 8);
    const left = Math.max(8, Math.min(innerWidth - w - 8, rect.left + rect.width / 2 - w / 2));
    el.style.top = top + scrollY + "px"; el.style.left = left + scrollX + "px";
  };
  let timer;
  const update = () => {
    if (!pop.hidden) return;
    const p = picked();
    if (!p) { fab.hidden = true; return; }
    quote = p.text.slice(0, 2000);
    where = p.r.getBoundingClientRect();
    fab.hidden = false;
    place(fab, where, touch);
  };
  document.addEventListener("selectionchange", () => { clearTimeout(timer); timer = setTimeout(update, touch ? 350 : 150); });
  fab.addEventListener("pointerdown", (e) => e.preventDefault());  // keep the selection while pressing
  const close = () => { pop.hidden = true; err.hidden = true; };
  fab.addEventListener("click", () => {
    fab.hidden = true;
    pop.querySelector("blockquote").textContent = quote;
    area.value = "";
    pop.hidden = false;
    place(pop, where, touch);
    area.focus({ preventScroll: true });
  });
  pop.querySelector("[data-cancel]").addEventListener("click", close);
  const save = async () => {
    const body = new FormData();
    body.append("quote", quote); body.append("text", area.value);
    const btn = pop.querySelector("[data-save]");
    btn.disabled = true;
    try {
      const res = await fetch(prose.dataset.notes, { method: "POST", body, headers: { "X-Inpace-Fetch": "1" } });
      if (!res.ok) throw new Error(await res.text());
      list.insertAdjacentHTML("beforeend", await res.text());
      const count = document.querySelector("[data-note-count]");
      if (count) { count.textContent = list.children.length; count.hidden = false; }
      close();
      getSelection().removeAllRanges();
      paint();
      const done = document.createElement("div");
      done.className = "note-saved"; done.setAttribute("role", "status"); done.textContent = T.saved;
      document.body.appendChild(done);
      setTimeout(() => done.remove(), 1800);
    } catch (e) {
      err.textContent = (e && e.message && e.message.length < 200 && !/fetch|network/i.test(e.message)) ? e.message : T.fail;
      err.hidden = false;
    } finally { btn.disabled = false; }
  };
  pop.querySelector("[data-save]").addEventListener("click", save);
  pop.addEventListener("keydown", (e) => {
    if (e.key === "Escape") { e.preventDefault(); close(); }
    else if (e.key === "Enter" && (e.ctrlKey || e.metaKey)) { e.preventDefault(); save(); }
  });
  document.addEventListener("pointerdown", (e) => { if (!pop.hidden && !pop.contains(e.target)) close(); });

  // Find a saved sentence in the lesson again. Spaces and line breaks are ignored, because the text you select
  // across paragraphs and the text inside the page are spaced differently.
  const find = (q) => {
    const want = q.replace(/\s+/g, "");
    if (!want) return null;
    const walk = document.createTreeWalker(prose, NodeFilter.SHOW_TEXT, {
      acceptNode: (n) => n.parentElement.closest("button, .code-bar, .iv-open, .diagram-tools, script, style") ? NodeFilter.FILTER_REJECT : NodeFilter.FILTER_ACCEPT });
    let flat = ""; const at = [];
    for (let n = walk.nextNode(); n; n = walk.nextNode()) {
      const t = n.nodeValue;
      for (let i = 0; i < t.length; i++) if (!/\s/.test(t[i])) { flat += t[i]; at.push([n, i]); }
    }
    const i = flat.indexOf(want);
    if (i < 0) return null;
    const r = document.createRange();
    r.setStart(at[i][0], at[i][1]);
    const end = at[i + want.length - 1];
    r.setEnd(end[0], end[1] + 1);
    return r;
  };
  const canPaint = window.CSS && CSS.highlights && typeof Highlight === "function";
  const paint = () => {
    if (!canPaint) return;
    const ranges = [...list.querySelectorAll("[data-quote]")].map((el) => find(el.dataset.quote)).filter(Boolean);
    CSS.highlights.set("inpace-notes", new Highlight(...ranges));
  };
  list.addEventListener("click", (e) => {
    const b = e.target.closest("[data-show-note]");
    if (!b) return;
    const r = find(b.closest("[data-quote]").dataset.quote);
    if (!r) return;
    const rect = r.getBoundingClientRect();
    scrollTo({ top: scrollY + rect.top - innerHeight / 3, behavior: matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
    if (canPaint) { CSS.highlights.set("inpace-note-now", new Highlight(r)); setTimeout(() => CSS.highlights.delete("inpace-note-now"), 2200); }
  });
  // Diagrams and pictures change the lesson after it loads, so paint again once they're in place.
  paint();
  setTimeout(paint, 1500);
})();

// Code blocks: language label + copy button.
document.querySelectorAll(".prose pre:not(.mermaid)").forEach((pre) => {
  const code = pre.querySelector("code");
  if (!code) return;
  const wrap = document.createElement("div");
  wrap.className = "code-wrap";
  pre.parentNode.insertBefore(wrap, pre);
  wrap.appendChild(pre);
  const lang = ((code.className.match(/language-([\w+-]+)/) || [])[1] || "code");
  const bar = document.createElement("div");
  bar.className = "code-bar";
  bar.innerHTML = `<span>${lang}</span><button type="button">Copy</button>`;
  wrap.appendChild(bar);
  const btn = bar.querySelector("button");
  const label = document.documentElement.lang === "ar" ? ["نسخ", "تم النسخ!"] : ["Copy", "Copied!"];
  btn.textContent = label[0];
  btn.addEventListener("click", async () => {
    try { await navigator.clipboard.writeText(code.innerText); } catch (e) {}
    btn.textContent = label[1];
    setTimeout(() => (btn.textContent = label[0]), 1500);
  });
});

// Celebration toast and a short burst of confetti.
function burstConfetti() {
  if (matchMedia("(prefers-reduced-motion: reduce)").matches) return;
  const c = document.createElement("canvas");
  c.className = "confetti";
  document.body.appendChild(c);
  const ctx = c.getContext("2d");
  c.width = innerWidth * devicePixelRatio; c.height = innerHeight * devicePixelRatio;
  const colors = ["#1F7A56", "#9FF0C8", "#F2B84B", "#7FB0F0", "#FF8FA3", "#3A506B"];
  const bits = Array.from({ length: 140 }, () => ({
    x: Math.random() * c.width, y: -Math.random() * c.height * 0.5, r: (4 + Math.random() * 5) * devicePixelRatio,
    vx: (Math.random() - 0.5) * 3, vy: 2 + Math.random() * 4, a: Math.random() * 6, va: (Math.random() - 0.5) * 0.3,
    color: colors[Math.floor(Math.random() * colors.length)],
  }));
  const start = performance.now();
  const frame = (t) => {
    ctx.clearRect(0, 0, c.width, c.height);
    for (const b of bits) {
      b.x += b.vx * devicePixelRatio; b.y += b.vy * devicePixelRatio; b.a += b.va; b.vy += 0.03;
      ctx.save(); ctx.translate(b.x, b.y); ctx.rotate(b.a); ctx.fillStyle = b.color;
      ctx.fillRect(-b.r / 2, -b.r / 4, b.r, b.r / 2); ctx.restore();
    }
    if (t - start < 3200) requestAnimationFrame(frame); else c.remove();
  };
  requestAnimationFrame(frame);
}
const closeYay = (yay) => { if (!yay.isConnected) return; yay.classList.add("out"); setTimeout(() => yay.remove(), 300); };
document.addEventListener("click", (e) => { const b = e.target.closest && e.target.closest(".yay-close"); if (b) closeYay(b.closest(".yay")); });
document.querySelectorAll(".yay").forEach((yay, i) => {
  setTimeout(() => closeYay(yay), 7000 + i * 1500);
  if (i === 0 && yay.hasAttribute("data-confetti")) burstConfetti();
});

// Small notice used by the app window (e.g. "Saved to Downloads: file.json").
window.inpaceToast = (text) => {
  const t = document.createElement("div");
  t.className = "mini-toast";
  t.setAttribute("role", "status");
  t.textContent = document.documentElement.lang === "ar" ? text.replace("Saved to Downloads:", "حُفظ في التنزيلات:") : text;
  document.body.appendChild(t);
  setTimeout(() => { t.classList.add("out"); setTimeout(() => t.remove(), 300); }, 4000);
};


// Online videos load only when you press play (nothing reaches the internet before that).
document.querySelectorAll(".embed-box").forEach((box) => {
  const btn = box.querySelector(".play");
  if (!btn) return;
  btn.addEventListener("click", () => {
    if (box.dataset.ytId && window.inpacePlayer && ytRules(box).own_controls !== false) { youtubeAsPlayer(box); return; }
    let el;
    if (box.dataset.embed) {
      el = document.createElement("iframe");
      el.src = box.dataset.ytKey ? youtubeSrc(box) : box.dataset.embed;
      el.allow = "autoplay; encrypted-media; picture-in-picture; fullscreen";
      el.allowFullscreen = true;
      el.referrerPolicy = "strict-origin-when-cross-origin";
      el.title = btn.textContent.trim();
    } else {
      const tag = box.dataset.embedVideo ? "video" : "audio";
      el = document.createElement(tag);
      el.src = box.dataset.embedVideo || box.dataset.embedAudio;
      el.controls = true;
      el.autoplay = true;
    }
    const wrap = document.createElement("div");
    wrap.className = el.tagName === "IFRAME" ? "frame-wrap video-ratio" : "";
    wrap.appendChild(el);
    box.replaceWith(wrap);
    if (box.dataset.ytKey) { youtubeRemember(el, box); youtubeExtras(el, box, wrap); }
  });
  const restart = box.querySelector("[data-yt-restart]");
  if (restart) restart.addEventListener("click", () => { box.dataset.resume = "0"; restart.parentElement.hidden = true; btn.click(); });
});

// YouTube in inPace's own player. The video plays in YouTube's frame, but YouTube's buttons are hidden
// (controls=0), a cover stops its title, logo and "More videos" from showing, and inPace's player drives it
// through YouTube's messages. To the player it looks like a <video>.
// The rules come from the inPace website once a day (Settings never needed): numbers and switches only.
function ytRules(box) {
  const R = { own_controls: true, fallback_ms: 9000, cover_after_ms: 2500, confirm_after_s: 3, long_video_s: 60,
              ad_shorter_by_s: 2, quality_menu: true, ad_guard: true };
  try { Object.assign(R, JSON.parse(box.dataset.ytRules || "{}")); } catch (e) {}
  return R;
}

// WebVTT subtitles into [{a, b, text}] (seconds). YouTube's automatic ones repeat the previous line as it rolls up:
// only each cue's newest line is kept, without the word-timing tags.
function parseVtt(text) {
  const sec = (s) => { const p = s.trim().split(":").map(parseFloat); return p.length === 3 ? p[0] * 3600 + p[1] * 60 + p[2] : p[0] * 60 + p[1]; };
  const out = [];
  for (const block of String(text || "").replace(/\r/g, "").split(/\n\n+/)) {
    const lines = block.split("\n");
    const i = lines.findIndex((l) => l.includes("-->"));
    if (i < 0) continue;
    const [a, b] = lines[i].split("-->").map((x) => sec(x.split(" ").filter(Boolean)[0] || "0"));
    const body = lines.slice(i + 1).map((l) => l.replace(/<[^>]+>/g, "").trim()).filter(Boolean);
    if (!body.length || !(b > a)) continue;
    out.push({ a, b, text: body.join("\n") });
  }
  // rolling captions: drop a cue that only repeats the one before, and show the newest line of each
  return out.filter((c, k) => !(k && c.text === out[k - 1].text && c.b - c.a < 0.05)).map((c) => {
    const ls = c.text.split("\n"); return ls.length > 1 && /align:start/.test(text) ? { ...c, text: ls[ls.length - 1] } : c;
  });
}

class YouTubeMedia extends EventTarget {
  constructor(frame, cover, id, from, R) {
    super();
    this.frame = frame; this.clickTarget = cover; this.id = id || ""; this.from = from || 0; this.R = R || ytRules({ dataset: {} });
    this._confirmed = this.R.ad_guard === false; this._inAd = false; this._vidOk = null;  // no ad guard: take every report as the lesson
    this.paused = true; this.ended = false; this.duration = 0; this.readyState = 0; this.error = null;
    this._t = 0; this._vol = 1; this._muted = false; this._rate = 1; this._started = false;
    this.buffered = { length: 0, end: () => 0 }; this.videoWidth = 16; this.videoHeight = 9; this.ccQuiet = true;
    // Subtitles: inPace asks which languages the video has (yt-dlp, on this computer), and shows the one you pick
    // in its own style over the video. YouTube's captions are never switched on, so only the video shows.
    this.textTracks = []; this.subsLater = !!this.id; this.subsLoading = false; this.subsWhy = "";
    this._subsBox = null; this._cues = [];
    addEventListener("message", (ev) => this._hear(ev));
    this.addEventListener("timeupdate", () => this._drawSub());
    const hello = () => { try { frame.contentWindow.postMessage(JSON.stringify({ event: "listening", id: "inpace", channel: "widget" }), "*"); } catch (e) {} };
    // Say hello until YouTube answers: on a busy phone (another video still loaded, a page in the mini player's
    // frame) its player can take longer than a few seconds to start listening, and without an answer inPace
    // would switch to YouTube's own player and buttons.
    this.addEventListener("ythello", () => { this._heard = true; }, { once: true });
    frame.addEventListener("load", () => {
      hello(); let n = 0;
      clearInterval(this._hi); this._hi = setInterval(() => { if (this._heard || ++n > 30 || !frame.isConnected) clearInterval(this._hi); else hello(); }, 700);
      setTimeout(() => { this._cmd("addEventListener", ["onError"]); this._cmd("addEventListener", ["onStateChange"]); }, 300); });
  }
  _cmd(func, args) { try { this.frame.contentWindow.postMessage(JSON.stringify({ event: "command", func, args: args || [] }), "*"); } catch (e) {} }
  loadSubs() {  // once: the list of languages, as text tracks the CC menu can show
    if (!this.id || this.subsLoading || this._subsAsked) return;
    this._subsAsked = true; this.subsLoading = true; this._fire("yttracks");
    fetch(`/yt-subs/${encodeURIComponent(this.id)}.json`).then((r) => r.json()).then((d) => {
      const self = this;
      this.textTracks = (d.tracks || []).map((x) => this._track(x.label, x.lang, x.from || ""));
      this.subsWhy = d.why || "";
    }).catch(() => { this.subsWhy = "x"; }).finally(() => {
      this.subsLoading = false;
      // inPace couldn't read the list (yt-dlp failed on this device): YouTube's own subtitles are still there.
      if (!this.textTracks.length && this.subsWhy) this._useYouTubeList();
      this._fire("yttracks");
    });
  }
  // One subtitle language for the CC menu. Showing it: inPace draws it over the video in its own style; if inPace
  // can't get its text, YouTube shows that language itself. Turning it off turns off both.
  _track(label, lang, from, onlyYouTube) {
    const self = this;
    return { label, language: lang, from, _m: "disabled", _yt: !!onlyYouTube,
      get mode() { return this._m; },
      set mode(m) {
        this._m = m;
        if (m === "showing") self._showSub(this);
        else if (self._shown === this) self._showSub(null);
      } };
  }
  _useYouTubeList() {
    const L = (this.frame.parentElement && this.frame.parentElement.dataset) || {};
    const list = this.ytList && this.ytList.length ? this.ytList : [{ lang: "", label: L.lCcyt || "Subtitles (YouTube)" }];
    let was = this._shown && this._shown.language;
    if (was === "" && this.ytList && this.ytList.length) was = this.ytNow || this.ytList[0].lang;  // YouTube's choice was showing
    this.textTracks = list.map((x) => this._track(x.label, x.lang, "", true));
    if (was !== undefined && was !== null) {
      const t = this.textTracks.find((x) => x.language === was) || null;
      if (t) { t._m = "showing"; this._shown = t; }
    }
  }
  // YouTube's own subtitles, through its player's messages. lang null: off.
  _ytCaptions(lang, from) {
    if (lang === null) {
      if (this._ytCc === null) return;
      this._ytCc = null;
      this._cmd("setOption", ["captions", "track", {}]);
      this._cmd("unloadModule", ["captions"]);
      return;
    }
    this._ytCc = lang;
    const track = from ? { languageCode: from, translationLanguage: { languageCode: lang } } : (lang ? { languageCode: lang } : null);
    this._cmd("loadModule", ["captions"]);
    if (track) {
      this._cmd("setOption", ["captions", "track", track]);
      setTimeout(() => { if (this._ytCc === lang) this._cmd("setOption", ["captions", "track", track]); }, 700);  // once the module is in
    }
  }
  _showSub(track) {
    this._shown = track; this._cues = [];
    if (!this._subsBox) {
      this._subsBox = document.createElement("div"); this._subsBox.className = "yt-subs"; this._subsBox.setAttribute("aria-live", "off");
      this.frame.parentElement.appendChild(this._subsBox);
    }
    this._subsBox.textContent = ""; this._subsBox.hidden = true;
    if (!track) { this._ytCaptions(null); return; }
    if (track._yt) { this._ytCaptions(track.language, track.from); return; }
    this._ytCaptions(null);
    fetch(`/yt-subs/${encodeURIComponent(this.id)}/${encodeURIComponent(track.language)}.vtt`).then((r) => (r.ok ? r.text() : ""))
      .catch(() => "").then((text) => {
        if (this._shown !== track) return;
        this._cues = parseVtt(text);
        if (this._cues.length) this._drawSub();
        else this._ytCaptions(track.language, track.from);  // inPace couldn't get the text: YouTube shows it
      });
  }
  _drawSub() {
    if (!this._subsBox) return;
    const t = this._t, c = this._cues.find((x) => t >= x.a && t < x.b);
    const line = c ? c.text : "";
    if (this._subsBox.textContent !== line) { this._subsBox.textContent = line; this._subsBox.hidden = !line; }
  }
  _fire(name) { this.dispatchEvent(new Event(name)); }
  _hear(ev) {
    if (ev.source !== this.frame.contentWindow) return;
    let d = ev.data;
    try { if (typeof d === "string") d = JSON.parse(d); } catch (e) { return; }
    if (!d || typeof d !== "object") return;
    if (d.event === "onError") { this.error = { code: d.info }; this._fire("yterror"); return; }
    const i = d.info;
    if (!i || typeof i !== "object") return;
    // YouTube's own list of subtitle languages (it sends it once its subtitles are loaded)
    const caps = i.captions && (i.captions.tracklist || i.captions.trackList);
    if (i.captions && i.captions.track && i.captions.track.languageCode) this.ytNow = i.captions.track.languageCode;
    if (Array.isArray(caps) && caps.length && !this.ytList) {
      this.ytList = caps.map((t) => ({ lang: t.languageCode || "", label: t.displayName || t.languageName || t.languageCode || "" }))
        .filter((t) => t.lang);
      if (this.ytList.length && this.textTracks.length && this.textTracks.every((t) => t._yt)) { this._useYouTubeList(); this._fire("yttracks"); }
    }
    if (d.event === "apiInfoDelivery") return;
    this._fire("ythello");
    // Ads: while YouTube plays an ad it reports the ad's time and length. Until we're sure the lesson's video
    // is playing (it reached the second we asked for, or it's the right video, or it's longer than an ad),
    // and whenever a shorter "video" appears in the middle, nothing is saved and the bar doesn't move.
    const vd = i.videoData;
    if (vd && typeof vd === "object" && vd.video_id) this._vidOk = vd.video_id === this.id;
    const dur = typeof i.duration === "number" && i.duration > 0 ? i.duration : 0;
    const t = typeof i.currentTime === "number" ? i.currentTime : null;
    const R = this.R;
    let ad = R.ad_guard !== false && (this._vidOk === false || (this._confirmed && dur && this.duration && dur < this.duration - R.ad_shorter_by_s));
    if (!this._confirmed && !ad && (this._vidOk === true || (this.from > 5 && t !== null && t >= this.from - 3)
        || (this.from <= 5 && (dur > R.long_video_s || (t !== null && t >= R.confirm_after_s))))) this._confirmed = true;
    // A longer video after the one we took for the lesson: that one was an ad, this is the lesson.
    if (this._confirmed && !ad && dur && this.duration && dur > this.duration + 2) { this.duration = dur; this._fire("loadedmetadata"); }
    const inAd = ad || !this._confirmed;
    if (inAd !== this._inAd) { this._inAd = inAd; this._fire(inAd ? "ytad" : "ytmain"); }
    if (!inAd) {
      if (dur && !this.duration) {
        this.duration = dur; this.readyState = 1; this._fire("loadedmetadata");
        if (this._vol !== 1) this._cmd("setVolume", [Math.round(this._vol * 100)]);
        if (this._rate !== 1) this._cmd("setPlaybackRate", [this._rate]);
      }
      if (t !== null) { this._t = t; this._fire("timeupdate"); }
    }
    // The qualities this video has, and the one playing now (YouTube reports both while it plays).
    if (Array.isArray(i.availableQualityLevels) && i.availableQualityLevels.join() !== (this.qualities || []).join()) {
      this.qualities = i.availableQualityLevels.slice(); this._fire("ytquality");
    }
    if (typeof i.playbackQuality === "string" && i.playbackQuality !== this.quality) { this.quality = i.playbackQuality; this._fire("ytquality"); }
    if (typeof i.muted === "boolean") this._muted = i.muted;
    if (typeof i.volume === "number") this._vol = i.volume / 100;
    if (typeof i.videoLoadedFraction === "number" && this.duration && !inAd) {
      const f = i.videoLoadedFraction; this.buffered = { length: 1, end: () => f * this.duration }; this._fire("progress");
    }
    if (typeof i.playerState === "number") {
      const st = i.playerState;
      this._st = st;
      if (st === 1 && !this._capsOff) {  // YouTube's own subtitles stay off unless you pick them in the CC menu
        this._capsOff = true;
        if (!this._ytCc && this._ytCc !== "") { this._ytCc = undefined; this._cmd("unloadModule", ["captions"]); }
      }
      if (st === 1) { this._started = true; clearTimeout(this._wd); }
      if (st === 1 && this.paused) { this.paused = false; this.ended = false; this._fire("play"); }
      else if (st === 2 && !this.paused) { this.paused = true; this._fire("pause"); }
      else if (st === 0 && !inAd) { this.paused = true; this.ended = true; this._fire("pause"); this._fire("ended"); }
    }
  }
  get currentTime() { return this._t; }
  set currentTime(t) { if (this._inAd) return; this._t = Math.max(0, t); this._cmd("seekTo", [this._t, true]); this._fire("timeupdate"); }
  get volume() { return this._vol; }
  set volume(x) { this._vol = Math.min(1, Math.max(0, x)); this._cmd("setVolume", [Math.round(this._vol * 100)]); }
  get muted() { return this._muted; }
  set muted(m) { this._muted = !!m; this._cmd(m ? "mute" : "unMute"); }
  get playbackRate() { return this._rate; }
  set playbackRate(r) { this._rate = r; this._cmd("setPlaybackRate", [r]); }
  set controls(x) {}
  play() {
    this.ended = false; this._cmd("playVideo");
    // Sometimes YouTube's player gets stuck (after the app was in the background, or a floating window): it
    // doesn't answer Play. Then it's loaded again at the same second and plays from there.
    clearTimeout(this._wd);
    if (this._started) {
      let waits = 0;
      const check = () => {
        if (!this.paused || this._inAd || document.visibilityState !== "visible") return;
        if (this._st === 3 && ++waits < 4) { this._wd = setTimeout(check, 2500); return; }  // still loading: give it time
        this.revive();
      };
      this._wd = setTimeout(check, 3000);
    }
    return Promise.resolve();
  }
  revive() {
    if (this._revived && Date.now() - this._revived < 10000) return;
    this._revived = Date.now();
    const t = Math.floor(this._t);
    try {
      const u = new URL(this.frame.src);
      u.searchParams.set("start", String(t)); u.searchParams.set("autoplay", "1");
      this.from = t; this._confirmed = this.R.ad_guard === false; this._vidOk = null; this._capsOff = false;
      if (this._ytCc !== undefined && this._ytCc !== null) { const lang = this._ytCc; this._ytCc = undefined;
        this.frame.addEventListener("load", () => setTimeout(() => this._ytCaptions(lang), 1500), { once: true }); }
      this.frame.src = u.href;
    } catch (e) { /* not a normal YouTube address */ }
  }
  pause() { this._cmd("pauseVideo"); }
  load() { this.frame.src = this.frame.src; }
  querySelector() { return null; }
}

// Quality for YouTube lessons. YouTube's player inside apps ignores "play in 1080p" (and on phones it ignores the
// size trick too), so the menu works like this:
//   Auto: YouTube's player, and YouTube picks the quality (the button shows what it's playing).
//   1080p, 720p, 480p, 360p (only the ones this video has): inPace gets the video at that size (yt-dlp) and plays
//   it in its own player, from the same second. YouTube keeps playing until it's ready, so there's no wait.
// The choice is remembered for the next lessons. If a size can't be had on this device, it says so and YouTube
// keeps playing.
const YT_SIZES = { hd2160: 2160, hd1440: 1440, hd1080: 1080, hd720: 720, large: 480, medium: 360, small: 240, tiny: 144 };
const YT_HEIGHTS = [1080, 720, 480, 360];
let ytQualityFailed = false;  // one failed try per page is enough: the next lessons stay on Auto until the page reloads

function plToast(player, text, ms) {
  const t = player.querySelector(".pl-toast");
  if (!t) return;
  t.textContent = text; t.classList.add("on");
  clearTimeout(t._h); t._h = setTimeout(() => t.classList.remove("on"), ms || 2600);
}
function ytWantQuality() { try { return localStorage.getItem("inpace-ytq") || "auto"; } catch (e) { return "auto"; } }
function ytSaveQuality(q) { try { localStorage.setItem("inpace-ytq", String(q)); } catch (e) { /* private window */ } }

// The quality button and menu (the same in YouTube's player and in inPace's own one).
function qualityMenu(player, opts) {
  const L = player.dataset, spd = player.querySelector(".pl-speed");
  if (!spd) return null;
  const btn = document.createElement("button");
  btn.type = "button"; btn.className = "pl-btn pl-q"; btn.title = L.lQuality || "Quality"; btn.setAttribute("aria-haspopup", "true");
  spd.insertAdjacentElement("beforebegin", btn);
  const menu = document.createElement("div");
  menu.className = "pl-menu pl-qmenu"; menu.hidden = true;
  menu.title = L.lQnote || "";
  player.appendChild(menu);
  const draw = () => { btn.textContent = opts.label(); btn.classList.toggle("auto", opts.current() === "auto"); };
  const fill = () => {
    const cur = opts.current(), auto = L.lAuto || "Auto", now = opts.autoNow ? opts.autoNow() : 0;
    menu.innerHTML = [`<button type="button" data-q="auto" class="${cur === "auto" ? "on" : ""}">${auto}${cur === "auto" && now ? ` · ${now}p` : ""}</button>`]
      .concat(opts.heights().map((h) => `<button type="button" data-q="${h}" class="${String(cur) === String(h) ? "on" : ""}">${h}p${h >= 720 ? " <small>HD</small>" : ""}</button>`))
      // the short note only where there's room for it (in small players it's the menu's tooltip)
      .concat(player.clientHeight >= 300 ? [`<p class="pl-qwait">${L.lQnote || "Auto: YouTube picks. Any other quality plays in inPace's own player."}</p>`] : []).join("");
  };
  btn.addEventListener("click", (e) => { e.stopPropagation(); fill(); menu.hidden = !menu.hidden; });
  menu.addEventListener("click", (e) => {
    e.stopPropagation();
    const b = e.target.closest("button");
    if (!b) return;
    menu.hidden = true;
    if (String(opts.current()) !== b.dataset.q) opts.pick(b.dataset.q);
  });
  document.addEventListener("click", () => (menu.hidden = true));
  draw();
  return { draw, refill: () => { if (!menu.hidden) fill(); }, busy: (h) => { btn.textContent = h + "p…"; btn.classList.add("busy"); },
           idle: () => { btn.classList.remove("busy"); draw(); } };
}

// In YouTube's player.
function youtubeQuality(player, frame, v, box) {
  const L = player.dataset;
  const heights = () => {  // the sizes this video has (YouTube tells once it plays); all four until then
    const hs = [...new Set((v.qualities || []).map((n) => YT_SIZES[n]).filter((h) => YT_HEIGHTS.includes(h)))].sort((x, y) => y - x);
    return hs.length ? hs : YT_HEIGHTS;
  };
  let busy = false;
  const m = qualityMenu(player, {
    current: () => "auto",
    label: () => (YT_SIZES[v.quality] ? YT_SIZES[v.quality] + "p" : (L.lAuto || "Auto")),
    autoNow: () => YT_SIZES[v.quality] || 0,
    heights,
    pick: (q) => { if (q !== "auto") { ytSaveQuality(q); go(+q, false); } },
  });
  if (!m) return;
  const go = (h, quiet) => {
    if (busy || !player.isConnected) return;
    busy = true; m.busy(h);
    if (!quiet) plToast(player, (L.lQget || "Getting {q}…").replace("{q}", h + "p"), 4000);
    box._ytHeights = heights();
    ytOwnPlayer(player, box, v, h).then((r) => {
      busy = false;
      if (r.ok || !player.isConnected) return;
      m.idle();
      ytQualityFailed = true;
      plToast(player, (L.lQfail || "{q} isn't available here right now, so YouTube picks the quality.").replace("{q}", h + "p"), 4500);
    });
  };
  v.addEventListener("ytquality", () => { if (!busy) m.draw(); m.refill(); });
  // A quality you chose before: once the video plays, it moves to that size (YouTube plays meanwhile).
  const want = +ytWantQuality();
  if (YT_HEIGHTS.includes(want) && !ytQualityFailed) v.addEventListener("play", () => setTimeout(() => go(want, true), 400), { once: true });
}

// inPace's own player for a YouTube lesson at one size. from: the player it replaces (YouTube's, or this one at
// another size); oldV: its video. Resolves {ok} once it's in place, or {why}.
function ytOwnPlayer(from, box, oldV, h) {
  const L = box.dataset, id = L.ytId;
  const hls = document.createElement("video").canPlayType("application/vnd.apple.mpegurl") ? "1" : "0";
  const ctl = new AbortController(), timer = setTimeout(() => ctl.abort(), 90000);
  const subs = fetch(`/yt-subs/${encodeURIComponent(id)}.json`).then((r) => r.json()).catch(() => ({}));
  return fetch(`/yt-stream/${encodeURIComponent(id)}?hls=${hls}&q=${h}`, { signal: ctl.signal }).then((r) => r.json()).catch(() => ({}))
    .then(async (d) => {
      clearTimeout(timer);
      if (!d || !(d.url || (d.video && d.audio))) return { why: (d && d.why) || "" };
      if (!from.isConnected) return { why: "gone" };
      const s = await Promise.race([subs, new Promise((r) => setTimeout(() => r({}), 2500))]);
      const t = oldV.currentTime || 0, wasPlaying = !oldV.paused;
      const player = document.createElement("div");
      player.className = "player yt-own"; player.tabIndex = 0; player.dataset.player = "";
      for (const k in L) if (/^l[A-Z]/.test(k) || ["speed", "start", "end", "ytId", "ytKey", "watch"].includes(k)) player.dataset[k] = L[k];
      player.dataset.key = L.ytKey; player.dataset.resume = String(t);
      const v = document.createElement("video");
      v.preload = "auto"; v.playsInline = true; v.ccQuiet = true;  // subtitles only if you chose them before
      v.src = d.url || d.video;
      for (const x of (s && s.tracks) || []) {
        const tr = document.createElement("track");
        tr.kind = "subtitles"; tr.label = x.label; tr.srclang = x.lang; tr.src = `/yt-subs/${encodeURIComponent(id)}/${encodeURIComponent(x.lang)}.vtt`;
        v.appendChild(tr);
      }
      player.appendChild(v);
      oldV.pause();
      if (from._sound) from._sound.pause();
      from.replaceWith(player);
      if (d.audio) player._sound = pairSound(v, d.audio);
      window.inpacePlayer(player, v);
      ownQuality(player, box, v, h, d.height);
      let played = false;
      v.addEventListener("playing", () => (played = true), { once: true });
      v.addEventListener("error", () => {
        if (played || !player.isConnected) return;
        ytQualityFailed = true;
        ytBackToYouTube(player, box, v, (L.lQfail || "{q} isn't available here right now, so YouTube picks the quality.").replace("{q}", h + "p"));
      });
      if (wasPlaying) v.play().catch(() => {});
      player.focus({ preventScroll: true });
      return { ok: true };
    });
}

// The quality menu in inPace's own player: another size, or Auto (back to YouTube's player at the same second).
function ownQuality(player, box, v, h, got) {
  const L = player.dataset;
  let busy = false;
  const m = qualityMenu(player, {
    current: () => h,
    label: () => (got || h) + "p",
    heights: () => box._ytHeights || YT_HEIGHTS,
    pick: (q) => {
      ytSaveQuality(q);
      if (q === "auto") { ytBackToYouTube(player, box, v); return; }
      if (busy) return;
      busy = true; m.busy(+q);
      plToast(player, (L.lQget || "Getting {q}…").replace("{q}", q + "p"), 4000);
      ytOwnPlayer(player, box, v, +q).then((r) => {
        busy = false;
        if (r.ok || !player.isConnected) return;
        m.idle();
        plToast(player, (L.lQfail || "{q} isn't available here right now.").replace("{q}", q + "p"), 4500);
      });
    },
  });
}

function ytBackToYouTube(own, box, v, msg) {
  const t = v.currentTime || +own.dataset.resume || 0;
  v.pause();
  if (own._sound) own._sound.pause();
  box.dataset.resume = String(Math.floor(t));
  own.replaceWith(box);
  youtubeAsPlayer(box);
  if (msg) { const p = box.isConnected ? null : document.querySelector(".yt-player"); if (p) plToast(p, msg, 4500); }
}

// "Play without ads", the second choice in a YouTube lesson's box: yt-dlp finds the video and inPace's own player
// plays it, so YouTube's ads never load. YouTube mostly gives the picture and the sound as two files: then a hidden
// audio element plays the sound, kept in step with the picture. If nothing works, a short note says so and
// "Play on YouTube" is still there.
function pairSound(v, url) {
  const a = new Audio(); a.preload = "auto"; a.src = url;
  const near = () => { if (Math.abs(a.currentTime - v.currentTime) > 0.25) a.currentTime = v.currentTime; };
  v.addEventListener("play", () => { near(); a.play().catch(() => {}); });
  v.addEventListener("playing", () => { near(); a.play().catch(() => {}); });
  v.addEventListener("pause", () => a.pause());
  v.addEventListener("waiting", () => a.pause());
  v.addEventListener("seeking", () => { a.currentTime = v.currentTime; });
  v.addEventListener("ratechange", () => { a.playbackRate = v.playbackRate; });
  v.addEventListener("volumechange", () => { a.volume = v.volume; a.muted = v.muted; });
  v.addEventListener("ended", () => a.pause());
  v.addEventListener("timeupdate", () => { if (!v.paused && Math.abs(a.currentTime - v.currentTime) > 0.35) a.currentTime = v.currentTime; });
  return a;
}
document.querySelectorAll("[data-yt-noads]").forEach((nb) => {
  const box = nb.closest(".embed-box"), fig = box && box.closest("figure");
  if (!box || !fig) return;
  const note = box.querySelector("[data-yt-noads-note]"), L = box.dataset;
  const title = nb.querySelector("b"), label = title.textContent;
  const back = () => {  // put the box back, ready for either choice
    fig.querySelectorAll(".yt-player, .player, .frame-wrap, .yt-holder, .yt-note, .yt-noads").forEach((x) => x.remove());
    if (!box.isConnected) { const at = fig.querySelector(".yt-save, figcaption"); at ? at.before(box) : fig.appendChild(box); }
  };
  const fail = (why) => {
    back(); nb.disabled = false; title.textContent = label;
    note.textContent = nb.dataset.lFail; note.title = why || ""; note.hidden = false;
  };
  nb.addEventListener("click", (ev) => {
    ev.stopPropagation();
    if (!window.inpacePlayer || nb.disabled) return;
    nb.disabled = true; title.textContent = nb.dataset.lBusy; note.hidden = true;
    const test = document.createElement("video");
    const hls = test.canPlayType("application/vnd.apple.mpegurl") ? "1" : "0";
    const ctl = new AbortController(), timer = setTimeout(() => ctl.abort(), 120000);
    fetch(nb.dataset.ytNoads + "?hls=" + hls, { signal: ctl.signal }).then((r) => r.json()).catch(() => ({})).then((d) => {
      clearTimeout(timer);
      if (!d || !(d.url || (d.video && d.audio))) return fail(d && d.why);
      nb.disabled = false; title.textContent = label;
      const player = document.createElement("div");
      player.className = "player"; player.tabIndex = 0; player.dataset.player = "";
      for (const k in L) if (/^l[A-Z]/.test(k) || ["speed", "start", "end", "resume"].includes(k)) player.dataset[k] = L[k];
      player.dataset.key = L.ytKey;
      const v = document.createElement("video");
      v.preload = "metadata"; v.playsInline = true;
      const st = +L.start || 0, en = +L.end || 0;
      v.src = (d.url || d.video) + (st || en ? `#t=${st}` + (en ? `,${en}` : "") : "");
      player.appendChild(v);
      box.replaceWith(player);
      if (d.audio) player._sound = pairSound(v, d.audio);
      const info = document.createElement("p");
      info.className = "small muted yt-noads";
      info.textContent = (L.lNoads || "No ads.") + (d.height ? ` ${d.height}p · ` : " · ");
      const hd = document.createElement("button");
      hd.type = "button"; hd.className = "link"; hd.textContent = L.lHd || "YouTube";
      hd.addEventListener("click", () => { v.pause(); player._sound && player._sound.pause(); back(); const p = box.querySelector(".play"); p && p.click(); });
      info.appendChild(hd);
      player.insertAdjacentElement("afterend", info);
      v.addEventListener("error", () => { if (v.currentTime < 1) { player._sound && player._sound.pause(); fail("video error"); } });
      window.inpacePlayer(player, v);
      player.focus({ preventScroll: true });
      v.play().catch(() => {});
    });
  });
});

// The still picture over a paused YouTube video: the sharpest one YouTube has (1280×720), else 640×480, else 480×360.
// YouTube answers a missing size with a tiny 120×90 grey picture, so anything that small means "try the next one".
function ytStill(el, id) {
  const sizes = ["maxresdefault", "sddefault", "hqdefault"];
  const at = (i) => {
    const url = `https://i.ytimg.com/vi/${encodeURIComponent(id)}/${sizes[i]}.jpg`;
    if (i === sizes.length - 1) { el.style.backgroundImage = `url("${url}")`; return; }
    const img = new Image();
    img.onload = () => (img.naturalWidth > 120 ? (el.style.backgroundImage = `url("${url}")`) : at(i + 1));
    img.onerror = () => at(i + 1);
    img.src = url;
  };
  el.style.backgroundImage = `url("https://i.ytimg.com/vi/${encodeURIComponent(id)}/hqdefault.jpg")`;  // right away, then sharper
  at(0);
}

function youtubeAsPlayer(box) {
  const L = box.dataset, id = L.ytId;
  const player = document.createElement("div");
  player.className = "player yt-player";
  player.tabIndex = 0;
  for (const k in L) if (k !== "embed") player.dataset[k] = L[k];
  player.dataset.key = L.ytKey;
  const frame = document.createElement("iframe");
  frame.src = youtubeSrc(box);
  frame.allow = "autoplay; encrypted-media; picture-in-picture; fullscreen";
  frame.referrerPolicy = "strict-origin-when-cross-origin";
  frame.title = "YouTube";
  frame.setAttribute("tabindex", "-1");
  // The cover sits over YouTube's picture: it catches clicks (so YouTube never shows its own buttons),
  // and while the video isn't playing it shows the video's still picture instead of YouTube's pause screen.
  const cover = document.createElement("div");
  cover.className = "yt-cover";
  ytStill(cover, id);
  player.append(frame, cover);
  box.replaceWith(player);
  const st = +L.start || 0, en = +L.end || 0, rs = +L.resume || 0;
  const from = rs > st + 5 && (!en || rs < en - 5) ? rs : st;   // the second youtubeSrc asks YouTube to start at
  const R = ytRules(box);
  const v = new YouTubeMedia(frame, cover, id, from, R);
  const adTag = document.createElement("div");
  adTag.className = "yt-adtag"; adTag.textContent = L.lAd || "Ad: the lesson starts after it";
  player.appendChild(adTag);
  v.addEventListener("ytad", () => player.classList.add("yt-ad"));
  v.addEventListener("ytmain", () => player.classList.remove("yt-ad"));
  const show = () => player.classList.toggle("yt-showing", !v.paused);
  // YouTube shows its title for a moment when a video first starts: only then does the still picture stay a little
  // longer. Going on after a pause shows the video right away.
  let firstPlay = true;
  v.addEventListener("play", () => { setTimeout(show, firstPlay ? R.cover_after_ms : 120); firstPlay = false; });
  v.addEventListener("pause", show);
  const ctl = window.inpacePlayer(player, v);
  player.focus({ preventScroll: true });
  if (R.quality_menu !== false) youtubeQuality(player, frame, v, box);
  const esc = (t) => String(t || "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const link = `<a class="btn small" href="${esc(L.watch)}" target="_blank" rel="noopener">${esc(L.lOpen)}</a>`;
  const note = (html, cls) => {
    let n = player.parentElement.querySelector(".yt-note");
    if (!n) { n = document.createElement("p"); player.insertAdjacentElement("afterend", n); }
    n.className = "yt-note " + (cls || ""); n.innerHTML = html;
  };
  let heard = false;
  v.addEventListener("ythello", () => { heard = true; const s = player.parentElement.querySelector(".yt-note.soft"); s && s.remove(); });
  // YouTube didn't answer inPace's player (it may have changed how it talks to apps): switch to YouTube's own
  // player and buttons, from the same second, so the lesson always plays.
  setTimeout(() => {
    if (heard || !player.isConnected) return;
    const plain = document.createElement("iframe");
    plain.src = frame.src.replace("&controls=0", "").replace("&fs=0", "").replace("&disablekb=1", "");
    plain.allow = frame.allow; plain.allowFullscreen = true; plain.referrerPolicy = frame.referrerPolicy; plain.title = "YouTube";
    const wrap = document.createElement("div");
    wrap.className = "frame-wrap video-ratio";
    wrap.appendChild(plain);
    player.replaceWith(wrap);
    youtubeRemember(plain, box);
  }, R.fallback_ms);
  v.addEventListener("yterror", () => { player.classList.add("failed"); note(`<b>${esc(L.lErr)}</b> <span class="small muted">(YouTube ${esc(v.error.code)})</span> ${link}`, "warn"); });
  setTimeout(() => { if (!heard && L.watch) note(`${esc(L.lSlow)} ${link}`, "soft"); }, 15000);
  return ctl;
}

// YouTube lessons: a lesson can be one piece of a long video (start and end), and it continues from the
// second you stopped at. The player tells us where it is through its own messages (no extra script).
function youtubeSrc(box) {
  const start = +box.dataset.start || 0, end = +box.dataset.end || 0, resume = +box.dataset.resume || 0;
  const from = resume > start + 5 && (!end || resume < end - 5) ? resume : start;
  let src = box.dataset.embed + "&origin=" + encodeURIComponent(location.origin);
  if (from) src += "&start=" + Math.floor(from);
  if (end) src += "&end=" + Math.floor(end);
  return src;
}
function youtubeRemember(frame, box) {
  const key = box.dataset.ytKey, end = +box.dataset.end || 0;
  let now = 0, length = 0, sent = -1;
  const send = (beacon) => {
    if (now <= 0 || Math.abs(now - sent) < 1) return;
    sent = now;
    const body = new FormData();
    body.append("key", key); body.append("t", now.toFixed(1)); body.append("d", String(end || length || 0));
    if (beacon && navigator.sendBeacon) navigator.sendBeacon("/media-pos", body);
    else fetch("/media-pos", { method: "POST", body, keepalive: true }).catch(() => {});
  };
  window.addEventListener("message", (ev) => {
    if (ev.source !== frame.contentWindow) return;
    let d = ev.data;
    try { if (typeof d === "string") d = JSON.parse(d); } catch (e) { return; }
    const info = d && d.info;
    if (!info || typeof info !== "object") return;
    if (typeof info.duration === "number" && info.duration > 0) length = info.duration;
    if (typeof info.currentTime === "number") {
      now = info.currentTime;
      if (Math.abs(now - sent) >= 5) send();
    }
    if (info.playerState === 2 || info.playerState === 0) send();  // paused or ended
  });
  const hello = () => {
    try { frame.contentWindow.postMessage(JSON.stringify({ event: "listening", id: key, channel: "widget" }), "*"); } catch (e) {}
  };
  frame.addEventListener("load", () => { hello(); setTimeout(hello, 1000); setTimeout(hello, 3000); });
  document.addEventListener("visibilitychange", () => { if (document.hidden) send(true); });
  window.addEventListener("pagehide", () => send(true));
}

// YouTube lessons: a bar of inPace's own under the video for a piece of a long video (it goes from 0:00 to the
// piece's length), and a clear way out when YouTube won't play inside the app.
const YT_ICON = {
  play: '<svg viewBox="0 0 24 24" width="20" height="20"><path d="M7 4.5v15l13-7.5z" fill="currentColor"/></svg>',
  pause: '<svg viewBox="0 0 24 24" width="20" height="20"><path d="M6 4h4.5v16H6zM13.5 4H18v16h-4.5z" fill="currentColor"/></svg>',
  back: '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12a9 9 0 1 0 3-6.7"/><path d="M3 4v5h5"/><text x="12" y="15.5" font-size="7.5" text-anchor="middle" fill="currentColor" stroke="none" font-weight="800">10</text></svg>',
  vol: '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 9h4l5-4v14l-5-4H4z"/><path d="M16.5 8.5a5 5 0 0 1 0 7"/></svg>',
  mute: '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 9h4l5-4v14l-5-4H4z"/><path d="M17 9l5 6M22 9l-5 6"/></svg>',
  full: '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M4 9V4h5M20 9V4h-5M4 15v5h5M20 15v5h-5"/></svg>',
  fwd: '<svg viewBox="0 0 24 24" width="20" height="20" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a9 9 0 1 1-3-6.7"/><path d="M21 4v5h-5"/><text x="12" y="15.5" font-size="7.5" text-anchor="middle" fill="currentColor" stroke="none" font-weight="800">10</text></svg>',
};
function clockText(s) {
  s = Math.max(0, Math.floor(s || 0));
  const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), x = String(s % 60).padStart(2, "0");
  return h ? `${h}:${String(m).padStart(2, "0")}:${x}` : `${m}:${x}`;
}
function youtubeExtras(frame, box, wrap) {
  const L = box.dataset, lo = +L.start || 0, end = +L.end || 0;
  const cmd = (func, args) => { try { frame.contentWindow.postMessage(JSON.stringify({ event: "command", func, args: args || [] }), "*"); } catch (e) {} };
  let now = lo, length = 0, playing = false, rate = 1, heard = false, failed = false;
  const watch = L.watch || "";
  const note = (html, cls) => {
    let n = wrap.parentElement.querySelector(".yt-note");
    if (!n) { n = document.createElement("p"); wrap.insertAdjacentElement("afterend", n); }
    n.className = "yt-note " + (cls || ""); n.innerHTML = html;
  };
  const esc = (t) => String(t || "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const link = `<a class="btn small" href="${esc(watch)}" target="_blank" rel="noopener">${esc(L.lOpen)}</a>`;
  frame.addEventListener("load", () => {
    const hi = () => { cmd("addEventListener", ["onError"]); cmd("addEventListener", ["onStateChange"]); };
    hi(); setTimeout(hi, 1200);
  });
  setTimeout(() => { if (!heard && !failed && watch) note(`${esc(L.lSlow)} ${link}`, "soft"); }, 15000);

  let bar = null, seek, time, play, spd, vol, muted = false, dragging = false;
  const single = (L.ytKey || "").includes("|yt:");  // one video (a playlist keeps YouTube's own buttons)
  if (single) {
    bar = document.createElement("div");
    bar.className = "yt-bar";
    bar.innerHTML = `<input type="range" class="pl-seek" min="0" max="1000" value="0" step="1" aria-label="${esc(L.lPiece)}">
      <div class="pl-row"><button type="button" class="pl-btn yb-play" title="${esc(L.lPlay)}">${YT_ICON.play}</button>
      <button type="button" class="pl-btn yb-back" title="${esc(L.lBack)}">${YT_ICON.back}</button>
      <button type="button" class="pl-btn yb-fwd" title="${esc(L.lFwd)}">${YT_ICON.fwd}</button>
      <span class="pl-time" dir="ltr">0:00 / 0:00</span><span class="pl-grow"></span>
      ${lo || end ? `<span class="yb-label">${esc(L.lPiece)}</span>` : ""}
      <button type="button" class="pl-btn yb-vol" title="${esc(L.lMute || "Sound")}">${YT_ICON.vol}</button>
      <button type="button" class="pl-btn yb-speed" title="${esc(L.lSpeed)}">1×</button>
      <button type="button" class="pl-btn yb-full" title="${esc(L.lFull || "Full screen")}">${YT_ICON.full}</button></div>`;
    const holder = document.createElement("div");
    holder.className = "yt-holder";
    wrap.replaceWith(holder); holder.appendChild(wrap); holder.appendChild(bar);
    vol = bar.querySelector(".yb-vol");
    seek = bar.querySelector(".pl-seek"); time = bar.querySelector(".pl-time"); play = bar.querySelector(".yb-play"); spd = bar.querySelector(".yb-speed");
  }
  const hiT = () => end || length || 0;
  const span = () => Math.max(0, hiT() - lo);
  const draw = () => {
    if (!bar) return;
    const d = span(), cur = Math.min(Math.max(0, now - lo), d || Infinity);
    if (!dragging) seek.value = d ? Math.round((cur / d) * 1000) : 0;
    seek.style.setProperty("--p", (seek.value / 10) + "%");
    time.textContent = `${clockText(dragging ? (seek.value / 1000) * d : cur)} / ${d ? clockText(d) : "…"}`;
    play.innerHTML = playing ? YT_ICON.pause : YT_ICON.play;
    play.title = playing ? L.lPause : L.lPlay;
    spd.textContent = rate + "×";
    vol.innerHTML = muted ? YT_ICON.mute : YT_ICON.vol;
  };
  const go = (t) => { now = Math.min(Math.max(lo, t), hiT() || t); cmd("seekTo", [now, true]); draw(); };
  if (bar) {
    play.addEventListener("click", () => {
      if (playing) cmd("pauseVideo");
      else { if (end && now >= end - 0.6) go(lo); cmd("playVideo"); }
    });
    bar.querySelector(".yb-back").addEventListener("click", () => go(now - 10));
    bar.querySelector(".yb-fwd").addEventListener("click", () => go(now + 10));
    seek.addEventListener("input", () => { dragging = true; draw(); });
    seek.addEventListener("change", () => { dragging = false; go(lo + (seek.value / 1000) * span()); });
    vol.addEventListener("click", () => { muted = !muted; cmd(muted ? "mute" : "unMute"); draw(); });
    bar.querySelector(".yb-full").addEventListener("click", () => {
      const h = bar.parentElement;
      if (document.fullscreenElement) document.exitFullscreen().catch(() => {});
      else if (h.requestFullscreen) h.requestFullscreen().catch(() => {});
    });
    spd.addEventListener("click", () => {
      const S = [0.5, 0.75, 1, 1.25, 1.5, 1.75, 2];
      rate = S[(S.indexOf(rate) + 1) % S.length] || 1; cmd("setPlaybackRate", [rate]); draw();
    });
    draw();
  }
  window.addEventListener("message", (ev) => {
    if (ev.source !== frame.contentWindow) return;
    let d = ev.data;
    try { if (typeof d === "string") d = JSON.parse(d); } catch (e) { return; }
    if (!d || typeof d !== "object") return;
    if (d.event === "onError") {
      failed = true;
      note(`<b>${esc(L.lErr)}</b> <span class="small muted">(YouTube ${esc(d.info)})</span> ${link}`, "warn");
      return;
    }
    const info = d.info;
    if (!info || typeof info !== "object") return;
    heard = true;
    const soft = wrap.parentElement.querySelector(".yt-note.soft");
    if (soft && info.playerState === 1) soft.remove();
    if (typeof info.duration === "number" && info.duration > 0) length = info.duration;
    if (typeof info.currentTime === "number") now = info.currentTime;
    if (typeof info.playbackRate === "number") rate = info.playbackRate;
    if (typeof info.playerState === "number") playing = info.playerState === 1;
    if (typeof info.muted === "boolean") muted = info.muted;
    draw();
  });
}

// Web pages in lessons can go full screen.
document.querySelectorAll("[data-fullscreen]").forEach((btn) => {
  btn.addEventListener("click", () => {
    const frame = btn.closest("figure").querySelector("iframe");
    if (frame && frame.requestFullscreen) frame.requestFullscreen().catch(() => {});
  });
});

// "Choose folder": opens your computer's own folder window and fills in the path.
document.querySelectorAll("[data-pick-folder]").forEach((btn) => {
  btn.addEventListener("click", async () => {
    const input = document.querySelector(btn.dataset.pickFolder);
    const label = btn.textContent;
    btn.disabled = true;
    btn.textContent = "…";
    try {
      const r = await fetch("/pick-folder", { method: "POST" });
      const d = await r.json();
      if (d.folder && input) { input.value = d.folder; input.dispatchEvent(new Event("input")); }
      else if (input) input.focus();
    } catch (e) { if (input) input.focus(); }
    btn.disabled = false;
    btn.textContent = label;
  });
});

// Voice notes as proof for a task: record, stop, and it's saved like any other file.
document.querySelectorAll("[data-recorder]").forEach((box) => {
  const btn = box.querySelector(".rec-btn");
  const time = box.querySelector(".rec-time");
  const L = box.dataset;
  let rec = null, chunks = [], started = 0, timer = null;
  const fmt = (s) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
  btn.addEventListener("click", async () => {
    if (rec && rec.state === "recording") { rec.stop(); return; }
    let stream;
    try { stream = await navigator.mediaDevices.getUserMedia({ audio: true }); }
    catch (e) { time.textContent = L.lNomic; return; }
    const type = ["audio/webm;codecs=opus", "audio/webm", "audio/ogg", "audio/mp4"].find((t) => window.MediaRecorder && MediaRecorder.isTypeSupported(t)) || "";
    rec = new MediaRecorder(stream, type ? { mimeType: type } : undefined);
    chunks = [];
    rec.ondataavailable = (e) => e.data.size && chunks.push(e.data);
    rec.onstop = async () => {
      clearInterval(timer);
      stream.getTracks().forEach((t) => t.stop());
      btn.disabled = true;
      btn.textContent = L.lSaving;
      const mime = rec.mimeType || type || "audio/webm";
      const ext = mime.includes("ogg") ? "ogg" : mime.includes("mp4") ? "m4a" : "webm";
      const stamp = new Date().toISOString().slice(0, 16).replace("T", " ").replace(":", "-");
      const body = new FormData();
      body.append("file", new Blob(chunks, { type: mime }), `voice note ${stamp}.${ext}`);
      const r = await fetch(box.dataset.upload, { method: "POST", body });
      goFresh(r.url || location.href);
    };
    rec.start(1000);
    started = Date.now();
    btn.classList.add("recording");
    btn.textContent = "■ " + L.lStop;
    timer = setInterval(() => (time.textContent = fmt(Math.round((Date.now() - started) / 1000))), 500);
  });
});

// ---------------------------------------------------------------------------
// Video player: big play button, ±10 s, speed, full screen, keyboard keys,
// and it continues from the second you stopped at (saved on this computer).
// ---------------------------------------------------------------------------
(() => {
  const fmt = (s) => {
    s = Math.max(0, Math.floor(s || 0));
    const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), x = String(s % 60).padStart(2, "0");
    return h ? `${h}:${String(m).padStart(2, "0")}:${x}` : `${m}:${x}`;
  };
  const save = (key, t, d, speed, beacon) => {
    const body = new FormData();
    body.append("key", key); body.append("t", t.toFixed(1)); body.append("d", (d || 0).toFixed(1));
    if (speed) body.append("speed", speed);
    if (beacon && navigator.sendBeacon) navigator.sendBeacon("/media-pos", body);
    else fetch("/media-pos", { method: "POST", body, keepalive: true }).catch(() => {});
  };
  const remember = (media, key, getSpeed, getEnd) => {
    let last = 0;
    const end = () => (getEnd && getEnd()) || media.duration;
    const tick = (force, beacon) => {
      if (!media.duration) return;
      if (force || Math.abs(media.currentTime - last) >= 4) {
        last = media.currentTime;
        save(key, media.currentTime, end(), getSpeed && getSpeed(), beacon);
      }
    };
    media.addEventListener("timeupdate", () => tick(false));
    media.addEventListener("pause", () => tick(true));
    media.addEventListener("ended", () => save(key, end(), end()));
    addEventListener("pagehide", () => tick(true, true));
    return tick;
  };
  // lo and hi: a lesson can be one piece of a long video file. It starts at lo and stops at hi.
  const resumeAt = (media, start, lo = 0, hi = 0) => {
    const at = start > lo + 5 && (!hi || start < hi - 3) ? start : lo;
    if (at > 0) {
      const go = () => { if (media.duration && at < media.duration - 3) media.currentTime = at; };
      media.readyState >= 1 ? go() : media.addEventListener("loadedmetadata", go, { once: true });
    }
  };

  // Audio keeps the browser's own controls, but also continues where you stopped.
  document.querySelectorAll("audio[data-remember]").forEach((a) => {
    resumeAt(a, parseFloat(a.dataset.resume || "0"));
    remember(a, a.dataset.key);
  });

  const ICON = {
    play: '<svg viewBox="0 0 24 24" width="22" height="22"><path d="M7 4.5v15l13-7.5z" fill="currentColor"/></svg>',
    pause: '<svg viewBox="0 0 24 24" width="22" height="22"><path d="M6 4h4.5v16H6zM13.5 4H18v16h-4.5z" fill="currentColor"/></svg>',
    back: '<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M3 12a9 9 0 1 0 3-6.7"/><path d="M3 4v5h5"/><text x="12" y="15.5" font-size="7.5" text-anchor="middle" fill="currentColor" stroke="none" font-weight="800">10</text></svg>',
    fwd: '<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round"><path d="M21 12a9 9 0 1 1-3-6.7"/><path d="M21 4v5h-5"/><text x="12" y="15.5" font-size="7.5" text-anchor="middle" fill="currentColor" stroke="none" font-weight="800">10</text></svg>',
    vol: '<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linejoin="round" stroke-linecap="round"><path d="M4 9h4l5-4v14l-5-4H4z" fill="currentColor"/><path d="M16.5 8.5a5 5 0 0 1 0 7M19 6a8.5 8.5 0 0 1 0 12"/></svg>',
    mute: '<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linejoin="round" stroke-linecap="round"><path d="M4 9h4l5-4v14l-5-4H4z" fill="currentColor"/><path d="M17 9l5 6M22 9l-5 6"/></svg>',
    full: '<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2.4" stroke-linecap="square"><path d="M4 9V4h5M15 4h5v5M20 15v5h-5M9 20H4v-5"/></svg>',
    pip: '<svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2.2"><rect x="3" y="5" width="18" height="14"/><rect x="12" y="12" width="7" height="5" fill="currentColor"/></svg>',
  };
  const SPEEDS = [0.5, 0.75, 1, 1.25, 1.5, 1.75, 2];

  const setup = (box, v) => {
    const L = box.dataset;
    // The mini player follows whichever video is playing. (The focus timer is its own thing: videos never touch it.)
    for (const ev of ["play", "pause", "ratechange", "seeked", "ended"]) v.addEventListener(ev, () => window.inpaceMediaChanged && window.inpaceMediaChanged());
    v.addEventListener("play", () => {
      if (window.inpaceFramePlay && window.inpaceFramePlay(box)) { v.pause(); return; }  // rule 2 (see "Videos: the rules")
      const was = window.inpaceNowPlaying;  // rule 1: one video at a time
      if (was && was.v !== v && !was.v.paused) { try { was.v.pause(); } catch (e) { /* gone */ } }
      window.inpaceNowPlaying = { box, v };
      if (window.inpaceMediaSession) inpaceMediaSession(box, v);
    });
    const lo = parseFloat(L.start || "0") || 0, hiSet = parseFloat(L.end || "0") || 0;
    const hi = () => hiSet || v.duration || 0;
    const span = () => Math.max(0, hi() - lo);
    v.controls = false;
    let speed = parseFloat(L.speed || "1") || 1;
    v.playbackRate = speed;
    v.addEventListener("loadedmetadata", () => (v.playbackRate = speed));

    box.insertAdjacentHTML("beforeend", `
      <button type="button" class="pl-big" aria-label="${L.lPlay}">${ICON.play}</button>
      <div class="pl-toast" aria-live="polite"></div>
      <div class="pl-bar">
        <input type="range" class="pl-seek" min="0" max="1000" value="0" step="1" aria-label="${L.lPlay}">
        <div class="pl-row">
          <button type="button" class="pl-btn pl-play" title="${L.lPlay} (K)">${ICON.play}</button>
          <button type="button" class="pl-btn pl-back" title="${L.lBack} (J)">${ICON.back}</button>
          <button type="button" class="pl-btn pl-fwd" title="${L.lFwd} (L)">${ICON.fwd}</button>
          <button type="button" class="pl-btn pl-mute" title="${L.lMute} (M)">${ICON.vol}</button>
          <input type="range" class="pl-vol" min="0" max="1" step="0.05" value="1" aria-label="${L.lMute}">
          <span class="pl-time" dir="ltr">0:00 / 0:00</span>
          <span class="pl-grow"></span>
          ${v.textTracks.length || L.subAction || v.subsLater ? `<button type="button" class="pl-btn pl-cc" title="${L.lCc} (C)" aria-haspopup="true">CC</button>` : ""}
          <button type="button" class="pl-btn pl-speed" title="${L.lSpeed}">${speed}×</button>
          ${document.pictureInPictureEnabled && v.requestPictureInPicture ? `<button type="button" class="pl-btn pl-pip" title="${L.lPip}">${ICON.pip}</button>` : ""}
          ${document.body.hasAttribute("data-mini-window") || window.InPaceAndroid ? "" : `<button type="button" class="pl-btn pl-out" title="${L.lMiniout}" aria-label="${L.lMiniout}"><svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" stroke-width="2.2"><rect x="3" y="4" width="18" height="16"/><rect x="11" y="11" width="8" height="7" fill="currentColor"/></svg></button>`}
          <button type="button" class="pl-btn pl-full" title="${L.lFull} (F)">${ICON.full}</button>
        </div>
      </div>`);
    const $ = (c) => box.querySelector(c);
    const outBtn = $(".pl-out");
    if (outBtn) outBtn.addEventListener("click", () => window.inpacePopout && window.inpacePopout({ box, v }));
    const seek = $(".pl-seek"), time = $(".pl-time"), play = $(".pl-play"), big = $(".pl-big");
    const mute = $(".pl-mute"), vol = $(".pl-vol"), spd = $(".pl-speed"), toast = $(".pl-toast");
    let toastTimer, hideTimer, dragging = false;

    const say = (text) => {
      toast.textContent = text; toast.classList.add("on");
      clearTimeout(toastTimer); toastTimer = setTimeout(() => toast.classList.remove("on"), 1300);
    };
    const atEnd = () => hiSet && v.currentTime >= hiSet - 0.3;
    const toggle = () => {
      if (v.paused || v.ended) { if (atEnd()) v.currentTime = lo; v.play(); } else v.pause();
    };
    const jump = (s) => { v.currentTime = Math.min(Math.max(lo, v.currentTime + s), hi()); say((s > 0 ? "+" : "") + s + "s"); };
    const draw = () => {
      const d = span(), cur = Math.min(Math.max(0, v.currentTime - lo), d);
      if (!dragging) seek.value = d ? Math.round((cur / d) * 1000) : 0;
      seek.style.setProperty("--p", (seek.value / 10) + "%");
      const b = v.buffered.length && d ? Math.min(100, Math.max(0, v.buffered.end(v.buffered.length - 1) - lo) / d * 100) : 0;
      seek.style.setProperty("--b", b + "%");
      time.textContent = `${fmt(cur)} / ${fmt(d)}`;
    };
    const state = () => {
      const p = v.paused || v.ended;
      play.innerHTML = p ? ICON.play : ICON.pause;
      play.title = (p ? L.lPlay : L.lPause) + " (K)";
      box.classList.toggle("playing", !p);
      big.hidden = !p;
    };
    const wake = () => {
      box.classList.add("awake");
      clearTimeout(hideTimer);
      hideTimer = setTimeout(() => { if (!v.paused) box.classList.remove("awake"); }, 2500);
    };

    const tick = remember(v, L.key, () => speed, () => hiSet);
    resumeAt(v, parseFloat(L.resume || "0"), lo, hiSet);
    // The end of this lesson's piece works like the end of the video.
    const pieceDone = () => { v.pause(); v.currentTime = hiSet; state(); say(L.lEnded); tick(true);
      const done = document.querySelector(".lesson-actions, .lesson-foot"); done && done.scrollIntoView({ behavior: "smooth", block: "center" }); };
    if (hiSet) v.addEventListener("timeupdate", () => { if (!v.paused && v.currentTime >= hiSet) pieceDone(); });
    v.addEventListener("loadedmetadata", draw);
    v.addEventListener("timeupdate", draw);
    v.addEventListener("progress", draw);
    v.addEventListener("play", state); v.addEventListener("pause", state);
    v.addEventListener("ended", () => { state(); say(L.lEnded); const done = document.querySelector(".lesson-actions, .lesson-foot"); done && done.scrollIntoView({ behavior: "smooth", block: "center" }); });
    // Keep the keyboard keys working after a click (the big button disappears once it's pressed).
    box.addEventListener("click", (e) => { if (e.target.tagName !== "INPUT") box.focus({ preventScroll: true }); });
    // Touch: while the bar is hidden, the first tap only shows it (like phone video apps); the next tap plays or pauses.
    let justWoke = false;
    box.addEventListener("pointerdown", (e) => {
      if (e.pointerType === "mouse") return;
      justWoke = box.classList.contains("playing") && !box.classList.contains("awake");
      wake();
    }, true);
    box.addEventListener("click", (e) => { if (justWoke) { justWoke = false; e.stopPropagation(); e.preventDefault(); } }, true);
    (v.clickTarget || v).addEventListener("click", toggle);
    (v.clickTarget || v).addEventListener("dblclick", () => $(".pl-full").click());
    big.addEventListener("click", toggle);
    play.addEventListener("click", toggle);
    $(".pl-back").addEventListener("click", () => jump(-10));
    $(".pl-fwd").addEventListener("click", () => jump(10));
    seek.addEventListener("input", () => { dragging = true; seek.style.setProperty("--p", (seek.value / 10) + "%"); time.textContent = `${fmt((seek.value / 1000) * span())} / ${fmt(span())}`; });
    seek.addEventListener("change", () => { v.currentTime = lo + (seek.value / 1000) * span(); dragging = false; tick(true); });
    const volState = () => { mute.innerHTML = v.muted || v.volume === 0 ? ICON.mute : ICON.vol; vol.value = v.muted ? 0 : v.volume; };
    mute.addEventListener("click", () => { v.muted = !v.muted; volState(); });
    vol.addEventListener("input", () => { v.volume = parseFloat(vol.value); v.muted = v.volume === 0; volState(); });
    spd.addEventListener("click", () => {
      speed = SPEEDS[(SPEEDS.indexOf(speed) + 1) % SPEEDS.length] || 1;
      v.playbackRate = speed; spd.textContent = speed + "×"; say(speed + "×"); tick(true);
    });
    const pip = $(".pl-pip");
    pip && pip.addEventListener("click", () => (document.pictureInPictureElement ? document.exitPictureInPicture() : v.requestPictureInPicture()).catch(() => {}));
    $(".pl-full").addEventListener("click", () => {
      if (document.fullscreenElement) document.exitFullscreen();
      else if (box.requestFullscreen) box.requestFullscreen().catch(() => {});
      else if (box.webkitRequestFullscreen) box.webkitRequestFullscreen();
      else if (v.webkitEnterFullscreen) v.webkitEnterFullscreen();
    });
    box.addEventListener("mousemove", wake);
    box.addEventListener("keydown", (e) => {
      if (e.target.tagName === "INPUT" && e.target.type === "range" && ["ArrowLeft", "ArrowRight", "ArrowUp", "ArrowDown"].includes(e.key)) return;
      const k = e.key.toLowerCase();
      const act = { " ": toggle, k: toggle, j: () => jump(-10), l: () => jump(10), arrowleft: () => jump(-5), arrowright: () => jump(5),
        f: () => $(".pl-full").click(), m: () => mute.click(),
        arrowup: () => { v.volume = Math.min(1, v.volume + 0.1); v.muted = false; volState(); say(Math.round(v.volume * 100) + "%"); },
        arrowdown: () => { v.volume = Math.max(0, v.volume - 0.1); volState(); say(Math.round(v.volume * 100) + "%"); } }[k];
      if (act && !(e.target.tagName === "BUTTON" && (k === " " || k === "enter"))) { e.preventDefault(); act(); wake(); }
    });
    const restart = box.parentElement.querySelector("[data-restart]");
    restart && restart.addEventListener("click", () => { v.currentTime = lo; v.play(); restart.closest(".resume-hint").remove(); });

    // Subtitles: files next to the video, or ones you add. The last one you chose is remembered.
    const cc = $(".pl-cc");
    if (cc) {
      const tracks = () => [].slice.call(v.textTracks);
      const pick = (i) => {
        tracks().forEach((t, j) => (t.mode = j === i ? "showing" : "disabled"));
        cc.classList.toggle("on", i >= 0);
        try { localStorage.setItem("inpace-cc", i >= 0 ? (tracks()[i].label || "on") : "off"); } catch (e) {}
      };
      let pref = null;
      try { pref = localStorage.getItem("inpace-cc"); } catch (e) {}
      const list = tracks();
      if (list.length && pref !== "off" && !(v.ccQuiet && pref !== list[0].label)) {
        let i = list.findIndex((t) => t.label === pref);
        if (i < 0) i = list.findIndex((t) => t.language && t.language === document.documentElement.lang);
        pick(i < 0 ? 0 : i);
      } else if (!(v.subsLater && !list.length)) pick(-1);  // a YouTube lesson's languages come later: keep your choice
      const menu = document.createElement("div");
      menu.className = "pl-menu"; menu.hidden = true;
      const esc = (t) => String(t || "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
      const fill = () => {
        const cur = tracks().findIndex((t) => t.mode === "showing");
        const note = v.subsLoading ? `<p class="pl-qwait">${esc(L.lCcfinding || "Finding subtitles…")}</p>`
          : (v.subsLater && !tracks().length ? `<p class="pl-qwait">${esc(L.lCcnone || "This video has no subtitles.")}</p>` : "");
        menu.innerHTML = note + tracks().map((t, i) => `<button type="button" data-i="${i}" class="${i === cur ? "on" : ""}" dir="auto">${esc(t.label)}</button>`).join("")
          + `<button type="button" data-i="-1" class="${cur < 0 ? "on" : ""}">${esc(L.lCcoff)}</button>`
          + (L.subAction ? `<button type="button" data-add>${esc(L.lCcadd)}</button>` : "");
      };
      // YouTube lessons: the languages arrive a moment after the video starts; the one you chose last comes back.
      if (v.subsLater) {
        v.addEventListener("yttracks", () => {
          if (!menu.hidden) fill();
          if (v.subsLoading || !tracks().length || pref === "off" || !pref) return;
          const i = tracks().findIndex((t) => t.label === pref || t.language === pref);
          if (i >= 0 && !tracks().some((t) => t.mode === "showing")) pick(i);
        });
        v.addEventListener("play", () => v.loadSubs(), { once: true });
        cc.addEventListener("click", () => v.loadSubs());
      }
      const file = document.createElement("input");
      file.type = "file"; file.accept = ".srt,.vtt"; file.hidden = true;
      box.appendChild(menu); box.appendChild(file);
      cc.addEventListener("click", (e) => { e.stopPropagation(); fill(); menu.hidden = !menu.hidden; });
      menu.addEventListener("click", (e) => {
        e.stopPropagation();
        const b = e.target.closest("button");
        if (!b) return;
        if (b.hasAttribute("data-add")) { file.click(); return; }
        pick(+b.dataset.i); menu.hidden = true; say(b.textContent);
      });
      document.addEventListener("click", () => (menu.hidden = true));
      file.addEventListener("change", () => {
        const f = file.files[0];
        if (!f) return;
        if (!/\.(srt|vtt)$/i.test(f.name)) { say(L.lCcbad); return; }
        const body = new FormData();
        body.append("media", L.media); body.append("file", f);
        fetch(L.subAction, { method: "POST", body, headers: { "X-Inpace-Fetch": "1" } })
          .then((r) => r.ok ? r.json() : { ok: false })
          .then((j) => {
            if (!j.ok) { say(L.lCcbad); return; }
            try { localStorage.setItem("inpace-cc", f.name.replace(/\.[^.]+$/, "")); } catch (e) {}
            tick(true); say(L.lCcsaved); setTimeout(() => location.reload(), 500);
          }).catch(() => say(L.lCcbad));
      });
      box.addEventListener("keydown", (e) => { if (e.key.toLowerCase() === "c" && e.target.tagName !== "INPUT") { cc.click(); } });
    }

    // A video the window can't play: say why, and give a way out instead of a black box.
    let failedShown = false;
    const fail = (why) => {
      if (failedShown) return;
      failedShown = true;
      const esc = (t) => String(t || "").replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
      const ua = navigator.userAgent, webkitGtk = L.system === "linux" && /AppleWebKit/.test(ua) && !/Chrome|Chromium|Edg/.test(ua);
      const plain = ["mp4", "m4v", "webm", ""].indexOf(L.ext || "") >= 0;
      let text, extra = "";
      if (L.system === "android") text = L.lFailphone;
      else if (webkitGtk && plain && why !== "nopic") {
        const command = "sudo apt install gstreamer1.0-libav gstreamer1.0-plugins-bad";
        text = L.lFaillinux;
        extra = `<div class="pl-cmd"><code dir="ltr">${command}</code><button type="button" class="btn small" data-copy-cmd>${esc(L.lFailcopy)}</button></div>`;
      } else if (why === "nopic") text = L.lFailnopic;
      else text = L.lFailformat;
      const panel = document.createElement("div");
      panel.className = "pl-fail";
      panel.innerHTML = `<b>${esc(L.lFailtitle)}</b><p>${esc(text)}</p>${extra}<div class="row wrap">`
        + (L.openAction ? `<button type="button" class="btn primary small" data-open-player>${esc(L.lFailopen)}</button>` : "")
        + `<button type="button" class="btn small" data-again>${esc(L.lFailagain)}</button></div>`;
      box.classList.add("failed");
      box.appendChild(panel);
      panel.addEventListener("click", (e) => e.stopPropagation());
      const copyBtn = panel.querySelector("[data-copy-cmd]");
      copyBtn && copyBtn.addEventListener("click", () => {
        const t = panel.querySelector(".pl-cmd code").textContent;
        (navigator.clipboard ? navigator.clipboard.writeText(t) : Promise.reject()).then(() => (copyBtn.textContent = L.lFailcopied)).catch(() => {});
      });
      const op = panel.querySelector("[data-open-player]");
      op && op.addEventListener("click", () => {
        const body = new FormData(); body.append("media", L.media);
        fetch(L.openAction, { method: "POST", body, headers: { "X-Inpace-Fetch": "1" } }).catch(() => {});
      });
      panel.querySelector("[data-again]").addEventListener("click", () => {
        panel.remove(); box.classList.remove("failed"); failedShown = false; v.load();
      });
    };
    v.addEventListener("error", () => fail("error"));
    const src = v.querySelector("source");
    src && src.addEventListener("error", () => fail("error"));
    const picCheck = () => setTimeout(() => { if (!v.error && v.readyState >= 2 && !v.videoWidth && !v.videoHeight) fail("nopic"); }, 1500);
    v.addEventListener("loadeddata", picCheck, { once: true });
    if (v.error) fail("error");
    state(); draw(); volState(); wake();
    return { toggle };
  };
  window.inpacePlayer = setup;
  document.querySelectorAll("[data-player]").forEach((box) => { const v = box.querySelector("video"); v && setup(box, v); });
})();

// AI course maker: show only the fields for the chosen starting point.
(() => {
  const radios = document.querySelectorAll('input[name="source"]');
  if (!radios.length) return;
  const show = () => {
    const v = (document.querySelector('input[name="source"]:checked') || {}).value || "topic";
    document.querySelectorAll("[data-for-source]").forEach((box) => {
      const on = box.dataset.forSource === v;
      box.hidden = !on;
      box.querySelectorAll("[data-required]").forEach((el) => (el.required = on));
    });
  };
  radios.forEach((r) => r.addEventListener("change", show));
  show();
})();

// "Make a course": show the fields for the chosen way to start.
(() => {
  const radios = document.querySelectorAll('input[name="start"]');
  if (!radios.length) return;
  const show = () => {
    const v = (document.querySelector('input[name="start"]:checked') || {}).value || "blank";
    document.querySelectorAll("[data-for-start]").forEach((box) => (box.hidden = box.dataset.forStart !== v));
  };
  radios.forEach((r) => r.addEventListener("change", show));
  show();
})();

// Lesson editor: formatting buttons and a live preview.
document.querySelectorAll("[data-lesson-editor]").forEach((form) => {
  const ta = form.querySelector("[data-md-target]");
  const edit = (fn) => {
    const s = ta.selectionStart, e = ta.selectionEnd, v = ta.value;
    const [text, a, b] = fn(v.slice(s, e), v, s, e);
    ta.setRangeText(text, s, e, "end");
    ta.focus();
    if (a !== undefined) ta.setSelectionRange(s + a, s + b);
    ta.dispatchEvent(new Event("input"));
  };
  form.querySelectorAll("[data-md]").forEach((b) => b.addEventListener("click", () => {
    const p = b.dataset.md;
    edit((sel, v, s) => {
      const atLineStart = s === 0 || v[s - 1] === "\n";
      const lines = (sel || "").split("\n").map((l) => p + l).join("\n") || p;
      return [(atLineStart ? "" : "\n") + lines];
    });
  }));
  form.querySelectorAll("[data-md-wrap]").forEach((b) => b.addEventListener("click", () => {
    const w = b.dataset.mdWrap;
    edit((sel) => [w + (sel || "text") + w, w.length, w.length + (sel || "text").length]);
  }));
  form.querySelectorAll("[data-md-block]").forEach((b) => b.addEventListener("click", () => {
    edit((sel) => ["\n```\n" + (sel || "code") + "\n```\n", 5, 5 + (sel || "code").length]);
  }));
  form.querySelectorAll("[data-md-link]").forEach((b) => b.addEventListener("click", () => {
    const url = prompt("Link (https://…)", "https://");
    if (url) edit((sel) => [`[${sel || url}](${url})`]);
  }));
  form.querySelectorAll("[data-md-video]").forEach((b) => b.addEventListener("click", () => {
    const ref = prompt("YouTube link, or a file path (video, audio, PDF, page, code)", "https://");
    if (ref) edit(() => [`\n![](${/\s/.test(ref) ? "<" + ref + ">" : ref})\n`]);
  }));
  // Write / Preview tabs
  const preview = form.querySelector(".preview-box");
  form.querySelectorAll("[data-tab]").forEach((tab) => tab.addEventListener("click", async () => {
    form.querySelectorAll("[data-tab]").forEach((t) => t.classList.toggle("on", t === tab));
    form.querySelectorAll("[data-pane]").forEach((p) => (p.hidden = p.dataset.pane !== tab.dataset.tab));
    if (tab.dataset.tab === "preview") {
      const body = new FormData();
      ["title", "content", "media"].forEach((k) => body.append(k, form.elements[k].value));
      preview.innerHTML = "…";
      const r = await fetch(form.dataset.preview, { method: "POST", body });
      preview.innerHTML = await r.text();
    }
  }));
});

// "Move to…" and other selects that save on change.

// Tempo's welcome tour: a spotlight on each part of inPace, with Tempo explaining it.
(() => {
  const data = document.getElementById("tour-data");
  if (!data) return;
  const T = JSON.parse(data.textContent);
  const steps = T.steps;
  let i = 0;
  const shade = document.createElement("div");
  shade.className = "tour-shade";
  const spot = document.createElement("div");
  spot.className = "tour-spot";
  const card = document.createElement("div");
  card.className = "tour-card-pop";
  card.setAttribute("role", "dialog");
  card.setAttribute("aria-modal", "true");
  card.setAttribute("aria-live", "polite");
  document.body.append(shade, spot, card);
  const visible = (el) => el && el.getClientRects().length > 0 && el.getBoundingClientRect().width > 0;
  // On a phone, People, Races, Settings and the rest live in the "More" sheet: open it (without its own backdrop,
  // so the tour stays on top) while a step points inside it, and close it again after.
  const sheet = document.querySelector("[data-more-sheet]");
  const tabbar = document.querySelector(".tabbar");
  const sheetOpen = (on) => {
    if (!sheet) return;
    if (on && !sheet.open) { sheet.setAttribute("open", ""); sheet.classList.add("tour-open"); }
    if (!on && sheet.classList.contains("tour-open")) { sheet.removeAttribute("open"); sheet.classList.remove("tour-open"); }
  };
  const finish = () => {
    fetch("/tour/done", { method: "POST" }).catch(() => {});
    sheetOpen(false);
    [shade, spot, card].forEach((x) => x.remove());
    document.removeEventListener("keydown", keys);
    if (location.search.includes("tour=1")) history.replaceState(null, "", location.pathname);
  };
  const place = () => {
    const s = steps[i];
    // A target can list a few places ("the sidebar link, or the phone tab"): use the first one on screen.
    const found = s.target ? s.target.split(",").map((t) => document.querySelector(t.trim())).filter(Boolean) : [];
    let el = found.find((x) => visible(x) && !(sheet && sheet.contains(x)));
    const inSheet = !el && sheet && visible(tabbar) && found.find((x) => sheet.contains(x));
    sheetOpen(Boolean(inSheet));
    if (inSheet) el = inSheet;
    card.classList.remove("center");
    if (visible(el)) {
      el.scrollIntoView({ block: "nearest" });
      const r = el.getBoundingClientRect(), pad = 6;
      Object.assign(spot.style, { display: "block", top: r.top - pad + "px", left: r.left - pad + "px",
        width: r.width + pad * 2 + "px", height: r.height + pad * 2 + "px" });
      shade.classList.add("clear");
      const narrow = innerWidth < 700;
      const cw = narrow ? innerWidth - 32 : Math.min(380, innerWidth - 32);
      card.style.width = cw + "px";
      const ch = card.offsetHeight;
      let left, top;
      if (narrow) {
        // A phone: the card goes across the screen, above the spot when the spot is low (the tab bar, the More
        // sheet), below it when it's high, so it never covers what it talks about.
        left = 16;
        top = r.top > innerHeight / 2 ? r.top - pad - ch - 14 : r.bottom + pad + 14;
        top = Math.max(12, Math.min(top, innerHeight - ch - 12));
      } else {
        left = r.right + 18; top = Math.max(16, Math.min(r.top - 20, innerHeight - ch - 16));
        if (left + cw > innerWidth - 16) left = r.left - cw - 18;              // no room on the right
        if (left < 16) { left = Math.max(16, Math.min(r.left, innerWidth - cw - 16)); top = r.bottom + 14; } // below
        if (top + ch > innerHeight - 16) top = Math.max(16, r.top - ch - 14);   // above
      }
      Object.assign(card.style, { left: left + "px", top: top + "px" });
    } else {
      spot.style.display = "none";
      shade.classList.remove("clear");
      card.classList.add("center");
      Object.assign(card.style, { left: "", top: "", width: "" });
    }
  };
  const draw = () => {
    const s = steps[i], last = i === steps.length - 1;
    const tempo = document.getElementById("tour-tempo-" + s.mood) || document.getElementById("tour-tempo-happy");
    card.innerHTML = `
      <div class="tour-tempo">${tempo ? tempo.innerHTML : ""}</div>
      <div class="tour-body">
        <p class="tour-count">${i + 1} / ${steps.length}</p>
        <h3></h3><p class="tour-text"></p>
        <div class="tour-actions">
          ${i > 0 ? `<button type="button" class="btn" data-t="back">${T.back}</button>` : `<button type="button" class="btn ghost" data-t="skip">${T.skip}</button>`}
          <button type="button" class="btn primary" data-t="next">${last ? T.done : T.next}</button>
        </div>
      </div>`;
    card.querySelector("h3").textContent = s.title;
    card.querySelector(".tour-text").textContent = s.text;
    card.querySelector('[data-t="next"]').addEventListener("click", () => (last ? finish() : go(1)));
    const b = card.querySelector('[data-t="back"]'); b && b.addEventListener("click", () => go(-1));
    const k = card.querySelector('[data-t="skip"]'); k && k.addEventListener("click", finish);
    place();
    card.querySelector('[data-t="next"]').focus({ preventScroll: true });
  };
  const go = (d) => { i = Math.max(0, Math.min(steps.length - 1, i + d)); draw(); };
  const keys = (e) => {
    if (e.key === "Escape") finish();
    else if (e.key === "ArrowRight" && document.dir !== "rtl" || e.key === "ArrowLeft" && document.dir === "rtl") go(1);
    else if (e.key === "ArrowLeft" && document.dir !== "rtl" || e.key === "ArrowRight" && document.dir === "rtl") go(-1);
  };
  document.addEventListener("keydown", keys);
  addEventListener("resize", place);
  shade.addEventListener("click", () => {});
  draw();
})();

// Search and jump (Ctrl+K or /): courses, lessons, tasks, people and pages.
(() => {
  const btn = document.querySelector("[data-search]");
  const L = document.getElementById("search-labels");
  if (!btn || !L) return;
  let items = null, box = null, list, input, sel = 0, shown = [];
  const norm = (s) => (s || "").toLowerCase().normalize("NFKD").replace(/[ً-ٰٟ]/g, "");
  const score = (it, q) => {
    const t = norm(it.t), k = norm(it.k);
    if (!q) return 1;
    let s = 0;
    for (const w of q.split(/\s+/).filter(Boolean)) {
      if (t.startsWith(w)) s += 5; else if (t.includes(w)) s += 3; else if (k.includes(w)) s += 1; else return 0;
    }
    return s;
  };
  const render = () => {
    const q = norm(input.value.trim());
    shown = items.map((it) => [score(it, q), it]).filter(([s]) => s > 0).sort((a, b) => b[0] - a[0]).slice(0, 40).map(([, it]) => it);
    sel = Math.min(sel, Math.max(0, shown.length - 1));
    list.innerHTML = "";
    if (!shown.length) { const li = document.createElement("li"); li.className = "empty"; li.textContent = L.dataset.empty; list.append(li); return; }
    shown.forEach((it, i) => {
      const li = document.createElement("li");
      li.className = i === sel ? "on" : "";
      li.setAttribute("role", "option");
      li.innerHTML = "<b dir='auto'></b><span dir='auto'></span>";
      li.firstChild.textContent = it.t; li.lastChild.textContent = it.k;
      li.addEventListener("click", () => (location.href = it.u));
      li.addEventListener("mousemove", () => { if (sel !== i) { sel = i; mark(); } });
      list.append(li);
    });
  };
  const mark = () => [...list.children].forEach((li, i) => { li.classList.toggle("on", i === sel); if (i === sel) li.scrollIntoView({ block: "nearest" }); });
  const close = () => { box && box.remove(); box = null; };
  const open = async () => {
    if (box) return;
    box = document.createElement("div");
    box.className = "search-pop";
    box.innerHTML = `<div class="search-card" role="dialog" aria-modal="true"><input type="search" autocomplete="off"><ul role="listbox"></ul><p class="small muted"></p></div>`;
    document.body.append(box);
    input = box.querySelector("input"); list = box.querySelector("ul");
    input.placeholder = L.dataset.placeholder; box.querySelector("p").textContent = L.dataset.hint;
    box.addEventListener("click", (e) => e.target === box && close());
    input.addEventListener("input", () => { sel = 0; render(); });
    input.addEventListener("keydown", (e) => {
      if (e.key === "ArrowDown") { e.preventDefault(); sel = Math.min(shown.length - 1, sel + 1); mark(); }
      else if (e.key === "ArrowUp") { e.preventDefault(); sel = Math.max(0, sel - 1); mark(); }
      else if (e.key === "Enter" && shown[sel]) location.href = shown[sel].u;
      else if (e.key === "Escape") close();
    });
    input.focus();
    if (!items) { try { items = await (await fetch("/nav.json")).json(); } catch (e) { items = []; } }
    render();
  };
  btn.addEventListener("click", open);
  document.addEventListener("keydown", (e) => {
    const typing = /INPUT|TEXTAREA|SELECT/.test(e.target.tagName) || e.target.isContentEditable;
    if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === "k") { e.preventDefault(); open(); }
    else if (e.key === "/" && !typing && !e.target.closest("[data-player]")) { e.preventDefault(); open(); }
    else if (!typing && !e.altKey && !e.ctrlKey && !e.metaKey && (e.key === "n" || e.key === "p") &&
             !e.target.closest("[data-player]")) {
      // N and P: next and previous lesson.
      const a = document.querySelector(e.key === "n" ? "[data-key-next]" : "[data-key-prev]");
      if (a) { e.preventDefault(); a.hasAttribute("data-replace") ? location.replace(a.href) : (location.href = a.href); }
    }
  });
})();

// Back and forward: the app window has no browser buttons, so inPace has its own (top left),
// plus Alt+← / Alt+→ and the side buttons on a mouse.
(() => {
  const back = document.querySelector("[data-nav-back]"), fwd = document.querySelector("[data-nav-fwd]");
  if (!back) return;
  // Back works like in a phone app (see inpaceBack below): it closes what's open, leaves a main page for Home,
  // and otherwise goes one page back.
  const goBack = () => (window.inpaceBack ? window.inpaceBack() : history.back());
  const goFwd = () => history.forward();
  back.addEventListener("click", goBack);
  fwd.addEventListener("click", goFwd);
  // Show which way you can go, where the window can tell.
  const nav = window.navigation;
  const sync = () => {
    if (!nav || nav.canGoBack === undefined) return;
    back.disabled = location.pathname === "/";
    fwd.disabled = !nav.canGoForward;
  };
  back.disabled = location.pathname === "/";
  sync();
  if (nav) nav.addEventListener("currententrychange", sync);
  document.addEventListener("keydown", (e) => {
    if (!e.altKey || e.ctrlKey || e.metaKey || e.shiftKey) return;
    if (/INPUT|TEXTAREA|SELECT/.test(e.target.tagName) || e.target.isContentEditable) return;
    // Left is always back, like in a browser, also in Arabic.
    if (e.key === "ArrowLeft") { e.preventDefault(); goBack(); }
    else if (e.key === "ArrowRight") { e.preventDefault(); goFwd(); }
  });
  window.addEventListener("mouseup", (e) => {
    if (e.button === 3) { e.preventDefault(); goBack(); }
    else if (e.button === 4) { e.preventDefault(); goFwd(); }
  });
})();

// Course search (My courses, the library, roadmaps): every word must match somewhere in the course: title, tags,
// section, description, author, or a module or lesson title. Forgiving: Arabic letter variants and accents don't
// matter, common short names work (k8s, js, ml, postgres), and a small typo still finds the word. The best
// matches come first: a word in the title or tags counts more than one deep in a lesson.
const SEARCH_SAME = { k8s: "kubernetes", js: "javascript", ts: "typescript", py: "python", ml: "machine learning",
  dl: "deep learning", ai: "artificial intelligence", db: "database", postgres: "postgresql", pg: "postgresql",
  sql: "sql", devops: "devops", sre: "observability", cv: "computer vision", nlp: "nlp", llm: "language model",
  cicd: "ci/cd", "c#": "csharp", dotnet: "dotnet", ".net": "dotnet", linux: "linux", os: "operating systems",
  "بايثون": "python", "لينكس": "linux", "انجليزي": "english", "الماني": "german", "اسباني": "spanish" };
function searchFold(s) {
  return String(s || "").toLowerCase().normalize("NFKD").replace(/[̀-ًͯ-ٰٟ]/g, "")
    .replace(/[أإآٱ]/g, "ا").replace(/ة/g, "ه").replace(/ى/g, "ي").replace(/ؤ/g, "و").replace(/ئ/g, "ي").replace(/ـ/g, "");
}
function nearWord(term, words) {  // one letter wrong, missing or extra (for words of 5+ letters)
  if (term.length < 5) return false;
  return words.some((w) => {
    if (Math.abs(w.length - term.length) > 1 || w[0] !== term[0]) return false;
    let i = 0, j = 0, edits = 0;
    while (i < term.length && j < w.length) {
      if (term[i] === w[j]) { i++; j++; continue; }
      if (++edits > 1) return false;
      if (term.length > w.length) i++; else if (w.length > term.length) j++; else { i++; j++; }
    }
    return edits + (term.length - i) + (w.length - j) <= 1;
  });
}
(() => {
  const box = document.querySelector("[data-course-filter]");
  if (!box) return;
  const cards = [...document.querySelectorAll("[data-course-search]")];
  cards.forEach((c, i) => {
    c._order = i;
    c._text = searchFold(c.dataset.courseSearch);
    c._title = searchFold(c.dataset.searchTitle || "");
    c._words = c._text.split(/[^\p{L}\p{N}#+.]+/u).filter(Boolean);
  });
  const none = document.querySelector("[data-course-none]");
  const levelBox = document.querySelector("[data-lib-level]"), langBox = document.querySelector("[data-lib-lang]");
  let topic = "";  // the library's section (or topic) buttons narrow the list too
  const score = (c, terms) => {
    let total = 0;
    for (const t of terms) {
      const alt = SEARCH_SAME[t] ? searchFold(SEARCH_SAME[t]) : null;
      const has = (s) => s.includes(t) || (alt && s.includes(alt));
      if (c._title && has(c._title)) total += 3;
      else if (has(c._text)) total += 1;
      else if (nearWord(t, c._words)) total += 0.5;
      else return -1;   // every word must match somewhere
    }
    return total;
  };
  const run = () => {
    const terms = searchFold(box.value).split(/\s+/).filter(Boolean);
    const level = levelBox ? levelBox.value : "", lang = langBox ? langBox.value : "";
    let shown = 0;
    cards.forEach((c) => {
      const s = terms.length ? score(c, terms) : 0;
      const ok = s >= 0 &&
        (!topic || c.dataset.section === topic || (c.dataset.tags || "").split("|").includes(topic)) &&
        (!level || c.dataset.level === level) && (!lang || c.dataset.lang === lang);
      c._score = s;
      c.hidden = !ok;
      shown += ok;
    });
    // Best matches first inside each list while searching; the usual order otherwise.
    const parents = new Set(cards.map((c) => c.parentElement));
    parents.forEach((p) => {
      const kids = cards.filter((c) => c.parentElement === p);
      kids.sort((a, b) => terms.length ? (b._score - a._score) || (a._order - b._order) : a._order - b._order);
      kids.forEach((k) => p.appendChild(k));
    });
    if (none) none.hidden = shown > 0;
    document.querySelectorAll("[data-lib-section]").forEach((sec) => {
      sec.hidden = !sec.querySelector("[data-course-search]:not([hidden])");
    });
    document.querySelectorAll("[data-folder-box]").forEach((f) => {
      f.hidden = terms.length > 0 && !f.querySelector("[data-course-search]:not([hidden])");
      if (terms.length && !f.hidden) f.querySelector("details").open = true;
    });
  };
  box.addEventListener("input", run);
  levelBox && levelBox.addEventListener("change", run);
  langBox && langBox.addEventListener("change", run);
  document.querySelectorAll("[data-lib-topic]").forEach((b) => b.addEventListener("click", () => {
    topic = b.dataset.libTopic;
    document.querySelectorAll("[data-lib-topic]").forEach((x) => x.setAttribute("aria-pressed", x === b ? "true" : "false"));
    run();
  }));
  if (box.value) run();  // opened from a shared link: show that course
})();

// A library course's sample lesson: shown folded, with a button to read all of it.
(() => {
  const box = document.querySelector("[data-lib-fade]");
  const more = document.querySelector("[data-lib-more]");
  if (!box || !more) return;
  const open = () => { box.classList.add("open"); more.parentElement.hidden = true; };
  if (box.scrollHeight <= box.clientHeight + 10) open();
  more.addEventListener("click", open);
})();

// ---- Android app ---------------------------------------------------------------------------------
// In the Android app there is no browser, so downloads, folder picking and sharing go through the app
// (window.InPaceAndroid, provided by the Flutter shell).
(() => {
  const bridge = window.InPaceAndroid;
  if (!bridge) return;
  document.documentElement.classList.add("android");
  const send = (msg) => bridge.postMessage(JSON.stringify(msg));
  const DOWNLOADS = /^\/(courses\/[^/]+\/(export|publish\/file)|milestones\/[^/]+\/(export|files|record)|people\/card|outbox\/|files\/[0-9a-f]{64}$|races\/[^/]+\/(invite|update)$|me\/turtle\.svg$|island\/share\.svg$|evidence\/[0-9a-f]{64}$|codenote\/lesson\.md$)/;

  // Downloads: the app saves or shares the file.
  document.addEventListener("click", (e) => {
    const a = e.target.closest && e.target.closest("a[href]");
    if (!a) return;
    const url = new URL(a.href, location.href);
    if (url.origin !== location.origin) return;
    if (a.hasAttribute("download") || DOWNLOADS.test(url.pathname)) {
      e.preventDefault();
      send({ type: "download", url: url.href });
    }
  }, true);

  // Forms that answer with a file (backups): fetch it here and hand the file to the app.
  document.addEventListener("submit", async (e) => {
    const form = e.target;
    const picture = form.matches('form[action="/me/turtle.png"], form[action="/island/share.png"]');
    if (!form.matches('form[action="/settings/backup"]') && !picture) return;
    if (picture && !form.png.value) return;  // the picture isn't drawn yet
    e.preventDefault();
    const r = await fetch(form.action, { method: "POST", body: new FormData(form) });
    if (!r.ok || !(r.headers.get("content-disposition") || "").includes("attachment")) { location.href = r.url; return; }
    const cd = r.headers.get("content-disposition") || "";
    const m = cd.match(/filename\*=UTF-8''([^;]+)/);
    const name = m ? decodeURIComponent(m[1]) : "inPace file";
    const buf = new Uint8Array(await r.arrayBuffer());
    let bin = "";
    for (let i = 0; i < buf.length; i += 0x8000) bin += String.fromCharCode.apply(null, buf.subarray(i, i + 0x8000));
    send({ type: "file", name, data: btoa(bin) });
  }, true);

  // "Choose folder" uses Android's folder picker.
  window.inpaceFolderPicked = (selector, path) => {
    const input = document.querySelector(selector);
    if (input && path) { input.value = path; input.dispatchEvent(new Event("input")); }
  };
  document.querySelectorAll("[data-pick-folder]").forEach((btn) => {
    btn.addEventListener("click", (e) => {
      e.stopImmediatePropagation();
      send({ type: "pickFolder", target: btn.dataset.pickFolder });
    }, true);
  });

  // Reminders: the app schedules Android notifications from inPace's plan (reminders, alarms and Tempo's
  // nudges). The plan is sent again whenever you use inPace (at most every 30 minutes), so it stays up to date.
  const onReminders = location.pathname === "/reminders";
  const syncPlan = async (force) => {
    let last = 0;
    try { last = +localStorage.getItem("inpace-plan-at") || 0; } catch (e) {}
    if (!force && Date.now() - last < 30 * 60e3) return;
    try {
      const r = await fetch("/reminders/plan.json");
      if (!r.ok) return;
      send({ type: "notifySync", plan: await r.json() });
      try { localStorage.setItem("inpace-plan-at", String(Date.now())); } catch (e) {}
    } catch (e) {}
  };
  syncPlan(onReminders);
  // Tempo's friendly ask: shown before Android's own permission box, once on a new install, then at most once a
  // week, and when you start a timer or a video while notifications are off. "Maybe later" is fine: no nagging.
  const sheet = document.querySelector("[data-notify-sheet]");
  const NS = "inpace-notify-asked";
  let notifyOn = null, askedNow = false;
  const recently = () => { try { return Date.now() - (+localStorage.getItem(NS) || 0) < 7 * 864e5; } catch (e) { return false; } };
  const askNicely = (force) => {
    if (!sheet || notifyOn !== false || askedNow || sheet.open || document.querySelector(".tour-shade")) return;
    if (!force && recently()) return;
    askedNow = true;
    try { localStorage.setItem(NS, String(Date.now())); } catch (e) { /* private */ }
    sheet.showModal ? sheet.showModal() : sheet.setAttribute("open", "");
  };
  if (sheet) {
    sheet.querySelector("[data-notify-yes]").addEventListener("click", () => { sheet.close(); send({ type: "notifyAllow" }); });
    sheet.querySelector("[data-notify-later]").addEventListener("click", () => sheet.close());
  }
  window.inpaceNotifyState = (state) => {
    const ask = document.querySelector("[data-notify-ask]");
    if (ask) ask.hidden = !!(state && state.enabled);
    notifyOn = !!(state && state.enabled);
    if (notifyOn) syncPlan(true);
    else setTimeout(() => askNicely(false), 1500);  // let the page settle first
  };
  send({ type: "notifyState" });
  addEventListener("inpace-timer", (e) => { if (e.detail && e.detail.on) askNicely(true); });
  window.inpaceAskNotify = () => askNicely(true);
  document.querySelectorAll("[data-notify-allow]").forEach((btn) =>
    btn.addEventListener("click", () => send({ type: "notifyAllow" })));
  document.querySelectorAll("[data-notify-test]").forEach((btn) => {
    btn.addEventListener("click", async (e) => {
      e.preventDefault();
      try {
        const plan = await (await fetch("/reminders/plan.json")).json();
        send({ type: "notifyTest", kind: btn.dataset.notifyTest, message: plan.test, labels: plan.labels });
      } catch (err) {}
    });
  });

  // Focus trip: the app shows Tempo's countdown in a notification while a trip runs, and it keeps counting
  // when inPace is in the background or closed. Every page tells the app how the trip stands now.
  let trip = null;
  try { trip = JSON.parse((document.getElementById("inpace-trip") || {}).textContent || "null"); } catch (e) {}
  if (document.getElementById("inpace-trip")) send({ type: "trip", trip });
  window.inpaceTripChanged = async () => {
    try {
      const r = await fetch("/island/live.json", { cache: "no-store" });
      if (r.ok) { trip = (await r.json()).trip; send({ type: "trip", trip }); }
    } catch (e) {}
  };
  window.inpaceTripPaused = () => { if (trip) send({ type: "trip", trip: { ...trip, state: "paused", ends_ms: null } }); };
  addEventListener("inpace-timer", () => window.inpaceTripChanged());  // the floating timer shows there too

  // Leaving the app (Home button, another app) while a video plays or a timer runs: Android keeps a small
  // window floating over other apps, with the video and the timer in the look picked in Settings.
  // Only a playing video floats. The timer has its own place: the notification, with Pause and Stop.
  const wantPip = () => { const n = window.inpaceNowPlaying; return !!(n && !n.v.paused && !n.v.ended); };
  let lastPip = null;
  const tellPip = () => { const w = wantPip(); if (w !== lastPip) { lastPip = w; send({ type: "pip", auto: w }); } };
  setInterval(tellPip, 1500);
  document.addEventListener("play", tellPip, true);
  document.addEventListener("pause", tellPip, true);
  // The lesson video in Android's media controls (the notification shade and lock screen), like YouTube's.
  let mediaTimer = null;
  window.inpaceMediaChanged = () => {
    if (window.inpaceNowPlaying && !inpaceNowPlaying.v.paused && window.inpaceAskNotify) inpaceAskNotify();
    clearTimeout(mediaTimer);
    mediaTimer = setTimeout(() => {
      const n = window.inpaceNowPlaying;
      if (!n || !window.inpaceMediaInfo) return;
      const v = n.v, i = inpaceMediaInfo(n.box);
      send({ type: "media", state: { active: true, title: i.lesson, artist: i.course, art: i.art,
        playing: !v.paused && !v.ended, position: v.currentTime || 0, duration: isFinite(v.duration) ? v.duration : 0,
        rate: v.playbackRate || 1, next: !!document.querySelector("[data-key-next]"), prev: !!document.querySelector("[data-key-prev]") } });
    }, 80);
  };
  addEventListener("pagehide", () => { if (window.inpaceNowPlaying) send({ type: "media", state: { active: false } }); });
  window.inpacePip = (on) => {
    const n = window.inpaceNowPlaying;
    const wasPlaying = !!(n && !n.v.paused && !n.v.ended);
    document.documentElement.classList.toggle("in-pip", !!on);
    document.querySelectorAll(".pip-video").forEach((x) => x.classList.remove("pip-video"));
    if (on && n) n.box.classList.add("pip-video");
    if (!on) {
      // Back in the app: lay the page out again for the full screen, and if the video was playing when the
      // floating window opened back up, make sure it still is (Android can pause it on the way).
      requestAnimationFrame(() => dispatchEvent(new Event("resize")));
      if (wasPlaying) setTimeout(() => {
        if (document.visibilityState === "visible" && n.box.isConnected && n.v.paused && !n.v.ended) n.v.play();
      }, 1200);
    }
  };

  // "More apps…" opens Android's share sheet.
  document.querySelectorAll("[data-share]").forEach((btn) => {
    btn.hidden = false;
    btn.addEventListener("click", () => send({ type: "share", text: document.querySelector(btn.dataset.share).value }));
  });
})();

// ---- Add a course: sort the files ------------------------------------------------------------------
// Sections and files live in the page; on submit they're written into one hidden "plan" field.
(() => {
  const form = document.querySelector("[data-organizer]");
  if (!form) return;
  const box = form.querySelector("[data-sections]");
  const out = form.querySelector("[data-out]");
  const outLabel = form.querySelector("[data-out-label]").innerHTML.trim();
  const sections = () => [...box.querySelectorAll(":scope > [data-sec]")];
  const lists = () => [...sections().map((s) => s.querySelector("[data-files]")), out.querySelector("[data-files]")];
  const size = (n) => {
    const u = ["bytes", "KB", "MB", "GB", "TB"];
    let i = 0;
    while (n >= 1024 && i < u.length - 1) { n /= 1024; i++; }
    return i ? n.toFixed(1) + " " + u[i] : n + " bytes";
  };

  const refresh = () => {
    const secs = sections();
    secs.forEach((s, i) => {
      s.querySelector(".org-num").textContent = i + 1;
      s.querySelector("[data-sec-up]").disabled = i === 0;
      s.querySelector("[data-sec-down]").disabled = i === secs.length - 1;
      s.classList.toggle("empty", !s.querySelector(".org-file"));
    });
    const names = secs.map((s, i) => `${i + 1}. ${s.querySelector("[data-sec-title]").value || "…"}`);
    lists().forEach((list, li) => {
      const rows = [...list.children];
      rows.forEach((row, ri) => {
        const sel = row.querySelector("[data-move]");
        sel.innerHTML = "";
        names.forEach((n, i) => sel.add(new Option(n, i, false, i === li)));
        sel.add(new Option("— " + outLabel, "out", false, li === names.length));
        row.querySelector("[data-file-up]").disabled = ri === 0;
        row.querySelector("[data-file-down]").disabled = ri === rows.length - 1;
      });
    });
    let total = 0, n = 0;
    secs.forEach((s) => s.querySelectorAll(".org-file").forEach((r) => { total += +r.dataset.size; n++; }));
    const count = form.querySelector("[data-count]");
    if (count) count.textContent = count.dataset.msg.replace("{n}", n).replace("{s}", secs.filter((s) => s.querySelector(".org-file")).length);
    const space = form.querySelector("[data-space]");
    if (space) {
      const free = +space.dataset.free;
      const full = free && total > free;
      const msg = full ? space.dataset.full : total > 2 * 1024 ** 3 ? space.dataset.big : space.dataset.msg;
      space.textContent = msg.replace("{size}", size(total)).replace("{free}", size(free));
      space.classList.toggle("warn", total > 2 * 1024 ** 3 || full);
      const copy = form.querySelector("[data-copy-choice]");
      copy.disabled = !!full;
      if (full && copy.checked) form.querySelector('[name=storage][value=keep]').checked = true;
    }
  };

  const moveTo = (row, target) => {
    const list = target === "out" ? out.querySelector("[data-files]") : sections()[+target].querySelector("[data-files]");
    list.appendChild(row);
    refresh();
    row.querySelector("[data-move]").focus();
  };

  form.addEventListener("change", (e) => {
    if (e.target.matches("[data-move]")) moveTo(e.target.closest(".org-file"), e.target.value);
  });
  form.addEventListener("input", (e) => { if (e.target.matches("[data-sec-title]")) refresh(); });
  form.addEventListener("click", (e) => {
    const b = e.target.closest("button");
    if (!b) return;
    const row = b.closest(".org-file");
    const sec = b.closest("[data-sec]");
    if (b.matches("[data-file-up]") && row.previousElementSibling) row.parentNode.insertBefore(row, row.previousElementSibling);
    else if (b.matches("[data-file-down]") && row.nextElementSibling) row.parentNode.insertBefore(row.nextElementSibling, row);
    else if (b.matches("[data-sec-up]") && sec.previousElementSibling) box.insertBefore(sec, sec.previousElementSibling);
    else if (b.matches("[data-sec-down]") && sec.nextElementSibling) box.insertBefore(sec.nextElementSibling, sec);
    else if (b.matches("[data-sec-remove]")) {
      sec.querySelectorAll(".org-file").forEach((r) => out.querySelector("[data-files]").appendChild(r));
      sec.remove();
    } else if (b.matches("[data-sec-add]")) {
      const s = form.querySelector("[data-sec-tpl]").content.firstElementChild.cloneNode(true);
      box.appendChild(s);
      refresh();
      const t = s.querySelector("[data-sec-title]");
      t.focus(); t.select();
      return;
    } else return;
    refresh();
    b.focus();
  });

  // Drag and drop with a mouse (on phones, "Move to" and the arrows do the same).
  let dragged = null;
  form.addEventListener("dragstart", (e) => {
    dragged = e.target.closest && e.target.closest(".org-file");
    if (!dragged) return;
    dragged.classList.add("dragging");
    e.dataTransfer.effectAllowed = "move";
    e.dataTransfer.setData("text/plain", dragged.dataset.file);
  });
  form.addEventListener("dragend", () => { if (dragged) dragged.classList.remove("dragging"); dragged = null; refresh(); });
  form.addEventListener("dragover", (e) => {
    if (!dragged) return;
    const sec = e.target.closest("[data-sec], [data-out]");
    if (!sec) return;
    e.preventDefault();
    const list = sec.querySelector("[data-files]");
    const over = e.target.closest(".org-file");
    if (over && over !== dragged) {
      const r = over.getBoundingClientRect();
      list.insertBefore(dragged, e.clientY > r.top + r.height / 2 ? over.nextSibling : over);
    } else if (!over) list.appendChild(dragged);
  });
  form.addEventListener("drop", (e) => { if (dragged) e.preventDefault(); });

  form.addEventListener("submit", () => {
    const names = {};
    const plan = { title: form.querySelector("[data-title]").value, names, sections: sections().map((s) => ({
      title: s.querySelector("[data-sec-title]").value,
      files: [...s.querySelectorAll(".org-file")].map((r) => {
        const inp = r.querySelector(".org-name");
        if (inp.value.trim() && inp.value !== inp.dataset.default) names[r.dataset.file] = inp.value.trim();
        return r.dataset.file;
      }),
    })) };
    form.querySelector("[data-plan]").value = JSON.stringify(plan);
  });
  refresh();
})();

// Picking files to add: show how big they are, and a note while they upload.
(() => {
  const form = document.querySelector("[data-upload-form]");
  if (!form) return;
  const input = form.querySelector("[data-upload-files]");
  const note = form.querySelector("[data-upload-size]");
  input.addEventListener("change", () => {
    let total = 0;
    for (const f of input.files) total += f.size;
    const mb = total / 1024 / 1024;
    note.hidden = !input.files.length;
    note.textContent = `${input.files.length} · ${mb >= 1024 ? (mb / 1024).toFixed(1) + " GB" : mb.toFixed(1) + " MB"}`;
  });
  form.addEventListener("submit", () => {
    form.querySelector("[data-upload-wait]").hidden = false;
    form.querySelector("button").disabled = true;
  });
})();

// Phones: the "More" tab opens a sheet with the other pages.
(() => {
  const sheet = document.querySelector("[data-more-sheet]");
  const open = document.querySelector("[data-more-open]");
  if (!sheet || !open) return;
  open.addEventListener("click", () => (sheet.showModal ? sheet.showModal() : sheet.setAttribute("open", "")));
  const close = () => (sheet.close ? sheet.close() : sheet.removeAttribute("open"));
  sheet.querySelector("[data-more-close]").addEventListener("click", close);
  sheet.addEventListener("click", (e) => { if (e.target === sheet) close(); });  // tap outside
})();

// Reminders: "Every day", "Weekdays" and "Weekends" tick the right days. "Other…" swaps the days for
// "every N days, starting on a day you pick"; "Pick days of the week instead" swaps back.
document.querySelectorAll("[data-rem-other]").forEach((btn) => {
  const form = btn.closest("form"), box = form.querySelector("[data-rem-every]");
  const set = (on) => {
    box.hidden = !on; btn.setAttribute("aria-expanded", String(on)); btn.classList.toggle("primary", on);
    form.querySelector("[data-rem-repeat]").value = on ? "every" : "days";
    box.querySelectorAll("input").forEach((i) => { i.disabled = !on; });
    form.querySelectorAll(".rem-day-chips input").forEach((i) => { i.disabled = on; });
    form.querySelector(".rem-day-chips").classList.toggle("rem-off", on);
    if (on) box.querySelector('input[name="every"]').focus();
  };
  form._remOther = set;
  form.addEventListener("reset", () => setTimeout(() => set(false)));  // after "Add": back to days of the week, all in step
  btn.addEventListener("click", () => set(box.hidden));
  box.querySelector("[data-rem-weekdays]").addEventListener("click", () => set(false));
});

// Moving inside a course (next lesson, previous, module tasks, next module, a quiz) replaces the page
// instead of adding one, so Back always takes you out to the course, not through every lesson.
// [data-up] links go back when that page is right behind you, so it isn't opened twice.
(() => {
  const path = (u) => { try { const x = new URL(u, location.href); return x.origin === location.origin ? x.pathname : null; } catch (e) { return null; } };
  const goUp = (href) => {
    const want = path(href);
    const nav = window.navigation;
    if (nav && nav.entries && nav.currentEntry) {
      const list = nav.entries(), here = nav.currentEntry.index;
      for (let i = here - 1; i >= 0 && i >= here - 3; i--) {
        if (path(list[i].url) === want) { nav.traverseTo(list[i].key); return; }
      }
    } else if (document.referrer && path(document.referrer) === want && history.length > 1) { history.back(); return; }
    location.href = href;
  };
  document.addEventListener("click", (e) => {
    if (e.defaultPrevented || e.button !== 0 || e.ctrlKey || e.metaKey || e.shiftKey || e.altKey) return;
    const a = e.target.closest("a[data-replace], a[data-up]");
    if (!a || a.target) return;
    e.preventDefault();
    if (a.hasAttribute("data-up")) goUp(a.href); else location.replace(a.href);
  });
  // Forms marked [data-nav-form] are sent in the background. The server answers with where to go,
  // and the page is replaced, so a sent form never sits behind the Back button.
  document.addEventListener("submit", async (e) => {
    const f = e.target;
    if (!(f instanceof HTMLFormElement) || !f.hasAttribute("data-nav-form") || e.defaultPrevented) return;
    e.preventDefault();
    if (f.dataset.sending) return;
    f.dataset.sending = "1";
    f.querySelectorAll("button").forEach((b) => { b.disabled = true; });
    const body = new FormData(f);
    if (e.submitter && e.submitter.name) body.append(e.submitter.name, e.submitter.value);
    try {
      const r = await fetch(f.action || location.href, { method: "POST", body, headers: { "X-InPace-Nav": "1" } });
      const type = r.headers.get("content-type") || "";
      if (type.includes("application/json")) {
        const data = await r.json();
        if (data && data.go) {
          // Back to this same page: update only what changed (see "Buttons update in place").
          const clean = () => { delete f.dataset.sending; f.querySelectorAll("button").forEach((b) => { b.disabled = false; }); };
          if (window.inpaceSoftGo && await window.inpaceSoftGo(data.go, clean)) { if (f.isConnected) f.reset(); return; }
          goFresh(data.go); return;
        }
      }
      if (type.includes("text/html")) {  // a page with a message (for example, a mistake in the form)
        const html = await r.text();
        document.open(); document.write(html); document.close();
        return;
      }
      location.reload();
    } catch (err) {
      delete f.dataset.sending;
      f.querySelectorAll("button").forEach((b) => { b.disabled = false; });
      f.removeAttribute("data-nav-form");
      sendForm(f);  // offline or blocked: send it the normal way
    }
  });
})();

// "⋯" menus: only one open at a time; a tap outside or Escape closes it.
(() => {
  const menus = () => document.querySelectorAll("details.menu[open]");
  document.addEventListener("toggle", (e) => {
    const d = e.target;
    if (!(d instanceof HTMLDetailsElement) || !d.classList.contains("menu") || !d.open) return;
    menus().forEach((m) => { if (m !== d) m.open = false; });
  }, true);
  document.addEventListener("click", (e) => {
    menus().forEach((m) => { if (!m.contains(e.target)) m.open = false; });
  });
  document.addEventListener("keydown", (e) => {
    if (e.key === "Escape") menus().forEach((m) => { m.open = false; m.querySelector("summary")?.focus(); });
  });
})();


// Tempo's island: a friend says hello when you tap them.
(() => {
  const say = document.querySelector("[data-friend-say]");
  if (!say) return;
  const lines = JSON.parse(document.getElementById("friend-lines")?.textContent || "{}");
  document.querySelectorAll(".isle-friend").forEach((f) => {
    f.style.cursor = "pointer";
    f.addEventListener("click", () => {
      const k = f.dataset.friend;
      if (!lines[k]) return;
      say.textContent = lines[k];
      say.hidden = false;
      f.classList.remove("hop"); void f.getBoundingClientRect(); f.classList.add("hop");
    });
  });
})();

// The focus trip: count down, grow the plant, plant it on the island when the time is up.
(() => {
  const box = document.querySelector("[data-trip]");
  if (!box || box.hidden) return;
  const goal = +box.dataset.goal, mode = box.dataset.mode;
  let base = +box.dataset.elapsed, t0 = Date.now(), state = box.dataset.state, finishing = false;
  const timeEl = box.querySelector("[data-time]");
  const stones = [...box.querySelectorAll("[data-stone]")];
  const stages = [...box.querySelectorAll(".trip-stage")];
  const note = box.querySelector("[data-paused]");
  const title = document.title;
  const now = () => (state === "running" ? base + (Date.now() - t0) / 1000 : base);
  const fmt = (s) => { s = Math.max(0, Math.ceil(s)); return String(Math.floor(s / 60)).padStart(2, "0") + ":" + String(s % 60).padStart(2, "0"); };
  const chime = () => {
    try {
      const a = new (window.AudioContext || window.webkitAudioContext)();
      [523.25, 659.25, 783.99, 1046.5].forEach((f, i) => {
        const o = a.createOscillator(), g = a.createGain();
        o.type = "sine"; o.frequency.value = f; o.connect(g); g.connect(a.destination);
        const t = a.currentTime + i * 0.16;
        g.gain.setValueAtTime(0.0001, t); g.gain.exponentialRampToValueAtTime(0.2, t + 0.02); g.gain.exponentialRampToValueAtTime(0.0001, t + 0.6);
        o.start(t); o.stop(t + 0.65);
      });
    } catch (e) { /* no sound here */ }
  };
  const told = () => { if (window.inpaceTripChanged) window.inpaceTripChanged(); };  // the phone's notification
  const done = () => {
    box.hidden = true;
    told();
    const d = document.querySelector("[data-trip-done]");
    if (d) d.hidden = false;
    document.title = title;
    chime();
    burstConfetti();
  };
  const finish = async () => {
    try {
      const d = await (await fetch("/island/done", { method: "POST" })).json();
      if (d.grown) return done();
      base = d.elapsed; t0 = Date.now();
    } catch (e) { /* try again next tick */ }
    finishing = false;
  };
  const draw = () => {
    const e = now(), p = Math.min(1, e / goal);
    timeEl.textContent = fmt(goal - e);
    if (state === "running") document.title = fmt(goal - e) + " · " + title;
    stones.forEach((s, i) => s.classList.toggle("on", p >= (i + 1) / 10));
    let cur = stages[0];
    stages.forEach((g) => { if (+g.dataset.g <= Math.max(p, 0.05) + 1e-9) cur = g; });
    stages.forEach((g) => { if (g === cur) g.removeAttribute("hidden"); else g.setAttribute("hidden", ""); });
    if (p >= 1 && !finishing) { finishing = true; finish(); }
  };
  setInterval(draw, 1000);
  draw();
  const sync = async () => {
    try {
      const d = await (await fetch("/island/resume", { method: "POST" })).json();
      if (d.grown) return done();
      if (state === "paused" && note) note.hidden = false;
      base = d.elapsed; t0 = Date.now(); state = d.state;
      told();
    } catch (e) { /* offline: keep counting here */ }
  };
  let lock = null;
  const keepAwake = async () => { try { if (mode === "phone" && navigator.wakeLock) lock = await navigator.wakeLock.request("screen"); } catch (e) { lock = null; } };
  keepAwake();
  document.addEventListener("visibilitychange", () => {
    if (document.hidden) {
      if (mode === "phone" && state === "running") {
        base = now(); state = "paused";
        if (navigator.sendBeacon) navigator.sendBeacon("/island/pause"); else fetch("/island/pause", { method: "POST", keepalive: true });
        if (window.inpaceTripPaused) window.inpaceTripPaused();
      }
    } else {
      sync();
      keepAwake();
    }
  });
})();

// ---- Your turtle (v1.17) ----------------------------------------------------------------------------
// The maker recolours a plain Tempo (kept in data-tbase) with the shell, scarf and skin you pick,
// and shows only the thing you chose to wear. "Save a picture" draws the share card as a PNG.
(() => {
  document.querySelectorAll("[data-turtle-maker]").forEach((maker) => {
    let colors;
    try { colors = JSON.parse(maker.querySelector("[data-turtle-colors]").textContent); } catch (e) { return; }
    const pick = (name) => Number((maker.querySelector(`input[name="${name}"]:checked`) || {}).value || 0);
    const recolor = (svg) => {
      const shell = colors.shells[pick("shell")], scarf = colors.scarves[pick("scarf")], skin = colors.skins[pick("skin")];
      const to = [shell[0], shell[1], shell[2], shell[3], scarf[0], scarf[1], skin[0], skin[1], skin[2]];
      // two steps, so one swap can't undo another (same as mascot._recolor)
      colors.base.forEach((from, i) => { if (from !== to[i]) svg = svg.split(from).join(`@@${i}@@`); });
      to.forEach((c, i) => { svg = svg.split(`@@${i}@@`).join(c); });
      return svg;
    };
    const draw = () => {
      maker.querySelectorAll("[data-tbase]").forEach((el) => { el.innerHTML = recolor(el.dataset.tbase); });
      const acc = (maker.querySelector('input[name="acc"]:checked') || {}).value || "none";
      maker.querySelectorAll("[data-turtle-preview] [data-acc]").forEach((g) => { g.toggleAttribute("hidden", g.dataset.acc !== acc); });
    };
    maker.addEventListener("change", draw);
  });

  // "Save a picture of my turtle" and "Share my island": the page draws the SVG as a PNG and sends it back.
  document.querySelectorAll("[data-turtle-png], [data-share-island]").forEach((form) => {
  const src = form.hasAttribute("data-share-island") ? "/island/share.svg" : "/me/turtle.svg";
  form.addEventListener("submit", async (e) => {
    if (form.png.value) return;  // the picture is ready: let the form send it
    e.preventDefault();
    e.stopImmediatePropagation();
    try {
      const svg = await (await fetch(src)).text();
      const url = URL.createObjectURL(new Blob([svg], { type: "image/svg+xml" }));
      const img = new Image();
      await new Promise((ok, bad) => { img.onload = ok; img.onerror = bad; img.src = url; });
      const canvas = document.createElement("canvas");
      canvas.width = canvas.height = 1080;
      canvas.getContext("2d").drawImage(img, 0, 0, 1080, 1080);
      URL.revokeObjectURL(url);
      form.png.value = canvas.toDataURL("image/png");
      form.requestSubmit ? form.requestSubmit() : form.submit();
      setTimeout(() => { form.png.value = ""; }, 1000);
    } catch (err) {
      location.href = src;
    }
  }, true);
  });
})();

// Course page: while the course's videos download, show how far along it is (asks inPace every 1.5 seconds).
(() => {
  const card = document.querySelector("[data-offline]");
  const job = card && card.querySelector("[data-offline-job]");
  if (!job || job.hidden) return;
  const $ = (s) => card.querySelector(s);
  const poll = async () => {
    try {
      const d = await (await fetch(card.dataset.offline, { cache: "no-store" })).json();
      const j = d.job || {};
      if (j.state !== "running") { location.reload(); return; }
      const pct = j.total ? ((j.done + (j.percent || 0) / 100) / j.total) * 100 : 0;
      $("[data-offline-bar]").style.width = pct.toFixed(1) + "%";
      $("[data-offline-num]").textContent = `${j.done} / ${j.total || "…"}`;
      const quick = document.querySelector("[data-offline-quick-num]");  // the small one at the top of the page
      if (quick) quick.textContent = `${j.done} / ${j.total || "…"}`;
      $("[data-offline-now]").textContent = j.title ? `${j.title}${j.percent ? " · " + Math.round(j.percent) + "%" : ""}` : "";
    } catch (e) { /* inPace is busy: try again */ }
    setTimeout(poll, 1500);
  };
  poll();
})();

// Course page: the small links at the top open the "Watch offline" box at the bottom and go there.
document.addEventListener("click", (ev) => {
  const a = ev.target.closest("[data-offline-open]");
  const box = a && document.getElementById("offline");
  if (box && box.tagName === "DETAILS") box.open = true;
});

// Lessons: the "Download this video" button under a YouTube video. It downloads in the background and shows
// how far along it is, right there; when it's saved, one tap plays the copy on this device.
(() => {
  const forms = document.querySelectorAll("form.yt-save[data-yt-save]");
  if (!forms.length) return;
  const show = (f, d) => {
    const btn = f.querySelector("button"), note = f.querySelector("[data-yt-save-note]"), L = f.dataset;
    const busy = d.state === "downloading" || d.state === "waiting";
    f.dataset.state = d.state;
    btn.hidden = busy;
    note.classList.toggle("muted", !busy);
    note.textContent = "";
    if (busy) { const s = document.createElement("span"); s.className = "spin"; s.setAttribute("aria-hidden", "true"); note.append(s); }
    if (d.state === "downloading") note.append(L.lDownloading.replace("{percent}", Math.round(d.percent || 0) + "%"));
    else if (d.state === "waiting") note.append(L.lWaiting);
    else if (d.state === "failed") { note.append(`${L.lFailed} ${d.why || ""}`); btn.querySelector("span").textContent = L.lAgain; }
    else if (d.state === "saved") {
      btn.hidden = true;
      note.append(L.lSaved + " ");
      const play = document.createElement("button");
      play.type = "button"; play.className = "btn small"; play.textContent = "▶ " + L.lPlay;
      play.addEventListener("click", () => location.reload());
      note.append(play);
    }
    return busy;
  };
  const watch = (f) => {
    const poll = async () => {
      let d;
      try { d = (await (await fetch(f.dataset.ytSave, { cache: "no-store" })).json()).video || {}; }
      catch (e) { setTimeout(poll, 3000); return; }  // inPace is busy: ask again a bit later
      if (show(f, d)) setTimeout(poll, 1500);
    };
    poll();
  };
  forms.forEach((f) => {
    if (f.dataset.state === "downloading" || f.dataset.state === "waiting") watch(f);
    f.addEventListener("submit", async (ev) => {
      ev.preventDefault();
      const btn = f.querySelector("button"), note = f.querySelector("[data-yt-save-note]");
      btn.disabled = true;
      note.textContent = f.dataset.lStarting;
      try {
        const r = await fetch(f.action, { method: "POST", body: new FormData(f), headers: { Accept: "application/json" } });
        const d = await r.json();
        btn.disabled = false;
        if (!d.ok) { note.textContent = d.message || f.dataset.lFailed; return; }
        if (show(f, d)) watch(f);
        if (window.inpaceDownloadsPoke) inpaceDownloadsPoke();
      } catch (e) {
        btn.disabled = false;
        note.textContent = f.dataset.lOffline;
      }
    });
  });
})();


// ---- Feels like an app, on every device (v1.23) ---------------------------------------------------------------
// inPace is pages drawn by Python, but it should move like an app:
//  * The main places (Home, My courses, Add, Milestones, the island…) are like tabs: going from one to another
//    replaces the page instead of stacking it, and tapping the one you're on scrolls to the top.
//  * Back closes what's open first (a sheet, a menu, full screen). On a main place it goes Home; on Home it
//    leaves the app (on a phone). Everywhere else it goes one page back, or up to the page it belongs to.
//  * Pages slide in going forward and slide back going back; tabs fade (the CSS reads <html data-nav>).
//  * A thin bar shows at the top when a page takes more than a moment.
(() => {
  const ROOTS = ["/", "/courses", "/roadmaps", "/add", "/milestones", "/island", "/races", "/library", "/people", "/open", "/reminders", "/settings"];
  const clean = (p) => p.replace(/\/+$/, "") || "/";
  const isRoot = (p) => ROOTS.includes(clean(p));
  const here = () => clean(location.pathname);
  const hint = (kind) => { try { sessionStorage.setItem("inpace-nav", kind); } catch (e) { /* private window */ } };
  const busy = () => { clearTimeout(busy.t); busy.t = setTimeout(() => document.documentElement.classList.add("nav-busy"), 180); };
  const idle = () => { clearTimeout(busy.t); document.documentElement.classList.remove("nav-busy"); };
  window.inpaceIdle = idle;
  window.addEventListener("pageshow", idle);
  window.addEventListener("pagehide", idle);

  // Close whatever is open on top of the page. Says whether something was closed.
  const closeTop = () => {
    if (document.fullscreenElement) { document.exitFullscreen(); return true; }
    const dialogs = document.querySelectorAll("dialog[open]");
    if (dialogs.length) { const d = dialogs[dialogs.length - 1]; if (d.close) d.close(); else d.removeAttribute("open"); return true; }
    const open = document.querySelector(".diagram-full [data-d-close], body.diagram-open [data-d-full]");
    if (open) { open.click(); return true; }
    const menu = document.querySelector("details.menu[open], details.course-menu[open]");
    if (menu) { menu.open = false; return true; }
    return false;
  };

  // The one Back for the button at the top, the phone's Back and Alt+←. Returns "handled", or "exit" on Home.
  window.inpaceBack = () => {
    if (closeTop()) return "handled";
    if (here() === "/") return "exit";
    if (isRoot(here())) { hint("back"); busy(); location.replace("/"); return "handled"; }
    const nav = window.navigation;
    const canBack = nav && nav.canGoBack !== undefined ? nav.canGoBack : history.length > 1;
    if (canBack) { history.back(); return "handled"; }
    const up = document.querySelector("a[data-up]");
    hint("back"); busy();
    location.replace(up ? up.href : "/");
    return "handled";
  };

  document.addEventListener("click", (e) => {
    if (e.defaultPrevented || e.button !== 0 || e.ctrlKey || e.metaKey || e.shiftKey || e.altKey) return;
    const a = e.target.closest("a[href]");
    if (!a || a.target || a.hasAttribute("download")) return;
    let url;
    try { url = new URL(a.href); } catch (err) { return; }
    if (url.origin !== location.origin) return;
    const tab = a.closest("nav.side, nav.tabbar, .more-sheet, header.top") && isRoot(url.pathname) && !url.search;
    if (tab && clean(url.pathname) === here() && !location.search) {  // the tab you're on: go to the top, with fresh numbers
      e.preventDefault();
      closeTop();
      window.scrollTo({ top: 0, behavior: "smooth" });
      if (window.inpaceRefresh) window.inpaceRefresh();
      return;
    }
    if (tab && isRoot(here())) {  // tab to tab: swap, don't stack
      e.preventDefault();
      hint("tab"); busy();
      location.replace(a.href);
      return;
    }
    if (url.pathname !== location.pathname || url.search !== location.search) busy();
  });
  document.addEventListener("submit", (e) => { if (!e.defaultPrevented && !e.target.closest("form.yt-save")) busy(); });

  // Nothing here is a web page to the person using it: no menu of "Open link in new tab" on a long press or right
  // click, except where it helps (text you typed, text you selected, lesson content, pictures and links in lessons).
  document.addEventListener("contextmenu", (e) => {
    const t = e.target;
    if (t.closest("input, textarea, select, [contenteditable], article, .lesson, pre, code, .player, video, audio")) return;
    if (String(window.getSelection && window.getSelection()).trim()) return;
    e.preventDefault();
  });
  // Links and pictures of the app itself don't drag out like on a web page.
  document.addEventListener("dragstart", (e) => {
    if (e.target.closest && e.target.closest("a, img, svg") && !e.target.closest("article, [draggable=true], .b-les, .b-mod")) e.preventDefault();
  });
})();

// ---- Fresh without reloading (v1.23) ---------------------------------------------------------------------------
// Like a Flutter screen that rebuilds only the widgets whose data changed: a page can mark its main part with
// [data-live]. When you come back to the app (or tap the tab you're on), inPace asks Python for the page again
// and changes only the parts that are different: a progress bar, a number, the next lesson. Nothing blinks, your
// place on the page stays, and open sections stay open. If a changed part needs its script again (a player, a
// folder picker), the page is simply loaded again.
(() => {
  // Never swapped: parts with a script on them (any data- hook, except ones handled for the whole page, or a
  // video, a frame, a text box). If one of them would have to be swapped, the page loads normally instead.
  const TAGS = "script, input:not([type=hidden]), textarea, select, video, audio, iframe, canvas, dialog";
  // Hooks handled by listeners on the whole document, so a freshly drawn copy works by itself (v1.31.2).
  const DELEGATED = new Set(["data-live", "data-live-buttons", "data-up", "data-replace", "data-nav-form", "data-confetti",
    "data-l", "data-tip", "data-autosubmit", "data-busy", "data-days", "data-theme-toggle", "data-look", "data-progress",
    "data-confirm", "data-dl-form", "data-dl-link", "data-codenote", "data-codenote-only", "data-course", "data-lesson",
    "data-task"]);
  const hooked = (n) => n.nodeType === 1 && (n.matches(TAGS)
    || [...n.attributes].some((at) => at.name.startsWith("data-") && !DELEGATED.has(at.name)));
  const scripted = (n) => n.nodeType === 1 && (hooked(n) || [...n.querySelectorAll("*")].some(hooked));
  class NeedsReload extends Error {}

  // a: the part on screen; b: the same part, freshly drawn by Python; p: how a looked when the page loaded.
  // Only what Python changed is changed here; what a script changed (an open section, a picture drawn from a
  // diagram, a button's busy label) is left alone, or, if it can't be, the page loads again.
  const patch = (a, b, p) => {
    if (p && p.isEqualNode(b)) return;  // Python drew the same thing: nothing to do
    if (!p && a.isEqualNode(b)) return;
    const same = a.nodeType === 1 && b.nodeType === 1 && a.tagName === b.tagName && a.childNodes.length === b.childNodes.length
      && (!p || (p.nodeType === 1 && p.childNodes.length === a.childNodes.length));
    if (!same) {
      if ((p && !a.isEqualNode(p)) || scripted(a) || scripted(b)) throw new NeedsReload();
      a.replaceWith(document.importNode(b, true));
      return;
    }
    const was = (name) => (p ? p.getAttribute(name) : a.getAttribute(name));
    for (const at of [...(p || a).attributes]) {
      if (!b.hasAttribute(at.name) && !(a.tagName === "DETAILS" && at.name === "open")) a.removeAttribute(at.name);
    }
    for (const at of [...b.attributes]) if (was(at.name) !== at.value) a.setAttribute(at.name, at.value);
    const mine = [...a.childNodes], theirs = [...b.childNodes], before = p ? [...p.childNodes] : [];
    for (let i = 0; i < mine.length; i++) patch(mine[i], theirs[i], p ? before[i] : null);
  };
  // Patch every live part from a freshly drawn page. Throws NeedsReload when it can't be done safely.
  const apply = (doc) => {
    const root = document.documentElement, fresh = doc.documentElement;
    for (const k of ["lang", "dir"]) if (root.getAttribute(k) !== fresh.getAttribute(k)) throw new NeedsReload();
    for (const k of ["accent", "theme", "black"]) if (root.dataset[k] !== fresh.dataset[k]) throw new NeedsReload();
    const live = [...document.querySelectorAll("[data-live][id]")];
    // Check every part first (on copies), so a page is never left half changed.
    for (const part of live) {
      const next = doc.getElementById(part.id);
      if (next) patch(part.cloneNode(true), next, inpacePristine.get(part.id));
    }
    for (const part of live) {
      const next = doc.getElementById(part.id);
      if (!next) continue;
      patch(part, next, inpacePristine.get(part.id));
      inpacePristine.set(part.id, next.cloneNode(true));
    }
  };

  let running = false, last = Date.now();
  const refresh = async () => {
    // Pages marked [data-live-buttons] only update after their buttons, not on their own.
    const live = [...document.querySelectorAll("[data-live][id]:not([data-live-buttons])")];
    if (!live.length || running || document.hidden) return;
    if (document.querySelector("dialog[open], [data-offline-job]:not([hidden])")) return;  // don't change what's being used
    const el = document.activeElement;
    if (el && /INPUT|TEXTAREA|SELECT/.test(el.tagName)) return;  // typing
    running = true;
    try {
      const r = await fetch(location.pathname + location.search, { cache: "no-store", headers: { "X-InPace-Soft": "1" } });
      if (!r.ok || new URL(r.url).pathname !== location.pathname) return;
      apply(new DOMParser().parseFromString(await r.text(), "text/html"));
      last = Date.now();
    } catch (e) {
      if (e instanceof NeedsReload) location.reload();  // a part that needs its script changed: load the page again
    } finally {
      running = false;
    }
  };
  window.inpaceRefresh = refresh;

  // Buttons update in place (v1.30.12). A button in a live part of the page (turn a reminder off, mark something,
  // save a setting) is sent in the background. If Python's answer is this same page, only the parts that changed
  // are updated: no reload, no flash, you stay where you are, and its message shows as a small notice. Anything
  // else (another page, a part with a script that would have to be redrawn, an error) loads the page as before.
  const strip = (u) => { const x = new URL(u, location.href); ["ok", "err", "yay"].forEach((k) => x.searchParams.delete(k)); return x; };
  const notice = (doc) => {
    const ok = doc.querySelector("main .page > .note.ok"), bad = doc.querySelector("main .page > .note.bad");
    if (ok && window.inpaceToast) inpaceToast(ok.textContent.trim());
    if (bad && window.inpaceToast) { inpaceToast(bad.textContent.trim()); const t = document.querySelector(".mini-toast:last-of-type"); t && t.classList.add("bad"); }
    const page = document.querySelector("main .page");
    for (const y of doc.querySelectorAll("main .page > .yay")) {
      const el = document.importNode(y, true);
      page.appendChild(el);
      setTimeout(() => closeYay(el), 7000);  // its × works through the page-wide helper
      if (el.hasAttribute("data-confetti") && typeof burstConfetti === "function") burstConfetti();
    }
  };
  // A form sent its own way says "go to this page": if it's this page, update it in place. Says if it did.
  window.inpaceSoftGo = async (url, before) => {
    const to = strip(url), here = strip(location.href);
    if (running || to.pathname !== here.pathname || to.search !== here.search) return false;
    if (!document.querySelector("[data-live][id]")) return false;  // a #section is ignored: you're already there
    running = true;
    try {
      const r = await fetch(new URL(url, location.href).href, { cache: "no-store", headers: { "X-InPace-Soft": "1" } });
      if (!r.ok || strip(r.url).pathname !== here.pathname) return false;
      const doc = new DOMParser().parseFromString(await r.text(), "text/html");
      if (before) before();
      apply(doc);
      if (location.href !== to.href) history.replaceState(history.state, "", to.href);
      notice(doc);
      last = Date.now();
      return true;
    } catch (e) {
      return false;
    } finally {
      running = false;
    }
  };
  addEventListener("submit", async (e) => {  // on window: after every form's own handler has had its say
    const f = e.target;
    if (e.defaultPrevented || !(f instanceof HTMLFormElement) || running) return;
    if ((f.getAttribute("method") || "get").toLowerCase() !== "post" || f.target || f.hasAttribute("data-nav-form")) return;
    if (!f.closest("[data-live][id]") || f.querySelector("input[type=file], [data-busy]") || f.enctype === "text/plain") return;
    const action = new URL(f.getAttribute("action") || location.href, location.href);
    if (action.origin !== location.origin) return;
    e.preventDefault();
    if (window.inpaceIdle) inpaceIdle();
    const body = new FormData(f);
    if (e.submitter && e.submitter.name) body.append(e.submitter.name, e.submitter.value);
    const btns = [...f.querySelectorAll("button, [type=submit]")];
    btns.forEach((b) => { b.disabled = true; });
    running = true;
    let r = null;
    try {
      r = await fetch(action.href, { method: "POST", body, headers: { "X-InPace-Soft": "1" } });
    } catch (err) {
      running = false;
      btns.forEach((b) => { b.disabled = false; });
      if (window.inpaceToast) inpaceToast(document.documentElement.lang === "ar" ? "تعذّر الإرسال. حاول مرة أخرى." : "Couldn't send it. Try again.");
      return;
    }
    try {
      const type = r.headers.get("content-type") || "";
      const to = strip(r.url), here = strip(location.href);
      if (!r.ok || !type.includes("text/html")) {  // an error page, or a file: show it as the browser would
        if (type.includes("text/html")) { const html = await r.text(); document.open(); document.write(html); document.close(); }
        else location.assign(r.url);
        return;
      }
      if (to.pathname !== here.pathname || to.search !== here.search) { location.assign(r.url); return; }
      const doc = new DOMParser().parseFromString(await r.text(), "text/html");
      btns.forEach((b) => { b.disabled = false; });  // back as Python drew them, so the page compares clean
      try {
        apply(doc);
      } catch (err) {
        location.replace(r.url);  // the change is saved; this only shows it
        return;
      }
      if (f.isConnected) f.reset();
      if (location.href !== to.href) history.replaceState(history.state, "", to.href);
      notice(doc);
      last = Date.now();
    } finally {
      running = false;
    }
  });
  // Coming back to the app or the window after a while: bring the page up to date, quietly.
  const back = () => { if (Date.now() - last > 20000) refresh(); };
  document.addEventListener("visibilitychange", () => { if (!document.hidden) back(); });
  window.addEventListener("focus", back);
})();

// ---- Make a roadmap (v1.24) ------------------------------------------------------------------------------------
// The path is a list you put in order: add courses from the list below, move them up and down, add a note and
// mark a course optional. It's sent as one hidden field (steps). Without JavaScript the ticked courses are used.
(() => {
  const form = document.querySelector("[data-rm-maker]");
  if (!form) return;
  const L = form.dataset;
  const list = form.querySelector("[data-rm-steps]");
  const empty = form.querySelector("[data-rm-empty]");
  const count = form.querySelector("[data-rm-count]");
  const field = form.querySelector("[data-rm-json]");
  const pick = form.querySelector("[data-rm-pick]");
  const find = form.querySelector("[data-rm-find]");
  const none = form.querySelector("[data-rm-none]");
  const items = pick ? [...pick.querySelectorAll("li[data-id]")] : [];
  form.classList.add("js");
  const icon = (d) => `<svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${d}</svg>`;
  const UP = icon('<path d="m6 15 6-6 6 6"/>'), DOWN = icon('<path d="m6 9 6 6 6-6"/>'), X = icon('<path d="M6 6l12 12M18 6 6 18"/>');

  const row = (course, title, note, optional) => {
    const li = document.createElement("li");
    li.className = "rm-edit-step";
    li.dataset.course = course;
    li.innerHTML = `<span class="rm-edit-num"></span>
      <div class="rm-edit-main"><b dir="auto"></b>
        <input class="rm-edit-note" dir="auto" maxlength="400">
        <label class="check small"><input type="checkbox" class="rm-edit-opt"> <span></span></label></div>
      <span class="rm-edit-tools">
        <button type="button" class="btn icon-btn small" data-up>${UP}</button>
        <button type="button" class="btn icon-btn small" data-down>${DOWN}</button>
        <button type="button" class="btn icon-btn small" data-x>${X}</button></span>`;
    li.querySelector("b").textContent = title;
    const n = li.querySelector(".rm-edit-note");
    n.value = note || ""; n.placeholder = L.lNote; n.setAttribute("aria-label", L.lNote);
    li.querySelector(".rm-edit-opt").checked = !!optional;
    li.querySelector(".check span").textContent = L.lOptional;
    li.querySelector("[data-up]").setAttribute("aria-label", L.lUp);
    li.querySelector("[data-down]").setAttribute("aria-label", L.lDown);
    li.querySelector("[data-x]").setAttribute("aria-label", L.lRemove);
    return li;
  };
  // the path as the server drew it becomes editable rows
  [...list.children].forEach((li) => {
    list.replaceChild(row(li.dataset.course, li.dataset.title, li.dataset.note, li.dataset.optional === "1"), li);
  });

  const ids = () => [...list.children].map((li) => li.dataset.course);
  const sync = () => {
    const have = ids();
    [...list.children].forEach((li, i) => {
      li.querySelector(".rm-edit-num").textContent = i + 1;
      li.querySelector("[data-up]").disabled = i === 0;
      li.querySelector("[data-down]").disabled = i === have.length - 1;
    });
    empty.hidden = have.length > 0;
    count.textContent = L.lCount.replace("{n}", have.length);
    items.forEach((it) => {
      const b = it.querySelector("[data-rm-add]");
      const on = have.includes(it.dataset.id);
      b.disabled = on; b.textContent = on ? L.lAdded : L.lAdd;
      it.classList.toggle("added", on);
      it.querySelector("input[type=checkbox]").checked = on;
    });
  };
  list.addEventListener("click", (e) => {
    const li = e.target.closest("li");
    if (!li) return;
    if (e.target.closest("[data-up]") && li.previousElementSibling) list.insertBefore(li, li.previousElementSibling);
    else if (e.target.closest("[data-down]") && li.nextElementSibling) list.insertBefore(li.nextElementSibling, li);
    else if (e.target.closest("[data-x]")) li.remove();
    else return;
    sync();
  });
  items.forEach((it) => {
    const b = it.querySelector("[data-rm-add]");
    b.hidden = false;
    b.addEventListener("click", () => {
      if (ids().includes(it.dataset.id)) return;
      const li = row(it.dataset.id, it.dataset.title, "", false);
      list.appendChild(li);
      sync();
      li.scrollIntoView({ block: "nearest", behavior: "smooth" });
    });
  });
  if (find) find.addEventListener("input", () => {
    const words = find.value.toLowerCase().split(/\s+/).filter(Boolean);
    let shown = 0;
    items.forEach((it) => { const ok = words.every((w) => it.dataset.q.includes(w)); it.hidden = !ok; shown += ok; });
    if (none) none.hidden = shown > 0;
  });
  form.addEventListener("submit", () => {
    field.value = JSON.stringify([...list.children].map((li) => ({
      course: li.dataset.course, note: li.querySelector(".rm-edit-note").value.trim(),
      optional: li.querySelector(".rm-edit-opt").checked })));
  });
  sync();
})();


// Voyage charts (v1.24): a long roadmap scrolls sideways on a phone; start with Tempo's boat in view.
document.querySelectorAll(".voyage-scroll").forEach((box) => {
  const boat = box.querySelector(".voyage-boat");
  if (!boat || box.scrollWidth <= box.clientWidth) return;
  const b = boat.getBoundingClientRect(), r = box.getBoundingClientRect();
  const rtl = getComputedStyle(box).direction === "rtl";
  const want = b.left - r.left + box.scrollLeft - box.clientWidth / 3;
  box.scrollLeft = rtl ? -(box.scrollWidth - box.clientWidth - want) : Math.max(0, want);
});

// "A new version is out": shown once, until you press Later (then again in three days, or for a newer one).
(() => {
  const d = document.querySelector("[data-news-dialog]");
  if (!d || !d.showModal) return;
  const later = () => fetch("/updates/later", { method: "POST", headers: { "X-Inpace-Fetch": "1" } }).catch(() => {});
  const form = d.querySelector("[data-news-later]");
  form && form.addEventListener("submit", (e) => { e.preventDefault(); later(); d.close(); });
  d.addEventListener("cancel", later);          // Escape counts as Later
  setTimeout(() => { try { d.showModal(); } catch (_) {} }, 600);
})();

// Forms that end on GitHub (feedback, publishing a course): the button's link carries what you typed, so GitHub
// opens with the form already filled in. Nothing is sent from inPace itself.
document.querySelectorAll("[data-issue-form]").forEach((box) => {
  const link = box.querySelector("[data-issue-link]");
  if (!link) return;
  const sys = box.querySelector("[data-include-system]");
  const build = () => {
    const kind = (box.querySelector('input[name="kind"]:checked') || {}).value || "";
    box.querySelectorAll("[data-only-kind]").forEach((el) => { el.hidden = el.dataset.onlyKind !== kind; });
    const q = new URLSearchParams({ template: box.dataset.template });
    box.querySelectorAll("[data-param]").forEach((el) => {
      if (el.type === "radio" && !el.checked) return;
      if (el.closest("[hidden]")) return;
      if (el.hasAttribute("data-system") && sys && !sys.checked) return;
      let v = (el.value || "").trim();
      if (!v) return;
      if (el.dataset.param === "title" && box.dataset.template === "feedback.yml") v = (kind ? kind + ": " : "") + v;
      q.set(el.dataset.param, v.slice(0, 3000));
    });
    link.href = box.dataset.base + "?" + q.toString().replace(/\+/g, "%20");
  };
  box.addEventListener("input", build);
  box.addEventListener("change", build);
  build();
});

// ---- The floating focus timer (v1.30) ------------------------------------------------------------------
// The server keeps the timer (so it carries on across pages and windows); this counts it down on screen,
// pauses and stops it, lets you drag it anywhere (the spot is remembered), and chimes when time is up.
// It runs on its own: only you pause or stop it (and, if you ticked it, it grows a plant on Tempo's island).
(() => {
  const box = document.querySelector("[data-ftimer]");
  const sheet = document.querySelector("[data-timer-sheet]");
  const openBtn = document.querySelector("[data-timer-open]");
  if (!box) return;
  let d = {};
  try { d = JSON.parse((document.getElementById("timer-data") || {}).textContent || "{}") || {}; } catch (e) { d = {}; }
  let t0 = Date.now();
  const L = (k) => box.dataset["l" + k[0].toUpperCase() + k.slice(1)] || "";
  const fmt = (s) => { s = Math.max(0, Math.ceil(s)); const h = Math.floor(s / 3600), m = Math.floor((s % 3600) / 60), x = s % 60;
    return (h ? h + ":" + String(m).padStart(2, "0") : String(m).padStart(2, "0")) + ":" + String(x).padStart(2, "0"); };
  const left = () => (d.state === "running" ? d.left - (Date.now() - t0) / 1000 : d.left);
  const chime = () => {
    try {
      const a = new (window.AudioContext || window.webkitAudioContext)();
      [523.25, 659.25, 783.99, 1046.5].forEach((f, i) => {
        const o = a.createOscillator(), g = a.createGain();
        o.type = "sine"; o.frequency.value = f; o.connect(g); g.connect(a.destination);
        const t = a.currentTime + i * 0.16;
        g.gain.setValueAtTime(0.0001, t); g.gain.exponentialRampToValueAtTime(0.2, t + 0.02); g.gain.exponentialRampToValueAtTime(0.0001, t + 0.6);
        o.start(t); o.stop(t + 0.65);
      });
    } catch (e) { /* no sound here */ }
  };
  const say = (text) => {
    const y = document.createElement("div");
    y.className = "yay"; y.setAttribute("role", "status");
    y.innerHTML = '<p></p><button type="button" class="yay-close" aria-label="×">×</button>';
    y.querySelector("p").textContent = text;
    y.querySelector("button").addEventListener("click", () => y.remove());
    document.body.appendChild(y);
    setTimeout(() => y.remove(), 12000);
  };
  const finished = () => {
    chime();
    say(L("done") + " " + L("doneBody").replace("{n}", Math.round((d.goal || 0) / 60) || ""));
  };
  const draw = () => {
    const on = !!d.on;
    box.hidden = !on;
    if (openBtn) openBtn.classList.toggle("on", on);
    if (!on) return;
    const s = left(), p = d.goal ? Math.min(1, Math.max(0, 1 - s / d.goal)) : 0;
    box.classList.toggle("paused", d.state !== "running");
    box.querySelectorAll("[data-ft-time]").forEach((el) => (el.textContent = fmt(s)));
    box.querySelectorAll("[data-ft-label]").forEach((el) => (el.textContent = d.state !== "running" ? L("paused") : (d.label || "")));
    const bar = box.querySelector("[data-ft-bar]"); if (bar) bar.style.width = (p * 100).toFixed(1) + "%";
    const ring = box.querySelector("[data-ft-ring]"); if (ring) ring.style.strokeDasharray = ((1 - p) * 289).toFixed(1) + " 289";
    box.classList.toggle("trip", d.kind === "trip");
    const label = d.state === "running" ? L("pause") : L("resume");
    box.querySelectorAll("[data-ft-toggle]").forEach((b) => { b.setAttribute("aria-label", label); b.title = label; });
    if (d.state === "running" && s <= 0 && !draw.ending) { draw.ending = true; refresh(true); }
  };
  const take = (nd, chimeIfDone) => {
    const wasOn = d.on;
    d = nd || { on: false }; t0 = Date.now(); draw.ending = false;
    if (!d.on && d.done && (wasOn || chimeIfDone)) finished();
    draw();
    window.dispatchEvent(new CustomEvent("inpace-timer", { detail: d }));
  };
  const send = async (what, extra) => {
    const body = new URLSearchParams(extra || {});
    try {
      const r = await fetch("/timer/" + what, { method: "POST", body, headers: { "x-inpace-fetch": "1", "accept": "application/json" } });
      take(await r.json(), false);
    } catch (e) { /* offline for a moment: the next look fixes it */ }
  };
  const refresh = async (chimeIfDone) => {
    try { take(await (await fetch("/timer.json", { cache: "no-store" })).json(), chimeIfDone); } catch (e) { /* later */ }
  };
  // Pause / go on, +5 min and Stop: the same three buttons in all three looks.
  box.querySelectorAll("[data-ft-toggle]").forEach((b) => b.addEventListener("click", () => send(d.state === "running" ? "pause" : "resume")));
  box.querySelectorAll("[data-ft-plus]").forEach((b) => b.addEventListener("click", () => send("add")));
  box.querySelectorAll("[data-ft-stop]").forEach((b) => b.addEventListener("click", () => send("stop")));
  window.inpaceTimer = {
    get: () => d,
    pause: () => (d.on && d.state === "running" ? send("pause") : null),
    resume: () => (d.on && d.state !== "running" ? send("resume") : null),
    refresh,
  };
  // The header button: start a timer, or bring the running one back into view.
  if (openBtn && sheet) openBtn.addEventListener("click", () => {
    if (d.on) { box.animate([{ transform: "scale(1)" }, { transform: "scale(1.08)" }, { transform: "scale(1)" }], { duration: 350 }); return; }
    sheet.showModal ? sheet.showModal() : sheet.setAttribute("open", "");
  });
  if (sheet) {
    sheet.querySelector("[data-timer-close]").addEventListener("click", () => sheet.close());
    sheet.addEventListener("click", (e) => { if (e.target === sheet) sheet.close(); });
    sheet.querySelector("[data-timer-form]").addEventListener("submit", async (e) => {
      e.preventDefault();
      await send("start", Object.fromEntries(new FormData(e.target)));
      sheet.close();
    });
  }
  // Drag it anywhere; the spot is kept for next time (separately for phone-size and computer-size windows).
  const spotKey = () => "inpace-timer-spot-" + (innerWidth < 860 ? "s" : "l");
  const place = (x, y) => {
    const r = box.getBoundingClientRect();
    x = Math.min(Math.max(8, x), innerWidth - r.width - 8); y = Math.min(Math.max(8, y), innerHeight - r.height - 8);
    Object.assign(box.style, { left: x + "px", top: y + "px", right: "auto", bottom: "auto" });
  };
  const phone = () => innerWidth < 860;  // there it's a bar under the header: nothing to move or resize
  try { const s = JSON.parse(localStorage.getItem(spotKey()) || "null"); if (s && !phone()) requestAnimationFrame(() => place(s.x, s.y)); } catch (e) { /* none */ }
  // Resize: drag the corner handle; the size (70% to 180%) is kept for next time.
  const setScale = (k) => { k = Math.min(1.8, Math.max(0.7, k)); box.style.setProperty("--ft-scale", k.toFixed(2)); return k; };
  try { setScale(parseFloat(localStorage.getItem("inpace-timer-scale") || "1") || 1); } catch (e) { /* none */ }
  const sizer = box.querySelector("[data-ft-size]");
  if (sizer) sizer.addEventListener("pointerdown", (e) => {
    e.preventDefault(); e.stopPropagation();
    const r = box.getBoundingClientRect(), k0 = parseFloat(getComputedStyle(box).getPropertyValue("--ft-scale")) || 1;
    const w0 = r.width / k0, rtl = document.dir === "rtl";
    const mv = (ev) => { const w = rtl ? r.right - ev.clientX : ev.clientX - r.left; setScale(w / w0); };
    const up = () => {
      removeEventListener("pointermove", mv); removeEventListener("pointerup", up);
      try { localStorage.setItem("inpace-timer-scale", getComputedStyle(box).getPropertyValue("--ft-scale").trim()); } catch (e2) { /* private */ }
      const r2 = box.getBoundingClientRect(); place(r2.left, r2.top);
    };
    addEventListener("pointermove", mv); addEventListener("pointerup", up);
  });
  // Keyboard: the size handle grows and shrinks with the arrow keys too.
  if (sizer) sizer.addEventListener("keydown", (e) => {
    const k = parseFloat(getComputedStyle(box).getPropertyValue("--ft-scale")) || 1;
    if (e.key === "ArrowUp" || e.key === "ArrowRight") { e.preventDefault(); setScale(k + 0.1); }
    else if (e.key === "ArrowDown" || e.key === "ArrowLeft") { e.preventDefault(); setScale(k - 0.1); }
    else return;
    try { localStorage.setItem("inpace-timer-scale", getComputedStyle(box).getPropertyValue("--ft-scale").trim()); } catch (e2) { /* private */ }
  });
  box.addEventListener("pointerdown", (e) => {
    if (!e.target.closest("[data-ft-grip]") || phone()) return;
    const r = box.getBoundingClientRect(), dx = e.clientX - r.left, dy = e.clientY - r.top, sx = e.clientX, sy = e.clientY;
    let dragging = false;
    const mv = (ev) => {
      if (!dragging && Math.hypot(ev.clientX - sx, ev.clientY - sy) < 6) return;
      dragging = true; box.classList.add("dragging");
      place(ev.clientX - dx, ev.clientY - dy);
    };
    const up = () => {
      removeEventListener("pointermove", mv); removeEventListener("pointerup", up);
      box.classList.remove("dragging");
      if (dragging) {
        const r2 = box.getBoundingClientRect();
        try { localStorage.setItem(spotKey(), JSON.stringify({ x: r2.left, y: r2.top })); } catch (e2) { /* private window */ }
      }
    };
    addEventListener("pointermove", mv); addEventListener("pointerup", up);
  });
  addEventListener("resize", () => {
    if (phone()) { Object.assign(box.style, { left: "", top: "", right: "", bottom: "" }); return; }
    if (box.style.left) { const r = box.getBoundingClientRect(); place(r.left, r.top); }
  });
  if (!d.on && d.done) finished();  // it ended while this page was loading
  setInterval(draw, 1000);
  setInterval(() => { if (!document.hidden) refresh(true); }, 30000);  // another window may have paused or stopped it
  document.addEventListener("visibilitychange", () => { if (!document.hidden) refresh(true); });
  draw();
})();


// ---- The pop-out mini window (v1.30) ---------------------------------------------------------------------------
// A small inPace window above your other apps, with just the lesson's video. The app window makes it
// (Windows, Mac, Linux); in a browser, Chrome and Edge's "picture-in-picture window" holds it, else a popup.
// The windows talk over a BroadcastChannel: "Back to inPace" in the small window brings the video back here.
(() => {
  const chan = "BroadcastChannel" in window ? new BroadcastChannel("inpace-mini") : null;
  if (document.body && document.body.hasAttribute("data-mini-window")) return;  // the small window itself: below
  window.inpacePopout = async (n) => {
    const key = n.box.dataset.key || "";
    const lesson = n.lesson || location.pathname;
    const url = lesson + "?mini=1&key=" + encodeURIComponent(key);
    n.v.pause();  // saves the second it's at, so the small window starts there
    await new Promise((r) => setTimeout(r, 350));
    let ok = false;
    try {
      const body = new URLSearchParams({ url });
      ok = (await (await fetch("/window/popout", { method: "POST", body })).json()).ok;
    } catch (e) { ok = false; }
    if (!ok && window.documentPictureInPicture) {
      try {
        const pip = await documentPictureInPicture.requestWindow({ width: 440, height: 360 });
        pip.document.body.style.margin = "0";
        const f = pip.document.createElement("iframe");
        f.src = url; f.allow = "autoplay; fullscreen";
        Object.assign(f.style, { border: "0", width: "100vw", height: "100vh", display: "block" });
        pip.document.body.appendChild(f);
        ok = true;
      } catch (e) { ok = false; }
    }
    if (!ok) ok = !!window.open(url, "inpace-mini", "popup,width=440,height=360");
    if (ok && window.inpaceMini && inpaceMini.active()) inpaceMini.stop();
  };
  // "Back to inPace" in the small window: carry on here, from the same second.
  if (chan) chan.addEventListener("message", (e) => {
    const m = e.data || {};
    if (m.type !== "back" || !m.lesson) return;
    if (location.pathname === m.lesson) {
      if (window.inpaceMini && inpaceMini.active()) inpaceMini.expand();
      const box = [...document.querySelectorAll("[data-player]")].find((b) => b.dataset.key === m.key);
      const v = box && box.querySelector("video");
      if (v) { if (m.t) v.currentTime = m.t; v.play().catch(() => {}); }
      else location.reload();
    } else location.href = m.lesson;
  });
})();

// The small window: keep only the video it was opened for, start it, and wire Back and Close.
(() => {
  if (!document.body || !document.body.hasAttribute("data-mini-window")) return;
  const chan = "BroadcastChannel" in window ? new BroadcastChannel("inpace-mini") : null;
  const lesson = document.body.dataset.lesson;
  const key = new URLSearchParams(location.search).get("key") || "";
  const prose = document.querySelector(".mw-video");
  const figs = [...prose.querySelectorAll("figure")];
  const sel = key ? `[data-key="${CSS.escape(key)}"], [data-yt-key="${CSS.escape(key)}"]` : "";
  const keep = (sel && figs.find((f) => f.querySelector(sel))) || figs.find((f) => f.querySelector("video, [data-embed], [data-player]"));
  prose.replaceChildren(...(keep ? [keep] : []));
  const media = () => { const n = window.inpaceNowPlaying; if (n) return n.v; const v = prose.querySelector("video"); return v; };
  setTimeout(() => {
    const v = prose.querySelector("video");
    if (v) v.play().catch(() => {});
    else { const b = prose.querySelector(".yt-choice.play, .embed-box .play"); if (b) b.click(); }
  }, 450);
  const shut = async () => {
    try { await fetch("/window/popout/close", { method: "POST" }); } catch (e) { /* no app window */ }
    try { window.close(); } catch (e) { /* not allowed */ }
  };
  document.querySelector("[data-mw-back]").addEventListener("click", async () => {
    const v = media();
    const t = v ? v.currentTime : 0;
    if (v) v.pause();
    await new Promise((r) => setTimeout(r, 250));  // let the second it's at be saved
    if (chan) chan.postMessage({ type: "back", lesson, key, t });
    if (window.parent !== window) { try { parent.close(); } catch (e) { /* the browser's PiP window closes itself */ } }
    shut();
  });
  document.querySelector("[data-mw-close]").addEventListener("click", () => { const v = media(); if (v) v.pause(); shut(); });
})();

// ---- Videos: the rules (v1.30.11) ------------------------------------------------------------------------------
// Every video feature (the mini player, Android's floating window, the system's media controls, the pop-out
// window) follows these rules, so they can't disagree about which video is "the" video:
//   1. One video at a time. Starting a video pauses whichever one was playing.
//   2. Videos only play in the main page. The mini player's frame (the page you opened while a lesson video
//      played) never plays one: pressing play there stops the mini player's video, opens that page as the main
//      page, and starts its video there.
//   3. window.inpaceNowPlaying (in the main page) is the one video. The mini player, the floating window and
//      the media controls all read it, and nothing else.
//   4. The mini player never covers anything: it hides while a menu, sheet or dialog is open, and closes when
//      its video stops for another one.
// ---- The mini player (v1.30) ---------------------------------------------------------------------------------
// Leave a lesson while its video plays, and the video shrinks into a corner and keeps playing, like YouTube.
// How: the lesson page stays loaded underneath; the page you went to opens in a full-window frame on top of
// it, and the video sits above that frame. Every page works as always inside the frame. "Back to the lesson"
// (or Back from the first page you opened) removes the frame: the lesson is right there, at the same second.
(() => {
  const html = document.documentElement;
  if (window.parent !== window) {
    // Inside the frame: a link to the lesson that's playing brings it back instead of loading it again.
    document.addEventListener("click", (e) => {
      const a = e.target.closest("a[href]");
      try { if (a && parent.inpaceMini && parent.inpaceMini.isLesson(a.href)) { e.preventDefault(); e.stopImmediatePropagation(); parent.inpaceMini.expand(); } } catch (x) { /* not ours */ }
    }, true);
    html.classList.add("in-mini-host");
    const mini = () => { try { return parent.inpaceMini || null; } catch (x) { return null; } };
    // Rule 2 (see "Videos: the rules"): no video plays in this frame. Pressing play here opens this page as the
    // main page and starts the video there, so there's never a second video hidden behind the mini player.
    const START = ".yt-cover, .yt-choice, .embed-box .play, .pl-big, .pl-play, [data-player] video";
    document.addEventListener("click", (e) => {
      const hit = e.target.closest(START), m = mini();
      if (!hit || !m || !m.promote) return;
      const figs = [...document.querySelectorAll("figure.media")], fig = hit.closest("figure.media");
      e.preventDefault(); e.stopImmediatePropagation();
      m.promote(location.href, fig ? figs.indexOf(fig) : -1, hit.matches("[data-yt-noads]") ? "noads" : "");
    }, true);
    window.inpaceFramePlay = (box) => {  // a video started here anyway (keyboard, a script): same rule 2
      const m = mini();
      if (!m || !m.promote) return false;
      const figs = [...document.querySelectorAll("figure.media")], fig = box.closest("figure.media");
      m.promote(location.href, fig ? figs.indexOf(fig) : -1, "");
      return true;
    };
    // A menu, sheet or dialog open on this page (More, search, a course's menu, the tour): the mini player
    // hides so it never covers it, and comes back when it closes.
    const open = () => !!document.querySelector("dialog[open], details.menu[open], .search-pop, .tour-shade, .iv[style*=flex], .diagram-box.is-full");
    let was = false;
    const check = () => { const now = open(); if (now !== was) { was = now; const m = mini(); m && m.under(now); } };
    new MutationObserver(check).observe(document.documentElement, { subtree: true, childList: true, attributes: true, attributeFilter: ["open", "class", "style"] });
    addEventListener("pagehide", () => { const m = mini(); m && m.under(false); });
    return;
  }
  let host = null, cur = null;
  const playing = () => { const n = window.inpaceNowPlaying; return n && !n.v.paused && !n.v.ended ? n : null; };
  const figOf = (n) => n.box.closest("figure") || n.box;
  const corner = () => { try { return localStorage.getItem("inpace-mini-corner") || "br"; } catch (e) { return "br"; } };
  const bar = (f, n) => {
    let b = f.querySelector(":scope > .mini-bar");
    if (b) return b;
    const L = n.box.dataset;
    const title = (document.querySelector("article h1") || {}).textContent || document.title;
    b = document.createElement("div");
    b.className = "mini-bar";
    b.innerHTML = `<span class="mini-title" data-mini-grip title="${L.lMinidrag || ""}"><b></b></span>
      <button type="button" class="mini-ic mini-toggle" data-mini-toggle aria-label="${L.lPause}" title="${L.lPause}"><svg viewBox="0 0 24 24" width="18" height="18"><path class="i-pause" d="M6 4h4.5v16H6zM13.5 4H18v16h-4.5z" fill="currentColor"/><path class="i-play" d="M7 4.5v15l13-7.5z" fill="currentColor"/></svg></button>
      <button type="button" class="mini-ic" data-mini-back aria-label="${L.lMiniback}" title="${L.lMiniback}"><svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2.4"><path d="M4 14v6h6M20 10V4h-6M4 20l7-7M20 4l-7 7"/></svg></button>
      ${window.inpacePopout ? `<button type="button" class="mini-ic" data-mini-out aria-label="${L.lMiniout}" title="${L.lMiniout}"><svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2.2"><rect x="3" y="5" width="18" height="14"/><rect x="12" y="12" width="7" height="5" fill="currentColor"/></svg></button>` : ""}
      <button type="button" class="mini-ic" data-mini-close aria-label="${L.lMiniclose}" title="${L.lMiniclose}"><svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="2.6"><path d="M6 6l12 12M18 6L6 18"/></svg></button>`;
    b.querySelector("b").textContent = title.trim();
    const sync = () => b.classList.toggle("paused", n.v.paused);
    n.v.addEventListener("play", sync); n.v.addEventListener("pause", sync); sync();
    b.querySelector("[data-mini-toggle]").addEventListener("click", () => (n.v.paused ? n.v.play() : n.v.pause()));
    b.querySelector("[data-mini-back]").addEventListener("click", () => api.expand());
    b.querySelector("[data-mini-close]").addEventListener("click", () => api.close());
    const out = b.querySelector("[data-mini-out]");
    if (out) out.addEventListener("click", () => window.inpacePopout(n));
    // Drag it; let go and it moves to the nearest corner (remembered).
    // Tap the title to go back to the lesson; drag it to move the video (it settles in the nearest corner).
    b.querySelector("[data-mini-grip]").addEventListener("pointerdown", (e) => {
      if (innerWidth < 860) return;
      const r = f.getBoundingClientRect(), dx = e.clientX - r.left, dy = e.clientY - r.top, sx = e.clientX, sy = e.clientY;
      let moved = false;
      const mv = (ev) => {
        if (!moved && Math.hypot(ev.clientX - sx, ev.clientY - sy) < 6) return;
        moved = true; f.classList.add("mini-drag");
        Object.assign(f.style, { left: ev.clientX - dx + "px", top: ev.clientY - dy + "px", right: "auto", bottom: "auto" });
      };
      const up = (ev) => {
        removeEventListener("pointermove", mv); removeEventListener("pointerup", up);
        if (!moved) { api.expand(); return; }
        f.classList.remove("mini-drag");
        const c = (ev.clientY < innerHeight / 2 ? "t" : "b") + (ev.clientX < innerWidth / 2 ? "l" : "r");
        try { localStorage.setItem("inpace-mini-corner", c); } catch (x) { /* private */ }
        Object.assign(f.style, { left: "", top: "", right: "", bottom: "" });
        f.dataset.corner = c;
      };
      addEventListener("pointermove", mv); addEventListener("pointerup", up);
    });
    b.querySelector("[data-mini-grip]").addEventListener("click", () => { if (innerWidth < 860) api.expand(); });
    f.appendChild(b);
    return b;
  };
  const lessonPath = location.pathname;
  const api = window.inpaceMini = {
    isLesson: (href) => { try { const u = new URL(href, location.href); return u.origin === location.origin && u.pathname === lessonPath; } catch (e) { return false; } },
    active: () => !!host,
    enter(url) {
      cur = playing();
      if (!cur) return false;
      const f = figOf(cur);
      bar(f, cur);
      f.dataset.corner = corner();
      f.classList.add("mini-player");
      f.classList.remove("mini-gone");
      html.classList.add("mini-on");
      history.pushState({ inpaceMini: 1 }, "", location.href);
      host = document.createElement("iframe");
      host.className = "mini-host";
      host.title = document.title;
      host.src = url;
      host.addEventListener("load", () => { try { document.title = host.contentDocument.title; } catch (e) { /* elsewhere */ } });
      document.body.appendChild(host);
      return true;
    },
    expand() {
      if (!host) return;
      host.remove(); host = null;
      html.classList.remove("mini-on", "mini-under");
      document.querySelectorAll(".mini-player").forEach((f) => f.classList.remove("mini-player", "mini-gone"));
      document.title = document.title;  // the frame's title went with it
      if (history.state && history.state.inpaceMini) history.replaceState(null, "", location.href);
    },
    stop() {  // another video started in the frame: this one stops and its mini player goes away
      if (cur) { cur.v.pause(); figOf(cur).classList.add("mini-gone"); }
    },
    under(on) { html.classList.toggle("mini-under", !!on); },  // the frame has a menu or sheet open
    promote(url, fig, choice) {  // play was pressed on a video in the frame: that page becomes the main page
      if (cur) cur.v.pause();
      if (window.inpaceNowPlaying) { try { window.inpaceNowPlaying.v.pause(); } catch (e) { /* gone */ } }
      try { sessionStorage.setItem("inpace-autoplay", JSON.stringify({ url, fig, choice, at: Date.now() })); } catch (e) { /* private */ }
      location.href = url;
    },
    close() {  // stop the video and stay on the page you're on now
      if (cur) cur.v.pause();
      let to = null;
      try { to = host && host.contentWindow.location.href; } catch (e) { to = null; }
      if (to) location.href = to; else api.expand();
    },
  };
  // Back from the first page in the frame comes back here: show the lesson again.
  addEventListener("popstate", (e) => { if (host && !(e.state && e.state.inpaceMini)) api.expand(); });
  // Going to another inPace page while the video plays: open it above the lesson instead of leaving it.
  document.addEventListener("click", (e) => {
    if (e.defaultPrevented || e.button !== 0 || e.ctrlKey || e.metaKey || e.shiftKey || e.altKey || host) return;
    const a = e.target.closest("a[href]");
    if (!a || a.target === "_blank" || a.hasAttribute("download") || !playing()) return;
    let u;
    try { u = new URL(a.href, location.href); } catch (x) { return; }
    if (u.origin !== location.origin || (u.pathname === location.pathname && u.search === location.search)) return;
    if (/^\/(files|media|yt-stream|pdf|outbox|static)\//.test(u.pathname)) return;  // files open as before
    if (api.enter(u.href)) { e.preventDefault(); e.stopImmediatePropagation(); }
  }, true);
  // Arriving from the frame after pressing play there: start that video here.
  let want = null;
  try { want = JSON.parse(sessionStorage.getItem("inpace-autoplay") || "null"); sessionStorage.removeItem("inpace-autoplay"); } catch (e) { want = null; }
  if (want && Date.now() - want.at < 20000 && new URL(want.url, location.href).pathname === location.pathname) {
    const start = () => {
      const figs = [...document.querySelectorAll("figure.media")];
      const fig = figs[want.fig] || figs[0];
      if (!fig) return;
      fig.scrollIntoView({ block: "center" });
      const b = (want.choice === "noads" && fig.querySelector(".yt-choice[data-yt-noads]"))
        || fig.querySelector(".yt-choice.play, .embed-box .play, .pl-big");
      if (b) b.click();
      else { const v = fig.querySelector("video"); if (v) v.play().catch(() => {}); }
    };
    if (document.readyState === "complete") setTimeout(start, 50); else addEventListener("load", () => setTimeout(start, 50), { once: true });
  }
})();


// ---- The system's media controls (v1.30) ----------------------------------------------------------------------
// While a lesson video plays, the computer's media controls (the media center on Windows and Linux, Control
// Center on Mac, media keys on the keyboard) show the lesson's name and course, with play/pause, 10 seconds back
// and forward, and previous/next lesson.
window.inpaceMediaInfo = (box) => {
  const lesson = ((document.querySelector("article h1") || document.querySelector(".mw-brand b") || {}).textContent || document.title).trim();
  const course = ((document.querySelector(".eyebrow a[data-up]") || {}).textContent || "inPace").trim();
  const yt = box.dataset.ytId || "";
  // The picture: the course's own cover, else the YouTube video's picture, else inPace's icon.
  const cover = (document.querySelector("[data-cover]") || { dataset: {} }).dataset.cover || "";
  const art = cover ? new URL(cover, location.href).href
    : yt ? `https://i.ytimg.com/vi/${encodeURIComponent(yt)}/hqdefault.jpg` : location.origin + "/static/icon-256.png";
  return { lesson, course, art };
};
// The buttons in the system's media controls (and Android's notification) land here.
window.inpaceMediaControl = (what) => {
  const n = window.inpaceNowPlaying;
  const v = n && n.v;
  const go = (sel) => { const a = document.querySelector(sel); if (a) location.href = a.href; };
  if (what === "next") return go("[data-key-next]");
  if (what === "prev") return go("[data-key-prev]");
  if (!v) return;
  if (what === "play") v.play();
  else if (what === "pause") v.pause();
  else if (what === "back") v.currentTime = Math.max(0, v.currentTime - 10);
  else if (what === "fwd") v.currentTime = Math.min(v.duration || 1e9, v.currentTime + 10);
  else if (String(what).startsWith("seek:")) v.currentTime = (parseFloat(String(what).slice(5)) || 0) / 1000;
};
window.inpaceMediaSession = (box, v) => {
  const ms = navigator.mediaSession;
  if (!ms || !window.MediaMetadata) return;
  const { lesson, course } = inpaceMediaInfo(box);
  const yt = box.dataset.ytId || "";
  const art = [{ src: inpaceMediaInfo(box).art, sizes: "512x512" }];
  try { ms.metadata = new MediaMetadata({ title: lesson, artist: course, album: "inPace", artwork: art }); } catch (e) { return; }
  const set = (action, fn) => { try { ms.setActionHandler(action, fn); } catch (e) { /* not on this system */ } };
  const jump = (s) => { v.currentTime = Math.max(0, Math.min((v.duration || 1e9), v.currentTime + s)); };
  set("play", () => v.play());
  set("pause", () => v.pause());
  set("stop", () => v.pause());
  set("seekbackward", (d) => jump(-((d && d.seekOffset) || 10)));
  set("seekforward", (d) => jump((d && d.seekOffset) || 10));
  set("seekto", (d) => { if (d && typeof d.seekTime === "number") v.currentTime = d.seekTime; });
  const go = (sel) => { const a = document.querySelector(sel); return a ? () => { location.href = a.href; } : null; };
  set("previoustrack", go("[data-key-prev]"));
  set("nexttrack", go("[data-key-next]"));
  const state = () => {
    try { ms.playbackState = v.paused ? "paused" : "playing"; } catch (e) { /* older */ }
    try { if (v.duration && isFinite(v.duration)) ms.setPositionState({ duration: v.duration, position: Math.min(v.currentTime, v.duration), playbackRate: v.playbackRate || 1 }); } catch (e) { /* older */ }
  };
  if (!v._msHooked) {
    v._msHooked = true;
    v.addEventListener("play", state); v.addEventListener("pause", state); v.addEventListener("ratechange", state);
    let last = 0;
    v.addEventListener("timeupdate", () => { const n = Date.now(); if (n - last > 4000) { last = n; state(); } });
  }
  state();
};


// ---- Downloads (v1.30.14) --------------------------------------------------------------------------------------
// Every video download in one place, like a download manager: what's downloading (with speed and time left),
// what's waiting, what failed (with why, and Retry), and what finished. While anything downloads:
//  * the Downloads item in the menu shows how many videos are left,
//  * on Android, the app shows a notification with a progress bar (main.dart polls /downloads.json), and keeps
//    downloading when you leave the app,
//  * on a computer, one notification says when everything is done.
(() => {
  const root = document.documentElement;
  const page = document.querySelector("[data-dl]");
  const L = page ? page.dataset : {};
  const esc = (t) => String(t == null ? "" : t).replace(/[&<>"]/g, (c) => ({ "&": "&amp;", "<": "&lt;", ">": "&gt;", '"': "&quot;" }[c]));
  const size = (n) => (n >= 1073741824 ? (n / 1073741824).toFixed(1) + " GB" : n >= 1048576 ? (n / 1048576).toFixed(n < 10485760 ? 1 : 0) + " MB"
    : Math.max(1, Math.round((n || 0) / 1024)) + " KB");
  const time = (s) => (s >= 3600 ? `${Math.floor(s / 3600)} h ${Math.round((s % 3600) / 60)} min` : s >= 60 ? `${Math.round(s / 60)} min` : `${Math.max(1, Math.round(s))} s`);
  const fill = (t, o) => Object.entries(o).reduce((a, [k, v]) => a.split("{" + k + "}").join(v), t || "");
  let tab = "all";
  try { tab = sessionStorage.getItem("inpace-dl-tab") || "all"; } catch (e) { /* private */ }

  const badges = (o) => {
    const n = o.running ? o.active + o.waiting : 0;
    document.querySelectorAll("[data-dl-link]").forEach((a) => {
      let b = a.querySelector(".badge");
      if (!n) { if (b) b.remove(); return; }
      if (!b) { b = document.createElement("em"); b.className = "badge"; a.appendChild(b); }
      b.textContent = n;
    });
    root.classList.toggle("dl-busy", !!o.running);
  };

  const form = (action, course, video, label, cls) =>
    `<form method="post" action="/downloads/${action}" data-dl-form>${course ? `<input type="hidden" name="course" value="${esc(course)}">` : ""}` +
    `${video ? `<input type="hidden" name="video" value="${esc(video)}">` : ""}<button class="btn small ${cls || ""}">${label}</button></form>`;

  const row = (kind, c, it) => {
    const st = { downloading: L.lDownloading, waiting: L.lWaiting, failed: L.lFailed, done: L.lSaved }[kind];
    let meta = "", bar = "", act = "";
    if (kind === "downloading") {
      const p = it.percent || 0;
      bar = `<div class="bar dl-bar-row"><span style="width:${p}%"></span></div>`;
      const bits = [`${Math.round(p)}%`];
      if (it.size) bits.push(fill(L.lOf, { a: size(it.got || 0), b: size(it.size) }));
      if (it.speed) bits.push(size(it.speed) + "/s");
      if (it.eta) bits.push(fill(L.lLeft, { t: time(it.eta) }));
      meta = bits.join(" · ");
      act = form("cancel", c.course, it.id, L.lCancel);
    } else if (kind === "waiting") {
      meta = "";
      act = it.id ? form("next", c.course, it.id, L.lNext) + form("cancel", c.course, it.id, L.lCancel) : "";
    } else if (kind === "failed") {
      meta = it.why || "";
      act = form("retry", c.course, it.id, L.lRetry, "primary");
    } else {
      meta = it.size ? size(it.size) : "";
    }
    const title = it.id || kind !== "waiting" ? it.title : L.lRest;
    return `<li class="dl-row ${kind}"><span class="dl-state">${esc(st)}</span><div class="grow"><b dir="auto">${esc(title)}</b>${bar}` +
      `<span class="small muted">${esc(meta)}</span></div><div class="row dl-acts">${act}</div></li>`;
  };

  const draw = (o) => {
    if (!page) return;
    const rows = { downloading: [], waiting: [], failed: [], done: [] };
    for (const c of o.courses) {
      c.active.forEach((it) => rows.downloading.push([c, it]));
      c.waiting_list.forEach((it) => rows.waiting.push([c, it]));
      c.failed.forEach((it) => rows.failed.push([c, it]));
      c.completed.slice().reverse().forEach((it) => rows.done.push([c, it]));
    }
    for (const [k, x] of Object.entries(o.packs || {})) {
      if (x.state !== "running" && x.state !== "installing") continue;
      const pct = x.size ? Math.round((100 * x.got) / x.size) : 0;
      rows.downloading.push([{ course: "" }, { id: "", title: x.title + (x.of > 1 ? ` (${x.n}/${x.of})` : ""), percent: pct, got: x.got, size: x.size, pack: true }]);
    }
    const count = (k) => (k === "all" ? rows.downloading.length + rows.waiting.length + rows.failed.length + rows.done.length : rows[k].length);
    page.querySelector("[data-dl-tabs]").innerHTML = ["all", "downloading", "waiting", "failed", "done"].map((k) =>
      `<button type="button" role="tab" class="chip-tab ${k === tab ? "on" : ""}" aria-selected="${k === tab}" data-dl-tab="${k}">` +
      `${esc({ all: L.lAll, downloading: L.lDownloading, waiting: L.lWaiting, failed: L.lFailed, done: L.lDone }[k])} <em>${count(k)}</em></button>`).join("");
    const anyFailed = rows.failed.length, anyDone = o.courses.some((c) => c.state !== "running");
    const paused = o.courses.filter((c) => c.state === "stopped" || c.state === "failed");
    page.querySelector("[data-dl-all]").innerHTML =
      (o.running ? form("stop", "", "", L.lPauseall) : "") +
      (paused.length ? form("resume", "", "", L.lResumeall, "primary") : "") +
      (anyFailed ? form("retry", "", "", L.lRetryall) : "") +
      (anyDone ? form("clear", "", "", L.lClear) : "");
    const kinds = tab === "all" ? ["downloading", "waiting", "failed", "done"] : [tab];
    let html = "";
    const packs = rows.downloading.filter(([, it]) => it.pack);
    if (packs.length && (tab === "all" || tab === "downloading")) {
      html += `<article class="card dl-course running"><h3>${esc(L.lCourses)}</h3><ul class="dl-rows">` +
        packs.map(([c, it]) => row("downloading", c, it).replace(/<div class="row dl-acts">.*?<\/div><\/li>$/, "</li>")).join("") + "</ul></article>";
    }
    for (const c of o.courses) {
      const items = kinds.flatMap((k) => (k === "downloading" ? c.active : k === "waiting" ? c.waiting_list : k === "failed" ? c.failed
        : c.completed.slice().reverse()).map((it) => row(k, c, it)));
      const stateLine = c.state === "running" ? (c.note || fill(L.lVideos, { a: c.done, b: c.total || "…" }))
        : c.state === "stopped" ? L.lPaused : c.state === "failed" ? (c.error || L.lStopped) : fill(L.lVideos, { a: c.done, b: c.total });
      if (!items.length && tab !== "all") continue;
      const ctl = c.state === "running" ? form("stop", c.course, "", L.lPause)
        : (c.state === "stopped" || c.state === "failed") ? form("resume", c.course, "", L.lResume, "primary") : "";
      html += `<article class="card dl-course ${esc(c.state)}"><div class="row between wrap"><div class="grow">` +
        `<h3 dir="auto"><a href="/courses/${encodeURIComponent(c.course)}/go">${esc(c.title)}</a></h3>` +
        `<div class="row"><div class="bar grow"><span style="width:${c.percent}%"></span></div><b class="small">${Math.round(c.percent)}%</b></div>` +
        `<p class="small muted">${esc(stateLine)}</p></div><div class="row wrap">${ctl}${c.failed.length ? form("retry", c.course, "", L.lRetryall) : ""}</div></div>` +
        (items.length ? `<ul class="dl-rows">${items.join("")}</ul>` : "") + `</article>`;
    }
    page.querySelector("[data-dl-list]").innerHTML = html || `<p class="card muted dl-none">${esc(o.courses.length ? L.lEmpty : L.lNone)}</p>`;
    const sum = document.querySelector("[data-dl-summary]");
    if (sum && o.running) sum.textContent = fill(L.lNow, { a: o.active, b: o.waiting }) + (o.speed ? " · " + fill(L.lSpeed, { s: size(o.speed) + "/s" }) : "");
  };

  let timer = null, wasRunning = !!(+root.dataset.dlNow);
  const poll = async () => {
    clearTimeout(timer);
    let o = null;
    try { o = await (await fetch("/downloads.json", { cache: "no-store" })).json(); } catch (e) { /* offline server: try later */ }
    if (o) {
      badges(o);
      draw(o);
      if (o.running && window.InPaceAndroid) { try { InPaceAndroid.postMessage(JSON.stringify({ type: "downloads" })); } catch (e) { /* old app */ } }
      if (wasRunning && !o.running && page) setTimeout(() => location.reload(), 600);  // "On this device" changed
      wasRunning = o.running;
    }
    if (document.hidden && !page) return;
    if (o && (o.running || page)) timer = setTimeout(poll, o.running ? 1000 : 5000);
  };
  window.inpaceDownloadsPoke = () => { wasRunning = true; poll(); };
  if (page) {
    try { const first = JSON.parse(page.querySelector("[data-dl-first]").textContent); badges(first); draw(first); wasRunning = first.running; } catch (e) { /* drawn by the poll */ }
    page.addEventListener("click", (e) => {
      const t = e.target.closest("[data-dl-tab]");
      if (!t) return;
      tab = t.dataset.dlTab;
      try { sessionStorage.setItem("inpace-dl-tab", tab); } catch (x) { /* private */ }
      poll();
    });
  }
  if (page || wasRunning) poll();
  document.addEventListener("visibilitychange", () => { if (!document.hidden && (page || wasRunning)) poll(); });

  // Buttons here are sent in the background, then the list is drawn again: no reload.
  document.addEventListener("submit", async (e) => {
    const f = e.target;
    if (!(f instanceof HTMLFormElement) || !f.hasAttribute("data-dl-form") || e.defaultPrevented) return;
    e.preventDefault();
    const sub = e.submitter;
    const body = new FormData(f);
    if (sub && sub.name) body.append(sub.name, sub.value);
    if (sub && sub.hasAttribute("formaction")) sub.classList.add("is-busy");
    f.querySelectorAll("button").forEach((b) => { b.disabled = true; });
    try {
      const r = await fetch(sub && sub.hasAttribute("formaction") ? sub.formAction : f.action, { method: "POST", body, headers: { "X-InPace-Soft": "1" } });
      if (sub && sub.hasAttribute("formaction")) { location.href = r.url; return; }  // the page changes (yt-dlp is ready)
      const msg = new URL(r.url).searchParams.get("ok") || new URL(r.url).searchParams.get("err");
      if (msg && window.inpaceToast) inpaceToast(msg);
    } catch (x) { /* offline */ }
    f.querySelectorAll("button").forEach((b) => { b.disabled = false; });
    wasRunning = true;
    poll();
  });
  // Deleting files: the first press asks, the second deletes.
  document.addEventListener("submit", (e) => {
    const f = e.target;
    if (!(f instanceof HTMLFormElement) || !f.dataset.confirm || f.dataset.sure) return;
    e.preventDefault();
    e.stopImmediatePropagation();
    const b = f.querySelector("button");
    const was = b.innerHTML;
    f.dataset.sure = "1";
    b.textContent = f.dataset.confirm;
    setTimeout(() => { delete f.dataset.sure; b.innerHTML = was; }, 5000);
  }, true);
})();


// ---- Works with CodeNote (v1.31) ------------------------------------------------------------------------------
// "Practice in CodeNote" sends a lesson (or a practical task) to CodeNote, the free code notebook app. It only shows
// when CodeNote is on this device: on a computer inPace's server checks (and checks again when you come back to
// the window, so installing CodeNote while inPace is open is enough); on Android the app checks. HTML work files
// (CodeNote's "Export for inPace") can be previewed in a sealed frame: no scripts, no internet.
(() => {
  document.addEventListener("toggle", (e) => {
    const d = e.target;
    if (!(d instanceof HTMLDetailsElement) || !d.classList.contains("html-proof") || !d.open) return;
    const f = d.querySelector("iframe[data-src]");
    if (f && !f.src) f.src = f.dataset.src;
  }, true);

  // On a lesson: the button lives on each code block's bar, next to Copy (made here, from [data-codenote-lesson]).
  const src = document.querySelector("[data-codenote-lesson]");
  if (src) {
    const svg = '<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2.2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M8 7l-5 5 5 5M16 7l5 5-5 5"/></svg>';
    document.querySelectorAll(".prose .code-wrap > .code-bar").forEach((bar) => {
      const copy = bar.querySelector("button");
      const acts = document.createElement("span");
      acts.className = "code-acts";
      const b = document.createElement("button");
      b.type = "button";
      b.className = "code-cn";
      b.dataset.codenote = ""; b.dataset.codenoteOnly = "";
      b.dataset.course = src.dataset.course; b.dataset.lesson = src.dataset.lesson;
      b.title = src.dataset.title;
      b.setAttribute("aria-label", src.dataset.label);
      b.innerHTML = `${svg}<span class="cn-long">${src.dataset.label.replace(/[&<>"]/g, "")}</span><span class="cn-short">CodeNote</span>`;
      b.hidden = src.dataset.on !== "1";
      acts.appendChild(b);
      if (copy) acts.appendChild(copy);
      bar.appendChild(acts);
    });
  }
  const only = () => document.querySelectorAll("[data-codenote-only]");
  if (!only().length) return;
  const bridge = window.InPaceAndroid;
  const show = (on) => only().forEach((el) => { el.hidden = !on; });
  window.inpaceCodeNote = (on) => show(!!on);  // the Android app answers here
  const ask = async (fresh) => {
    if (bridge) { try { bridge.postMessage(JSON.stringify({ type: "codenoteCheck" })); } catch (x) { /* old app: stays hidden */ } return; }
    try {
      const d = await (await fetch("/codenote.json" + (fresh ? "?fresh=1" : ""), { cache: "no-store" })).json();
      show(!!d.available);
    } catch (x) { /* keep what the page showed */ }
  };
  ask(false);
  document.addEventListener("visibilitychange", () => { if (!document.hidden) ask(true); });
  addEventListener("focus", () => ask(true));

  document.addEventListener("click", async (e) => {
    const b = e.target.closest("[data-codenote]");
    if (!b || b.disabled) return;
    const body = new FormData();
    body.append("course", b.dataset.course || "");
    if (b.dataset.lesson) body.append("lesson", b.dataset.lesson);
    if (b.dataset.task) body.append("task", b.dataset.task);
    b.disabled = true;
    b.classList.add("is-busy");
    try {
      const d = await (await fetch("/codenote/open", { method: "POST", body, headers: { Accept: "application/json" } })).json();
      if (d.file) {  // too long for a link: the lesson as a .md file, which CodeNote opens
        if (d.message && window.inpaceToast) inpaceToast(d.message);
        if (bridge) bridge.postMessage(JSON.stringify({ type: "download", url: new URL(d.file, location.href).href }));
        else location.href = d.file;
      } else if (d.link && bridge) {
        bridge.postMessage(JSON.stringify({ type: "codenote", link: d.link, web: d.web }));
      } else if (!d.ok && d.message && window.inpaceToast) {
        inpaceToast(d.message);
      }
    } catch (x) { /* nothing opened: the button can be pressed again */ }
    setTimeout(() => { b.disabled = false; b.classList.remove("is-busy"); }, 1200);
  });
})();


// ---- Light, dark and colors (v1.31.2) -------------------------------------------------------------------------
// One place for how inPace looks. The light/dark button at the top and the choices in Settings change the page right
// away, keep every control on the page in step with what's showing (so picking a choice always works, the second
// time too), and are saved in the background. No reload.
(() => {
  const root = document.documentElement;
  const now = {
    theme: () => root.dataset.theme || "",
    dark_style: () => (root.hasAttribute("data-black") ? "black" : ""),
    accent: () => root.dataset.accent || "",
  };
  const set = {
    theme: (v) => { if (v === "light" || v === "dark") root.dataset.theme = v; else delete root.dataset.theme; },
    dark_style: (v) => root.toggleAttribute("data-black", v === "black"),
    accent: (v) => { if (v) root.dataset.accent = v; else delete root.dataset.accent; },
  };
  const sync = () => document.querySelectorAll("input[data-look]").forEach((i) => {
    if (now[i.name]) i.checked = i.value === now[i.name]();
  });
  const save = async (url, body) => {
    try {
      const r = await fetch(url, { method: "POST", body, headers: { "X-InPace-Soft": "1" } });
      const ok = new URL(r.url).searchParams.get("ok");
      if (ok && window.inpaceToast && url !== "/theme") inpaceToast(ok);
    } catch (e) { /* offline server: it's applied on this page, and saved next time */ }
  };
  document.addEventListener("change", (e) => {
    const i = e.target.closest && e.target.closest("input[data-look]");
    if (!i || !set[i.name]) return;
    set[i.name](i.value);
    sync();
    save(i.form.action, new FormData(i.form));
  });
  document.addEventListener("click", (e) => {
    if (!(e.target.closest && e.target.closest("[data-theme-toggle]"))) return;
    const shown = now.theme() || (matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light");
    set.theme(shown === "dark" ? "light" : "dark");
    sync();
    const body = new FormData();
    body.append("theme", now.theme());
    save("/theme", body);
  });
  sync();
})();


// ---- The app window's background (v1.31.3) ---------------------------------------------------------------------
// Every kind of app window (Linux, Windows, Mac, Android) has a background of its own under the page. It shows for a
// moment between pages, and where the page isn't drawn yet while you scroll fast. It used to be white (cream on
// Android), so dark mode flashed. Here the page tells the window its color: when it opens, and whenever the look
// changes (the light/dark button, Settings, or the device switching to dark). A plain browser tab ignores it.
(() => {
  let last = "";
  const tell = () => {
    const m = getComputedStyle(document.body).backgroundColor.match(/\d+(\.\d+)?/g);
    if (!m || m.length < 3) return;
    const hex = "#" + m.slice(0, 3).map((n) => Math.round(+n).toString(16).padStart(2, "0")).join("").toUpperCase();
    if (hex === last) return;
    last = hex;
    try { window.webkit.messageHandlers.inpace.postMessage("bg:" + hex); } catch (e) { /* not the Linux window */ }
    try { if (window.InPaceAndroid) InPaceAndroid.postMessage(JSON.stringify({ type: "bg", color: hex })); } catch (e) { /* older app */ }
    try { if (window.pywebview && pywebview.api && pywebview.api.background) pywebview.api.background(hex); } catch (e) { /* not ready */ }
    if (/QtWebEngine/.test(navigator.userAgent)) console.info("inpace-shell bg:" + hex);  // the Qt window reads this
  };
  // After the styles apply (the theme attributes change first, the colors a frame later).
  const soon = () => requestAnimationFrame(() => requestAnimationFrame(tell));
  new MutationObserver(soon).observe(document.documentElement, { attributes: true, attributeFilter: ["data-theme", "data-black", "data-accent"] });
  try { matchMedia("(prefers-color-scheme: dark)").addEventListener("change", soon); } catch (e) { /* old engine */ }
  window.addEventListener("pywebviewready", () => { last = ""; tell(); });
  window.addEventListener("pageshow", (e) => { if (e.persisted) { last = ""; soon(); } });  // back from the page cache
  tell();
})();

// ---- Long buttons: progress you can see (v1.31.2) -------------------------------------------------------------
// The rules, for every page:
//  1. A form marked [data-progress] (adding a course or a roadmap, updating inPace, getting yt-dlp) is sent in the
//     background with a random token. Its button fills up and says what's happening (/progress.json, filled in by
//     progress.py on the server), and the page stays usable. When the answer comes, the page goes where it says.
//  2. A form that sends big files (2 MB or more) is sent the same way, and its button shows the upload.
//  3. Any other button that takes more than half a second gets a small spinner.
// Without JavaScript every form still works the plain way.
(() => {
  const W = document.body.dataset;
  const size = (n) => (n >= 1073741824 ? (n / 1073741824).toFixed(1) + " GB" : n >= 1048576 ? (n / 1048576).toFixed(n < 10485760 ? 1 : 0) + " MB"
    : Math.max(1, Math.round((n || 0) / 1024)) + " KB");
  const pressed = (form, e) => e.submitter || form.querySelector("button:not([type=button]), [type=submit]");
  const show = (btn, pct, text) => {
    if (!btn) return;
    btn.classList.add("btn-progress");
    btn.style.setProperty("--p", Math.max(0, Math.min(100, pct)) + "%");
    btn.setAttribute("aria-busy", "true");
    btn.disabled = true;
    btn.textContent = text;
  };
  const restore = (btn, html) => {
    if (!btn) return;
    btn.classList.remove("btn-progress", "is-busy"); btn.style.removeProperty("--p"); btn.removeAttribute("data-indeterminate");
    btn.removeAttribute("aria-busy"); btn.disabled = false; btn.innerHTML = html;
  };
  // Where to go with the server's answer: the page it redirected to, or the page it sent (an error, "Restarting…").
  const follow = async (r, action) => {
    const type = r.headers.get("content-type") || "";
    if (r.redirected || (r.url && r.url !== action)) { goFresh(r.url); return; }
    if (type.includes("text/html")) { const html = await r.text(); document.open(); document.write(html); document.close(); return; }
    location.reload();
  };
  const text = (x) => {
    const steps = x.of > 1 ? ` ${x.n}/${x.of}` : "";
    if (x.state === "installing") return x.note === "install" ? W.wInstalling : W.wAdding + steps;
    if (x.size) {
      const pct = Math.round((100 * x.got) / x.size);
      const what = x.note === "download" && x.title ? ` ${x.title}` : "";
      return [`${W.wDownloading}${what}${steps}`, `${pct}%`, `${size(x.got)} / ${size(x.size)}`].join(" · ");
    }
    return x.note === "check" ? W.wChecking : x.got ? `${W.wDownloading}${steps} · ${size(x.got)}` : W.wConnecting;
  };

  // 1. [data-progress] forms
  document.addEventListener("submit", async (e) => {
    const f = e.target;
    if (!(f instanceof HTMLFormElement) || e.defaultPrevented || !f.hasAttribute("data-progress")) return;
    e.preventDefault();
    if (f.dataset.sending) return;
    f.dataset.sending = "1";
    const btn = pressed(f, e), was = btn ? btn.innerHTML : "";
    const token = Array.from(crypto.getRandomValues(new Uint8Array(9)), (b) => (b % 36).toString(36)).join("");
    const body = new FormData(f);
    if (e.submitter && e.submitter.name) body.append(e.submitter.name, e.submitter.value);
    body.set("progress", token);
    const action = new URL(f.getAttribute("action") || location.href, location.href).href;
    let running = true;
    show(btn, 0, W.wConnecting);
    if (window.InPaceAndroid) { try { InPaceAndroid.postMessage(JSON.stringify({ type: "downloads" })); } catch (x) { /* older app */ } }
    let ticks = 0;
    const tick = async () => {
      if (!running) return;
      ticks += 1;
      try {
        const x = await (await fetch("/progress.json?t=" + token, { cache: "no-store" })).json();
        if (running && x && x.state) {
          btn && btn.removeAttribute("data-indeterminate");
          show(btn, x.state === "installing" ? 100 : x.size ? (100 * x.got) / x.size : 0, text(x));
        } else if (running && ticks === 3 && btn) {  // work with no steps to count (an AI answer, say): it's busy
          btn.setAttribute("data-indeterminate", "");
          show(btn, 100, W.wWorking);
        }
      } catch (err) { /* busy: next time */ }
      if (running) setTimeout(tick, 400);
    };
    setTimeout(tick, 250);
    try {
      const r = await fetch(action, { method: "POST", body });
      running = false;
      await follow(r, action);
    } catch (err) {
      running = false;
      delete f.dataset.sending;
      restore(btn, was);
      if (window.inpaceToast) inpaceToast(W.wFailed);
    }
  });

  // 2. Big files: the upload's own progress
  document.addEventListener("submit", (e) => {
    const f = e.target;
    if (!(f instanceof HTMLFormElement) || e.defaultPrevented || f.hasAttribute("data-nav-form") || f.target) return;
    if ((f.getAttribute("enctype") || "") !== "multipart/form-data") return;
    const bytes = [...f.querySelectorAll("input[type=file]")].reduce((a, i) => a + [...(i.files || [])].reduce((b, x) => b + x.size, 0), 0);
    if (bytes < 2 * 1024 * 1024) return;  // small: it's sent in a blink, the usual way
    e.preventDefault();
    const body = new FormData(f);
    if (e.submitter && e.submitter.name) body.append(e.submitter.name, e.submitter.value);
    const btn = pressed(f, e);
    const action = new URL(f.getAttribute("action") || location.href, location.href).href;
    show(btn, 0, `${W.wUploading} 0%`);
    const x = new XMLHttpRequest();
    x.open("POST", action);
    x.upload.onprogress = (ev) => {
      if (!ev.lengthComputable) return;
      const p = Math.round((100 * ev.loaded) / ev.total);
      show(btn, p, p >= 100 ? W.wWorking : `${W.wUploading} ${p}% · ${size(ev.loaded)} / ${size(ev.total)}`);
    };
    x.upload.onload = () => show(btn, 100, W.wWorking);
    x.onload = () => {
      if (x.responseURL && x.responseURL !== action) { goFresh(x.responseURL); return; }
      document.open(); document.write(x.responseText); document.close();
    };
    x.onerror = () => { HTMLFormElement.prototype.submit.call(f); };  // couldn't send it this way: the usual way
    x.send(body);
  });

  // 3. Everything else that takes a moment: a small spinner on the button
  document.addEventListener("submit", (e) => {
    const f = e.target;
    if (!(f instanceof HTMLFormElement) || e.defaultPrevented || f.target) return;
    const btn = pressed(f, e);
    if (!btn || btn.classList.contains("btn-progress")) return;
    // Forms that update the page in place have their own feedback (and their buttons must stay as drawn).
    if (f.closest("[data-live]") || f.matches("[data-nav-form], [data-dl-form], .yt-save, [data-timer-form]")) return;
    const t = setTimeout(() => { if (btn.isConnected) btn.classList.add("is-busy"); }, 450);
    addEventListener("pagehide", () => clearTimeout(t), { once: true });
  });
})();
})();
