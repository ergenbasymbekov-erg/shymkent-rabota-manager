const $ = (s) => document.querySelector(s);
const KEY_STORAGE = "manager_web_key";

function headers() {
  const key = sessionStorage.getItem(KEY_STORAGE) || "";
  return {
    "Content-Type": "application/json",
    "X-Manager-Key": key,
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
}

async function checkKey(key) {
  const r = await fetch("/api/manager/preview", {
    method: "POST",
    headers: {
      "Content-Type": "application/json",
      "X-Manager-Key": key,
    },
    body: JSON.stringify({ text: "ping" }),
  });
  if (r.status === 401) return false;
  return r.ok || r.status === 400;
}

function setStatus(msg) {
  $("#status-line").textContent = msg || "";
}

function vacancyText() {
  return $("#vacancy-text").value.trim();
}

function renderPreview(j) {
  const block = $("#preview-block");
  const img = $("#poster-img");
  const wrap = $("#poster-wrap");
  if (j.poster_png_url) {
    wrap.hidden = false;
    img.src = `${j.poster_png_url}?t=${Date.now()}`;
  } else {
    wrap.hidden = true;
  }
  $("#tg-preview").textContent = j.outputs?.telegram_text || "";
  block.hidden = false;
  window._lastWa = j.outputs?.whatsapp_text || "";
}

async function preview() {
  const text = vacancyText();
  if (!text) {
    setStatus("Мәтін бос");
    return;
  }
  const btn = $("#preview-btn");
  btn.disabled = true;
  setStatus("Дайындау…");
  try {
    const r = await fetch("/api/manager/preview", {
      method: "POST",
      headers: headers(),
      body: JSON.stringify({ text }),
    });
    const j = await r.json();
    if (!r.ok) throw new Error(j.detail || j.error || r.statusText);
    renderPreview(j);
    setStatus("Preview дайын");
  } catch (e) {
    setStatus(`Қате: ${e.message}`);
  } finally {
    btn.disabled = false;
  }
}

async function publish() {
  const text = vacancyText();
  if (!text) {
    setStatus("Мәтін бос");
    return;
  }
  if (!confirm("Каналға жариялайсыз ба?")) return;

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
    if (!r.ok) throw new Error(typeof j.detail === "string" ? j.detail : JSON.stringify(j.detail) || r.statusText);
    setStatus(`✅ Жарияланды: ${j.channel || "канал"}`);
    renderPreview(await (await fetch("/api/manager/preview", {
      method: "POST",
      headers: headers(),
      body: JSON.stringify({ text }),
    })).json());
  } catch (e) {
    setStatus(`Қате: ${e.message}`);
  } finally {
    btn.disabled = false;
  }
}

function init() {
  $("#login-btn").onclick = async () => {
    const key = $("#manager-key").value.trim();
    if (!key) return showLogin("Кодты енгізіңіз");
    setStatus("");
    try {
      const ok = await checkKey(key);
      if (!ok) return showLogin("Қате код");
      sessionStorage.setItem(KEY_STORAGE, key);
      showApp();
    } catch (e) {
      showLogin(`Байланыс қатесі: ${e.message}`);
    }
  };

  $("#logout-btn").onclick = () => {
    sessionStorage.removeItem(KEY_STORAGE);
    showLogin();
  };

  $("#preview-btn").onclick = preview;
  $("#publish-btn").onclick = publish;

  $("#copy-wa-btn").onclick = async () => {
    const t = window._lastWa || "";
    if (!t) return;
    try {
      await navigator.clipboard.writeText(t);
      setStatus("WhatsApp мәтіні көшірілді");
    } catch {
      setStatus("Көшіру сәтсіз — қолмен таңдаңыз");
    }
  };

  const saved = sessionStorage.getItem(KEY_STORAGE);
  if (saved) {
    checkKey(saved).then((ok) => (ok ? showApp() : showLogin()));
  } else {
    showLogin();
  }
}

init();
