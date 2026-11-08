const assert = require("node:assert/strict");
const fs = require("node:fs");
const path = require("node:path");
const test = require("node:test");
const vm = require("node:vm");

const source = fs.readFileSync(
  path.join(__dirname, "..", "static", "app.js"),
  "utf8",
);
const headingStart = source.indexOf("function stripDuplicateLeadingLessonHeading(");
const headingEnd = source.indexOf("function getOrderedOfficialLessons(", headingStart);
const headingContext = vm.createContext({});
vm.runInContext(
  `${source.slice(headingStart, headingEnd)}\nglobalThis.stripDuplicateHeading = stripDuplicateLeadingLessonHeading;`,
  headingContext,
);
const start = source.indexOf("function getOrderedOfficialLessons(");
const end = source.indexOf("function renderOfficialLessonNavigation(", start);
const helperSource = source.slice(start, end);
const context = vm.createContext({});
vm.runInContext(
  `${helperSource}\nglobalThis.lessonNavigation = getOfficialLessonNeighbors;\n`
    + "globalThis.resumeCandidates = getOfficialResumeCandidates;\n"
    + "globalThis.resumeLesson = getOfficialResumeLesson;",
  context,
);

const pathFixture = {
  id: "foundations",
  modules: [
    { id: "intro", lessons: [{ id: "lesson-1" }, { id: "lesson-2" }] },
    { id: "empty", lessons: [] },
    { id: "practice", lessons: [{ id: "lesson-3" }] },
  ],
};

test("matching Markdown title is suppressed while distinct headings remain", () => {
  const markdown = "# What Is Artificial Intelligence?\n\nAn explanation.\n";
  assert.equal(
    headingContext.stripDuplicateHeading(markdown, "What Is Artificial Intelligence?"),
    "An explanation.\n",
  );
  assert.equal(
    headingContext.stripDuplicateHeading("# Learning from examples\n\nText", "What is AI?"),
    "# Learning from examples\n\nText",
  );
  assert.equal(headingContext.stripDuplicateHeading("Text without a title", "What is AI?"), "Text without a title");
});

function neighborIds(moduleId, lessonId) {
  const module = pathFixture.modules.find((item) => item.id === moduleId);
  const lesson = module.lessons.find((item) => item.id === lessonId);
  const neighbors = context.lessonNavigation(pathFixture, module, lesson);
  return {
    previous: neighbors.previous && [neighbors.previous.module.id, neighbors.previous.lesson.id],
    next: neighbors.next && [neighbors.next.module.id, neighbors.next.lesson.id],
  };
}

test("lesson order follows modules and lessons, skipping empty modules", () => {
  assert.deepEqual(neighborIds("intro", "lesson-1"), {
    previous: null,
    next: ["intro", "lesson-2"],
  });
  assert.deepEqual(neighborIds("intro", "lesson-2"), {
    previous: ["intro", "lesson-1"],
    next: ["practice", "lesson-3"],
  });
  assert.deepEqual(neighborIds("practice", "lesson-3"), {
    previous: ["intro", "lesson-2"],
    next: null,
  });
});

test("single-lesson paths have no previous or next lesson", () => {
  const onlyModule = { id: "only", lessons: [{ id: "only-lesson" }] };
  const onlyPath = { id: "single", modules: [onlyModule] };
  assert.deepEqual(
    JSON.parse(JSON.stringify(context.lessonNavigation(onlyPath, onlyModule, onlyModule.lessons[0]))),
    { previous: null, next: null },
  );
});

test("empty modules and unknown lessons produce no navigation targets", () => {
  const emptyModule = { id: "empty", lessons: [] };
  assert.deepEqual(JSON.parse(JSON.stringify(context.lessonNavigation({ modules: [emptyModule] }, emptyModule, {}))), {
    previous: null,
    next: null,
  });
  assert.deepEqual(JSON.parse(JSON.stringify(context.lessonNavigation(pathFixture, pathFixture.modules[0], { id: "missing" }))), {
    previous: null,
    next: null,
  });
});

test("resume candidates prefer a valid last-accessed path and otherwise preserve catalog order", () => {
  const paths = [{ id: "first" }, { id: "recent" }, { id: "last" }];
  assert.deepEqual(
    JSON.parse(JSON.stringify(context.resumeCandidates(paths, {
      learning_path_id: "recent",
    }))).map((path) => path.id),
    ["recent", "first", "last"],
  );
  assert.deepEqual(
    JSON.parse(JSON.stringify(context.resumeCandidates(paths, {
      learning_path_id: "removed",
    }))).map((path) => path.id),
    ["first", "recent", "last"],
  );
});

