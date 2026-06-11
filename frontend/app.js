const DEFAULT_API_BASE = "http://localhost:8081";
const DEFAULT_AI_BASE = "http://localhost:8000";
const hasBrowserDom = typeof document !== "undefined";

const state = {
  apiBase: typeof localStorage !== "undefined" ? localStorage.getItem("jinroApiBase") || DEFAULT_API_BASE : DEFAULT_API_BASE,
  aiBase: typeof localStorage !== "undefined" ? localStorage.getItem("jinroAiBase") || DEFAULT_AI_BASE : DEFAULT_AI_BASE,
  page: 0,
  size: 5,
  selectedArticleId: null,
  articles: [],
  pageInfo: null,
};

const elements = hasBrowserDom
  ? {
      apiBaseInput: document.querySelector("#apiBaseInput"),
      aiBaseInput: document.querySelector("#aiBaseInput"),
      saveApiBaseButton: document.querySelector("#saveApiBaseButton"),
      apiStatus: document.querySelector("#apiStatus"),
      articleCount: document.querySelector("#articleCount"),
      selectedArticleLabel: document.querySelector("#selectedArticleLabel"),
      refreshButton: document.querySelector("#refreshButton"),
      notFoundButton: document.querySelector("#notFoundButton"),
      methodCheckButton: document.querySelector("#methodCheckButton"),
      pageSizeSelect: document.querySelector("#pageSizeSelect"),
      pageSummary: document.querySelector("#pageSummary"),
      articleList: document.querySelector("#articleList"),
      previousPageButton: document.querySelector("#previousPageButton"),
      nextPageButton: document.querySelector("#nextPageButton"),
      detailEmpty: document.querySelector("#detailEmpty"),
      detailContent: document.querySelector("#detailContent"),
      detailSource: document.querySelector("#detailSource"),
      detailTitle: document.querySelector("#detailTitle"),
      detailUrl: document.querySelector("#detailUrl"),
      detailId: document.querySelector("#detailId"),
      detailPublishedAt: document.querySelector("#detailPublishedAt"),
      detailAnalysisCount: document.querySelector("#detailAnalysisCount"),
      analysisGrid: document.querySelector("#analysisGrid"),
      analysisOnlyButton: document.querySelector("#analysisOnlyButton"),
      commentAnalysisButton: document.querySelector("#commentAnalysisButton"),
      commentPanel: document.querySelector("#commentPanel"),
      clearLogButton: document.querySelector("#clearLogButton"),
      responseLog: document.querySelector("#responseLog"),
    }
  : {};

export function normalizeApiBase(value) {
  const trimmed = String(value || "").trim().replace(/\/+$/, "");
  return trimmed || DEFAULT_API_BASE;
}

export function normalizeAiBase(value) {
  const trimmed = String(value || "").trim().replace(/\/+$/, "");
  return trimmed || DEFAULT_AI_BASE;
}

export function formatDateTime(value) {
  if (!value) {
    return "-";
  }
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return "-";
  }
  return new Intl.DateTimeFormat("ko-KR", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

export function scoreToPercent(score, kind) {
  if (typeof score !== "number" || Number.isNaN(score)) {
    return 0;
  }
  if (kind === "sentiment") {
    return Math.round(((Math.max(-1, Math.min(1, score)) + 1) / 2) * 100);
  }
  return Math.round(Math.max(0, Math.min(1, score)) * 100);
}

export function formatScore(score) {
  if (typeof score !== "number" || Number.isNaN(score)) {
    return "-";
  }
  return score.toFixed(2);
}

export function formatScoreAsPoints(score, kind) {
  if (typeof score !== "number" || Number.isNaN(score)) {
    return "-";
  }
  return `${scoreToPercent(score, kind)}점`;
}

export function scoreTone(score, kind) {
  const percent = scoreToPercent(score, kind);
  if (kind === "bias") {
    if (percent <= 35) {
      return "good";
    }
    if (percent <= 70) {
      return "warn";
    }
    return "bad";
  }
  if (percent >= 70) {
    return "good";
  }
  if (percent >= 35) {
    return "warn";
  }
  return "bad";
}

export function summarizePage(pageData) {
  const page = pageData?.page || {};
  return {
    content: Array.isArray(pageData?.content) ? pageData.content : [],
    number: Number.isInteger(page.number) ? page.number : 0,
    size: Number.isInteger(page.size) ? page.size : 0,
    totalElements: Number.isInteger(page.totalElements) ? page.totalElements : 0,
    totalPages: Number.isInteger(page.totalPages) ? page.totalPages : 0,
  };
}

function setStatus(element, text, className) {
  element.textContent = text;
  element.classList.remove("state-ok", "state-error", "state-warn");
  if (className) {
    element.classList.add(className);
  }
}

function buildUrl(path) {
  return `${state.apiBase}${path}`;
}

function buildAiUrl(path) {
  return `${state.aiBase}${path}`;
}

async function requestJson(path, options = {}) {
  const response = await fetch(buildUrl(path), {
    headers: {
      Accept: "application/json",
      ...(options.headers || {}),
    },
    ...options,
  });
  const text = await response.text();
  let body = null;
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      body = text;
    }
  }
  return {
    ok: response.ok,
    status: response.status,
    statusText: response.statusText,
    headers: response.headers,
    body,
  };
}

