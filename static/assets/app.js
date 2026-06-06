const state = {
  examples: [],
  lastResponse: null,
  chart: null,
  typeTimer: null,
  processTimer: null,
  processOpen: false,
  currentSql: "-- SQL will appear here",
  evaluationReport: null,
  evaluationFilter: "all",
  evaluationLoaded: false,
  files: {
    schema: [],
    rag: [],
  },
};

const pendingProcessSteps = [
  { name: "understand", title: "理解问题", detail: "识别用户想要分析的业务对象和指标。" },
  { name: "schema", title: "读取数据结构", detail: "读取 MySQL 示例库中的表、字段和关系。" },
  { name: "metric_retrieval", title: "检索指标口径", detail: "查找 GMV、销售额、客单价等业务定义。" },
  { name: "generate_sql", title: "生成 SQL", detail: "结合 schema 和指标口径生成只读查询。" },
  { name: "execute_sql", title: "执行查询", detail: "校验 SQL 安全性并返回结果数据。" },
  { name: "chart", title: "生成图表", detail: "根据字段类型推荐可视化配置。" },
  { name: "insight", title: "生成结论", detail: "基于查询结果生成简短业务分析。" },
];

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

const fileManagers = {
  schema: {
    endpoint: "/api/files/schema",
    input: "#schemaFileInput",
    uploadZone: "#schemaUploadZone",
    table: "#schemaFileTable",
    count: "#schemaFileCount",
    state: "#schemaUploadState",
    previewTitle: "#schemaPreviewTitle",
    previewBlock: "#schemaPreviewBlock",
    defaultPreview: "选择左侧文件后查看内容。",
    emptyTitle: "还没有结构资料",
    emptyDescription: "上传数据字典、建表 SQL 或字段说明后，这里会展示可管理的结构文件。",
  },
  rag: {
    endpoint: "/api/files/rag",
    input: "#ragFileInput",
    uploadZone: "#ragUploadZone",
    table: "#ragFileTable",
    count: "#ragFileCount",
    state: "#ragUploadState",
    previewTitle: "#ragPreviewTitle",
    previewBlock: "#ragPreviewBlock",
    defaultPreview: "选择左侧文件后查看内容。",
    emptyTitle: "还没有知识库资料",
    emptyDescription: "上传业务口径、FAQ 或分析规则后，这里会展示可用于检索增强的资料。",
  },
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
  followupPanel: document.querySelector("#followupPanel"),
  followupToggle: document.querySelector("#followupToggle"),
  followupList: document.querySelector("#followupList"),
  processPanel: document.querySelector("#processPanel"),
  processSummary: document.querySelector("#processSummary"),
  processTimeline: document.querySelector("#processTimeline"),
  toggleProcessButton: document.querySelector("#toggleProcessButton"),
  chartHost: document.querySelector("#chartHost"),
  chartInteraction: document.querySelector("#chartInteraction"),
  resultTable: document.querySelector("#resultTable"),
  sqlBlock: document.querySelector("#sqlBlock"),
  sqlLineNumbers: document.querySelector("#sqlLineNumbers"),
  sqlMeta: document.querySelector("#sqlMeta"),
  formatSqlButton: document.querySelector("#formatSqlButton"),
  downloadSqlButton: document.querySelector("#downloadSqlButton"),
  copySqlButton: document.querySelector("#copySqlButton"),
  tabs: document.querySelectorAll(".tab"),
  tabPanels: document.querySelectorAll(".tab-panel"),
  navItems: document.querySelectorAll(".nav-item"),
  viewPanels: document.querySelectorAll(".view-panel"),
  refreshSchemaFilesButton: document.querySelector("#refreshSchemaFilesButton"),
  refreshRagFilesButton: document.querySelector("#refreshRagFilesButton"),
  runEvaluationButton: document.querySelector("#runEvaluationButton"),
  evaluationRunMeta: document.querySelector("#evaluationRunMeta"),
  evaluationState: document.querySelector("#evaluationState"),
  evaluationKpis: document.querySelector("#evaluationKpis"),
  evaluationSuites: document.querySelector("#evaluationSuites"),
  evaluationVersionBody: document.querySelector("#evaluationVersionBody"),
  evaluationFilters: document.querySelector("#evaluationFilters"),
  evaluationCaseList: document.querySelector("#evaluationCaseList"),
};

function setRunState(label, kind = "idle") {
  el.runState.textContent = label;
  el.runState.className = `state-label ${kind}`;
}