test("resume opens the exact recent lesson or falls back to the first lesson after empty modules", () => {
  const path = {
    id: "foundations",
    modules: [
      { id: "empty", lessons: [] },
      { id: "start", lessons: [{ id: "lesson-1" }, { id: "lesson-2" }] },
    ],
  };
  assert.equal(context.resumeLesson(path, "lesson-2").lesson.id, "lesson-2");
  assert.deepEqual(
    JSON.parse(JSON.stringify(context.resumeLesson(path, "removed"))).lesson.id,
    "lesson-1",
  );
  assert.equal(context.resumeLesson({ id: "empty", modules: [{ lessons: [] }] }), null);
  assert.deepEqual(context.resumeCandidates([], null), []);
});

test("each real workspace re-entry resumes and restores the current lesson outline", () => {
  const workspaceStart = source.indexOf("function showWorkspace(name)");
  const workspaceEnd = source.indexOf("workspaceLinks.forEach", workspaceStart);
  const workspaceSource = source.slice(workspaceStart, workspaceEnd);
  const home = { dataset: { workspace: "home" }, hidden: false };
  const study = { dataset: { workspace: "study" }, hidden: true };
  const official = { dataset: { workspace: "official-learning-paths" }, hidden: true };
  let resumeCount = 0;
  let restoredLesson = null;
  const workspaceContext = vm.createContext({
    workspaces: [home, study, official],
    officialPathsWorkspace: official,
    navigationLinks: [],
    dashboardController: null,
    dashboardRequestId: 0,
    dashboardSummary: null,
    dashboardWorkspace: home,
    window: { scrollTo() {} },
    document: { querySelector() { return home; } },
    cancelOfficialLessonResume() {},
    resetOfficialQuizProgress() {},
    loadOfficialLearningPaths() {},
    loadDashboardSummary() {},
    startOfficialLessonResume() {
      resumeCount += 1;
      const entry = context.resumeLesson(pathFixture, "lesson-3");
      entry.module.open = true;
      restoredLesson = {
        pathId: pathFixture.id,
        moduleId: entry.module.id,
        lessonId: entry.lesson.id,
        activeLessonId: entry.lesson.id,
      };
    },
  });
  vm.runInContext(`${workspaceSource}\nglobalThis.activateWorkspace = showWorkspace;`, workspaceContext);

  workspaceContext.activateWorkspace("official-learning-paths");
  assert.equal(resumeCount, 1);
  assert.deepEqual(restoredLesson, {
    pathId: "foundations",
    moduleId: "practice",
    lessonId: "lesson-3",
    activeLessonId: "lesson-3",
  });
  assert.equal(pathFixture.modules[2].open, true);

  workspaceContext.activateWorkspace("home");
  pathFixture.modules[2].open = false;
  restoredLesson = null;
  workspaceContext.activateWorkspace("official-learning-paths");
  assert.equal(resumeCount, 2);
  assert.equal(restoredLesson.lessonId, "lesson-3");
  assert.equal(restoredLesson.activeLessonId, "lesson-3");
  assert.equal(pathFixture.modules[2].open, true);

  workspaceContext.activateWorkspace("study");
  workspaceContext.activateWorkspace("official-learning-paths");
  assert.equal(resumeCount, 3);
  assert.equal(restoredLesson.lessonId, "lesson-3");
});

