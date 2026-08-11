import argparse
import concurrent.futures
import os
import shutil
import struct
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

from virtual_checkpoint import DEFAULT_START_MARKER
from virtual_checkpoint import DEFAULT_STOP_MARKER
from virtual_checkpoint import parse_virtual_profiling_logs
from virtual_checkpoint import validate_virtual_nemu
from virtual_checkpoint import virtual_checkpoint_max_instr

AUTO_RESUME = "auto"
COMPLETE_STATE = "complete"
AUTO_RESUME_BACKUP_SUFFIX = "auto-resume-full"
KNOWN_WORKLOAD_SUFFIXES = (
    ".fw_payload.bin",
    ".bin",
)
FDT_MAGIC = 0xD00DFEED
FDT_MAGIC_BYTES = FDT_MAGIC.to_bytes(4, byteorder="big")
FDT_HEADER = struct.Struct(">10I")
FDT_HEADER_SIZE = FDT_HEADER.size
FDT_BEGIN_NODE = 1
FDT_END_NODE = 2
FDT_PROP = 3
FDT_NOP = 4
FDT_END = 9
FDT_SCAN_CHUNK_SIZE = 1024 * 1024
FDT_KNOWN_OFFSETS = (2 * 1024 * 1024, 1536 * 1024, 0)
KIB = 1024
MIB = 1024 * KIB
GIB = 1024 * MIB
QEMU_CPU = (
    "rv64,zicond=true,v=true,vlen=128,h=true,sv39=true,sv48=true,"
    "sv57=false,sv64=false,smstateen=true,sscofpmf=true,svade=true,"
    "svinval=true,svnapot=true,svpbmt=true,zacas=true,zawrs=true,"
    "zba=true,zbb=true,zbc=true,zbkb=true,zbkc=true,zbkx=true,zbs=true,"
    "zca=true,zcb=true,zcmop=true,zfa=true,zfh=true,zfhmin=true,"
    "zicntr=true,zicsr=true,zifencei=true,zihintntl=true,"
    "zihintpause=true,zihpm=true,zimop=true,zkn=true,zknd=true,zkne=true,"
    "zknh=true,zksed=true,zksh=true,zkt=true,zvbb=true,zvfh=true,"
    "zvfhmin=true,zvkt=true"
)


@dataclass(frozen=True)
class NemuPaths:
    home: str
    nemu: str
    simpoint: str


@dataclass(frozen=True)
class QemuPaths:
    home: str
    qemu: str
    profiling_plugin: str


def _align_fdt_offset(offset: int) -> int:
    return (offset + 3) & ~3


def _read_fdt_blob(handle, file_size: int, offset: int) -> bytes:
    if offset < 0 or offset + FDT_HEADER_SIZE > file_size:
        raise ValueError("FDT header is outside the workload bin")

    handle.seek(offset)
    header = handle.read(FDT_HEADER_SIZE)
    if len(header) != FDT_HEADER_SIZE:
        raise ValueError("truncated FDT header")

    (magic, total_size, struct_offset, strings_offset, _, _, _, _,
     strings_size, struct_size) = FDT_HEADER.unpack(header)
    if magic != FDT_MAGIC:
        raise ValueError("not an FDT header")
    if total_size < FDT_HEADER_SIZE or offset + total_size > file_size:
        raise ValueError("invalid FDT total size")
    if struct_offset + struct_size > total_size:
        raise ValueError("invalid FDT structure block")
    if strings_offset + strings_size > total_size:
        raise ValueError("invalid FDT strings block")

    handle.seek(offset)
    blob = handle.read(total_size)
    if len(blob) != total_size:
        raise ValueError("truncated FDT")
    return blob


def _fdt_property_name(blob: bytes, strings_offset: int, strings_size: int,
                       name_offset: int) -> str:
    start = strings_offset + name_offset
    end_limit = strings_offset + strings_size
    if start >= end_limit:
        raise ValueError("invalid FDT property name offset")
    end = blob.find(b"\0", start, end_limit)
    if end < 0:
        raise ValueError("unterminated FDT property name")
    return blob[start:end].decode("ascii")


def _fdt_cell_value(data: bytes, offset: int, cells: int) -> int:
    value = 0
    for index in range(cells):
        value = (value << 32) | struct.unpack_from(">I", data,
                                                    offset + index * 4)[0]
    return value


def _memory_size_from_reg(reg: bytes, address_cells: int, size_cells: int) -> int:
    entry_cells = address_cells + size_cells
    entry_size = entry_cells * 4
    if address_cells < 1 or size_cells < 1 or len(reg) % entry_size:
        raise ValueError("invalid memory reg property in workload DTB")

    total_size = 0
    for offset in range(0, len(reg), entry_size):
        total_size += _fdt_cell_value(reg, offset + address_cells * 4,
                                      size_cells)
    if total_size < 1:
        raise ValueError("workload DTB declares no RAM")
    return total_size


def _memory_size_from_fdt(blob: bytes) -> int:
    (_, total_size, struct_offset, strings_offset, _, _, _, _, strings_size,
     struct_size) = FDT_HEADER.unpack_from(blob)
    if total_size != len(blob):
        raise ValueError("inconsistent FDT size")

    struct_end = struct_offset + struct_size
    if struct_end > len(blob):
        raise ValueError("invalid FDT structure block")

    address_cells = 2
    size_cells = 1
    node_stack = []
    offset = struct_offset
    while offset < struct_end:
        token = struct.unpack_from(">I", blob, offset)[0]
        offset += 4

        if token == FDT_BEGIN_NODE:
            name_end = blob.find(b"\0", offset, struct_end)
            if name_end < 0:
                raise ValueError("unterminated FDT node name")
            node_stack.append({
                "name": blob[offset:name_end].decode("ascii"),
                "properties": {},
            })
            offset = _align_fdt_offset(name_end + 1)
        elif token == FDT_END_NODE:
            if not node_stack:
                raise ValueError("unbalanced FDT node end")
            node = node_stack.pop()
            properties = node["properties"]
            is_memory = (node["name"] == "memory"
                         or node["name"].startswith("memory@")
                         or properties.get("device_type", b"").rstrip(b"\0")
                         == b"memory")
            if is_memory and "reg" in properties:
                return _memory_size_from_reg(properties["reg"], address_cells,
                                             size_cells)
        elif token == FDT_PROP:
            if not node_stack or offset + 8 > struct_end:
                raise ValueError("invalid FDT property")
            value_size, name_offset = struct.unpack_from(">II", blob, offset)
            offset += 8
            value_end = offset + value_size
            if value_end > struct_end:
                raise ValueError("truncated FDT property value")
            property_name = _fdt_property_name(blob, strings_offset,
                                                strings_size, name_offset)
            value = blob[offset:value_end]
            offset = _align_fdt_offset(value_end)
            node_stack[-1]["properties"][property_name] = value
            if len(node_stack) == 1 and property_name == "#address-cells":
                if len(value) != 4:
                    raise ValueError("invalid FDT address cell count")
                address_cells = struct.unpack(">I", value)[0]
            elif len(node_stack) == 1 and property_name == "#size-cells":
                if len(value) != 4:
                    raise ValueError("invalid FDT size cell count")
                size_cells = struct.unpack(">I", value)[0]
        elif token == FDT_NOP:
            continue
        elif token == FDT_END:
            break
        else:
            raise ValueError(f"unknown FDT token: {token}")

    raise ValueError("workload DTB has no memory node")


