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

function showWorkspace(name) {
  const selected = workspaces.find((workspace) => workspace.dataset.workspace === name)
    || document.querySelector('[data-workspace="home"]');

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
  window.scrollTo(0, 0);
}

workspaceLinks.forEach((link) => {
  link.addEventListener("click", () => showWorkspace(link.getAttribute("href").slice(1)));
});
window.addEventListener("hashchange", () => showWorkspace(window.location.hash.slice(1)));
showWorkspace(window.location.hash.slice(1) || "home");
