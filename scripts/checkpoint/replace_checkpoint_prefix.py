import argparse
import gzip
import os
import shutil
import subprocess
import tempfile
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path


COPY_BUFFER_SIZE = 1024 * 1024
RESTORE_SIZE_OFFSET = 4
RESTORE_SIZE_BYTES = 4
CHECKPOINT_SUFFIXES = (".gz", ".zstd")
GZIP_MAGIC = b"\x1f\x8b"
ZSTD_MAGIC = b"\x28\xb5\x2f\xfd"


@dataclass(frozen=True)
class ReplacementSummary:
    files: int
    gcpt_size: int


ProgressCallback = Callable[[str], None]


def find_zstd() -> str:
    zstd = shutil.which("zstd")
    if zstd is None:
        raise RuntimeError("zstd command not found in PATH")
    return zstd


def iter_checkpoint_files(checkpoint_dir: Path) -> list[Path]:
    files = sorted(
        path for path in checkpoint_dir.rglob("*")
        if path.is_file() and path.suffix in CHECKPOINT_SUFFIXES
    )
    if not files:
        raise ValueError(
            f"no compressed checkpoint files found under: {checkpoint_dir}"
        )
    return files


def read_restore_size(gcpt_bin: Path) -> int:
    with gcpt_bin.open("rb") as handle:
        header = handle.read(RESTORE_SIZE_OFFSET + RESTORE_SIZE_BYTES)
    if len(header) < RESTORE_SIZE_OFFSET + RESTORE_SIZE_BYTES:
        raise ValueError(f"gcpt.bin is too small to contain restore_size: {gcpt_bin}")

    restore_size = int.from_bytes(
        header[RESTORE_SIZE_OFFSET:RESTORE_SIZE_OFFSET + RESTORE_SIZE_BYTES],
        byteorder="little",
        signed=False,
    )
    if restore_size <= 0:
        raise ValueError(f"gcpt.bin restore_size is zero: {gcpt_bin}")
    return restore_size


def detect_compression(checkpoint_file: Path) -> str:
    with checkpoint_file.open("rb") as handle:
        magic = handle.read(4)
    if magic.startswith(GZIP_MAGIC):
        return "gzip"
    if magic == ZSTD_MAGIC:
        return "zstd"
    raise ValueError(f"unsupported checkpoint compression: {checkpoint_file}")


def validate_inputs(gcpt_bin: Path, checkpoint_dir: Path, output_dir: Path | None) -> int:
    if not gcpt_bin.is_file():
        raise FileNotFoundError(gcpt_bin)
    if not checkpoint_dir.is_dir():
        raise NotADirectoryError(checkpoint_dir)
    if output_dir is None:
        raise ValueError("output_dir is required")

    checkpoint_dir_resolved = checkpoint_dir.resolve()
    output_dir_resolved = output_dir.resolve()
    if output_dir_resolved == checkpoint_dir_resolved:
        raise ValueError("output_dir must be different from checkpoint_dir")
    if checkpoint_dir_resolved in output_dir_resolved.parents:
        raise ValueError("output_dir must not be inside checkpoint_dir")

    gcpt_size = gcpt_bin.stat().st_size
    if gcpt_size <= 0:
        raise ValueError(f"gcpt.bin is empty: {gcpt_bin}")
    restore_size = read_restore_size(gcpt_bin)
    if restore_size > gcpt_size:
        raise ValueError(
            f"gcpt.bin restore_size exceeds file size: {gcpt_bin} ({restore_size} > {gcpt_size})"
        )
    return restore_size


def run_zstd(command: list[str]) -> None:
    try:
        subprocess.run(command, check=True)
    except subprocess.CalledProcessError as exc:
        raise RuntimeError(f"zstd command failed with exit code {exc.returncode}") from exc


def copy_prefix(source_path: Path, target_path: Path, byte_count: int) -> None:
    with source_path.open("rb") as source, target_path.open("r+b") as target:
        remaining = byte_count
        while remaining > 0:
            chunk = source.read(min(COPY_BUFFER_SIZE, remaining))
            if not chunk:
                raise ValueError(
                    f"source ended before requested prefix bytes were copied: {source_path}"
                )
            target.write(chunk)
            remaining -= len(chunk)


def decompress_gzip(source_path: Path, target_path: Path) -> None:
    with gzip.open(source_path, "rb") as source, target_path.open("wb") as target:
        shutil.copyfileobj(source, target, length=COPY_BUFFER_SIZE)


