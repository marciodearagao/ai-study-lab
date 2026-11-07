const form = document.querySelector("#study-form");
const topicInput = document.querySelector("#topic");
const message = document.querySelector("#form-message");
const lesson = document.querySelector("#lesson-placeholder");
const lessonTitle = document.querySelector("#lesson-title");
const lessonDescription = document.querySelector("#lesson-description");
const keyPoints = document.querySelector("#key-points");
const studyPdfInput = document.querySelector("#study-pdf");
const studyPdfFileName = document.querySelector("#study-pdf-file-name");
const groundedIndicator = document.querySelector("#grounded-indicator");
const lessonSources = document.querySelector("#lesson-sources");
const sourceReferences = document.querySelector("#source-references");
const submitButton = form.querySelector('button[type="submit"]');
const buttonLabel = submitButton.querySelector(".button-label");
const studyFlashcardsButton = document.querySelector("#study-flashcards");
const flashcardMode = document.querySelector("#flashcard-mode");
const cardCounter = document.querySelector("#card-counter");
const flashcardQuestion = document.querySelector("#flashcard-question");
const flashcardAnswer = document.querySelector("#flashcard-answer");
const flashcardAnswerText = flashcardAnswer.querySelector("p");
const revealAnswerButton = document.querySelector("#reveal-answer");
const previousCardButton = document.querySelector("#previous-card");
const nextCardButton = document.querySelector("#next-card");
const backToLessonButton = document.querySelector("#back-to-lesson");
const takeQuizButton = document.querySelector("#take-quiz");
const quizMode = document.querySelector("#quiz-mode");
const quizCounter = document.querySelector("#quiz-counter");
const quizQuestionText = document.querySelector("#quiz-question");
const quizOptions = document.querySelector("#quiz-options");
const quizFeedback = document.querySelector("#quiz-feedback");
const quizFeedbackLabel = document.querySelector("#quiz-feedback-label");
const quizExplanation = document.querySelector("#quiz-explanation");
const nextQuestionButton = document.querySelector("#next-question");
const quizQuestionView = document.querySelector("#quiz-question-view");
const quizCompletion = document.querySelector("#quiz-completion");
const quizScore = document.querySelector("#quiz-score");
const backFromQuizButtons = [...document.querySelectorAll(".back-from-quiz")];
const studyWorkspace = document.querySelector("#study");
let flashcards = [];
let currentCardIndex = 0;
let quizQuestions = [];
let currentQuizIndex = 0;
let quizCorrectCount = 0;
let quizAnswered = false;

function renderFlashcard() {
  const card = flashcards[currentCardIndex];
  cardCounter.textContent = `Card ${currentCardIndex + 1} / ${flashcards.length}`;
  flashcardQuestion.textContent = card.question;
  flashcardAnswerText.textContent = card.answer;
  flashcardAnswer.hidden = true;
  revealAnswerButton.hidden = false;
  previousCardButton.disabled = currentCardIndex === 0;
  nextCardButton.disabled = currentCardIndex === flashcards.length - 1;
}

function renderQuizQuestion() {
  const item = quizQuestions[currentQuizIndex];
  quizAnswered = false;
  quizCounter.textContent = `Question ${currentQuizIndex + 1} / ${quizQuestions.length}`;
  quizQuestionText.textContent = item.question;
  quizFeedback.hidden = true;
  nextQuestionButton.hidden = true;
  nextQuestionButton.textContent = currentQuizIndex === quizQuestions.length - 1
    ? "See results →"
    : "Next question →";
  quizOptions.replaceChildren(
    ...item.options.map((option) => {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = option;
      button.addEventListener("click", () => answerQuizQuestion(button, option));
      return button;
    }),
  );
}

function answerQuizQuestion(selectedButton, selectedAnswer) {
  if (quizAnswered) {
    return;
  }
  quizAnswered = true;
  const item = quizQuestions[currentQuizIndex];
  const isCorrect = selectedAnswer === item.correct_answer;
  if (isCorrect) {
    quizCorrectCount += 1;
  }
  [...quizOptions.children].forEach((button) => {
    button.disabled = true;
    if (button.textContent === item.correct_answer) {
      button.classList.add("correct-answer");
    }
  });
  selectedButton.classList.add(isCorrect ? "selected-correct" : "selected-incorrect");
  quizFeedbackLabel.textContent = isCorrect ? "Correct" : "Incorrect";
  quizFeedback.className = `quiz-feedback ${isCorrect ? "correct" : "incorrect"}`;
  quizExplanation.textContent = item.explanation;
  quizFeedback.hidden = false;
  nextQuestionButton.hidden = false;
}