function setHealth(label, kind = "") {
  el.healthStatus.textContent = label;
  el.healthStatus.className = `status-pill ${kind}`;
}

function setFileState(category, label, kind = "") {
  const config = fileManagers[category];
  const node = document.querySelector(config.state);
  const zone = document.querySelector(config.uploadZone);
  node.textContent = label;
  node.className = `muted-text ${kind}`;
  zone.classList.toggle("is-busy", label.includes("中"));
  zone.classList.toggle("has-error", kind === "error");
  zone.classList.toggle("is-ok", kind === "ok");
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
  resetAnalysisResult(question);
  startPendingProcess();

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
    renderProcessTimeline(
      pendingProcessSteps.map((step) => ({ ...step, status: step.name === "understand" ? "failed" : "pending" })),
    );
  } finally {
    stopPendingProcess();
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
  setSqlContent(data.generated_sql || "-- SQL unavailable");

  renderWarnings(data.warnings || []);
  renderTable(data.columns, data.rows);
  renderProcessTimeline(normalizeTraceSteps(data.trace_steps || []));
  renderChart(data.chart, data.rows);
  typeInsight(data.insight || "暂无分析结论。");
  renderFollowups(generateFollowupQuestions(data));
}

function resetAnalysisResult(question) {
  clearTypewriter();
  el.metricRows.textContent = "0";
  el.metricColumns.textContent = "0";
  el.metricChart.textContent = "-";
  el.metricTrace.textContent = "0";
  el.activeQuestion.textContent = question;
  el.insightText.textContent = "正在分析，请稍候";
  el.insightText.classList.add("streaming");
  el.warningList.innerHTML = "";
  el.followupPanel.hidden = true;
  el.followupToggle.hidden = true;
  setFollowupsOpen(false);
  el.followupList.innerHTML = "";
  setSqlContent("-- SQL will appear here");
  setProcessOpen(false);
  renderTable([], []);
  renderChartSkeleton();
}

function startPendingProcess() {
  let activeIndex = 0;
  renderProcessTimeline(
    pendingProcessSteps.map((step, index) => ({
      ...step,
      status: index === 0 ? "active" : "pending",
    })),
  );
  clearInterval(state.processTimer);
  state.processTimer = setInterval(() => {
    activeIndex = Math.min(activeIndex + 1, pendingProcessSteps.length - 1);
    renderProcessTimeline(
      pendingProcessSteps.map((step, index) => ({
        ...step,
        status: index < activeIndex ? "ok" : index === activeIndex ? "active" : "pending",
      })),
    );
  }, 900);
}

function stopPendingProcess() {
  clearInterval(state.processTimer);
  state.processTimer = null;
}

function renderWarnings(warnings) {
  el.warningList.innerHTML = warnings
    .map((warning) => `<div class="warning-item">${escapeHtml(warning)}</div>`)
    .join("");
}

