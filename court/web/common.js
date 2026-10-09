/* Общие утилиты интерфейса. Без внешних библиотек — демо работает офлайн. */

function esc(s) {
  return String(s === null || s === undefined ? "" : s)
    .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;");
}

function el(id) { return document.getElementById(id); }

async function api(path, payload) {
  const res = await fetch(path, {
    method: payload ? "POST" : "GET",
    headers: { "Content-Type": "application/json" },
    body: payload ? JSON.stringify(payload) : undefined
  });
  const data = await res.json();
  if (data.error) throw new Error(data.error);
  return data;
}

/* ------------------------------------------------------------------ */
/* Загрузка файлов: чтение выполняется в браузере, на сервер уходит    */
/* только текст. Файлы на диск не сохраняются.                         */
/* ------------------------------------------------------------------ */
const TEXT_EXT = ["txt", "md", "text", "csv"];

function extOf(name) {
  const parts = String(name || "").split(".");
  return parts.length > 1 ? parts.pop().toLowerCase() : "";
}

function setupDropzone(zoneId, inputId, listId, store, onChange) {
  const zone = el(zoneId), input = el(inputId), list = el(listId);

  function render() {
    list.innerHTML = store.length ? store.map(function (f) {
      const ext = extOf(f.name);
      return '<li><span>' + esc(f.name) + '</span>' +
        (ext ? '<span class="pill">' + esc(ext) + '</span>' : '') +
        '<span class="sz">' + Math.max(1, Math.ceil(f.size / 1024)) + ' КБ</span></li>';
    }).join("") : "";
    if (onChange) onChange();
  }

  /* Текстовые файлы читаются как текст, остальные — как base64: разбор
     docx, rtf и pdf выполняется на сервере, локально, без записи на диск. */
  function addFiles(files) {
    let pending = files.length;
    if (!pending) return;
    Array.prototype.forEach.call(files, function (file) {
      const reader = new FileReader();
      const isText = TEXT_EXT.indexOf(extOf(file.name)) >= 0 || !extOf(file.name);
      reader.onload = function () {
        if (isText) {
          store.push({ name: file.name, text: String(reader.result || ""),
                       size: file.size });
        } else {
          const result = String(reader.result || "");
          store.push({ name: file.name, size: file.size,
                       data_base64: result.slice(result.indexOf(",") + 1) });
        }
        if (--pending === 0) render();
      };
      reader.onerror = function () { if (--pending === 0) render(); };
      if (isText) reader.readAsText(file, "utf-8");
      else reader.readAsDataURL(file);
    });
  }

  zone.addEventListener("click", function () { input.click(); });
  input.addEventListener("change", function () { addFiles(input.files); input.value = ""; });
  ["dragenter", "dragover"].forEach(function (e) {
    zone.addEventListener(e, function (ev) { ev.preventDefault(); zone.classList.add("over"); });
  });
  ["dragleave", "drop"].forEach(function (e) {
    zone.addEventListener(e, function (ev) { ev.preventDefault(); zone.classList.remove("over"); });
  });
  zone.addEventListener("drop", function (ev) { addFiles(ev.dataTransfer.files); });

  return { render: render, clear: function () { store.length = 0; render(); } };
}

function renderDemoCases(containerId, onPick) {
  return api("/api/demo-cases").then(function (data) {
    el(containerId).innerHTML = data.cases.map(function (c) {
      return '<button class="demo-case" data-id="' + esc(c.id) + '">' +
        '<b>' + esc(c.title) + '</b><span>' + esc(c.short) + ' — ' +
        esc(c.expectation) + '</span></button>';
    }).join("");
    Array.prototype.forEach.call(
      el(containerId).querySelectorAll(".demo-case"),
      function (btn) {
        btn.addEventListener("click", function () { onPick(btn.dataset.id); });
      });
  });
}

function showError(nodeId, message) {
  el(nodeId).innerHTML = '<div class="err">Не удалось выполнить анализ: ' +
    esc(message) + "</div>";
  el(nodeId).classList.remove("hidden");
}

/* Круговой индикатор вероятности (рисуется вручную, без библиотек) */
function gauge(pct) {
  const r = 74, c = 2 * Math.PI * r;
  const color = pct >= 70 ? "var(--green)" : pct >= 45 ? "#c08c1e" : "var(--red)";
  return '<div class="gauge"><svg width="168" height="168" viewBox="0 0 168 168">' +
    '<circle cx="84" cy="84" r="' + r + '" fill="none" stroke="#e7ebf1" stroke-width="13"/>' +
    '<circle cx="84" cy="84" r="' + r + '" fill="none" stroke="' + color +
    '" stroke-width="13" stroke-linecap="round" stroke-dasharray="' + c +
    '" stroke-dashoffset="' + (c * (1 - pct / 100)) + '"/></svg>' +
    '<div class="val"><div class="num">' + pct + '%</div>' +
    '<div class="lbl">ориентировочно</div></div></div>';
}