def compress_gzip(source_path: Path, target_path: Path) -> None:
    with source_path.open("rb") as source, gzip.open(
            target_path, "wb", compresslevel=6) as target:
        shutil.copyfileobj(source, target, length=COPY_BUFFER_SIZE)


def rewrite_checkpoint(
    *,
    zstd: str | None,
    compression: str,
    gcpt_bin: Path,
    gcpt_size: int,
    checkpoint_file: Path,
    target_file: Path,
) -> None:
    checkpoint_stat = checkpoint_file.stat()
    target_file.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(
        prefix=f".{target_file.name}.",
        suffix=".work",
        dir=target_file.parent,
    ) as temp:
        temp_dir = Path(temp)
        raw_checkpoint = temp_dir / "checkpoint.raw"
        rewritten_checkpoint = temp_dir / target_file.name

        if compression == "gzip":
            decompress_gzip(checkpoint_file, raw_checkpoint)
        else:
            assert zstd is not None
            run_zstd([
                zstd, "-q", "-d", "-f", str(checkpoint_file),
                "-o", str(raw_checkpoint)
            ])
        raw_size = raw_checkpoint.stat().st_size
        if raw_size < gcpt_size:
            raise ValueError(
                f"decompressed checkpoint is smaller than gcpt.bin: "
                f"{checkpoint_file} ({raw_size} < {gcpt_size})"
            )

        copy_prefix(gcpt_bin, raw_checkpoint, gcpt_size)
        if compression == "gzip":
            compress_gzip(raw_checkpoint, rewritten_checkpoint)
        else:
            assert zstd is not None
            run_zstd([
                zstd, "-q", "-f", str(raw_checkpoint),
                "-o", str(rewritten_checkpoint)
            ])
        rewritten_checkpoint.chmod(checkpoint_stat.st_mode & 0o777)
        os.replace(rewritten_checkpoint, target_file)


def replace_checkpoint_prefixes(
    gcpt_bin: str | Path,
    checkpoint_dir: str | Path,
    *,
    output_dir: str | Path | None = None,
    progress: ProgressCallback | None = None,
) -> ReplacementSummary:
    gcpt_bin = Path(gcpt_bin)
    checkpoint_dir = Path(checkpoint_dir)
    output_dir = None if output_dir is None else Path(output_dir)
    gcpt_size = validate_inputs(gcpt_bin, checkpoint_dir, output_dir)
    checkpoint_files = iter_checkpoint_files(checkpoint_dir)
    compression_by_path = {
        path: detect_compression(path) for path in checkpoint_files
    }
    zstd = (
        find_zstd()
        if "zstd" in compression_by_path.values()
        else None
    )
    total_files = len(checkpoint_files)

    if progress is not None:
        progress(f"Found checkpoint files: {total_files}")

    assert output_dir is not None
    for done_count, checkpoint_file in enumerate(checkpoint_files, start=1):
        target_file = output_dir / checkpoint_file.relative_to(checkpoint_dir)
        rewrite_checkpoint(
            zstd=zstd,
            compression=compression_by_path[checkpoint_file],
            gcpt_bin=gcpt_bin,
            gcpt_size=gcpt_size,
            checkpoint_file=checkpoint_file,
            target_file=target_file,
        )
        if progress is not None:
            relative_path = checkpoint_file.relative_to(checkpoint_dir)
            progress(f"Wrote [{done_count}/{total_files}] {relative_path}")

    return ReplacementSummary(
        files=total_files,
        gcpt_size=gcpt_size,
    )


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Decompress every .gz or .zstd checkpoint under a directory, "
            "replace the front of the decompressed payload with gcpt.bin, "
            "then recompress the result into an output directory."
        )
    )
    parser.add_argument(
        "--gcpt-bin",
        required=True,
        help="gcpt.bin whose bytes will replace the beginning of each checkpoint payload.",
    )
    parser.add_argument(
        "--checkpoint-dir",
        required=True,
        help="Directory containing .zstd checkpoint files to update recursively.",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory where rewritten checkpoints are stored with the same relative paths.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)

    def print_progress(message: str) -> None:
        print(message, flush=True)

    summary = replace_checkpoint_prefixes(
        args.gcpt_bin,
        args.checkpoint_dir,
        output_dir=args.output_dir,
        progress=print_progress,
    )
    print(f"Checkpoint files written: {summary.files}")
    print(f"gcpt.bin bytes: {summary.gcpt_size}")
    print(f"output directory: {args.output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