function renderTable(columns, rows) {
  const thead = el.resultTable.querySelector("thead");
  const tbody = el.resultTable.querySelector("tbody");
  if (!columns.length) {
    thead.innerHTML = "";
    tbody.innerHTML = `<tr><td><div class="inline-empty">暂无数据</div></td></tr>`;
    return;
  }
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

function renderProcessTimeline(steps) {
  updateProcessSummary(steps);
  if (!steps.length) {
    el.processTimeline.innerHTML = '<li class="timeline-empty">暂无执行过程</li>';
    return;
  }
  el.processTimeline.innerHTML = steps
    .map((step, index) => {
      const detail = step.detail || "暂无更多细节。";
      const expanded = false;
      return `
        <li class="timeline-item ${escapeHtml(step.status || "pending")}">
          <button class="timeline-head" type="button" aria-expanded="${expanded ? "true" : "false"}">
            <span class="timeline-dot">${index + 1}</span>
            <span class="timeline-title">${escapeHtml(step.title || labelForStep(step.name))}</span>
            <span class="timeline-status">${escapeHtml(labelForStatus(step.status || "pending"))}</span>
            <svg><use href="#icon-chevron"></use></svg>
          </button>
          <div class="timeline-detail" ${expanded ? "" : "hidden"}>${escapeHtml(detail)}</div>
        </li>
      `;
    })
    .join("");
}

function updateProcessSummary(steps) {
  if (!steps.length) {
    el.processSummary.textContent = "从理解问题到生成结果的完整链路，运行后会显示当前进度。";
    el.processSummary.className = "process-summary";
    return;
  }

  const failedStep = steps.find((step) => step.status === "failed");
  if (failedStep) {
    el.processSummary.textContent = `执行到「${failedStep.title || labelForStep(failedStep.name)}」时失败，可展开查看具体原因。`;
    el.processSummary.className = "process-summary failed";
    return;
  }

  const activeStep = steps.find((step) => step.status === "active");
  if (activeStep) {
    const okCount = steps.filter((step) => step.status === "ok").length;
    el.processSummary.textContent = `正在处理：${activeStep.title || labelForStep(activeStep.name)}，已完成 ${okCount}/${steps.length} 步。`;
    el.processSummary.className = "process-summary working";
    return;
  }

  const okCount = steps.filter((step) => step.status === "ok").length;
  el.processSummary.textContent = `已完成 ${okCount}/${steps.length} 个步骤，点击“查看过程”可以展开完整链路。`;
  el.processSummary.className = "process-summary ok";
}

function normalizeTraceSteps(steps) {
  return steps.map((step) => ({
    name: step.name,
    title: labelForStep(step.name),
    status: step.status,
    detail: step.detail || "该步骤已完成。",
  }));
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
    el.chartInteraction.textContent = "暂无可交互数据。";
    return;
  }

  const localizedOption = localizeChartOption(chartOption);

  if (window.echarts && localizedOption?.series) {
    const chartNode = document.createElement("div");
    chartNode.className = "chart-canvas";
    el.chartHost.appendChild(chartNode);
    state.chart = window.echarts.init(chartNode);
    state.chart.setOption(enhanceChartOption(localizedOption), true);
    state.chart.on("click", handleChartClick);
    el.chartInteraction.textContent = "可悬停查看数据，点击图表元素查看明细。";
    return;
  }

  renderFallbackChart(localizedOption);
}

