/* multiplayer.js — TypeForge Multiplayer Logic
 * Created by: Olanrewaju Abdulmuiz Olamide
 * Works with Flask-Socket.IO backend (app.py)
 */

document.addEventListener("DOMContentLoaded", () => {
  const socket = io.connect(window.location.origin);
    const level = document.body.dataset.level || "beginner";

  // Request a race once connected
  socket.on("connect", () => {
    console.log("Connected to multiplayer server, requesting race...");
    socket.emit("request_race", { level });
  });

  const sentenceEl = document.getElementById("sentence");
  const inputEl = document.getElementById("input");
  const countdownEl = document.getElementById("countdown");
  const progressContainer = document.getElementById("progress-container");

  let currentSentence = "";
  let players = {};
  let started = false;

  // --- Receive sentence from server ---
  socket.on("new_sentence", (data) => {
    currentSentence = data.sentence;
    sentenceEl.textContent = currentSentence;
    showCountdown(() => startTyping());
  });

  // --- Countdown animation (5→GO) ---
  function showCountdown(callback) {
    const sequence = ["5", "4", "3", "2", "1", "GO!"];
    let i = 0;
    countdownEl.style.display = "block";

    const next = () => {
      countdownEl.textContent = sequence[i];
      countdownEl.style.animation = "pop 1s ease-in-out";
      i++;
      if (i < sequence.length) {
        setTimeout(next, 900);
      } else {
        setTimeout(() => {
          countdownEl.style.display = "none";
          callback();
        }, 900);
      }
    };
    next();
  }

  // --- Start typing ---
  function startTyping() {
    inputEl.disabled = false;
    inputEl.focus();
    started = true;
  }

  // --- Update progress as user types ---
  inputEl.addEventListener("input", () => {
    if (!started || !currentSentence) return;
    const progress = (inputEl.value.length / currentSentence.length) * 100;
    socket.emit("progress_update", { progress: progress });

    // if user finishes the sentence
    if (inputEl.value.trim() === currentSentence.trim()) {
      socket.emit("race_finished", { username: window.username });
      inputEl.disabled = true;
    }
  });

  // --- Receive progress updates from server ---
  socket.on("update_progress", (data) => {
    players = data.players;
    updateProgressBars();
  });

  // --- Display progress bars dynamically ---
  function updateProgressBars() {
    progressContainer.innerHTML = "";
    Object.keys(players).forEach((name) => {
      const wrapper = document.createElement("div");
      wrapper.className = "player-progress";

      const fill = document.createElement("div");
      fill.className = "player-fill";
      fill.style.width = players[name] + "%";

      const label = document.createElement("span");
      label.className = "player-name";
      label.textContent = `${name} — ${Math.round(players[name])}%`;

      wrapper.appendChild(fill);
      wrapper.appendChild(label);
      progressContainer.appendChild(wrapper);
    });
  }

  // --- Race finished event ---
  socket.on("race_finished", (data) => {
    alert(`🏁 Race finished! Winner: ${data.winner}`);
    inputEl.disabled = true;
  });

  // --- Handle disconnection ---
  socket.on("disconnect", () => {
    inputEl.disabled = true;
    sentenceEl.textContent = "⚠️ Connection lost. Please reload.";
  });
});
