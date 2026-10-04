const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const source = fs.readFileSync(path.join(__dirname, "sonar-report-template/assets/app.js"), "utf8");
const bootstrap = source.indexOf("\ninitHeader();");
assert.ok(bootstrap >= 0);

function reportContext(report = {}) {
  const context = vm.createContext({ window: { __SONAR_REPORT__: report } });
  // Загрузка функций отчёта без DOM и запуска интерфейса.
  vm.runInContext(source.slice(0, bootstrap), context);
  return context;
}

test("missing metrics stay unknown and do not change folder coverage", () => {
  const context = reportContext();
  vm.runInContext(`
    const missing = [null, undefined, "", "  "];
    if (!missing.every(value => parseNumeric(value) === null)) throw Error("missing number");
    if (projectMeasureNumber("new_violations") !== null) throw Error("missing project metric");
    const accumulator = weightedMetricAccumulator();
    addWeightedMetric(accumulator, 80, 10);
    addWeightedMetric(accumulator, fileMeasureNumber(new Map(), "coverage"), 10);
    if (accumulator.weightedSum / accumulator.weight !== 80) throw Error("missing file diluted coverage");
  `, context);
});

test("real zero metrics remain zero", () => {
  const context = reportContext({ raw: { project_measures: { measures: [{ metric: "new_violations", value: "0" }] } } });
  assert.equal(vm.runInContext('projectMeasureNumber("new_violations")', context), 0);
  assert.equal(vm.runInContext('fileMeasureNumber(new Map([["coverage", {value: "0"}]]), "coverage")', context), 0);
  assert.equal(vm.runInContext('parseNumeric("12.5")', context), 12.5);
  assert.equal(vm.runInContext('parseNumeric("invalid")', context), null);
});

test("specific analysis card shows resolved baseline version and date", () => {
  const context = reportContext();
  const html = vm.runInContext(`renderProjectCard(
    {version: "next", leakPeriodDate: "2025-01-01"}, "",
    {mode: "specific_analysis", parameter: "baseline-uuid"},
    {baseline: {version: "stable", date: "2026-02-03", qualityGateStatus: "OK"}}
  )`, context);
  assert.ok(html.includes("stable"));
  assert.ok(!html.includes("baseline-uuid"));
  assert.ok(html.includes(vm.runInContext('formatDateTime("2026-02-03")', context)));
  assert.ok(!html.includes(vm.runInContext('formatDateTime("2025-01-01")', context)));
});

test("unresolved period parameters are not presented as baseline versions", () => {
  const context = reportContext();
  for (const mode of ["specific_analysis", "number_of_days", "date"]) {
    context.period = { mode, parameter: "unresolved-parameter" };
    assert.ok(!vm.runInContext('renderProjectCard({}, "", period, {})', context).includes("unresolved-parameter"));
  }
  assert.ok(vm.runInContext('renderProjectCard({}, "", {mode: "previous_version", parameter: "stable"}, {})', context).includes("stable"));
});

test("issues belong to files and folders for project keys containing colons", () => {
  for (const project of ["kafka-adapter", "kafka-adapter:prerelease", "kafka-adapter:feature:2Freport", "kafka-adapter::sha256:" + "a".repeat(64)]) {
    const context = reportContext({ meta: { project } });
    context.issue = { component: project + ":modules/example.txt", severity: "MAJOR" };
    vm.runInContext(`
      const file = "modules/example.txt";
      const stats = fileIssueStats([issue], [issue]).get(file);
      if (stats?.total !== 1 || stats?.new !== 1) throw Error("issue counts");
      if (issuesByFile([issue]).get(file)?.length !== 1) throw Error("file issues");
      if (issuesByFolder([issue]).get("modules")?.length !== 1) throw Error("folder issues");
    `, context);
  }
});