function renderChartSkeleton() {
  if (state.chart) {
    state.chart.dispose();
    state.chart = null;
  }
  el.chartHost.classList.add("empty-chart");
  el.chartHost.innerHTML = `
    <div class="chart-skeleton">
      <span></span><span></span><span></span><span></span><span></span>
    </div>
  `;
  el.chartInteraction.textContent = "正在准备图表区域。";
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

function enhanceChartOption(option) {
  const enhanced = JSON.parse(JSON.stringify(option || {}));
  enhanced.animationDuration = 520;
  enhanced.animationEasing = "cubicOut";
  enhanced.tooltip = {
    trigger: enhanced.xAxis ? "axis" : "item",
    confine: true,
    ...enhanced.tooltip,
  };
  const toolboxFeature = {
    restore: {},
    saveAsImage: {},
  };
  if (enhanced.xAxis) {
    toolboxFeature.dataZoom = { yAxisIndex: "none" };
  }
  enhanced.toolbox = {
    right: 8,
    feature: toolboxFeature,
  };
  if (enhanced.xAxis && !enhanced.dataZoom) {
    enhanced.dataZoom = [
      { type: "inside", throttle: 50 },
      { type: "slider", height: 18, bottom: 6 },
    ];
    enhanced.grid = {
      ...(enhanced.grid || {}),
      bottom: 54,
      containLabel: true,
    };
  }
  return enhanced;
}

function handleChartClick(params) {
  const label = params.name || params.seriesName || "选中项";
  const value = Array.isArray(params.value) ? params.value.join(" / ") : params.value;
  el.chartInteraction.textContent = `已选中：${label}，数值：${formatCell(value)}。可以基于这个点继续追问。`;
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

function toggleTimelineItem(button) {
  const detail = button.parentElement.querySelector(".timeline-detail");
  const expanded = button.getAttribute("aria-expanded") === "true";
  button.setAttribute("aria-expanded", String(!expanded));
  detail.hidden = expanded;
}

function setProcessOpen(open) {
  state.processOpen = open;
  el.processPanel.classList.toggle("collapsed", !open);
  el.toggleProcessButton.querySelector("span").textContent = open ? "收起过程" : "查看过程";
}

function toggleProcessPanel() {
  setProcessOpen(!state.processOpen);
}

function switchView(viewId) {
  el.navItems.forEach((item) => item.classList.toggle("active", item.dataset.view === viewId));
  el.viewPanels.forEach((panel) => panel.classList.toggle("active", panel.id === viewId));
  if (viewId === "analysisView" && state.chart) {
    setTimeout(() => state.chart.resize(), 0);
  }
  if (viewId === "schemaView") {
    loadManagedFiles("schema");
  }
  if (viewId === "ragView") {
    loadManagedFiles("rag");
  }
  if (viewId === "evaluationView" && !state.evaluationLoaded) {
    runEvaluations();
  }
}

async function runEvaluations() {
  setEvaluationState("运行中", "idle");
  el.runEvaluationButton.disabled = true;
  el.runEvaluationButton.querySelector("span").textContent = "运行中";
  el.evaluationRunMeta.textContent = "正在执行内置评测套件";
  renderEvaluationLoading();
  try {
    const report = await fetchJson("/api/evaluations/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({}),
    });
    state.evaluationReport = report;
    state.evaluationLoaded = true;
    renderEvaluationReport(report);
    const failed = report.cases.filter((item) => item.status === "failed").length;
    setEvaluationState(failed ? "存在失败" : "全部通过", failed ? "warning" : "ok");
    el.evaluationRunMeta.textContent = `${formatDate(report.generated_at)} · ${report.duration_ms}ms`;
  } catch (error) {
    setEvaluationState("运行失败", "error");
    el.evaluationRunMeta.textContent = error.message;
    renderEvaluationError(error.message);
  } finally {
    el.runEvaluationButton.disabled = false;
    el.runEvaluationButton.querySelector("span").textContent = "运行评测";
  }
}

function setEvaluationState(label, kind = "idle") {
  el.evaluationState.textContent = label;
  el.evaluationState.className = `state-label ${kind}`;
}

function renderEvaluationLoading() {
  el.evaluationKpis.innerHTML = Array.from({ length: 5 })
    .map(
      () => `
        <div class="evaluation-kpi skeleton">
          <span></span>
          <strong></strong>
          <p></p>
        </div>
      `,
    )
    .join("");
  el.evaluationSuites.innerHTML = '<div class="inline-empty">正在运行评测套件</div>';
  el.evaluationVersionBody.innerHTML = "";
  el.evaluationCaseList.innerHTML = '<div class="inline-empty">等待评测结果</div>';
}

function renderEvaluationError(message) {
  el.evaluationKpis.innerHTML = "";
  el.evaluationSuites.innerHTML = "";
  el.evaluationVersionBody.innerHTML = "";
  el.evaluationCaseList.innerHTML = `<div class="manager-empty"><strong>评测运行失败</strong><p>${escapeHtml(message)}</p></div>`;
}

function renderEvaluationReport(report) {
  renderEvaluationKpis(report.kpis || []);
  renderEvaluationSuites(report.suites || []);
  renderEvaluationVersionSnapshots(report.version_snapshots || []);
  renderEvaluationCases();
}

function renderEvaluationKpis(kpis) {
  el.evaluationKpis.innerHTML = kpis
    .map(
      (kpi) => `
        <div class="evaluation-kpi ${escapeHtml(kpi.status || "idle")}">
          <span>${escapeHtml(kpi.label)}</span>
          <strong>${escapeHtml(kpi.value)}</strong>
          <p>${escapeHtml(kpi.description)}</p>
        </div>
      `,
    )
    .join("");
}

function renderEvaluationSuites(suites) {
  if (!suites.length) {
    el.evaluationSuites.innerHTML = '<div class="inline-empty">暂无评测套件</div>';
    return;
  }
  el.evaluationSuites.innerHTML = suites
    .map(
      (suite) => `
        <article class="evaluation-suite ${escapeHtml(suite.status)}">
          <div>
            <strong>${escapeHtml(suite.name)}</strong>
            <p>${escapeHtml(suite.description)}</p>
          </div>
          <div class="suite-score">
            <span>${formatPercent(suite.pass_rate)}</span>
            <small>${suite.passed}/${suite.total} 通过 · ${suite.duration_ms}ms</small>
          </div>
        </article>
      `,
    )
    .join("");
}

function renderEvaluationVersionSnapshots(snapshots) {
  if (!snapshots.length) {
    el.evaluationVersionBody.innerHTML = `<tr><td colspan="6"><div class="inline-empty">暂无版本快照</div></td></tr>`;
    return;
  }
  el.evaluationVersionBody.innerHTML = snapshots
    .map(
      (item) => `
        <tr>
          <td><strong>${escapeHtml(item.version)}</strong></td>
          <td>${formatPercent(item.overall_pass_rate)}</td>
          <td>${formatPercent(item.sql_executable_rate)}</td>
          <td>${formatPercent(item.safety_pass_rate)}</td>
          <td>${formatPercent(item.retrieval_pass_rate)}</td>
          <td>${escapeHtml(item.avg_latency_ms)}ms</td>
        </tr>
      `,
    )
    .join("");
}

function renderEvaluationCases() {
  const report = state.evaluationReport;
  if (!report) {
    el.evaluationCaseList.innerHTML = '<div class="inline-empty">运行评测后查看明细</div>';
    return;
  }
  const cases = report.cases.filter((item) => {
    if (state.evaluationFilter === "all") {
      return true;
    }
    return item.status === state.evaluationFilter;
  });
  if (!cases.length) {
    el.evaluationCaseList.innerHTML = '<div class="inline-empty">当前筛选条件下没有用例</div>';
    return;
  }
  el.evaluationCaseList.innerHTML = cases
    .map(
      (item) => `
        <details class="evaluation-case ${escapeHtml(item.status)}">
          <summary>
            <span class="case-status">${escapeHtml(labelForEvalStatus(item.status))}</span>
            <span class="case-main">
              <strong>${escapeHtml(item.title)}</strong>
              <small>${escapeHtml(item.suite_name)} · ${escapeHtml((item.tags || []).join(" / ") || "baseline")}</small>
            </span>
          </summary>
          <div class="case-detail-grid">
            <div>
              <span>期望</span>
              <p>${escapeHtml(item.expected || "-")}</p>
            </div>
            <div>
              <span>实际</span>
              <p>${escapeHtml(item.actual || "-")}</p>
            </div>
            <div>
              <span>错误原因</span>
              <p>${escapeHtml((item.errors || []).join("；") || "无")}</p>
            </div>
            ${
              item.generated_sql
                ? `<pre>${escapeHtml(item.generated_sql)}</pre>`
                : ""
            }
          </div>
        </details>
      `,
    )
    .join("");
}

function labelForEvalStatus(status) {
  return status === "passed" ? "通过" : "失败";
}

function formatPercent(value) {
  return `${Math.round(Number(value || 0) * 1000) / 10}%`;
}

async function loadManagedFiles(category) {
  const config = fileManagers[category];
  setFileState(category, "读取中");
  try {
    const data = await fetchJson(config.endpoint);
    state.files[category] = data.files || [];
    renderManagedFiles(category);
    setFileState(category, "已同步", "ok");
  } catch (error) {
    setFileState(category, error.message, "error");
  }
}

function renderManagedFiles(category) {
  const config = fileManagers[category];
  const files = state.files[category] || [];
  document.querySelector(config.count).textContent = `${files.length} 个文件`;
  const table = document.querySelector(config.table);
  if (!files.length) {
    table.innerHTML = `
      <tr class="empty-row">
        <td colspan="5">
          <div class="manager-empty">
            <div class="manager-empty-icon">
              <svg><use href="#icon-file-text"></use></svg>
            </div>
            <strong>${escapeHtml(config.emptyTitle)}</strong>
            <p>${escapeHtml(config.emptyDescription)}</p>
          </div>
        </td>
      </tr>
    `;
    return;
  }

  table.innerHTML = files
    .map(
      (file) => `
        <tr>
          <td><div class="file-name-cell" title="${escapeHtml(file.name)}">${escapeHtml(file.name)}</div></td>
          <td><span class="file-type-badge">${escapeHtml((file.extension || "-").toUpperCase())}</span></td>
          <td>${escapeHtml(formatBytes(file.size_bytes))}</td>
          <td>${escapeHtml(formatDate(file.uploaded_at))}</td>
          <td>
            <div class="file-actions">
              <button class="icon-button" type="button" data-action="preview" data-id="${escapeHtml(file.id)}" title="预览">
                <svg><use href="#icon-eye"></use></svg>
              </button>
              <button class="danger-button icon-only" type="button" data-action="delete" data-id="${escapeHtml(file.id)}" title="删除">
                <svg><use href="#icon-trash"></use></svg>
              </button>
            </div>
          </td>
        </tr>
      `,
    )
    .join("");
}

async function uploadManagedFile(category, file) {
  if (!file) {
    return;
  }
  const config = fileManagers[category];
  const formData = new FormData();
  formData.append("file", file);
  setFileState(category, "上传中");
  try {
    await fetchJson(config.endpoint, {
      method: "POST",
      body: formData,
    });
    setFileState(category, "上传完成", "ok");
    await loadManagedFiles(category);
  } catch (error) {
    setFileState(category, error.message, "error");
  } finally {
    document.querySelector(config.input).value = "";
    document.querySelector(config.uploadZone).classList.remove("is-dragging");
  }
}

async function previewManagedFile(category, fileId) {
  const config = fileManagers[category];
  const title = document.querySelector(config.previewTitle);
  const block = document.querySelector(config.previewBlock);
  title.textContent = "读取中";
  block.textContent = "读取中";
  block.classList.remove("empty", "error");
  try {
    const data = await fetchJson(`${config.endpoint}/${fileId}/preview`);
    title.textContent = data.name;
    block.textContent = data.previewable ? data.preview : "该文件类型暂不支持文本预览。";
    block.classList.toggle("empty", !data.previewable);
  } catch (error) {
    title.textContent = "预览失败";
    block.textContent = error.message;
    block.classList.add("error");
  }
}

async function deleteManagedFile(category, fileId) {
  const confirmed = window.confirm("确认删除这个文件吗？");
  if (!confirmed) {
    return;
  }
  const config = fileManagers[category];
  setFileState(category, "删除中");
  try {
    await fetchJson(`${config.endpoint}/${fileId}`, { method: "DELETE" });
    resetPreview(category);
    await loadManagedFiles(category);
    setFileState(category, "已删除", "ok");
  } catch (error) {
    setFileState(category, error.message, "error");
  }
}

function resetPreview(category) {
  const config = fileManagers[category];
  document.querySelector(config.previewTitle).textContent = "未选择文件";
  const block = document.querySelector(config.previewBlock);
  block.textContent = config.defaultPreview;
  block.classList.add("empty");
  block.classList.remove("error");
}

function bindUploadZone(category) {
  const config = fileManagers[category];
  const zone = document.querySelector(config.uploadZone);
  const input = document.querySelector(config.input);

  zone.addEventListener("dragenter", (event) => {
    event.preventDefault();
    zone.classList.add("is-dragging");
  });
  zone.addEventListener("dragover", (event) => {
    event.preventDefault();
    zone.classList.add("is-dragging");
  });
  zone.addEventListener("dragleave", (event) => {
    if (!zone.contains(event.relatedTarget)) {
      zone.classList.remove("is-dragging");
    }
  });
  zone.addEventListener("drop", (event) => {
    event.preventDefault();
    zone.classList.remove("is-dragging");
    uploadManagedFile(category, event.dataTransfer?.files?.[0]);
  });
  input.addEventListener("change", (event) => {
    uploadManagedFile(category, event.target.files[0]);
  });
}

async function copySql() {
  const sql = state.currentSql;
  if (isPlaceholderSql(sql)) {
    return;
  }
  await navigator.clipboard.writeText(sql);
  el.copySqlButton.innerHTML = '<svg><use href="#icon-check"></use></svg>';
  setTimeout(() => {
    el.copySqlButton.innerHTML = '<svg><use href="#icon-copy"></use></svg>';
  }, 1200);
}

function setSqlContent(sql) {
  state.currentSql = sql || "-- SQL unavailable";
  const lines = state.currentSql.split(/\r?\n/);
  el.sqlBlock.innerHTML = highlightSql(state.currentSql);
  el.sqlLineNumbers.textContent = lines.map((_, index) => index + 1).join("\n");
  el.sqlMeta.textContent = `${lines.length} 行 · ${isPlaceholderSql(state.currentSql) ? "等待生成" : "只读查询"}`;
}

function formatCurrentSql() {
  if (isPlaceholderSql(state.currentSql)) {
    return;
  }
  setSqlContent(formatSqlText(state.currentSql));
}

function downloadSql() {
  if (isPlaceholderSql(state.currentSql)) {
    return;
  }
  const blob = new Blob([state.currentSql], { type: "text/sql;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = `datawhisperer-query-${new Date().toISOString().slice(0, 19).replaceAll(":", "-")}.sql`;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function isPlaceholderSql(sql) {
  return !sql || sql.trim().startsWith("-- SQL");
}

function formatSqlText(sql) {
  const stringLiterals = [];
  const protectedSql = sql.replace(/'(?:''|[^'])*'/g, (literal) => {
    const key = `__SQL_STRING_${stringLiterals.length}__`;
    stringLiterals.push(literal);
    return key;
  });
  const compact = protectedSql.trim().replace(/\s+/g, " ");
  const clausePattern =
    /\b(SELECT|FROM|WHERE|GROUP BY|ORDER BY|HAVING|LIMIT|INNER JOIN|LEFT JOIN|RIGHT JOIN|JOIN|ON|AND|OR)\b/gi;
  const formatted = compact
    .replace(clausePattern, (match) => `\n${match.toUpperCase()}`)
    .replace(/,\s*/g, ",\n  ")
    .replace(/^\n/, "")
    .replace(/\n(AND|OR)\b/g, "\n  $1");
  return formatted.replace(/__SQL_STRING_(\d+)__/g, (_, index) => stringLiterals[Number(index)]);
}