def _hart_count_from_fdt(blob: bytes) -> int:
    (_, total_size, struct_offset, strings_offset, _, _, _, _, strings_size,
     struct_size) = FDT_HEADER.unpack_from(blob)
    if total_size != len(blob):
        raise ValueError("inconsistent FDT size")

    struct_end = struct_offset + struct_size
    if struct_end > len(blob):
        raise ValueError("invalid FDT structure block")

    node_stack = []
    hart_count = 0
    offset = struct_offset
    while offset < struct_end:
        token = struct.unpack_from(">I", blob, offset)[0]
        offset += 4

        if token == FDT_BEGIN_NODE:
            name_end = blob.find(b"\0", offset, struct_end)
            if name_end < 0:
                raise ValueError("unterminated FDT node name")
            node_stack.append({
                "name": blob[offset:name_end].decode("ascii"),
                "properties": {},
            })
            offset = _align_fdt_offset(name_end + 1)
        elif token == FDT_END_NODE:
            if not node_stack:
                raise ValueError("unbalanced FDT node end")
            node = node_stack.pop()
            parent_name = node_stack[-1]["name"] if node_stack else ""
            properties = node["properties"]
            device_type = properties.get("device_type", b"").rstrip(b"\0")
            status = properties.get("status", b"okay\0").rstrip(b"\0")
            if (parent_name == "cpus"
                    and (node["name"] == "cpu"
                         or node["name"].startswith("cpu@")
                         or device_type == b"cpu")
                    and status != b"disabled"):
                hart_count += 1
        elif token == FDT_PROP:
            if not node_stack or offset + 8 > struct_end:
                raise ValueError("invalid FDT property")
            value_size, name_offset = struct.unpack_from(">II", blob, offset)
            offset += 8
            value_end = offset + value_size
            if value_end > struct_end:
                raise ValueError("truncated FDT property value")
            property_name = _fdt_property_name(blob, strings_offset,
                                                strings_size, name_offset)
            if property_name in ("device_type", "status"):
                node_stack[-1]["properties"][property_name] = blob[offset:value_end]
            offset = _align_fdt_offset(value_end)
        elif token == FDT_NOP:
            continue
        elif token == FDT_END:
            break
        else:
            raise ValueError(f"unknown FDT token: {token}")

    if hart_count < 1:
        raise ValueError("workload DTB has no enabled CPU nodes")
    return hart_count


def _fdt_offsets(handle, file_size: int):
    for offset in FDT_KNOWN_OFFSETS:
        if offset < file_size:
            yield offset

    handle.seek(0)
    prefix = b""
    file_offset = 0
    while True:
        handle.seek(file_offset)
        chunk = handle.read(FDT_SCAN_CHUNK_SIZE)
        if not chunk:
            return
        data = prefix + chunk
        start = 0
        while True:
            found = data.find(FDT_MAGIC_BYTES, start)
            if found < 0:
                break
            yield file_offset - len(prefix) + found
            start = found + 1
        prefix = data[-(len(FDT_MAGIC_BYTES) - 1):]
        file_offset += len(chunk)


def format_qemu_memory_size(memory_bytes: int) -> str:
    if memory_bytes < 1:
        raise ValueError("QEMU memory size must be positive")
    for unit, suffix in ((GIB, "G"), (MIB, "M"), (KIB, "K")):
        if memory_bytes % unit == 0:
            return f"{memory_bytes // unit}{suffix}"
    return str(memory_bytes)


def qemu_memory_from_workload_bin(workload_bin: str) -> str:
    """Return QEMU's -m value from the workload DTB's memory node."""
    try:
        memory_bytes = workload_memory_size(workload_bin)
    except ValueError as exc:
        raise ValueError(
            f"{exc}; pass --qemu-memory explicitly (for example, 64G)"
        ) from exc
    return format_qemu_memory_size(memory_bytes)


def workload_memory_size(workload_bin: str) -> int:
    """Return RAM bytes from the first valid workload DTB."""
    file_size = os.path.getsize(workload_bin)
    seen_offsets = set()
    with open(workload_bin, "rb") as handle:
        for offset in _fdt_offsets(handle, file_size):
            if offset in seen_offsets:
                continue
            seen_offsets.add(offset)
            try:
                blob = _read_fdt_blob(handle, file_size, offset)
                return _memory_size_from_fdt(blob)
            except (UnicodeDecodeError, ValueError, struct.error):
                continue

    raise ValueError(f"cannot determine memory from workload DTB: {workload_bin}")


def workload_hart_count(workload_bin: str) -> int | None:
    """Return enabled CPU nodes from the workload DTB when detectable."""
    file_size = os.path.getsize(workload_bin)
    seen_offsets = set()
    with open(workload_bin, "rb") as handle:
        for offset in _fdt_offsets(handle, file_size):
            if offset in seen_offsets:
                continue
            seen_offsets.add(offset)
            try:
                blob = _read_fdt_blob(handle, file_size, offset)
                return _hart_count_from_fdt(blob)
            except (UnicodeDecodeError, ValueError, struct.error):
                continue
    return None


def validate_workload_copies(workload_bin: str, copies: int) -> None:
    hart_count = workload_hart_count(workload_bin)
    if hart_count is not None and hart_count != copies:
        raise ValueError(
            f"workload DTB declares {hart_count} enabled harts, but --copies is "
            f"{copies}; rerun with --copies {hart_count}")


def resolve_qemu_memory(workload_bin: str, qemu_memory: str | None) -> str:
    if qemu_memory is not None:
        qemu_memory = qemu_memory.strip()
        if not qemu_memory:
            raise ValueError("--qemu-memory cannot be empty")
        return qemu_memory
    return qemu_memory_from_workload_bin(workload_bin)


