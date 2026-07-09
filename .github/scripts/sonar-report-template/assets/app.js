const report = window.__SONAR_REPORT__ || {};
const raw = report.raw || {};
const meta = report.meta || {};
const locale = "ru";
const i18n = window.__SONAR_I18N__?.[locale] || {};

const $ = (selector) => document.querySelector(selector);

const escapeHtml = (value) => String(value ?? "")
  .replaceAll("&", "&amp;")
  .replaceAll("<", "&lt;")
  .replaceAll(">", "&gt;")
  .replaceAll('"', "&quot;")
  .replaceAll("'", "&#39;");

function tr(key, fallback, params = {}) {
  const template = String(i18n[key] || fallback || "");
  return template.replace(/\{([a-zA-Z0-9_]+)\}/g, (_, name) => String(params[name] ?? ""));
}

function trMap(group, value) {
  if (value === undefined || value === null || value === "") return "";
  const map = i18n[group] || {};
  const text = String(value);
  return map[text] || map[text.toUpperCase()] || text;
}

const translatedStatus = (value) => trMap("statusValues", value);
const translatedSeverity = (value) => trMap("severityValues", value);
const translatedIssueType = (value) => trMap("issueTypeValues", value);
const translatedSoftwareQuality = (value) => trMap("softwareQualityValues", value);
const translatedHotspotStatus = (value) => trMap("hotspotStatusValues", value);
const translatedSecurityCategory = (value) => trMap("securityCategoryValues", value);
const translatedMetricDomain = (value) => trMap("metricDomainValues", value);
const translatedMetricValueKey = (value) => trMap("metricValueKeys", translatedSeverity(value));

const isPlainObject = (value) => value && typeof value === "object" && !Array.isArray(value);
const asItems = (section) => Array.isArray(raw[section]?.items) ? raw[section].items : [];
const jsonText = (value) => JSON.stringify(value ?? null, null, 2);
const htmlTagPattern = /<\/?(?:h[1-6]|p|table|thead|tbody|tr|th|td|ul|ol|li|pre|code|br|strong|em|b|i|div|span|a|blockquote)\b/i;

const metricCatalog = Object.fromEntries((raw.metrics_catalog?.items || [])
  .filter((metric) => metric && metric.key)
  .map((metric) => [metric.key, metric]));

function initHeader() {
  const project = raw.project?.component || {};
  const title = project.name || meta.project || "SonarQube";
  document.title = tr("titlePrefix", "Отчет SonarQube: {title}", { title });
  $("#reportTitle").textContent = title;
  $("#reportMeta").textContent = [
    meta.generated_at ? tr("generatedAt", "Сформировано: {value}", { value: formatDateTime(meta.generated_at) }) : "",
    meta.branch ? tr("branch", "Ветка: {value}", { value: meta.branch }) : "",
    meta.language ? tr("language", "Язык: {value}", { value: meta.language }) : "",
    meta.url ? tr("server", "Сервер: {value}", { value: meta.url }) : "",
  ].filter(Boolean).join(" | ");
  document.querySelectorAll("[data-i18n]").forEach((node) => {
    node.textContent = tr(node.dataset.i18n, node.textContent);
  });
  document.querySelectorAll("[data-i18n-aria]").forEach((node) => {
    node.setAttribute("aria-label", tr(node.dataset.i18nAria, node.getAttribute("aria-label") || ""));
  });
}

function sectionHead(title, count, extra = "") {
  const suffix = count === undefined ? "" : `<div class="muted">${escapeHtml(tr("records", "{count} записей", { count }))}</div>`;
  return `<div class="section-head"><h2>${escapeHtml(title)}</h2>${suffix}${extra}</div>`;
}

function statusClass(status) {
  const normalized = String(status || "").toLowerCase();
  if (["ok", "passed", "success"].includes(normalized)) return "status-ok";
  if (["error", "failed", "fail"].includes(normalized)) return "status-error";
  if (["warn", "warning"].includes(normalized)) return "status-warn";
  return "status-neutral";
}

function formatValue(value) {
  if (value === undefined || value === null || value === "") return "";
  if (Array.isArray(value)) {
    if (!value.length) return "";
    const hasStructuredItems = value.some((item) => item && typeof item === "object");
    return value.map(formatArrayItem).filter(Boolean).join(hasStructuredItems ? " | " : ", ");
  }
  if (isPlainObject(value)) {
    return Object.entries(value)
      .map(([key, item]) => {
        const formatted = formatValue(item);
        return formatted === "" ? key : `${key}: ${formatted}`;
      })
      .join("; ");
  }
  return String(value);
}

function formatArrayItem(value) {
  if (isPlainObject(value)) return `{${formatValue(value)}}`;
  return formatValue(value);
}

function sourceCodeHtml(value) {
  const template = document.createElement("template");
  template.innerHTML = String(value ?? "");
  const render = (node) => {
    if (node.nodeType === Node.TEXT_NODE) return escapeHtml(node.nodeValue || "");
    if (node.nodeType !== Node.ELEMENT_NODE) return "";
    const children = Array.from(node.childNodes).map(render).join("");
    if (node.tagName.toLowerCase() !== "span") return children;
    const classes = String(node.getAttribute("class") || "")
      .split(/\s+/)
      .filter((name) => /^[a-zA-Z0-9_-]+$/.test(name))
      .join(" ");
    return classes ? `<span class="${classes}">${children}</span>` : `<span>${children}</span>`;
  };
  return Array.from(template.content.childNodes).map(render).join("");
}