function highlightSql(sql) {
  const keywords = new Set([
    "SELECT",
    "FROM",
    "WHERE",
    "JOIN",
    "INNER",
    "LEFT",
    "RIGHT",
    "FULL",
    "OUTER",
    "ON",
    "AND",
    "OR",
    "GROUP",
    "BY",
    "ORDER",
    "HAVING",
    "LIMIT",
    "AS",
    "DESC",
    "ASC",
    "DISTINCT",
    "CASE",
    "WHEN",
    "THEN",
    "ELSE",
    "END",
    "INTERVAL",
  ]);
  const functions = new Set([
    "COUNT",
    "SUM",
    "AVG",
    "MIN",
    "MAX",
    "ROUND",
    "DATE_FORMAT",
    "DATE_SUB",
    "CURRENT_DATE",
    "NOW",
    "YEAR",
    "MONTH",
    "CONCAT",
    "CAST",
    "COALESCE",
    "IFNULL",
    "NULLIF",
  ]);
  const tokenPattern =
    /(--[^\n]*|'(?:''|[^'])*'|`[^`]*`|\b\d+(?:\.\d+)?\b|\b[A-Za-z_][A-Za-z0-9_]*\b|[(),.*=<>+\-/])/g;
  let cursor = 0;
  let html = "";
  for (const match of sql.matchAll(tokenPattern)) {
    const token = match[0];
    html += escapeHtml(sql.slice(cursor, match.index));
    html += renderSqlToken(token, keywords, functions);
    cursor = match.index + token.length;
  }
  html += escapeHtml(sql.slice(cursor));
  return html;
}

