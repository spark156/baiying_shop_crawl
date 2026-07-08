const state = {
  shops: [],
  selectedShops: new Set(),
  page: 1,
  pageSize: 50,
  total: 0,
  polling: null,
};

const $ = (selector) => document.querySelector(selector);
const elements = {
  startDate: $("#startDate"),
  endDate: $("#endDate"),
  startDateDisplay: $("#startDateDisplay"),
  endDateDisplay: $("#endDateDisplay"),
  maxPages: $("#maxPages"),
  shopPickerButton: $("#shopPickerButton"),
  shopMenu: $("#shopMenu"),
  recordsBody: $("#recordsBody"),
  emptyState: $("#emptyState"),
  taskPanel: $("#taskPanel"),
  taskMessage: $("#taskMessage"),
  taskDot: $("#taskDot"),
  taskLog: $("#taskLog"),
  toast: $("#toast"),
};

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

async function api(path, options = {}) {
  const response = await fetch(path, {
    headers: { "Content-Type": "application/json", ...(options.headers || {}) },
    ...options,
  });
  const data = await response.json();
  if (!response.ok) throw new Error(data.error || `请求失败 (${response.status})`);
  return data;
}

function showToast(message, error = false) {
  elements.toast.textContent = message;
  elements.toast.classList.toggle("error", error);
  elements.toast.hidden = false;
  clearTimeout(showToast.timer);
  showToast.timer = setTimeout(() => { elements.toast.hidden = true; }, 3500);
}

function isoToDisplay(value) {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(value || "");
  return match ? `${match[2]}/${match[3]}/${match[1]}` : "";
}

function displayToIso(value) {
  const match = /^(\d{1,2})\/(\d{1,2})\/(\d{4})$/.exec((value || "").trim());
  if (!match) return "";
  const month = Number(match[1]);
  const day = Number(match[2]);
  const year = Number(match[3]);
  const candidate = new Date(Date.UTC(year, month - 1, day));
  if (
    candidate.getUTCFullYear() !== year
    || candidate.getUTCMonth() !== month - 1
    || candidate.getUTCDate() !== day
  ) return "";
  return `${String(year).padStart(4, "0")}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}`;
}

function setDateValue(nativeInput, displayInput, isoValue) {
  nativeInput.value = isoValue || "";
  displayInput.value = isoToDisplay(nativeInput.value);
  displayInput.classList.remove("invalid");
}

function syncDateInput(nativeInput, displayInput) {
  const raw = displayInput.value.trim();
  const isoValue = displayToIso(raw);
  const valid = !raw || Boolean(isoValue);
  nativeInput.value = isoValue;
  displayInput.classList.toggle("invalid", !valid);
  return valid;
}

function requireValidDates() {
  const startValid = syncDateInput(elements.startDate, elements.startDateDisplay);
  const endValid = syncDateInput(elements.endDate, elements.endDateDisplay);
  if (!startValid || !endValid) throw new Error("日期格式请填写为 MM/DD/YYYY");
}

function currentFilters() {
  requireValidDates();
  return {
    start_date: elements.startDate.value,
    end_date: elements.endDate.value,
    shops: [...state.selectedShops],
  };
}

function updateShopPickerLabel() {
  const selected = [...state.selectedShops];
  if (selected.length === state.shops.length) {
    elements.shopPickerButton.textContent = `全部店铺 (${selected.length})`;
  } else if (!selected.length) {
    elements.shopPickerButton.textContent = "请选择店铺";
  } else if (selected.length === 1) {
    elements.shopPickerButton.textContent = selected[0];
  } else {
    elements.shopPickerButton.textContent = `已选 ${selected.length} 家店铺`;
  }
}

function renderShopMenu() {
  elements.shopMenu.innerHTML = state.shops.map((shop) => `
    <label class="shop-option">
      <input type="checkbox" value="${escapeHtml(shop.name)}" ${state.selectedShops.has(shop.name) ? "checked" : ""}>
      <span>${escapeHtml(shop.name)}</span>
    </label>
  `).join("");
  elements.shopMenu.querySelectorAll("input").forEach((input) => {
    input.addEventListener("change", () => {
      if (input.checked) state.selectedShops.add(input.value);
      else state.selectedShops.delete(input.value);
      updateShopPickerLabel();
    });
  });
  updateShopPickerLabel();
}

function renderSummary(summary) {
  $("#productCount").textContent = Number(summary.product_count || 0).toLocaleString("zh-CN");
  $("#sessionCount").textContent = Number(summary.session_count || 0).toLocaleString("zh-CN");
  $("#shopCount").textContent = Number(summary.shop_count || 0).toLocaleString("zh-CN");
  $("#dateRange").textContent = summary.first_date
    ? `${summary.first_date} 至 ${summary.last_date}`
    : "-";
  $("#summaryNote").textContent = "历史场次命中缓存后不会重复抓取";
}

