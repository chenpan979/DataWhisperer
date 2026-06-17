const state = {
  examples: [],
  lastResponse: null,
  chart: null,
  typeTimer: null,
  processTimer: null,
  processOpen: false,
  currentSql: "-- SQL will appear here",
  evaluationTrendChart: null,
  evaluationReport: null,
  evaluationFilter: "all",
  evaluationLoaded: false,
  evaluationTab: "overview",
  files: {
    schema: [],
    rag: [],
    evaluation: [],
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
  evaluation: {
    endpoint: "/api/evaluations/datasets",
    input: "#evaluationDatasetFileInput",
    uploadZone: "#evaluationDatasetUploadZone",
    table: "#evaluationDatasetFileTable",
    count: "#evaluationDatasetFileCount",
    state: "#evaluationDatasetUploadState",
    previewTitle: "#evaluationDatasetPreviewTitle",
    previewBlock: "#evaluationDatasetPreviewBlock",
    defaultPreview: "选择左侧测试集后查看内容。",
    emptyTitle: "还没有上传测试集",
    emptyDescription: "上传 JSON、JSONL、CSV 或 YAML 测试集后，这里会展示可管理的评测资料。",
  },
};

const el = {
  healthStatus: document.querySelector("#healthStatus"),
  newConversationButton: document.querySelector("#newConversationButton"),
  clearConversationButton: document.querySelector("#clearConversationButton"),
  conversationList: document.querySelector("#conversationList"),
  chatTitle: document.querySelector("#chatTitle"),
  currentCondition: document.querySelector("#currentCondition"),
  resetContextButton: document.querySelector("#resetContextButton"),
  chatThread: document.querySelector("#chatThread"),
  userMessage: document.querySelector("#userMessage"),
  userQuestionText: document.querySelector("#userQuestionText"),
  userMessageTime: document.querySelector("#userMessageTime"),
  assistantResultMessage: document.querySelector("#assistantResultMessage"),
  assistantMessageTime: document.querySelector("#assistantMessageTime"),
  questionInput: document.querySelector("#questionInput"),
  maxRowsInput: document.querySelector("#maxRowsInput"),
  runButton: document.querySelector("#runButton"),
  refreshExamplesButton: document.querySelector("#refreshExamplesButton"),
  loadSchemaButton: document.querySelector("#loadSchemaButton"),
  sceneGrid: document.querySelector("#sceneGrid"),
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
  copyChartPngButton: document.querySelector("#copyChartPngButton"),
  downloadChartSvgButton: document.querySelector("#downloadChartSvgButton"),
  copyChartOptionButton: document.querySelector("#copyChartOptionButton"),
  copyTableHtmlButton: document.querySelector("#copyTableHtmlButton"),
  copyTableMarkdownButton: document.querySelector("#copyTableMarkdownButton"),
  downloadCsvButton: document.querySelector("#downloadCsvButton"),
  sqlBlock: document.querySelector("#sqlBlock"),
  sqlLineNumbers: document.querySelector("#sqlLineNumbers"),
  sqlMeta: document.querySelector("#sqlMeta"),
  sqlQuestionText: document.querySelector("#sqlQuestionText"),
  sqlExplanationText: document.querySelector("#sqlExplanationText"),
  sqlCheckList: document.querySelector("#sqlCheckList"),
  formatSqlButton: document.querySelector("#formatSqlButton"),
  downloadSqlButton: document.querySelector("#downloadSqlButton"),
  copySqlButton: document.querySelector("#copySqlButton"),
  tabs: document.querySelectorAll(".tab"),
  tabPanels: document.querySelectorAll(".tab-panel"),
  resultDetailButtons: document.querySelectorAll(".detail-toggle"),
  navItems: document.querySelectorAll(".nav-item"),
  viewPanels: document.querySelectorAll(".view-panel"),
  refreshSchemaFilesButton: document.querySelector("#refreshSchemaFilesButton"),
  refreshRagFilesButton: document.querySelector("#refreshRagFilesButton"),
  runEvaluationButton: document.querySelector("#runEvaluationButton"),
  evaluationRunMeta: document.querySelector("#evaluationRunMeta"),
  evaluationDatasetSelect: document.querySelector("#evaluationDatasetSelect"),
  evaluationDatasetPicker: document.querySelector("#evaluationDatasetPicker"),
  evaluationDatasetTrigger: document.querySelector("#evaluationDatasetTrigger"),
  evaluationDatasetLabel: document.querySelector("#evaluationDatasetLabel"),
  evaluationDatasetHint: document.querySelector("#evaluationDatasetHint"),
  evaluationDatasetMenu: document.querySelector("#evaluationDatasetMenu"),
  evaluationState: document.querySelector("#evaluationState"),
  evaluationKpis: document.querySelector("#evaluationKpis"),
  evaluationTabs: document.querySelector("#evaluationTabs"),
  evaluationTabPanels: document.querySelectorAll(".evaluation-tab-panel"),
  evaluationTrendChart: document.querySelector("#evaluationTrendChart"),
  evaluationIssueList: document.querySelector("#evaluationIssueList"),
  evaluationRecentRuns: document.querySelector("#evaluationRecentRuns"),
  evaluationSuites: document.querySelector("#evaluationSuites"),
  evaluationVersionBody: document.querySelector("#evaluationVersionBody"),
  evaluationFilters: document.querySelector("#evaluationFilters"),
  evaluationCaseList: document.querySelector("#evaluationCaseList"),
  evaluationModelBody: document.querySelector("#evaluationModelBody"),
  evaluationErrorList: document.querySelector("#evaluationErrorList"),
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
  el.schemaBox.classList.add("is-visible");
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
  showConversationQuestion(question);
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
    el.assistantResultMessage.classList.remove("is-loading");
    setRunState("失败", "error");
    el.insightText.textContent = error.message;
    renderProcessTimeline(
      pendingProcessSteps.map((step) => ({ ...step, status: step.name === "understand" ? "failed" : "pending" })),
    );
  } finally {
    stopPendingProcess();
    el.runButton.disabled = false;
    el.runButton.querySelector("span").textContent = "发送";
    scrollChatToBottom();
  }
}

function renderResponse(data) {
  el.assistantResultMessage.classList.remove("is-loading");
  el.metricRows.textContent = data.rows.length;
  el.metricColumns.textContent = data.columns.length;
  el.metricChart.textContent = chartTypeLabels[data.chart?.type] || data.chart?.type || "-";
  el.metricTrace.textContent = data.trace_steps.length;
  el.activeQuestion.textContent = data.question;
  setSqlContent(formatGeneratedSql(data.generated_sql || "-- SQL unavailable", data));
  renderSqlReview(data);

  renderWarnings(data.warnings || []);
  renderTable(data.columns, data.rows);
  renderProcessTimeline(normalizeTraceSteps(data.trace_steps || []));
  renderChart(data.chart, data.rows);
  typeInsight(data.insight || "暂无分析结论。");
  renderFollowups(generateFollowupQuestions(data));
  scrollChatToBottom();
}