def safe_name(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in "._-" else "-" for ch in value)


def resolve_output_base_dir() -> str:
    override = os.environ.get("CHECKPOINT_OUTPUT_BASE")
    if override:
        return os.path.realpath(override)
    return os.path.realpath("archive")


def build_archive_root(archive_id: str) -> str:
    return os.path.realpath(os.path.join(resolve_output_base_dir(), archive_id))


def require_env_path(env_var: str) -> str:
    value = os.environ.get(env_var)
    if not value:
        raise EnvironmentError(f"{env_var} is not set")
    if not os.path.isdir(value):
        raise EnvironmentError(f"{env_var} does not point to a directory: {value}")
    return value


def load_nemu_paths() -> NemuPaths:
    nemu_home = require_env_path("NEMU_HOME")
    paths = NemuPaths(
        home=nemu_home,
        nemu=os.path.join(nemu_home, "build", "riscv64-nemu-interpreter"),
        simpoint=os.path.join(
            nemu_home,
            "resource",
            "simpoint",
            "simpoint_repo",
            "bin",
            "simpoint",
        ),
    )
    missing = [
        path for path in [paths.nemu, paths.simpoint] if not os.path.isfile(path)
    ]
    if missing:
        raise FileNotFoundError(
            "required runtime tool missing: " + ", ".join(missing))
    return paths


def load_qemu_paths() -> QemuPaths:
    qemu_home = require_env_path("QEMU_HOME")
    paths = QemuPaths(
        home=qemu_home,
        qemu=os.path.join(qemu_home, "build", "qemu-system-riscv64"),
        profiling_plugin=os.path.join(
            qemu_home,
            "build",
            "contrib",
            "plugins",
            "libprofilingv2.so",
        ),
    )
    missing = [
        path for path in [paths.qemu, paths.profiling_plugin]
        if not os.path.isfile(path)
    ]
    if missing:
        raise FileNotFoundError(
            "required QEMU runtime tool missing: " + ", ".join(missing))
    return paths


def validate_virtual_workload(workload_bin: str) -> int:
    hart_count = workload_hart_count(workload_bin)
    if hart_count != 1:
        detected = "unknown" if hart_count is None else str(hart_count)
        raise ValueError(
            "virtualized workloads require a one-hart outer Host DTB; "
            f"detected {detected}"
        )
    nemu_paths = load_nemu_paths()
    required_memory = workload_memory_size(workload_bin)
    return validate_virtual_nemu(
        nemu_paths.nemu,
        os.path.join(nemu_paths.home, ".config"),
        required_memory,
    )


def _normalize_ids(ids):
    return tuple(int(item) for item in ids)


def format_stage_name(base: str, *ids) -> str:
    normalized = _normalize_ids(ids)
    if not normalized or all(item == 0 for item in normalized):
        return base
    return f"{base}-{'-'.join(str(item) for item in normalized)}"


def profiling_stage_name(profiling_id=0) -> str:
    return format_stage_name("profiling", profiling_id)


def cluster_stage_name(profiling_id=0, cluster_id=0) -> str:
    return format_stage_name("cluster", profiling_id, cluster_id)


def checkpoint_stage_name(profiling_id=0, cluster_id=0, checkpoint_id=0) -> str:
    return format_stage_name("checkpoint", profiling_id, cluster_id,
                             checkpoint_id)


def archive_layout(archive_root: str) -> dict[str, str]:
    return {
        "logs": os.path.join(archive_root, "logs"),
        "metadata": os.path.join(archive_root, "metadata"),
        "json": os.path.join(archive_root, "json"),
    }


def profiling_dir(archive_root: str, workload: str, profiling_id=0) -> str:
    return os.path.join(archive_root, profiling_stage_name(profiling_id),
                        workload)


def cluster_dir(archive_root: str,
                workload: str,
                profiling_id=0,
                cluster_id=0) -> str:
    return os.path.join(archive_root,
                        cluster_stage_name(profiling_id, cluster_id), workload)


def checkpoint_dir(archive_root: str,
                   workload: str,
                   profiling_id=0,
                   cluster_id=0,
                   checkpoint_id=0) -> str:
    return os.path.join(
        archive_root,
        checkpoint_stage_name(profiling_id, cluster_id, checkpoint_id),
        workload,
    )


def profiling_log_dir(archive_root: str, workload: str, profiling_id=0) -> str:
    return os.path.join(archive_root, "logs", profiling_stage_name(profiling_id),
                        workload)


def cluster_log_dir(archive_root: str,
                    workload: str,
                    profiling_id=0,
                    cluster_id=0) -> str:
    return os.path.join(
        archive_root,
        "logs",
        cluster_stage_name(profiling_id, cluster_id),
        workload,
    )


def checkpoint_log_dir(archive_root: str,
                       workload: str,
                       profiling_id=0,
                       cluster_id=0,
                       checkpoint_id=0) -> str:
    return os.path.join(
        archive_root,
        "logs",
        checkpoint_stage_name(profiling_id, cluster_id, checkpoint_id),
        workload,
    )


def workload_json_path(archive_root: str, workload: str) -> str:
    return os.path.join(archive_root, "json", f"{workload}.json")


def checkpoint_list_path(archive_root: str,
                         profiling_id=0,
                         cluster_id=0,
                         checkpoint_id=0) -> str:
    return os.path.join(
        archive_root,
        checkpoint_stage_name(profiling_id, cluster_id, checkpoint_id),
        "checkpoint.lst",
    )


def json_output_dir(base_path: str, checkpoint_name: str) -> str:
    if checkpoint_name == "checkpoint":
        return os.path.join(base_path, "json")
    return os.path.join(base_path, "json", checkpoint_name)


def count_checkpoints(archive_root: str, workload: str) -> int:
    from step_checkpoint import count_checkpoints as _count_checkpoints

    return _count_checkpoints(archive_root, workload)


def validate_outputs(archive_root: str, workload: str) -> None:
    from step_checkpoint import validate_outputs as _validate_outputs

    _validate_outputs(archive_root, workload)


def generate_checkpoint_metadata(archive_root, workloads, times, ids):
    from step_metadata import generate_checkpoint_metadata as _generate_metadata

    _generate_metadata(archive_root, workloads, times, ids)


def build_archive_layout(archive_root: str) -> dict[str, str]:
    return archive_layout(archive_root)


def ensure_directories(paths) -> None:
    for path in paths:
        os.makedirs(path, exist_ok=True)


