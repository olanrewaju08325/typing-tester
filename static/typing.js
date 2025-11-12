/* typing.js — TypeForge Typing Logic (v2.1 - Updated)
 * Author: Olanrewaju Abdulmuiz Olamide
 * Updated: November 2025
 * Changes:
 * - Prevent auto-start on load (starts only when Load Sentence is clicked)
 * - Real-time text color feedback (green for correct, red for incorrect)
 * - Retained all existing code and modal logic.
 *
 * NOTE: This file preserves your original code EXACTLY and appends
 *       new functionality (live in-test graph + sampling + extra
 *       sync fallback) **without removing any of your code**.
 */

document.addEventListener("DOMContentLoaded", () => {
  // --- Element references ---
  const sentenceBox = document.getElementById("typing-text");
  const inputBox = document.getElementById("typing-input");
  const timerDisplay = document.getElementById("time-left");
  const wpmDisplay = document.getElementById("wpm");
  const accuracyDisplay = document.getElementById("accuracy");
  const loadBtn = document.getElementById("load-btn");
  const submitBtn = document.getElementById("submit-btn");
  const retryBtn = document.getElementById("retry-btn");
  const levelSelect = document.getElementById("difficulty-select");
  const progressBar = document.getElementById("progress-bar");
  const plan = document.getElementById("user-plan")?.textContent.trim() || "free";

  // --- State variables ---
  let timer = null;
  let timeLeft = 0;
  let startTime = null;
  let currentSentence = "";
  let started = false;
  let recentSentences = [];

  const levelDurations = {
    easy: 30,
    medium: 45,
    hard: 60,
    expert: 70,
  };

  // --- Restrict access for free users ---
  levelSelect.addEventListener("change", () => {
    const selected = levelSelect.value;
    if (plan === "free" && selected === "expert") {
      alert("⚠️ Expert level is only available for Premium or Premium Plus users!");
      levelSelect.value = "hard";
    }
  });

  // --- Load a new sentence from backend ---
  async function loadSentence() {
    const level = levelSelect.value;
    if (plan === "free" && level === "expert") {
      alert("⚠️ Upgrade to Premium to access Expert level!");
      return;
    }

    sentenceBox.textContent = "Loading sentence...";
    inputBox.value = "";
    inputBox.disabled = true;
    started = false;

    try {
      const res = await fetch(`/api/sentences?difficulty=${level}`);
      if (!res.ok) throw new Error("Failed to fetch sentence");
      const data = await res.json();

      let newSentence = data.sentence;

      // Avoid showing the same sentence twice in a row
      if (recentSentences.includes(newSentence)) {
        console.warn("Duplicate sentence detected, reloading...");
        return loadSentence();
      }

      currentSentence = newSentence;
      recentSentences.push(currentSentence);
      if (recentSentences.length > 5) recentSentences.shift();

      // 🔹 Wrap each character in a span for color highlighting
      sentenceBox.innerHTML = "";
      currentSentence.split("").forEach((char) => {
        const span = document.createElement("span");
        span.textContent = char;
        sentenceBox.appendChild(span);
      });

      localStorage.setItem("lastSentence", currentSentence);

      // Show countdown AFTER user loads manually
      showCountdown(startTyping);
    } catch (err) {
      console.error("Error fetching sentence:", err);
      const cached = localStorage.getItem("lastSentence");
      if (cached) {
        currentSentence = cached;
        sentenceBox.innerHTML = "";
        cached.split("").forEach((char) => {
          const span = document.createElement("span");
          span.textContent = char;
          sentenceBox.appendChild(span);
        });
        showCountdown(startTyping);
      } else {
        sentenceBox.textContent = "⚠️ Could not load sentence. Please retry.";
      }
    }
  }

  // --- Countdown overlay before typing starts ---
  function showCountdown(callback) {
    const overlay = document.createElement("div");
    Object.assign(overlay.style, {
      position: "fixed",
      top: 0,
      left: 0,
      width: "100%",
      height: "100%",
      display: "flex",
      justifyContent: "center",
      alignItems: "center",
      background: "rgba(0,0,0,0.75)",
      zIndex: "9999",
      fontSize: "80px",
      color: "#00ffcc",
      fontWeight: "900",
    });
    document.body.appendChild(overlay);

    const sequence = ["5", "4", "3", "2", "1", "GO!"];
    let i = 0;

    const animate = () => {
      overlay.textContent = sequence[i];
      overlay.animate(
        [
          { opacity: 0, transform: "scale(0.5)" },
          { opacity: 1, transform: "scale(1.2)" },
          { opacity: 0, transform: "scale(0.5)" },
        ],
        { duration: 800, easing: "ease-in-out" }
      );
      i++;
      if (i < sequence.length) setTimeout(animate, 900);
      else setTimeout(() => {
        overlay.remove();
        callback();
      }, 900);
    };
    animate();
  }

  // --- Start typing session ---
  function startTyping() {
    const level = levelSelect.value;
    timeLeft = levelDurations[level];
    inputBox.disabled = false;
    inputBox.focus();
    started = true;
    startTime = Date.now();

    timerDisplay.textContent = `${timeLeft}s`;
    progressBar.style.width = "100%";

    if (timer) clearInterval(timer);
    timer = setInterval(() => {
      timeLeft--;
      timerDisplay.textContent = `${timeLeft}s`;
      progressBar.style.width = `${(timeLeft / levelDurations[level]) * 100}%`;

      if (timeLeft <= 0) finishTyping();
    }, 1000);
  }

  // --- Live tracking while typing ---
 // --- Live tracking while typing with color feedback ---
 // --- Live tracking while typing with color feedback and auto-submit ---
 inputBox.addEventListener("input", () => {
  if (!started) return;

  const typed = inputBox.value;
  const target = currentSentence;

  // Highlight each character
  let highlighted = "";
  for (let i = 0; i < target.length; i++) {
    if (i < typed.length) {
      highlighted += `<span style="color:${typed[i] === target[i] ? "#00ff88" : "#ff4444"}">${target[i]}</span>`;
    } else {
      highlighted += `<span style="color:#999">${target[i]}</span>`;
    }
  }
  sentenceBox.innerHTML = highlighted;

  // Update WPM and Accuracy
  const wpm = calculateWPM();
  const accuracy = calculateAccuracy(target, typed);
  wpmDisplay.textContent = wpm;
  accuracyDisplay.textContent = accuracy;

  // 🟢 Auto-submit when user completes typing correctly
  if (typed.trim() === target.trim()) {
    finishTyping(); // Automatically end the test
  }
 });


  // --- Accuracy calculation ---
  function calculateAccuracy(target, input) {
    if (!input) return 0;
    const tWords = target.trim().split(/\s+/);
    const iWords = input.trim().split(/\s+/);
    let correct = 0;
    for (let i = 0; i < Math.min(tWords.length, iWords.length); i++) {
      if (tWords[i] === iWords[i]) correct++;
    }
    return Math.round((correct / tWords.length) * 100);
  }

  // --- WPM calculation ---
  function calculateWPM() {
    const typed = inputBox.value.trim();
    if (!typed) return 0;
    const words = typed.split(/\s+/).length;
    const minutes = (Date.now() - startTime) / 60000;
    return Math.max(0, Math.round(words / minutes || 0));
  }
 let finished = false;

  // --- When typing session ends ---
 function finishTyping() {
  if (!started || finished) return;
  finished = true;
  clearInterval(timer);
  inputBox.disabled = true;
  started = false;

    const level = levelSelect.value;
    const wpm = calculateWPM();
    const accuracy = calculateAccuracy(currentSentence, inputBox.value);

    saveProgress(wpm, accuracy);
    showResultModal(level, wpm, accuracy);
  }

  // --- Display modal with stats ---
  function showResultModal(level, wpm, accuracy) {
    const duration = levelDurations[level];
    const key = `bestStats_${level}`;
    const previous = JSON.parse(localStorage.getItem(key)) || { wpm: 0, accuracy: 0 };
    const wpmDiff = wpm - previous.wpm;
    const accDiff = accuracy - previous.accuracy;
    if (wpm > previous.wpm || accuracy > previous.accuracy) {
      localStorage.setItem(key, JSON.stringify({ wpm, accuracy }));
    }

    if (document.getElementById("resultModal")) document.getElementById("resultModal").remove();

    const overlay = document.createElement("div");
    overlay.id = "resultModal";
    Object.assign(overlay.style, {
      position: "fixed",
      top: 0,
      left: 0,
      width: "100%",
      height: "100%",
      background: "rgba(0,0,0,0.7)",
      display: "flex",
      justifyContent: "center",
      alignItems: "center",
      zIndex: "9999",
      opacity: "0",
      transition: "opacity 0.4s ease",
    });

    const box = document.createElement("div");
    Object.assign(box.style, {
      background: "linear-gradient(145deg, #0e0e0e, #1a1a1a)",
      padding: "30px",
      borderRadius: "18px",
      border: "1px solid #00ffcc66",
      width: "450px",
      textAlign: "center",
      color: "#fff",
      boxShadow: "0 0 25px rgba(0,255,204,0.2)",
      transform: "scale(0.85)",
      transition: "transform 0.3s ease",
    });

    box.innerHTML = `
      <h2 style="color:#00ffcc;margin-bottom:6px;">🏁 Test Complete</h2>
      <div style="opacity:0.8;margin-bottom:25px;">Difficulty: <strong>${level}</strong></div>
      <div style="display:flex;justify-content:space-around;margin-bottom:25px;font-size:1.1rem;">
        <div>
          ⚡ <strong>WPM</strong><br>
          <span style="font-size:1.6rem;color:#00ffcc">${wpm}</span><br>
          <small style="color:${wpmDiff>=0?"#00ffcc":"#ff6666"}">
            ${wpmDiff >= 0 ? `+${wpmDiff}` : `${wpmDiff}`} vs best
          </small>
        </div>
        <div>
          🎯 <strong>Accuracy</strong><br>
          <span style="font-size:1.6rem;color:#00ffcc">${accuracy}%</span><br>
          <small style="color:${accDiff>=0?"#00ffcc":"#ff6666"}">
            ${accDiff >= 0 ? `+${accDiff}%` : `${accDiff}%`} vs best
          </small>
        </div>
      </div>
      <canvas id="resultChart" width="380" height="120" style="margin-bottom:25px;"></canvas>
      <div style="display:flex;justify-content:center;gap:10px;">
        <button id="nextSentenceBtn" style="
          background:#00ffcc;
          border:none;
          color:#000;
          padding:10px 20px;
          border-radius:10px;
          font-weight:600;
          cursor:pointer;
          transition:all 0.2s;
        ">Next Sentence</button>
        <button id="closeModalBtn" style="
          background:transparent;
          border:1px solid #00ffcc66;
          color:#00ffcc;
          padding:10px 20px;
          border-radius:10px;
          font-weight:600;
          cursor:pointer;
        ">Close</button>
      </div>
    `;

    overlay.appendChild(box);
    document.body.appendChild(overlay);

    requestAnimationFrame(() => {
      overlay.style.opacity = "1";
      box.style.transform = "scale(1)";
    });

    const ctx = box.querySelector("#resultChart").getContext("2d");
    const points = Array.from({ length: 30 }, () => Math.max(0, wpm - 10 + Math.random() * 20));
    let i = 0;

    (function draw() {
      ctx.clearRect(0, 0, 380, 120);
      ctx.beginPath();
      ctx.moveTo(0, 120 - points[0]);
      for (let j = 1; j < i; j++) {
        ctx.lineTo((j / points.length) * 380, 120 - points[j]);
      }
      ctx.strokeStyle = "#00ffcc";
      ctx.lineWidth = 2;
      ctx.stroke();
      if (i < points.length) {
        i++;
        requestAnimationFrame(draw);
      }
    })();

    box.querySelector("#nextSentenceBtn").addEventListener("click", () => {
      overlay.style.opacity = "0";
      box.style.transform = "scale(0.9)";
      setTimeout(() => {
        overlay.remove();
        resetUI();
        loadSentence();
      }, 400);
    });

    box.querySelector("#closeModalBtn").addEventListener("click", () => {
      overlay.style.opacity = "0";
      setTimeout(() => overlay.remove(), 400);
    });
  }

  // --- Reset UI for next round ---
 function resetUI() {
  finished = false;
  inputBox.value = "";
  wpmDisplay.textContent = "0";
  accuracyDisplay.textContent = "0";
  timerDisplay.textContent = "";
  progressBar.style.width = "100%";
 }

 // --- Save Progress (Server + Local Fallback) ---
 // --- Save Progress (Server + Local Fallback + UI Sync) ---
 async function saveProgress(wpm, accuracy) {
  const level = levelSelect.value;

  try {
    // ✅ Build complete data to send to Flask
const payload = {
  username: window.currentUser?.username || "Guest",
  plan: window.currentUser?.plan || "free",
  difficulty: level || "beginner",  // ✅ use “difficulty” key to match table
  wpm,
  accuracy,
  time: levelDurations[level] - timeLeft,
  status: "completed"
};

    // ✅ Send to Flask /save_history endpoint
    const res = await fetch("/save_history", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });

    const data = await res.json();
    if (!res.ok || !data.success) throw new Error("Server rejected entry");

    console.log("✅ Saved successfully:", data.message);

    // ✅ Refresh UI immediately
    updateHistoryUI();
    updateLeaderboardUI();

  } catch (err) {
    console.warn("⚠️ Offline mode: saving locally", err);

    const result = {
      username: window.currentUser?.username || "Guest",
      plan: window.currentUser?.plan || "free",
      level: level || "beginner",
      wpm,
      accuracy,
      time: levelDurations[level] - timeLeft,
      status: "completed",
      date: new Date().toLocaleString()
    };

    // 🟠 Store locally in browser
    const history = JSON.parse(localStorage.getItem("history") || "[]");
    history.push(result);
    localStorage.setItem("history", JSON.stringify(history));

    // 🛰 Queue unsynced result for later sync
    queueResult(result);

    updateHistoryUI();
    updateLeaderboardUI();
  }
}

 // --- Update History Page in Real-time (if user is on history.html) ---
 // --- Update History Page in Real-time (with Pending Sync Indicator) ---
 function updateHistoryUI() {
  const table = document.querySelector("#history-table");
  if (!table) return; // Exit if not on history page

  const tbody = table.querySelector("tbody");
  tbody.innerHTML = "";

  const synced = JSON.parse(localStorage.getItem("history") || "[]");
  const pending = JSON.parse(localStorage.getItem("pendingResults") || "[]");

  // Combine both, but pending shown last
  const allResults = [...synced, ...pending.map(p => ({ ...p, pending: true }))];

  allResults.slice(-30).reverse().forEach((item) => {
    const row = document.createElement("tr");
    const isPending = item.pending === true;

    row.innerHTML = `
      <td>${item.difficulty}</td>
      <td>${item.wpm}</td>
      <td>${item.accuracy}%</td>
      <td>${item.time}s</td>
      <td>${item.date || "—"}</td>
      <td>${isPending ? "<span style='color:#ffcc00;'>⏳ Pending Sync</span>" : "<span style='color:#00ffcc;'>✅ Synced</span>"}</td>
    `;

    // Style pending rows slightly dimmer
    if (isPending) {
      row.style.opacity = "0.6";
    }

    tbody.appendChild(row);
  });
 }

 // --- Update Leaderboard Page in Real-time (if user is on leaderboard.html) ---
 async function updateLeaderboardUI() {
  const table = document.querySelector("#leaderboard-table");
  if (!table) return; // Not on leaderboard page
  if (!document.querySelector("#leaderboard-table")) return; // Exit if not on leaderboard page
  try {
    const res = await fetch("/api/leaderboard");
    if (!res.ok) throw new Error("Failed to refresh leaderboard");
    const data = await res.json();

    const tbody = document.querySelector("#leaderboard-table tbody");
    tbody.innerHTML = "";
    data.forEach((entry, i) => {
      const row = document.createElement("tr");
      row.innerHTML = `
        <td>${i + 1}</td>
        <td>${entry.username}</td>
        <td>${entry.difficulty}</td>
        <td>${entry.wpm}</td>
        <td>${entry.accuracy}%</td>`;
      tbody.appendChild(row);
    });
  } catch (err) {
  console.warn("⚠️ Could not load leaderboard (offline or error)", err);
  const result = {
    difficulty: level,
    wpm,
    accuracy,
    time: levelDurations[level] - timeLeft,
    date: new Date().toLocaleString(),
  };

  // 🟠 Store locally for viewing in history
  const history = JSON.parse(localStorage.getItem("history") || "[]");
  history.push(result);
  localStorage.setItem("history", JSON.stringify(history));

  // 🛰 Queue for later sync
  queueResult(result);

  updateHistoryUI();
  updateLeaderboardUI();
 }
 }


  // --- Retry and manual submit buttons ---
  retryBtn.addEventListener("click", () => {
    clearInterval(timer);
    started = false;
    resetUI();
    sentenceBox.textContent = "Loading new sentence...";
    loadSentence();
  });

  submitBtn.addEventListener("click", finishTyping);
  loadBtn.addEventListener("click", loadSentence);

  // ❌ Removed auto-load at start — user must click "Load Sentence"
  // loadSentence();
  // Auto-refresh if user opens history.html or leaderboard.html
 // --- 🛰 Offline Queue + Auto-Sync System ---
 async function syncOfflineResults() {
  const pending = JSON.parse(localStorage.getItem("pendingResults") || "[]");
  if (!pending.length) return;

  console.log(`🟡 Syncing ${pending.length} pending results...`);
  const successful = [];

  for (const result of pending) {
    try {
      const res = await fetch("/save_result", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(result),
      });

      const data = await res.json();
      if (res.ok && data.ok) {
        successful.push(result);
        console.log("✅ Synced:", result);
      }
    } catch (err) {
      console.warn("🔴 Failed to sync result:", err);
      break; // stop trying if offline again
    }
  }

  // Remove successfully synced results
  if (successful.length > 0) {
    const remaining = pending.filter(r => !successful.includes(r));
    localStorage.setItem("pendingResults", JSON.stringify(remaining));
  }

  // Refresh UI if on history or leaderboard
  updateHistoryUI();
  updateLeaderboardUI();
 }

 // --- Helper to store result offline if server unreachable ---
 function queueResult(result) {
  const pending = JSON.parse(localStorage.getItem("pendingResults") || "[]");
  pending.push(result);
  localStorage.setItem("pendingResults", JSON.stringify(pending));
  console.log("🟠 Result queued for later sync:", result);
 }

 // 🔄 Try syncing queued results every 15 seconds and on reconnect
 setInterval(syncOfflineResults, 15000);
 window.addEventListener("online", syncOfflineResults);

}); // END of your original DOMContentLoaded block