function resetAnalysisResult(question) {
  el.assistantResultMessage.hidden = false;
  el.assistantResultMessage.classList.add("is-loading");
  el.assistantMessageTime.textContent = currentMessageTime();
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
  renderSqlReview({
    question,
    generated_sql: "",
    sql_explanation: "",
    trace_steps: [],
    rows: [],
    warnings: [],
  });
  setProcessOpen(false);
  closeResultDetails();
  renderTable([], []);
  renderChartSkeleton();
  scrollChatToBottom();
}

function showConversationQuestion(question) {
  el.userMessageTime.textContent = currentMessageTime();
  el.userMessage.hidden = false;
  el.userQuestionText.textContent = question;
  el.assistantResultMessage.hidden = false;
  updateConversationMeta(question);
  scrollChatToBottom();
}

function resetConversation() {
  clearTypewriter();
  stopPendingProcess();
  if (state.chart) {
    state.chart.dispose();
    state.chart = null;
  }
  state.lastResponse = null;
  el.questionInput.value = "";
  el.questionInput.style.height = "auto";
  el.userQuestionText.textContent = "";
  el.userMessageTime.textContent = "--:--";
  el.assistantMessageTime.textContent = "--:--";
  el.chatTitle.textContent = "新对话";
  el.currentCondition.textContent = "无";
  renderConversationList("新对话", "等待数据问题");
  el.userMessage.hidden = true;
  el.assistantResultMessage.hidden = true;
  el.metricRows.textContent = "0";
  el.metricColumns.textContent = "0";
  el.metricChart.textContent = "-";
  el.metricTrace.textContent = "0";
  el.activeQuestion.textContent = "等待问题输入";
  el.insightText.textContent = "运行一次分析后，这里会显示基于查询结果生成的业务结论。";
  el.insightText.classList.remove("streaming");
  el.warningList.innerHTML = "";
  el.followupPanel.hidden = true;
  el.followupToggle.hidden = true;
  el.followupList.innerHTML = "";
  setFollowupsOpen(false);
  el.schemaBox.classList.remove("is-visible");
  el.schemaBox.textContent = "未加载表结构。";
  setRunState("空闲", "idle");
  setProcessOpen(false);
  closeResultDetails();
  renderProcessTimeline([]);
  renderTable([], []);
  renderChart({ type: "empty" }, []);
  setSqlContent("-- SQL will appear here");
  renderSqlReview({
    question: "",
    generated_sql: "",
    sql_explanation: "",
    trace_steps: [],
    rows: [],
    warnings: [],
  });
  el.questionInput.focus();
  scrollChatToTop();
}

function updateConversationMeta(question) {
  const title = question.length > 18 ? `${question.slice(0, 18)}...` : question;
  el.chatTitle.textContent = title || "新对话";
  const condition = inferQuestionCondition(question);
  el.currentCondition.textContent = condition;
  renderConversationList(title || "新对话", condition === "无" ? "示例 MySQL 库" : condition);
}

function inferQuestionCondition(question) {
  const normalized = question.replace(/\s+/g, "");
  const conditions = [];
  if (/最近|近|上月|本月|季度|月份|月度|趋势/.test(normalized)) {
    conditions.push("时间范围");
  }
  if (/6个?月|六个?月/.test(normalized)) {
    conditions.push("最近6个月");
  }
  if (/地区|区域|华东|华北|华南|西部/.test(normalized)) {
    conditions.push("地区维度");
  }
  if (/商品|产品|品类|销量|销售额/.test(normalized)) {
    conditions.push("商品/销售口径");
  }
  if (/客单价|平均每单|订单均价/.test(normalized)) {
    conditions.push("客单价口径");
  }
  if (/GMV|销售额|金额/.test(question)) {
    conditions.push("金额指标");
  }
  return conditions.length ? Array.from(new Set(conditions)).join(" · ") : "无";
}

function renderConversationList(title = "新对话", subtitle = "等待数据问题") {
  if (!el.conversationList) {
    return;
  }
  el.conversationList.innerHTML = `
    <button class="conversation-item active" type="button">
      <strong>${escapeHtml(title)}</strong>
      <span>${escapeHtml(subtitle)}</span>
    </button>
    <button class="conversation-item" type="button" data-question="查询最近 6 个月每月销售额趋势">
      <strong>月度销售趋势分析</strong>
      <span>最近6个月 · 折线图</span>
    </button>
    <button class="conversation-item" type="button" data-question="查询各商品品类销售额占比">
      <strong>商品结构分析</strong>
      <span>品类占比 · 饼图</span>
    </button>
  `;
}

function hydrateConversationalCopy() {
  const welcomeTitle = document.querySelector("#analysisView .welcome-card h2");
  const welcomeIntro = document.querySelector("#analysisView .welcome-card > p");
  const quickTitle = document.querySelector("#analysisView .quick-title");
  const tabLabels = [
    ["chart", "图表"],
    ["table", "详细数据"],
    ["sql", "生成 SQL"],
  ];

  if (welcomeTitle) {
    welcomeTitle.textContent = "👋 你好，我是你的专属数据分析助手";
  }
  if (welcomeIntro) {
    welcomeIntro.textContent = "不用写 SQL，用大白话提问，我就能自动连接数据库、生成可视化图表、给出业务分析结论。";
  }
  if (quickTitle) {
    quickTitle.textContent = "快速开始分析：";
  }

  const sceneCards = [
    {
      question: "查询最近 6 个月每月销售额趋势",
      icon: "↗",
      title: "销售趋势分析",
      desc: "查看销售额变化与增长",
    },
    {
      question: "查询各商品品类销售额占比",
      icon: "▦",
      title: "商品结构分析",
      desc: "品类占比与销量排名",
    },
    {
      question: "哪个地区客单价最高",
      icon: "◎",
      title: "区域表现分析",
      desc: "地区客单价与订单表现",
    },
  ];

  document.querySelectorAll("#analysisView .scene-card").forEach((card, index) => {
    const config = sceneCards[index];
    if (!config) {
      return;
    }
    card.dataset.question = config.question;
    card.querySelector(".scene-icon").textContent = config.icon;
    card.querySelector("strong").textContent = config.title;
    card.querySelector("small").textContent = config.desc;
  });

  tabLabels.forEach(([tab, label]) => {
    const button = document.querySelector(`#analysisView .tab[data-tab="${tab}"]`);
    if (button) {
      button.textContent = label;
    }
  });
}

