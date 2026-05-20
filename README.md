# JARVIS — Desktop AI Assistant

JARVIS is a macOS background daemon that watches your screen and proactively offers AI-powered advice when you get stuck, tracks your activity across apps, and gives you context-aware recaps of your recent work.

## Features

- **Stuck-screen detection** — if your screen stays static for 5 seconds, JARVIS sends a screenshot to Claude and streams advice directly to an overlay window
- **Activity tracking** — silently records what you're doing in each app (VS Code, browser, WeChat, etc.) by detecting context switches
- **Previous work recall** — when you return to an app you were in before, JARVIS reminds you what you were working on
- **Wandering detection** — if you keep switching apps rapidly, JARVIS shows a recap of everything you've done in the last 2 hours
- **Interactive overlay** — More, Chat, Good, and Dismiss buttons; Chat lets you ask follow-up questions inline
- **Stats logging** — every LLM call logs TTFT, total time, token counts, and cost to CSV

## Requirements

- macOS (uses `mss` for screen capture and `pyobjc` for lock detection)
- Python 3.12+
- An [Anthropic API key](https://console.anthropic.com/)

## Setup

```bash
# Clone the repo
git clone <repo-url>
cd desktop-JARVIS

# Create and activate a virtual environment
python3 -m venv venv
source venv/bin/activate

# Install dependencies
pip install -r requirements.txt
```

Set your API key:

```bash
export ANTHROPIC_API_KEY=sk-ant-...
```

To make it permanent, add the line above to your `~/.zshrc` or `~/.bash_profile`.

## Usage

```bash
source venv/bin/activate
python main.py
```

Leave it running in the background. JARVIS will:
1. Capture your screen at 1 fps
2. Show an overlay with advice if you're idle for 5 seconds
3. Silently track app switches and build an activity history

Press `Ctrl+C` to stop.

## Overlay Buttons

| Button | Action |
|--------|--------|
| **Good** | Acknowledge and close |
| **More** | Ask Claude for more detailed advice |
| **Chat** | Type a follow-up question |
| **Dismiss** | Close and resume monitoring |

## File Structure

```
desktop-JARVIS/
├── main.py          # Daemon loop and state machine
├── capture.py       # Screen capture (mss + Pillow)
├── monitor.py       # dHash + PSNR frame comparison, rolling screenshot buffer
├── activity.py      # Activity tracker — app/summary records, dHash matching
├── display.py       # Tkinter overlay window
├── response.py      # Anthropic API calls (streaming + blocking)
├── stats.py         # CSV logging and cost tracking
├── test/
│   ├── test_capture.py   # Capture 1fps to ./stats/screenshots
│   ├── test_compare.py   # Compare all screenshots, output compare.csv
│   └── test_display.py   # Test the overlay UI with fake streaming
├── tmp/
│   ├── screenshots/      # Rolling 300-frame capture buffer
│   └── record.csv        # Per-frame dHash + PSNR log
└── stats/
    ├── llm_calls.csv      # Stuck/More/Chat LLM call metrics
    ├── activity_calls.csv # Silent background activity query metrics
    ├── screenshots/       # Screenshots sent to LLM
    ├── responses/         # Full LLM response text
    └── tasks/
        ├── tasks.json         # Activity records (app + summary + dHash)
        └── screenshots/       # One screenshot per unique activity context
```

## Privacy

All processing happens on your machine except for the screenshots sent to the Anthropic API. Screenshots are only sent when:
- Your screen is static for 5+ seconds (stuck-screen trigger)
- You switch app context and settle on a new screen (activity summary, silent)

No data is sent to any other service.

## Troubleshooting

**Overlay doesn't appear** — make sure your terminal has Screen Recording permission in System Settings → Privacy & Security → Screen Recording.

**`list index out of range` on capture** — your display went to sleep. JARVIS will auto-resume when it wakes.

**API errors** — check that `ANTHROPIC_API_KEY` is set and valid.
