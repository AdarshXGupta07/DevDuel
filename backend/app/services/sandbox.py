"""The box untrusted code runs in.

Every safety property here is a flag, not a default — a bare `docker run` is a
convenience feature, not a sandbox. See docs/threat-model.md for the attack each of
these controls exists to stop.

Known limitation: containers share the host kernel, so a kernel-level escape is not
defended against here. That is the accepted tradeoff of ADR-0019; the second line of
defense is that the judge host holds no secrets and no production database access.
"""

import asyncio
import logging
import shutil
import tempfile
import uuid
from dataclasses import dataclass
from pathlib import Path

from app.config import settings

logger = logging.getLogger(__name__)

LANGUAGES: dict[str, dict] = {
    "python": {
        "image": lambda: settings.judge_image_python,
        "filename": "main.py",
        # -I: isolated mode (ignores env vars and the cwd on sys.path)
        # -B: no .pyc writes, which a read-only filesystem would reject anyway
        "command": ["python", "-I", "-B", "/box/main.py"],
        "label": "Python 3.12",
    },
    "javascript": {
        "image": lambda: settings.judge_image_node,
        "filename": "main.js",
        "command": ["node", "--no-experimental-fetch", "/box/main.js"],
        "label": "JavaScript (Node 22)",
    },
    # --- compiled languages ---------------------------------------------------
    # These compile and run inside one container. That needs an executable /tmp, so
    # the `noexec` flag is dropped for them — a real, deliberate weakening of the
    # sandbox (a submission can now write and execute a binary). Everything else
    # still holds: no network, read-only /box, dropped capabilities, non-root, and
    # the pid/memory/time caps. See ADR-0036.
    "cpp": {
        "image": lambda: settings.judge_image_cpp,
        "filename": "main.cpp",
        "command": [
            "sh",
            "-c",
            # Exit 92 is our sentinel for "failed to compile" — it separates the
            # player writing invalid code from their code crashing at runtime, which
            # are different verdicts and deserve different messages.
            "g++ -O2 -std=c++17 -o /tmp/prog /box/main.cpp 2>/tmp/cc.err "
            "|| { cat /tmp/cc.err >&2; exit 92; }; exec /tmp/prog",
        ],
        "needs_exec_tmp": True,
        "label": "C++17 (GCC)",
    },
    "java": {
        "image": lambda: settings.judge_image_java,
        "filename": "Main.java",
        "command": [
            "sh",
            "-c",
            "cd /tmp && cp /box/Main.java . && javac Main.java 2>/tmp/cc.err "
            "|| { cat /tmp/cc.err >&2; exit 92; }; exec java -XX:+UseSerialGC -Xss64m Main",
        ],
        "needs_exec_tmp": True,
        # A JVM needs materially more headroom than an interpreter, and spawns its
        # own threads — the defaults would fail every correct Java solution.
        "memory_mb": 512,
        "pids_limit": 256,
        "tmp_size_mb": 64,
        "label": "Java 21",
    },
}

COMPILE_ERROR_EXIT = 92

# Never run more than N containers at once, no matter how many players submit. Without
# this, 50 simultaneous submissions is a self-inflicted denial of service.
_slots = asyncio.Semaphore(settings.judge_max_concurrent)


class UnsupportedLanguage(Exception):
    pass


@dataclass
class RunResult:
    status: str  # 'ok' | 'timeout' | 'oom' | 'output_limit' | 'compile_error' | 'system_error'
    exit_code: int | None
    stdout: str
    stderr: str
    duration_ms: int
    stdout_truncated: bool = False
    stderr_truncated: bool = False

    @property
    def ok(self) -> bool:
        return self.status == "ok" and self.exit_code == 0


def supported_languages() -> list[dict]:
    """Ordered for the UI: the two interview defaults first, then the compiled pair."""
    order = ["python", "javascript", "cpp", "java"]
    return [
        {"id": key, "label": LANGUAGES[key].get("label", key)}
        for key in order
        if key in LANGUAGES
    ]