function scrollChatToBottom() {
  requestAnimationFrame(() => {
    if (el.chatThread) {
      el.chatThread.scrollTo({ top: el.chatThread.scrollHeight, behavior: "smooth" });
    }
  });
}

function scrollChatToTop() {
  requestAnimationFrame(() => {
    if (el.chatThread) {
      el.chatThread.scrollTo({ top: 0, behavior: "smooth" });
    }
  });
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
    resizeActiveChart();
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

function resizeActiveChart() {
  requestAnimationFrame(() => {
    if (state.chart) {
      state.chart.resize();
    }
    setTimeout(() => {
      if (state.chart) {
        state.chart.resize();
      }
    }, 80);
  });
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
  enhanced.backgroundColor = "#ffffff";
  enhanced.tooltip = {
    trigger: enhanced.xAxis ? "axis" : "item",
    confine: true,
    appendToBody: true,
    extraCssText:
      "max-width: 260px; min-width: 120px; width: auto; white-space: normal; line-height: 1.5; box-shadow: 0 10px 28px rgba(20,31,27,0.14);",
    ...enhanced.tooltip,
  };
  enhanced.toolbox = undefined;
  enhanced.dataZoom = undefined;
  if (enhanced.xAxis) {
    enhanced.grid = {
      left: 46,
      right: 28,
      top: 34,
      bottom: 44,
      ...(enhanced.grid || {}),
      containLabel: true,
    };
    enhanced.xAxis = {
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: "#718096", fontSize: 12 },
      splitLine: { show: false },
      ...enhanced.xAxis,
    };
    enhanced.yAxis = {
      axisLine: { show: false },
      axisTick: { show: false },
      axisLabel: { color: "#718096", fontSize: 12 },
      splitLine: { lineStyle: { color: "#edf2f7", type: "dashed" } },
      ...(enhanced.yAxis || {}),
    };
  }
  if (Array.isArray(enhanced.series)) {
    enhanced.series = enhanced.series.map((series) => {
      if (series.type === "line") {
        return {
          ...series,
          smooth: 0.38,
          symbol: "circle",
          symbolSize: 7,
          lineStyle: { color: "#0d9488", width: 3 },
          itemStyle: { color: "#0d9488", borderColor: "#ffffff", borderWidth: 2 },
          areaStyle: {
            color: {
              type: "linear",
              x: 0,
              y: 0,
              x2: 0,
              y2: 1,
              colorStops: [
                { offset: 0, color: "rgba(13, 148, 136, 0.18)" },
                { offset: 1, color: "rgba(13, 148, 136, 0.02)" },
              ],
            },
          },
        };
      }
      if (series.type === "bar") {
        return {
          ...series,
          barMaxWidth: 46,
          itemStyle: { color: "#0d9488", borderRadius: [7, 7, 0, 0] },
        };
      }
      return series;
    });
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

function setResultDetailOpen(targetName, open) {
  el.resultDetailButtons.forEach((button) => {
    const isTarget = button.dataset.detailTarget === targetName;
    button.classList.toggle("active", isTarget && open);
    button.setAttribute("aria-expanded", String(isTarget && open));
  });

  ["table", "sql"].forEach((name) => {
    const panel = document.querySelector(`#${name}Panel`);
    panel?.classList.toggle("active", name === targetName && open);
  });
}

function closeResultDetails() {
  setResultDetailOpen("table", false);
  setResultDetailOpen("sql", false);
}

function toggleResultDetail(targetName) {
  const button = Array.from(el.resultDetailButtons).find((item) => item.dataset.detailTarget === targetName);
  const shouldOpen = button?.getAttribute("aria-expanded") !== "true";
  setResultDetailOpen(targetName, shouldOpen);
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
  toggleEvaluationDatasetMenu(false);
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
  if (viewId === "datasetView") {
    loadManagedFiles("evaluation");
  }
  if (viewId === "evaluationView" && state.evaluationTrendChart) {
    setTimeout(() => state.evaluationTrendChart.resize(), 0);
  }
}

async function runEvaluations() {
  const datasetFileId = el.evaluationDatasetSelect?.value || "";
  const datasetName = selectedEvaluationDatasetName();
  setEvaluationState("运行中", "idle");
  el.runEvaluationButton.disabled = true;
  el.runEvaluationButton.querySelector("span").textContent = "运行中";
  el.evaluationRunMeta.textContent = datasetFileId
    ? `正在执行上传测试集：${datasetName}`
    : "正在执行内置评测套件";
  renderEvaluationLoading();
  try {
    const report = await fetchJson("/api/evaluations/run", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ dataset_file_id: datasetFileId || null }),
    });
    state.evaluationReport = report;
    state.evaluationLoaded = true;
    renderEvaluationReport(report);
    const failed = report.cases.filter((item) => item.status === "failed").length;
    setEvaluationState(failed ? "存在失败" : "全部通过", failed ? "warning" : "ok");
    el.evaluationRunMeta.textContent = `${report.dataset_name || datasetName} · ${formatDate(report.generated_at)} · ${report.duration_ms}ms`;
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
  el.evaluationTrendChart.innerHTML = '<div class="inline-empty">正在生成质量趋势</div>';
  el.evaluationIssueList.innerHTML = '<div class="inline-empty">正在统计问题分布</div>';
  el.evaluationRecentRuns.innerHTML = '<div class="inline-empty">正在读取最近任务</div>';
  el.evaluationSuites.innerHTML = '<div class="inline-empty">正在运行评测套件</div>';
  el.evaluationVersionBody.innerHTML = "";
  el.evaluationCaseList.innerHTML = '<div class="inline-empty">等待评测结果</div>';
  el.evaluationModelBody.innerHTML = "";
  el.evaluationErrorList.innerHTML = '<div class="inline-empty">等待错误案例</div>';
}

function renderEvaluationError(message) {
  el.evaluationKpis.innerHTML = "";
  el.evaluationTrendChart.innerHTML = "";
  el.evaluationIssueList.innerHTML = "";
  el.evaluationRecentRuns.innerHTML = "";
  el.evaluationSuites.innerHTML = "";
  el.evaluationVersionBody.innerHTML = "";
  el.evaluationModelBody.innerHTML = "";
  el.evaluationErrorList.innerHTML = "";
  el.evaluationCaseList.innerHTML = `<div class="manager-empty"><strong>评测运行失败</strong><p>${escapeHtml(message)}</p></div>`;
}

