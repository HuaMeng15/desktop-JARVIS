# JARVIS — Your Proactive Desktop AI

> Stop copy-pasting into ChatGPT. JARVIS watches your screen and helps you *before* you have to ask.

▶ Click to watch the demo

[![JARVIS Demo](https://img.youtube.com/vi/cguMHtoSZsE/maxresdefault.jpg)](https://youtu.be/cguMHtoSZsE)

---

## Why JARVIS?

Most AI assistants are reactive — you open a tab, craft a prompt, paste your context, and wait. JARVIS flips that model.

It lives on your desktop, understands what you're doing right now, and speaks up when it can help. No tab switching. No prompt engineering. No copy-paste.

| | ChatGPT / Claude.ai | Copilot / Cursor | **JARVIS** |
|---|---|---|---|
| Requires manual prompting | Yes | Partial | **No** |
| Aware of your full screen | No | Editor only | **Yes** |
| Proactively offers help | No | No | **Yes** |
| Works across all apps | No | No | **Yes** |
| Tracks context across app switches | No | No | **Yes** |

---

## Features

**One-Tap Launch**
Say "Hi" to Desktop JARVIS, right from your desktop. One click and your AI assistant is live.

**Instant Explainer**
Copy any concept with `Ctrl + C` and get a clear explanation in context — no tab switching, no rephrasing.

**Proactive Guidance**
When you get stuck, JARVIS reads the screen and gives a high-confidence next step. Cursor-aware hints adapt to where you are looking. It can analyze code, suggest fixes, and continue the conversation when you need deeper help.

**Quick Recap**
Return to an app and instantly remember what you were working on. JARVIS keeps your context so you don't have to.

**Work Summary**
Jump between apps and lose momentum? JARVIS organizes your recent activity into a clear summary so you can get back on track fast.

**Privacy Control**
Pause JARVIS anytime to prevent sensitive content from being captured. Resume with a single click when you're ready.

---

## Requirements

- macOS
- Python 3.12+
- An [OpenAI API key](https://platform.openai.com/api-keys)

---

## Setup

```bash
git clone <repo-url>
cd desktop-JARVIS

python3 -m venv venv
source venv/bin/activate

pip install -r requirements.txt
```

Set your API key:

```bash
export OPENAI_API_KEY=sk-...
```

To persist it, add the line above to your `~/.zshrc` or `~/.bash_profile`.
Optionally set `OPENAI_MODEL` to override the default model.

---

## Usage

```bash
./run.sh
```

JARVIS runs in the background and proactively surfaces help as you work.

### Controls

| Action | Shortcut | Mouse |
|--------|----------|-------|
| Immediate response | `Ctrl + F11` | Left-click pet |
| Insert Word signature | `Ctrl + F10` | Right-click pet → Insert Word Signature |
| Pause / Resume | `Ctrl + F12` | Right-click pet → Pause/Resume |
| Quit | — | Right-click pet → Quit |

### Word Signature

With a Microsoft Word document frontmost, use `Ctrl + F10` or the pet menu to insert your signature image near a configured signature label. By default JARVIS uses `test/signature.jpg`, searches for common labels such as `Signature of the Student`, moves two tab stops from the label, pastes the image, and sizes it to 1.45 inches wide.

Optional environment variables:

| Variable | Default |
|----------|---------|
| `JARVIS_SIGNATURE_PATH` | `test/signature.jpg` |
| `JARVIS_SIGNATURE_LABELS` | `Signature of the Student|Student Signature|Signature` |
| `JARVIS_SIGNATURE_TABS` | `2` |
| `JARVIS_SIGNATURE_WIDTH_IN` | `1.45` |
| `JARVIS_SIGNATURE_SAVE` | `false` |

### Overlay Buttons

| Button | Action |
|--------|--------|
| **Good** | Acknowledge and close |
| **More** | Ask for more detailed advice |
| **Chat** | Type a follow-up question |
| **Dismiss** | Close and resume monitoring |

### Conversation Context

When you copy a term and get an explanation, JARVIS maintains conversation history for follow-ups:

- **Turn 1** — JARVIS sends your screenshot + the copied text to OpenAI and displays the response.
- **More / Chat** — subsequent turns send only the conversation history (no image re-sent), so the model stays focused on the copied term rather than re-analyzing the screen.

This means you can ask "give me an example" or "explain it differently" and get a contextually aware reply, not a generic screen description. Each chat turn appends to the history, so the full thread is preserved for the duration of the overlay.

---

## Privacy

All processing happens on your machine except for screenshots sent to the OpenAI API. Screenshots are only sent when:
- Your screen is static for 5+ seconds (stuck-screen trigger)
- You switch app context and settle on a new screen (activity summary)

No data is sent to any other service.

---

## For Developers

| Script | Purpose |
|--------|---------|
| `test/test_display.py` | UI sandbox — visually test the overlay and pet window without running the full daemon |
| `test/test_hint.py` | Prompt sandbox — test hint generation from a screenshot or selected text without the full daemon |

---

## Troubleshooting

**Overlay doesn't appear** — grant Screen Recording permission in System Settings → Privacy & Security → Screen Recording.

**`list index out of range` on capture** — your display went to sleep; JARVIS auto-resumes on wake.

**API errors** — verify `OPENAI_API_KEY` is set and valid.