def _docker_args(
    container_name: str, host_dir: Path, image: str, command: list[str], spec: dict
) -> list[str]:
    # Per-language overrides, because one set of limits cannot fit both a Python
    # interpreter and a JVM.
    memory = f"{spec.get('memory_mb', settings.judge_memory_mb)}m"
    pids = spec.get("pids_limit", settings.judge_pids_limit)
    tmp_size = spec.get("tmp_size_mb", 16)
    # `exec` must be stated explicitly: Docker keeps noexec on a tmpfs unless told
    # otherwise, so merely omitting `noexec` leaves a compiled binary unrunnable.
    tmp_flags = "rw,exec,nosuid" if spec.get("needs_exec_tmp") else "rw,noexec,nosuid"

    return [
        "docker", "run",
        "--rm",
        "--interactive",
        "--name", container_name,
        # --- what it can see ---
        "--network", "none",                       # no exfiltration, no fetching solutions
        "--read-only",                             # filesystem is immutable
        "--tmpfs", f"/tmp:{tmp_flags},size={tmp_size}m",  # ...except a small scratch space
        "--volume", f"{host_dir}:/box:ro",         # the submission, read-only
        "--workdir", "/box",
        # --- what it can use ---
        "--memory", memory,
        # Without this, swap is unlimited and the memory cap is decorative.
        "--memory-swap", memory,
        "--cpus", str(settings.judge_cpus),
        "--pids-limit", str(pids),
        # --- what it may ask the kernel to do ---
        "--cap-drop", "ALL",
        "--security-opt", "no-new-privileges",
        "--user", "10001:10001",
        # --- no inherited environment: the app's secrets never cross this line ---
        "--env", "HOME=/tmp",
        "--env", "PYTHONDONTWRITEBYTECODE=1",
        image,
        *command,
    ]


async def _read_capped(stream: asyncio.StreamReader | None, limit: int) -> tuple[bytes, bool]:
    """Read at most `limit` bytes.

    A submission that prints 2GB is not stopped by any Docker flag — the container is
    behaving perfectly, it is *our* process that would die holding the output. So we
    stop reading, and the caller kills the container.
    """
    if stream is None:
        return b"", False
    data = await stream.read(limit + 1)
    if len(data) > limit:
        return data[:limit], True
    return data, False


# Failures that come from the docker CLI itself rather than from the submitted program.
# Told apart by stderr: the container's own stderr is a Python/Node traceback, while
# these are emitted by `docker run` before any code is executed.
_DOCKER_CLI_ERRORS = (
    "failed to connect to the docker api",
    "cannot connect to the docker daemon",
    "error during connect",
    "is the docker daemon running",
    "error response from daemon",
    "no such image",
    "unable to find image",
)


def _is_infrastructure_failure(exit_code: int | None, stderr: str) -> bool:
    """Did *we* fail, or did the submission?

    This distinction is the difference between telling a player "your code crashed" and
    admitting "our judge is down". Getting it wrong means a player loses a ranked duel
    because Docker Desktop stopped — which is exactly what happened while testing.

    125 is docker's own "the run could not be started"; 126/127 mean the command inside
    the image was not executable or not found — all of them our problem, not theirs.
    """
    if exit_code in (125, 126, 127):
        return True
    lowered = stderr.lower()
    return any(marker in lowered for marker in _DOCKER_CLI_ERRORS)