function renderSqlToken(token, keywords, functions) {
  const upper = token.toUpperCase();
  if (token.startsWith("--")) {
    return `<span class="sql-comment">${escapeHtml(token)}</span>`;
  }
  if (token.startsWith("'")) {
    return `<span class="sql-string">${escapeHtml(token)}</span>`;
  }
  if (token.startsWith("`")) {
    return `<span class="sql-identifier">${escapeHtml(token)}</span>`;
  }
  if (/^\d/.test(token)) {
    return `<span class="sql-number">${escapeHtml(token)}</span>`;
  }
  if (functions.has(upper)) {
    return `<span class="sql-function">${escapeHtml(token)}</span>`;
  }
  if (keywords.has(upper)) {
    return `<span class="sql-keyword">${escapeHtml(token)}</span>`;
  }
  if (/^[(),.*=<>+\-/]$/.test(token)) {
    return `<span class="sql-operator">${escapeHtml(token)}</span>`;
  }
  return `<span class="sql-name">${escapeHtml(token)}</span>`;
}

function typeInsight(text) {
  clearTypewriter();
  el.insightText.textContent = "";
  el.insightText.classList.add("streaming");
  let index = 0;
  state.typeTimer = setInterval(() => {
    const chunk = text.slice(index, index + 2);
    el.insightText.textContent += chunk;
    el.insightText.scrollTop = el.insightText.scrollHeight;
    index += 2;
    if (index >= text.length) {
      clearTypewriter();
      el.insightText.classList.remove("streaming");
    }
  }, 18);
}

