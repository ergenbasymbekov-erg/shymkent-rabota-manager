const $ = (s) => document.querySelector(s);
const KEY_STORAGE = "manager_web_key";

function headers() {
  return {
    "Content-Type": "application/json",
    "X-Manager-Key": sessionStorage.getItem(KEY_STORAGE) || "",
  };
}

function showLogin(err) {
  $("#login-screen").hidden = false;
  $("#app-screen").hidden = true;
  const el = $("#login-err");
  if (err) {
    el.textContent = err;
    el.hidden = false;
  } else {
    el.hidden = true;
  }
}

function showApp() {
  $("#login-screen").hidden = true;
  $("#app-screen").hidden = false;
  showInput();
}

function showInput() {
  $("#input-section").hidden = false;
  $("#preview-screen").hidden = true;
  $("#publish-btn").disabled = true;
  window._previewPayload = null;
}

function showPreviewScreen() {
  $("#input-section").hidden = true;
  $("#preview-screen").hidden = false;
  $("#publish-btn").disabled = false;
}

function setStatus(msg) {
  $("#status-line").textContent = msg || "";
}

function vacancyText() {
  return $("#vacancy-text").value.trim();
}

/** Remove platform footer from WhatsApp (works even if server not redeployed yet). */
function stripWaPlatformFooter(text) {
  if (!text) return "";
  const drop = (line) => {
    const t = line.trim();
    if (!t) return false;
    if (/хабарландыру/i.test(t)) return true;
    if (/776\s*383\s*7171/.test(t)) return true;
    if (/^━+$/.test(t)) return true;
    return false;
  };
  return text
    .split("\n")
    .filter((line) => !drop(line))
    .join("\n")
    .replace(/\n{3,}/g, "\n\n")
    .trim();
}

function renderPreview(j) {
  const img = $("#poster-img");
  const missing = $("#poster-missing");
  if (j.poster_png_url) {
    img.src = `${j.poster_png_url}?t=${Date.now()}`;
    img.hidden = false;
    missing.hidden = true;
  } else {
    img.hidden = true;
    missing.hidden = false;
    if (j.error) missing.textContent = `Постер: ${j.error}`;
  }

  const tg = $("#tg-preview");
  if (j.telegram_html) {
    tg.innerHTML = j.telegram_html;
  } else {
    tg.textContent = j.outputs?.telegram_text || "";
  }

  const waRaw = j.outputs?.whatsapp_text || "";
  const wa = stripWaPlatformFooter(waRaw);
  $("#wa-preview").textContent = wa;
  window._lastWa = wa;
  window._previewPayload = j;
  showPreviewScreen();
}

async function preview() {
  const text = vacancyText();
  if (!text) {
    setStatus("Мәтін бос");
    return;
  }
  const btn = $("#preview-btn");
  btn.disabled = true;
  setStatus("Постер + Telegram дайындау…");
  try {
    const r = await fetch("/api/manager/preview", {
      method: "POST",
      headers: headers(),
      body: JSON.stringify({ text }),
    });
    const j = await r.json();
    if (!r.ok) throw new Error(j.detail || j.error || r.statusText);
    renderPreview(j);
    setStatus("");
    window.scrollTo({ top: 0, behavior: "smooth" });
  } catch (e) {
    setStatus(`Қате: ${e.message}`);
  } finally {
    btn.disabled = false;
  }
}

async function publish() {
  const text = vacancyText();
  if (!text || !window._previewPayload) {
    setStatus("Алдымен preview көріңіз");
    return;
  }
  if (!confirm("Каналға жариялайсыз ба?\n@Shymkent_Rabota_Job")) return;

  const btn = $("#publish-btn");
  btn.disabled = true;
  setStatus("Жариялау…");
  try {
    const r = await fetch("/api/manager/publish", {
      method: "POST",
      headers: headers(),
      body: JSON.stringify({ text }),
    });
    const j = await r.json();
    if (!r.ok) {
      const detail = typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail);
      throw new Error(detail || r.statusText);
    }
    setStatus(`✅ Жарияланды: ${j.channel || "@Shymkent_Rabota_Job"}`);
  } catch (e) {
    setStatus(`Қате: ${e.message}`);
    btn.disabled = false;
  }
}

function init() {
  $("#login-btn").onclick = async () => {
    const key = $("#manager-key").value.trim();
    if (!key) return showLogin("Кодты енгізіңіз");
    try {
      const ok = await fetch("/api/manager/preview", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-Manager-Key": key },
        body: JSON.stringify({ text: "ping" }),
      }).then((r) => r.status !== 401);
      if (!ok) return showLogin("Қате код");
      sessionStorage.setItem(KEY_STORAGE, key);
      showApp();
    } catch (e) {
      showLogin(`Байланыс: ${e.message}`);
    }
  };

  $("#logout-btn").onclick = () => {
    sessionStorage.removeItem(KEY_STORAGE);
    showLogin();
  };

  $("#preview-btn").onclick = preview;
  $("#publish-btn").onclick = publish;
  $("#back-btn").onclick = () => {
    showInput();
    setStatus("");
  };

  $("#copy-wa-btn").onclick = async () => {
    const t = window._lastWa || "";
    if (!t) return;
    try {
      await navigator.clipboard.writeText(t);
      setStatus("WhatsApp көшірілді");
    } catch {
      setStatus("Көшіру сәтсіз");
    }
  };

  const saved = sessionStorage.getItem(KEY_STORAGE);
  if (saved) {
    fetch("/api/health")
      .then(() => {
        sessionStorage.setItem(KEY_STORAGE, saved);
        showApp();
      })
      .catch(() => showLogin());
  } else {
    showLogin();
  }
}

init();