def derive_archive_label(input_path: str | None) -> str:
    if not input_path:
        return "bins"
    label = os.path.basename(os.path.normpath(input_path))
    return safe_name(label) or "bins"


def generate_archive_id(mode: str,
                        workload: str | None = None,
                        input_path: str | None = None) -> str:
    timestamp = datetime.now().strftime("%Y-%m-%d-%H-%M-%S")
    if mode == "file":
        return f"{timestamp}_{safe_name(workload or 'workload')}"
    if mode == "directory":
        return f"{timestamp}_{derive_archive_label(input_path)}"
    raise ValueError(f"unsupported archive mode: {mode}")


def write_request_metadata(metadata_dir: str,
                           request: dict,
                           filename: str = "request.yaml") -> str:
    os.makedirs(metadata_dir, exist_ok=True)
    output_path = os.path.join(metadata_dir, filename)
    lines = []
    for key, value in request.items():
        if isinstance(value, list):
            rendered = "[" + ", ".join(str(item) for item in value) + "]"
        else:
            rendered = value
        lines.append(f"{key}: {rendered}")
    lines.append(f"timestamp: {datetime.now().isoformat(timespec='seconds')}")
    with open(output_path, "w", encoding="utf-8") as handle:
        handle.write("\n".join(str(line) for line in lines) + "\n")
    return output_path


def remove_path(path: str) -> None:
    if os.path.isdir(path):
        shutil.rmtree(path)
    elif os.path.exists(path):
        os.remove(path)


def clear_aggregate_metadata(archive_root: str) -> None:
    for path in [
            os.path.join(archive_root, "json", "checkpoints_cov0.3.json"),
            os.path.join(archive_root, "json", "checkpoints_all.json"),
            checkpoint_list_path(archive_root),
            os.path.join(archive_root, "checkpoint-0-0-0", "checkpoint.lst"),
            os.path.join(archive_root, "checkpoint-0-0-0", "cluster-0-0.json"),
    ]:
        remove_path(path)


def validate_resume_artifacts(archive_root: str, workload: str,
                              resume_after: str | None) -> None:
    required = []
    if resume_after == "profiling":
        required = [os.path.join(profiling_dir(archive_root, workload), "simpoint_bbv.gz")]
    elif resume_after == "cluster":
        required = [
            os.path.join(cluster_dir(archive_root, workload), "simpoints0"),
            os.path.join(cluster_dir(archive_root, workload), "weights0"),
        ]

    for path in required:
        if not os.path.exists(path):
            raise FileNotFoundError(f"required resume artifact missing: {path}")


def load_virtual_profiling_evidence(archive_root: str, workload: str,
                                    start_marker: str, stop_marker: str):
    log_dir = profiling_log_dir(archive_root, workload)
    return parse_virtual_profiling_logs(
        [
            os.path.join(log_dir, "profiling.out.log"),
            os.path.join(log_dir, "profiling.err.log"),
        ],
        start_marker,
        stop_marker,
    )


def parse_simpoint_points(simpoints_path: str) -> list[str]:
    points = []
    with open(simpoints_path, "r", encoding="utf-8") as handle:
        for raw_line in handle:
            parts = raw_line.split()
            if parts:
                points.append(parts[0])
    return points


def read_cluster_rows(cluster_output_dir: str) -> tuple[dict[str, str], dict[str, str]]:
    simpoint_rows = {}
    weight_rows = {}

    with open(os.path.join(cluster_output_dir, "simpoints0"),
              "r",
              encoding="utf-8") as handle:
        for raw_line in handle:
            parts = raw_line.split()
            if len(parts) >= 2:
                point, cluster_id = parts[0], parts[1]
                simpoint_rows[point] = cluster_id

    with open(os.path.join(cluster_output_dir, "weights0"),
              "r",
              encoding="utf-8") as handle:
        for raw_line in handle:
            parts = raw_line.split()
            if len(parts) >= 2:
                weight, cluster_id = parts[0], parts[1]
                weight_rows[cluster_id] = weight

    return simpoint_rows, weight_rows


def checkpoint_point_has_artifact(point_dir: str) -> bool:
    if not os.path.isdir(point_dir):
        return False
    return any(name.endswith((".gz", ".zstd")) for name in os.listdir(point_dir))


def detect_auto_resume_state(archive_root: str, workload: str) -> dict[str, object]:
    profiling_path = os.path.join(profiling_dir(archive_root, workload),
                                  "simpoint_bbv.gz")
    workload_cluster_dir = cluster_dir(archive_root, workload)
    simpoints_path = os.path.join(workload_cluster_dir, "simpoints0")
    weights_path = os.path.join(workload_cluster_dir, "weights0")
    simpoints_read_path = (f"{simpoints_path}.{AUTO_RESUME_BACKUP_SUFFIX}"
                           if os.path.exists(
                               f"{simpoints_path}.{AUTO_RESUME_BACKUP_SUFFIX}")
                           else simpoints_path)
    workload_checkpoint_dir = checkpoint_dir(archive_root, workload)

    if not os.path.exists(profiling_path):
        return {
            "state": "fresh",
            "resume_after": None,
            "skip": False,
            "expected_points": [],
            "present_points": [],
            "missing_points": [],
        }

    if not (os.path.exists(simpoints_path) and os.path.exists(weights_path)):
        return {
            "state": "after_profiling",
            "resume_after": "profiling",
            "skip": False,
            "expected_points": [],
            "present_points": [],
            "missing_points": [],
        }

    expected_points = parse_simpoint_points(simpoints_read_path)
    present_points = [
        point for point in expected_points
        if checkpoint_point_has_artifact(os.path.join(workload_checkpoint_dir, point))
    ]
    missing_points = [
        point for point in expected_points if point not in set(present_points)
    ]

    if expected_points and not missing_points:
        return {
            "state": COMPLETE_STATE,
            "resume_after": None,
            "skip": True,
            "expected_points": expected_points,
            "present_points": present_points,
            "missing_points": [],
        }

    return {
        "state": "after_cluster",
        "resume_after": "cluster",
        "skip": False,
        "expected_points": expected_points,
        "present_points": present_points,
        "missing_points": missing_points,
    }


def backup_file_once(path: str, suffix: str) -> None:
    if not os.path.exists(path):
        return
    backup_path = f"{path}.{suffix}"
    if not os.path.exists(backup_path):
        shutil.copy2(path, backup_path)


