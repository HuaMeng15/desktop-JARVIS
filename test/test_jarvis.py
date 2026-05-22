"""Unit tests for JARVIS — pure function tests, no real LLM calls, no main loop."""

import base64
import csv
import io
import json
import sys
import tempfile
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from PIL import Image

sys.path.insert(0, str(Path(__file__).parent.parent))


# ── helpers ──────────────────────────────────────────────────────────────────

def _png_bytes(color=(100, 149, 237), size=(64, 64)) -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", size, color).save(buf, format="PNG")
    return buf.getvalue()

def _b64(color=(100, 149, 237)) -> str:
    return base64.standard_b64encode(_png_bytes(color)).decode()


# ── capture ───────────────────────────────────────────────────────────────────

class TestCapture:
    def test_returns_six_tuple(self):
        from capture import capture_screen
        b64, raw, cx, cy, w, h = capture_screen(monitor_index=1)
        assert isinstance(b64, str) and len(b64) > 0
        assert isinstance(raw, bytes)
        assert isinstance(cx, int) and isinstance(cy, int)
        assert w > 0 and h > 0

    def test_b64_is_valid_png(self):
        from capture import capture_screen
        b64, *_ = capture_screen(monitor_index=1)
        img = Image.open(io.BytesIO(base64.b64decode(b64)))
        assert img.format == "PNG"

    def test_cursor_within_screen(self):
        from capture import capture_screen
        _, _, cx, cy, w, h = capture_screen(monitor_index=1)
        assert 0 <= cx <= w
        assert 0 <= cy <= h

    def test_get_clipboard_change_count_is_int(self):
        from capture import get_clipboard_change_count
        assert isinstance(get_clipboard_change_count(), int)

    def test_get_clipboard_text_is_str_or_none(self):
        from capture import get_clipboard_text
        result = get_clipboard_text()
        assert result is None or isinstance(result, str)

    def test_clipboard_count_increments_on_write(self):
        from AppKit import NSPasteboard, NSStringPboardType
        pb = NSPasteboard.generalPasteboard()
        before = pb.changeCount()
        pb.clearContents()
        pb.setString_forType_("jarvis_test", NSStringPboardType)
        assert pb.changeCount() > before


# ── monitor (FrameMonitor) ────────────────────────────────────────────────────

class TestFrameMonitor:
    @pytest.fixture
    def fm(self, tmp_path, monkeypatch):
        import monitor
        monkeypatch.setattr(monitor, "TMP_DIR", tmp_path)
        monkeypatch.setattr(monitor, "SCREENSHOTS_DIR", tmp_path / "screenshots")
        monkeypatch.setattr(monitor, "RECORD_CSV", tmp_path / "record.csv")
        return monitor.FrameMonitor()

    def test_identical_frames_score_zero_psnr_inf(self, fm):
        img = Image.new("RGB", (64, 64), (128, 128, 128))
        fm.update(img, "a.png")
        score, psnr = fm.update(img, "b.png")
        assert score == 0
        assert psnr == float("inf")

    def test_different_frames_nonzero_score(self, fm):
        # Use images with actual detail so dHash differs
        import random
        random.seed(42)
        pixels_a = bytes(random.randint(0, 255) for _ in range(64 * 64 * 3))
        pixels_b = bytes(random.randint(0, 255) for _ in range(64 * 64 * 3))
        img_a = Image.frombytes("RGB", (64, 64), pixels_a)
        img_b = Image.frombytes("RGB", (64, 64), pixels_b)
        fm.update(img_a, "a.png")
        score, psnr = fm.update(img_b, "b.png")
        assert score > 0
        assert psnr < 100

    def test_first_frame_returns_zero(self, fm):
        score, psnr = fm.update(Image.new("RGB", (64, 64)), "a.png")
        assert score == 0
        assert psnr == float("inf")

    def test_reset_clears_previous(self, fm):
        img = Image.new("RGB", (64, 64), (50, 50, 50))
        fm.update(img, "a.png")
        fm.reset()
        score, psnr = fm.update(img, "b.png")
        assert score == 0 and psnr == float("inf")

    def test_rolling_window_enforced(self, tmp_path, monkeypatch):
        import monitor
        monkeypatch.setattr(monitor, "TMP_DIR", tmp_path)
        monkeypatch.setattr(monitor, "SCREENSHOTS_DIR", tmp_path / "screenshots")
        monkeypatch.setattr(monitor, "RECORD_CSV", tmp_path / "record.csv")
        monkeypatch.setattr(monitor, "MAX_FRAMES", 3)
        fm = monitor.FrameMonitor()
        for i in range(5):
            fm.save_frame(_png_bytes(color=(i*40, i*40, i*40)), f"f{i}.png")
        assert len(fm._frame_files) == 3

    def test_psnr_identical_is_inf(self, fm):
        from monitor import _psnr
        img = Image.new("RGB", (32, 32), (100, 100, 100))
        assert _psnr(img, img) == float("inf")

    def test_psnr_different_is_finite(self, fm):
        from monitor import _psnr
        import random
        random.seed(1)
        px_a = bytes(random.randint(0, 255) for _ in range(32 * 32 * 3))
        px_b = bytes(random.randint(0, 255) for _ in range(32 * 32 * 3))
        a = Image.frombytes("RGB", (32, 32), px_a)
        b = Image.frombytes("RGB", (32, 32), px_b)
        assert 0 < _psnr(a, b) < 100


