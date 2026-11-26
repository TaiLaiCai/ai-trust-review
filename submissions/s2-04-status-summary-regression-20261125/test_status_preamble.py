"""Replay only the recorded functional response shape with synthetic data."""
import argparse
from hashlib import sha256
import importlib.util
import json
from pathlib import Path

RUN = "10000000-0000-4000-8000-000000000001"
ACK = "S1_READY_fixture_only"
FILES = {"/fixture/role.txt": "mock role\n", "/fixture/skill.txt": "mock skill\n"}


def load_parser(path):
    spec = importlib.util.spec_from_file_location("session_gate_fixture", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.READS = {path: sha256(value.encode()).hexdigest() for path, value in FILES.items()}
    return module


def fixture(progress):
    records = [{"type": "thread.started", "thread_id": RUN}]
    if progress:
        records.append({"type": "item.completed", "item": {"type": "agent_message", "text": "Preparing to read two files."}})
    for path, value in FILES.items():
        records.append({"type": "item.completed", "item": {
            "type": "command_execution", "command": f"/usr/bin/cat {path}",
            "status": "completed", "exit_code": 0, "aggregated_output": value,
        }})
    records.extend([
        {"type": "item.completed", "item": {"type": "agent_message", "text": ACK}},
        {"type": "turn.completed"},
    ])
    return b"".join(json.dumps(row).encode() + b"\n" for row in records)


def main():
    cli = argparse.ArgumentParser()
    cli.add_argument("source", type=Path)
    args = cli.parse_args()
    parser = load_parser(args.source)
    assert parser.capture_first_turn(fixture(False), ACK) == RUN
    print("baseline: accepted")
    try:
        actual = parser.capture_first_turn(fixture(True), ACK)
    except ValueError as exc:
        if str(exc) != "preflight acknowledgement differs":
            raise
        print(f"preamble: rejected ({exc})")
        return 1
    assert actual == RUN
    print("preamble: accepted")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
