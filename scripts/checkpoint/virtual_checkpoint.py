import re
import subprocess
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path


DEFAULT_START_MARKER = "exec command:"
DEFAULT_STOP_MARKER = "TEST DONE!"
NEMU_MARKER_OPTIONS = (
    "--start-profiling-on-uart-marker",
    "--stop-profiling-on-uart-marker",
)

START_MATCH_RE = re.compile(r"ROI uart marker matched:\s*(.*)")
START_BASE_RE = re.compile(
    r"Start profiling\. Setting inst count base to Current inst count\s+([0-9,]+)"
)
STOP_MATCH_RE = re.compile(r"ROI uart stop marker matched:\s*(.*)")
ROI_INSTRUCTIONS_RE = re.compile(r"ROI dynamic instructions\s*=\s*([0-9,]+)")
CHECKPOINT_RE = re.compile(r"Taking checkpoint @ instruction count\s+([0-9,]+)")
MSIZE_RE = re.compile(r"^CONFIG_MSIZE=(0x[0-9a-fA-F]+|[0-9]+)$", re.MULTILINE)
ANSI_ESCAPE_RE = re.compile(r"\x1b\[[0-?]*[ -/]*[@-~]")


@dataclass(frozen=True)
class VirtualProfilingEvidence:
    start_marker: str
    stop_marker: str
    marker_base: int
    roi_instructions: int


def _parse_count(value: str) -> int:
    return int(value.replace(",", ""), 10)


def _clean_marker(value: str) -> str:
    return ANSI_ESCAPE_RE.sub("", value).strip()


def _read_log_texts(paths: list[str | Path]) -> list[tuple[Path, str]]:
    result = []
    for raw_path in paths:
        path = Path(raw_path)
        if path.is_file():
            result.append((path, path.read_text(encoding="utf-8", errors="replace")))
    return result


def parse_virtual_profiling_text(
    text: str,
    expected_start_marker: str,
    expected_stop_marker: str,
) -> VirtualProfilingEvidence:
    start_match = START_MATCH_RE.search(text)
    start_base = START_BASE_RE.search(text)
    stop_match = STOP_MATCH_RE.search(text)
    roi_instructions = ROI_INSTRUCTIONS_RE.search(text)

    missing = []
    if start_match is None:
        missing.append("start marker match")
    if start_base is None:
        missing.append("profiling start")
    if stop_match is None:
        missing.append("stop marker match")
    if roi_instructions is None:
        missing.append("ROI instruction count")
    if missing:
        raise ValueError("virtual profiling evidence missing: " + ", ".join(missing))

    assert start_match is not None
    assert start_base is not None
    assert stop_match is not None
    assert roi_instructions is not None
    actual_start_marker = _clean_marker(start_match.group(1))
    actual_stop_marker = _clean_marker(stop_match.group(1))
    if actual_start_marker != expected_start_marker:
        raise ValueError(
            "virtual profiling matched unexpected start marker: "
            f"{actual_start_marker!r} (expected {expected_start_marker!r})"
        )
    if actual_stop_marker != expected_stop_marker:
        raise ValueError(
            "virtual profiling matched unexpected stop marker: "
            f"{actual_stop_marker!r} (expected {expected_stop_marker!r})"
        )
    if not (
        start_match.start()
        < start_base.start()
        < stop_match.start()
        < roi_instructions.start()
    ):
        raise ValueError("virtual profiling markers and ROI evidence are out of order")

    marker_base = _parse_count(start_base.group(1))
    roi_count = _parse_count(roi_instructions.group(1))
    if roi_count < 1:
        raise ValueError("virtual profiling reported an empty ROI")
    return VirtualProfilingEvidence(
        start_marker=actual_start_marker,
        stop_marker=actual_stop_marker,
        marker_base=marker_base,
        roi_instructions=roi_count,
    )


