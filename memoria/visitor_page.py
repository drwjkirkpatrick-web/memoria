"""memoria.visitor_page — the page a visitor lands on.

A single self-contained HTML file: ask a question and hear the person answer
in their voice, browse the timeline, see letters as sealed or open. Calm,
organic, quiet. The QR code on a physical marker points here.

The page is generated (not hand-edited) so the API contract is baked in.
"""
from __future__ import annotations
from pathlib import Path

PAGE_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>memoria</title>
<style>
  :root {
    --ink: #2c2a26; --paper: #f6f3ec; --moss: #5a6b52; --stone: #8a8578;
    --line: #e2ddd0; --sealed: #b8b2a2;
  }
  * { box-sizing: border-box; margin: 0; }
  body {
    font-family: Georgia, 'Times New Roman', serif;
    background: var(--paper); color: var(--ink);
    max-width: 720px; margin: 0 auto; padding: 2rem 1.25rem 4rem;
    line-height: 1.65;
  }
  header { text-align: center; padding: 1.5rem 0 2rem; }
  h1 { font-weight: normal; font-size: 2rem; letter-spacing: 0.02em; }
  .dates { color: var(--stone); font-style: italic; margin-top: 0.3rem; }
  .rule { border: none; border-top: 1px solid var(--line); margin: 1.5rem 0; }
  section { margin: 2.5rem 0; }
  h2 { font-size: 1.1rem; color: var(--moss); letter-spacing: 0.08em;
       text-transform: uppercase; margin-bottom: 1rem; }
  /* ask */
  .ask { display: flex; gap: 0.5rem; }
  .ask input {
    flex: 1; font: inherit; padding: 0.6rem 0.8rem; border: 1px solid var(--line);
    border-radius: 2px; background: #fffdf8; color: var(--ink);
  }
  .ask button {
    font: inherit; padding: 0.6rem 1.2rem; border: 1px solid var(--moss);
    background: var(--moss); color: #fff; border-radius: 2px; cursor: pointer;
  }
  .ask button:hover { background: #4c5a45; }
  .answer {
    margin-top: 1.2rem; padding: 1.1rem 1.2rem; background: #fffdf8;
    border-left: 3px solid var(--moss); display: none;
  }
  .answer .words { font-size: 1.05rem; }
  .answer .cites { margin-top: 0.9rem; font-size: 0.8rem; color: var(--stone); }
  .answer .cites span { display: block; }
  .refused { color: var(--stone); font-style: italic; }
  .play {
    margin-top: 0.9rem; display: none; cursor: pointer; color: var(--moss);
    background: none; border: none; font: inherit; font-size: 0.9rem;
    text-decoration: underline;
  }
  /* timeline */
  .chapter { margin-bottom: 1.5rem; }
  .chapter h3 { font-size: 1rem; color: var(--ink); margin-bottom: 0.5rem; }
  .entry { padding: 0.6rem 0 0.6rem; border-bottom: 1px dotted var(--line); }
  .entry .q { color: var(--stone); font-size: 0.85rem; }
  .entry .a { margin-top: 0.2rem; }
  /* letters */
  .letter {
    padding: 0.9rem 1rem; margin-bottom: 0.7rem; background: #fffdf8;
    border: 1px solid var(--line); border-radius: 2px;
  }
  .letter.sealed { color: var(--sealed); border-style: dashed; }
  .letter .to { font-size: 0.85rem; color: var(--stone); }
  .letter .body { margin-top: 0.5rem; }
  footer { margin-top: 4rem; text-align: center; color: var(--stone);
           font-size: 0.8rem; }
  .err { color: #8b3a3a; font-size: 0.9rem; margin-top: 0.6rem; display: none; }
</style>
</head>
<body>
<header>
  <h1 id="name">…</h1>
  <div class="dates" id="years"></div>
</header>

<section id="ask-section">
  <h2>Ask</h2>
  <div class="ask">
    <input id="question" placeholder="Ask a question…" aria-label="question">
    <button id="ask-btn">Ask</button>
  </div>
  <div class="err" id="ask-err"></div>
  <div class="answer" id="answer-box">
    <div class="words" id="answer-text"></div>
    <button class="play" id="play-btn">▸ hear it spoken</button>
    <div class="cites" id="cites"></div>
  </div>
</section>

<section id="life-section">
  <h2>The life</h2>
  <div id="timeline"></div>
</section>

<section id="letters-section">
  <h2>Letters</h2>
  <div id="letters"></div>
</section>

<footer>kept by memoria — a record given in love, not invented</footer>

<script>
const API = new URLSearchParams(location.search).get("api") || "__API_BASE__";
const PERSON = new URLSearchParams(location.search).get("person") || "__PERSON__";
const ROLE = new URLSearchParams(location.search).get("role") || "public";
const $ = (id) => document.getElementById(id);

async function api(path, opts) {
  const r = await fetch(API + path, opts);
  if (!r.ok) throw new Error("API " + r.status);
  return r.json();
}

async function loadHeader() {
  const people = await api("/people");
  const person = people.find((p) => p.id === PERSON) || people[0];
  if (!person) return;
  $("name").textContent = person.name;
  if (person.birth_year) $("years").textContent = "b. " + person.birth_year;
}

async function askQuestion() {
  const q = $("question").value.trim();
  if (!q) return;
  $("ask-err").style.display = "none";
  $("play-btn").style.display = "none";
  $("answer-box").style.display = "block";
  $("answer-text").textContent = "…";
  $("cites").innerHTML = "";
  try {
    const body = { person_id: PERSON, question: q, role: ROLE };
    const j = await api("/ask", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(body),
    });
    const box = $("answer-text");
    if (j.refused) {
      box.innerHTML = '<span class="refused">' + j.answer + "</span>";
    } else {
      box.textContent = j.answer;
      $("play-btn").style.display = "inline";
      $("play-btn").onclick = () => speak(q, j.answer);
      const cites = $("cites");
      (j.citations || []).forEach((c) => {
        const s = document.createElement("span");
        s.textContent = "— from what they said: " + "\u201c" + c.quote + "\u201d";
        cites.appendChild(s);
      });
    }
  } catch (e) {
    $("answer-box").style.display = "none";
    $("ask-err").textContent = "The memorial could not be reached.";
    $("ask-err").style.display = "block";
  }
}

async function speak(question, answer) {
  try {
    const r = await fetch(API + "/voice", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ person_id: PERSON, text: question, role: ROLE }),
    });
    if (!r.ok) throw new Error("voice " + r.status);
    const blob = await r.blob();
    new Audio(URL.createObjectURL(blob)).play();
  } catch (e) {
    alert("Voice is not available right now.");
  }
}