def restore_auto_resume_artifacts(archive_root: str, workload: str) -> None:
    workload_cluster_dir = cluster_dir(archive_root, workload)
    for name in ["simpoints0", "weights0"]:
        path = os.path.join(workload_cluster_dir, name)
        backup_path = f"{path}.{AUTO_RESUME_BACKUP_SUFFIX}"
        if os.path.exists(backup_path):
            shutil.copy2(backup_path, path)


def prepare_auto_resume_artifacts(archive_root: str, workload: str,
                                  state: dict[str, object]) -> str | None:
    resume_after = state["resume_after"]
    if resume_after != "cluster":
        return resume_after

    missing_points = list(state.get("missing_points", []))
    present_points = list(state.get("present_points", []))
    if not missing_points or not present_points:
        return resume_after

    workload_cluster_dir = cluster_dir(archive_root, workload)
    simpoints_path = os.path.join(workload_cluster_dir, "simpoints0")
    weights_path = os.path.join(workload_cluster_dir, "weights0")
    restore_auto_resume_artifacts(archive_root, workload)
    backup_file_once(simpoints_path, AUTO_RESUME_BACKUP_SUFFIX)
    backup_file_once(weights_path, AUTO_RESUME_BACKUP_SUFFIX)

    simpoint_rows, weight_rows = read_cluster_rows(workload_cluster_dir)
    with open(simpoints_path, "w", encoding="utf-8") as simpoints, open(
            weights_path, "w", encoding="utf-8") as weights:
        for new_cluster_id, point in enumerate(missing_points):
            old_cluster_id = simpoint_rows[point]
            print(f"{point} {new_cluster_id}", file=simpoints)
            print(f"{weight_rows[old_cluster_id]} {new_cluster_id}", file=weights)

    return resume_after


def inspect_input_kind(input_path: str) -> str:
    if os.path.isfile(input_path):
        return "file"
    if os.path.isdir(input_path):
        return "directory"
    raise FileNotFoundError(f"input path does not exist: {input_path}")


def validate_input_args(args) -> None:
    if not os.path.exists(args.input_path):
        raise FileNotFoundError(f"input path does not exist: {args.input_path}")
    if not os.access(args.input_path, os.R_OK):
        raise PermissionError(f"input path is not readable: {args.input_path}")

    input_kind = inspect_input_kind(args.input_path)
    if input_kind == "directory" and args.name is not None:
        raise ValueError("--name can only be used with a single file input")

    if args.resume_after is not None and args.archive_id is None:
        raise ValueError("--archive-id is required when using --resume-after")

    if args.max_workers < 1:
        raise ValueError("--max-workers must be at least 1")
    if args.copies < 1:
        raise ValueError("--copies must be at least 1")
    if args.interval <= 0:
        raise ValueError("--interval must be a positive integer")
    if args.max_k is not None and args.max_k <= 0:
        raise ValueError("--max-k must be a positive integer")
    if args.virtual_max_instr is not None and args.virtual_max_instr <= 0:
        raise ValueError("--virtual-max-instr must be a positive integer")

    if args.virtualized:
        if args.copies != 1:
            raise ValueError("--virtualized requires --copies 1 for the outer Host")
        if args.qemu_memory is not None:
            raise ValueError("--qemu-memory cannot be used with --virtualized")
        if input_kind == "file" and args.name is None:
            raise ValueError("--name is required for a single virtualized workload")
        if not args.virtual_start_marker:
            raise ValueError("--virtual-start-marker cannot be empty")
        if not args.virtual_stop_marker:
            raise ValueError("--virtual-stop-marker cannot be empty")
    elif args.virtual_max_instr is not None:
        raise ValueError("--virtual-max-instr requires --virtualized")


def ensure_resume_logs(archive_root: str, workload: str,
                       resume_after: str | None) -> None:
    if resume_after is None:
        return
    log_dir = profiling_log_dir(archive_root, workload)
    os.makedirs(log_dir, exist_ok=True)
    for name in ["profiling.out.log", "profiling.err.log"]:
        path = os.path.join(log_dir, name)
        if not os.path.exists(path):
            with open(path, "w", encoding="utf-8") as handle:
                handle.write("")


def reset_stage_outputs(archive_root: str, workload: str,
                        resume_after: str | None,
                        preserve_checkpoint_workload: bool = False) -> None:
    if resume_after is None:
        stages_to_remove = ("profiling", "cluster", "checkpoint")
    elif resume_after == "profiling":
        stages_to_remove = ("cluster", "checkpoint")
    elif resume_after == "cluster":
        stages_to_remove = ("checkpoint",)
    else:
        raise ValueError(f"unsupported resume stage: {resume_after}")

    stage_paths = {
        "profiling": [
            profiling_dir(archive_root, workload),
            profiling_log_dir(archive_root, workload),
        ],
        "cluster": [
            cluster_dir(archive_root, workload),
            cluster_log_dir(archive_root, workload),
        ],
        "checkpoint": [
            checkpoint_log_dir(archive_root, workload),
            workload_json_path(archive_root, workload),
            os.path.join(archive_root, "checkpoint-0-0-0", "cluster-0-0.json"),
            os.path.join(archive_root, "checkpoint-0-0-0", "checkpoint.lst"),
        ],
    }
    if not preserve_checkpoint_workload:
        stage_paths["checkpoint"].insert(0, checkpoint_dir(archive_root, workload))

    for stage in stages_to_remove:
        for path in stage_paths[stage]:
            remove_path(path)


def build_single_run_args(input_path: str, workload_name: str | None,
                          archive_id: str | None, interval: int,
                          max_workers: int,
                          copies: int,
                          qemu_memory: str | None,
                          max_k: int | None,
                          resume_after: str | None,
                          virtualized: bool = False,
                          virtual_start_marker: str = DEFAULT_START_MARKER,
                          virtual_stop_marker: str = DEFAULT_STOP_MARKER,
                          virtual_max_instr: int | None = None) -> argparse.Namespace:
    return argparse.Namespace(
        input_path=input_path,
        name=workload_name,
        archive_id=archive_id,
        interval=interval,
        max_workers=max_workers,
        copies=copies,
        qemu_memory=qemu_memory,
        max_k=max_k,
        resume_after=resume_after,
        virtualized=virtualized,
        virtual_start_marker=virtual_start_marker,
        virtual_stop_marker=virtual_stop_marker,
        virtual_max_instr=virtual_max_instr,
    )


def get_worker_bindings(index: int, numa_nodes: int = 2) -> tuple[str, str]:
    node = str(index % max(1, numa_nodes))
    return node, node


