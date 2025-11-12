// Typing Tester Script — accurate timing, WPM, colors & saving

let timer = null;
let timeLeft = 0;
let totalTime = 0;
let startTime = 0;
let timerStarted = false;
let targetSentence = "";
let currentLevel = "easy";

const $ = id => document.getElementById(id);

function updateTimerUI() {
  if ($("timer")) $("timer").textContent = `Time: ${timeLeft}s`;
}
function updateProgress() {
  const bar = $("progress-bar");
  if (bar && totalTime) bar.style.width = `${((totalTime - timeLeft) / totalTime) * 100}%`;
}

function startTest() {
  currentLevel = $("difficulty").value;
  fetch(`/get_sentence/${currentLevel}`)
    .then(res => res.json())
    .then(data => {
      targetSentence = data.sentence;
      totalTime = timeLeft = data.time_limit;
      $("typing-text").textContent = targetSentence;
      $("typing-input").value = "";
      $("typing-input").disabled = false;
      $("typing-input").focus();
      $("result-box").classList.add("hidden");
      timerStarted = false;
      clearInterval(timer);
      updateTimerUI();
      updateProgress();
    });
}

function startCountdown() {
  if (timerStarted) return;
  timerStarted = true;
  startTime = Date.now();
  timer = setInterval(() => {
    timeLeft--;
    updateTimerUI();
    updateProgress();
    if (timeLeft <= 0) {
      clearInterval(timer);
      finishTest();
    }
  }, 1000);
}

function handleTyping() {
  const input = $("typing-input").value;
  if (!timerStarted && input.trim().length > 0) startCountdown();

  let displayHTML = "";
  let correctChars = 0;

  for (let i = 0; i < targetSentence.length; i++) {
    if (i < input.length) {
      if (input[i] === targetSentence[i]) {
        displayHTML += `<span style="color:#00ff99;">${targetSentence[i]}</span>`;
        correctChars++;
      } else {
        displayHTML += `<span style="color:#ff5555;">${targetSentence[i]}</span>`;
      }
    } else {
      displayHTML += `<span style="color:#ccc;">${targetSentence[i]}</span>`;
    }
  }

  $("typing-text").innerHTML = displayHTML;

  if (input.trim() === targetSentence.trim()) {
    clearInterval(timer);
    finishTest();
  }
}

function finishTest() {
  $("typing-input").disabled = true;
  $("result-box").classList.remove("hidden");

  const typed = $("typing-input").value.trim();
  const elapsed = (Date.now() - startTime) / 1000;
  const words = typed.split(/\s+/).filter(Boolean).length;
  const wpm = Math.round(words / (elapsed / 60));
  let correct = 0;
  for (let i = 0; i < Math.min(typed.length, targetSentence.length); i++) {
    if (typed[i] === targetSentence[i]) correct++;
  }
  const accuracy = Math.round((correct / targetSentence.length) * 100);

  $("speed").textContent = wpm;
  $("accuracy").textContent = accuracy;
  $("time").textContent = (totalTime - timeLeft).toFixed(1);

  $("save-status").textContent = "Saving...";
  fetch("/submit_result", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({
      typed,
      target: targetSentence,
      elapsed,
      level: currentLevel
    })
  })
    .then(res => res.json())
    .then(() => {
      $("save-status").textContent = "Saved ✅";
    })
    .catch(() => {
      $("save-status").textContent = "Save failed ❌";
    });
}

function retryTest() {
  $("typing-input").value = "";
  $("typing-input").disabled = false;
  $("typing-text").textContent = "Click “Start Test” to begin typing...";
  $("result-box").classList.add("hidden");
  clearInterval(timer);
  timerStarted = false;
  updateTimerUI();
  updateProgress();
}

document.addEventListener("DOMContentLoaded", () => {
  $("start-btn").addEventListener("click", startTest);
  $("typing-input").addEventListener("input", handleTyping);
  $("submit-btn").addEventListener("click", finishTest);
  $("retry-btn").addEventListener("click", retryTest);

  $("copy-btn").addEventListener("click", () => {
    const acct = $("acct-number").innerText;
    navigator.clipboard.writeText(acct);
    const status = $("copy-status");
    status.style.display = "inline";
    setTimeout(() => (status.style.display = "none"), 2000);
  });
});