function renderEvaluationReport(report) {
  renderEvaluationKpis(report.kpis || []);
  renderEvaluationTrend(report.trend_points || []);
  renderEvaluationIssues(report.issue_distribution || []);
  renderEvaluationRecentRuns(report.recent_runs || []);
  renderEvaluationSuites(report.suites || []);
  renderEvaluationVersionSnapshots(report.version_snapshots || []);
  renderEvaluationModelComparisons(report.model_comparisons || []);
  renderEvaluationCases();
  renderEvaluationErrors();
}

function renderEvaluationKpis(kpis) {
  el.evaluationKpis.innerHTML = kpis
    .map(
      (kpi) => `
        <div class="evaluation-kpi ${escapeHtml(kpi.status || "idle")}">
          <div class="kpi-head">
            <span>${escapeHtml(kpi.label)}</span>
            <em>${escapeHtml(deltaForKpi(kpi.id))}</em>
          </div>
          <strong>${escapeHtml(kpi.value)}</strong>
          <p>${escapeHtml(kpi.description)}</p>
        </div>
      `,
    )
    .join("");
}

function renderEvaluationTrend(points) {
  if (state.evaluationTrendChart) {
    state.evaluationTrendChart.dispose();
    state.evaluationTrendChart = null;
  }
  if (!points.length) {
    el.evaluationTrendChart.innerHTML = '<div class="inline-empty">暂无趋势数据</div>';
    return;
  }
  if (!window.echarts) {
    el.evaluationTrendChart.innerHTML = points
      .map((item) => `<div class="inline-empty">${escapeHtml(item.version)} · ${formatPercent(item.overall_pass_rate)}</div>`)
      .join("");
    return;
  }
  el.evaluationTrendChart.innerHTML = "";
  state.evaluationTrendChart = window.echarts.init(el.evaluationTrendChart);
  state.evaluationTrendChart.setOption(
    {
      color: ["#0f766e", "#2563eb", "#b7791f"],
      grid: { left: 40, right: 18, top: 24, bottom: 34 },
      tooltip: { trigger: "axis", valueFormatter: (value) => `${value}%` },
      legend: {
        bottom: 0,
        itemHeight: 8,
        itemWidth: 14,
        textStyle: { color: "#66736d" },
      },
      xAxis: {
        type: "category",
        boundaryGap: false,
        data: points.map((item) => item.version),
        axisLine: { lineStyle: { color: "#dde5e1" } },
        axisLabel: { color: "#66736d" },
      },
      yAxis: {
        type: "value",
        min: 0,
        max: 100,
        axisLabel: { formatter: "{value}%", color: "#66736d" },
        splitLine: { lineStyle: { color: "#edf2f0" } },
      },
      series: [
        {
          name: "综合",
          type: "line",
          smooth: true,
          areaStyle: { opacity: 0.08 },
          data: points.map((item) => Math.round(item.overall_pass_rate * 1000) / 10),
        },
        {
          name: "SQL",
          type: "line",
          smooth: true,
          data: points.map((item) => Math.round(item.sql_quality_rate * 1000) / 10),
        },
        {
          name: "检索",
          type: "line",
          smooth: true,
          data: points.map((item) => Math.round(item.retrieval_pass_rate * 1000) / 10),
        },
      ],
    },
    true,
  );
}

function renderEvaluationIssues(items) {
  if (!items.length) {
    el.evaluationIssueList.innerHTML = '<div class="inline-empty">暂无问题分布</div>';
    return;
  }
  const total = Math.max(1, items.reduce((sum, item) => sum + Number(item.value || 0), 0));
  el.evaluationIssueList.innerHTML = items
    .map((item) => {
      const value = Number(item.value || 0);
      const width = value === 0 ? 4 : Math.max(8, Math.round((value / total) * 100));
      return `
        <div class="issue-item ${escapeHtml(item.status || "ok")}">
          <div>
            <strong>${escapeHtml(item.name)}</strong>
            <span>${value} 个问题</span>
          </div>
          <div class="issue-bar"><span style="width: ${width}%"></span></div>
        </div>
      `;
    })
    .join("");
}