form.addEventListener("submit", async (event) => {
  event.preventDefault();
  const topic = topicInput.value.trim();

  if (!topic) {
    message.textContent = "Add a topic to begin.";
    topicInput.setAttribute("aria-invalid", "true");
    topicInput.focus();
    lesson.hidden = true;
    return;
  }

  const level = new FormData(form).get("level");
  const studyPdf = studyPdfInput.files[0];
  message.textContent = "";
  topicInput.removeAttribute("aria-invalid");
  lesson.hidden = true;
  flashcardMode.hidden = true;
  submitButton.disabled = true;
  buttonLabel.textContent = studyPdf ? "Preparing your study material..." : "Creating lesson...";
  form.setAttribute("aria-busy", "true");
  let failureMessage = "We couldn’t create that lesson. Please try again.";

  try {
    let endpoint = "/api/lessons";
    let requestOptions = {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ topic, level }),
    };
    if (studyPdf) {
      const formData = new FormData();
      formData.append("topic", topic);
      formData.append("level", level);
      formData.append("study_pdf", studyPdf);
      endpoint = "/api/lessons/pdf";
      requestOptions = { method: "POST", body: formData };
    }
    const response = await fetch(endpoint, requestOptions);
    const result = await response.json();

    if (!response.ok) {
      if (typeof result.detail === "string") {
        failureMessage = result.detail;
      }
      throw new Error("Lesson request failed");
    }

    const lessonResult = studyPdf ? result.lesson : result;
    lessonTitle.textContent = lessonResult.title;
    lessonDescription.textContent = lessonResult.short_explanation;
    keyPoints.replaceChildren(
      ...lessonResult.key_concepts.map((point) => {
        const item = document.createElement("li");
        item.textContent = point;
        return item;
      }),
    );
    flashcards = lessonResult.flashcards;
    quizQuestions = lessonResult.quiz_questions;
    const sources = studyPdf ? result.sources : [];
    groundedIndicator.hidden = !result.used_uploaded_material;
    lessonSources.hidden = sources.length === 0;
    sourceReferences.replaceChildren(
      ...sources.map((source) => {
        const item = document.createElement("li");
        const page = document.createElement("strong");
        page.textContent = `Page ${source.page_number}`;
        item.append(page, source.excerpt);
        return item;
      }),
    );
    currentCardIndex = 0;
    lesson.hidden = false;
    lesson.focus();
  } catch (_error) {
    message.textContent = failureMessage;
  } finally {
    submitButton.disabled = false;
    buttonLabel.textContent = "Start learning";
    form.removeAttribute("aria-busy");
  }
});

studyPdfInput.addEventListener("change", () => {
  const file = studyPdfInput.files[0];
  studyPdfFileName.textContent = file ? `Selected: ${file.name}` : "No PDF selected";
});

studyFlashcardsButton.addEventListener("click", () => {
  renderFlashcard();
  lesson.hidden = true;
  flashcardMode.hidden = false;
  studyWorkspace.classList.add("activity-active");
  flashcardMode.focus();
});

revealAnswerButton.addEventListener("click", () => {
  flashcardAnswer.hidden = false;
  revealAnswerButton.hidden = true;
});

previousCardButton.addEventListener("click", () => {
  if (currentCardIndex > 0) {
    currentCardIndex -= 1;
    renderFlashcard();
  }
});

nextCardButton.addEventListener("click", () => {
  if (currentCardIndex < flashcards.length - 1) {
    currentCardIndex += 1;
    renderFlashcard();
  }
});

backToLessonButton.addEventListener("click", () => {
  flashcardMode.hidden = true;
  lesson.hidden = false;
  studyWorkspace.classList.remove("activity-active");
  lesson.focus();
});

takeQuizButton.addEventListener("click", () => {
  currentQuizIndex = 0;
  quizCorrectCount = 0;
  quizQuestionView.hidden = false;
  quizCompletion.hidden = true;
  renderQuizQuestion();
  lesson.hidden = true;
  quizMode.hidden = false;
  studyWorkspace.classList.add("activity-active");
  quizMode.focus();
});

nextQuestionButton.addEventListener("click", () => {
  if (!quizAnswered) {
    return;
  }
  if (currentQuizIndex < quizQuestions.length - 1) {
    currentQuizIndex += 1;
    renderQuizQuestion();
    return;
  }
  quizQuestionView.hidden = true;
  quizCompletion.hidden = false;
  quizScore.textContent = `${quizCorrectCount} / ${quizQuestions.length} correct`;
});

backFromQuizButtons.forEach((button) => {
  button.addEventListener("click", () => {
    quizMode.hidden = true;
    lesson.hidden = false;
    studyWorkspace.classList.remove("activity-active");
    lesson.focus();
  });
});

topicInput.addEventListener("input", () => {
  if (topicInput.value.trim()) {
    message.textContent = "";
    topicInput.removeAttribute("aria-invalid");
  }
});

const interviewForm = document.querySelector("#interview-form");
const jobDescriptionInput = document.querySelector("#job-description");
const resumeInput = document.querySelector("#resume-text");
const resumePdfInput = document.querySelector("#resume-pdf");
const pdfFileName = document.querySelector("#pdf-file-name");
const linkedinPdfInput = document.querySelector("#linkedin-pdf");
const linkedinFileName = document.querySelector("#linkedin-file-name");
const coverLetterPdfInput = document.querySelector("#cover-letter-pdf");
const coverLetterFileName = document.querySelector("#cover-letter-file-name");
const interviewMessage = document.querySelector("#interview-message");
const analysisResults = document.querySelector("#analysis-results");
const analyzeButton = interviewForm.querySelector('button[type="submit"]');
const analyzeButtonLabel = analyzeButton.querySelector(".coach-button-label");

function renderAnalysisList(selector, items, emptyMessage) {
  const list = document.querySelector(selector);
  const values = items.length ? items : [emptyMessage];
  list.replaceChildren(
    ...values.map((value) => {
      const item = document.createElement("li");
      item.textContent = value;
      return item;
    }),
  );
}