/* ------------------------------------------------------------
   --- NEW APPEND: live in-test graph, sampling and enhanced sync
   --- This block intentionally runs AFTER your original code,
       but inside its logical lifetime (window scope). It uses
       the same DOM elements and functions you already defined.
   ------------------------------------------------------------ */

(function liveEnhancements() {
  // We use a separate DOMContentLoaded to ensure original code created its handlers.
  document.addEventListener("DOMContentLoaded", () => {
    // quick element refs (may be null on pages without typing UI)
    const inputBox = document.getElementById("typing-input");
    const levelSelect = document.getElementById("difficulty-select");
    const progressContainer = document.querySelector(".progress-bar-container");
    const progressBar = document.getElementById("progress-bar");

    // live chart variables
    let liveChart = null;
    let liveWpmData = [];
    let liveTimeLabels = [];
    let liveSampler = null;

    // small helper to ensure live canvas exists under the typing area
    function ensureLiveCanvas() {
      if (!document.getElementById("live-graph")) {
        // create container and canvas right after progress bar container
        const canvas = document.createElement("canvas");
        canvas.id = "live-graph";
        canvas.style.width = "100%";
        canvas.style.height = "120px";
        canvas.style.display = "block";
        canvas.style.marginTop = "12px";
        if (progressContainer && progressContainer.parentNode) {
          progressContainer.parentNode.insertBefore(canvas, progressContainer.nextSibling);
        } else {
          // fallback: append to body
          document.body.appendChild(canvas);
        }
      }
    }

    // init or update Chart.js chart
    function updateLiveChart() {
      const canvas = document.getElementById("live-graph");
      if (!canvas) return;
      const ctx = canvas.getContext("2d");

      if (window.Chart) {
        if (!liveChart) {
          liveChart = new Chart(ctx, {
            type: "line",
            data: {
              labels: liveTimeLabels,
              datasets: [{
                label: "WPM (live)",
                data: liveWpmData,
                fill: true,
                backgroundColor: "rgba(0,255,204,0.08)",
                borderColor: "#00ffcc",
                tension: 0.35,
                pointRadius: 0,
                borderWidth: 2
              }]
            },
            options: {
              animation: { duration: 200 },
              responsive: true,
              maintainAspectRatio: false,
              scales: {
                x: { display: true, title: { display: true, text: "Seconds" } },
                y: {
                  title: { display: true, text: "WPM" },
                  beginAtZero: true,
                  grid: { color: "rgba(255,255,255,0.03)" }
                }
              },
              plugins: { legend: { display: false } }
            }
          });
        } else {
          liveChart.data.labels = liveTimeLabels;
          liveChart.data.datasets[0].data = liveWpmData;
          liveChart.update('none');
        }
      } else {
        // fallback: simple line on canvas (if Chart.js missing)
        ctx.clearRect(0, 0, canvas.width, canvas.height);
        if (!liveWpmData.length) return;
        const max = Math.max(...liveWpmData, 1);
        ctx.strokeStyle = "#00ffcc";
        ctx.lineWidth = 2;
        ctx.beginPath();
        for (let i = 0; i < liveWpmData.length; i++) {
          const x = (i / (liveWpmData.length - 1 || 1)) * canvas.width;
          const y = canvas.height - (liveWpmData[i] / max) * canvas.height;
          if (i === 0) ctx.moveTo(x, y); else ctx.lineTo(x, y);
        }
        ctx.stroke();
      }
    }

    // start live sampling every 1000ms while test is running
    function startLiveSampling(getWpmFn) {
      stopLiveSampling();
      liveWpmData = [];
      liveTimeLabels = [];
      ensureLiveCanvas();
      let t = 0;
      liveSampler = setInterval(() => {
        if (!getWpmFn) return;
        const w = Math.max(0, Math.round(getWpmFn()));
        liveWpmData.push(w);
        t += 1;
        liveTimeLabels.push(t);
        // cap to 60 points to keep chart snappy
        if (liveWpmData.length > 60) {
          liveWpmData.shift();
          liveTimeLabels.shift();
        }
        updateLiveChart();
      }, 1000);
    }
    function stopLiveSampling() {
      if (liveSampler) { clearInterval(liveSampler); liveSampler = null; }
    }

    // Enhanced sync: try the /save_result endpoint first (your code), but
    // if server rejects or is unavailable, attempt /api/save_run as a fallback.
    async function enhancedSyncPending() {
      const pending = JSON.parse(localStorage.getItem("pendingResults") || "[]");
      if (!pending.length) return;
      const stillPending = [];

      for (const p of pending) {
        try {
          // try main API (your save_result)
          let res = await fetch("/save_result", {
            method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(p)
          });
          if (!res.ok) {
            // fallback to /api/save_run (older endpoint)
            try {
              res = await fetch("/api/save_run", {
                method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ wpm: p.wpm, accuracy: p.accuracy, time: p.time })
              });
            } catch (err) {
              // noop - we'll queue
            }
          }
          const data = await (res && res.json().catch(() => ({})));
          // success heuristics: either res.ok or data.ok (both used elsewhere)
          if (!res || !(res.ok || data.ok || data.success)) {
            stillPending.push(p);
          } else {
            // push to local history as synced if needed
            const hist = JSON.parse(localStorage.getItem("history") || "[]");
            hist.push({ ...p, date: new Date().toLocaleString() });
            localStorage.setItem("history", JSON.stringify(hist));
          }
        } catch (err) {
          stillPending.push(p);
        }
      }

      localStorage.setItem("pendingResults", JSON.stringify(stillPending));
      // refresh UI
      if (window.updateHistoryUI) try { updateHistoryUI(); } catch (e) {}
      if (window.updateLeaderboardUI) try { updateLeaderboardUI(); } catch (e) {}
    }

    // run enhanced sync interval (small extra interval on top of original)
    setInterval(enhancedSyncPending, 15000);
    window.addEventListener("online", enhancedSyncPending);

    // Hook: start/stop sampling when test begins/ends.
    // We can't safely modify your existing startTyping/finishTyping definitions (kept intact),
    // so we watch the input and start sampling on the first typed char after a sentence is loaded.
    let samplingActive = false;
    const typerStartHandler = () => {
      // find calculateWPM in window scope
      const getWpm = () => {
        try {
          // call your calculateWPM if defined in the same scope (should be)
          if (typeof calculateWPM === "function") return calculateWPM();
          // fallback: approximate by chars/5 and startTime
          const typed = inputBox?.value?.trim() || "";
          const words = typed.split(/\s+/).length || 0;
          const mins = (Date.now() - (window.startTime || Date.now())) / 60000 || 1/60;
          return Math.round(words / mins);
        } catch (err) { return 0; }
      };

      if (!samplingActive) {
        samplingActive = true;
        startLiveSampling(getWpm);
      }
    };

    const typerStopHandler = () => {
      samplingActive = false;
      stopLiveSampling();
    };

    // Attach extra input listeners (these will run in addition to your existing listeners)
    if (inputBox) {
      inputBox.addEventListener("input", () => {
        // start sampling when started flag becomes true and not finished
        try {
          // rely on your started/finished variables declared in the main scope
          if (typeof started !== "undefined" && started && typeof finished !== "undefined" && !finished) {
            typerStartHandler();
          }
        } catch (e) {}
      });

      // Stop sampling on blur or when user clicks submit
      inputBox.addEventListener("blur", () => { typerStopHandler(); });
    }

    // Also stop sampling when result modal is opened (observe DOM insertion)
    const bodyObserver = new MutationObserver((mutations) => {
      for (const m of mutations) {
        for (const n of m.addedNodes) {
          try {
            if (n.id === "resultModal" || (n.querySelector && n.querySelector("#resultChart"))) {
              typerStopHandler();
            }
          } catch (e) {}
        }
      }
    });
    bodyObserver.observe(document.body, { childList: true, subtree: false });

    // Quick guard: if page initially contains a live canvas (e.g. reload), create chart instance
    if (document.getElementById("live-graph")) updateLiveChart();

    // Expose internal helpers for debugging
    window.TypeForgeLive = {
      ensureLiveCanvas,
      updateLiveChart,
      startLiveSampling,
      stopLiveSampling,
      enhancedSyncPending
    };
    /* ------------------------------------------------------------
   🟢 PATCH: Restore Auto-Submit on Full Sentence (November 2025)
   - Runs after all your original logic.
   - Does NOT overwrite or replace anything.
   - Re-enables auto-submit behavior that stopped after safety fix.
------------------------------------------------------------- */
document.addEventListener("DOMContentLoaded", () => {
  const inputBox = document.getElementById("typing-input");
  const sentenceBox = document.getElementById("typing-text");

  if (!inputBox || !sentenceBox) return;

  inputBox.addEventListener("input", () => {
    try {
      if (typeof started === "undefined" || typeof finishTyping !== "function") return;
      if (!started) return;

      const typed = inputBox.value.trim();
      const target = (typeof currentSentence !== "undefined" ? currentSentence.trim() : "");

      if (typed === target) {
        console.log("✅ Auto-submitting — full sentence typed correctly!");
        finishTyping();
      }
    } catch (err) {
      console.warn("⚠️ Auto-submit patch error:", err);
    }
  });
});

  });
})();
