"""Insert a configured signature image into the active Microsoft Word document."""

from __future__ import annotations

import os
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DEFAULT_SIGNATURE = ROOT / "test" / "signature.jpg"
DEFAULT_LABELS = (
    "Signature of the Student",
    "Student Signature",
    "Signature",
)
DEFAULT_WORD_APP = os.getenv("JARVIS_WORD_APP", "Microsoft Word")
SUPPORTED_IMAGE_SUFFIXES = {".jpg", ".jpeg", ".png", ".tif", ".tiff", ".bmp", ".gif", ".webp"}


class WordSignatureError(RuntimeError):
    """Raised when Jarvis cannot insert the signature into Word."""


@dataclass(frozen=True)
class WordSignatureConfig:
    signature_path: Path = DEFAULT_SIGNATURE
    labels: tuple[str, ...] = DEFAULT_LABELS
    tabs_after_label: int = 2
    width_inches: float = 1.45
    save_after: bool = False
    word_app: str = DEFAULT_WORD_APP
    timeout_seconds: int = 60
    paste_wait_seconds: float = 0.3
    require_word_active: bool = True

    @classmethod
    def from_env(cls) -> "WordSignatureConfig":
        signature = Path(os.getenv("JARVIS_SIGNATURE_PATH", str(DEFAULT_SIGNATURE))).expanduser()
        labels = _parse_labels(os.getenv("JARVIS_SIGNATURE_LABELS"))
        tabs = _env_int("JARVIS_SIGNATURE_TABS", 2)
        width = _env_float("JARVIS_SIGNATURE_WIDTH_IN", 1.45)
        save = _env_bool("JARVIS_SIGNATURE_SAVE", False)
        require_active = _env_bool("JARVIS_SIGNATURE_REQUIRE_WORD_ACTIVE", True)
        word_app = os.getenv("JARVIS_WORD_APP", DEFAULT_WORD_APP)
        return cls(
            signature_path=signature,
            labels=labels,
            tabs_after_label=tabs,
            width_inches=width,
            save_after=save,
            word_app=word_app,
            require_word_active=require_active,
        )

    def validate(self) -> None:
        if not self.labels:
            raise WordSignatureError("No signature labels configured.")
        if self.tabs_after_label < 0:
            raise WordSignatureError("Signature tab count cannot be negative.")
        if self.width_inches <= 0:
            raise WordSignatureError("Signature width must be greater than zero.")
        if self.timeout_seconds <= 0:
            raise WordSignatureError("Word automation timeout must be greater than zero.")


@dataclass(frozen=True)
class WordSignatureResult:
    label: str
    signature_path: Path
    width_inches: float
    saved: bool
    elapsed_ms: float

    @property
    def message(self) -> str:
        saved = " and saved" if self.saved else ""
        return f"Signature inserted near '{self.label}'{saved}."


def paste_signature_into_active_word(config: WordSignatureConfig | None = None) -> WordSignatureResult:
    """Paste the configured signature image into the active Word document."""
    config = config or WordSignatureConfig.from_env()
    config.validate()
    signature_path = config.signature_path.expanduser().resolve()
    if not signature_path.exists():
        raise WordSignatureError(f"Signature image not found: {signature_path}")
    if signature_path.suffix.lower() not in SUPPORTED_IMAGE_SUFFIXES:
        raise WordSignatureError(f"Unsupported signature image type: {signature_path.suffix}")

    script = build_word_signature_applescript(config, signature_path=signature_path)
    start = time.monotonic()
    output = _run_osascript(script, timeout=config.timeout_seconds + 5)

    elapsed_ms = (time.monotonic() - start) * 1000
    label = _last_output_line(output) or config.labels[0]
    return WordSignatureResult(
        label=label,
        signature_path=signature_path,
        width_inches=config.width_inches,
        saved=config.save_after,
        elapsed_ms=elapsed_ms,
    )