async function requestAiJson(path, options = {}) {
  const response = await fetch(buildAiUrl(path), {
    headers: {
      Accept: "application/json",
      ...(options.headers || {}),
    },
    ...options,
  });
  const text = await response.text();
  let body = null;
  if (text) {
    try {
      body = JSON.parse(text);
    } catch {
      body = text;
    }
  }
  return {
    ok: response.ok,
    status: response.status,
    statusText: response.statusText,
    body,
  };
}

function renderArticleList() {
  const page = state.pageInfo || { number: state.page, size: state.size, totalElements: 0, totalPages: 0 };
  elements.pageSummary.textContent = `page=${page.number}, size=${page.size}, total=${page.totalElements}`;
  elements.articleCount.textContent = String(page.totalElements);
  elements.articleList.innerHTML = "";

  if (state.articles.length === 0) {
    const empty = document.createElement("div");
    empty.className = "empty-state";
    empty.innerHTML = "<h2>기사 없음</h2><p>SBS 기사 크롤링과 기사/댓글 분석을 실행한 뒤 새로고침하세요.</p>";
    elements.articleList.append(empty);
  }

  for (const article of state.articles) {
    const button = document.createElement("button");
    button.type = "button";
    button.className = `article-button${article.id === state.selectedArticleId ? " active" : ""}`;
    button.innerHTML = `
      <span class="article-title">${escapeHtml(article.title || "제목 없음")}</span>
      <span class="article-meta">
        <span>#${article.id}</span>
        <span>${escapeHtml(article.sourceName || "출처 없음")}</span>
        <span>${formatDateTime(article.publishedAt)}</span>
      </span>
    `;
    button.addEventListener("click", () => selectArticle(article.id));
    elements.articleList.append(button);
  }

  elements.previousPageButton.disabled = page.number <= 0;
  elements.nextPageButton.disabled = page.totalPages <= 0 || page.number >= page.totalPages - 1;
}

function renderArticleDetail(article) {
  elements.detailEmpty.classList.add("hidden");
  elements.detailContent.classList.remove("hidden");
  elements.detailSource.textContent = article.sourceName || "출처 없음";
  elements.detailTitle.textContent = article.title || "제목 없음";
  elements.detailUrl.href = article.url || "#";
  elements.detailId.textContent = String(article.id);
  elements.detailPublishedAt.textContent = formatDateTime(article.publishedAt);
  renderAnalysis(article.analysisResults || []);
  renderCommentLoading();
  elements.selectedArticleLabel.textContent = `#${article.id}`;
  loadCommentAnalysis(article.id);
}

