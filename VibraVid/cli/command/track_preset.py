# 06.08.26

import logging
from typing import Dict, List, Optional

from rich.console import Console
from rich.prompt import Prompt

from VibraVid.utils import config_manager
from VibraVid.utils.console.shared_styles import create_styled_table, TableStyle


console = Console()
msg = Prompt()
logger = logging.getLogger(__name__)
TABLE_STYLE = TableStyle.MODERN_ROUNDED

# Sentinel understood by StreamSelector / FilterSpec to drop a track type entirely
DROP = "false"

# Audio modes: (slug, label, description, filter spec)
AUDIO_MODES = [
    ("dub",   "Dubbed",    "Italian audio",  "ita|it"),
    ("org",   "Original",  "original audio", "eng|en|jpn|ja|best"),
    ("multi", "All audio", "every audio",    "all"),
]

# Subtitle modes: (slug suffix, label suffix, description, filter spec)
SUBTITLE_MODES = [
    ("",     "",              "no subtitles",      DROP),
    ("ita",  " + ITA subs",   "Italian subtitles", "ita|it"),
    ("eng",  " + ENG subs",   "English subtitles", "eng|en"),
    ("all",  " + all subs",   "every subtitle",    "all"),
]


def _build_presets() -> List[Dict[str, Optional[str]]]:
    """Expand the audio x subtitle matrix into the numbered preset list."""
    presets = []

    for a_slug, a_label, a_detail, a_spec in AUDIO_MODES:
        for s_slug, s_label, s_detail, s_spec in SUBTITLE_MODES:
            presets.append({
                "key": str(len(presets) + 1),
                "slug": f"{a_slug}-{s_slug}" if s_slug else a_slug,
                "name": f"{a_label}{s_label}",
                "detail": f"{a_detail}, {s_detail}",
                "audio": a_spec,
                "subtitle": s_spec,
            })

    presets.append({
        "key": str(len(presets) + 1),
        "slug": "custom",
        "name": "Custom",
        "detail": "Type audio and subtitle filters manually",
        "audio": None,
        "subtitle": None,
    })
    return presets


# Ordered list of selectable presets. "audio"/"subtitle" hold the filter spec
# passed to DOWNLOAD.select_audio / DOWNLOAD.select_subtitle.
TRACK_PRESETS: List[Dict[str, Optional[str]]] = _build_presets()

PRESET_BY_KEY = {preset["key"]: preset for preset in TRACK_PRESETS}
PRESET_BY_SLUG = {preset["slug"]: preset for preset in TRACK_PRESETS}

# Set once the prompt has run (or been suppressed) for this session
_resolved = False
_suppressed = False


def suppress() -> None:
    """Disable the interactive prompt for this session (explicit -sa/-ss or --no-track-prompt)."""
    global _suppressed
    _suppressed = True
    logger.debug("Track preset prompt suppressed for this session.")


def reset() -> None:
    """Allow the prompt to run again (used when starting a new search)."""
    global _resolved
    _resolved = False


def _current_filters() -> Dict[str, str]:
    return {
        "audio": config_manager.config.get("DOWNLOAD", "select_audio") or "",
        "subtitle": config_manager.config.get("DOWNLOAD", "select_subtitle") or "",
    }


def _describe(spec: str) -> str:
    """Human-readable rendering of a filter spec for the summary line."""
    if not spec or spec.lower() == DROP:
        return "[red]none[/red]"
    if spec.lower() == "all":
        return "[green]all[/green]"
    return f"[yellow]{spec}[/yellow]"


def _apply(audio: str, subtitle: str) -> None:
    """Write the chosen filters to the in-memory config (session only, never persisted)."""
    config_manager.config.set_key("DOWNLOAD", "select_audio", audio)
    config_manager.config.set_key("DOWNLOAD", "select_subtitle", subtitle)
    logger.info(f"Track preset applied -> audio={audio!r} subtitle={subtitle!r}")


def _render_table(current: Dict[str, str]) -> None:
    table = create_styled_table(TABLE_STYLE)
    table.add_column("Index", style="red", justify="center", no_wrap=True)
    table.add_column("Preset", style="magenta", no_wrap=True)
    table.add_column("Audio", style="green", no_wrap=True)
    table.add_column("Subtitle", style="blue", no_wrap=True)

    for preset in TRACK_PRESETS:
        if preset["audio"] is None:
            audio_cell, subtitle_cell = "—", "—"
        else:
            audio_cell = "none" if preset["audio"] == DROP else preset["audio"]
            subtitle_cell = "none" if preset["subtitle"] == DROP else preset["subtitle"]

        table.add_row(preset["key"], preset["name"], audio_cell, subtitle_cell)

    table.add_row("0", "Keep current", current["audio"] or "—", current["subtitle"] or "—")
    console.print(table)


def _ask_custom(current: Dict[str, str]) -> None:
    console.print("[dim]Language tokens separated by '|' (e.g. \"ita|eng\"), \"all\", or \"false\" for none.[/dim]")
    audio = msg.ask("[cyan]Audio filter[/cyan]", default=current["audio"] or "all")
    subtitle = msg.ask("[cyan]Subtitle filter[/cyan]", default=current["subtitle"] or DROP)
    _apply(audio.strip(), subtitle.strip())


def apply_named_preset(name: str) -> bool:
    """Apply a preset by index or name (used by --tracks). Returns True on success."""
    key = str(name).strip().lower()
    preset = PRESET_BY_KEY.get(key) or PRESET_BY_SLUG.get(key)

    if preset is None or preset["audio"] is None:
        console.print(f"[red]Unknown track preset: '{name}'.")
        logger.warning(f"User provided unknown track preset: '{name}'")
        return False

    _apply(preset["audio"], preset["subtitle"])
    suppress()
    return True


def prompt_track_preset() -> None:
    """
    Ask once per session which audio/subtitle combination to download.

    Called right after the episode selection so the choice is made in context,
    just before any stream is fetched. Silently returns when suppressed by
    command line flags or when already answered.
    """
    global _resolved

    if _resolved or _suppressed:
        return
    _resolved = True

    current = _current_filters()
    console.print("\n[cyan]Track preset:")
    _render_table(current)
    console.print()

    choice = msg.ask(
        "[cyan]Insert preset index[/cyan]",
        choices=list(PRESET_BY_KEY.keys()) + ["0"],
        default="0",
        show_choices=False,
        show_default=False,
    )

    if choice == "0":
        detail = "current configuration"
        logger.info("Track preset: keeping current configuration.")
    else:
        preset = PRESET_BY_KEY[choice]
        detail = preset["detail"]
        if preset["audio"] is None:
            _ask_custom(current)
        else:
            _apply(preset["audio"], preset["subtitle"])

    final = _current_filters()
    console.print(
        f"[dim]{detail} —[/dim] audio: {_describe(final['audio'])}"
        f"  [dim]|[/dim]  subtitle: {_describe(final['subtitle'])}\n"
    )
