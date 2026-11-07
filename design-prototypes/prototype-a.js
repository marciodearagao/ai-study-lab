const lessons = [
  {
    id: "welcome",
    title: "Welcome to the course",
    module: "Introduction",
    question: "What is the main goal of this learning path?",
    correct: "B",
    answers: ["Memorize every AI term", "Build a clear beginner understanding of AI", "Replace every tool you already use", "Write a large AI program"],
    paragraphs: [
      "Welcome to AI Fundamentals. This path introduces the basic ideas behind artificial intelligence in clear, practical steps.",
      "You will explore what AI is, where people use it, and how some systems learn from examples. Each lesson ends with a short check for understanding.",
      "You can move through the lessons in order or use the course outline to revisit a topic."
    ]
  },
  {
    id: "what-is-ai",
    title: "What Is Artificial Intelligence?",
    module: "Introduction",
    question: "What can some AI systems learn from examples?",
    correct: "A",
    answers: ["Patterns that help with a task", "Human feelings and life experiences", "Only the appearance of a computer screen", "Nothing; examples are never useful"],
    paragraphs: [
      "Artificial intelligence, or AI, is software designed to do tasks that usually need some human intelligence. These tasks can include understanding words, recognizing pictures, making suggestions, or finding patterns in information.",
      "Some AI systems learn patterns from examples. After seeing many labeled pictures of cats and dogs, for example, a system can learn to sort new pictures. It uses patterns in the examples; it does not learn exactly like a person.",
      "AI is useful in voice assistants, translation apps, and recommendation systems. It can also make mistakes, so people should check important results."
    ],
    subheading: "Learning from examples"
  },
  {
    id: "ai-around-us",
    title: "AI Around Us",
    module: "Introduction",
    question: "Which tool might use AI to suggest a song?",
    correct: "C",
    answers: ["A paper notebook", "A plain wall clock", "A music app that learns your preferences", "An unplugged lamp"],
    paragraphs: [
      "AI can be part of tools people already use. It may help a voice assistant understand a request or help a map suggest a route.",
      "A recommendation system can compare patterns in choices and suggest something a person may like. The suggestion is a prediction, not a guarantee.",
      "Not every digital tool uses AI. Looking at what a tool does can help us tell the difference."
    ],
    subheading: "Everyday examples"
  },
  {
    id: "learning-examples",
    title: "Learning from Examples",
    module: "How AI Learns",
    question: "What helps a system learn to sort example pictures?",
    correct: "B",
    answers: ["Changing the screen color", "Finding repeated patterns in labeled examples", "Guessing without information", "Copying a person's feelings"],
    paragraphs: [
      "Some AI systems are trained with examples. A training example gives the system information it can use to find a pattern.",
      "If pictures are labeled, the system can compare their features with those labels. Later, it can use the patterns it found to sort a new picture.",
      "The quality and variety of examples matter. Limited examples can lead to mistakes."
    ],
    subheading: "From examples to patterns"
  },
  {
    id: "patterns",
    title: "Patterns and Predictions",
    module: "How AI Learns",
    question: "An AI prediction is best understood as…",
    correct: "A",
    answers: ["A result based on patterns, which can still be wrong", "A promise that the future is certain", "A human feeling", "A fact that never needs checking"],
    paragraphs: [
      "A pattern is something that appears repeatedly in information. AI systems can use patterns to make a prediction or recommendation.",
      "For example, a system may notice that certain words often appear together and use that pattern to suggest the next word.",
      "A prediction can be useful, but it is not certain. People should consider the context and check important results."
    ],
    subheading: "Predictions are not guarantees"
  },
  {
    id: "limitations",
    title: "What AI Can Get Wrong",
    module: "How AI Learns",
    question: "What should we do with an important AI result?",
    correct: "D",
    answers: ["Assume it is always correct", "Ignore its limits", "Share it without checking", "Check it using reliable information"],
    paragraphs: [
      "AI systems can make mistakes. They may miss context, rely on incomplete examples, or produce an answer that sounds confident but is incorrect.",
      "A useful habit is to check important results against reliable sources and use human judgment.",
      "Knowing that a tool has limits helps us decide when its output is useful and when it needs more review."
    ],
    subheading: "Use AI thoughtfully"
  }
];