function clearTypewriter() {
  clearInterval(state.typeTimer);
  state.typeTimer = null;
}

function generateFollowupQuestions(data) {
  const question = data.question || "本次分析";
  const columns = new Set(data.columns || []);
  const chartType = data.chart?.type;
  const suggestions = [];

  if (columns.has("region_name")) {
    suggestions.push("按地区继续拆分到商品品类看差异。");
  }
  if (columns.has("product_name") || columns.has("category")) {
    suggestions.push("找出贡献最高和最低的商品，并解释原因。");
  }
  if (columns.has("month") || chartType === "line") {
    suggestions.push("对最近 6 个月趋势做环比变化分析。");
  }
  if (columns.has("sales_amount") || columns.has("amount_change")) {
    suggestions.push("把销售额变化最大的对象单独列出来。");
  }
  if (columns.has("avg_order_value")) {
    suggestions.push("比较不同地区客单价差异，并给出可能原因。");
  }
  suggestions.push(`基于“${question}”继续给出下一步经营建议。`);
  suggestions.push("把本次结果按销售额从高到低重新排序。");
  suggestions.push("找出异常值，并说明可能的业务原因。");

  return [...new Set(suggestions)].slice(0, 5);
}

function renderFollowups(suggestions) {
  if (!suggestions.length) {
    el.followupPanel.hidden = true;
    el.followupToggle.hidden = true;
    setFollowupsOpen(false);
    return;
  }
  el.followupPanel.hidden = false;
  el.followupToggle.hidden = false;
  setFollowupsOpen(false);
  el.followupToggle.querySelector("span").textContent = `${suggestions.length} 个追问`;
  el.followupList.innerHTML = suggestions
    .map(
      (question) => `
        <button class="followup-chip" type="button" data-question="${escapeHtml(question)}">
          ${escapeHtml(question)}
        </button>
      `,
    )
    .join("");
}