interviewForm.addEventListener("submit", async (event) => {
  event.preventDefault();
  const jobDescription = jobDescriptionInput.value.trim();
  const resumeText = resumeInput.value.trim();
  const resumePdf = resumePdfInput.files[0];
  const linkedinPdf = linkedinPdfInput.files[0];
  const coverLetterPdf = coverLetterPdfInput.files[0];

  jobDescriptionInput.removeAttribute("aria-invalid");
  resumeInput.removeAttribute("aria-invalid");
  resumePdfInput.removeAttribute("aria-invalid");
  linkedinPdfInput.removeAttribute("aria-invalid");
  coverLetterPdfInput.removeAttribute("aria-invalid");
  if (!jobDescription) {
    interviewMessage.textContent = "Add the Job Description to continue.";
    jobDescriptionInput.setAttribute("aria-invalid", "true");
    jobDescriptionInput.focus();
    return;
  }
  if (!resumePdf && !resumeText) {
    interviewMessage.textContent = "Choose a PDF or add your Resume / CV text to continue.";
    resumeInput.setAttribute("aria-invalid", "true");
    resumeInput.focus();
    return;
  }
  if (resumePdf && (resumePdf.type !== "application/pdf" || !resumePdf.name.toLowerCase().endsWith(".pdf"))) {
    interviewMessage.textContent = "Choose one PDF resume file.";
    resumePdfInput.setAttribute("aria-invalid", "true");
    resumePdfInput.focus();
    return;
  }
  if (linkedinPdf && (linkedinPdf.type !== "application/pdf" || !linkedinPdf.name.toLowerCase().endsWith(".pdf"))) {
    interviewMessage.textContent = "Choose one PDF file for LinkedIn Profile.";
    linkedinPdfInput.setAttribute("aria-invalid", "true");
    linkedinPdfInput.focus();
    return;
  }
  if (coverLetterPdf && (coverLetterPdf.type !== "application/pdf" || !coverLetterPdf.name.toLowerCase().endsWith(".pdf"))) {
    interviewMessage.textContent = "Choose one PDF file for Cover Letter.";
    coverLetterPdfInput.setAttribute("aria-invalid", "true");
    coverLetterPdfInput.focus();
    return;
  }

  interviewMessage.textContent = "";
  analysisResults.hidden = true;
  analyzeButton.disabled = true;
  analyzeButtonLabel.textContent = "Analyzing...";
  interviewForm.setAttribute("aria-busy", "true");
  let failureMessage = "We couldn’t analyze these details. Please try again.";

  try {
    let endpoint = "/api/interview-analysis";
    let requestOptions = {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ job_description: jobDescription, resume_text: resumeText }),
    };
    if (resumePdf || linkedinPdf || coverLetterPdf) {
      const formData = new FormData();
      formData.append("job_description", jobDescription);
      if (resumePdf) {
        formData.append("resume_pdf", resumePdf);
      } else {
        formData.append("resume_text", resumeText);
      }
      if (linkedinPdf) {
        formData.append("linkedin_pdf", linkedinPdf);
      }
      if (coverLetterPdf) {
        formData.append("cover_letter_pdf", coverLetterPdf);
      }
      endpoint = "/api/interview-analysis/pdf";
      requestOptions = { method: "POST", body: formData };
    }
    const response = await fetch(endpoint, requestOptions);
    const result = await response.json();
    if (!response.ok) {
      if (typeof result.detail === "string") {
        failureMessage = result.detail;
      }
      throw new Error("Interview analysis failed");
    }

    document.querySelector("#fit-level").textContent = result.fit_level;
    document.querySelector("#fit-summary").textContent = result.fit_summary;
    renderAnalysisList("#analysis-evidence", result.evidence, "No clear supporting evidence found.");
    renderAnalysisList("#analysis-gaps", result.gaps, "No clear gaps found.");
    renderAnalysisList("#analysis-topics", result.suggested_study_topics, "No study topics suggested.");
    renderAnalysisList("#analysis-questions", result.interview_questions, "No questions generated.");
    analysisResults.hidden = false;
    analysisResults.focus();
  } catch (_error) {
    interviewMessage.textContent = failureMessage;
  } finally {
    analyzeButton.disabled = false;
    analyzeButtonLabel.textContent = "Analyze";
    interviewForm.removeAttribute("aria-busy");
  }
});

resumePdfInput.addEventListener("change", () => {
  const file = resumePdfInput.files[0];
  pdfFileName.textContent = file ? `Selected: ${file.name}` : "No PDF selected";
  resumePdfInput.removeAttribute("aria-invalid");
  interviewMessage.textContent = "";
});

linkedinPdfInput.addEventListener("change", () => {
  const file = linkedinPdfInput.files[0];
  linkedinFileName.textContent = file ? `Selected: ${file.name}` : "No LinkedIn PDF selected";
  linkedinPdfInput.removeAttribute("aria-invalid");
  interviewMessage.textContent = "";
});

coverLetterPdfInput.addEventListener("change", () => {
  const file = coverLetterPdfInput.files[0];
  coverLetterFileName.textContent = file ? `Selected: ${file.name}` : "No Cover Letter PDF selected";
  coverLetterPdfInput.removeAttribute("aria-invalid");
  interviewMessage.textContent = "";
});

[jobDescriptionInput, resumeInput].forEach((input) => {
  input.addEventListener("input", () => {
    if (input.value.trim()) {
      input.removeAttribute("aria-invalid");
      interviewMessage.textContent = "";
    }
  });
});

const workspaces = [...document.querySelectorAll("[data-workspace]")];
const workspaceLinks = [...document.querySelectorAll("[data-workspace-link]")];
const navigationLinks = [...document.querySelectorAll("nav [data-workspace-link]")];
const officialPathStatus = document.querySelector("#official-paths-status");
const officialPathList = document.querySelector("#official-path-list");
const officialPathDetail = document.querySelector("#official-path-detail");
const officialPathDetailTitle = document.querySelector("#official-path-detail-title");
const officialPathContent = document.querySelector("#official-path-content");
const officialPathRetry = document.querySelector("#official-paths-retry");
const dashboardWorkspace = document.querySelector("#home");
const dashboardStatus = document.querySelector("#dashboard-status");
const dashboardRetry = document.querySelector("#dashboard-retry");
const dashboardContent = document.querySelector("#dashboard-content");
const dashboardContinueContent = document.querySelector("#dashboard-continue-content");
const dashboardContinueButton = document.querySelector("#dashboard-continue-button");
const dashboardStartLink = document.querySelector("#dashboard-start-link");
const dashboardProgressLabel = document.querySelector("#dashboard-progress-label");
const dashboardProgressBar = document.querySelector("#dashboard-progress-bar");
const dashboardProgressPercentage = document.querySelector("#dashboard-progress-percentage");
const dashboardPathList = document.querySelector("#dashboard-path-list");
const dashboardActivityList = document.querySelector("#dashboard-activity-list");
let officialPathsLoaded = false;
let officialPathsLoading = false;
let officialQuizState = null;
let officialLessonRequestId = 0;
let officialSelectedPathId = null;
let officialPathRequestId = 0;
let dashboardSummary = null;
let dashboardRequestId = 0;
let dashboardController = null;

