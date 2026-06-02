const state = {
  examples: [],
  lastResponse: null,
  chart: null,
};

const chartTypeLabels = {
  bar: "柱状图",
  line: "折线图",
  pie: "饼图",
  table: "表格",
  empty: "空结果",
};

const columnLabels = {
  region_name: "地区",
  order_count: "订单数量",
  sales_amount: "销售额",
  product_name: "商品",
  category: "品类",
  month: "月份",
  avg_order_value: "客单价",
  current_quantity: "本期销量",
  previous_quantity: "上期销量",
  growth_rate_percent: "环比增长率",
  previous_amount: "上期销售额",
  last_amount: "本期销售额",
  amount_change: "销售额变化",
  industry: "行业",
  customer_count: "客户数量",
};

const valueLabels = {
  "East China": "华东",
  "North China": "华北",
  "South China": "华南",
  "West China": "西部",
};

const el = {
  healthStatus: document.querySelector("#healthStatus"),
  questionInput: document.querySelector("#questionInput"),
  maxRowsInput: document.querySelector("#maxRowsInput"),
  runButton: document.querySelector("#runButton"),
  refreshExamplesButton: document.querySelector("#refreshExamplesButton"),
  loadSchemaButton: document.querySelector("#loadSchemaButton"),
  exampleList: document.querySelector("#exampleList"),
  schemaBox: document.querySelector("#schemaBox"),
  metricRows: document.querySelector("#metricRows"),
  metricColumns: document.querySelector("#metricColumns"),
  metricChart: document.querySelector("#metricChart"),
  metricTrace: document.querySelector("#metricTrace"),
  activeQuestion: document.querySelector("#activeQuestion"),
  runState: document.querySelector("#runState"),
  insightText: document.querySelector("#insightText"),
  warningList: document.querySelector("#warningList"),
  chartHost: document.querySelector("#chartHost"),
  resultTable: document.querySelector("#resultTable"),
  sqlBlock: document.querySelector("#sqlBlock"),
  copySqlButton: document.querySelector("#copySqlButton"),
  traceList: document.querySelector("#traceList"),
  tabs: document.querySelectorAll(".tab"),
  tabPanels: document.querySelectorAll(".tab-panel"),
};

function setRunState(label, kind = "idle") {
  el.runState.textContent = label;
  el.runState.className = `state-label ${kind}`;
}

function setHealth(label, kind = "") {
  el.healthStatus.textContent = label;
  el.healthStatus.className = `status-pill ${kind}`;
}

async function fetchJson(url, options) {
  const response = await fetch(url, options);
  const contentType = response.headers.get("content-type") || "";
  const payload = contentType.includes("application/json") ? await response.json() : null;
  if (!response.ok) {
    const message = payload?.detail || `Request failed: ${response.status}`;
    throw new Error(message);
  }
  return payload;
}

async function checkHealth() {
  try {
    const data = await fetchJson("/api/health");
    const modelText = data.llm_enabled ? ` · ${data.llm_model}` : " · 演示模式";
    setHealth(`服务在线${modelText}`, "ok");
  } catch (error) {
    setHealth("服务异常", "error");
  }
}

async function loadExamples() {
  el.exampleList.innerHTML = '<div class="empty-state">加载中</div>';
  try {
    const data = await fetchJson("/api/examples");
    state.examples = data.examples || [];
    renderExamples();
  } catch (error) {
    el.exampleList.innerHTML = `<div class="warning-item">${escapeHtml(error.message)}</div>`;
  }
}

function renderExamples() {
  if (!state.examples.length) {
    el.exampleList.innerHTML = '<div class="empty-state">暂无示例</div>';
    return;
  }

  el.exampleList.innerHTML = state.examples
    .map(
      (example, index) => `
        <button class="example-button" type="button" data-index="${index}">
          <strong>${escapeHtml(example.question)}</strong>
          <span>${escapeHtml(example.intent)} · ${escapeHtml(chartTypeLabels[example.expected_chart] || example.expected_chart)}</span>
        </button>
      `,
    )
    .join("");
}