function renderAnalysis(results) {
  elements.detailAnalysisCount.textContent = `${results.length}건`;
  elements.analysisGrid.innerHTML = "";

  if (results.length === 0) {
    const empty = document.createElement("p");
    empty.className = "summary";
    empty.textContent = "등록된 분석 결과가 없습니다.";
    elements.analysisGrid.append(empty);
    return;
  }

  for (const result of results) {
    const card = document.createElement("section");
    card.className = "analysis-card";
    card.innerHTML = `
      <h4>${escapeHtml(result.modelUsed || "unknown-model")}</h4>
      <div class="score-list">
        ${scoreRow("감정", result.sentimentScore, "sentiment")}
        ${scoreRow("편향", result.biasScore, "bias")}
        ${scoreRow("사실성", result.factualityScore, "factuality")}
      </div>
      <p class="summary">${escapeHtml(result.summary || "요약 없음")}</p>
    `;
    elements.analysisGrid.append(card);
  }
}

function renderCommentLoading() {
  elements.commentPanel.innerHTML = '<p class="summary">댓글 여론 분석 결과를 조회하는 중입니다.</p>';
}

function renderCommentAnalysis(payload) {
  const data = payload?.data;
  if (!data) {
    elements.commentPanel.innerHTML = '<p class="summary">댓글 여론 분석 결과가 없습니다.</p>';
    return;
  }

  const comments = Array.isArray(data.top_comments) ? data.top_comments : [];
  const sentimentTone = scoreTone(data.avg_sentiment, "sentiment");
  elements.commentPanel.innerHTML = `
    <section class="opinion-box">
      <p class="summary">${escapeHtml(data.public_opinion || "여론 요약 없음")}</p>
      <div class="opinion-metrics">
        <span>댓글 수 <strong>${data.total_comments ?? 0}</strong></span>
        <span class="metric-pill ${sentimentTone}">평균 감정 <strong>${formatScoreAsPoints(data.avg_sentiment, "sentiment")}</strong></span>
        <span>긍정 비율 <strong>${formatRatio(data.positive_ratio)}</strong></span>
        <span>부정 비율 <strong>${formatRatio(data.negative_ratio)}</strong></span>
      </div>
    </section>
    ${comments.map(renderCommentItem).join("")}
  `;
}

function renderCommentError(error) {
  elements.commentPanel.innerHTML = `
    <section class="opinion-box">
      <p class="summary">댓글 API 조회 실패: ${escapeHtml(error.message)}. AI 엔진이 실행 중인지 확인하세요.</p>
    </section>
  `;
}

function renderCommentItem(comment) {
  return `
    <article class="comment-item">
      <p class="summary">${escapeHtml(comment.content || "")}</p>
      <div class="comment-meta">
        <span>${escapeHtml(comment.author || "익명")}</span>
        <span>공감 ${comment.likes ?? 0}</span>
        <span>비공감 ${comment.dislikes ?? 0}</span>
      </div>
    </article>
  `;
}

function formatRatio(value) {
  if (typeof value !== "number" || Number.isNaN(value)) {
    return "-";
  }
  return `${Math.round(value * 100)}%`;
}

function scoreRow(label, value, kind) {
  const percent = scoreToPercent(value, kind);
  const tone = scoreTone(value, kind);
  return `
    <div class="score-row ${tone}">
      <span>${label}</span>
      <span class="score-bar"><span class="score-fill ${kind}" style="width: ${percent}%"></span></span>
      <strong class="score-badge ${tone}">${formatScoreAsPoints(value, kind)}</strong>
    </div>
  `;
}

function renderLog(title, payload) {
  elements.responseLog.textContent = `${title}\n${JSON.stringify(payload, null, 2)}`;
}