function renderRows(rows) {
  elements.recordsBody.innerHTML = rows.map((row) => {
    const image = escapeHtml(row["商品图片"] || "");
    const productUrl = escapeHtml(row["商品链接"] || "#");
    const shopUrl = escapeHtml(row["店铺网址"] || "");
    const shopName = escapeHtml(row["店铺名称"] || "-");
    const shopCell = shopUrl
      ? `<a class="product-link shop-name" href="${shopUrl}" target="_blank" rel="noreferrer">${shopName}</a>`
      : `<span class="shop-name">${shopName}</span>`;
    return `
      <tr>
        <td>${image ? `<a href="${image}" target="_blank" rel="noreferrer"><img class="product-image" src="${image}" alt="" loading="lazy" onerror="this.style.visibility='hidden'"></a>` : "-"}</td>
        <td>${shopCell}</td>
        <td>${escapeHtml(row["直播时间"] || "-")}<span class="secondary-text">${escapeHtml(row["直播时长"] || "")}</span></td>
        <td><a class="product-link" href="${productUrl}" target="_blank" rel="noreferrer">${escapeHtml(row["商品名称"] || "未命名商品")}</a></td>
        <td>${escapeHtml(row["到手价"] || "-")}</td>
        <td class="settlement">${escapeHtml(row["单场直播结算额"] || "-")}</td>
      </tr>
    `;
  }).join("");
  elements.emptyState.hidden = rows.length > 0;
}

async function loadRecords(resetPage = false) {
  if (resetPage) state.page = 1;
  try {
    const filters = currentFilters();
    const params = new URLSearchParams({
      start_date: filters.start_date,
      end_date: filters.end_date,
      shops: filters.shops.join(","),
      page: state.page,
      page_size: state.pageSize,
    });
    $("#summaryNote").textContent = "正在查询";
    const data = await api(`/api/records?${params}`);
    state.total = data.total;
    renderRows(data.rows);
    renderSummary(data.summary);
    const pages = Math.max(1, Math.ceil(data.total / state.pageSize));
    $("#resultMeta").textContent = `${data.total.toLocaleString("zh-CN")} 条记录`;
    $("#pageInfo").textContent = `第 ${state.page} / ${pages} 页`;
    $("#previousButton").disabled = state.page <= 1;
    $("#nextButton").disabled = state.page >= pages;
  } catch (error) {
    showToast(error.message, true);
  }
}

function renderTask(task) {
  const visible = task.status !== "idle" || task.events?.length;
  elements.taskPanel.hidden = !visible;
  elements.taskMessage.textContent = task.error ? `${task.message}：${task.error}` : task.message;
  elements.taskDot.className = `task-dot ${task.status}`;
  elements.taskLog.innerHTML = (task.events || [])
    .map((event) => `<div>${escapeHtml(event.message)}</div>`).join("");
  elements.taskLog.scrollTop = elements.taskLog.scrollHeight;
  $("#crawlButton").disabled = task.status === "running";
}

async function pollTask() {
  try {
    const task = await api("/api/task");
    renderTask(task);
    if (task.status === "running") return;
    clearInterval(state.polling);
    state.polling = null;
    if (task.status === "complete") {
      showToast("增量抓取完成");
      await loadRecords(true);
    } else if (task.status === "error") {
      showToast(task.error || "抓取失败", true);
    }
  } catch (error) {
    showToast(error.message, true);
  }
}

async function startCrawl() {
  try {
    const filters = currentFilters();
    if (!filters.shops.length) throw new Error("请至少选择一家店铺");
    if (filters.start_date && filters.end_date && filters.start_date > filters.end_date) {
      throw new Error("开始日期不能晚于结束日期");
    }
    const data = await api("/api/crawl", {
      method: "POST",
      body: JSON.stringify({ ...filters, max_pages: Number(elements.maxPages.value) }),
    });
    renderTask(data.task);
    state.polling = setInterval(pollTask, 1200);
  } catch (error) {
    showToast(error.message, true);
  }
}

async function exportXlsx() {
  const button = $("#exportButton");
  button.disabled = true;
  button.textContent = "正在生成...";
  try {
    const filters = currentFilters();
    const data = await api("/api/export", {
      method: "POST",
      body: JSON.stringify(filters),
    });
    showToast(`已生成 ${data.count} 条记录`);
    window.location.href = data.download_url;
  } catch (error) {
    showToast(error.message, true);
  } finally {
    button.disabled = false;
    button.textContent = "导出 Excel";
  }
}

