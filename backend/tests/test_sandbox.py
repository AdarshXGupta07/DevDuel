"""The attack suite.

Every test here must FAIL from the submission's point of view and SUCCEED from ours:
a clean, structured, non-hanging result, with no container left behind.

These need Docker and the runner images:

    docker build -f docker/runner/Dockerfile.python -t devduel-runner:py312 docker/runner
    pytest tests/test_sandbox.py -v
"""

import asyncio
import os
import subprocess

import pytest

from app.services.sandbox import run_in_sandbox

pytestmark = pytest.mark.docker


def _docker_state() -> tuple[bool, str]:
    """Is the sandbox testable, and if not, exactly why?

    Returns a specific reason rather than a blanket "unavailable" — the difference
    between "Docker Desktop is still booting" and "you never built the image" is the
    whole diagnosis, and a vague skip message sent this exact investigation the long way
    round once already.
    """
    try:
        daemon = subprocess.run(
            ["docker", "version", "--format", "{{.Server.Version}}"],
            capture_output=True,
            timeout=60,
        )
        if daemon.returncode != 0:
            return False, (
                "Docker daemon is not responding — start Docker Desktop and wait for "
                "'Engine running'"
            )

        image = subprocess.run(
            ["docker", "image", "inspect", IMAGE], capture_output=True, timeout=60
        )
        if image.returncode != 0:
            return False, (
                f"image {IMAGE} not built — run: docker build -f "
                f"docker/runner/Dockerfile.python -t {IMAGE} docker/runner"
            )
        return True, ""
    except FileNotFoundError:
        return False, "docker executable not found on PATH"
    except subprocess.TimeoutExpired:
        return False, "Docker did not answer within 60s (daemon may still be starting)"


IMAGE = "devduel-runner:py312"
DOCKER_OK, DOCKER_REASON = _docker_state()

# A security suite that silently skips is worse than one that fails: "13 skipped" exits
# 0 and reads as success. Set DEVDUEL_REQUIRE_DOCKER=1 in CI so an unrun sandbox suite
# is a hard failure rather than a green tick.
if not DOCKER_OK and os.environ.get("DEVDUEL_REQUIRE_DOCKER") == "1":
    raise RuntimeError(f"DEVDUEL_REQUIRE_DOCKER=1 but the sandbox is untestable: {DOCKER_REASON}")

requires_docker = pytest.mark.skipif(not DOCKER_OK, reason=DOCKER_REASON)


@requires_docker
async def test_happy_path_still_works():
    """Verify last in spirit, first in file: hardening must not break correct code."""
    result = await run_in_sandbox("print(21 * 2)", stdin="")
    assert result.status == "ok"
    assert result.exit_code == 0
    assert result.stdout.strip() == "42"


@requires_docker
async def test_stdin_is_delivered():
    result = await run_in_sandbox("import sys; print(sys.stdin.read().strip().upper())", stdin="hi")
    assert result.stdout.strip() == "HI"


@requires_docker
async def test_infinite_loop_times_out():
    result = await run_in_sandbox("while True: pass", timeout_seconds=3)
    assert result.status == "timeout"


@requires_docker
async def test_no_network_access():
    code = (
        "import urllib.request\n"
        "try:\n"
        "    urllib.request.urlopen('http://example.com', timeout=3)\n"
        "    print('NETWORK_REACHED')\n"
        "except Exception as e:\n"
        "    print('BLOCKED')\n"
    )
    result = await run_in_sandbox(code, timeout_seconds=10)
    assert "NETWORK_REACHED" not in result.stdout


@requires_docker
async def test_filesystem_is_read_only():
    code = (
        "try:\n"
        "    open('/box/evil.txt', 'w').write('x')\n"
        "    print('WROTE')\n"
        "except OSError:\n"
        "    print('READONLY')\n"
    )
    result = await run_in_sandbox(code)
    assert "WROTE" not in result.stdout


@requires_docker
async def test_cannot_see_host_application_files():
    code = (
        "import os\n"
        "print(sorted(os.listdir('/box')))\n"
        "print('ENV' if os.path.exists('/box/.env') else 'NO_ENV')\n"
    )
    result = await run_in_sandbox(code)
    assert "NO_ENV" in result.stdout
    assert "main.py" in result.stdout  # only the submission itself


@requires_docker
async def test_no_secrets_in_environment():
    code = "import os; print([k for k in os.environ if 'SUPABASE' in k or 'JWT' in k])"
    result = await run_in_sandbox(code)
    assert result.stdout.strip() == "[]"


@requires_docker
async def test_memory_balloon_is_killed():
    result = await run_in_sandbox("x = 'a' * (10 ** 10)", timeout_seconds=20)
    assert result.status in ("oom", "timeout")
    assert result.exit_code != 0 or result.status != "ok"


