/* typing.js — Combined TypeForge logic (jQuery + Chart.js)
 * Merged by assistant for Olanrewaju Abdulmuiz Olamide
 *
 * Features:
 * - Monkeytype-style wrapped typing area (per-char spans)
 * - Countdown (5..4..3..2..1..GO!)
 * - Per-char coloring (correct/incorrect/current)
 * - Auto-submit when finished or time ends
 * - WPM sampling and Chart.js smooth line in modal
 * - Offline queueing + sync
 * - Live JSON updates for /api/history and /api/leaderboard
 */

(function ($) {
  "use strict";

  // helper to get element by id quickly (jQuery version)
  function $id(id) { return $('#' + id); }

  // config / state
  const testModes = { time: 'Time', words: 'Words', quote: 'Quote', zen: 'Zen', practice: 'Practice', challenge: 'Challenge', puzzle: 'Puzzle', code: 'Code' };
  let currentMode = 'time';
  let currentLength = 30;
  let currentLanguage = 'english';
  let punctuationEnabled = false;
  let numbersEnabled = false;
  let soundEnabled = false;
  let blindMode = false;
  let stopOnError = false;
  let caretStyle = 'default';
  let started = false;
  let finished = false;
  let startTime = 0;
  let timeLeft = 0;
  let timerInterval = null;
  let samplingInterval = null;
  let wpmSamples = [];
  let rawWpmSamples = [];
  let currentSentence = "";
  let recentSentences = [];
  let charIndex = 0;
  let errors = 0;
  let totalChars = 0;
  let keyHeatmap = {}; // track key press counts for heatmap
  let errorAnalysis = {}; // track common typing errors
  let customWordList = []; // user uploaded word list

  // DOM elements
  const $sentenceBox = $id('typing-text');
  const $inputBox = $id('typing-input');
  const $timeLeft = $id('time-left');
  const $wpm = $id('wpm');
  const $accuracy = $id('accuracy');
  const $consistency = $id('consistency');
  const $rawWpm = $id('raw-wpm');
  const $loadBtn = $id('load-btn');
  const $submitBtn = $id('submit-btn');
  const $retryBtn = $id('retry-btn');
  const $testMode = $id('test-mode');
  const $testLength = $id('test-length');
  const $language = $id('language');
  const $punctuation = $id('punctuation');
  const $numbers = $id('numbers');
  const $sound = $id('sound');
  const $blindMode = $id('blind-mode');
  const $stopOnError = $id('stop-on-error');
  const $theme = $id('theme');
  const $progressBar = $id('progress-bar');
  const userPlan = ($id('user-plan').text() || 'free').trim();

  // Utility: attempt posting result to preferred endpoints
  async function postResultToServer(payload) {
    // try /save_result (app.py has this)
    try {
      const r = await fetch('/save_result', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      const data = await r.json().catch(() => ({}));
      if (r.ok && (data.ok || data.status === 'success' || data.saved)) {
        return { ok: true, data };
      }
    } catch (e) { /* ignore, will fallback */ }

    // fallback to /api/save_run
    try {
      const r2 = await fetch('/api/save_run', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload)
      });
      const d2 = await r2.json().catch(() => ({}));
      if (r2.ok) return { ok: true, data: d2 };
    } catch (e) { /* ignore */ }

    return { ok: false };
  }

  // Render sentence as char spans (keeps wrapping like paragraph)
  function renderSentenceAsSpans(sentence) {
    $sentenceBox.empty();
    // Use <span class="char"> for each character
    for (let i = 0; i < sentence.length; i++) {
      const ch = sentence[i];
      const $span = $('<span>').addClass('char').text(ch);
      $sentenceBox.append($span);
    }
    // allow wrapping
    $sentenceBox.css('white-space', 'pre-wrap');
  }

  // Load sentence from backend
  async function loadSentence() {
    $sentenceBox.text('Loading...');
    $inputBox.val('').prop('disabled', true);
    started = false;
    finished = false;
    clearAllIntervals();

    // Get current settings
    currentMode = $testMode.val();
    currentLength = $testLength.val();
    currentLanguage = $language.val();
    punctuationEnabled = $punctuation.is(':checked');
    numbersEnabled = $numbers.is(':checked');
    soundEnabled = $sound.is(':checked');
    blindMode = $blindMode.is(':checked');
    stopOnError = $stopOnError.is(':checked');
    caretStyle = $caretStyle.val();

    try {
      let sentence;
      if (customWordList.length > 0 && currentMode !== 'custom') {
        // Use custom word list
        const wordCount = currentMode === 'words' ? parseInt(currentLength) : 30;
        const selectedWords = [];
        for (let i = 0; i < wordCount; i++) {
          selectedWords.push(customWordList[Math.floor(Math.random() * customWordList.length)]);
        }
        sentence = selectedWords.join(' ');
      } else {
        // Use API
        const params = new URLSearchParams({
          mode: currentMode,
          length: currentLength,
          language: currentLanguage,
          punctuation: punctuationEnabled,
          numbers: numbersEnabled,
          custom_text: currentMode === 'custom' ? $id('custom-text').val() : ''
        });
        const res = await fetch(`/api/sentences?${params}`);
        if (!res.ok) throw new Error('fetch failed');
        const data = await res.json();
        sentence = data.text || data.sentence || 'The quick brown fox jumps over the lazy dog.';
      }

      // avoid immediate duplicates
      if (recentSentences.includes(sentence) && recentSentences.length < 20) {
        return loadSentence();
      }

      currentSentence = sentence;
      recentSentences.push(sentence);
      if (recentSentences.length > 20) recentSentences.shift();

      renderSentenceAsSpans(currentSentence);
      if (blindMode) {
        $sentenceBox.find('.char').css('color', 'transparent').css('text-shadow', '0 0 8px rgba(255,255,255,0.3)');
      }
      localStorage.setItem('lastSentence', currentSentence);

      // show countdown then start typing
      showCountdown(() => startTyping());
    } catch (err) {
      console.error('Error fetching sentence:', err);
      const cached = localStorage.getItem('lastSentence');
      if (cached) {
        currentSentence = cached;
        renderSentenceAsSpans(currentSentence);
        showCountdown(() => startTyping());
      } else {
        $sentenceBox.text('⚠️ Could not load text. Please retry.');
      }
    }
  }

  // Countdown overlay 5..4..3..2..1..GO!
  function showCountdown(onDone) {
    const seq = ['5','4','3','2','1','GO!'];
    const $overlay = $('<div>').addClass('tf-countdown-overlay').css({
      position:'fixed', inset:0, display:'flex', justifyContent:'center', alignItems:'center',
      background:'rgba(0,0,0,0.75)', zIndex: 99999, fontSize:'110px', color: '#ffd166', fontWeight:900
    }).appendTo('body');

    let i = 0;
    (function step(){
      $overlay.text(seq[i]);
      $overlay.animate({opacity:1, transform: 'scale(1.05)'}, 300);
      i++;
      if (i < seq.length) setTimeout(step, 900);
      else setTimeout(() => { $overlay.remove(); onDone && onDone(); }, 900);
    })();
  }

  // Start typing session
  function startTyping() {
    startTime = Date.now();
    started = true;
    finished = false;
    wpmSamples = [];
    rawWpmSamples = [];
    charIndex = 0;
    errors = 0;
    totalChars = currentSentence.length;
    keyHeatmap = {}; // reset heatmap
    errorAnalysis = {}; // reset error analysis

    $inputBox.prop('disabled', false).focus();
    $submitBtn.removeClass('hidden');
    $loadBtn.addClass('hidden');

    if (currentMode === 'time') {
      timeLeft = parseInt(currentLength);
      $timeLeft.text(`${timeLeft}s`);
      $progressBar.css('width', '100%');

      // countdown
      timerInterval = setInterval(() => {
        timeLeft--;
        if (timeLeft < 0) timeLeft = 0;
        $timeLeft.text(`${timeLeft}s`);
        const pct = ((timeLeft / parseInt(currentLength)) * 100).toFixed(2);
        $progressBar.css('width', pct + '%');

        if (timeLeft <= 0) {
          clearAllIntervals();
          finishTyping();
        }
      }, 1000);
    } else if (currentMode === 'words') {
      // For words mode, track word count
      $timeLeft.text('Words: 0/' + currentLength);
      $progressBar.css('width', '0%');
    } else if (currentMode === 'quote') {
      // Quote mode is time-based
      timeLeft = 60; // Default 60 seconds for quotes
      $timeLeft.text(`${timeLeft}s`);
      $progressBar.css('width', '100%');

      timerInterval = setInterval(() => {
        timeLeft--;
        if (timeLeft < 0) timeLeft = 0;
        $timeLeft.text(`${timeLeft}s`);
        const pct = ((timeLeft / 60) * 100).toFixed(2);
        $progressBar.css('width', pct + '%');

        if (timeLeft <= 0) {
          clearAllIntervals();
          finishTyping();
        }
      }, 1000);
    } else if (currentMode === 'zen') {
      // Zen mode - no timer
      $timeLeft.text('∞');
      $progressBar.css('width', '100%');
    } else if (currentMode === 'practice') {
      // Practice mode - focus on accuracy, slower pace
      $timeLeft.text('Practice');
      $progressBar.css('width', '100%');
    } else if (currentMode === 'challenge') {
      // Challenge mode - timed with WPM goal
      timeLeft = parseInt(currentLength) || 60;
      $timeLeft.text(`${timeLeft}s (Goal: ${Math.max(40, parseInt(currentLength) * 2)} WPM)`);
      $progressBar.css('width', '100%');

      timerInterval = setInterval(() => {
        timeLeft--;
        if (timeLeft < 0) timeLeft = 0;
        $timeLeft.text(`${timeLeft}s (Goal: ${Math.max(40, parseInt(currentLength) * 2)} WPM)`);
        const pct = ((timeLeft / (parseInt(currentLength) || 60)) * 100).toFixed(2);
        $progressBar.css('width', pct + '%');

        if (timeLeft <= 0) {
          clearAllIntervals();
          finishTyping();
        }
      }, 1000);
    } else if (currentMode === 'puzzle') {
      // Puzzle mode - unscramble words
      $timeLeft.text('Puzzle Mode');
      $progressBar.css('width', '100%');
    } else if (currentMode === 'code') {
      // Code mode - programming snippets
      $timeLeft.text('Code Mode');
      $progressBar.css('width', '100%');
    }

    // sample WPM every second
    samplingInterval = setInterval(() => {
      const w = calculateWPM();
      const rawW = calculateRawWPM();
      wpmSamples.push(w);
      rawWpmSamples.push(rawW);
    }, 1000);
  }

  function clearAllIntervals() {
    if (timerInterval) { clearInterval(timerInterval); timerInterval = null; }
    if (samplingInterval) { clearInterval(samplingInterval); samplingInterval = null; }
  }

  // Calculate WPM
  function calculateWPM() {
    const typed = $inputBox.val() || '';
    if (!typed || !startTime) return 0;
    const words = typed.trim().split(/\s+/).filter(Boolean).length;
    const minutes = Math.max(0.001, (Date.now() - startTime) / 60000);
    return Math.max(0, Math.round(words / minutes));
  }

  function calculateRawWPM() {
    const typed = $inputBox.val() || '';
    if (!typed || !startTime) return 0;
    const chars = typed.length;
    const minutes = Math.max(0.001, (Date.now() - startTime) / 60000);
    return Math.max(0, Math.round((chars / 5) / minutes));
  }

  function calculateAccuracy() {
    const typed = $inputBox.val() || '';
    if (!typed) return 0;
    const correctChars = charIndex - errors;
    return Math.round((correctChars / charIndex) * 100) || 0;
  }

  function calculateConsistency() {
    if (wpmSamples.length < 2) return 0;
    const avg = wpmSamples.reduce((a, b) => a + b, 0) / wpmSamples.length;
    const variance = wpmSamples.reduce((sum, wpm) => sum + Math.pow(wpm - avg, 2), 0) / wpmSamples.length;
    const stdDev = Math.sqrt(variance);
    return Math.round((1 - (stdDev / avg)) * 100) || 0;
  }

  // Per-character coloring and cursor handling
  $inputBox.on('input', function () {
    if (!started || finished) return;
    const typed = $inputBox.val() || '';
    const chars = $sentenceBox.find('.char');

    let currentErrors = 0;
    for (let i = 0; i < chars.length; i++) {
      const $ch = $(chars[i]);
      const expected = $ch.text();
      const typedChar = typed[i] || '';

      $ch.removeClass('correct incorrect current-char');
      $ch.css({ color: '#999', background: 'transparent' });

      if (typedChar === expected && typedChar !== '') {
        $ch.addClass('correct');
        $ch.css('color', '#e6f9f0'); // light/white
        if (blindMode) $ch.css('text-shadow', 'none');
        if (typedChar !== ' ') playSound('correct');
      } else if (typedChar && typedChar !== expected) {
        $ch.addClass('incorrect');
        $ch.css('color', '#ff6b6b'); // red
        if (blindMode) $ch.css('text-shadow', 'none');
        currentErrors++;
        // Track error analysis
        const errorKey = expected + '->' + typedChar;
        errorAnalysis[errorKey] = (errorAnalysis[errorKey] || 0) + 1;
        playSound('error');
        if (stopOnError) {
          setTimeout(() => finishTyping(), 100);
          return;
        }
      } else if (blindMode && !typedChar) {
        // In blind mode, hide untyped text
        $ch.css('color', 'transparent').css('text-shadow', 'none');
      }

      // current caret / next char
      if (i === typed.length) {
        $ch.addClass('current-char ' + caretStyle);
      }
    }

    errors = currentErrors;
    charIndex = typed.length;

    // update stats
    const wpm = calculateWPM();
    const rawWpm = calculateRawWPM();
    const acc = calculateAccuracy();
    const consistency = calculateConsistency();
    $wpm.text(wpm);
    $rawWpm.text(rawWpm);
    $accuracy.text(acc);
    $consistency.text(consistency);

    // progress
    let pct = 0;
    if (currentMode === 'words') {
      const wordsTyped = typed.trim().split(/\s+/).length;
      pct = ((wordsTyped / parseInt(currentLength)) * 100).toFixed(2);
      $timeLeft.text(`Words: ${wordsTyped}/${currentLength}`);
    } else {
      pct = ((typed.length / (currentSentence.length || 1)) * 100).toFixed(2);
    }
    $progressBar.css('width', pct + '%');

    // check completion
    if (currentMode === 'words') {
      const wordsTyped = typed.trim().split(/\s+/).filter(w => w.length > 0).length;
      if (wordsTyped >= parseInt(currentLength)) {
        setTimeout(() => finishTyping(), 80);
      }
    } else if (typed.trim() === (currentSentence || '').trim()) {
      setTimeout(() => finishTyping(), 80);
    }
  });

  // Finish typing session
  async function finishTyping() {
    if (!started || finished) return;
    finished = true;
    started = false;
    clearAllIntervals();
    $inputBox.prop('disabled', true);
    $submitBtn.addClass('hidden');
    $loadBtn.removeClass('hidden');

    playSound('complete');

    const wpm = calculateWPM();
    const rawWpm = calculateRawWPM();
    const accuracy = calculateAccuracy();
    const consistency = calculateConsistency();
    const timeSpent = currentMode === 'time' ? parseInt(currentLength) - timeLeft : Math.round((Date.now() - startTime) / 1000);

    const result = {
      mode: currentMode,
      length: currentLength,
      wpm,
      rawWpm,
      accuracy,
      consistency,
      time: timeSpent,
      characters: charIndex,
      errors,
      date: new Date().toISOString()
    };

    // Attempt to post to server; if fails, queue locally
    const pushed = await postResultToServer(result);
    if (!pushed.ok) {
      queueResult(result);
      const hist = JSON.parse(localStorage.getItem('history') || '[]');
      hist.push(result);
      localStorage.setItem('history', JSON.stringify(hist));
    }

    // update UI components
    updateHistoryUI();
    updateLeaderboardUI();

    // show result modal with Chart
    const samples = wpmSamples.length ? wpmSamples.slice() : generateFallbackSamples(wpm);
    showResultModal(wpm, rawWpm, accuracy, consistency, timeSpent, charIndex, samples);
    playSound('complete');
  }

  // fallback sample generator based on final WPM
  function generateFallbackSamples(finalWpm, level) {
    const dur = difficultyDurations[level] || 60;
    const n = Math.min(30, Math.max(6, Math.round(dur / 2)));
    const out = [];
    for (let i = 0; i < n; i++) {
      out.push(Math.round(finalWpm * (i / n) + Math.random() * finalWpm * 0.12));
    }
    return out;
  }

  // Render keyboard heatmap
  function renderKeyboardHeatmap() {
    const container = $id('keyboard-heatmap');
    container.empty();

    const keys = 'qwertyuiopasdfghjklzxcvbnm ';
    const maxCount = Math.max(...Object.values(keyHeatmap)) || 1;

    for (let key of keys) {
      const count = keyHeatmap[key] || 0;
      const intensity = count / maxCount;
      let heatClass = '';
      if (intensity > 0.7) heatClass = 'hot';
      else if (intensity > 0.4) heatClass = 'warm';
      else if (intensity > 0) heatClass = 'medium';

      const keyEl = $('<div>').addClass('key-heat').addClass(heatClass).text(key.toUpperCase());
      container.append(keyEl);
    }
  }

  // Render error analysis
  function renderErrorAnalysis() {
    const container = $id('error-analysis');
    container.empty();

    const sortedErrors = Object.entries(errorAnalysis)
      .sort((a, b) => b[1] - a[1])
      .slice(0, 10); // top 10 errors

    for (let [error, count] of sortedErrors) {
      const [expected, typed] = error.split('->');
      const item = $('<div>').addClass('error-item').html(`
        <span>${expected} → ${typed}</span>
        <span>${count}</span>
      `);
      container.append(item);
    }

    if (sortedErrors.length === 0) {
      container.html('<p>No errors recorded</p>');
    }
  }

  // Show result modal (Monkeytype-like)
  function showResultModal(wpm, rawWpm, accuracy, consistency, timeSpent, characters, samples) {
    $('#result-modal').removeClass('hidden');

    // Update modal content
    $id('result-wpm').text(wpm);
    $id('result-accuracy').text(accuracy + '%');
    $id('result-consistency').text(consistency + '%');
    $id('result-raw-wpm').text(rawWpm);
    $id('result-characters').text(characters);
    $id('result-time').text(timeSpent + 's');

    // Render advanced stats
    renderKeyboardHeatmap();
    renderErrorAnalysis();

    // Chart rendering
    const ctx = document.getElementById('result-graph');
    if (ctx && window.Chart) {
      new Chart(ctx, {
        type: 'line',
        data: {
          labels: samples.map((_, i) => i + 1),
          datasets: [{
            label: 'WPM',
            data: samples,
            borderColor: '#00ffcc',
            backgroundColor: 'rgba(0, 255, 204, 0.1)',
            tension: 0.4,
            fill: true
          }]
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          scales: {
            y: { beginAtZero: true, grid: { color: '#333' }, ticks: { color: '#fff' } },
            x: { grid: { color: '#333' }, ticks: { color: '#fff' } }
          },
          plugins: {
            legend: { labels: { color: '#fff' } }
          }
        }
      });
    }

    // Event listeners
    $id('next-test').off('click').on('click', function() {
      $('#result-modal').addClass('hidden');
      loadSentence();
    });
  }

  // Offline queue
  function queueResult(result) {
    const pending = JSON.parse(localStorage.getItem('pendingResults') || '[]');
    pending.push(result);
    localStorage.setItem('pendingResults', JSON.stringify(pending));
    console.log('Queued result for later sync', result);
  }

  async function syncOfflineResults() {
    const pending = JSON.parse(localStorage.getItem('pendingResults') || '[]');
    if (!pending.length) return;
    const remaining = [];
    for (const r of pending) {
      const res = await postResultToServer(r);
      if (!res.ok) remaining.push(r);
      else {
        // push to local history as synced
        const hist = JSON.parse(localStorage.getItem('history') || '[]');
        hist.push(r);
        localStorage.setItem('history', JSON.stringify(hist));
      }
    }
    localStorage.setItem('pendingResults', JSON.stringify(remaining));
    updateHistoryUI();
    updateLeaderboardUI();
  }

  // Update history UI (tries /api/history else localStorage)
  async function updateHistoryUI() {
    const $table = $('#history-table');
    if (!$table.length) return;
    try {
      const res = await fetch('/api/history');
      if (!res.ok) throw new Error('not ok');
      const data = await res.json();
      renderHistoryRows($table, data);
      return;
    } catch (e) {
      // fallback local
      const local = JSON.parse(localStorage.getItem('history') || '[]');
      renderHistoryRows($table, local);
    }
  }

  function renderHistoryRows($table, runs) {
    const $tbody = $table.find('tbody');
    if (!$tbody.length) return;
    $tbody.empty();
    (runs || []).slice(-30).reverse().forEach(r => {
      const date = r.date ? new Date(r.date).toLocaleString() : (r.timestamp ? new Date(r.timestamp * 1000).toLocaleString() : '—');
      const difficulty = r.difficulty || r.level || '—';
      const wpm = r.wpm || '—';
      const acc = r.accuracy !== undefined ? `${r.accuracy}%` : '—';
      const time = r.time || r.time_spent || '—';
      const status = r.status || '✅';
      const $tr = $('<tr>').html(`<td>${date}</td><td>${difficulty}</td><td>${wpm}</td><td>${acc}</td><td>${time}s</td><td>${status}</td>`);
      $tbody.append($tr);
    });
  }

  // Update leaderboard UI (tries /api/leaderboard)
  async function updateLeaderboardUI() {
    const $table = $('#leaderboard-table');
    if (!$table.length) return;
    try {
      const res = await fetch('/api/leaderboard');
      if (!res.ok) throw new Error('not ok');
      const data = await res.json();
      renderLeaderboardRows($table, data);
    } catch (e) {
      console.warn('Leaderboard fetch failed, using local history fallback', e);
      const local = JSON.parse(localStorage.getItem('history') || '[]');
      // simple summary by username
      const summary = {};
      local.forEach(r => {
        const u = r.username || 'You';
        summary[u] = summary[u] || { total: 0, count: 0, best: 0 };
        summary[u].total += r.wpm || 0;
        summary[u].count += 1;
        summary[u].best = Math.max(summary[u].best, r.wpm || 0);
      });
      const arr = Object.keys(summary).map(u => ({ username: u, avg: Math.round(summary[u].total / summary[u].count), best: summary[u].best }));
      arr.sort((a,b) => b.avg - a.avg);
      renderLeaderboardRows($table, arr);
    }
  }

  function renderLeaderboardRows($table, rows) {
    const $tbody = $table.find('tbody');
    if (!$tbody.length) return;
    $tbody.empty();
    (rows || []).forEach((r, idx) => {
      const username = r.username || r.user || r.name || '—';
      const difficulty = r.difficulty || r.level || '—';
      const wpm = r.wpm ?? r.best ?? r.avg ?? '—';
      const acc = r.accuracy !== undefined ? `${r.accuracy}%` : (r.avg ? `${r.avg}` : '—');
      const $tr = $('<tr>').html(`<td>${idx+1}</td><td>${username}</td><td>${difficulty}</td><td>${wpm}</td><td>${acc}</td>`);
      $tbody.append($tr);
    });
  }

  // Event listeners
  $loadBtn.on('click', function () {
    $loadBtn.prop('disabled', true);
    loadSentence();
  });

  $retryBtn.on('click', function () {
    resetUI();
    loadSentence();
  });

  $submitBtn.on('click', function () {
    finishTyping();
  });

  // Settings change handlers
  $testMode.on('change', function() {
    const mode = $(this).val();
    if (mode === 'time' || mode === 'quote') {
      $testLength.html('<option value="15">15</option><option value="30" selected>30</option><option value="60">60</option><option value="120">120</option>');
    } else if (mode === 'words') {
      $testLength.html('<option value="10">10</option><option value="25" selected>25</option><option value="50">50</option><option value="100">100</option>');
    } else {
      $testLength.html('<option value="30" selected>30</option>');
    }
  });

  $theme.on('change', function() {
    const theme = $(this).val();
    applyTheme(theme);
  });

  // Event listeners for new controls
  $testMode.on('change', function() {
    const mode = $(this).val();
    if (mode === 'time' || mode === 'quote') {
      $testLength.html('<option value="15">15</option><option value="30" selected>30</option><option value="60">60</option><option value="120">120</option>');
    } else if (mode === 'words') {
      $testLength.html('<option value="10">10</option><option value="25" selected>25</option><option value="50">50</option><option value="100">100</option>');
    } else {
      $testLength.html('<option value="30" selected>30</option>');
    }
  });

  $theme.on('change', function() {
    const theme = $(this).val();
    applyTheme(theme);
  });

  // start/stop auto-sync
  setInterval(syncOfflineResults, 15000);
  window.addEventListener('online', syncOfflineResults);

  // initial auto update if history/leaderboard pages are open
  $(function () {
    updateHistoryUI();
    updateLeaderboardUI();
    setInterval(() => { updateHistoryUI(); updateLeaderboardUI(); }, 10000);

    // Add keydown listener for heatmap tracking
    $(document).on('keydown', function(e) {
      if (!started || finished) return;
      const key = e.key.toLowerCase();
      if (key.length === 1 || key === ' ') { // only track printable chars and space
        keyHeatmap[key] = (keyHeatmap[key] || 0) + 1;
      }
    });

    // Handle custom word list upload
    $id('word-list-file').on('change', function(e) {
      const file = e.target.files[0];
      if (file) {
        const reader = new FileReader();
        reader.onload = function(e) {
          const text = e.target.result;
          customWordList = text.split(/\s+/).filter(word => word.length > 0);
          console.log('Loaded custom word list with', customWordList.length, 'words');
        };
        reader.readAsText(file);
      }
    });
  });

  // Reset UI
  function resetUI() {
    finished = false;
    started = false;
    $inputBox.val('').prop('disabled', true);
    $wpm.text('0');
    $rawWpm.text('0');
    $accuracy.text('0%');
    $consistency.text('0%');
    $timeLeft.text('');
    $progressBar.css('width','0%');
    clearAllIntervals();
  }

  function applyTheme(theme) {
    const themes = {
      dark: { bg: '#0e0e0e', text: '#f1f1f1', accent: '#00ffcc' },
      light: { bg: '#ffffff', text: '#000000', accent: '#00aaff' },
      matrix: { bg: '#000000', text: '#00ff00', accent: '#00ff00' },
      ocean: { bg: '#001122', text: '#00aaff', accent: '#00aaff' },
      sunset: { bg: '#2c1810', text: '#ff6b35', accent: '#ff6b35' },
      forest: { bg: '#0a1f0f', text: '#4caf50', accent: '#4caf50' },
      neon: { bg: '#0d0d0d', text: '#ff00ff', accent: '#ff00ff' }
    };
    const t = themes[theme] || themes.dark;
    $('body').css('background-color', t.bg).css('color', t.text);
    $('.btn').css('background-color', t.accent);
    $('.char.correct').css('color', t.accent);
    $('.progress-bar').css('background-color', t.accent);
  }

  // Sound effects
  function playSound(type) {
    if (!soundEnabled) return;
    try {
      const audioContext = new (window.AudioContext || window.webkitAudioContext)();
      const oscillator = audioContext.createOscillator();
      const gainNode = audioContext.createGain();

      oscillator.connect(gainNode);
      gainNode.connect(audioContext.destination);

      if (type === 'correct') {
        oscillator.frequency.setValueAtTime(800, audioContext.currentTime);
        oscillator.frequency.exponentialRampToValueAtTime(600, audioContext.currentTime + 0.1);
      } else if (type === 'error') {
        oscillator.frequency.setValueAtTime(300, audioContext.currentTime);
        oscillator.frequency.exponentialRampToValueAtTime(200, audioContext.currentTime + 0.2);
      } else if (type === 'complete') {
        oscillator.frequency.setValueAtTime(600, audioContext.currentTime);
        oscillator.frequency.exponentialRampToValueAtTime(800, audioContext.currentTime + 0.5);
      }

      gainNode.gain.setValueAtTime(0.1, audioContext.currentTime);
      gainNode.gain.exponentialRampToValueAtTime(0.01, audioContext.currentTime + 0.5);

      oscillator.start(audioContext.currentTime);
      oscillator.stop(audioContext.currentTime + 0.5);
    } catch (e) {
      // Ignore audio errors
    }
  }

  // Expose minimal API
  window.TypeForge = {
    loadSentence,
    finishTyping,
    resetUI,
    updateHistoryUI,
    updateLeaderboardUI,
    syncOfflineResults
  };

})(jQuery);