async function loadSchema() {
  el.schemaBox.textContent = "读取中";
  try {
    const data = await fetchJson("/api/schema/overview");
    if (!data.tables?.length) {
      el.schemaBox.textContent = "暂无表";
      return;
    }
    el.schemaBox.innerHTML = `
      <table class="schema-table">
        <tbody>
          ${data.tables
            .map(
              (table) => `
                <tr>
                  <td>${escapeHtml(table.name)}</td>
                  <td>${escapeHtml(table.columns.map((column) => column.name).join(", "))}</td>
                </tr>
              `,
            )
            .join("")}
        </tbody>
      </table>
    `;
  } catch (error) {
    el.schemaBox.innerHTML = `<div class="warning-item">${escapeHtml(error.message)}</div>`;
  }
}

async function runAnalysis() {
  const question = el.questionInput.value.trim();
  const maxRows = Number(el.maxRowsInput.value || 100);
  if (!question) {
    setRunState("缺少问题", "error");
    el.questionInput.focus();
    return;
  }

  setRunState("分析中", "");
  el.runButton.disabled = true;
  el.runButton.querySelector("span").textContent = "分析中";

  try {
    const data = await fetchJson("/api/chat/query", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, max_rows: maxRows }),
    });
    state.lastResponse = data;
    renderResponse(data);
    setRunState("完成", "ok");
  } catch (error) {
    setRunState("失败", "error");
    el.insightText.textContent = error.message;
  } finally {
    el.runButton.disabled = false;
    el.runButton.querySelector("span").textContent = "运行分析";
  }
}

function renderResponse(data) {
  el.metricRows.textContent = data.rows.length;
  el.metricColumns.textContent = data.columns.length;
  el.metricChart.textContent = chartTypeLabels[data.chart?.type] || data.chart?.type || "-";
  el.metricTrace.textContent = data.trace_steps.length;
  el.activeQuestion.textContent = data.question;
  el.insightText.textContent = data.insight;
  el.sqlBlock.textContent = data.generated_sql || "-- SQL unavailable";

  renderWarnings(data.warnings || []);
  renderTable(data.columns, data.rows);
  renderTrace(data.trace_steps || []);
  renderChart(data.chart, data.rows);
}

function renderWarnings(warnings) {
  el.warningList.innerHTML = warnings
    .map((warning) => `<div class="warning-item">${escapeHtml(warning)}</div>`)
    .join("");
}

function renderTable(columns, rows) {
  const thead = el.resultTable.querySelector("thead");
  const tbody = el.resultTable.querySelector("tbody");
  thead.innerHTML = `<tr>${columns.map((column) => `<th>${escapeHtml(labelForColumn(column))}</th>`).join("")}</tr>`;
  tbody.innerHTML = rows
    .map(
      (row) => `
        <tr>
          ${columns.map((column) => `<td>${escapeHtml(formatCell(row[column]))}</td>`).join("")}
        </tr>
      `,
    )
    .join("");
}

function renderTrace(steps) {
  el.traceList.innerHTML = steps
    .map(
      (step, index) => `
        <li>
          <span class="trace-index">${index + 1}</span>
          <div>
            <div class="trace-title">${escapeHtml(labelForStep(step.name))} · ${escapeHtml(labelForStatus(step.status))}</div>
            <div class="trace-detail">${escapeHtml(step.detail || "")}</div>
          </div>
        </li>
      `,
    )
    .join("");
}

function renderChart(chartOption, rows) {
  if (state.chart) {
    state.chart.dispose();
    state.chart = null;
  }

  el.chartHost.innerHTML = "";
  el.chartHost.classList.remove("empty-chart");

  if (!rows.length || chartOption?.type === "empty") {
    el.chartHost.classList.add("empty-chart");
    el.chartHost.innerHTML = '<div class="empty-state">暂无图表</div>';
    return;
  }

  const localizedOption = localizeChartOption(chartOption);

  if (window.echarts && localizedOption?.series) {
    const chartNode = document.createElement("div");
    chartNode.className = "chart-canvas";
    el.chartHost.appendChild(chartNode);
    state.chart = window.echarts.init(chartNode);
    state.chart.setOption(localizedOption, true);
    return;
  }

  renderFallbackChart(localizedOption);
}