@requires_docker
async def test_fork_bomb_is_contained():
    code = (
        "import os\n"
        "try:\n"
        "    while True:\n"
        "        os.fork()\n"
        "except Exception:\n"
        "    print('LIMITED')\n"
    )
    result = await run_in_sandbox(code, timeout_seconds=10)
    assert result.status in ("ok", "timeout", "oom")


@requires_docker
async def test_output_flood_does_not_eat_our_memory():
    """10MB, not 100MB.

    The original 100MB version proved nothing extra — the cap is 64KB, so anything past
    a few hundred KB exercises the same code path — but it pushed Docker Desktop on WSL2
    hard enough to take the daemon (and the whole test run) down with it. A test that
    destabilises the machine is not a better test.
    """
    result = await run_in_sandbox("print('x' * (10 ** 7))", timeout_seconds=20)
    assert result.status in ("output_limit", "timeout")
    assert len(result.stdout) <= 64 * 1024 + 1


@requires_docker
async def test_runs_as_non_root():
    result = await run_in_sandbox("import os; print(os.getuid())")
    assert result.stdout.strip() == "10001"


@requires_docker
async def test_no_container_is_left_behind():
    await run_in_sandbox("while True: pass", timeout_seconds=2)
    await asyncio.sleep(1)
    out = subprocess.run(
        ["docker", "ps", "-a", "--filter", "name=devduel-", "--format", "{{.Names}}"],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert out.stdout.strip() == ""


# --------------------------------------------------------------------- compiled
#
# C++ and Java compile inside the container, which needs an executable /tmp. That is a
# real weakening of the sandbox (a submission can write and run a binary), so the
# isolation that still must hold is re-tested here rather than assumed from Python.


def _image_present(tag: str) -> bool:
    try:
        return (
            subprocess.run(["docker", "image", "inspect", tag], capture_output=True, timeout=60)
            .returncode
            == 0
        )
    except Exception:  # noqa: BLE001
        return False


needs_cpp = pytest.mark.skipif(
    not (DOCKER_OK and _image_present("devduel-runner:cpp13")),
    reason="devduel-runner:cpp13 not built",
)
needs_java = pytest.mark.skipif(
    not (DOCKER_OK and _image_present("devduel-runner:java21")),
    reason="devduel-runner:java21 not built",
)

DOUBLE_CPP = "#include <bits/stdc++.h>\nint main(){long long n;std::cin>>n;std::cout<<n*2;}"
DOUBLE_JAVA = (
    "import java.util.*;\npublic class Main{public static void main(String[] a){"
    "Scanner s=new Scanner(System.in);System.out.print(s.nextLong()*2);}}"
)


@needs_cpp
async def test_cpp_compiles_and_runs():
    result = await run_in_sandbox(DOUBLE_CPP, language="cpp", stdin="21", timeout_seconds=30)
    assert result.status == "ok", result.stderr
    assert result.stdout.strip() == "42"


@needs_cpp
async def test_cpp_compile_error_is_not_a_runtime_error():
    """A player who wrote invalid code must not be told their program crashed."""
    result = await run_in_sandbox("int main(){ not c++ }", language="cpp", timeout_seconds=30)
    assert result.status == "compile_error"
    assert result.stderr.strip()


@needs_cpp
async def test_cpp_still_has_no_network():
    """The executable /tmp must not have bought a submission anything else."""
    code = (
        "#include <cstdlib>\n#include <cstdio>\n"
        'int main(){ int r = system("curl -s -m 3 http://example.com > /dev/null 2>&1");'
        ' printf("%s", r == 0 ? "REACHED" : "BLOCKED"); }'
    )
    result = await run_in_sandbox(code, language="cpp", timeout_seconds=30)
    assert "REACHED" not in result.stdout


@needs_cpp
async def test_cpp_cannot_write_to_box():
    code = (
        "#include <cstdio>\n"
        'int main(){ FILE* f = fopen("/box/evil.txt","w");'
        ' printf("%s", f ? "WROTE" : "READONLY"); }'
    )
    result = await run_in_sandbox(code, language="cpp", timeout_seconds=30)
    assert "WROTE" not in result.stdout


@needs_java
async def test_java_compiles_and_runs():
    result = await run_in_sandbox(DOUBLE_JAVA, language="java", stdin="21", timeout_seconds=40)
    assert result.status == "ok", result.stderr
    assert result.stdout.strip() == "42"


@needs_java
async def test_java_compile_error_is_not_a_runtime_error():
    result = await run_in_sandbox(
        "public class Main { oops }", language="java", timeout_seconds=40
    )
    assert result.status == "compile_error"


@requires_docker
async def test_concurrent_submissions_do_not_deadlock():
    results = await asyncio.gather(*(run_in_sandbox(f"print({i})") for i in range(8)))
    assert [r.stdout.strip() for r in results] == [str(i) for i in range(8)]
