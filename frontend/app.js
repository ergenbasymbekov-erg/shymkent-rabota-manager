const $ = (s) => document.querySelector(s);

async function init() {
  bindGenerate();
  document.querySelectorAll(".copy-btn[data-copy]").forEach((b) => {
    b.onclick = () => copyOutput(b.dataset.copy, b);
  });
}

function bindGenerate() {
  $("#generate-btn").onclick = async () => {
    const text = $("#final-text").value;
    if (!text.trim()) return;

    const btn = $("#generate-btn");
    btn.disabled = true;
    btn.textContent = "Generating…";
    $("#results").hidden = true;

    try {
      const r = await fetch("/api/generate", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      });
      const j = await r.json();
      if (!r.ok) throw new Error(j.detail || j.error || r.statusText);
      renderResults(j);
    } catch (e) {
      alert(`Error: ${e.message}`);
    } finally {
      btn.disabled = false;
      btn.textContent = "Generate";
    }
  };
}

function renderResults(j) {
  const warnCard = $("#warning-card");
  const warnOut = $("#warning-out");
  if (j.poster_warning) {
    warnCard.hidden = false;
    warnOut.textContent = j.poster_warning;
  } else {
    warnCard.hidden = true;
  }

  $("#telegram-out").textContent = j.outputs?.telegram_text || "";
  $("#telegram-buttons-out").textContent = JSON.stringify(j.outputs?.telegram_buttons || [], null, 2);
  $("#whatsapp-out").textContent = j.outputs?.whatsapp_text || "";

  const img = $("#poster-preview");
  const dl = $("#poster-download");
  if (j.poster_png_url) {
    const bust = `${j.poster_png_url}?t=${Date.now()}`;
    img.src = bust;
    img.hidden = false;
    dl.href = bust;
    dl.download = j.poster_png_filename || "vacancy_poster.png";
    dl.hidden = false;
  } else {
    img.hidden = true;
    dl.hidden = true;
    if (j.error) alert(j.error);
  }

  $("#results").hidden = false;
}

async function copyOutput(id, btn) {
  const el = document.getElementById(id);
  if (!el?.textContent) return;
  try {
    await navigator.clipboard.writeText(el.textContent);
    const prev = btn.textContent;
    btn.textContent = "Copied!";
    setTimeout(() => { btn.textContent = prev; }, 1500);
  } catch {
    alert("Copy failed — select text manually.");
  }
}

init();