function updateChromeStatus(status) {
  const chip = $("#chromeStatus");
  chip.className = "status-chip";
  if (status.buyin_ready) {
    chip.textContent = "登录浏览器已就绪";
    chip.classList.add("ready");
  } else if (status.connected) {
    chip.textContent = "浏览器已启动，等待登录";
    chip.classList.add("warning");
  } else {
    chip.textContent = "登录浏览器未启动";
  }
}

async function startChrome() {
  const button = $("#startChromeButton");
  button.disabled = true;
  button.textContent = "正在启动...";
  try {
    const result = await api("/api/chrome/start", { method: "POST", body: "{}" });
    updateChromeStatus(result);
    showToast(`${result.browser} 已启动`);
  } catch (error) {
    showToast(error.message, true);
  } finally {
    button.disabled = false;
    button.textContent = "启动登录浏览器";
  }
}

function shopRow(shop = { name: "", url: "" }) {
  const row = document.createElement("div");
  row.className = "shop-row";
  row.innerHTML = `
    <input class="shop-name-input" value="${escapeHtml(shop.name)}" placeholder="店铺名称">
    <input class="shop-url" value="${escapeHtml(shop.url)}" placeholder="https://buyin.jinritemai.com/...">
    <button type="button" class="remove-shop">删除</button>
  `;
  row.querySelector(".remove-shop").addEventListener("click", () => row.remove());
  return row;
}

function openShopDialog() {
  const container = $("#shopRows");
  container.innerHTML = "";
  state.shops.forEach((shop) => container.append(shopRow(shop)));
  $("#shopDialog").showModal();
}

async function saveShops() {
  const shops = [...document.querySelectorAll(".shop-row")].map((row) => ({
    name: row.querySelector(".shop-name-input").value.trim(),
    url: row.querySelector(".shop-url").value.trim(),
  }));
  try {
    const data = await api("/api/shops", {
      method: "POST",
      body: JSON.stringify({ shops }),
    });
    state.shops = data.shops;
    state.selectedShops = new Set(state.shops.map((shop) => shop.name));
    renderShopMenu();
    $("#shopDialog").close();
    showToast("店铺列表已保存");
    await loadRecords(true);
  } catch (error) {
    showToast(error.message, true);
  }
}

async function bootstrap() {
  try {
    const data = await api("/api/bootstrap");
    state.shops = data.shops;
    state.selectedShops = new Set(data.shops.map((shop) => shop.name));
    setDateValue(elements.endDate, elements.endDateDisplay, data.summary.last_date || data.today);
    setDateValue(elements.startDate, elements.startDateDisplay, data.summary.first_date || data.default_start);
    renderShopMenu();
    renderSummary(data.summary);
    renderTask(data.task);
    updateChromeStatus(data.chrome);
    await loadRecords(true);
    if (data.task.status === "running") state.polling = setInterval(pollTask, 1200);
  } catch (error) {
    showToast(error.message, true);
  }
}

elements.shopPickerButton.addEventListener("click", () => {
  elements.shopMenu.hidden = !elements.shopMenu.hidden;
  elements.shopPickerButton.setAttribute("aria-expanded", String(!elements.shopMenu.hidden));
});
document.addEventListener("click", (event) => {
  if (!event.target.closest(".shop-picker")) elements.shopMenu.hidden = true;
});
$("#queryButton").addEventListener("click", () => loadRecords(true));
$("#crawlButton").addEventListener("click", startCrawl);
$("#exportButton").addEventListener("click", exportXlsx);
$("#startChromeButton").addEventListener("click", startChrome);
$("#shopSettingsButton").addEventListener("click", openShopDialog);
$("#addShopButton").addEventListener("click", () => $("#shopRows").append(shopRow()));
$("#saveShopsButton").addEventListener("click", saveShops);
$("#toggleLogButton").addEventListener("click", () => {
  elements.taskLog.hidden = !elements.taskLog.hidden;
  $("#toggleLogButton").textContent = elements.taskLog.hidden ? "查看明细" : "收起明细";
});
$("#pageSize").addEventListener("change", (event) => {
  state.pageSize = Number(event.target.value);
  loadRecords(true);
});
$("#previousButton").addEventListener("click", () => { state.page -= 1; loadRecords(); });
$("#nextButton").addEventListener("click", () => { state.page += 1; loadRecords(); });
[
  [elements.startDate, elements.startDateDisplay],
  [elements.endDate, elements.endDateDisplay],
].forEach(([nativeInput, displayInput]) => {
  nativeInput.addEventListener("change", () => setDateValue(nativeInput, displayInput, nativeInput.value));
  displayInput.addEventListener("blur", () => syncDateInput(nativeInput, displayInput));
  displayInput.addEventListener("input", () => displayInput.classList.remove("invalid"));
});

bootstrap();