function isValidDashboardSummary(summary) {
  return summary
    && Number.isInteger(summary.total_lessons)
    && Number.isInteger(summary.completed_lessons)
    && Number.isFinite(summary.completion_percentage)
    && (summary.most_recently_accessed_lesson === null
      || (
        typeof summary.most_recently_accessed_lesson.id === "string"
        && typeof summary.most_recently_accessed_lesson.title === "string"
        && typeof summary.most_recently_accessed_lesson.learning_path_id === "string"
      ))
    && Array.isArray(summary.learning_paths)
    && summary.learning_paths.every((path) => (
      typeof path.id === "string"
      && typeof path.title === "string"
      && Number.isInteger(path.total_lessons)
      && Number.isInteger(path.completed_lessons)
      && Number.isFinite(path.completion_percentage)
    ))
    && Array.isArray(summary.recent_quiz_attempts)
    && summary.recent_quiz_attempts.every((attempt) => (
      typeof attempt.lesson_id === "string"
      && typeof attempt.lesson_title === "string"
      && Number.isInteger(attempt.score)
      && Number.isInteger(attempt.total_questions)
      && typeof attempt.completed_at === "string"
    ));
}

function formatDashboardDate(value) {
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) {
    return value;
  }
  return new Intl.DateTimeFormat("en", {
    dateStyle: "medium",
    timeStyle: "short",
  }).format(date);
}

function renderDashboardSummary(summary) {
  const recentLesson = summary.most_recently_accessed_lesson;
  dashboardContinueContent.replaceChildren();
  if (recentLesson) {
    const title = document.createElement("h4");
    title.textContent = recentLesson.title;
    const path = summary.learning_paths.find(
      (item) => item.id === recentLesson.learning_path_id,
    );
    const pathTitle = document.createElement("p");
    pathTitle.textContent = path ? path.title : "Official Learning Path";
    dashboardContinueContent.append(title, pathTitle);
    dashboardContinueButton.hidden = false;
    dashboardStartLink.hidden = true;
  } else {
    const empty = document.createElement("p");
    empty.className = "dashboard-empty";
    empty.textContent = "No recent lesson yet. Choose an official learning path to get started.";
    dashboardContinueContent.append(empty);
    dashboardContinueButton.hidden = true;
    dashboardStartLink.hidden = false;
  }

  dashboardProgressLabel.textContent = `${summary.completed_lessons} of ${summary.total_lessons} lessons completed`;
  dashboardProgressBar.value = Math.max(
    0,
    Math.min(100, summary.completion_percentage),
  );
  dashboardProgressPercentage.textContent = `${summary.completion_percentage}%`;

  dashboardPathList.replaceChildren();
  if (summary.learning_paths.length === 0) {
    const empty = document.createElement("p");
    empty.className = "dashboard-empty";
    empty.textContent = "No official learning paths are available yet.";
    dashboardPathList.append(empty);
  } else {
    summary.learning_paths.forEach((path) => {
      const item = document.createElement("article");
      item.className = "dashboard-path-item";
      const title = document.createElement("h4");
      title.textContent = path.title;
      const progressText = document.createElement("p");
      progressText.textContent = `${path.completed_lessons} of ${path.total_lessons} lessons · ${path.completion_percentage}%`;
      const progress = document.createElement("progress");
      progress.max = 100;
      progress.value = Math.max(0, Math.min(100, path.completion_percentage));
      progress.setAttribute("aria-label", `${path.title} completion`);
      const open = document.createElement("button");
      open.type = "button";
      open.textContent = "Open learning path";
      open.addEventListener("click", () => navigateToOfficialPath(path.id, path.title));
      item.append(title, progressText, progress, open);
      dashboardPathList.append(item);
    });
  }

  dashboardActivityList.replaceChildren();
  if (summary.recent_quiz_attempts.length === 0) {
    const empty = document.createElement("li");
    empty.className = "dashboard-empty";
    empty.textContent = "No quiz attempts yet. Complete a lesson quiz to see activity here.";
    dashboardActivityList.append(empty);
  } else {
    summary.recent_quiz_attempts.slice(0, 5).forEach((attempt) => {
      const item = document.createElement("li");
      const title = document.createElement("strong");
      title.textContent = attempt.lesson_title;
      const score = document.createElement("span");
      score.textContent = `${attempt.score} / ${attempt.total_questions} correct · `;
      const date = document.createElement("time");
      date.dateTime = attempt.completed_at;
      date.textContent = formatDashboardDate(attempt.completed_at);
      item.append(title, score, date);
      dashboardActivityList.append(item);
    });
  }
}

function dashboardRequestIsCurrent(requestId) {
  return requestId === dashboardRequestId && !dashboardWorkspace.hidden;
}

