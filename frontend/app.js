"use strict";

const STORAGE_KEY = "blc-history";
const STATE_RESET_MS = 1400;
const ERROR_TEXT = "Sorry, something went wrong on my end. Please try again.";

const messagesEl = document.getElementById("messages");
const emptyEl = document.getElementById("empty");
const formEl = document.getElementById("form");
const inputEl = document.getElementById("input");
const sendEl = document.getElementById("send");
const inputLaurel = document.getElementById("laurel-input");

let history = loadHistory();
let busy = false;
let resetTimer = null;

function loadHistory() {
  try {
    const saved = JSON.parse(sessionStorage.getItem(STORAGE_KEY) || "[]");
    return Array.isArray(saved) ? saved : [];
  } catch (e) {
    return [];
  }
}

function saveHistory() {
  try { sessionStorage.setItem(STORAGE_KEY, JSON.stringify(history)); } catch (e) { /* ignore */ }
}

function laurelSvg() {
  const ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg");
  svg.setAttribute("class", "laurel active");
  svg.setAttribute("data-state", "idle");
  svg.setAttribute("viewBox", "0 0 64 64");
  svg.setAttribute("aria-hidden", "true");
  svg.setAttribute("focusable", "false");
  fillLaurel(svg);
  return svg;
}

// Each Laurel gets its own copy of the drawing. A <use> reference would hide the
// parts from the state CSS, so they would never animate.
function fillLaurel(svg) {
  const symbol = document.getElementById("laurel");
  Array.from(symbol.children).forEach((part) => svg.appendChild(part.cloneNode(true)));
}

// Only the Laurel by the input and the one on the newest bot message move.
function retireOldLaurels(except) {
  messagesEl.querySelectorAll(".row .laurel.active").forEach((s) => {
    if (s !== except) s.classList.remove("active");
  });
}

function addRow(kind, text) {
  emptyEl.hidden = true;
  const row = document.createElement("div");
  row.className = "row " + kind;
  const bubble = document.createElement("div");
  bubble.className = "bubble";
  bubble.textContent = text;
  let laurel = null;
  if (kind !== "user") {
    laurel = laurelSvg();
    retireOldLaurels(laurel);
    row.appendChild(laurel);
  }
  row.appendChild(bubble);
  messagesEl.appendChild(row);
  scrollDown();
  return { row, bubble, laurel };
}

function scrollDown() {
  messagesEl.scrollTop = messagesEl.scrollHeight;
}

function setState(svgs, state, thenIdle) {
  clearTimeout(resetTimer);
  svgs.filter(Boolean).forEach((s) => s.setAttribute("data-state", state));
  if (thenIdle) {
    resetTimer = setTimeout(() => svgs.filter(Boolean).forEach((s) => s.setAttribute("data-state", "idle")), STATE_RESET_MS);
  }
}

function setBusy(value) {
  busy = value;
  inputEl.disabled = value;
  sendEl.disabled = value;
}

function showDots(bubble) {
  const dots = document.createElement("span");
  dots.className = "dots";
  dots.setAttribute("aria-hidden", "true");
  for (let i = 0; i < 3; i++) dots.appendChild(document.createElement("i"));
  bubble.appendChild(dots);
}

async function ask(question) {
  if (busy) return;
  question = question.trim();
  if (!question) return;
  setBusy(true);
  addRow("user", question);
  inputEl.value = "";
  autoGrow();

  const bot = addRow("bot thinking", "");
  showDots(bot.bubble);
  const faces = [bot.laurel, inputLaurel];
  setState(faces, "thinking");

  let text = "";
  let finished = false;
  const onLine = (msg) => {
    if (msg.type === "token") {
      if (!text) {
        bot.row.classList.remove("thinking");
        bot.bubble.textContent = "";
        setState(faces, "talking");
      }
      text += msg.text;
      bot.bubble.textContent = text;
      scrollDown();
    } else if (msg.type === "done") {
      finished = true;
      bot.row.classList.remove("thinking");
      bot.bubble.textContent = msg.reply;
      history = msg.history;
      saveHistory();
      setState(faces, "happy", true);
    } else if (msg.type === "error") {
      fail(bot, faces, msg.message);
      finished = true;
    }
  };

  try {
    const res = await fetch("/api/chat", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ question, history }),
    });
    if (!res.ok || !res.body) throw new Error("bad response");
    await readLines(res.body, onLine);
    if (!finished) throw new Error("stream ended early");
  } catch (e) {
    if (!bot.row.classList.contains("error")) fail(bot, faces, ERROR_TEXT);
  } finally {
    setBusy(false);
    inputEl.focus();
    scrollDown();
  }
}

function fail(bot, faces, message) {
  bot.row.classList.remove("thinking");
  bot.row.classList.add("error");
  bot.bubble.textContent = message || ERROR_TEXT;
  setState(faces, "oops", true);
}

async function readLines(body, onLine) {
  const reader = body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";
  for (;;) {
    const { value, done } = await reader.read();
    if (done) break;
    buffer += decoder.decode(value, { stream: true });
    let idx;
    while ((idx = buffer.indexOf("\n")) >= 0) {
      const line = buffer.slice(0, idx).trim();
      buffer = buffer.slice(idx + 1);
      if (line) onLine(JSON.parse(line));
    }
  }
  buffer += decoder.decode();
  if (buffer.trim()) onLine(JSON.parse(buffer));
}

function autoGrow() {
  inputEl.style.height = "auto";
  inputEl.style.height = Math.min(inputEl.scrollHeight, 140) + "px";
}

function renderSaved() {
  history.forEach((item) => {
    if (item.role === "user") addRow("user", item.content);
    else if (item.role === "assistant") addRow("bot", item.content);
  });
}

function newChat() {
  if (busy) return;
  history = [];
  saveHistory();
  messagesEl.querySelectorAll(".row").forEach((r) => r.remove());
  emptyEl.hidden = false;
  setState([inputLaurel], "idle");
}

formEl.addEventListener("submit", (e) => {
  e.preventDefault();
  ask(inputEl.value);
});
inputEl.addEventListener("keydown", (e) => {
  if (e.key === "Enter" && !e.shiftKey && !e.isComposing) {
    e.preventDefault();
    ask(inputEl.value);
  }
});
inputEl.addEventListener("input", autoGrow);
document.querySelectorAll(".chip").forEach((chip) => {
  chip.addEventListener("click", () => ask(chip.textContent));
});
document.getElementById("new-chat").addEventListener("click", newChat);

document.querySelectorAll("svg.laurel").forEach(fillLaurel);
renderSaved();