async def _kill_container(name: str) -> None:
    try:
        proc = await asyncio.create_subprocess_exec(
            "docker", "kill", name,
            stdout=asyncio.subprocess.DEVNULL,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await asyncio.wait_for(proc.wait(), timeout=10)
    except Exception:  # noqa: BLE001 — best-effort cleanup, never fails the run
        logger.warning("failed to kill container %s", name, exc_info=True)


async def run_in_sandbox(
    code: str,
    language: str = "python",
    stdin: str = "",
    timeout_seconds: float | None = None,
) -> RunResult:
    if language not in LANGUAGES:
        raise UnsupportedLanguage(f"Language {language!r} is not supported.")

    spec = LANGUAGES[language]
    timeout = timeout_seconds or settings.judge_timeout_seconds
    limit = settings.judge_max_output_bytes
    container_name = f"devduel-{uuid.uuid4().hex[:12]}"

    host_dir = Path(tempfile.mkdtemp(prefix="devduel-box-"))
    (host_dir / spec["filename"]).write_text(code, encoding="utf-8", newline="\n")

    args = _docker_args(container_name, host_dir, spec["image"](), spec["command"], spec)

    async with _slots:
        loop = asyncio.get_running_loop()
        started = loop.time()
        proc = None
        try:
            proc = await asyncio.create_subprocess_exec(
                *args,
                stdin=asyncio.subprocess.PIPE,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )

            async def _drive() -> tuple[bytes, bool, bytes, bool, int | None]:
                if proc.stdin is not None:
                    try:
                        proc.stdin.write(stdin.encode("utf-8"))
                        await proc.stdin.drain()
                    except (BrokenPipeError, ConnectionResetError):
                        pass  # the program exited without reading its input; fine
                    finally:
                        try:
                            proc.stdin.close()
                        except Exception:  # noqa: BLE001
                            pass

                (out, out_cut), (err, err_cut) = await asyncio.gather(
                    _read_capped(proc.stdout, limit),
                    _read_capped(proc.stderr, limit),
                )

                # A program that outran the cap is still writing into a pipe we have
                # stopped draining, so it is blocked and can never exit. Waiting on it
                # here is a guaranteed deadlock — kill the container first, THEN wait.
                # (This is the flood case: we have our evidence, the rest is noise.)
                if out_cut or err_cut:
                    await _kill_container(container_name)

                try:
                    code_ = await asyncio.wait_for(proc.wait(), timeout=15)
                except asyncio.TimeoutError:
                    # Belt and braces: never let a stuck `docker run` client hold the
                    # judge open, whatever the reason.
                    proc.kill()
                    code_ = None
                return out, out_cut, err, err_cut, code_

            try:
                out, out_cut, err, err_cut, exit_code = await asyncio.wait_for(
                    _drive(), timeout=timeout
                )
            except asyncio.TimeoutError:
                # Killing our local `docker run` client is NOT enough — the container
                # keeps burning CPU. Kill it by name, explicitly.
                await _kill_container(container_name)
                if proc.returncode is None:
                    proc.kill()
                    await proc.wait()
                return RunResult(
                    status="timeout",
                    exit_code=None,
                    stdout="",
                    stderr="",
                    duration_ms=int((loop.time() - started) * 1000),
                )

            duration_ms = int((loop.time() - started) * 1000)
            stdout = out.decode("utf-8", errors="replace")
            stderr = err.decode("utf-8", errors="replace")

            if out_cut or err_cut:
                # The container was already killed inside _drive, before the wait.
                return RunResult(
                    status="output_limit",
                    exit_code=exit_code,
                    stdout=stdout,
                    stderr=stderr,
                    duration_ms=duration_ms,
                    stdout_truncated=out_cut,
                    stderr_truncated=err_cut,
                )

            # The judge being unavailable is never the player's fault. Without this the
            # daemon being down surfaced as exit 1 with empty output, which the verdict
            # mapper read as `runtime_error` — a loss for code that never ran.
            if exit_code != 0 and _is_infrastructure_failure(exit_code, stderr):
                logger.error("judge infrastructure failure: %s", stderr.strip()[:300])
                return RunResult(
                    status="system_error",
                    exit_code=exit_code,
                    stdout="",
                    stderr=stderr,
                    duration_ms=duration_ms,
                )

            # Our sentinel from the compile step. "You wrote code that does not build"
            # and "your program crashed" are different failures and read very
            # differently to the player, so they must not collapse into one verdict.
            if exit_code == COMPILE_ERROR_EXIT:
                return RunResult(
                    status="compile_error",
                    exit_code=exit_code,
                    stdout="",
                    stderr=stderr,
                    duration_ms=duration_ms,
                )

            # 137 = 128 + SIGKILL. With --rm we cannot inspect OOMKilled after the fact,
            # and we know it was not our timeout because that path returned above, so
            # attribute it to the memory cap.
            if exit_code == 137:
                return RunResult(
                    status="oom",
                    exit_code=exit_code,
                    stdout=stdout,
                    stderr=stderr,
                    duration_ms=duration_ms,
                )

            return RunResult(
                status="ok",
                exit_code=exit_code,
                stdout=stdout,
                stderr=stderr,
                duration_ms=duration_ms,
            )

        except FileNotFoundError:
            return RunResult(
                status="system_error",
                exit_code=None,
                stdout="",
                stderr="docker executable not found on PATH",
                duration_ms=0,
            )
        except Exception as e:  # noqa: BLE001
            logger.exception("sandbox run failed")
            await _kill_container(container_name)
            return RunResult(
                status="system_error",
                exit_code=None,
                stdout="",
                stderr=f"{type(e).__name__}: {e}",
                duration_ms=int((asyncio.get_running_loop().time() - started) * 1000),
            )
        finally:
            shutil.rmtree(host_dir, ignore_errors=True)


async def docker_available() -> bool:
    try:
        proc = await asyncio.create_subprocess_exec(
            "docker", "version", "--format", "{{.Server.Version}}",
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.DEVNULL,
        )
        await asyncio.wait_for(proc.communicate(), timeout=10)
        return proc.returncode == 0
    except Exception:  # noqa: BLE001
        return False