function createResumeHarness(fetchSummary) {
  const path = {
    id: "foundations",
    title: "Foundations",
    modules: [
      { id: "empty", title: "Empty module", lessons: [] },
      {
        id: "practice",
        title: "Practice",
        lessons: [{ id: "lesson-old" }, { id: "lesson-latest" }],
      },
    ],
  };
  const home = { dataset: { workspace: "home" }, hidden: false };
  const study = { dataset: { workspace: "study" }, hidden: true };
  const official = { dataset: { workspace: "official-learning-paths" }, hidden: true };
  const state = {
    summaryRequests: 0,
    selections: [],
    renderedLessonId: null,
    activeLessonId: null,
    activeModuleId: null,
    completion: new Map([["lesson-old", true]]),
    quizSubmissions: 0,
  };
  const testController = class {
    constructor() { this.signal = {}; }
    abort() { this.aborted = true; }
  };
  const resumeSourceStart = source.indexOf("async function resumeOfficialLearningPath(");
  const resumeSourceEnd = source.indexOf("officialPathRetry.addEventListener", resumeSourceStart);
  const resumeSource = source.slice(resumeSourceStart, resumeSourceEnd).replace(
    "resumeOfficialLearningPath(requestId);",
    "globalThis.pendingResume = resumeOfficialLearningPath(requestId);",
  );
  const cancelSourceStart = source.indexOf("function cancelOfficialLessonResume()");
  const cancelSourceEnd = source.indexOf("async function selectOfficialPath(", cancelSourceStart);
  const workspaceStart = source.indexOf("function showWorkspace(name)");
  const workspaceEnd = source.indexOf("workspaceLinks.forEach", workspaceStart);
  const testContext = vm.createContext({
    workspaces: [home, study, official],
    officialPathsWorkspace: official,
    navigationLinks: [],
    dashboardController: null,
    dashboardRequestId: 0,
    dashboardWorkspace: home,
    officialResumeRequestId: 0,
    officialResumeSuppressed: false,
    officialResumeController: null,
    window: { scrollTo() {}, setTimeout() { return 1; }, clearTimeout() {} },
    document: { querySelector() { return home; } },
    AbortController: testController,
    resetOfficialQuizProgress() {},
    loadDashboardSummary() {},
    loadOfficialLearningPaths: async () => [path],
    isValidDashboardSummary: (summary) => Boolean(summary),
    fetch: async () => {
      state.summaryRequests += 1;
      return fetchSummary();
    },
    selectOfficialPath: async (selectedPath, _button, targetLessonId, resumeRequestId) => {
      state.selections.push({ pathId: selectedPath.id, targetLessonId, resumeRequestId });
      const entry = context.resumeLesson(selectedPath, targetLessonId);
      if (!entry) {
        return { openedLesson: false };
      }
      entry.module.open = true;
      state.renderedLessonId = entry.lesson.id;
      state.activeLessonId = entry.lesson.id;
      state.activeModuleId = entry.module.id;
      return { openedLesson: true };
    },
  });
  vm.runInContext(
    `${helperSource}\n${source.slice(cancelSourceStart, cancelSourceEnd)}\n`
      + `${resumeSource}\n${source.slice(workspaceStart, workspaceEnd)}\n`
      + "globalThis.activateWorkspace = showWorkspace;",
    testContext,
  );
  return { context: testContext, path, home, official, state };
}

test("workspace return runs the real resume flow and restores latest lesson state", async () => {
  const summary = {
    most_recently_accessed_lesson: {
      id: "lesson-latest",
      learning_path_id: "foundations",
    },
  };
  const harness = createResumeHarness(async () => ({
    ok: true,
    json: async () => summary,
  }));
  const { context: activeContext, path, state } = harness;

  activeContext.activateWorkspace("official-learning-paths");
  await activeContext.pendingResume;
  assert.equal(state.renderedLessonId, "lesson-latest");
  assert.equal(state.activeLessonId, "lesson-latest");
  assert.equal(state.activeModuleId, "practice");
  assert.equal(path.modules[1].open, true);
  assert.equal(state.completion.get("lesson-old"), true);
  assert.equal(state.quizSubmissions, 0);

  activeContext.activateWorkspace("home");
  path.modules[1].open = false;
  state.renderedLessonId = null;
  state.activeLessonId = null;
  activeContext.activateWorkspace("official-learning-paths");
  await activeContext.pendingResume;
  assert.equal(state.renderedLessonId, "lesson-latest");
  assert.equal(state.activeLessonId, "lesson-latest");
  assert.equal(path.modules[1].open, true);
  assert.equal(state.summaryRequests, 2);

  activeContext.activateWorkspace("official-learning-paths");
  await Promise.resolve();
  assert.equal(state.summaryRequests, 2);
  activeContext.activateWorkspace("study");
  activeContext.activateWorkspace("official-learning-paths");
  await activeContext.pendingResume;
  assert.equal(state.renderedLessonId, "lesson-latest");
  assert.equal(state.summaryRequests, 3);
});

test("failed resume summary falls back to the first lesson and preserves quiz progress", async () => {
  const harness = createResumeHarness(async () => {
    throw new Error("Summary request failed.");
  });
  harness.context.activateWorkspace("official-learning-paths");
  await harness.context.pendingResume;

  assert.equal(harness.state.renderedLessonId, "lesson-old");
  assert.equal(harness.state.activeModuleId, "practice");
  assert.equal(harness.path.modules[1].open, true);
  assert.equal(harness.state.completion.get("lesson-old"), true);
  assert.equal(harness.state.quizSubmissions, 0);
});

test("manual navigation cancels a delayed resume response before it can select a lesson", async () => {
  let deliverSummary;
  const harness = createResumeHarness(() => new Promise((resolve) => {
    deliverSummary = resolve;
  }));
  harness.context.activateWorkspace("official-learning-paths");
  await new Promise((resolve) => setImmediate(resolve));
  harness.context.cancelOfficialLessonResume();
  deliverSummary({
    ok: true,
    json: async () => ({
      most_recently_accessed_lesson: {
        id: "lesson-latest",
        learning_path_id: "foundations",
      },
    }),
  });
  await harness.context.pendingResume;

  assert.equal(harness.state.selections.length, 0);
  assert.equal(harness.state.renderedLessonId, null);
  assert.equal(harness.state.quizSubmissions, 0);
});