function renderEvaluationRecentRuns(items) {
  if (!items.length) {
    el.evaluationRecentRuns.innerHTML = '<div class="inline-empty">暂无最近任务</div>';
    return;
  }
  el.evaluationRecentRuns.innerHTML = items
    .map(
      (item) => `
        <article class="recent-run ${escapeHtml(item.status || "ok")}">
          <div class="recent-run-head">
            <strong>${escapeHtml(item.name)}</strong>
            <span>${escapeHtml(item.status === "ok" ? "已完成" : "需关注")}</span>
          </div>
          <div class="recent-run-meta">
            <span>${escapeHtml(item.case_count)} 条用例</span>
            <span>${escapeHtml(item.duration_ms)}ms</span>
          </div>
          <div class="progress-track"><span style="width: ${Math.round(Number(item.pass_rate || 0) * 100)}%"></span></div>
          <small>通过率 ${formatPercent(item.pass_rate)} · ${formatDate(item.finished_at)}</small>
        </article>
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

function renderEvaluationModelComparisons(items) {
  if (!items.length) {
    el.evaluationModelBody.innerHTML = `<tr><td colspan="7"><div class="inline-empty">暂无模型对比数据</div></td></tr>`;
    return;
  }
  el.evaluationModelBody.innerHTML = items
    .map(
      (item) => `
        <tr>
          <td><strong>${escapeHtml(item.name)}</strong></td>
          <td>${escapeHtml(item.scenario)}</td>
          <td>${formatPercent(item.overall_pass_rate)}</td>
          <td>${formatPercent(item.sql_quality_rate)}</td>
          <td>${formatPercent(item.retrieval_pass_rate)}</td>
          <td>${escapeHtml(item.avg_latency_ms)}ms</td>
          <td>${escapeHtml(item.note)}</td>
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

function renderEvaluationErrors() {
  const report = state.evaluationReport;
  if (!report) {
    el.evaluationErrorList.innerHTML = '<div class="inline-empty">运行评测后查看错误案例</div>';
    return;
  }
  const failedCases = report.cases.filter((item) => item.status === "failed");
  if (!failedCases.length) {
    el.evaluationErrorList.innerHTML = `
      <div class="manager-empty evaluation-success-empty">
        <div class="manager-empty-icon"><svg><use href="#icon-check"></use></svg></div>
        <strong>本次没有失败案例</strong>
        <p>当前内置评测全部通过。后续可以扩展更难的测试集来继续压测模型边界。</p>
      </div>
    `;
    return;
  }
  el.evaluationErrorList.innerHTML = failedCases
    .map(
      (item) => `
        <details class="evaluation-case failed">
          <summary>
            <span class="case-status">失败</span>
            <span class="case-main">
              <strong>${escapeHtml(item.title)}</strong>
              <small>${escapeHtml(item.suite_name)}</small>
            </span>
          </summary>
          <div class="case-detail-grid">
            <div><span>错误原因</span><p>${escapeHtml((item.errors || []).join("；") || "未知")}</p></div>
            <div><span>修复建议</span><p>${escapeHtml(suggestionForFailure(item))}</p></div>
          </div>
        </details>
      `,
    )
    .join("");
}

function switchEvaluationTab(tabName) {
  if (!tabName) {
    return;
  }
  state.evaluationTab = tabName;
  el.evaluationTabs
    .querySelectorAll("button")
    .forEach((button) => {
      const isActive = button.dataset.evalTab === tabName;
      button.classList.toggle("active", isActive);
      button.setAttribute("aria-selected", String(isActive));
    });
  el.evaluationTabPanels.forEach((panel) =>
    panel.classList.toggle("active", panel.id === `evaluation${capitalize(tabName)}Panel`),
  );
  if (tabName === "overview" && state.evaluationTrendChart) {
    setTimeout(() => state.evaluationTrendChart.resize(), 0);
  }
}

function labelForEvalStatus(status) {
  return status === "passed" ? "通过" : "失败";
}

function deltaForKpi(id) {
  const labels = {
    overall: "较基线提升",
    sql_quality: "稳定",
    sql_safety: "硬边界",
    retrieval: "RAG 增强",
    latency: "离线评测",
  };
  return labels[id] || "监控中";
}

function suggestionForFailure(item) {
  if (item.suite_id === "text_to_sql") {
    return "优先检查 prompt 模板、schema 摘要和 SQL 生成规则。";
  }
  if (item.suite_id === "metric_retrieval") {
    return "优先补充指标别名、业务口径文档或调整检索阈值。";
  }
  if (item.suite_id === "sql_safety") {
    return "优先检查服务端 SQL 安全校验正则和多语句拦截逻辑。";
  }
  return "建议查看 trace、输入问题和实际输出后定位。";
}

function capitalize(value) {
  return value.charAt(0).toUpperCase() + value.slice(1);
}

function bindEvaluationTabs() {
  el.evaluationTabs.querySelectorAll("button[data-eval-tab]").forEach((button) => {
    button.setAttribute("role", "tab");
    button.setAttribute("aria-selected", String(button.classList.contains("active")));
    button.addEventListener("click", () => switchEvaluationTab(button.dataset.evalTab));
    button.addEventListener("keydown", (event) => {
      if (event.key !== "Enter" && event.key !== " ") {
        return;
      }
      event.preventDefault();
      switchEvaluationTab(button.dataset.evalTab);
    });
  });
  el.evaluationTabs.addEventListener("click", (event) => {
    switchEvaluationTab(getEvaluationTabFromEvent(event));
  });
}

function getEvaluationTabFromEvent(event) {
  const directButton = event.target.closest?.("button[data-eval-tab]");
  if (directButton) {
    return directButton.dataset.evalTab;
  }

  const x = event.clientX;
  const y = event.clientY;
  const fallbackButton = Array.from(el.evaluationTabs.querySelectorAll("button[data-eval-tab]")).find((button) => {
    const rect = button.getBoundingClientRect();
    return x >= rect.left && x <= rect.right && y >= rect.top && y <= rect.bottom;
  });
  return fallbackButton?.dataset.evalTab || "";
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
    if (category === "evaluation") {
      renderEvaluationDatasetOptions();
    }
    setFileState(category, "已同步", "ok");
  } catch (error) {
    setFileState(category, error.message, "error");
  }
}

function renderEvaluationDatasetOptions() {
  if (!el.evaluationDatasetSelect) {
    return;
  }
  const selected = el.evaluationDatasetSelect.value;
  const files = state.files.evaluation || [];
  const options = [
    { id: "", name: "内置评测集", description: "默认 Text-to-SQL / SQL 安全 / 指标检索套件" },
    ...files.map((file) => ({
      id: file.id,
      name: file.name,
      description: `${(file.extension || "").toUpperCase()} · ${formatBytes(file.size_bytes)}`,
    })),
  ];
  el.evaluationDatasetSelect.innerHTML = [
    '<option value="">内置评测集</option>',
    ...files.map(
      (file) => `<option value="${escapeHtml(file.id)}">${escapeHtml(file.name)}</option>`,
    ),
  ].join("");
  if (files.some((file) => file.id === selected)) {
    el.evaluationDatasetSelect.value = selected;
  }
  renderEvaluationDatasetMenu(options);
  updateEvaluationDatasetTrigger();
  toggleEvaluationDatasetMenu(false);
}

function renderEvaluationDatasetMenu(options) {
  if (!el.evaluationDatasetMenu) {
    return;
  }
  const selected = el.evaluationDatasetSelect?.value || "";
  el.evaluationDatasetMenu.innerHTML = options
    .map(
      (option) => `
        <button
          class="evaluation-dataset-option ${option.id === selected ? "active" : ""}"
          type="button"
          role="option"
          aria-selected="${option.id === selected ? "true" : "false"}"
          data-id="${escapeHtml(option.id)}"
        >
          <strong>${escapeHtml(option.name)}</strong>
          <span>${escapeHtml(option.description)}</span>
        </button>
      `,
    )
    .join("");
}

function updateEvaluationDatasetTrigger() {
  const selectedId = el.evaluationDatasetSelect?.value || "";
  const selectedFile = state.files.evaluation.find((file) => file.id === selectedId);
  const name = selectedFile?.name || "内置评测集";
  const hint = selectedFile
    ? `${(selectedFile.extension || "").toUpperCase()} · ${formatBytes(selectedFile.size_bytes)}`
    : "默认回归套件";
  if (el.evaluationDatasetLabel) {
    el.evaluationDatasetLabel.textContent = name;
  }
  if (el.evaluationDatasetHint) {
    el.evaluationDatasetHint.textContent = hint;
  }
  if (el.evaluationDatasetMenu) {
    el.evaluationDatasetMenu
      .querySelectorAll(".evaluation-dataset-option")
      .forEach((option) => {
        const isActive = option.dataset.id === selectedId;
        option.classList.toggle("active", isActive);
        option.setAttribute("aria-selected", String(isActive));
      });
  }
}

function selectedEvaluationDatasetName() {
  const selectedId = el.evaluationDatasetSelect?.value || "";
  if (!selectedId) {
    return "内置评测集";
  }
  return state.files.evaluation.find((file) => file.id === selectedId)?.name || "上传测试集";
}

function toggleEvaluationDatasetMenu(forceOpen) {
  if (!el.evaluationDatasetMenu || !el.evaluationDatasetTrigger) {
    return;
  }
  const isOpen = forceOpen ?? el.evaluationDatasetMenu.hidden;
  el.evaluationDatasetMenu.hidden = !isOpen;
  el.evaluationDatasetTrigger.setAttribute("aria-expanded", String(isOpen));
}

function selectEvaluationDataset(fileId) {
  if (!el.evaluationDatasetSelect) {
    return;
  }
  el.evaluationDatasetSelect.value = fileId || "";
  updateEvaluationDatasetTrigger();
  toggleEvaluationDatasetMenu(false);
  state.evaluationLoaded = false;
  el.evaluationRunMeta.textContent = `${selectedEvaluationDatasetName()} · 等待运行`;
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

function renderSqlReview(data = {}) {
  const sql = data.generated_sql || state.currentSql || "";
  if (el.sqlQuestionText) {
    el.sqlQuestionText.textContent = data.question || "等待用户提问";
  }
  if (el.sqlExplanationText) {
    el.sqlExplanationText.textContent =
      data.sql_explanation || "运行分析后，这里会说明 SQL 的查询意图、聚合口径和排序逻辑。";
  }
  if (!el.sqlCheckList) {
    return;
  }
  el.sqlCheckList.innerHTML = buildSqlChecks(sql, data)
    .map(
      (item) => `
        <span class="sql-check ${escapeHtml(item.status)}">
          <span>${escapeHtml(item.label)}</span>
          <strong>${escapeHtml(item.detail)}</strong>
        </span>
      `,
    )
    .join("");
}

function buildSqlChecks(sql, data = {}) {
  if (isPlaceholderSql(sql) || !sql.trim()) {
    return [{ label: "等待生成", detail: "输入问题后自动生成 SQL", status: "pending" }];
  }

  const normalized = stripSqlComments(sql).trim();
  const readOnly = isReadOnlySql(normalized);
  const singleStatement = isSingleSqlStatement(normalized);
  const balanced = hasBalancedParentheses(normalized);
  const hasLimit = /\bLIMIT\b/i.test(normalized);
  const hasSelectStar = /\bSELECT\s+\*/i.test(normalized);
  const executionOk = Array.isArray(data.trace_steps)
    && data.trace_steps.some((step) => step.name === "execute_sql" && step.status === "ok");

  return [
    {
      label: "只读范围",
      detail: readOnly ? "仅 SELECT/WITH" : "存在非只读风险",
      status: readOnly ? "ok" : "error",
    },
    {
      label: "语法结构",
      detail: singleStatement && balanced ? "单语句且括号匹配" : "需检查分号或括号",
      status: singleStatement && balanced ? "ok" : "warning",
    },
    {
      label: "执行验证",
      detail: executionOk ? `数据库执行成功，返回 ${data.rows?.length ?? 0} 行` : "等待数据库执行结果",
      status: executionOk ? "ok" : "pending",
    },
    {
      label: "结果限制",
      detail: hasLimit ? "已设置 LIMIT" : "建议增加 LIMIT",
      status: hasLimit ? "ok" : "warning",
    },
    {
      label: "书写规范",
      detail: hasSelectStar ? "建议显式列名" : "字段、聚合和排序清晰",
      status: hasSelectStar ? "warning" : "ok",
    },
  ];
}

function formatGeneratedSql(sql, data = {}) {
  if (isPlaceholderSql(sql)) {
    return sql;
  }
  return annotateSqlText(formatSqlText(stripLeadingSqlComments(sql)), data);
}

function setSqlContent(sql) {
  state.currentSql = sql || "-- SQL unavailable";
  const lines = state.currentSql.split(/\r?\n/);
  el.sqlBlock.innerHTML = highlightSql(state.currentSql);
  el.sqlLineNumbers.textContent = lines.map((_, index) => index + 1).join("\n");
  const sqlState = isPlaceholderSql(state.currentSql)
    ? "等待生成"
    : state.currentSql.includes("-- DataWhisperer 自动生成 SQL")
      ? "只读查询 · 含注释"
      : "只读查询";
  el.sqlMeta.textContent = `${lines.length} 行 · ${sqlState}`;
}

function formatCurrentSql() {
  if (isPlaceholderSql(state.currentSql)) {
    return;
  }
  const sourceSql = state.lastResponse?.generated_sql || stripLeadingSqlComments(state.currentSql);
  setSqlContent(formatGeneratedSql(sourceSql, state.lastResponse || {}));
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

function getResultDataset() {
  const response = state.lastResponse || {};
  return {
    columns: response.columns || [],
    rows: response.rows || [],
  };
}

function hasResultRows() {
  const { columns, rows } = getResultDataset();
  return columns.length > 0 && rows.length > 0;
}

function buildResultHtmlTable() {
  const { columns, rows } = getResultDataset();
  const header = columns.map((column) => `<th>${escapeHtml(labelForColumn(column))}</th>`).join("");
  const body = rows
    .map(
      (row) => `
        <tr>
          ${columns.map((column) => `<td>${escapeHtml(formatCell(row[column]))}</td>`).join("")}
        </tr>
      `,
    )
    .join("");
  return `
    <table style="border-collapse:collapse;font-family:Arial,'Microsoft YaHei',sans-serif;font-size:12px;">
      <thead>
        <tr>${header}</tr>
      </thead>
      <tbody>${body}</tbody>
    </table>
  `.replaceAll("<th>", '<th style="border:1px solid #d8e2de;background:#eef5f2;padding:8px 10px;text-align:left;">')
    .replaceAll("<td>", '<td style="border:1px solid #d8e2de;padding:8px 10px;text-align:left;">');
}

function buildResultMarkdownTable() {
  const { columns, rows } = getResultDataset();
  const escapeMarkdown = (value) => String(value ?? "").replaceAll("|", "\\|").replace(/\r?\n/g, " ");
  const header = `| ${columns.map((column) => escapeMarkdown(labelForColumn(column))).join(" | ")} |`;
  const divider = `| ${columns.map(() => "---").join(" | ")} |`;
  const body = rows
    .map((row) => `| ${columns.map((column) => escapeMarkdown(formatCell(row[column]))).join(" | ")} |`)
    .join("\n");
  return [header, divider, body].filter(Boolean).join("\n");
}

function buildResultCsv() {
  const { columns, rows } = getResultDataset();
  const escapeCsv = (value) => {
    const text = String(value ?? "");
    return /[",\r\n]/.test(text) ? `"${text.replaceAll('"', '""')}"` : text;
  };
  const header = columns.map((column) => escapeCsv(labelForColumn(column))).join(",");
  const body = rows.map((row) => columns.map((column) => escapeCsv(formatCell(row[column]))).join(",")).join("\n");
  return [header, body].filter(Boolean).join("\n");
}

async function copyTableHtml() {
  if (!hasResultRows()) {
    return;
  }
  const html = buildResultHtmlTable();
  const markdown = buildResultMarkdownTable();
  if (window.ClipboardItem) {
    await navigator.clipboard.write([
      new ClipboardItem({
        "text/html": new Blob([html], { type: "text/html" }),
        "text/plain": new Blob([markdown], { type: "text/plain" }),
      }),
    ]);
  } else {
    await navigator.clipboard.writeText(markdown);
  }
  markButtonDone(el.copyTableHtmlButton, "已复制");
}

async function copyTableMarkdown() {
  if (!hasResultRows()) {
    return;
  }
  await navigator.clipboard.writeText(buildResultMarkdownTable());
  markButtonDone(el.copyTableMarkdownButton, "已复制");
}

function downloadResultCsv() {
  if (!hasResultRows()) {
    return;
  }
  downloadBlob(
    new Blob([`\ufeff${buildResultCsv()}`], { type: "text/csv;charset=utf-8" }),
    `datawhisperer-result-${timestampForFilename()}.csv`,
  );
  markButtonDone(el.downloadCsvButton, "已下载");
}

function getChartSvgText() {
  const svg = buildChartSvgForExport();
  if (!svg) {
    return "";
  }
  svg.setAttribute("xmlns", "http://www.w3.org/2000/svg");
  return new XMLSerializer().serializeToString(svg);
}

function buildChartSvgForExport() {
  if (!window.echarts || !state.lastResponse?.chart) {
    return el.chartHost.querySelector("svg");
  }
  const canvasRect = el.chartHost.getBoundingClientRect();
  const exportNode = document.createElement("div");
  exportNode.style.cssText = [
    "position: fixed",
    "left: -10000px",
    "top: -10000px",
    `width: ${Math.max(720, Math.round(canvasRect.width || 720))}px`,
    `height: ${Math.max(420, Math.round(canvasRect.height || 420))}px`,
    "background: #ffffff",
  ].join(";");
  document.body.appendChild(exportNode);

  const exportChart = window.echarts.init(exportNode, null, { renderer: "svg" });
  exportChart.setOption(enhanceChartOption(localizeChartOption(state.lastResponse.chart)), true);
  const svg = exportNode.querySelector("svg")?.cloneNode(true);
  exportChart.dispose();
  exportNode.remove();
  return svg;
}

async function copyChartPng() {
  if (!state.chart) {
    return;
  }
  const blob = await imageDataUrlToPngBlob(
    state.chart.getDataURL({ type: "png", pixelRatio: 2, backgroundColor: "#ffffff" }),
  );
  if (window.ClipboardItem) {
    try {
      await navigator.clipboard.write([new ClipboardItem({ "image/png": blob })]);
      markButtonDone(el.copyChartPngButton, "已复制");
      return;
    } catch (error) {
      console.warn("Clipboard image copy failed; downloading PNG instead.", error);
    }
  }
  downloadBlob(blob, `datawhisperer-chart-${timestampForFilename()}.png`);
  markButtonDone(el.copyChartPngButton, "已下载");
}

function downloadChartSvg() {
  const svgText = getChartSvgText();
  if (!svgText) {
    return;
  }
  downloadBlob(
    new Blob([svgText], { type: "image/svg+xml;charset=utf-8" }),
    `datawhisperer-chart-${timestampForFilename()}.svg`,
  );
  markButtonDone(el.downloadChartSvgButton, "已下载");
}

async function copyChartOption() {
  if (!state.chart) {
    return;
  }
  const payload = {
    question: state.lastResponse?.question || "",
    chart: state.lastResponse?.chart || {},
    echarts_option: state.chart.getOption(),
    columns: state.lastResponse?.columns || [],
    rows: state.lastResponse?.rows || [],
  };
  await navigator.clipboard.writeText(JSON.stringify(payload, null, 2));
  markButtonDone(el.copyChartOptionButton, "已复制");
}

async function imageDataUrlToPngBlob(dataUrl) {
  const sourceBlob = await (await fetch(dataUrl)).blob();
  if (sourceBlob.type === "image/png") {
    return sourceBlob;
  }
  return new Promise((resolve, reject) => {
    const image = new Image();
    image.onload = () => {
      const canvas = document.createElement("canvas");
      canvas.width = image.naturalWidth || image.width;
      canvas.height = image.naturalHeight || image.height;
      const context = canvas.getContext("2d");
      context.fillStyle = "#ffffff";
      context.fillRect(0, 0, canvas.width, canvas.height);
      context.drawImage(image, 0, 0);
      canvas.toBlob((blob) => (blob ? resolve(blob) : reject(new Error("Chart export failed"))), "image/png");
      URL.revokeObjectURL(image.src);
    };
    image.onerror = reject;
    image.src = URL.createObjectURL(sourceBlob);
  });
}

function downloadBlob(blob, filename) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  document.body.appendChild(link);
  link.click();
  link.remove();
  URL.revokeObjectURL(url);
}

function timestampForFilename() {
  return new Date().toISOString().slice(0, 19).replaceAll(":", "-");
}

function markButtonDone(button, label) {
  const textNode = button?.querySelector("span");
  if (!textNode) {
    return;
  }
  const original = textNode.textContent;
  textNode.textContent = label;
  button.classList.add("is-done");
  setTimeout(() => {
    textNode.textContent = original;
    button.classList.remove("is-done");
  }, 1200);
}

function isPlaceholderSql(sql) {
  return !sql || sql.trim().startsWith("-- SQL");
}

function stripLeadingSqlComments(sql) {
  return sql
    .split(/\r?\n/)
    .filter((line) => !line.trim().startsWith("--"))
    .join("\n")
    .trim();
}

function stripSqlComments(sql) {
  return sql.replace(/--.*$/gm, "").replace(/\/\*[\s\S]*?\*\//g, "");
}

function isReadOnlySql(sql) {
  const forbidden = /\b(INSERT|UPDATE|DELETE|DROP|ALTER|TRUNCATE|CREATE|REPLACE|GRANT|REVOKE|CALL|EXEC)\b/i;
  return /^(SELECT|WITH)\b/i.test(sql) && !forbidden.test(sql);
}

function isSingleSqlStatement(sql) {
  return sql
    .split(";")
    .map((part) => part.trim())
    .filter(Boolean).length <= 1;
}

function hasBalancedParentheses(sql) {
  let depth = 0;
  for (const character of sql) {
    if (character === "(") {
      depth += 1;
    }
    if (character === ")") {
      depth -= 1;
    }
    if (depth < 0) {
      return false;
    }
  }
  return depth === 0;
}

function annotateSqlText(sql, data = {}) {
  const lines = sql.split(/\r?\n/).filter((line) => line.trim());
  const comments = [
    "-- DataWhisperer 自动生成 SQL",
    `-- 原始问题：${data.question || "用户自然语言问题"}`,
  ];

  if (data.sql_explanation) {
    comments.push(`-- 生成说明：${data.sql_explanation}`);
  }
  comments.push("-- 说明：以下 SQL 仅用于只读查询，复制后仍可直接在 MySQL 中执行。", "");

  const annotatedLines = [];
  let lastComment = "";
  for (const line of lines) {
    const clauseComment = commentForSqlLine(line);
    if (clauseComment && clauseComment !== lastComment) {
      annotatedLines.push(clauseComment);
      lastComment = clauseComment;
    }
    annotatedLines.push(line);
  }
  return [...comments, ...annotatedLines].join("\n");
}

function commentForSqlLine(line) {
  const normalized = line.trim().toUpperCase();
  if (normalized.startsWith("SELECT")) {
    return "-- 选择查询结果需要展示的维度字段和计算指标。";
  }
  if (normalized.startsWith("FROM")) {
    return "-- 指定主查询表，作为本次分析的数据来源。";
  }
  if (
    normalized.startsWith("JOIN")
    || normalized.startsWith("LEFT JOIN")
    || normalized.startsWith("RIGHT JOIN")
    || normalized.startsWith("INNER JOIN")
  ) {
    return "-- 关联维度表或明细表，补充分析所需字段。";
  }
  if (normalized.startsWith("ON")) {
    return "-- 指定表之间的关联条件，避免产生错误笛卡尔积。";
  }
  if (normalized.startsWith("WHERE")) {
    return "-- 设置过滤条件，例如时间范围、地区或业务状态。";
  }
  if (normalized.startsWith("GROUP BY")) {
    return "-- 按业务维度分组，用于聚合统计指标。";
  }
  if (normalized.startsWith("ORDER BY")) {
    return "-- 按核心指标排序，方便快速查看排名或趋势。";
  }
  if (normalized.startsWith("LIMIT")) {
    return "-- 限制返回行数，避免一次性返回过多数据。";
  }
  return "";
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

function currentMessageTime() {
  return new Date().toLocaleTimeString("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
    hour12: false,
  });
}

function bindEvents() {
  el.newConversationButton?.addEventListener("click", resetConversation);
  el.clearConversationButton?.addEventListener("click", resetConversation);
  el.resetContextButton?.addEventListener("click", () => {
    el.currentCondition.textContent = "无";
    renderConversationList(el.chatTitle.textContent || "新对话", "上下文已重置");
  });
  el.runButton.addEventListener("click", runAnalysis);
  el.questionInput.addEventListener("input", () => {
    el.questionInput.style.height = "auto";
    el.questionInput.style.height = `${Math.min(el.questionInput.scrollHeight, 160)}px`;
  });
  el.questionInput.addEventListener("keydown", (event) => {
    if (event.key === "Enter" && !event.shiftKey) {
      event.preventDefault();
      runAnalysis();
    }
  });
  el.refreshExamplesButton.addEventListener("click", loadExamples);
  el.loadSchemaButton.addEventListener("click", loadSchema);
  el.formatSqlButton.addEventListener("click", formatCurrentSql);
  el.downloadSqlButton.addEventListener("click", downloadSql);
  el.copySqlButton.addEventListener("click", copySql);
  el.copyChartPngButton.addEventListener("click", copyChartPng);
  el.downloadChartSvgButton.addEventListener("click", downloadChartSvg);
  el.copyChartOptionButton.addEventListener("click", copyChartOption);
  el.copyTableHtmlButton.addEventListener("click", copyTableHtml);
  el.copyTableMarkdownButton.addEventListener("click", copyTableMarkdown);
  el.downloadCsvButton.addEventListener("click", downloadResultCsv);
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
  el.evaluationDatasetSelect?.addEventListener("change", () => {
    selectEvaluationDataset(el.evaluationDatasetSelect.value);
  });
  el.evaluationDatasetTrigger?.addEventListener("click", (event) => {
    event.stopPropagation();
    toggleEvaluationDatasetMenu();
  });
  el.evaluationDatasetMenu?.addEventListener("click", (event) => {
    const button = event.target.closest(".evaluation-dataset-option");
    if (!button) {
      return;
    }
    selectEvaluationDataset(button.dataset.id);
  });
  el.runEvaluationButton.addEventListener("click", runEvaluations);
  bindEvaluationTabs();
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
      scrollChatToBottom();
      if (!el.runButton.disabled) {
        runAnalysis();
      }
    }
  });
  el.sceneGrid?.addEventListener("click", (event) => {
    const button = event.target.closest(".scene-card");
    if (!button || el.runButton.disabled) {
      return;
    }
    el.questionInput.value = button.dataset.question || "";
    runAnalysis();
  });
  el.conversationList?.addEventListener("click", (event) => {
    const button = event.target.closest(".conversation-item[data-question]");
    if (!button || el.runButton.disabled) {
      return;
    }
    el.questionInput.value = button.dataset.question || "";
    runAnalysis();
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
  el.resultDetailButtons.forEach((button) => {
    button.addEventListener("click", () => toggleResultDetail(button.dataset.detailTarget));
  });
  el.navItems.forEach((item) => {
    item.addEventListener("click", () => switchView(item.dataset.view));
  });
  window.addEventListener("resize", () => {
    if (state.chart) {
      state.chart.resize();
    }
    if (state.evaluationTrendChart) {
      state.evaluationTrendChart.resize();
    }
  });
  document.addEventListener("click", (event) => {
    if (!el.evaluationDatasetPicker?.contains(event.target)) {
      toggleEvaluationDatasetMenu(false);
    }
  });
}

bindEvents();
hydrateConversationalCopy();
setSqlContent(state.currentSql);
renderConversationList();
checkHealth();
loadExamples();
renderProcessTimeline([]);
loadManagedFiles("schema");
loadManagedFiles("rag");
loadManagedFiles("evaluation");
