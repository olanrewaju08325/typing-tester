// main.js — TypeForge unified typing logic + chart.js + dynamic difficulty
// Use shared global started flag to avoid redeclaration
window.started = window.started || false;

function $(id) { return document.getElementById(id); }

let started = false;
let startTime = 0;
let timerInterval = null;
let currentDifficulty = "easy";
let sentencesData = {};
let currentSentence = "";

// ----------------------------
// Difficulty-based durations
// ----------------------------
const difficultyDurations = {
  easy: 30,
  medium: 45,
  hard: 60,
  expert: 70
};

// ----------------------------
// Countdown + Auto Submit
// ----------------------------
function startCountdown(duration) {
  clearInterval(timerInterval);
  started = true;
  startTime = Date.now();
  const end = startTime + duration * 1000;

  timerInterval = setInterval(() => {
    const now = Date.now();
    const remaining = Math.max(0, Math.round((end - now) / 1000));
    const elapsed = duration - remaining;
    const percent = Math.min(100, Math.round((elapsed / duration) * 100));

    $("progress-bar").style.width = percent + "%";
    $("time-left").textContent = remaining + "s";

    if (remaining <= 0) {
      clearInterval(timerInterval);
      finishTestAuto();
    }
  }, 200);
}

// ----------------------------
// Auto submit + accuracy
// ----------------------------
function finishTestAuto() {
  const input = $("typing-input");
  if (!input) return;

  const text = input.value.trim();
  const words = text.length ? text.split(/\s+/).length : 0;
  const elapsedMs = Date.now() - startTime;
  const minutes = Math.max(1 / 60, elapsedMs / 60000);
  const wpm = Math.round(words / minutes);
  const accuracy = calcAccuracy();

  $("wpm").textContent = wpm;
  $("accuracy").textContent = accuracy;

  fetch("/api/save_run", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ wpm, accuracy, time: new Date().toISOString() }),
  }).finally(() => {
    input.disabled = true;
    $("load-btn").disabled = false;
  });
}

// ----------------------------
// Accuracy + Color Feedback
// ----------------------------
function calcAccuracy() {
  const originalWords = currentSentence.trim().split(/\s+/);
  const typedWords = ($("typing-input")?.value.trim() || "").split(/\s+/);
  if (!originalWords.length) return 0;

  let correct = 0;
  for (let i = 0; i < Math.min(originalWords.length, typedWords.length); i++) {
    if (originalWords[i] === typedWords[i]) correct++;
  }
  return Math.round((correct / originalWords.length) * 100);
}

function updateLiveColors() {
  const textEl = $("typing-text");
  const inputVal = $("typing-input").value.trim();
  const typedWords = inputVal.split(/\s+/);
  const originalWords = currentSentence.trim().split(/\s+/);

  const colored = originalWords.map((word, i) => {
    if (typedWords[i] === undefined) return `<span>${word}</span>`;
    if (typedWords[i] === word)
      return `<span style='color:limegreen'>${word}</span>`;
    return `<span style='color:#ff3b3b'>${word}</span>`;
  });

  textEl.innerHTML = colored.join(" ");
}

// ----------------------------
// Sentences + Difficulty Handling
// ----------------------------
function loadSentencesData() {
  const el = $("sentences-data");
  if (!el) return {};
  try {
    return JSON.parse(el.textContent || "{}");
  } catch (e) {
    console.error("Error parsing sentences-data", e);
    return {};
  }
}

function getRandomSentence(difficulty) {
  const sents = sentencesData[difficulty] || [];
  if (!sents.length) return "";
  const idx = Math.floor(Math.random() * sents.length);
  return sents[idx];
}

function renderSentence(difficulty) {
  const sent = getRandomSentence(difficulty);
  currentSentence = sent;
  $("typing-text").textContent = sent || "No sentences available!";
  const inputEl = $("typing-input");
  inputEl.value = "";
  inputEl.disabled = false;
  inputEl.focus();
  resetTimer(difficulty);
}

// ----------------------------
// Reset Timer
// ----------------------------
function resetTimer(diff = "easy") {
  clearInterval(timerInterval);
  started = false;
  startTime = 0;
  $("progress-bar").style.width = "0%";
  const dur = difficultyDurations[diff] || 60;
  $("time-left").textContent = dur + "s";
  $("wpm").textContent = "0";
  $("accuracy").textContent = "0";
}

// ----------------------------
// Button Logic
// ----------------------------
function initButtons() {
  $("load-btn").addEventListener("click", () => {
    renderSentence(currentDifficulty);
    $("load-btn").disabled = true;
  });

  $("submit-btn").addEventListener("click", finishTestAuto);

  $("retry-btn").addEventListener("click", () => {
    renderSentence(currentDifficulty);
  });
}

// ----------------------------
// Init
// ----------------------------
document.addEventListener("DOMContentLoaded", () => {
  sentencesData = loadSentencesData();

  const userPlan = $("user-plan") ? $("user-plan").textContent.trim() : "free";
  const difficultySelect = $("difficulty-select");

  if (difficultySelect) {
    difficultySelect.addEventListener("change", () => {
      currentDifficulty = difficultySelect.value;
      if (
        (currentDifficulty === "expert" || currentDifficulty === "hard") &&
        userPlan === "free"
      ) {
        alert(
          "You need to upgrade to Premium to access this difficulty or Multiplayer!"
        );
        difficultySelect.value = "easy";
        currentDifficulty = "easy";
        return;
      }
      renderSentence(currentDifficulty);
    });
  }

  if (userPlan === "free") {
    const expertOpt = document.querySelector(
      '#difficulty-select option[value="expert"]'
    );
    if (expertOpt) expertOpt.disabled = true;
  }

  initButtons();
  resetTimer("easy");

  const input = $("typing-input");
  if (input) {
    input.addEventListener("keydown", (e) => {
      if (!started && (e.key.length === 1 || ["Backspace", " "].includes(e.key))) {
        startCountdown(difficultyDurations[currentDifficulty] || 60);
      }
    });
    input.addEventListener("input", updateLiveColors);
  }

  const footer = document.querySelector("footer");
  if (footer)
    footer.innerHTML =
      "Created by <strong>Olanrewaju Abdulmuiz Olamide</strong> — Opay: <em>8125815188</em> — TypeForge © 2025";
});
