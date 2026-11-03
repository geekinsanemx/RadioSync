"""radiosync chirp_client: runs chirp_worker.py in the CHIRP interpreter as a subprocess.

Changelog:
- 0.1.0 (2026-11-01): initial version.
"""

import json
import subprocess
from importlib import resources
from pathlib import Path

from .config import RadiosyncError

WORKER_TIMEOUT_SECONDS = 1800


class ChirpWorkerError(RadiosyncError):
    def __init__(self, message, details=(), log=()):
        lines = [d if isinstance(d, str) else _format_detail(d) for d in details]
        super().__init__(message, lines)
        self.raw_details = list(details)
        self.log = list(log)


def _format_detail(detail: dict) -> str:
    where = []
    if detail.get("number") is not None:
        where.append(f"memory {detail['number']}")
    if detail.get("ref") is not None:
        where.append(str(detail["ref"]))
    if detail.get("index") is not None:
        where.append(f"item {detail['index']}")
    prefix = f"[{', '.join(where)}] " if where else ""
    return prefix + str(detail.get("error", detail))


class ChirpClient:
    def __init__(self, python: Path):
        self.python = Path(python)
        self.worker = Path(str(resources.files("radiosync") / "chirp_worker.py"))

    def call(self, op: str, **payload) -> dict:
        request = json.dumps({"op": op, **payload})
        process = subprocess.run(
            [str(self.python), "-I", "-B", str(self.worker)],
            input=request, capture_output=True, text=True,
            timeout=WORKER_TIMEOUT_SECONDS, check=False)
        try:
            response = json.loads(process.stdout)
        except json.JSONDecodeError as exc:
            raise ChirpWorkerError(
                f"CHIRP worker failed (exit {process.returncode})",
                process.stderr.strip().splitlines()[-15:]) from exc
        if not response.get("ok"):
            raise ChirpWorkerError(response.get("error", "CHIRP worker error"),
                                   response.get("details", []), response.get("log", []))
        return response["result"]

    def version(self) -> str:
        return self.call("version")["chirp_version"]

    def inspect(self, path: Path) -> dict:
        return self.call("inspect", path=str(path))

    def read_channels(self, path: Path) -> dict:
        return self.call("read_channels", path=str(path))

    def normalize(self, memories: list[dict]) -> list[dict]:
        return self.call("normalize", memories=memories)["memories"]

    def write_csv(self, path: Path, memories: list[dict]) -> dict:
        return self.call("write_csv", path=str(path), memories=memories)

    def build(self, **request) -> dict:
        return self.call("build", **request)

    def verify(self, path: Path, identity: dict, expected: dict) -> dict:
        return self.call("verify", path=str(path), identity=identity, expected=expected)

    def settings_diff(self, template: Path, image: Path) -> list[dict]:
        return self.call("settings_diff", template=str(template),
                         image=str(image))["differences"]