async function loadTimeline() {
  try {
    const chapters = await api("/timeline?person_id=" + PERSON + "&role=" + ROLE);
    const tl = $("timeline");
    tl.innerHTML = "";
    let n = 0;
    for (const [chapter, entries] of Object.entries(chapters)) {
      const div = document.createElement("div");
      div.className = "chapter";
      const h = document.createElement("h3");
      h.textContent = chapter.charAt(0).toUpperCase() + chapter.slice(1);
      div.appendChild(h);
      entries.forEach((e) => {
        n++;
        const en = document.createElement("div");
        en.className = "entry";
        const q = document.createElement("div");
        q.className = "q";
        q.textContent = e.question;
        const a = document.createElement("div");
        a.className = "a";
        a.textContent = e.text;
        en.appendChild(q); en.appendChild(a);
        div.appendChild(en);
      });
      tl.appendChild(div);
    }
    if (!n) $("life-section").style.display = "none";
  } catch (e) { /* timeline absent: hide quietly */ $("life-section").style.display = "none"; }
}

async function loadLetters() {
  try {
    const letters = await api("/letters?person_id=" + PERSON + "&role=" + ROLE);
    const box = $("letters");
    box.innerHTML = "";
    if (!letters.length) { $("letters-section").style.display = "none"; return; }
    letters.forEach((l) => {
      const d = document.createElement("div");
      d.className = "letter" + (l.sealed ? " sealed" : "");
      const to = document.createElement("div");
      to.className = "to";
      to.textContent = "to " + l.recipient + (l.occasion ? " — " + l.occasion : "");
      d.appendChild(to);
      if (!l.sealed && l.body) {
        const b = document.createElement("div");
        b.className = "body";
        b.textContent = l.body;
        d.appendChild(b);
      } else {
        const b = document.createElement("div");
        b.className = "body";
        b.textContent = "sealed until its time";
        d.appendChild(b);
      }
      box.appendChild(d);
    });
  } catch (e) { $("letters-section").style.display = "none"; }
}

$("ask-btn").onclick = askQuestion;
$("question").addEventListener("keydown", (e) => { if (e.key === "Enter") askQuestion(); });
loadHeader(); loadTimeline(); loadLetters();
</script>
</body>
</html>
"""


def render_page(api_base: str = "http://127.0.0.1:8093", person_id: str = "") -> str:
    """The visitor HTML, pointed at a memorial server and person."""
    return (PAGE_TEMPLATE
            .replace("__API_BASE__", api_base)
            .replace("__PERSON__", person_id))


def write_page(out_path: str, api_base: str = "http://127.0.0.1:8093",
               person_id: str = "") -> Path:
    out = Path(out_path)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(render_page(api_base, person_id), encoding="utf-8")
    return out


def qr_payload(api_base: str, person_id: str, role: str = "public") -> str:
    """The URL a physical marker's QR code encodes."""
    return f"{api_base}/visit.html?person={person_id}&role={role}"