# ── stats ─────────────────────────────────────────────────────────────────────

class TestStats:
    @pytest.fixture
    def s(self, tmp_path, monkeypatch):
        import stats
        monkeypatch.setattr(stats, "STATS_DIR", tmp_path)
        monkeypatch.setattr(stats, "SCREENSHOTS_DIR", tmp_path / "screenshots")
        monkeypatch.setattr(stats, "RESPONSES_DIR", tmp_path / "responses")
        monkeypatch.setattr(stats, "LLM_LOG_FILE", tmp_path / "llm_calls.csv")
        monkeypatch.setattr(stats, "ACTIVITY_LOG_FILE", tmp_path / "activity_calls.csv")
        return stats

    def _rows(self, s):
        return list(csv.DictReader(open(s.LLM_LOG_FILE)))

    def test_log_creates_csv_row(self, s):
        s.log_llm_call("stuck", 100.0, 200.0, 10, 5, response_text="hint")
        rows = self._rows(s)
        assert len(rows) == 1
        assert rows[0]["trigger"] == "stuck"

    def test_all_fields_present(self, s):
        s.log_llm_call("stuck", 100.0, 200.0, 10, 5, response_text="x")
        row = self._rows(s)[0]
        for field in s._LLM_FIELDS:
            assert field in row

    def test_cursor_stored(self, s):
        s.log_llm_call("stuck", 100.0, 200.0, 10, 5, response_text="x",
                       cursor_x=320, cursor_y=240)
        row = self._rows(s)[0]
        assert row["cursor_x"] == "320"
        assert row["cursor_y"] == "240"

    def test_screenshot_saved_with_crosshair(self, s):
        s.log_llm_call("stuck", 100.0, 200.0, 10, 5, response_text="x",
                       image_bytes=_png_bytes(), cursor_x=32, cursor_y=32)
        pngs = list((s.SCREENSHOTS_DIR).glob("*.png"))
        assert len(pngs) == 1
        assert Image.open(pngs[0]).size == (64, 64)

    def test_cost_calculation(self, s):
        # 1M input @ $15 + 1M output @ $75 = $90
        s.log_llm_call("test", 0, 0, 1_000_000, 1_000_000, response_text="x")
        assert abs(float(self._rows(s)[0]["cost_usd"]) - 90.0) < 0.01

    def test_selected_text_truncated_to_200(self, s):
        s.log_llm_call("clipboard", 0, 0, 10, 5, response_text="x",
                       selected_text="a" * 500)
        assert len(self._rows(s)[0]["selected_text"]) == 200

    def test_update_reaction(self, s):
        key = s.log_llm_call("stuck", 0, 0, 10, 5, response_text="x")
        s.update_llm_reaction(key, "good")
        assert self._rows(s)[0]["reaction"] == "good"

    def test_update_reaction_noop_for_unknown_key(self, s):
        s.log_llm_call("stuck", 0, 0, 10, 5, response_text="x")
        s.update_llm_reaction("nonexistent", "good")  # should not raise
        assert self._rows(s)[0]["reaction"] == ""

    def test_response_file_saved(self, s):
        s.log_llm_call("stuck", 0, 0, 10, 5, response_text="my hint text")
        row = self._rows(s)[0]
        content = (s.RESPONSES_DIR / row["response_file"]).read_text()
        assert content == "my hint text"

    def test_migrate_csv_adds_missing_columns(self, s):
        # Write a CSV with fewer columns than current schema
        s.LLM_LOG_FILE.parent.mkdir(parents=True, exist_ok=True)
        with open(s.LLM_LOG_FILE, "w", newline="") as f:
            w = csv.DictWriter(f, fieldnames=["timestamp", "trigger"])
            w.writeheader()
            w.writerow({"timestamp": "2026-01-01", "trigger": "stuck"})
        s._migrate_csv(s.LLM_LOG_FILE, s._LLM_FIELDS)
        rows = self._rows(s)
        assert rows[0]["trigger"] == "stuck"
        for field in s._LLM_FIELDS:
            assert field in rows[0]