async function loadDashboardSummary() {
  dashboardRequestId += 1;
  const requestId = dashboardRequestId;
  if (dashboardController) {
    dashboardController.abort();
  }
  const controller = new AbortController();
  dashboardController = controller;
  let timeoutId;
  dashboardStatus.textContent = "Loading dashboard...";
  dashboardRetry.hidden = true;
  dashboardContent.hidden = true;
  dashboardContent.setAttribute("aria-busy", "true");

  try {
    timeoutId = window.setTimeout(() => controller.abort(), 10000);
    const response = await fetch("/api/dashboard/summary", { signal: controller.signal });
    if (!response.ok) {
      throw new Error("Dashboard summary could not be loaded.");
    }
    const summary = await response.json();
    if (!isValidDashboardSummary(summary)) {
      throw new Error("Dashboard summary response is invalid.");
    }
    if (!dashboardRequestIsCurrent(requestId)) {
      return;
    }
    dashboardSummary = summary;
    renderDashboardSummary(summary);
    dashboardStatus.textContent = "";
    dashboardContent.hidden = false;
  } catch (_error) {
    if (!dashboardRequestIsCurrent(requestId)) {
      return;
    }
    dashboardStatus.textContent = "Dashboard could not be loaded. Please try again.";
    dashboardRetry.hidden = false;
  } finally {
    window.clearTimeout(timeoutId);
    if (requestId === dashboardRequestId) {
      dashboardController = null;
      dashboardContent.removeAttribute("aria-busy");
    }
  }
}

function navigateToOfficialPath(pathId, pathTitle, lessonId = null) {
  window.location.hash = "#official-learning-paths";
  showWorkspace("official-learning-paths");
  selectOfficialPath({ id: pathId, title: pathTitle }, null, lessonId);
}

dashboardRetry.addEventListener("click", loadDashboardSummary);
dashboardContinueButton.addEventListener("click", () => {
  const lesson = dashboardSummary?.most_recently_accessed_lesson;
  if (!lesson) {
    return;
  }
  const path = dashboardSummary.learning_paths.find(
    (item) => item.id === lesson.learning_path_id,
  );
  navigateToOfficialPath(
    lesson.learning_path_id,
    path ? path.title : "Official Learning Path",
    lesson.id,
  );
});

function resetOfficialQuizProgress() {
  if (!officialQuizState || officialQuizState.persisting) {
    return;
  }
  officialQuizState.questionIndex = 0;
  officialQuizState.correctCount = 0;
  officialQuizState.selectedKey = null;
  officialQuizState.submitted = false;
  officialQuizState.finished = false;
  officialQuizState.saveStatus.textContent = "";
  officialQuizState.restart.disabled = false;
  officialQuizState.completion.hidden = true;
  officialQuizState.questionView.hidden = false;
  renderOfficialQuizQuestion();
}

function renderOfficialQuizQuestion() {
  const state = officialQuizState;
  const question = state.questions[state.questionIndex];
  state.counter.textContent = `Question ${state.questionIndex + 1} / ${state.questions.length}`;
  state.question.textContent = question.question;
  state.feedback.hidden = true;
  state.next.hidden = true;
  state.submit.disabled = true;
  state.options.replaceChildren(
    ...["A", "B", "C", "D"].map((key) => {
      const option = document.createElement("button");
      option.type = "button";
      option.setAttribute("aria-pressed", "false");
      option.textContent = `${key}. ${question.options[key]}`;
      option.addEventListener("click", () => {
        if (state.submitted) {
          return;
        }
        state.selectedKey = key;
        state.submit.disabled = false;
        [...state.options.children].forEach((button) => {
          button.setAttribute("aria-pressed", String(button === option));
        });
      });
      return option;
    }),
  );
}

function submitOfficialQuizAnswer() {
  const state = officialQuizState;
  if (!state || state.submitted || !state.selectedKey) {
    return;
  }
  const question = state.questions[state.questionIndex];
  state.submitted = true;
  const isCorrect = state.selectedKey === question.correct_answer;
  if (isCorrect) {
    state.correctCount += 1;
  }
  [...state.options.children].forEach((button, index) => {
    const key = ["A", "B", "C", "D"][index];
    button.disabled = true;
    if (key === question.correct_answer) {
      button.classList.add("correct-answer");
    }
    if (key === state.selectedKey && !isCorrect) {
      button.classList.add("selected-incorrect");
    }
  });
  state.feedbackLabel.textContent = isCorrect ? "Correct!" : "Incorrect.";
  state.feedbackText.textContent = isCorrect
    ? "Your answer is correct."
    : `The correct answer is ${question.correct_answer}: ${question.options[question.correct_answer]}`;
  state.feedback.className = `quiz-feedback ${isCorrect ? "correct" : "incorrect"}`;
  state.feedback.hidden = false;
  state.next.textContent = state.questionIndex === state.questions.length - 1
    ? "See results"
    : "Next question";
  state.next.hidden = false;
}

function advanceOfficialQuiz() {
  const state = officialQuizState;
  if (!state || !state.submitted || state.finished) {
    return;
  }
  if (state.questionIndex < state.questions.length - 1) {
    state.questionIndex += 1;
    state.selectedKey = null;
    state.submitted = false;
    renderOfficialQuizQuestion();
    return;
  }
  state.finished = true;
  state.persisting = true;
  state.questionView.hidden = true;
  state.completion.hidden = false;
  state.score.textContent = `${state.correctCount} / ${state.questions.length} correct`;
  state.saveStatus.textContent = "Saving your result...";
  state.restart.disabled = true;
  saveOfficialQuizAttempt(state);
}