def parse_virtual_profiling_logs(
    paths: list[str | Path],
    expected_start_marker: str,
    expected_stop_marker: str,
) -> VirtualProfilingEvidence:
    texts = _read_log_texts(paths)
    if not texts:
        raise FileNotFoundError("virtual profiling logs are missing")

    errors = []
    for path, text in texts:
        try:
            return parse_virtual_profiling_text(
                text, expected_start_marker, expected_stop_marker
            )
        except ValueError as exc:
            errors.append(f"{path}: {exc}")

    combined = "\n".join(text for _, text in texts)
    try:
        return parse_virtual_profiling_text(
            combined, expected_start_marker, expected_stop_marker
        )
    except ValueError as exc:
        details = "; ".join(errors)
        raise ValueError(f"{exc}; checked {details}") from exc


def validate_virtual_bbv(path: str | Path) -> None:
    bbv_path = Path(path)
    if not bbv_path.is_file() or bbv_path.stat().st_size == 0:
        raise FileNotFoundError(f"virtual profiling BBV is missing or empty: {bbv_path}")


def validate_virtual_checkpoint_logs(
    paths: list[str | Path], expected_start_marker: str
) -> int:
    texts = _read_log_texts(paths)
    if not texts:
        raise FileNotFoundError("virtual checkpoint logs are missing")
    text = "\n".join(item for _, item in texts)
    start_match = START_MATCH_RE.search(text)
    start_base = START_BASE_RE.search(text)
    checkpoint = CHECKPOINT_RE.search(text)
    if start_match is None or start_base is None:
        raise ValueError("virtual checkpoint did not start after the UART marker")
    actual_marker = _clean_marker(start_match.group(1))
    if actual_marker != expected_start_marker:
        raise ValueError(
            "virtual checkpoint matched unexpected start marker: "
            f"{actual_marker!r} (expected {expected_start_marker!r})"
        )
    if checkpoint is None or checkpoint.start() < start_base.start():
        raise ValueError("virtual checkpoint log has no checkpoint after ROI start")
    return _parse_count(start_base.group(1))


def max_simpoint(simpoints_path: str | Path) -> int:
    path = Path(simpoints_path)
    points = []
    with path.open("r", encoding="utf-8") as handle:
        for raw_line in handle:
            fields = raw_line.split()
            if fields:
                points.append(int(fields[0], 0))
    if not points:
        raise ValueError(f"no SimPoint entries found: {path}")
    return max(points)


def virtual_checkpoint_max_instr(
    marker_base: int,
    simpoints_path: str | Path,
    interval: int,
    hard_limit: int | None = None,
) -> int:
    if marker_base < 0:
        raise ValueError("virtual marker base cannot be negative")
    if interval <= 0:
        raise ValueError("checkpoint interval must be positive")
    limit = marker_base + (max_simpoint(simpoints_path) + 2) * interval
    if hard_limit is not None and limit > hard_limit:
        raise ValueError(
            f"virtual checkpoint requires -I {limit}, exceeding "
            f"--virtual-max-instr {hard_limit}"
        )
    return limit


@lru_cache(maxsize=None)
def validate_virtual_nemu(
    nemu_bin: str, nemu_config: str, required_memory_bytes: int
) -> int:
    help_result = subprocess.run(
        [nemu_bin, "--help"],
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
        timeout=30,
        check=False,
    )
    missing_options = [
        option for option in NEMU_MARKER_OPTIONS if option not in help_result.stdout
    ]
    if help_result.returncode != 0 or missing_options:
        detail = ", ".join(missing_options) or f"exit code {help_result.returncode}"
        raise RuntimeError(f"NEMU does not support virtual ROI markers: {detail}")

    config_path = Path(nemu_config)
    if not config_path.is_file():
        raise FileNotFoundError(f"NEMU configuration is missing: {config_path}")
    match = MSIZE_RE.search(config_path.read_text(encoding="utf-8"))
    if match is None:
        raise ValueError(f"CONFIG_MSIZE is missing from NEMU configuration: {config_path}")
    configured_memory = int(match.group(1), 0)
    if configured_memory < required_memory_bytes:
        raise ValueError(
            f"NEMU CONFIG_MSIZE is {configured_memory} bytes, but the virtual "
            f"workload DTB requires {required_memory_bytes} bytes"
        )
    return configured_memory
