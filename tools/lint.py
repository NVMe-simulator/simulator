"""Run the same C++ checks locally, in pre-commit, and in CI."""

import argparse
import json
import os
from pathlib import Path
import re
import shlex
import shutil
import subprocess
import sys

from check_records import check_records


ROOT = Path(__file__).resolve().parents[1]
EXTENSIONS = {".cc", ".cpp", ".cxx", ".h", ".hh", ".hpp", ".hxx"}
SOURCES = {".cc", ".cpp", ".cxx"}
EXCLUDED = {".git", ".venv", ".cache", "build", "third_party", "vendor", "__pycache__"}


def source_files():
    files = []
    for directory, dirs, names in os.walk(ROOT):
        dirs[:] = [d for d in dirs if d not in EXCLUDED and not d.startswith("cmake-build-")]
        files.extend(
            Path(directory) / name for name in names if Path(name).suffix in EXTENSIONS
        )
    return sorted(files)


def executable(name):
    local = Path(sys.executable).parent / name
    found = str(local) if local.is_file() else shutil.which(name)
    if not found:
        raise RuntimeError(f"Missing {name}; install requirements-dev.txt into .venv")
    return found


def system_includes():
    # libclang wheels do not contain C++ standard library headers. Ask the host
    # compiler for its search paths (also handles the macOS SDK).
    compiler = shlex.split(os.environ.get("CXX", "c++"))
    result = subprocess.run(
        [*compiler, "-E", "-x", "c++", "-", "-v"],
        input="", text=True, capture_output=True, check=True,
    )
    paths = []
    collecting = False
    for line in result.stderr.splitlines():
        if "#include <...> search starts here:" in line:
            collecting = True
        elif "End of search list." in line:
            break
        elif collecting:
            path = line.strip()
            if path.endswith(" (framework directory)"):
                paths.extend(["-iframework", path.removesuffix(" (framework directory)")])
            else:
                paths.extend(["-isystem", path])
    if not paths:
        raise RuntimeError("Cannot discover C++ include paths; set CXX to clang++ or g++")
    return paths


def database_arguments(entry):
    """Strip driver-only inputs while preserving the build's parsing flags."""
    directory = Path(entry["directory"])
    source = (directory / entry["file"]).resolve()
    argv = entry.get("arguments") or shlex.split(entry["command"])
    args = ["-working-directory=" + str(directory)]
    skip = False
    for arg in argv[1:]:
        if skip:
            skip = False
        elif arg in {"-o", "-MF", "-MT", "-MQ", "-MJ", "--serialize-diagnostics"}:
            skip = True
        elif arg in {"-c", "-MD", "-MMD", "-MP"}:
            continue
        elif not arg.startswith("-") and (directory / arg).resolve() == source:
            continue
        else:
            args.append(arg)
    return args


def run(command):
    print("+ " + shlex.join(map(str, command)), flush=True)
    return subprocess.run(command, cwd=ROOT).returncode != 0


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--format", action="store_true", help="Only apply clang-format")
    parser.add_argument("--build-dir", type=Path, help="Directory with compile_commands.json")
    options = parser.parse_args()
    files = source_files()
    if not files:
        print("No C++ files yet; configuration is ready.")
        return 0
    relative_files = [str(p.relative_to(ROOT)) for p in files]
    formatter = executable("clang-format")
    if options.format:
        return int(run([formatter, "-i", *relative_files]))
    failed = run([formatter, "--dry-run", "--Werror", *relative_files])
    failed |= run([executable("cpplint"), "--root=.", *relative_files])
    tidy = executable("clang-tidy")
    failed |= run([tidy, "--verify-config"])
    header_filter = "(^|/)(" + "|".join(re.escape(p) for p in relative_files) + ")$"
    tidy_command = [tidy, "--header-filter=" + header_filter]

    build_dir = options.build_dir
    if build_dir is None:
        build_dir = next(
            (p for p in [ROOT / "build", ROOT] if (p / "compile_commands.json").is_file()),
            None,
        )
    entries = {}
    if build_dir is not None:
        build_dir = build_dir.resolve()
        for entry in json.loads((build_dir / "compile_commands.json").read_text()):
            path = (Path(entry["directory"]) / entry["file"]).resolve()
            entries.setdefault(path, []).append(entry)

    includes = system_includes()
    # Wheel binaries also need the host SDK paths when using a build database.
    tidy_command += ["--extra-arg=" + arg for arg in includes]
    # Headers without their own build command use the project's C++23 standard.
    fallback = ["-x", "c++", "-std=c++23", "-I" + str(ROOT), *includes]
    for path in files:
        commands = entries.get(path)
        if commands:
            failed |= run([*tidy_command, str(path), "-p", str(build_dir)])
            argument_sets = [database_arguments(entry) + includes for entry in commands]
        elif build_dir is not None and path.suffix in SOURCES:
            print(f"{path}: missing compile command; regenerate the build database", file=sys.stderr)
            failed = True
            continue
        else:
            # Headers are also parsed on their own: Google requires self-contained
            # headers. In database mode they are additionally checked in each TU.
            failed |= run([*tidy_command, str(path), "--", *fallback])
            argument_sets = [fallback]
        for args in argument_sets:
            errors = check_records(path, args, files)
            for error in errors:
                print(error, file=sys.stderr)
            failed |= bool(errors)
    return int(failed)


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, RuntimeError, ValueError, subprocess.CalledProcessError) as error:
        print(f"lint: {error}", file=sys.stderr)
        sys.exit(1)