def build_word_signature_applescript(
    config: WordSignatureConfig,
    signature_path: Path | None = None,
) -> str:
    """Build the Word automation script for the given config."""
    tab_lines = "\n".join("        key code 48" for _ in range(config.tabs_after_label))
    tab_block = f"""
    tell application "System Events"
{tab_lines}
    end tell
""" if tab_lines else ""
    save_command = "\n        save active document" if config.save_after else ""
    width_points = config.width_inches * 72
    active_check = _build_word_active_check(config.word_app) if config.require_word_active else ""
    find_blocks = _build_find_blocks(config.labels)
    signature_path = signature_path or config.signature_path.expanduser().resolve()
    clipboard_line = _build_clipboard_line(signature_path)

    return f'''
with timeout of {int(config.timeout_seconds)} seconds
{active_check}
    tell application {_applescript_string(config.word_app)}
        activate
        if not (exists active document) then error "No active Word document."

        set foundLabel to missing value
{find_blocks}
        if foundLabel is missing value then error "Could not find any configured signature label."

        set insertionPoint to selection end of selection
        set selection start of selection to insertionPoint
        set selection end of selection to insertionPoint
    end tell

    {clipboard_line}

{tab_block}
    tell application {_applescript_string(config.word_app)}
        set pastePoint to selection start of selection
        set shapeCountBefore to count of inline shapes of active document
    end tell

    tell application "System Events"
        keystroke "v" using command down
    end tell

    delay {config.paste_wait_seconds:.2f}

    tell application {_applescript_string(config.word_app)}
        set pastedShape to missing value
        repeat with i from 1 to 30
            set shapeCountAfter to count of inline shapes of active document
            if shapeCountAfter > shapeCountBefore then
                set pastedShape to inline shape shapeCountAfter of active document
                exit repeat
            end if
            delay 0.1
        end repeat

        if pastedShape is not missing value then
            set bestStart to 999999999
            repeat with shapeIndex from 1 to shapeCountAfter
                set candidateShape to inline shape shapeIndex of active document
                set candidateStart to start of content of text object of candidateShape
                if candidateStart is greater than or equal to pastePoint and candidateStart is less than bestStart then
                    set pastedShape to candidateShape
                    set bestStart to candidateStart
                end if
            end repeat
            set lock aspect ratio of pastedShape to true
            set width of pastedShape to {width_points:.2f}
        end if
{save_command}
        activate
        return foundLabel
    end tell
end timeout
'''.strip()


def _build_find_blocks(labels: tuple[str, ...]) -> str:
    blocks = []
    for label in labels:
        quoted = _applescript_string(label)
        blocks.append(f'''        if foundLabel is missing value then
            set selection start of selection to 0
            set selection end of selection to 0
            set finder to find object of selection
            set forward of finder to true
            set wrap of finder to find continue
            set foundIt to execute find finder find text {quoted} match forward true wrap find find continue
            if foundIt is not false then set foundLabel to {quoted}
        end if''')
    return "\n".join(blocks)


def _build_clipboard_line(signature_path: Path) -> str:
    as_type = _clipboard_picture_type(signature_path)
    return f"set the clipboard to (read (POSIX file {_applescript_string(signature_path)}) as {as_type})"


def _clipboard_picture_type(signature_path: Path) -> str:
    suffix = signature_path.suffix.lower()
    if suffix in {".jpg", ".jpeg"}:
        return "JPEG picture"
    if suffix == ".png":
        return "«class PNGf»"
    if suffix in {".tif", ".tiff"}:
        return "TIFF picture"
    return "picture"


def _run_osascript(script: str, timeout: int) -> str:
    try:
        proc = subprocess.run(
            ["osascript", "-e", script],
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as exc:
        raise WordSignatureError("Timed out while controlling Microsoft Word.") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or str(exc)).strip()
        raise WordSignatureError(_clean_osascript_error(detail)) from exc
    return proc.stdout.strip()


def _build_word_active_check(word_app: str) -> str:
    return f'''
    tell application "System Events"
        set frontApp to name of first process whose frontmost is true
    end tell
    if frontApp is not {_applescript_string(word_app)} then ¬
        error "Microsoft Word must be the frontmost app before inserting a signature."
'''.rstrip()


def _applescript_string(value: str | Path) -> str:
    escaped = str(value).replace("\\", "\\\\").replace('"', '\\"')
    return f'"{escaped}"'


def _parse_labels(value: str | None) -> tuple[str, ...]:
    if not value:
        return DEFAULT_LABELS
    labels = tuple(label.strip() for label in value.split("|") if label.strip())
    return labels or DEFAULT_LABELS


def _env_bool(name: str, default: bool) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError as exc:
        raise WordSignatureError(f"{name} must be an integer.") from exc


def _env_float(name: str, default: float) -> float:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return float(value)
    except ValueError as exc:
        raise WordSignatureError(f"{name} must be a number.") from exc


def _last_output_line(output: str) -> str:
    lines = [line.strip() for line in output.splitlines() if line.strip()]
    return lines[-1] if lines else ""


def _clean_osascript_error(detail: str) -> str:
    if not detail:
        return "Microsoft Word automation failed."
    marker = "execution error:"
    if marker in detail:
        detail = detail.split(marker, 1)[1].strip()
    return detail