def strip_known_bin_suffix(file_name: str) -> str:
    for suffix in KNOWN_WORKLOAD_SUFFIXES:
        if file_name.endswith(suffix) and len(file_name) > len(suffix):
            return file_name[:-len(suffix)]
    return Path(file_name).stem


def longest_common_suffix(names: list[str]) -> str:
    if not names:
        return ""
    reversed_names = [name[::-1] for name in names]
    return os.path.commonprefix(reversed_names)[::-1]


def derive_common_bin_suffix(names: list[str]) -> str:
    for suffix in KNOWN_WORKLOAD_SUFFIXES:
        if all(name.endswith(suffix) for name in names):
            return suffix

    common_suffix = longest_common_suffix(names)
    if not common_suffix:
        return ""

    for marker in [".", "_", "-"]:
        index = common_suffix.find(marker)
        if index > 0:
            return common_suffix[index:]
    return common_suffix


def derive_directory_entries(input_dir: str) -> tuple[list[dict[str, str]], str]:
    files = sorted(entry for entry in Path(input_dir).iterdir() if entry.is_file())
    if not files:
        raise ValueError(f"input directory does not contain any files: {input_dir}")

    basenames = [entry.name for entry in files]
    common_suffix = derive_common_bin_suffix(basenames)
    entries = []
    seen_names = set()

    for file_path in files:
        workload_name = file_path.name
        if common_suffix and len(workload_name) > len(common_suffix):
            workload_name = workload_name[:-len(common_suffix)]
        workload_name = workload_name.rstrip(".-_") or strip_known_bin_suffix(
            file_path.name)
        if not workload_name:
            raise ValueError(
                f"unable to derive workload name from file: {file_path}")
        if workload_name in seen_names:
            raise ValueError(
                f"duplicate workload name derived from input directory: {workload_name}")

        entries.append({"bin": str(file_path), "name": workload_name})
        seen_names.add(workload_name)

    return entries, common_suffix


def load_input_entries(input_path: str,
                       name_override: str | None = None
                       ) -> tuple[str, list[dict[str, str]], str | None]:
    input_kind = inspect_input_kind(input_path)
    if input_kind == "file":
        workload_name = name_override or strip_known_bin_suffix(
            os.path.basename(os.path.normpath(input_path)))
        return "file", [{"bin": input_path, "name": workload_name}], None
    entries, common_suffix = derive_directory_entries(input_path)
    return "directory", entries, common_suffix