const lessonLinks = [...document.querySelectorAll("[data-lesson]")];
const courseDisclosure = document.querySelector("#course-content");
const lessonTitle = document.querySelector("#lesson-title");
const lessonCopy = document.querySelector("#lesson-copy");
const lessonModule = document.querySelector("#lesson-module");
const lessonPosition = document.querySelector("#lesson-position");
const breadcrumbLesson = document.querySelector("#breadcrumb-lesson");
const questionLegend = document.querySelector("#quiz-question");
const questionCount = document.querySelector("#question-count");
const feedback = document.querySelector("#quiz-feedback");
const answerInputs = [...document.querySelectorAll(".answer-option input")];
const previousButton = document.querySelector("#previous-lesson");
const nextButton = document.querySelector("#next-lesson");
let currentIndex = 1;

function updateLesson(index) {
  currentIndex = Math.max(0, Math.min(index, lessons.length - 1));
  const lesson = lessons[currentIndex];
  const count = lessons.length;

  lessonTitle.textContent = lesson.title;
  lessonModule.textContent = lesson.module;
  lessonPosition.textContent = `Lesson ${currentIndex + 1} of ${count}`;
  breadcrumbLesson.textContent = lesson.title;
  lessonCopy.replaceChildren();

  lesson.paragraphs.forEach((paragraph, paragraphIndex) => {
    if (paragraphIndex === 1 && lesson.subheading) {
      const subheading = document.createElement("h3");
      subheading.textContent = lesson.subheading;
      lessonCopy.append(subheading);
    }
    const item = document.createElement("p");
    item.textContent = paragraph;
    lessonCopy.append(item);
  });

  questionLegend.textContent = lesson.question;
  questionCount.textContent = `Question 1 of ${count}`;
  answerInputs.forEach((input, answerIndex) => {
    input.checked = false;
    input.value = String.fromCharCode(65 + answerIndex);
    input.nextElementSibling.nextElementSibling.textContent = lesson.answers[answerIndex];
  });
  feedback.textContent = "Choose one answer to check your understanding.";

  lessonLinks.forEach((link) => {
    const active = link.dataset.lesson === lesson.id;
    link.classList.toggle("current", active);
    if (active) {
      link.setAttribute("aria-current", "page");
    } else {
      link.removeAttribute("aria-current");
    }
  });
  previousButton.disabled = currentIndex === 0;
  nextButton.disabled = currentIndex === count - 1;

  if (window.matchMedia("(max-width: 1100px)").matches) {
    courseDisclosure.open = false;
    document.querySelector("#lesson").scrollIntoView({ block: "start" });
  }
}

lessonLinks.forEach((link) => {
  link.addEventListener("click", () => {
    const index = lessons.findIndex((lesson) => lesson.id === link.dataset.lesson);
    if (index >= 0) updateLesson(index);
  });
});

previousButton.addEventListener("click", () => updateLesson(currentIndex - 1));
nextButton.addEventListener("click", () => updateLesson(currentIndex + 1));

document.querySelector("#check-answer").addEventListener("click", () => {
  const selected = answerInputs.find((input) => input.checked);
  if (!selected) {
    feedback.textContent = "Choose an answer before checking.";
    return;
  }
  const lesson = lessons[currentIndex];
  feedback.textContent = selected.value === lesson.correct
    ? "That is correct."
    : `Not quite. The correct answer is ${lesson.correct}.`;
});

const desktopSidebar = window.matchMedia("(min-width: 1101px)");
function matchSidebarToViewport() {
  courseDisclosure.open = desktopSidebar.matches;
}
matchSidebarToViewport();
desktopSidebar.addEventListener("change", matchSidebarToViewport);

const mentorOrb = document.querySelector("#mentor-orb");
const mentorPanel = document.querySelector("#mentor-panel");
const mentorClose = document.querySelector("#mentor-close");

function closeMentorPanel({ restoreFocus = true } = {}) {
  if (mentorPanel.hidden) return;
  mentorPanel.hidden = true;
  mentorOrb.setAttribute("aria-expanded", "false");
  if (restoreFocus) mentorOrb.focus();
}

mentorOrb.addEventListener("click", () => {
  const isOpening = mentorPanel.hidden;
  mentorPanel.hidden = !isOpening;
  mentorOrb.setAttribute("aria-expanded", String(isOpening));
  if (isOpening) mentorClose.focus();
});

mentorClose.addEventListener("click", () => closeMentorPanel());

document.addEventListener("keydown", (event) => {
  if (event.key === "Escape") closeMentorPanel();
});

document.addEventListener("pointerdown", (event) => {
  if (!event.target.closest(".mentor-widget")) {
    closeMentorPanel({ restoreFocus: false });
  }
});