async function saveOfficialQuizAttempt(state) {
  const controller = new AbortController();
  let timeoutId;
  try {
    timeoutId = window.setTimeout(() => controller.abort(), 10000);
    const response = await fetch("/api/progress/quiz-attempts", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      signal: controller.signal,
      body: JSON.stringify({
        lesson_id: state.lessonId,
        score: state.correctCount,
        total_questions: state.questions.length,
      }),
    });
    if (!response.ok) {
      throw new Error("Quiz result could not be saved.");
    }
    if (officialQuizState !== state || state.lessonRequestId !== officialLessonRequestId) {
      return;
    }
    state.saveStatus.textContent = "Result saved successfully. Lesson completed.";
    state.progressStatus.textContent = "Lesson completed.";
    state.progressStatus.dataset.completed = "true";
  } catch (_error) {
    if (officialQuizState !== state || state.lessonRequestId !== officialLessonRequestId) {
      return;
    }
    state.saveStatus.textContent = "Your score is shown, but we could not confirm whether it was saved. Check lesson progress before submitting again.";
  } finally {
    window.clearTimeout(timeoutId);
    state.persisting = false;
    if (officialQuizState === state && state.lessonRequestId === officialLessonRequestId) {
      state.restart.disabled = false;
    }
  }
}

function renderOfficialQuiz(quiz) {
  const section = document.createElement("section");
  section.className = "official-quiz";
  const title = document.createElement("h5");
  title.textContent = "Lesson quiz";
  section.append(title);

  const validQuiz = Array.isArray(quiz) && quiz.length > 0 && quiz.every((question) => (
    question
    && typeof question.question === "string"
    && question.options
    && ["A", "B", "C", "D"].every((key) => typeof question.options[key] === "string")
    && ["A", "B", "C", "D"].includes(question.correct_answer)
  ));
  if (!validQuiz) {
    const empty = document.createElement("p");
    empty.textContent = "Quiz questions are not available yet.";
    section.append(empty);
    return section;
  }

  const questionView = document.createElement("div");
  questionView.className = "official-quiz-question-view";
  const counter = document.createElement("p");
  counter.className = "lesson-kicker";
  counter.setAttribute("aria-live", "polite");
  const questionText = document.createElement("h6");
  questionText.className = "official-quiz-question";
  const options = document.createElement("div");
  options.className = "quiz-options official-quiz-options";
  const feedback = document.createElement("div");
  feedback.className = "quiz-feedback";
  feedback.setAttribute("role", "status");
  feedback.hidden = true;
  const feedbackLabel = document.createElement("strong");
  const feedbackText = document.createElement("p");
  feedback.append(feedbackLabel, feedbackText);
  const controls = document.createElement("div");
  controls.className = "official-quiz-controls";
  const submit = document.createElement("button");
  submit.type = "button";
  submit.textContent = "Submit answer";
  submit.addEventListener("click", submitOfficialQuizAnswer);
  const next = document.createElement("button");
  next.type = "button";
  next.textContent = "Next question";
  next.hidden = true;
  next.addEventListener("click", advanceOfficialQuiz);
  controls.append(submit, next);
  questionView.append(counter, questionText, options, feedback, controls);

  const completion = document.createElement("div");
  completion.className = "official-quiz-completion";
  completion.hidden = true;
  const completedTitle = document.createElement("h6");
  completedTitle.textContent = "Quiz result";
  const score = document.createElement("p");
  const saveStatus = document.createElement("p");
  saveStatus.className = "official-quiz-save-status";
  saveStatus.setAttribute("role", "status");
  saveStatus.setAttribute("aria-live", "polite");
  const restart = document.createElement("button");
  restart.type = "button";
  restart.textContent = "Restart quiz";
  restart.addEventListener("click", resetOfficialQuizProgress);
  completion.append(completedTitle, score, saveStatus, restart);
  section.append(questionView, completion);

  officialQuizState = {
    questions: quiz,
    questionIndex: 0,
    correctCount: 0,
    selectedKey: null,
    submitted: false,
    questionView,
    completion,
    counter,
    question: questionText,
    options,
    feedback,
    feedbackLabel,
    feedbackText,
    submit,
    next,
    score,
    saveStatus,
    restart,
    finished: false,
    persisting: false,
  };
  renderOfficialQuizQuestion();
  return section;
}