def run_workload(*,
                 bin_path: str,
                 workload_name: str,
                 archive_root: str,
                 interval: int,
                 copies: int,
                 max_k: int | None,
                 resume_after: str | None,
                 qemu_memory: str | None = None,
                 cpu_bind: str = "0",
                 mem_bind: str = "0",
                 metadata_dir: str | None = None,
                 generate_metadata: bool = True,
                 virtualized: bool = False,
                 virtual_start_marker: str = DEFAULT_START_MARKER,
                 virtual_stop_marker: str = DEFAULT_STOP_MARKER,
                 virtual_max_instr: int | None = None) -> dict[str, str | int]:
    from step_checkpoint import run_checkpoint_step
    from step_profiling import run_profiling_step
    from step_cluster import run_cluster_step

    layout = build_archive_layout(archive_root)
    ensure_directories(layout.values())
    load_nemu_paths()
    if copies > 1:
        load_qemu_paths()

    validate_workload_copies(bin_path, copies)
    virtual_nemu_memory = None
    if virtualized:
        virtual_nemu_memory = validate_virtual_workload(bin_path)

    effective_resume_after = resume_after
    preserve_checkpoint_workload = False
    if resume_after == AUTO_RESUME:
        state = detect_auto_resume_state(archive_root, workload_name)
        if state["skip"]:
            if virtualized:
                load_virtual_profiling_evidence(
                    archive_root,
                    workload_name,
                    virtual_start_marker,
                    virtual_stop_marker,
                )
            workload_checkpoint_dir = checkpoint_dir(archive_root, workload_name)
            return {
                "name": workload_name,
                "archive_id": os.path.basename(archive_root),
                "archive_root": archive_root,
                "checkpoint_count": count_checkpoints(archive_root, workload_name),
                "checkpoint_dir": workload_checkpoint_dir,
                "skipped": 1,
            }
        effective_resume_after = prepare_auto_resume_artifacts(
            archive_root, workload_name, state)
        preserve_checkpoint_workload = bool(state.get("present_points"))

    effective_qemu_memory = None
    if copies > 1:
        effective_qemu_memory = resolve_qemu_memory(bin_path, qemu_memory)

    request = {
        "bin": os.path.realpath(bin_path),
        "name": workload_name,
        "archive_id": os.path.basename(archive_root),
        "interval": interval,
        "copies": copies,
        "qemu_memory": effective_qemu_memory or "",
        "max_k": max_k,
        "resume_after": resume_after,
        "virtualized": virtualized,
        "virtual_start_marker": virtual_start_marker if virtualized else "",
        "virtual_stop_marker": virtual_stop_marker if virtualized else "",
        "virtual_max_instr": virtual_max_instr or "",
        "virtual_nemu_memory_bytes": virtual_nemu_memory or "",
    }
    request_dir = metadata_dir or layout["metadata"]
    metadata_path = write_request_metadata(request_dir,
                                           request,
                                           filename=f"{workload_name}.yaml")
    print(
        f"[Workload] name={workload_name} archive={os.path.basename(archive_root)} input={os.path.realpath(bin_path)}",
        flush=True,
    )

    reset_stage_outputs(
        archive_root,
        workload_name,
        effective_resume_after,
        preserve_checkpoint_workload=preserve_checkpoint_workload,
    )
    validate_resume_artifacts(archive_root, workload_name, effective_resume_after)
    if not virtualized:
        ensure_resume_logs(archive_root, workload_name, effective_resume_after)

    virtual_evidence = None
    if virtualized and effective_resume_after is not None:
        virtual_evidence = load_virtual_profiling_evidence(
            archive_root,
            workload_name,
            virtual_start_marker,
            virtual_stop_marker,
        )

    try:
        if effective_resume_after is None:
            print(
                f"[Profiling] start workload={workload_name} interval={interval} cpu={cpu_bind} mem={mem_bind}",
                flush=True,
            )
            profiling_rc = run_profiling_step(
                archive_root=archive_root,
                workload=workload_name,
                workload_bin=bin_path,
                interval=interval,
                copies=copies,
                qemu_memory=effective_qemu_memory,
                cpu_bind=cpu_bind,
                mem_bind=mem_bind,
                virtualized=virtualized,
                virtual_start_marker=virtual_start_marker,
                virtual_stop_marker=virtual_stop_marker,
                virtual_max_instr=virtual_max_instr,
            )
            if profiling_rc != 0:
                raise RuntimeError(
                    f"profiling stage failed for {workload_name} with exit code "
                    f"{profiling_rc}; see "
                    f"{profiling_log_dir(archive_root, workload_name)}")
            print(
                f"[Profiling] done workload={workload_name} log={profiling_log_dir(archive_root, workload_name)}",
                flush=True,
            )
            if virtualized:
                virtual_evidence = load_virtual_profiling_evidence(
                    archive_root,
                    workload_name,
                    virtual_start_marker,
                    virtual_stop_marker,
                )
            print(
                f"[Clustering] start workload={workload_name} cpu={cpu_bind} mem={mem_bind}",
                flush=True,
            )
            run_cluster_step(
                archive_root=archive_root,
                workload=workload_name,
                max_k=max_k,
                cpu_bind=cpu_bind,
                mem_bind=mem_bind,
            )
            print(
                f"[Clustering] done workload={workload_name} log={cluster_log_dir(archive_root, workload_name)}",
                flush=True,
            )
        elif effective_resume_after == "profiling":
            print(
                f"[Clustering] resume workload={workload_name} from=profiling cpu={cpu_bind} mem={mem_bind}",
                flush=True,
            )
            run_cluster_step(
                archive_root=archive_root,
                workload=workload_name,
                max_k=max_k,
                cpu_bind=cpu_bind,
                mem_bind=mem_bind,
            )
            print(
                f"[Clustering] done workload={workload_name} log={cluster_log_dir(archive_root, workload_name)}",
                flush=True,
            )
        elif effective_resume_after != "cluster":
            raise ValueError(f"unsupported resume stage: {effective_resume_after}")

        if effective_resume_after == "cluster":
            print(
                f"[Checkpoint] resume workload={workload_name} from=cluster cpu={cpu_bind} mem={mem_bind}",
                flush=True,
            )
        else:
            print(
                f"[Checkpoint] start workload={workload_name} interval={interval} cpu={cpu_bind} mem={mem_bind}",
                flush=True,
            )
        virtual_checkpoint_limit = None
        if virtualized:
            if virtual_evidence is None:
                raise RuntimeError("virtual profiling evidence was not loaded")
            virtual_checkpoint_limit = virtual_checkpoint_max_instr(
                virtual_evidence.marker_base,
                os.path.join(cluster_dir(archive_root, workload_name), "simpoints0"),
                interval,
                virtual_max_instr,
            )
            request.update({
                "virtual_marker_base": virtual_evidence.marker_base,
                "virtual_roi_instructions": virtual_evidence.roi_instructions,
                "virtual_checkpoint_max_instr": virtual_checkpoint_limit,
            })
            metadata_path = write_request_metadata(
                request_dir, request, filename=f"{workload_name}.yaml")
        checkpoint_rc = run_checkpoint_step(
            archive_root=archive_root,
            workload=workload_name,
            workload_bin=bin_path,
            interval=interval,
            copies=copies,
            qemu_memory=effective_qemu_memory,
            cpu_bind=cpu_bind,
            mem_bind=mem_bind,
            virtualized=virtualized,
            virtual_start_marker=virtual_start_marker,
            virtual_stop_marker=virtual_stop_marker,
            virtual_max_instr=virtual_max_instr,
            virtual_checkpoint_limit=virtual_checkpoint_limit,
        )
        if checkpoint_rc != 0:
            raise RuntimeError(
                f"checkpoint stage failed for {workload_name} with exit code "
                f"{checkpoint_rc}; see "
                f"{checkpoint_log_dir(archive_root, workload_name)}")
        print(
            f"[Checkpoint] done workload={workload_name} log={checkpoint_log_dir(archive_root, workload_name)}",
            flush=True,
        )
    finally:
        if resume_after == AUTO_RESUME:
            restore_auto_resume_artifacts(archive_root, workload_name)

    validate_outputs(archive_root, workload_name)
    if generate_metadata:
        print(f"[Metadata] start workload={workload_name}", flush=True)
        clear_aggregate_metadata(archive_root)
        generate_checkpoint_metadata(
            archive_root=archive_root,
            workloads=[workload_name],
            times=[1, 1, 1],
            ids=[0, 0, 0],
        )
        print(f"[Metadata] done workload={workload_name}", flush=True)

    workload_checkpoint_dir = checkpoint_dir(archive_root, workload_name)
    print(
        f"[Workload] done name={workload_name} checkpoints={count_checkpoints(archive_root, workload_name)} dir={workload_checkpoint_dir}",
        flush=True,
    )
    return {
        "name": workload_name,
        "archive_id": os.path.basename(archive_root),
        "archive_root": archive_root,
        "checkpoint_count": count_checkpoints(archive_root, workload_name),
        "checkpoint_dir": workload_checkpoint_dir,
        "metadata": metadata_path,
    }


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=
        "Run profiling, cluster, checkpoint, and metadata from one bin or a directory of bins",
    )
    parser.add_argument("--input-path",
                        required=True,
                        help="Path to a GCPT-bootable bin file or a directory of bin files")
    parser.add_argument("--name",
                        help="Optional workload name override used only with a single input file")
    parser.add_argument("--archive-id", help="Existing or new archive id")
    parser.add_argument("--interval",
                        type=int,
                        default=20_000_000,
                        help="Checkpoint interval")
    parser.add_argument("--max-k",
                        type=int,
                        help="Optional SimPoint maxK override; effective value is max(workload default, user value)")
    parser.add_argument("--max-workers",
                        type=int,
                        default=3,
                        help="Maximum parallel workloads used in directory mode")
    parser.add_argument("--copies",
                        type=int,
                        default=1,
                        help="Number of workload copies encoded in the GCPT bin")
    parser.add_argument(
        "--qemu-memory",
        help="QEMU guest RAM for --copies > 1; defaults to the workload DTB memory size",
    )
    parser.add_argument(
        "--virtualized",
        action="store_true",
        help="Profile a workload-builder Host/QEMU/KVM/Guest payload by UART ROI markers",
    )
    parser.add_argument("--virtual-start-marker", default=DEFAULT_START_MARKER)
    parser.add_argument("--virtual-stop-marker", default=DEFAULT_STOP_MARKER)
    parser.add_argument(
        "--virtual-max-instr",
        type=int,
        help="Optional hard outer-NEMU instruction limit for a virtualized workload",
    )
    parser.add_argument("--resume-after",
                        choices=["profiling", "cluster", AUTO_RESUME],
                        help="Resume from a later stage")
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()
    validate_input_args(args)

    input_mode, entries, common_suffix = load_input_entries(args.input_path,
                                                            args.name)
    for entry in entries:
        validate_input_args(
            build_single_run_args(input_path=entry["bin"],
                                  workload_name=entry["name"],
                                  archive_id=args.archive_id,
                                  interval=args.interval,
                                  max_workers=args.max_workers,
                                  copies=args.copies,
                                  qemu_memory=args.qemu_memory,
                                  max_k=args.max_k,
                                  resume_after=args.resume_after,
                                  virtualized=args.virtualized,
                                  virtual_start_marker=args.virtual_start_marker,
                                  virtual_stop_marker=args.virtual_stop_marker,
                                  virtual_max_instr=args.virtual_max_instr))

    if input_mode == "file":
        archive_id = args.archive_id or generate_archive_id("file",
                                                            entries[0]["name"])
        archive_root = build_archive_root(archive_id)
        ensure_directories(build_archive_layout(archive_root).values())
        clear_aggregate_metadata(archive_root)
        write_request_metadata(
            os.path.join(archive_root, "metadata"),
            {
                "mode": "file",
                "input_path": os.path.realpath(args.input_path),
                "name": entries[0]["name"],
                "archive_id": archive_id,
                "interval": args.interval,
                "copies": args.copies,
                "qemu_memory": args.qemu_memory or "auto",
                "max_k": args.max_k,
                "resume_after": args.resume_after,
                "virtualized": args.virtualized,
                "virtual_start_marker": args.virtual_start_marker if args.virtualized else "",
                "virtual_stop_marker": args.virtual_stop_marker if args.virtualized else "",
                "virtual_max_instr": args.virtual_max_instr or "",
            },
        )
        print(f"Archive: {archive_id}", flush=True)
        print(f"Archive root: {archive_root}", flush=True)
        run_workload(
            bin_path=entries[0]["bin"],
            workload_name=entries[0]["name"],
            archive_root=archive_root,
            interval=args.interval,
            copies=args.copies,
            qemu_memory=args.qemu_memory,
            max_k=args.max_k,
            resume_after=args.resume_after,
            virtualized=args.virtualized,
            virtual_start_marker=args.virtual_start_marker,
            virtual_stop_marker=args.virtual_stop_marker,
            virtual_max_instr=args.virtual_max_instr,
        )
        return 0

    archive_id = args.archive_id or generate_archive_id("directory",
                                                        input_path=args.input_path)
    archive_root = build_archive_root(archive_id)
    layout = build_archive_layout(archive_root)
    ensure_directories(layout.values())
    clear_aggregate_metadata(archive_root)
    write_request_metadata(
        layout["metadata"],
        {
            "mode": "directory",
            "input_path": os.path.realpath(args.input_path),
            "archive_id": archive_id,
            "interval": args.interval,
            "copies": args.copies,
            "qemu_memory": args.qemu_memory or "auto",
            "max_k": args.max_k,
            "resume_after": args.resume_after,
            "max_workers": args.max_workers,
            "common_suffix": common_suffix or "",
            "workloads": [entry["name"] for entry in entries],
            "virtualized": args.virtualized,
            "virtual_start_marker": args.virtual_start_marker if args.virtualized else "",
            "virtual_stop_marker": args.virtual_stop_marker if args.virtualized else "",
            "virtual_max_instr": args.virtual_max_instr or "",
        },
        filename="batch_request.yaml",
    )

    print(f"Batch size: {len(entries)}", flush=True)
    print(f"Archive: {archive_id}", flush=True)
    print(f"Archive root: {archive_root}", flush=True)
    print(f"Max workers: {args.max_workers}", flush=True)
    print(f"Copies: {args.copies}", flush=True)
    if args.copies > 1:
        print(f"QEMU memory: {args.qemu_memory or 'auto (from DTB)'}",
              flush=True)
    if args.max_k is not None:
        print(f"Max k override: {args.max_k}", flush=True)
    if common_suffix:
        print(f"Derived common suffix: {common_suffix}", flush=True)

    results = []
    failures = []
    requests_dir = os.path.join(layout["metadata"], "requests")
    os.makedirs(requests_dir, exist_ok=True)

    with concurrent.futures.ThreadPoolExecutor(
            max_workers=args.max_workers) as executor:
        future_to_entry = {}
        for index, entry in enumerate(entries):
            cpu_bind, mem_bind = get_worker_bindings(index)
            print(
                f"=== [{index + 1}/{len(entries)}] Checkpointing {entry['name']} from {entry['bin']} (cpu={cpu_bind}, mem={mem_bind}) ===",
                flush=True,
            )
            future = executor.submit(run_workload,
                                     bin_path=entry["bin"],
                                     workload_name=entry["name"],
                                     archive_root=archive_root,
                                     interval=args.interval,
                                     copies=args.copies,
                                     qemu_memory=args.qemu_memory,
                                     max_k=args.max_k,
                                     resume_after=args.resume_after,
                                     cpu_bind=cpu_bind,
                                     mem_bind=mem_bind,
                                     metadata_dir=requests_dir,
                                     generate_metadata=False,
                                     virtualized=args.virtualized,
                                     virtual_start_marker=args.virtual_start_marker,
                                     virtual_stop_marker=args.virtual_stop_marker,
                                     virtual_max_instr=args.virtual_max_instr)
            future_to_entry[future] = entry

        for future in concurrent.futures.as_completed(future_to_entry):
            entry = future_to_entry[future]
            try:
                results.append(future.result())
            except Exception as exc:
                failures.append({"name": entry["name"], "error": str(exc)})

    if failures:
        print("Batch failures:", flush=True)
        for failure in failures:
            print(f"- {failure['name']}: {failure['error']}", flush=True)
        return 1

    print("[Metadata] start workload=batch", flush=True)
    generate_checkpoint_metadata(
        archive_root=archive_root,
        workloads=[entry["name"] for entry in entries],
        times=[1, 1, 1],
        ids=[0, 0, 0],
    )
    print("[Metadata] done workload=batch", flush=True)

    print("Batch summary:", flush=True)
    for result in results:
        suffix = ", skipped=complete" if result.get("skipped") else ""
        print(
            f"- {result['name']}: archive={result['archive_id']}, checkpoints={result['checkpoint_count']}, dir={result['checkpoint_dir']}{suffix}",
            flush=True,
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