# ── response (mocked API) ─────────────────────────────────────────────────────

def _mock_msg(text: str, in_tok=10, out_tok=5):
    msg = MagicMock()
    msg.content = [MagicMock(text=text)]
    msg.usage.input_tokens = in_tok
    msg.usage.output_tokens = out_tok
    return msg


class TestResponse:
    def test_get_selection_hint_parses_json(self):
        from response import get_selection_hint
        payload = json.dumps({"needs_hint": True, "hint": "HPCC is a cluster",
                              "confidence": "high", "reason": "concept", "category": "other"})
        with patch("response._client") as c:
            c.messages.create.return_value = _mock_msg(payload)
            result = get_selection_hint("HPCC")
        assert result.needs_hint is True
        assert result.hint == "HPCC is a cluster"
        assert result.confidence == "high"
        assert result.input_tokens == 10

    def test_get_selection_hint_sends_text_in_message(self):
        from response import get_selection_hint
        payload = json.dumps({"needs_hint": True, "hint": "x",
                              "confidence": "high", "reason": "concept", "category": "other"})
        with patch("response._client") as c:
            c.messages.create.return_value = _mock_msg(payload)
            get_selection_hint("gradient descent")
        call_args = c.messages.create.call_args
        messages = call_args.kwargs.get("messages", call_args.args[0] if call_args.args else [])
        assert "gradient descent" in str(messages)

    def test_get_selection_hint_strips_markdown_fences(self):
        from response import get_selection_hint
        payload = '```json\n{"needs_hint":true,"hint":"x","confidence":"high","reason":"r","category":"other"}\n```'
        with patch("response._client") as c:
            c.messages.create.return_value = _mock_msg(payload)
            result = get_selection_hint("test")
        assert result.hint == "x"

    def test_get_hint_sends_image_and_cursor(self):
        from response import get_hint
        payload = json.dumps({"needs_hint": True, "hint": "fix it",
                              "confidence": "high", "reason": "r", "category": "coding"})
        with patch("response._client") as c:
            c.messages.create.return_value = _mock_msg(payload)
            get_hint(_b64(), 100, 200, 1920, 1080, 5)
        call_args = c.messages.create.call_args
        messages = call_args.kwargs.get("messages", [])
        content_str = str(messages)
        assert "100" in content_str   # cursor x
        assert "200" in content_str   # cursor y
        # image content block present
        assert "base64" in content_str

    def test_get_hint_parses_needs_hint_false(self):
        from response import get_hint
        payload = json.dumps({"needs_hint": False, "hint": "",
                              "confidence": "low", "reason": "idle", "category": "other"})
        with patch("response._client") as c:
            c.messages.create.return_value = _mock_msg(payload)
            result = get_hint(_b64(), 0, 0, 1920, 1080, 5)
        assert result.needs_hint is False
        assert result.confidence == "low"

    def test_get_hint_handles_malformed_json(self):
        from response import get_hint
        with patch("response._client") as c:
            c.messages.create.return_value = _mock_msg("not json at all")
            result = get_hint(_b64(), 0, 0, 1920, 1080, 5)
        # Should not raise; returns defaults
        assert result.needs_hint is False
        assert result.hint == ""

    def test_hint_result_fields(self):
        from response import HintResult
        h = HintResult(needs_hint=True, hint="do X", confidence="high",
                       reason="r", category="coding",
                       input_tokens=100, output_tokens=50, total_ms=200.0)
        assert h.needs_hint is True
        assert h.total_ms == 200.0