function safeRichHtml(value) {
  const allowedTags = new Set(["p", "br", "ul", "ol", "li", "table", "thead", "tbody", "tr", "th", "td", "h1", "h2", "h3", "h4", "pre", "code", "strong", "em", "b", "i", "span", "div", "a", "blockquote"]);
  const template = document.createElement("template");
  template.innerHTML = String(value ?? "");
  const render = (node) => {
    if (node.nodeType === Node.TEXT_NODE) return escapeHtml(node.nodeValue || "");
    if (node.nodeType !== Node.ELEMENT_NODE) return "";
    const tag = node.tagName.toLowerCase();
    const children = Array.from(node.childNodes).map(render).join("");
    if (!allowedTags.has(tag)) return children;
    if (tag === "code" || tag === "pre") {
      const classes = String(node.getAttribute("class") || "")
        .split(/\s+/)
        .filter((name) => /^[a-zA-Z0-9_-]+$/.test(name))
        .join(" ");
      return classes ? `<${tag} class="${classes}">${children}</${tag}>` : `<${tag}>${children}</${tag}>`;
    }
    if (tag === "a") {
      const href = String(node.getAttribute("href") || "");
      const safeHref = /^(https?:|mailto:|#|\/)/i.test(href) ? ` href="${escapeHtml(href)}"` : "";
      return `<a${safeHref}>${children}</a>`;
    }
    return `<${tag}>${children}</${tag}>`;
  };
  return Array.from(template.content.childNodes).map(render).join("");
}

function isRichHtmlColumn(column) {
  return column.endsWith(".riskDescription")
    || column.endsWith(".descriptionSections.content")
    || column.endsWith(".htmlDesc")
    || column === "htmlDesc";
}

function containsHtml(value) {
  return typeof value === "string" && htmlTagPattern.test(value);
}

function renderCell(value, column = "") {
  if (column === "code") {
    return `<pre class="code-cell"><code>${sourceCodeHtml(value)}</code></pre>`;
  }
  if (isRichHtmlColumn(column) || containsHtml(value)) {
    return `<div class="rich-cell">${safeRichHtml(value)}</div>`;
  }
  return escapeHtml(formatValue(value));
}

function assignFlatValue(target, key, value) {
  if (!key) return;
  const formatted = formatValue(value);
  if (formatted === "") return;
  if (target[key]) {
    target[key] = `${target[key]} | ${formatted}`;
  } else {
    target[key] = formatted;
  }
}

function flattenInto(target, prefix, value) {
  if (Array.isArray(value)) {
    if (!value.length) return;
    if (value.every((item) => item === null || typeof item !== "object")) {
      assignFlatValue(target, prefix, value);
      return;
    }
    for (const item of value) {
      if (isPlainObject(item)) {
        for (const [key, child] of Object.entries(item)) {
          flattenInto(target, `${prefix}.${key}`, child);
        }
      } else {
        assignFlatValue(target, prefix, item);
      }
    }
    return;
  }
  if (isPlainObject(value)) {
    for (const [key, child] of Object.entries(value)) {
      flattenInto(target, `${prefix}.${key}`, child);
    }
    return;
  }
  assignFlatValue(target, prefix, value);
}

function flattenRow(row) {
  const result = {};
  for (const [key, value] of Object.entries(row || {})) {
    if (Array.isArray(value) || isPlainObject(value)) {
      flattenInto(result, key, value);
    } else {
      result[key] = value;
    }
  }
  return result;
}

function flattenRows(rows) {
  return (rows || []).map(flattenRow);
}

function objectColumns(rows, preferred = [], onlyPreferred = false) {
  const all = [];
  for (const row of rows) {
    for (const key of Object.keys(row || {})) {
      if (!all.includes(key)) all.push(key);
    }
  }
  if (onlyPreferred) return preferred.filter((key) => all.includes(key));
  const known = new Set(preferred);
  const columns = [];
  for (const key of preferred) {
    if (all.includes(key) && !columns.includes(key)) columns.push(key);
    for (const childKey of all) {
      if (childKey.startsWith(`${key}.`) && !columns.includes(childKey)) columns.push(childKey);
    }
  }
  for (const key of all) {
    if (!known.has(key) && !columns.includes(key)) columns.push(key);
  }
  return columns;
}

function tableFromObjects(rows, preferred = [], options = {}) {
  if (!rows || !rows.length) return `<div class="empty">${escapeHtml(tr("noData", "Нет данных"))}</div>`;
  const flatRows = flattenRows(rows);
  const columns = objectColumns(flatRows, preferred, options.onlyPreferred);
  return `<div class="table-wrap"><table>
    <thead><tr>${columns.map((column) => `<th>${escapeHtml(column)}</th>`).join("")}</tr></thead>
    <tbody>${flatRows.map((row) => `<tr>${columns.map((column) => `<td>${renderCell(row?.[column], column)}</td>`).join("")}</tr>`).join("")}</tbody>
  </table></div>`;
}

function keyValueTable(value) {
  if (!isPlainObject(value)) return `<div class="value-text">${renderCell(value)}</div>`;
  const flat = flattenRow(value);
  const rows = Object.entries(flat).filter(([, item]) => !isEmptyDetailValue(item));
  if (!rows.length) return `<div class="empty">${escapeHtml(tr("noData", "Нет данных"))}</div>`;
  return `<div class="detail-list api-field-list">
    ${rows.map(([key, item]) => `
      <div class="detail-item api-field-item">
        <div class="detail-label">${escapeHtml(key)}</div>
        <div class="detail-value">${renderCell(item, key)}</div>
      </div>`).join("")}
  </div>`;
}

function isEmptyDetailValue(value) {
  return value === undefined || value === null || value === "" || (Array.isArray(value) && !value.length);
}

function detailList(items) {
  const rows = items.filter((item) => !isEmptyDetailValue(item.value));
  if (!rows.length) return `<div class="empty">${escapeHtml(tr("noData", "Нет данных"))}</div>`;
  return `<div class="detail-list">
    ${rows.map((item) => `
      <div class="detail-item">
        <div class="detail-label">${escapeHtml(item.label)}</div>
        <div class="detail-value">${renderCell(item.value)}</div>
      </div>`).join("")}
  </div>`;
}

function formatDateTime(value) {
  if (!value || typeof value !== "string") return value;
  const normalized = value.replace(/([+-]\d{2})(\d{2})$/, "$1:$2");
  const date = new Date(normalized);
  if (Number.isNaN(date.getTime())) return value;
  return new Intl.DateTimeFormat("ru-RU", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

function renderProjectCard(project, branch, qualityGatePeriod, versionAnalysis) {
  const previousVersion = qualityGatePeriod?.parameter || "";
  const currentVersion = project.version || versionAnalysis?.version || "";
  const previousStatus = versionAnalysis?.baseline?.qualityGateStatus || "";
  return `
    <div class="project-card">
      <div>
        <div class="project-name">${escapeHtml(project.name || meta.project || "SonarQube")}</div>
        <div class="project-meta">
          ${project.key ? `<span>${escapeHtml(project.key)}</span>` : ""}
          ${branch ? `<span>${escapeHtml(tr("branch", "Ветка: {value}", { value: branch }))}</span>` : ""}
        </div>
      </div>
      <div class="release-strip">
        <div class="release-flow">
          <div class="release-point release-before">
            <div class="release-version-row">
              <div class="release-version">${escapeHtml(previousVersion || tr("noData", "Нет данных").toLowerCase())}</div>
              ${previousStatus ? `<div class="release-status ${statusClass(previousStatus)}">${escapeHtml(translatedStatus(previousStatus))}</div>` : ""}
            </div>
            <div class="release-date">${escapeHtml(formatDateTime(project.leakPeriodDate) || "")}</div>
          </div>
          <div class="release-arrow" aria-hidden="true"></div>
          <div class="release-point release-after">
            <div class="release-version">${escapeHtml(currentVersion || tr("noData", "Нет данных").toLowerCase())}</div>
            <div class="release-date">${escapeHtml(formatDateTime(versionAnalysis?.date) || "")}</div>
          </div>
        </div>
      </div>
      ${project.tags?.length ? detailList([{ label: tr("tags", "Теги"), value: project.tags }]) : ""}
    </div>`;
}

function metricName(key) {
  if (i18n.metricNames?.[key]) return i18n.metricNames[key];
  const metric = metricCatalog[key] || {};
  return metric.name || metric.shortName || key;
}

function overviewMetricName(key) {
  return {
    new_coverage: tr("coverage", "Покрытие"),
    new_duplicated_lines_density: tr("duplicatedLinesDensity", "Дублирование строк"),
  }[key] || metricName(key);
}

function metricType(key) {
  return metricCatalog[key]?.type || "";
}

function measureValue(measure) {
  if (!measure) return "";
  const value = measure.value !== undefined ? measure.value : measure.period?.value;
  if (typeof value === "string") {
    const trimmed = value.trim();
    if ((trimmed.startsWith("{") && trimmed.endsWith("}")) || (trimmed.startsWith("[") && trimmed.endsWith("]"))) {
      try {
        return JSON.parse(trimmed);
      } catch {
        return value;
      }
    }
  }
  if (value !== undefined) return value;
  return "";
}

function cleanMetricValue(value) {
  if (Array.isArray(value)) return value.map(cleanMetricValue);
  if (!isPlainObject(value)) return value;
  const result = {};
  for (const [key, item] of Object.entries(value)) {
    if (["key", "language", "rulesUpdatedAt"].includes(key)) continue;
    result[key] = cleanMetricValue(item);
  }
  return result;
}

function parseNumeric(value) {
  const number = Number(value);
  return Number.isFinite(number) ? number : null;
}

function formatNumber(value, maximumFractionDigits = 2) {
  const number = parseNumeric(value);
  if (number === null) return formatValue(value);
  return new Intl.NumberFormat("ru-RU", { maximumFractionDigits }).format(number);
}

function formatDurationMinutes(value) {
  const minutes = parseNumeric(value);
  if (minutes === null) return formatValue(value);
  if (minutes === 0) return `0 ${tr("minuteShort", "мин")}`;
  const day = 8 * 60;
  const days = Math.floor(minutes / day);
  const hours = Math.floor((minutes % day) / 60);
  const rest = Math.round(minutes % 60);
  return [
    days ? `${days} ${tr("dayShort", "д")}` : "",
    hours ? `${hours} ${tr("hourShort", "ч")}` : "",
    rest ? `${rest} ${tr("minuteShort", "мин")}` : "",
  ].filter(Boolean).join(" ");
}

function formatEpochMillis(value) {
  const millis = parseNumeric(value);
  if (millis === null) return formatDateTime(String(value)) || formatValue(value);
  const date = new Date(millis);
  return Number.isNaN(date.getTime()) ? formatValue(value) : formatDateTime(date.toISOString());
}

function ratingLetter(value) {
  const number = parseNumeric(value);
  if (number === null) return "";
  return ["A", "B", "C", "D", "E"][Math.max(0, Math.min(4, Math.round(number) - 1))] || "";
}

function renderValueBadge(value, className = "") {
  return `<span class="metric-value-badge ${escapeHtml(className)}">${escapeHtml(value)}</span>`;
}

function renderStructuredMetricValue(value) {
  const cleaned = cleanMetricValue(value);
  if (Array.isArray(cleaned)) {
    if (!cleaned.length) return "";
    return `<div class="metric-value-list">${cleaned.map((item) => `<span class="metric-value-item">${renderStructuredMetricItem(item)}</span>`).join("")}</div>`;
  }
  if (isPlainObject(cleaned)) {
    const entries = Object.entries(cleaned).filter(([, item]) => !isEmptyDetailValue(item));
    if (!entries.length) return "";
    return `<div class="metric-value-list">${entries.map(([key, item]) => {
      const label = translatedMetricValueKey(key);
      return `<span class="metric-value-item"><span class="metric-value-label" title="${escapeHtml(key)}">${escapeHtml(label)}</span><span class="metric-value-separator">:</span><span class="metric-value-number">${renderStructuredMetricItem(item)}</span></span>`;
    }).join("")}</div>`;
  }
  return renderStructuredMetricItem(cleaned);
}

function renderStructuredMetricItem(value) {
  if (Array.isArray(value)) return escapeHtml(value.map(formatStructuredMetricScalar).filter(Boolean).join(", "));
  if (isPlainObject(value)) return escapeHtml(formatValue(value));
  return escapeHtml(formatStructuredMetricScalar(value));
}

function formatStructuredMetricScalar(value) {
  if (typeof value !== "string") return formatValue(value);
  const parts = value.split("=");
  if (parts.length > 1) {
    return `${parts[0]}=${parts.slice(1).join("=")}`;
  }
  return translatedSeverity(translatedStatus(value));
}

function renderMetricValue(measure) {
  const type = metricType(measure.metric);
  const value = cleanMetricValue(measureValue(measure));
  if (value === "" || value === undefined || value === null) return "";
  if (type === "PERCENT") return `${escapeHtml(formatNumber(value, 2))} %`;
  if (type === "RATING") {
    const letter = ratingLetter(value);
    return letter ? renderValueBadge(letter, `rating-${letter.toLowerCase()}`) : escapeHtml(formatValue(value));
  }
  if (type === "WORK_DUR") return escapeHtml(formatDurationMinutes(value));
  if (type === "MILLISEC") return escapeHtml(formatEpochMillis(value));
  if (type === "BOOL") return renderValueBadge(value === true || value === "true" ? tr("yes", "Да") : tr("no", "Нет"), value === true || value === "true" ? "status-ok" : "status-neutral");
  if (type === "LEVEL") return renderValueBadge(translatedStatus(value), statusClass(value));
  if (type === "INT") return escapeHtml(formatNumber(value, 0));
  if (type === "FLOAT") return escapeHtml(formatNumber(value, 2));
  if (type === "DATA" || Array.isArray(value) || isPlainObject(value)) return renderStructuredMetricValue(value);
  return escapeHtml(formatValue(value));
}

function renderMetricTable(rows) {
  if (!rows.length) return `<div class="empty">${escapeHtml(tr("noData", "Нет данных"))}</div>`;
  return `<div class="table-wrap metric-table-wrap"><table class="metric-table">
    <thead>
      <tr>
        <th>${escapeHtml(tr("metricDomainColumn", "Домен"))}</th>
        <th>${escapeHtml(tr("metricNameColumn", "Название"))}</th>
        <th>${escapeHtml(tr("metricValueColumn", "Значение"))}</th>
      </tr>
    </thead>
    <tbody>
      ${rows.map((row) => `<tr class="metric-row ${row.isStructured ? "metric-row-structured" : ""}" data-domain="${escapeHtml(row.domain)}" data-search="${escapeHtml(jsonText({ key: row.key, name: row.name, domain: row.domainLabel, value: row.searchValue }).toLowerCase())}">
        <td class="metric-domain">${escapeHtml(row.domainLabel || tr("noDomain", "Без домена"))}</td>
        <td class="metric-name"><span title="${escapeHtml(row.key)}">${escapeHtml(row.name)}</span></td>
        <td class="metric-value">${row.valueHtml}</td>
      </tr>`).join("")}
    </tbody>
  </table>
  </div>`;
}

function renderMetricDomainOptions(domains) {
  return `<option value="">${escapeHtml(tr("allMetricDomains", "Все домены"))}</option>${domains.map((domain) => `<option value="${escapeHtml(domain)}">${escapeHtml(domain ? translatedMetricDomain(domain) : tr("noDomain", "Без домена"))}</option>`).join("")}`;
}

function projectMeasure(metric) {
  return (raw.project_measures?.measures || []).find((item) => item.metric === metric);
}

function projectMeasureNumber(metric) {
  const value = parseNumeric(measureValue(projectMeasure(metric)));
  return value === null ? null : value;
}

function formatCount(value) {
  const number = parseNumeric(value);
  return number === null ? formatValue(value) : String(Math.trunc(number));
}

function formatCountPair(newCount, totalCount) {
  return newCount === null
    ? formatCount(totalCount)
    : `${formatCount(newCount)}/${formatCount(totalCount)}`;
}

function sumKnownCounts(...counts) {
  return counts.some((count) => count !== null)
    ? counts.reduce((sum, count) => sum + (count ?? 0), 0)
    : null;
}

function baseMetricForNewMetric(metric) {
  return {
    new_coverage: "coverage",
    new_duplicated_lines_density: "duplicated_lines_density",
  }[metric] || "";
}

function renderMetricValuePair(metric, newValue) {
  const baseMetric = baseMetricForNewMetric(metric);
  if (!baseMetric) return renderMetricValue({ metric, value: newValue });
  const baseMeasure = projectMeasure(baseMetric);
  if (!baseMeasure) return renderMetricValue({ metric, value: newValue });
  if (metricType(metric) === "PERCENT" && metricType(baseMetric) === "PERCENT") {
    return `${escapeHtml(formatNumber(newValue, 2))} / ${escapeHtml(formatNumber(measureValue(baseMeasure), 2))} %`;
  }
  return [
    renderMetricValue({ metric, value: newValue }),
    renderMetricValue(baseMeasure),
  ].join(" / ");
}

function renderMeasurePair(measuresByMetric, newMetric, totalMetric) {
  const newMeasure = measuresByMetric.get(newMetric);
  const totalMeasure = measuresByMetric.get(totalMetric);
  if (!newMeasure && !totalMeasure) return "";
  if (metricType(newMetric) === "PERCENT" && metricType(totalMetric) === "PERCENT") {
    const newValue = newMeasure ? measureValue(newMeasure) : "";
    const totalValue = totalMeasure ? measureValue(totalMeasure) : "";
    if (newValue !== "" && totalValue !== "") {
      return `${escapeHtml(formatNumber(newValue, 2))} / ${escapeHtml(formatNumber(totalValue, 2))} %`;
    }
  }
  return [
    newMeasure ? renderMetricValue(newMeasure) : "",
    totalMeasure ? renderMetricValue(totalMeasure) : "",
  ].filter(Boolean).join(" / ");
}

function qualityGateDetailsMeasure() {
  const measure = projectMeasure("quality_gate_details");
  const value = measureValue(measure);
  return isPlainObject(value) ? value : {};
}

function qualityGateConditions() {
  const details = qualityGateDetailsMeasure();
  const detailedConditions = Array.isArray(details.conditions) ? details.conditions : [];
  if (detailedConditions.length) return detailedConditions;
  return raw.quality_gate?.projectStatus?.conditions || [];
}

function renderQualityGateConditionCards() {
  const gate = raw.quality_gate?.projectStatus || {};
  return qualityGateConditions().filter((condition) => {
    const key = condition.metricKey || condition.metric || "";
    return key !== "new_violations";
  }).map((condition) => {
    const key = condition.metricKey || condition.metric || "";
    const actual = condition.actualValue ?? condition.actual ?? "";
    const status = condition.status || condition.level || gate.status || "";
    return `<article class="card quality-condition-card ${escapeHtml(statusClass(status))}">
      <div class="card-title">${escapeHtml(overviewMetricName(key))}</div>
      <div class="card-value">${renderMetricValuePair(key, actual)}</div>
    </article>`;
  }).join("");
}

function issueSeverityCounts(issues) {
  const counts = { BLOCKER: 0, CRITICAL: 0, MAJOR: 0, MINOR: 0, INFO: 0 };
  for (const issue of issues) {
    const severity = String(issue.severity || "").toUpperCase();
    if (severity in counts) counts[severity] += 1;
  }
  return counts;
}

function severityClass(value) {
  const severity = String(value || "").trim().toUpperCase();
  if (severity === "BLOCKER") return "severity-blocker";
  if (severity === "CRITICAL" || severity === "HIGH") return "severity-critical";
  if (severity === "MAJOR" || severity === "MEDIUM") return "severity-major";
  if (severity === "MINOR" || severity === "LOW") return "severity-minor";
  if (severity === "INFO") return "severity-info";
  return "";
}

function severityCountClass(severity, count) {
  return count ? severityClass(severity) || "severity-info" : "severity-empty";
}

function renderSeverityBadge(value) {
  if (!value) return "";
  return `<span class="severity-badge ${escapeHtml(severityClass(value))}" title="${escapeHtml(value)}">${escapeHtml(translatedSeverity(value))}</span>`;
}

function issueImpactBadges(issue) {
  const impacts = Array.isArray(issue.impacts)
    ? issue.impacts
    : (isPlainObject(issue.impacts) ? [issue.impacts] : []);
  const badges = [];
  const seen = new Set();
  for (const impact of impacts) {
    const quality = String(impact.softwareQuality || "").trim();
    const severity = String(impact.severity || "").trim();
    if (quality && !seen.has(`quality:${quality}`)) {
      badges.push(`<span class="badge" title="${escapeHtml(quality)}">${escapeHtml(translatedSoftwareQuality(quality))}</span>`);
      seen.add(`quality:${quality}`);
    }
    if (severity && !seen.has(`severity:${severity}`)) {
      badges.push(renderSeverityBadge(severity));
      seen.add(`severity:${severity}`);
    }
  }
  return badges.join("");
}

function renderSeverityCount(severity, count, newCount = null) {
  return `<span class="severity-count ${severityCountClass(severity, count)}" title="${escapeHtml(severity)}"><span class="severity-count-label">${escapeHtml(translatedSeverity(severity))}</span><span class="severity-count-separator">:</span><span class="severity-count-value">${escapeHtml(formatCountPair(newCount, count))}</span></span>`;
}

function problemCardClass(counts) {
  if (counts.BLOCKER > 0 || counts.CRITICAL > 0) return "status-error";
  if (counts.MAJOR > 0 || counts.MINOR > 0) return "status-warn";
  return "status-neutral";
}

function renderProblemsCard(issueCount, hotspotCount, severityCounts, newIssueCount, newHotspotCount, newSeverityCounts) {
  const problemCount = issueCount + hotspotCount;
  const newProblemCount = sumKnownCounts(newIssueCount, newHotspotCount);
  return `<article id="problems" class="card problems-card ${escapeHtml(problemCardClass(severityCounts))}">
    <div class="card-title">${escapeHtml(tr("problems", "Проблемы"))}</div>
    <div class="card-value">${escapeHtml(formatCountPair(newProblemCount, problemCount))}</div>
    <div class="card-sub">
      <div class="severity-counts">
        ${severityCounts.BLOCKER ? renderSeverityCount("BLOCKER", severityCounts.BLOCKER, newSeverityCounts.BLOCKER) : ""}
        ${renderSeverityCount("CRITICAL", severityCounts.CRITICAL, newSeverityCounts.CRITICAL)}
        ${renderSeverityCount("MAJOR", severityCounts.MAJOR, newSeverityCounts.MAJOR)}
        ${renderSeverityCount("MINOR", severityCounts.MINOR, newSeverityCounts.MINOR)}
        ${renderSeverityCount("INFO", severityCounts.INFO, newSeverityCounts.INFO)}
      </div>
    </div>
  </article>`;
}

function renderQualityGateBadge(status) {
  const value = status ? translatedStatus(status) : tr("noData", "Нет данных").toLowerCase();
  return `<span class="quality-gate-badge ${escapeHtml(statusClass(status))}">${escapeHtml(tr("qualityGate", "Критерий качества: {value}", { value }))}</span>`;
}

function renderOverview() {
  const project = raw.project?.component || {};
  const gate = raw.quality_gate?.projectStatus || {};
  const qualityGatePeriod = gate.period || {};
  const versionAnalysis = raw.current_version_analysis || {};
  const branches = raw.branches?.branches || [];
  const branchName = meta.branch || branches.find((branch) => branch.isMain)?.name || "";
  const issues = asItems("issues");
  const issueCount = issues.length;
  const hotspotCount = (raw.hotspots?.all?.items || raw.hotspots?.open?.items || []).length;
  const severityCounts = issueSeverityCounts(issues);
  const newIssueCount = projectMeasureNumber("new_violations");
  const newHotspotCount = projectMeasureNumber("new_security_hotspots");
  const newSeverityCounts = {
    BLOCKER: projectMeasureNumber("new_blocker_violations"),
    CRITICAL: projectMeasureNumber("new_critical_violations"),
    MAJOR: projectMeasureNumber("new_major_violations"),
    MINOR: projectMeasureNumber("new_minor_violations"),
    INFO: projectMeasureNumber("new_info_violations"),
  };

  $("#overview").innerHTML = `
    ${sectionHead(tr("navOverview", "Обзор"), undefined, renderQualityGateBadge(gate.status))}
    <div class="summary-grid">
      ${renderProblemsCard(issueCount, hotspotCount, severityCounts, newIssueCount, newHotspotCount, newSeverityCounts)}
      ${renderQualityGateConditionCards()}
    </div>
    <div class="overview-details">
      <div class="panel">
        <h3>${escapeHtml(tr("project", "Проект"))}</h3>
        ${renderProjectCard(project, branchName, qualityGatePeriod, versionAnalysis)}
      </div>
    </div>`;
}

function renderMetrics() {
  const values = raw.project_measures?.measures || [];
  const rows = values
    .filter((measure) => measure.metric !== "quality_gate_details")
    .map((measure) => {
      const metric = metricCatalog[measure.metric] || {};
      const value = cleanMetricValue(measureValue(measure));
      return {
        key: measure.metric,
        domain: metric.domain || "",
        domainLabel: metric.domain ? translatedMetricDomain(metric.domain) : tr("noDomain", "Без домена"),
        name: metricName(measure.metric),
        searchValue: formatValue(value),
        isStructured: metricType(measure.metric) === "DATA" || Array.isArray(value) || isPlainObject(value),
        valueHtml: renderMetricValue(measure),
      };
    })
    .sort((a, b) => String(a.name).localeCompare(String(b.name), "ru") || String(a.domainLabel).localeCompare(String(b.domainLabel), "ru"));
  const domains = [...new Set(rows.map((row) => row.domain))]
    .sort((a, b) => String(a).localeCompare(String(b), "ru"));

  $("#metrics").innerHTML = `
    ${sectionHead(tr("navMetrics", "Метрики"), rows.length)}
    <div class="panel">
      <div class="filters">
        <select id="metricDomain" required aria-label="${escapeHtml(tr("metricDomainAria", "Домен метрик"))}">
          ${renderMetricDomainOptions(domains)}
        </select>
        <input id="metricSearch" type="search" placeholder="${escapeHtml(tr("metricSearchPlaceholder", "Фильтр по названию или значению"))}">
      </div>
      ${renderMetricTable(rows)}
    </div>`;
  initMetricFilters("#metricDomain", "#metricSearch", "#metrics .metric-row");
}

function issueTitle(issue) {
  return issue.message || issue.key || issue.rule || tr("issue", "Нарушение");
}

function issueMetaHtml(issue) {
  const parts = [
    issue.effort,
    formatDateTime(issue.updateDate),
  ].filter(Boolean);
  return parts.length ? `<div class="record-meta">${parts.map(escapeHtml).join(" · ")}</div>` : "";
}

function numericLine(value) {
  const line = Number(value);
  return Number.isFinite(line) && line > 0 ? line : null;
}

function renderSourceSnippet(item) {
  const component = item.component;
  const source = raw.source_files?.[component];
  const lines = source?.sources || [];
  if (!lines.length) return `<div class="empty">${escapeHtml(tr("sourceUnavailable", "Исходный код недоступен или не был возвращен API"))}</div>`;

  const startLine = numericLine(item.textRange?.startLine) || numericLine(item.line);
  const endLine = numericLine(item.textRange?.endLine) || startLine;
  if (!startLine) return `<div class="empty">${escapeHtml(tr("sourceLineMissing", "Строка кода не указана"))}</div>`;

  const maxLine = Math.max(...lines.map((line) => numericLine(line.line) || 0));
  let contextStartLine = Math.max(1, startLine - 1);
  let contextEndLine = Math.min(maxLine || endLine + 1, endLine + 1);
  let issueLines = lines.filter((line) => {
    const number = numericLine(line.line);
    return number && number >= contextStartLine && number <= contextEndLine;
  });
  while (issueLines.length < 3 && (contextStartLine > 1 || contextEndLine < maxLine)) {
    if (contextStartLine > 1) contextStartLine -= 1;
    if (issueLines.length < 3 && contextEndLine < maxLine) contextEndLine += 1;
    issueLines = lines.filter((line) => {
      const number = numericLine(line.line);
      return number && number >= contextStartLine && number <= contextEndLine;
    });
  }
  if (!issueLines.length) return `<div class="empty">${escapeHtml(tr("sourceLineNotFound", "Код строки {line} не найден в исходнике", { line: startLine }))}</div>`;

  const codeLines = issueLines.map((line) => {
    const number = numericLine(line.line);
    const isTarget = number && number >= startLine && number <= endLine;
    return `<span class="issue-code-line ${isTarget ? "is-issue-line" : ""}"><span class="issue-code-number">${escapeHtml(line.line)}</span><span class="issue-code-text">${sourceCodeHtml(line.code)}</span></span>`;
  }).join("");
  return `<pre class="issue-code-block"><code>${codeLines}</code></pre>`;
}

function issueFields(issue) {
  const result = { ...issue };
  delete result.key;
  delete result.rule;
  delete result.message;
  delete result.component;
  delete result.line;
  delete result.severity;
  delete result.impactSeverity;
  delete result.type;
  delete result.creationDate;
  delete result.updateDate;
  delete result.effort;
  delete result.issueStatus;
  delete result.status;
  delete result.impacts;
  delete result.tags;
  return result;
}

function hotspotFields(hotspot) {
  const detail = raw.hotspot_details?.[hotspot.key] || {};
  const rule = detail.rule || {};
  return {
    ruleKey: hotspot.ruleKey || rule.key,
    ruleName: rule.name,
    message: hotspot.message,
    updateDate: hotspot.updateDate,
  };
}

function issueDetailHtml(issue) {
  return renderSourceSnippet(issue);
}

function hotspotDetailHtml(hotspot) {
  return renderSourceSnippet(hotspot);
}

function filterValues(values) {
  return [...new Set(values.filter(Boolean))]
    .sort((a, b) => String(a).localeCompare(String(b), "ru"));
}

function renderFilterOptions(values, allLabel, label = (value) => value) {
  return `<option value="">${escapeHtml(allLabel)}</option>${values.map((value) => `<option value="${escapeHtml(value)}">${escapeHtml(label(value))}</option>`).join("")}`;
}

function renderRequiredFilterOptions(values, label = (value) => value) {
  return values.map((value) => `<option value="${escapeHtml(value)}">${escapeHtml(label(value))}</option>`).join("");
}

function normalizedSearchData(value) {
  if (Array.isArray(value)) return value.map(normalizedSearchData);
  if (value && typeof value === "object") {
    return Object.fromEntries(Object.entries(value).map(([key, item]) => [key, normalizedSearchData(item)]));
  }
  if (typeof value === "string") return stripProjectPrefix(value);
  return value;
}

function issueFilterData(issue) {
    return {
      kind: "issue",
      severity: issue.severity || issue.impactSeverity || "",
      type: issue.type || "",
      rule: issue.rule || "",
    };
}

function hotspotFilterData(hotspot) {
  const detail = raw.hotspot_details?.[hotspot.key] || {};
  const rule = detail.rule || {};
  return {
    kind: "hotspot",
    severity: "",
    type: "",
    rule: hotspot.ruleKey || rule.key || "",
  };
}

function renderIssues() {
  const issues = asItems("issues");
  const hotspots = raw.hotspots?.all?.items || raw.hotspots?.open?.items || [];
  const issueRows = issues.map((issue) => {
    const filters = issueFilterData(issue);
    return {
      component: issue.component || "",
      line: numericLine(issue.line) || 0,
      kind: 0,
      filters,
      html: `
    <article class="record issue-record" data-search="${escapeHtml(jsonText(normalizedSearchData(issue)).toLowerCase())}" data-kind="${escapeHtml(filters.kind)}" data-severity="${escapeHtml(filters.severity)}" data-type="${escapeHtml(filters.type)}" data-rule="${escapeHtml(filters.rule)}">
      <div class="record-main">
        <div>
          <div class="record-title">${escapeHtml(issueTitle(issue))}</div>
          <div class="muted">${escapeHtml([componentFilePath(issue.component), issue.line].filter(Boolean).join(":"))}</div>
          ${issueMetaHtml(issue)}
        </div>
        <div class="badges">
          <span class="badge">${escapeHtml(tr("issue", "Нарушение"))}</span>
          ${renderSeverityBadge(issue.severity || issue.impactSeverity)}
          ${issue.type ? `<span class="badge" title="${escapeHtml(issue.type)}">${escapeHtml(translatedIssueType(issue.type))}</span>` : ""}
          ${issueImpactBadges(issue)}
        </div>
      </div>
      <div class="issue-code-section">${issueDetailHtml(issue)}</div>
    </article>`,
    };
  });

  const hotspotRows = hotspots.map((hotspot) => {
    const details = hotspotFields(hotspot);
    const filters = hotspotFilterData(hotspot);
    const hotspotDetail = raw.hotspot_details?.[hotspot.key] || {};
    const hotspotRule = hotspotDetail.rule || {};
    const vulnerabilityProbability = hotspot.vulnerabilityProbability || hotspotRule.vulnerabilityProbability;
    const securityCategory = hotspot.securityCategory || hotspotRule.securityCategory;
    return {
      component: hotspot.component || "",
      line: numericLine(hotspot.line) || 0,
      kind: 1,
      filters,
      html: `
      <article class="record hotspot-record" data-search="${escapeHtml(jsonText(normalizedSearchData({ ...details, status: hotspot.status, vulnerabilityProbability, securityCategory })).toLowerCase())}" data-kind="${escapeHtml(filters.kind)}" data-severity="${escapeHtml(filters.severity)}" data-type="${escapeHtml(filters.type)}" data-rule="${escapeHtml(filters.rule)}">
        <div class="record-main">
          <div>
            <div class="record-title">${escapeHtml(hotspot.message || details.ruleName || hotspot.key)}</div>
            <div class="muted">${escapeHtml([componentFilePath(hotspot.component), hotspot.line].filter(Boolean).join(":"))}</div>
          </div>
          <div class="badges">
            <span class="badge">${escapeHtml(tr("hotspot", "Потенциальная уязвимость"))}</span>
            ${hotspot.status ? `<span class="badge" title="${escapeHtml(hotspot.status)}">${escapeHtml(translatedHotspotStatus(hotspot.status))}</span>` : ""}
            ${renderSeverityBadge(vulnerabilityProbability)}
            ${securityCategory ? `<span class="badge" title="${escapeHtml(securityCategory)}">${escapeHtml(translatedSecurityCategory(securityCategory))}</span>` : ""}
          </div>
        </div>
        <div class="issue-code-section">${hotspotDetailHtml(hotspot)}</div>
      </article>`,
    };
  });
  const rows = [...issueRows, ...hotspotRows]
    .sort((a, b) => String(a.component).localeCompare(String(b.component), "ru") || a.line - b.line || a.kind - b.kind)
    .map((row) => row.html)
    .join("");
  const allRows = [...issueRows, ...hotspotRows];

  $("#issues").innerHTML = `
    ${sectionHead(tr("issues", "Нарушения"), issues.length + hotspots.length)}
    <details id="issuesDetails" class="collapsible-panel">
      <summary id="issuesDetailsSummary">${escapeHtml(tr("showAllIssues", "Показать общую таблицу нарушений"))}</summary>
      <div class="panel issues-panel">
        <div class="filters">
          <select id="issueKind" aria-label="${escapeHtml(tr("issueKindAria", "Тип записи"))}">
            <option value="">${escapeHtml(tr("issueKindAll", "Все записи"))}</option>
            <option value="issue">${escapeHtml(tr("issueKindIssues", "Нарушения"))}</option>
            <option value="hotspot">${escapeHtml(tr("issueKindHotspots", "Потенциальные уязвимости"))}</option>
          </select>
          <select id="issueSeverity" aria-label="${escapeHtml(tr("severityColumn", "Критичность"))}">${renderFilterOptions(filterValues(allRows.map((row) => row.filters.severity)), tr("issueSeverityAny", "Любая критичность"), translatedSeverity)}</select>
          <select id="issueType" aria-label="${escapeHtml(tr("typeColumn", "Тип"))}">${renderFilterOptions(filterValues(allRows.map((row) => row.filters.type)), tr("issueTypeAny", "Любой тип"), translatedIssueType)}</select>
          <select id="issueRule" aria-label="${escapeHtml(tr("issueRuleAria", "Правило"))}">${renderFilterOptions(filterValues(allRows.map((row) => row.filters.rule)), tr("issueRuleAny", "Любое правило"))}</select>
          <input id="issueSearch" type="search" placeholder="${escapeHtml(tr("issueSearchPlaceholder", "Фильтр по нарушениям и потенциальным уязвимостям"))}">
        </div>
        <div id="issuesList" class="record-list issues-scroll">${rows || `<div class="empty">${escapeHtml(tr("noData", "Нет данных"))}</div>`}</div>
      </div>
    </details>`;

  initIssueFilters("#issues .record");
  initIssuesDetailsSummary();
}

function initIssuesDetailsSummary() {
  const details = $("#issuesDetails");
  const summary = $("#issuesDetailsSummary");
  if (!details || !summary) return;

  const syncSummary = () => {
    summary.textContent = details.open
      ? tr("hideAllIssues", "Скрыть общую таблицу нарушений")
      : tr("showAllIssues", "Показать общую таблицу нарушений");
  };

  details.addEventListener("toggle", syncSummary);
  syncSummary();
}

function renderFiles() {
  const components = asItems("file_measures");
  const issues = asItems("issues");
  const issueStats = fileIssueStats(issues, asItems("new_issues"));
  const hasNewIssueData = Array.isArray(raw.new_issues?.items);
  const rows = fileTreeRows(components, issueStats, hasNewIssueData);

  $("#files").innerHTML = `
    ${sectionHead(tr("files", "Файлы"), components.length)}
    <div class="panel">
      <div class="filters"><input id="fileSearch" type="search" placeholder="${escapeHtml(tr("fileSearchPlaceholder", "Фильтр по любому полю файла"))}"></div>
      <div class="file-browser">
        <div class="table-wrap file-table-wrap">
          <table>
            <thead>
              <tr>
                <th>${escapeHtml(tr("fileColumn", "Файл"))}</th>
                <th>${escapeHtml(tr("issuesColumn", "Нарушения"))}</th>
                <th>${escapeHtml(tr("severityColumn", "Критичность"))}</th>
                <th>${escapeHtml(tr("coverageColumn", "Покрытие"))}</th>
                <th>${escapeHtml(tr("duplicationsColumn", "Дублирование"))}</th>
                <th>${escapeHtml(tr("linesColumn", "Строки"))}</th>
                <th>${escapeHtml(tr("complexityColumn", "Сложность"))}</th>
              </tr>
            </thead>
            <tbody>${rows || `<tr><td colspan="7" class="empty">${escapeHtml(tr("noData", "Нет данных"))}</td></tr>`}</tbody>
          </table>
        </div>
        <aside id="fileIssuePanel" class="file-issue-panel" aria-live="polite"></aside>
      </div>
    </div>`;
  const syncFilePanelHeight = initFilePanelHeight();
  initFileTreeFilter("#fileSearch", syncFilePanelHeight);
  initFileNavigator(issues);
}

function initFilePanelHeight() {
  const browser = $("#files .file-browser");
  const tableWrap = $("#files .file-table-wrap");
  if (!browser || !tableWrap) return () => {};

  const sync = () => {
    browser.style.setProperty("--file-table-height", `${Math.ceil(tableWrap.getBoundingClientRect().height)}px`);
  };

  sync();
  if ("ResizeObserver" in window) {
    const observer = new ResizeObserver(sync);
    observer.observe(tableWrap);
  }
  window.addEventListener("resize", sync);
  return sync;
}

function componentFilePath(component) {
  const value = String(component || "");
  const separator = value.indexOf(":");
  return separator >= 0 ? value.slice(separator + 1) : value;
}

function stripProjectPrefix(value) {
  const text = String(value || "");
  const projectKey = meta.project || raw.project?.component?.key || "";
  const prefix = projectKey ? `${projectKey}:` : "";
  return prefix && text.startsWith(prefix) ? text.slice(prefix.length) : text;
}

function shortFilePath(path) {
  const parts = String(path || "").split(/[\\/]+/).filter(Boolean);
  if (parts.length <= 4) return path;
  return `.../${parts.slice(-4).join("/")}`;
}

function fileTreeDisplayParts(path) {
  const parts = String(path || "").split(/[\\/]+/).filter(Boolean);
  return parts[0]?.toLowerCase() === "src" ? parts.slice(1) : parts;
}

function fileTreePath(parts) {
  return parts.join("/");
}

function fileTreeFilterPath(displayPath) {
  return displayPath ? `src/${displayPath}` : "";
}

function fileTreeRows(components, issueStats, hasNewIssueData) {
  const root = { name: "", children: new Map(), files: [] };
  for (const component of components) {
    const path = component.path || component.name || "";
    const parts = fileTreeDisplayParts(path);
    const displayParts = parts.length ? parts : [path || component.name || ""].filter(Boolean);
    if (!displayParts.length) {
      root.files.push({ component, label: path || component.name || "" });
      continue;
    }
    let node = root;
    for (const part of displayParts.slice(0, -1)) {
      if (!node.children.has(part)) node.children.set(part, { name: part, children: new Map(), files: [] });
      node = node.children.get(part);
    }
    node.files.push({ component, label: displayParts[displayParts.length - 1] });
  }

  const rows = [];
  const sortByName = (a, b) => String(a.name || a.label || "").localeCompare(String(b.name || b.label || ""), "ru");
  const aggregateNode = (node) => {
    const result = {
      files: node.files.length,
      total: 0,
      new: hasNewIssueData ? 0 : null,
      severities: [],
      lines: 0,
      complexity: 0,
      coverage: weightedMetricAccumulator(),
      newCoverage: weightedMetricAccumulator(),
      duplications: weightedMetricAccumulator(),
      newDuplications: weightedMetricAccumulator(),
    };
    for (const { component } of node.files) {
      const path = component.path || component.name || "";
      const measuresByMetric = fileMeasuresByMetric(component);
      const stats = issueStats.get(path) || { total: 0, new: hasNewIssueData ? 0 : null, severities: [] };
      const lines = fileMeasureNumber(measuresByMetric, "lines");
      const newLines = fileMeasureNumber(measuresByMetric, "new_lines");
      const linesToCover = fileMeasureNumber(measuresByMetric, "lines_to_cover");
      const newLinesToCover = fileMeasureNumber(measuresByMetric, "new_lines_to_cover");
      const complexity = fileMeasureNumber(measuresByMetric, "complexity");
      result.total += stats.total || 0;
      if (hasNewIssueData) result.new += stats.new || 0;
      result.severities.push(...(stats.severities || []));
      if (lines !== null) result.lines += lines;
      if (complexity !== null) result.complexity += complexity;
      addWeightedMetric(result.coverage, fileMeasureNumber(measuresByMetric, "coverage"), linesToCover ?? lines);
      addWeightedMetric(result.newCoverage, fileMeasureNumber(measuresByMetric, "new_coverage"), newLinesToCover ?? newLines ?? lines);
      addWeightedMetric(result.duplications, fileMeasureNumber(measuresByMetric, "duplicated_lines_density"), lines);
      addWeightedMetric(result.newDuplications, fileMeasureNumber(measuresByMetric, "new_duplicated_lines_density"), newLines ?? lines);
    }
    for (const child of node.children.values()) {
      const stats = aggregateNode(child);
      result.files += stats.files;
      result.total += stats.total;
      if (hasNewIssueData) result.new += stats.new || 0;
      result.severities.push(...stats.severities);
      result.lines += stats.lines || 0;
      result.complexity += stats.complexity || 0;
      mergeWeightedMetric(result.coverage, stats.coverage);
      mergeWeightedMetric(result.newCoverage, stats.newCoverage);
      mergeWeightedMetric(result.duplications, stats.duplications);
      mergeWeightedMetric(result.newDuplications, stats.newDuplications);
    }
    node.stats = result;
    return result;
  };
  aggregateNode(root);

  const renderNode = (node, depth, parentId, parts) => {
    const children = [...node.children.values()].sort(sortByName);
    const files = [...node.files].sort(sortByName);
    for (const child of children) {
      const childParts = [...parts, child.name];
      const id = fileTreePath(childParts);
      rows.push(fileFolderRow(child, depth, parentId, id, childParts, hasNewIssueData));
      renderNode(child, depth + 1, id, childParts);
    }
    for (const file of files) {
      rows.push(fileRow(file.component, issueStats, hasNewIssueData, {
        depth,
        label: file.label,
        parentId,
        displayPath: fileTreePath([...parts, file.label]),
      }));
    }
  };

  renderNode(root, 0, "", []);
  return rows.join("");
}

function fileMeasuresByMetric(component) {
  return new Map((component.measures || []).map((measure) => [measure.metric, measure]));
}

function fileMeasureNumber(measuresByMetric, metric) {
  const value = parseNumeric(measureValue(measuresByMetric.get(metric)));
  return value === null ? null : value;
}

function weightedMetricAccumulator() {
  return { weightedSum: 0, weight: 0, fallbackSum: 0, count: 0 };
}

function addWeightedMetric(accumulator, value, weight) {
  if (value === null) return;
  const metricWeight = weight && weight > 0 ? weight : 0;
  if (metricWeight) {
    accumulator.weightedSum += value * metricWeight;
    accumulator.weight += metricWeight;
  } else {
    accumulator.fallbackSum += value;
    accumulator.count += 1;
  }
}

function mergeWeightedMetric(target, source) {
  target.weightedSum += source.weightedSum;
  target.weight += source.weight;
  target.fallbackSum += source.fallbackSum;
  target.count += source.count;
}

function weightedMetricValue(accumulator) {
  if (accumulator.weight > 0) return accumulator.weightedSum / accumulator.weight;
  if (accumulator.count > 0) return accumulator.fallbackSum / accumulator.count;
  return null;
}

function renderAggregatedPercentPair(newAccumulator, totalAccumulator) {
  const newValue = weightedMetricValue(newAccumulator);
  const totalValue = weightedMetricValue(totalAccumulator);
  if (newValue === null && totalValue === null) return "";
  if (newValue !== null && totalValue !== null) {
    return `${escapeHtml(formatNumber(newValue, 2))} / ${escapeHtml(formatNumber(totalValue, 2))} %`;
  }
  const value = newValue !== null ? newValue : totalValue;
  return `${escapeHtml(formatNumber(value, 2))} %`;
}

function fileFolderRow(node, depth, parentId, id, parts, hasNewIssueData) {
  const stats = node.stats || { files: 0, total: 0, new: hasNewIssueData ? 0 : null, severities: [] };
  const displayPath = fileTreePath(parts);
  const searchData = {
    path: displayPath,
    issues: `${stats.new ?? ""}/${stats.total}`,
    severity: worstSeverity(stats.severities),
    coverage: [
      weightedMetricValue(stats.newCoverage),
      weightedMetricValue(stats.coverage),
    ],
    duplications: [
      weightedMetricValue(stats.newDuplications),
      weightedMetricValue(stats.duplications),
    ],
    lines: stats.lines,
    complexity: stats.complexity,
  };
  return `
    <tr class="file-row file-tree-row file-tree-folder" data-tree-id="${escapeHtml(id)}" data-tree-parent="${escapeHtml(parentId)}" data-search="${escapeHtml(jsonText(searchData).toLowerCase())}">
      <td>
        <button class="file-tree-toggle is-collapsed" type="button" data-tree-toggle="${escapeHtml(id)}" data-folder-select="${escapeHtml(displayPath)}" data-folder-filter="${escapeHtml(fileTreeFilterPath(displayPath))}" aria-expanded="false" style="--tree-depth:${depth}">
          <span class="file-tree-caret" aria-hidden="true"></span>
          <span class="file-tree-name">${escapeHtml(node.name)}</span>
          <span class="file-tree-count">${escapeHtml(String(stats.files))}</span>
        </button>
      </td>
      <td>${escapeHtml(formatCountPair(stats.new, stats.total))}</td>
      <td>${renderSeverityBadge(searchData.severity)}</td>
      <td>${renderAggregatedPercentPair(stats.newCoverage, stats.coverage)}</td>
      <td>${renderAggregatedPercentPair(stats.newDuplications, stats.duplications)}</td>
      <td>${escapeHtml(formatNumber(stats.lines, 0))}</td>
      <td>${escapeHtml(formatNumber(stats.complexity, 0))}</td>
    </tr>`;
}

function worstSeverity(severities) {
  const rank = { BLOCKER: 5, CRITICAL: 4, MAJOR: 3, MINOR: 2, INFO: 1 };
  return severities
    .map((severity) => String(severity || "").toUpperCase())
    .filter(Boolean)
    .sort((a, b) => (rank[b] || 0) - (rank[a] || 0))[0] || "";
}

function fileIssueStats(issues, newIssues) {
  const stats = new Map();
  const ensure = (path) => {
    if (!stats.has(path)) stats.set(path, { total: 0, new: 0, severities: [] });
    return stats.get(path);
  };
  for (const issue of issues || []) {
    const path = componentFilePath(issue.component);
    if (!path) continue;
    const stat = ensure(path);
    stat.total += 1;
    stat.severities.push(issue.severity || issue.impactSeverity);
  }
  for (const issue of newIssues || []) {
    const path = componentFilePath(issue.component);
    if (!path) continue;
    ensure(path).new += 1;
  }
  return stats;
}

function issuesByFile(issues) {
  const result = new Map();
  for (const [index, issue] of (issues || []).entries()) {
    const path = componentFilePath(issue.component);
    if (!path) continue;
    if (!result.has(path)) result.set(path, []);
    result.get(path).push({ issue, index });
  }
  for (const items of result.values()) {
    items.sort((a, b) => (numericLine(a.issue.line) || 0) - (numericLine(b.issue.line) || 0) || issueTitle(a.issue).localeCompare(issueTitle(b.issue), "ru"));
  }
  return result;
}

function issuesByFolder(issues) {
  const result = new Map();
  for (const [index, issue] of (issues || []).entries()) {
    const path = componentFilePath(issue.component);
    const parts = fileTreeDisplayParts(path);
    if (parts.length < 2) continue;
    for (let length = 1; length < parts.length; length += 1) {
      const folderPath = fileTreePath(parts.slice(0, length));
      if (!result.has(folderPath)) result.set(folderPath, []);
      result.get(folderPath).push({ issue, index });
    }
  }
  for (const items of result.values()) {
    items.sort((a, b) => {
      const pathA = componentFilePath(a.issue.component);
      const pathB = componentFilePath(b.issue.component);
      return pathA.localeCompare(pathB, "ru")
        || (numericLine(a.issue.line) || 0) - (numericLine(b.issue.line) || 0)
        || issueTitle(a.issue).localeCompare(issueTitle(b.issue), "ru");
    });
  }
  return result;
}

function renderFileIssueRecord(issue, index) {
  return `
    <article class="record issue-record file-issue-record">
      <div class="record-main">
        <div>
          <div class="record-title">${escapeHtml(issueTitle(issue))}</div>
          ${issue.rule ? `<div class="record-rule">${escapeHtml(issue.rule)}</div>` : ""}
          ${issueMetaHtml(issue)}
        </div>
        <div class="badges">
          ${renderSeverityBadge(issue.severity || issue.impactSeverity)}
          ${issue.type ? `<span class="badge" title="${escapeHtml(issue.type)}">${escapeHtml(translatedIssueType(issue.type))}</span>` : ""}
          ${issueImpactBadges(issue)}
        </div>
      </div>
      <div class="issue-code-section">${issueDetailHtml(issue)}</div>
    </article>`;
}

function renderFileIssuePanel(path, fileIssues, filterPath = path) {
  const title = path || tr("fileNotSelected", "Файл не выбран");
  const issueCount = fileIssues.length;
  return `
    <div class="file-issue-head">
      <div>
        <h3>${escapeHtml(tr("fileIssuesTitle", "Нарушения файла"))}</h3>
        <div class="muted" title="${escapeHtml(title)}">${escapeHtml(title)}</div>
      </div>
      ${filterPath ? `<a href="#issues" data-file-filter="${escapeHtml(filterPath)}">${escapeHtml(tr("openInIssuesTable", "Открыть в общей таблице"))}</a>` : ""}
    </div>
    <div class="file-issue-count">${escapeHtml(tr("fileIssuesCount", "{count} нарушений", { count: issueCount }))}</div>
    <div class="record-list file-issue-list">
      ${fileIssues.length
        ? fileIssues.map(({ issue, index }) => renderFileIssueRecord(issue, index)).join("")
        : `<div class="empty">${escapeHtml(tr("fileIssuesEmpty", "Для выбранного файла нарушений нет"))}</div>`}
    </div>`;
}

function initFileNavigator(issues) {
  const panel = $("#fileIssuePanel");
  const links = [...document.querySelectorAll("[data-file-select]")];
  const folders = [...document.querySelectorAll("[data-folder-select]")];
  if (!panel) return;
  const issueIndex = issuesByFile(issues);
  const folderIssueIndex = issuesByFolder(issues);
  const syncSelection = (kind, path) => {
    links.forEach((link) => {
      const isSelected = kind === "file" && link.dataset.fileSelect === path;
      link.classList.toggle("is-selected", isSelected);
      link.closest(".file-row")?.classList.toggle("is-selected", isSelected);
    });
    folders.forEach((button) => {
      const isSelected = kind === "folder" && button.dataset.folderSelect === path;
      button.classList.toggle("is-selected", isSelected);
      button.closest(".file-row")?.classList.toggle("is-selected", isSelected);
    });
  };
  const selectPanel = (kind, path, title, fileIssues, filterPath, shouldScroll = false) => {
    syncSelection(kind, path);
    panel.innerHTML = renderFileIssuePanel(title, fileIssues, filterPath);
    initFileIssueLinks(panel);
    if (shouldScroll && window.matchMedia("(max-width: 1040px)").matches) {
      panel.scrollIntoView({ behavior: "smooth", block: "start" });
    }
  };
  const selectFile = (path, shouldScroll = false) => {
    selectPanel("file", path, path, issueIndex.get(path) || [], path, shouldScroll);
  };
  const selectFolder = (path, filterPath, shouldScroll = false) => {
    selectPanel("folder", path, path, folderIssueIndex.get(path) || [], filterPath, shouldScroll);
  };
  links.forEach((link) => {
    link.addEventListener("click", (event) => {
      event.preventDefault();
      selectFile(link.dataset.fileSelect || "", true);
    });
  });
  folders.forEach((button) => {
    button.addEventListener("click", () => {
      selectFolder(button.dataset.folderSelect || "", button.dataset.folderFilter || "", true);
    });
  });
  panel.innerHTML = "";
}

function fileRow(component, issueStats, hasNewIssueData, tree = {}) {
  const path = component.path || component.name || "";
  const measuresByMetric = fileMeasuresByMetric(component);
  const stats = issueStats.get(path) || { total: 0, new: hasNewIssueData ? 0 : null, severities: [] };
  const depth = Number.isFinite(tree.depth) ? tree.depth : 0;
  const label = tree.label || shortFilePath(path);
  const searchData = {
    path,
    displayPath: tree.displayPath || path,
    issues: `${stats.new ?? ""}/${stats.total}`,
    severity: worstSeverity(stats.severities),
    coverage: [
      measureValue(measuresByMetric.get("new_coverage")),
      measureValue(measuresByMetric.get("coverage")),
    ],
    duplications: [
      measureValue(measuresByMetric.get("new_duplicated_lines_density")),
      measureValue(measuresByMetric.get("duplicated_lines_density")),
    ],
    lines: measureValue(measuresByMetric.get("lines")),
    complexity: measureValue(measuresByMetric.get("complexity")),
  };
  return `
    <tr class="file-row file-tree-row file-tree-file" data-tree-parent="${escapeHtml(tree.parentId || "")}" data-search="${escapeHtml(jsonText(searchData).toLowerCase())}">
      <td><a class="file-link file-tree-file-link" href="#files" data-file-select="${escapeHtml(path)}" title="${escapeHtml(path)}" style="--tree-depth:${depth}">${escapeHtml(label)}</a></td>
      <td>${escapeHtml(formatCountPair(stats.new, stats.total))}</td>
      <td>${renderSeverityBadge(searchData.severity)}</td>
      <td>${renderMeasurePair(measuresByMetric, "new_coverage", "coverage")}</td>
      <td>${renderMeasurePair(measuresByMetric, "new_duplicated_lines_density", "duplicated_lines_density")}</td>
      <td>${renderMetricValue(measuresByMetric.get("lines"))}</td>
      <td>${renderMetricValue(measuresByMetric.get("complexity"))}</td>
    </tr>`;
}

function initFileTreeFilter(inputSelector, afterFilter = () => {}) {
  const input = $(inputSelector);
  const tbody = $("#files tbody");
  if (!input || !tbody) return;

  const rows = [...tbody.querySelectorAll(".file-row")];
  const folders = rows.filter((row) => row.classList.contains("file-tree-folder"));
  const files = rows.filter((row) => row.classList.contains("file-tree-file"));
  const folderById = new Map(folders.map((row) => [row.dataset.treeId || "", row]));
  const collapsed = new Set(folders.map((row) => row.dataset.treeId || "").filter(Boolean));

  const hasCollapsedParent = (row) => {
    let parentId = row.dataset.treeParent || "";
    while (parentId) {
      if (collapsed.has(parentId)) return true;
      parentId = folderById.get(parentId)?.dataset.treeParent || "";
    }
    return false;
  };

  const collectParents = (row, result) => {
    let parentId = row.dataset.treeParent || "";
    while (parentId) {
      result.add(parentId);
      parentId = folderById.get(parentId)?.dataset.treeParent || "";
    }
  };

  const apply = () => {
    const query = input.value.trim().toLowerCase();
    const visibleFolders = new Set();
    const matchedFiles = new Set();

    for (const row of files) {
      const matched = !query || (row.dataset.search || "").includes(query);
      if (matched) {
        matchedFiles.add(row);
        collectParents(row, visibleFolders);
      }
    }

    for (const row of folders) {
      const filterVisible = !query || visibleFolders.has(row.dataset.treeId || "");
      const treeVisible = query ? true : !hasCollapsedParent(row);
      row.hidden = !(filterVisible && treeVisible);
    }
    for (const row of files) {
      const filterVisible = matchedFiles.has(row);
      const treeVisible = query ? true : !hasCollapsedParent(row);
      row.hidden = !(filterVisible && treeVisible);
    }

    afterFilter();
  };

  tbody.querySelectorAll("[data-tree-toggle]").forEach((button) => {
    button.addEventListener("click", () => {
      const id = button.dataset.treeToggle || "";
      if (!id) return;
      if (collapsed.has(id)) {
        collapsed.delete(id);
        button.setAttribute("aria-expanded", "true");
      } else {
        collapsed.add(id);
        button.setAttribute("aria-expanded", "false");
      }
      button.classList.toggle("is-collapsed", collapsed.has(id));
      apply();
    });
  });

  input.addEventListener("input", apply);
  apply();
}

function initFileIssueLinks(root = document) {
  root.querySelectorAll("[data-file-filter]").forEach((link) => {
    link.addEventListener("click", (event) => {
      const input = $("#issueSearch");
      const issuesSection = $("#issues");
      if (!input || !issuesSection) return;
      event.preventDefault();
      const issuesDetails = $("#issuesDetails");
      if (issuesDetails) issuesDetails.open = true;
      ["#issueKind", "#issueSeverity", "#issueType", "#issueRule"].forEach((selector) => {
        const control = $(selector);
        if (control) control.value = "";
      });
      input.value = link.dataset.fileFilter || "";
      input.dispatchEvent(new Event("input", { bubbles: true }));
      issuesSection.scrollIntoView({ behavior: "smooth", block: "start" });
      history.replaceState(null, "", "#issues");
    });
  });
}

function ruleDocumentationUrl(rule) {
  const key = String(rule.key || "").trim();
  return key ? `https://1c-syntax.github.io/bsl-language-server/diagnostics/${encodeURIComponent(key)}` : "";
}

function ruleDiagnosticNameHtml(rule) {
  const name = rule.name || rule.key || "";
  const url = ruleDocumentationUrl(rule);
  const text = escapeHtml(name);
  if (!url) return text;
  return `<a href="${escapeHtml(url)}" target="_blank" rel="noopener noreferrer">${text}</a>`;
}

function issueCountsByRule(issues) {
  const counts = new Map();
  for (const issue of issues || []) {
    const rule = issue.rule;
    if (!rule) continue;
    counts.set(rule, (counts.get(rule) || 0) + 1);
  }
  return counts;
}

function renderRules() {
  const rulesByKey = {};
  for (const [key, value] of Object.entries(raw.rules || {})) {
    rulesByKey[key] = { key, source: "issues", ...(value?.rule || value || {}) };
  }
  for (const [profileKey, section] of Object.entries(raw.profile_rules || {})) {
    for (const rule of section?.items || []) {
      const key = rule.key || `${profileKey}:${rule.name || ""}`;
      rulesByKey[key] = { ...(rulesByKey[key] || {}), ...rule, key, profileKey, source: "quality profile" };
    }
  }
  const totalIssuesByRule = issueCountsByRule(asItems("issues"));
  const hasNewIssueData = Array.isArray(raw.new_issues?.items);
  const newIssuesByRule = issueCountsByRule(asItems("new_issues"));
  const ruleRows = Object.values(rulesByKey)
    .sort((a, b) => String(a.key || "").localeCompare(String(b.key || ""), "ru"))
    .map((rule) => {
      const tags = rule.tags || rule.sysTags || [];
      const totalIssueCount = totalIssuesByRule.get(rule.key) || 0;
      const newIssueCount = hasNewIssueData ? (newIssuesByRule.get(rule.key) || 0) : null;
      const filters = {
        severity: rule.severity || "",
        type: rule.type || "",
        tags,
      };
      const searchData = {
        ...rule,
        documentation: ruleDocumentationUrl(rule),
        totalIssueCount,
        newIssueCount,
      };
      return {
        filters,
        html: `
      <tr class="rule-row" data-search="${escapeHtml(jsonText(searchData).toLowerCase())}" data-severity="${escapeHtml(filters.severity)}" data-type="${escapeHtml(filters.type)}" data-tags="${escapeHtml(tags.join("\n"))}">
        <td>
          <div class="record-title">${ruleDiagnosticNameHtml(rule)}</div>
          <div class="muted">${escapeHtml(rule.key || "")}</div>
        </td>
        <td>${escapeHtml(formatCountPair(newIssueCount, totalIssueCount))}</td>
        <td>${escapeHtml(translatedSeverity(rule.severity || ""))}</td>
        <td>${escapeHtml(translatedIssueType(rule.type || ""))}</td>
        <td>${escapeHtml(tags.join(", "))}</td>
      </tr>`,
      };
    });
  const rows = ruleRows.map((row) => row.html).join("");

  $("#rules").innerHTML = `
    ${sectionHead(tr("diagnostics", "Диагностики"), Object.keys(rulesByKey).length)}
    <div class="panel">
      <div class="filters">
        <select id="ruleSeverity" required aria-label="${escapeHtml(tr("severityColumn", "Критичность"))}">${renderRequiredFilterOptions(filterValues(ruleRows.map((row) => row.filters.severity)), translatedSeverity)}</select>
        <select id="ruleType" aria-label="${escapeHtml(tr("typeColumn", "Тип"))}">${renderFilterOptions(filterValues(ruleRows.map((row) => row.filters.type)), tr("anyType", "Любой тип"), translatedIssueType)}</select>
        <select id="ruleTag" aria-label="${escapeHtml(tr("tagsColumn", "Теги"))}">${renderFilterOptions(filterValues(ruleRows.flatMap((row) => row.filters.tags)), tr("anyTag", "Любой тег"))}</select>
        <input id="ruleSearch" type="search" placeholder="${escapeHtml(tr("ruleSearchPlaceholder", "Фильтр по любому полю правила"))}">
      </div>
      <div class="table-wrap">
        <table>
          <thead>
            <tr>
              <th>${escapeHtml(tr("diagnosticColumn", "Диагностика"))}</th>
              <th>${escapeHtml(tr("issuesColumn", "Нарушения"))}</th>
              <th>${escapeHtml(tr("severityColumn", "Критичность"))}</th>
              <th>${escapeHtml(tr("typeColumn", "Тип"))}</th>
              <th>${escapeHtml(tr("tagsColumn", "Теги"))}</th>
            </tr>
          </thead>
          <tbody>${rows || `<tr><td colspan="5" class="empty">${escapeHtml(tr("noData", "Нет данных"))}</td></tr>`}</tbody>
        </table>
      </div>
    </div>`;
  initRuleFilters("#rules .rule-row");
}

function initTableFilter(inputSelector, rowSelector, afterFilter) {
  const input = $(inputSelector);
  if (!input) return;
  input.addEventListener("input", () => {
    const query = input.value.trim().toLowerCase();
    document.querySelectorAll(rowSelector).forEach((row) => {
      const haystack = row.dataset.search || row.innerText;
      row.style.display = !query || haystack.toLowerCase().includes(query) ? "" : "none";
    });
    if (afterFilter) afterFilter();
  });
}

function initMetricFilters(domainSelector, inputSelector, rowSelector) {
  const select = $(domainSelector);
  const input = $(inputSelector);
  if (!select || !input) return;
  const applyFilter = () => {
    const domain = select.value;
    const query = input.value.trim().toLowerCase();
    document.querySelectorAll(rowSelector).forEach((row) => {
      const matchesDomain = !domain || row.dataset.domain === domain;
      const haystack = `${row.dataset.search || ""} ${row.innerText || ""}`.toLowerCase();
      const matchesQuery = !query || haystack.includes(query);
      row.style.display = matchesDomain && matchesQuery ? "" : "none";
    });
  };
  select.addEventListener("change", applyFilter);
  input.addEventListener("input", applyFilter);
  applyFilter();
}

function initRecordFilter(inputSelector, rowSelector) {
  const input = $(inputSelector);
  if (!input) return;
  input.addEventListener("input", () => {
    const query = input.value.trim().toLowerCase();
    document.querySelectorAll(rowSelector).forEach((row) => {
      row.style.display = !query || row.dataset.search.includes(query) ? "" : "none";
    });
  });
}

function initRuleFilters(rowSelector) {
  const controls = {
    severity: $("#ruleSeverity"),
    type: $("#ruleType"),
    tag: $("#ruleTag"),
    search: $("#ruleSearch"),
  };
  const applyFilter = () => {
    const query = controls.search?.value.trim().toLowerCase() || "";
    document.querySelectorAll(rowSelector).forEach((row) => {
      const matchesFields = ["severity", "type"]
        .every((field) => !controls[field]?.value || row.dataset[field] === controls[field].value);
      const matchesTag = !controls.tag?.value || (row.dataset.tags || "").split("\n").includes(controls.tag.value);
      const matchesQuery = !query || row.dataset.search.includes(query);
      row.style.display = matchesFields && matchesTag && matchesQuery ? "" : "none";
    });
  };
  Object.values(controls).forEach((control) => {
    if (!control) return;
    control.addEventListener(control.tagName === "SELECT" ? "change" : "input", applyFilter);
  });
  applyFilter();
}

function initIssueFilters(rowSelector) {
  const controls = {
    kind: $("#issueKind"),
    severity: $("#issueSeverity"),
    type: $("#issueType"),
    rule: $("#issueRule"),
    search: $("#issueSearch"),
  };
  const list = $("#issuesList");
  const applyFilter = () => {
    const query = controls.search?.value.trim().toLowerCase() || "";
    document.querySelectorAll(rowSelector).forEach((row) => {
      const matchesFields = ["kind", "severity", "type", "rule"]
        .every((field) => !controls[field]?.value || row.dataset[field] === controls[field].value);
      const matchesQuery = !query || row.dataset.search.includes(query);
      row.style.display = matchesFields && matchesQuery ? "" : "none";
    });
    if (list) list.scrollTop = 0;
  };
  Object.values(controls).forEach((control) => {
    if (!control) return;
    control.addEventListener(control.tagName === "SELECT" ? "change" : "input", applyFilter);
  });
  applyFilter();
}

initHeader();
renderOverview();
renderMetrics();
renderFiles();
renderIssues();
renderRules();