function renderInlineMarkdown(text, parent) {
  const pattern = /`([^`]+)`/g;
  let lastIndex = 0;
  for (const match of text.matchAll(pattern)) {
    parent.append(document.createTextNode(text.slice(lastIndex, match.index)));
    const code = document.createElement("code");
    code.textContent = match[1];
    parent.append(code);
    lastIndex = match.index + match[0].length;
  }
  parent.append(document.createTextNode(text.slice(lastIndex)));
}

function renderLessonMarkdown(markdown) {
  const fragment = document.createDocumentFragment();
  const lines = markdown.replace(/\r\n?/g, "\n").split("\n");
  let paragraph = [];
  let list = null;
  let codeLines = null;

  const flushParagraph = () => {
    if (paragraph.length) {
      const element = document.createElement("p");
      renderInlineMarkdown(paragraph.join(" "), element);
      fragment.append(element);
      paragraph = [];
    }
  };
  const flushList = () => {
    if (list) {
      fragment.append(list);
      list = null;
    }
  };

  for (const line of lines) {
    if (codeLines !== null) {
      if (/^\s*```/.test(line)) {
        const pre = document.createElement("pre");
        const code = document.createElement("code");
        code.textContent = codeLines.join("\n");
        pre.append(code);
        fragment.append(pre);
        codeLines = null;
      } else {
        codeLines.push(line);
      }
      continue;
    }
    if (/^\s*```/.test(line)) {
      flushParagraph();
      flushList();
      codeLines = [];
      continue;
    }
    const heading = line.match(/^(#{1,6})\s+(.+?)\s*#*\s*$/);
    if (heading) {
      flushParagraph();
      flushList();
      const element = document.createElement(`h${heading[1].length}`);
      renderInlineMarkdown(heading[2], element);
      fragment.append(element);
      continue;
    }
    const item = line.match(/^\s*(?:[-*+]\s+|(\d+)\.\s+)(.+)$/);
    if (item) {
      flushParagraph();
      const tag = item[1] ? "ol" : "ul";
      if (!list || list.tagName.toLowerCase() !== tag) {
        flushList();
        list = document.createElement(tag);
      }
      const listItem = document.createElement("li");
      renderInlineMarkdown(item[2], listItem);
      list.append(listItem);
      continue;
    }
    if (!line.trim()) {
      flushParagraph();
      flushList();
    } else {
      flushList();
      paragraph.push(line.trim());
    }
  }
  if (codeLines !== null) {
    const pre = document.createElement("pre");
    const code = document.createElement("code");
    code.textContent = codeLines.join("\n");
    pre.append(code);
    fragment.append(pre);
  }
  flushParagraph();
  flushList();
  return fragment;
}

function renderOfficialModule(path, module) {
  officialQuizState = null;
  officialLessonRequestId += 1;
  officialPathContent.replaceChildren();
  const back = document.createElement("button");
  back.type = "button";
  back.className = "official-path-back";
  back.textContent = "← Back to modules";
  back.addEventListener("click", () => showOfficialPathModules(path));
  const heading = document.createElement("h4");
  heading.textContent = module.title;
  const lessons = document.createElement("ul");
  module.lessons.forEach((lessonItem) => {
    const item = document.createElement("li");
    const button = document.createElement("button");
    button.type = "button";
    button.className = "official-path-lesson";
    button.textContent = lessonItem.title;
    button.addEventListener("click", () => renderOfficialLesson(path, module, lessonItem));
    item.append(button);
    lessons.append(item);
  });
  officialPathContent.append(back, heading, lessons);
}

function showOfficialPathModules(path) {
  officialQuizState = null;
  officialLessonRequestId += 1;
  officialPathContent.replaceChildren();
  const heading = document.createElement("h4");
  heading.textContent = "Modules";
  if (path.modules.length === 0) {
    const empty = document.createElement("p");
    empty.textContent = "Modules are not available yet.";
    officialPathContent.append(heading, empty);
    return;
  }
  const modules = document.createElement("ul");
  path.modules.forEach((module) => {
    const item = document.createElement("li");
    const button = document.createElement("button");
    button.type = "button";
    button.className = "official-path-module";
    button.textContent = module.title;
    button.addEventListener("click", () => renderOfficialModule(path, module));
    item.append(button);
    modules.append(item);
  });
  officialPathContent.append(heading, modules);
}

function renderOfficialLesson(path, module, lessonItem) {
  officialQuizState = null;
  officialLessonRequestId += 1;
  const requestId = officialLessonRequestId;
  officialPathContent.replaceChildren();
  const back = document.createElement("button");
  back.type = "button";
  back.className = "official-path-back";
  back.textContent = `← Back to ${module.title}`;
  back.addEventListener("click", () => renderOfficialModule(path, module));
  const heading = document.createElement("h4");
  heading.textContent = lessonItem.title;
  const progressStatus = document.createElement("p");
  progressStatus.className = "official-progress-status";
  progressStatus.setAttribute("role", "status");
  progressStatus.setAttribute("aria-live", "polite");
  progressStatus.textContent = "Checking lesson progress...";
  const explanation = document.createElement("article");
  explanation.className = "official-lesson-markdown";
  const markdown = typeof lessonItem.explanation === "string" ? lessonItem.explanation : "";
  if (markdown.trim()) {
    explanation.append(renderLessonMarkdown(markdown));
  } else {
    const empty = document.createElement("p");
    empty.textContent = "Lesson content is not available yet.";
    explanation.append(empty);
  }
  const quiz = renderOfficialQuiz(lessonItem.quiz);
  if (officialQuizState) {
    officialQuizState.lessonId = lessonItem.id;
    officialQuizState.lessonRequestId = requestId;
    officialQuizState.progressStatus = progressStatus;
  }
  officialPathContent.append(back, heading, progressStatus, explanation, quiz);
  loadOfficialLessonProgress(lessonItem.id, progressStatus, requestId);
}

async function loadOfficialLessonProgress(lessonId, statusElement, requestId) {
  const accessController = new AbortController();
  let accessTimeoutId;
  const accessRequest = (async () => {
    try {
      accessTimeoutId = window.setTimeout(() => accessController.abort(), 10000);
      const response = await fetch(
        `/api/progress/lessons/${encodeURIComponent(lessonId)}/access`,
        { method: "POST", signal: accessController.signal },
      );
      if (!response.ok) {
        throw new Error("Lesson access could not be recorded.");
      }
    } finally {
      window.clearTimeout(accessTimeoutId);
    }
  })();
  const progressController = new AbortController();
  let progressTimeoutId;
  const progressRequest = (async () => {
    try {
      progressTimeoutId = window.setTimeout(() => progressController.abort(), 10000);
      const response = await fetch(
        `/api/progress/lessons/${encodeURIComponent(lessonId)}`,
        { signal: progressController.signal },
      );
      if (!response.ok) {
        throw new Error("Lesson progress could not be loaded.");
      }
      return await response.json();
    } finally {
      window.clearTimeout(progressTimeoutId);
    }
  })();
  const [accessResult, progressResult] = await Promise.allSettled([
    accessRequest,
    progressRequest,
  ]);
  if (requestId !== officialLessonRequestId || !statusElement.isConnected) {
    return;
  }
  if (statusElement.dataset.completed === "true") {
    return;
  }
  if (progressResult.status === "fulfilled") {
    statusElement.dataset.completed = String(Boolean(progressResult.value.completed));
    statusElement.textContent = progressResult.value.completed
      ? "Lesson completed previously."
      : "Lesson not completed yet.";
    if (accessResult.status === "rejected") {
      statusElement.textContent += " Lesson access could not be recorded.";
    }
  } else {
    statusElement.textContent = accessResult.status === "rejected"
      ? "Lesson progress could not be loaded or access recorded."
      : "Lesson progress could not be loaded.";
  }
}

async function selectOfficialPath(path, selectedButton, targetLessonId = null) {
  const requestId = ++officialPathRequestId;
  officialQuizState = null;
  officialLessonRequestId += 1;
  officialSelectedPathId = path.id;
  officialPathDetailTitle.textContent = path.title;
  officialPathDetail.hidden = false;
  officialPathContent.textContent = "Loading learning path...";
  const controller = new AbortController();
  let timeoutId;
  officialPathList.querySelectorAll(".official-path-choice").forEach((button) => {
    button.setAttribute(
      "aria-pressed",
      String(button === selectedButton || button.dataset.pathId === path.id),
    );
  });
  try {
    timeoutId = window.setTimeout(() => controller.abort(), 10000);
    const response = await fetch(
      `/api/learning-paths/${encodeURIComponent(path.id)}`,
      { signal: controller.signal },
    );
    if (!response.ok) {
      throw new Error("Learning path could not be loaded.");
    }
    const detail = await response.json();
    if (requestId !== officialPathRequestId || officialSelectedPathId !== path.id) {
      return;
    }
    if (!Array.isArray(detail.modules) || detail.modules.some((module) => (
      !Array.isArray(module.lessons)
    ))) {
      throw new Error("Learning path response is invalid.");
    }
    if (targetLessonId) {
      const module = detail.modules.find((item) => (
        item.lessons.some((lesson) => lesson.id === targetLessonId)
      ));
      const lesson = module?.lessons.find((item) => item.id === targetLessonId);
      if (module && lesson) {
        renderOfficialLesson(detail, module, lesson);
        return;
      }
    }
    showOfficialPathModules(detail);
  } catch (_error) {
    if (requestId !== officialPathRequestId || officialSelectedPathId !== path.id) {
      return;
    }
    officialPathContent.replaceChildren();
    const error = document.createElement("p");
    error.textContent = "This learning path could not be loaded. Please select it again to retry.";
    officialPathContent.append(error);
  } finally {
    window.clearTimeout(timeoutId);
  }
}

async function loadOfficialLearningPaths() {
  if (officialPathsLoaded || officialPathsLoading) {
    return;
  }
  officialPathsLoading = true;
  officialPathStatus.textContent = "Loading official learning paths...";
  officialPathRetry.hidden = true;
  officialPathDetail.hidden = true;
  officialPathList.replaceChildren();

  let timeoutId;
  try {
    const controller = new AbortController();
    timeoutId = window.setTimeout(() => controller.abort(), 10000);
    const response = await fetch("/api/learning-paths", { signal: controller.signal });
    if (!response.ok) {
      throw new Error("Learning paths could not be loaded.");
    }
    const paths = await response.json();
    if (!Array.isArray(paths) || paths.some((path) => (
      typeof path.id !== "string"
      || typeof path.title !== "string"
      || !Array.isArray(path.modules)
      || path.modules.some((module) => typeof module.title !== "string")
    ))) {
      throw new Error("Learning paths response is invalid.");
    }

    if (paths.length === 0) {
      officialPathStatus.textContent = "No official learning paths are available yet.";
      officialPathsLoaded = true;
      return;
    }

    paths.forEach((path) => {
      const button = document.createElement("button");
      button.className = "official-path-choice";
      button.type = "button";
      button.dataset.pathId = path.id;
      button.setAttribute("aria-pressed", String(path.id === officialSelectedPathId));
      button.setAttribute("aria-controls", "official-path-detail");

      const title = document.createElement("span");
      title.className = "official-path-choice-title";
      title.textContent = path.title;
      const moduleSummary = document.createElement("span");
      moduleSummary.className = "official-path-choice-summary";
      moduleSummary.textContent = `${path.modules.length} ${path.modules.length === 1 ? "module" : "modules"}`;
      button.append(title, moduleSummary);
      button.addEventListener("click", () => selectOfficialPath(path, button));
      officialPathList.append(button);
    });
    officialPathStatus.textContent = `${paths.length} learning ${paths.length === 1 ? "path" : "paths"} available. Select one to view its modules.`;
    officialPathsLoaded = true;
  } catch (_error) {
    officialPathStatus.textContent = "Learning paths could not be loaded. Please try again.";
    officialPathRetry.hidden = false;
  } finally {
    window.clearTimeout(timeoutId);
    officialPathsLoading = false;
  }
}

officialPathRetry.addEventListener("click", () => {
  loadOfficialLearningPaths();
});

function showWorkspace(name) {
  const selected = workspaces.find((workspace) => workspace.dataset.workspace === name)
    || document.querySelector('[data-workspace="home"]');

  if (selected.dataset.workspace !== "home" && dashboardController) {
    dashboardRequestId += 1;
    dashboardController.abort();
    dashboardController = null;
  }
  if (selected.dataset.workspace !== "official-learning-paths") {
    resetOfficialQuizProgress();
  }

  workspaces.forEach((workspace) => {
    workspace.hidden = workspace !== selected;
  });
  navigationLinks.forEach((link) => {
    const isActive = link.getAttribute("href") === `#${selected.dataset.workspace}`;
    link.classList.toggle("active", isActive);
    if (isActive) {
      link.setAttribute("aria-current", "page");
    } else {
      link.removeAttribute("aria-current");
    }
  });
  if (selected.dataset.workspace === "official-learning-paths") {
    loadOfficialLearningPaths();
  }
  if (selected.dataset.workspace === "home") {
    loadDashboardSummary();
  }
  window.scrollTo(0, 0);
}

workspaceLinks.forEach((link) => {
  link.addEventListener("click", () => showWorkspace(link.getAttribute("href").slice(1)));
});
window.addEventListener("hashchange", () => showWorkspace(window.location.hash.slice(1)));
showWorkspace(window.location.hash.slice(1) || "home");