# ── clipboard trigger logic ───────────────────────────────────────────────────

class TestClipboardTriggerLogic:
    """Test the dedup logic that prevents re-triggering on the same clipboard text."""

    def _simulate(self, events):
        """events: list of (change_count, text). Returns list of triggered texts."""
        last_count = 0
        last_triggered = None
        triggered = []
        for count, text in events:
            if count != last_count:
                last_count = count
                if text and text != last_triggered:
                    last_triggered = text
                    triggered.append(text)
        return triggered

    def test_new_text_triggers(self):
        assert self._simulate([(1, "hello")]) == ["hello"]

    def test_same_count_no_trigger(self):
        assert self._simulate([(1, "hello"), (1, "hello")]) == ["hello"]

    def test_same_text_different_count_no_retrigger(self):
        assert self._simulate([(1, "hello"), (2, "hello")]) == ["hello"]

    def test_different_text_triggers_again(self):
        assert self._simulate([(1, "hello"), (2, "world")]) == ["hello", "world"]

    def test_empty_text_no_trigger(self):
        assert self._simulate([(1, ""), (2, None)]) == []

    def test_sequence(self):
        events = [(0, None), (1, "a"), (1, "a"), (2, "a"), (3, "b"), (4, "b"), (5, "a")]
        assert self._simulate(events) == ["a", "b", "a"]


# ── context switch logic ──────────────────────────────────────────────────────

class TestContextSwitchLogic:
    """Test the dHash threshold and post-switch settling logic."""

    THRESHOLD = 20

    def _run(self, scores):
        """Simulate the context-switch state machine. Returns list of switch events."""
        in_post = False
        post_scores = []
        events = []
        for score in scores:
            if score > self.THRESHOLD and not in_post:
                in_post = True
                post_scores.clear()
                events.append("switch_detected")
            elif in_post:
                post_scores.append(score)
                if len(post_scores) >= 2:
                    in_post = False
                    settled = all(s < 10 for s in post_scores)
                    events.append("settled" if settled else "wandering")
                    post_scores.clear()
        return events

    def test_no_switch_below_threshold(self):
        assert self._run([0, 5, 10, 15, 20]) == []

    def test_spike_triggers_switch(self):
        events = self._run([0, 25, 0, 0])
        assert "switch_detected" in events

    def test_settled_after_low_scores(self):
        events = self._run([0, 25, 3, 2])
        assert events == ["switch_detected", "settled"]

    def test_wandering_after_high_scores(self):
        events = self._run([0, 25, 15, 18])
        assert events == ["switch_detected", "wandering"]

    def test_multiple_switches(self):
        events = self._run([0, 25, 2, 2, 0, 30, 3, 3])
        assert events.count("switch_detected") == 2
        assert events.count("settled") == 2