function localizeChartOption(chartOption) {
  if (!chartOption) {
    return chartOption;
  }
  const option = JSON.parse(JSON.stringify(chartOption));
  if (Array.isArray(option.xAxis?.data)) {
    option.xAxis.data = option.xAxis.data.map((value) => valueLabels[value] || value);
  }
  if (Array.isArray(option.series)) {
    option.series = option.series.map((series) => {
      if (!Array.isArray(series.data)) {
        return series;
      }
      return {
        ...series,
        data: series.data.map((item) => {
          if (typeof item === "object" && item !== null && "name" in item) {
            return { ...item, name: valueLabels[item.name] || item.name };
          }
          return item;
        }),
      };
    });
  }
  return option;
}

function renderFallbackChart(chartOption) {
  const series = chartOption?.series?.[0];
  const values = Array.isArray(series?.data) ? series.data : [];
  const normalized = values.map((item, index) => {
    if (typeof item === "number") {
      return { name: chartOption?.xAxis?.data?.[index] || `#${index + 1}`, value: item };
    }
    return { name: item.name, value: Number(item.value || 0) };
  });
  const max = Math.max(...normalized.map((item) => item.value), 1);

  el.chartHost.innerHTML = `
    <div class="fallback-chart">
      ${normalized
        .map(
          (item) => `
            <div class="fallback-bar" title="${escapeHtml(item.name)}: ${item.value}">
              <span style="height: ${Math.max(4, (item.value / max) * 100)}%"></span>
              <span>${escapeHtml(item.name)}</span>
            </div>
          `,
        )
        .join("")}
    </div>
  `;
}

function switchTab(tabName) {
  el.tabs.forEach((tab) => tab.classList.toggle("active", tab.dataset.tab === tabName));
  el.tabPanels.forEach((panel) => panel.classList.toggle("active", panel.id === `${tabName}Panel`));
  if (tabName === "chart" && state.chart) {
    setTimeout(() => state.chart.resize(), 0);
  }
}

async function copySql() {
  const sql = el.sqlBlock.textContent;
  if (!sql || sql.startsWith("--")) {
    return;
  }
  await navigator.clipboard.writeText(sql);
  el.copySqlButton.innerHTML = '<svg><use href="#icon-check"></use></svg>';
  setTimeout(() => {
    el.copySqlButton.innerHTML = '<svg><use href="#icon-copy"></use></svg>';
  }, 1200);
}

function formatCell(value) {
  if (value === null || value === undefined) {
    return "";
  }
  if (typeof value === "number") {
    return Number.isInteger(value) ? String(value) : value.toFixed(2);
  }
  return valueLabels[String(value)] || String(value);
}

function labelForColumn(column) {
  return columnLabels[column] || column;
}

function labelForStep(step) {
  const labels = {
    schema: "读取数据结构",
    generate_sql: "生成 SQL",
    execute_sql: "执行查询",
    chart: "生成图表",
    insight: "生成结论",
  };
  return labels[step] || step;
}

function labelForStatus(status) {
  const labels = {
    ok: "成功",
    failed: "失败",
  };
  return labels[status] || status;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

function bindEvents() {
  el.runButton.addEventListener("click", runAnalysis);
  el.refreshExamplesButton.addEventListener("click", loadExamples);
  el.loadSchemaButton.addEventListener("click", loadSchema);
  el.copySqlButton.addEventListener("click", copySql);
  el.exampleList.addEventListener("click", (event) => {
    const button = event.target.closest(".example-button");
    if (!button) {
      return;
    }
    const example = state.examples[Number(button.dataset.index)];
    if (example) {
      el.questionInput.value = example.question;
      el.questionInput.focus();
    }
  });
  el.tabs.forEach((tab) => {
    tab.addEventListener("click", () => switchTab(tab.dataset.tab));
  });
  window.addEventListener("resize", () => {
    if (state.chart) {
      state.chart.resize();
    }
  });
}

bindEvents();
checkHealth();
loadExamples();