function escapeHtml(value) {
  return String(value)
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

async function checkApiStatus() {
  try {
    const result = await requestJson("/api/v1/articles?page=0&size=1", { cache: "no-store" });
    if (!result.ok) {
      throw new Error(`HTTP ${result.status}`);
    }
    setStatus(elements.apiStatus, "연결됨", "state-ok");
  } catch (error) {
    setStatus(elements.apiStatus, "연결 실패", "state-error");
    renderLog("API 서버 상태 확인 실패", { message: error.message, apiBase: state.apiBase });
  }
}

async function loadArticles() {
  setStatus(elements.apiStatus, "조회 중", "state-warn");
  try {
    const result = await requestJson(`/api/v1/articles?page=${state.page}&size=${state.size}`);
    if (!result.ok) {
      throw new Error(`HTTP ${result.status}`);
    }
    const page = summarizePage(result.body);
    state.articles = page.content;
    state.pageInfo = page;
    state.page = page.number;
    renderArticleList();
    setStatus(elements.apiStatus, "연결됨", "state-ok");

    if (!state.selectedArticleId && state.articles[0]) {
      await selectArticle(state.articles[0].id);
    } else {
      renderArticleList();
    }
  } catch (error) {
    state.articles = [];
    state.pageInfo = null;
    renderArticleList();
    setStatus(elements.apiStatus, "조회 실패", "state-error");
    renderLog("기사 목록 조회 실패", { message: error.message, apiBase: state.apiBase });
  }
}

async function selectArticle(id) {
  state.selectedArticleId = id;
  renderArticleList();
  try {
    const result = await requestJson(`/api/v1/articles/${id}`);
    if (!result.ok) {
      throw new Error(`HTTP ${result.status}`);
    }
    renderArticleDetail(result.body);
  } catch (error) {
    renderLog("기사 상세 조회 실패", { id, message: error.message });
  }
}

async function reloadAnalysisOnly() {
  if (!state.selectedArticleId) {
    return;
  }
  try {
    const result = await requestJson(`/api/v1/articles/${state.selectedArticleId}/analysis`);
    if (!result.ok) {
      throw new Error(`HTTP ${result.status}`);
    }
    renderAnalysis(Array.isArray(result.body) ? result.body : []);
    renderLog("분석 API 재조회 성공", result.body);
  } catch (error) {
    renderLog("분석 API 재조회 실패", { id: state.selectedArticleId, message: error.message });
  }
}

async function loadCommentAnalysis(id = state.selectedArticleId) {
  if (!id) {
    return;
  }
  renderCommentLoading();
  try {
    const result = await requestAiJson(`/api/comments/analysis/${id}`);
    if (!result.ok) {
      throw new Error(`HTTP ${result.status}`);
    }
    renderCommentAnalysis(result.body);
  } catch (error) {
    renderCommentError(error);
  }
}

async function runNotFoundCheck() {
  const result = await requestJson("/api/v1/articles/999999");
  renderLog("404 검증 결과", {
    status: result.status,
    body: result.body,
  });
}

async function runMethodCheck() {
  const result = await requestJson("/api/v1/articles", { method: "POST" });
  renderLog("405 검증 결과", {
    status: result.status,
    allow: result.headers.get("Allow"),
    body: result.body,
  });
}

function bindEvents() {
  elements.apiBaseInput.value = state.apiBase;
  elements.aiBaseInput.value = state.aiBase;
  elements.saveApiBaseButton.addEventListener("click", () => {
    state.apiBase = normalizeApiBase(elements.apiBaseInput.value);
    state.aiBase = normalizeAiBase(elements.aiBaseInput.value);
    localStorage.setItem("jinroApiBase", state.apiBase);
    localStorage.setItem("jinroAiBase", state.aiBase);
    state.page = 0;
    state.selectedArticleId = null;
    loadArticles();
  });
  elements.refreshButton.addEventListener("click", loadArticles);
  elements.notFoundButton.addEventListener("click", runNotFoundCheck);
  elements.methodCheckButton.addEventListener("click", runMethodCheck);
  elements.pageSizeSelect.addEventListener("change", () => {
    state.size = Number(elements.pageSizeSelect.value);
    state.page = 0;
    loadArticles();
  });
  elements.previousPageButton.addEventListener("click", () => {
    state.page = Math.max(0, state.page - 1);
    loadArticles();
  });
  elements.nextPageButton.addEventListener("click", () => {
    state.page += 1;
    loadArticles();
  });
  elements.analysisOnlyButton.addEventListener("click", reloadAnalysisOnly);
  elements.commentAnalysisButton.addEventListener("click", () => loadCommentAnalysis());
  elements.clearLogButton.addEventListener("click", () => {
    elements.responseLog.textContent = "아직 실행된 검증 요청이 없습니다.";
  });
}

if (hasBrowserDom) {
  bindEvents();
  checkApiStatus();
  loadArticles();
}