function setFollowupsOpen(open) {
  el.followupPanel.classList.toggle("open", open);
  el.followupToggle?.setAttribute("aria-expanded", String(open));
}

function toggleFollowups() {
  const open = el.followupPanel.classList.contains("open");
  setFollowupsOpen(!open);
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

function formatBytes(value) {
  if (value < 1024) {
    return `${value} B`;
  }
  if (value < 1024 * 1024) {
    return `${(value / 1024).toFixed(1)} KB`;
  }
  return `${(value / 1024 / 1024).toFixed(1)} MB`;
}

function formatDate(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "-";
  }
  return date.toLocaleString("zh-CN", {
    hour12: false,
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  });
}

function labelForColumn(column) {
  return columnLabels[column] || column;
}

function labelForStep(step) {
  const labels = {
    schema: "读取数据结构",
    metric_retrieval: "检索指标口径",
    generate_sql: "生成 SQL",
    sql_repair: "修复 SQL",
    execute_sql: "执行查询",
    chart: "生成图表",
    insight: "生成结论",
  };
  return labels[step] || step;
}

function labelForStatus(status) {
  const labels = {
    active: "进行中",
    pending: "等待",
    ok: "成功",
    failed: "失败",
    retry: "重试",
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
  el.formatSqlButton.addEventListener("click", formatCurrentSql);
  el.downloadSqlButton.addEventListener("click", downloadSql);
  el.copySqlButton.addEventListener("click", copySql);
  el.toggleProcessButton.addEventListener("click", toggleProcessPanel);
  el.followupToggle.addEventListener("click", toggleFollowups);
  el.processTimeline.addEventListener("click", (event) => {
    const button = event.target.closest(".timeline-head");
    if (button) {
      toggleTimelineItem(button);
    }
  });
  el.followupList.addEventListener("click", (event) => {
    const button = event.target.closest(".followup-chip");
    if (!button) {
      return;
    }
    el.questionInput.value = button.dataset.question;
    switchView("analysisView");
    el.questionInput.focus();
  });
  el.refreshSchemaFilesButton.addEventListener("click", () => loadManagedFiles("schema"));
  el.refreshRagFilesButton.addEventListener("click", () => loadManagedFiles("rag"));
  el.runEvaluationButton.addEventListener("click", runEvaluations);
  el.evaluationFilters.addEventListener("click", (event) => {
    const button = event.target.closest("button[data-filter]");
    if (!button) {
      return;
    }
    state.evaluationFilter = button.dataset.filter;
    el.evaluationFilters
      .querySelectorAll("button")
      .forEach((item) => item.classList.toggle("active", item === button));
    renderEvaluationCases();
  });

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

  for (const category of Object.keys(fileManagers)) {
    const config = fileManagers[category];
    bindUploadZone(category);
    document.querySelector(config.table).addEventListener("click", (event) => {
      const button = event.target.closest("button[data-action]");
      if (!button) {
        return;
      }
      if (button.dataset.action === "preview") {
        previewManagedFile(category, button.dataset.id);
      }
      if (button.dataset.action === "delete") {
        deleteManagedFile(category, button.dataset.id);
      }
    });
  }

  el.tabs.forEach((tab) => {
    tab.addEventListener("click", () => switchTab(tab.dataset.tab));
  });
  el.navItems.forEach((item) => {
    item.addEventListener("click", () => switchView(item.dataset.view));
  });
  window.addEventListener("resize", () => {
    if (state.chart) {
      state.chart.resize();
    }
  });
}

bindEvents();
setSqlContent(state.currentSql);
checkHealth();
loadExamples();
renderProcessTimeline([]);
loadManagedFiles("schema");
loadManagedFiles("rag");
