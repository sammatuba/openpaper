#!/usr/bin/env python3
"""Run required integration suites on the socket-only disposable test cluster.

The default creates /tmp/openpaper-pg-transaction-test, refuses to reuse any
existing directory/socket, and stops/removes only the cluster it created.
--run-existing explicitly runs against an already-started cluster without
stopping or deleting it. Every test retains its exact URL/directory/TCP guards.
No application .env, configured database URL, or cloud credential is inherited.
"""

import argparse
import getpass
import os
from pathlib import Path
import shutil
import signal
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[2]
DATA = Path("/tmp/openpaper-pg-transaction-test")
SOCKET = Path("/tmp/.s.PGSQL.55439")
PORT = "55439"
SUITES = (
    "tests.test_mcp_postgres",
    "tests.test_mcp_import_postgres",
    "tests.test_mcp_project_postgres",
    "tests.test_mcp_project_tools",
    "tests.test_mcp_projects_database",
    "tests.test_mcp_protocol",
    "tests.test_pdf_webhook_postgres",
    "tests.test_table_webhook_postgres",
    "tests.test_google_oauth_state_claim",
    "tests.test_passage_backfill_postgres",
    "tests.test_project_research_brief",
    "tests.test_paper_previews",
    "tests.test_project_investigation",
    "tests.test_project_investigation_postgres",
    "tests.test_project_draft_requests",
)

RUNNER = """
import sys, unittest
loader = unittest.TestLoader()
suite = unittest.TestSuite()
for name in sys.argv[1:]:
    component = loader.loadTestsFromName(name)
    if component.countTestCases() == 0:
        raise SystemExit('Required integration suite contains no tests: ' + name)
    suite.addTests(component)
result = unittest.TextTestRunner(verbosity=2).run(suite)
if result.skipped:
    print('Required integration tests were skipped:', result.skipped, file=sys.stderr)
raise SystemExit(0 if result.wasSuccessful() and not result.skipped else 1)
"""


def postgres_bin() -> Path:
    """Find matching initdb/pg_ctl binaries, including Ubuntu's versioned path."""
    installed = shutil.which("pg_config")
    candidates = []
    if installed:
        candidates.append(Path(subprocess.check_output([installed, "--bindir"], text=True).strip()))
    candidates.extend(sorted(Path("/usr/lib/postgresql").glob("*/bin"),
                             key=lambda path: tuple(int(part) for part in path.parent.name.split(".")
                                                    if part.isdigit()), reverse=True))
    installed = shutil.which("initdb")
    if installed:
        candidates.append(Path(installed).parent)
    for candidate in candidates:
        if all((candidate / binary).is_file() for binary in ("initdb", "pg_ctl")):
            return candidate
    raise RuntimeError("PostgreSQL initdb and pg_ctl are required (Ubuntu package: postgresql)")


def test_environment() -> dict:
    """Only process/runtime essentials plus known dummy application settings."""
    environment = {key: os.environ[key] for key in (
        "PATH", "HOME", "LANG", "LC_ALL", "LD_LIBRARY_PATH", "TMPDIR", "SYSTEMROOT"
    ) if key in os.environ}
    environment.update({
        "PYTHON_DOTENV_DISABLED": "1",
        "PYTHONDONTWRITEBYTECODE": "1",
        "PYTHONPATH": str(ROOT / "server"),
        "OPENPAPER_ISOLATED_PG_TEST": "1",
        "DATABASE_URL": f"postgresql://{getpass.getuser()}@/postgres?host=/tmp&port={PORT}",
        "OPENAI_API_KEY": "ci-placeholder",
        "ANTHROPIC_API_KEY": "ci-placeholder",
        "GEMINI_API_KEY": "ci-placeholder",
        "GOOGLE_API_KEY": "ci-placeholder",
        "E2B_API_KEY": "ci-placeholder",
        "FIRECRAWL_API_KEY": "ci-placeholder",
        "AWS_ACCESS_KEY_ID": "ci-placeholder",
        "AWS_SECRET_ACCESS_KEY": "ci-placeholder",
        "AWS_EC2_METADATA_DISABLED": "true",
        "AWS_DEFAULT_REGION": "us-east-1",
        "CLIENT_DOMAIN": "https://papers.example.workers.dev",
        "GOOGLE_CLIENT_ID": "test-client",
        "GOOGLE_CLIENT_SECRET": "test-secret",
        "MCP_JWT_SIGNING_KEY": "testing-signing-key-with-32-characters",
        "MCP_STORAGE_ENCRYPTION_KEY": "MDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDAwMDA=",
        "LANGFUSE_TRACING_ENABLED": "false",
    })
    return environment


def run_suite() -> int:
    return subprocess.run([sys.executable, "-c", RUNNER, *SUITES], cwd="/tmp",
                          env=test_environment(), check=False).returncode


def run(*, existing: bool = False) -> int:
    if existing:
        if DATA.is_symlink() or not DATA.is_dir() or DATA.stat().st_uid != os.getuid():
            raise RuntimeError("Existing cluster must be a real directory owned by this user")
        if not (DATA / "PG_VERSION").is_file() or not SOCKET.exists():
            raise RuntimeError("Existing cluster is not initialized and running on the expected socket")
        # Test-level SQL checks verify data_directory and listen_addresses;
        # this branch never owns, stops, or removes any database directory.
        return run_suite()

    if os.getuid() == 0:
        raise RuntimeError("Run this disposable cluster as a non-root user")
    if DATA.exists() or DATA.is_symlink() or SOCKET.exists():
        raise RuntimeError("Refusing existing test directory/socket; use --run-existing deliberately")
    binaries = postgres_bin()
    DATA.mkdir(mode=0o700)  # Atomic ownership claim; never use exist_ok=True.
    identity = (DATA.stat().st_dev, DATA.stat().st_ino)
    start_attempted = False
    try:
        subprocess.run([str(binaries / "initdb"), "-D", str(DATA), "--auth-local=trust",
                        "--auth-host=reject", "--no-locale", "-E", "UTF8", "-U", getpass.getuser()],
                       check=True, stdout=subprocess.DEVNULL)
        start_attempted = True
        subprocess.run([str(binaries / "pg_ctl"), "-D", str(DATA), "-l", str(DATA / "postgres.log"),
                        "-o", "-F -h '' -k /tmp -p " + PORT, "-w", "start"], check=True)
        return run_suite()
    finally:
        if DATA.is_symlink() or not DATA.is_dir() or (DATA.stat().st_dev, DATA.stat().st_ino) != identity:
            raise RuntimeError("Cluster directory ownership changed; refusing cleanup")
        if start_attempted and (DATA / "postmaster.pid").exists():
            subprocess.run([str(binaries / "pg_ctl"), "-D", str(DATA), "-m", "fast", "-w", "stop"],
                           check=True)
        # A failed stop raises above; leave its files intact for inspection.
        shutil.rmtree(DATA)


def main(argv=None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-existing", action="store_true",
                        help="Run tests only; do not stop or remove an existing cluster")
    args = parser.parse_args(argv)
    def interrupted(signum, _frame):
        raise SystemExit(128 + signum)
    previous = {signum: signal.signal(signum, interrupted) for signum in (signal.SIGTERM, signal.SIGINT)}
    try:
        return run(existing=args.run_existing)
    finally:
        for signum, handler in previous.items():
            signal.signal(signum, handler)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except (RuntimeError, subprocess.CalledProcessError) as error:
        print(str(error), file=sys.stderr)
        raise SystemExit(1)
