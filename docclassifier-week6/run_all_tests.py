#!/usr/bin/env python3
"""
Complete CI Test Suite - Document Classifier
Run all tests locally before pushing to GitHub:
1. Lint (Ruff)
2. Type-check (MyPy)
3. Golden-set regression test (64 images)
4. Smoke test (full stack: SFTP → inference → API)

Usage:
    python run_all_tests.py                          # Run all tests
    python run_all_tests.py --skip-lint              # Skip lint check
    python run_all_tests.py --skip-golden            # Skip golden-set test
    python run_all_tests.py --skip-smoke             # Skip smoke test
    python run_all_tests.py --only-smoke             # Run only smoke test
"""

import subprocess
import sys
import time
import json
import argparse
import os
from pathlib import Path
from typing import Tuple, Optional
import urllib.request
import urllib.error

# Force UTF-8 encoding on Windows
os.environ['PYTHONIOENCODING'] = 'utf-8'


class Colors:
    """ANSI color codes for terminal output"""
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    RED = "\033[91m"
    YELLOW = "\033[93m"
    RESET = "\033[0m"
    BOLD = "\033[1m"


class TestRunner:
    """Run all CI tests locally"""

    def __init__(self, skip_lint=False, skip_type_check=False, skip_golden=False, skip_smoke=False):
        self.skip_lint = skip_lint
        self.skip_type_check = skip_type_check
        self.skip_golden = skip_golden
        self.skip_smoke = skip_smoke
        self.tests_passed = 0
        self.tests_failed = 0
        self.tests_skipped = 0
        self.start_time = time.time()
        self.project_dir = Path(__file__).parent

    def write_section(self, title: str):
        """Print a section header"""
        print(f"\n{Colors.CYAN}{'=' * 80}")
        print(f"  {title}")
        print(f"{'=' * 80}{Colors.RESET}\n")

    def write_pass(self, message: str):
        """Print a passing test"""
        print(f"{Colors.GREEN}✅ {message}{Colors.RESET}")
        self.tests_passed += 1

    def write_fail(self, message: str):
        """Print a failing test"""
        print(f"{Colors.RED}❌ {message}{Colors.RESET}")
        self.tests_failed += 1

    def write_skip(self, message: str):
        """Print a skipped test"""
        print(f"{Colors.YELLOW}⊘ {message}{Colors.RESET}")
        self.tests_skipped += 1

    def run_command(self, cmd: str, show_output=False) -> Tuple[int, str]:
        """Run a shell command and return exit code and output"""
        try:
            result = subprocess.run(
                cmd,
                shell=True,
                cwd=self.project_dir,
                capture_output=True,
                text=True,
                encoding='utf-8',
                errors='replace',
                timeout=300,
            )
            if show_output and result.stdout:
                print(result.stdout)
            if result.stderr and show_output:
                print(result.stderr)
            return result.returncode, result.stdout + result.stderr
        except subprocess.TimeoutExpired:
            return 1, "Command timed out"
        except Exception as e:
            return 1, str(e)

    def test_lint(self):
        """Test 1: Lint with Ruff"""
        self.write_section("Test 1: LINT (Ruff)")

        if self.skip_lint:
            self.write_skip("Lint check skipped")
            return

        print(f"{Colors.CYAN}Checking code style with Ruff...{Colors.RESET}")
        exit_code, output = self.run_command(
            "uv run ruff check app/ streamlit-dashboard.py",
            show_output=True,
        )

        if exit_code == 0:
            self.write_pass("Lint check passed (no style errors)")
        else:
            self.write_fail("Lint check failed (see errors above)")

    def test_type_check(self):
        """Test 2: Type-check with MyPy"""
        self.write_section("Test 2: TYPE-CHECK (MyPy)")

        if self.skip_type_check:
            self.write_skip("Type-check skipped")
            return

        print(f"{Colors.CYAN}Type-checking with MyPy...{Colors.RESET}")
        exit_code, output = self.run_command(
            "uv run mypy app/ --ignore-missing-imports --config-file=mypy.ini",
            show_output=True,
        )

        if exit_code == 0:
            self.write_pass("Type-check passed (no type errors)")
        else:
            error_count = output.count("error:")
            self.write_fail(f"Type-check found {error_count} error(s) (see above)")

    def test_golden_set(self):
        """Test 3: Golden-set regression test"""
        self.write_section("Test 3: GOLDEN-SET (Model Regression - 64 images)")

        if self.skip_golden:
            self.write_skip("Golden-set test skipped")
            return

        print(f"{Colors.CYAN}Running 64-image regression test...{Colors.RESET}")
        print(f"{Colors.CYAN}This loads the model and verifies 64 golden images...{Colors.RESET}\n")

        exit_code, output = self.run_command("uv sync", show_output=False)
        exit_code, output = self.run_command(
            "uv run python -m app.classifier.eval.golden",
            show_output=True,
        )

        if exit_code == 0:
            self.write_pass("Golden-set test passed (all 64 images matched)")
        else:
            self.write_fail("Golden-set test failed (image predictions don't match)")

    def test_smoke(self):
        """Test 4: Smoke test (full stack)"""
        self.write_section("Test 4: SMOKE TEST (Full Stack: SFTP → Inference → API)")

        if self.skip_smoke:
            self.write_skip("Smoke test skipped")
            return

        print(f"{Colors.CYAN}Starting full stack and running end-to-end test...{Colors.RESET}\n")

        # Step 1: Start services
        print(f"{Colors.YELLOW}[Step 1/5] Starting services...{Colors.RESET}")
        exit_code, _ = self.run_command(
            "docker compose up --build --wait --wait-timeout 180 api worker sftp-ingest",
            show_output=False,
        )

        if exit_code != 0:
            self.write_fail("Failed to start services")
            return

        print(f"{Colors.GREEN}✓ Services started{Colors.RESET}")

        # Step 2: Seed admin
        print(f"{Colors.YELLOW}[Step 2/5] Seeding admin user...{Colors.RESET}")
        exit_code, _ = self.run_command(
            "docker compose run --rm --no-TTY --entrypoint python api scripts/seed_admin.py",
            show_output=False,
        )

        if exit_code != 0:
            self.write_fail("Failed to seed admin")
            self.cleanup_docker()
            return

        print(f"{Colors.GREEN}✓ Admin seeded{Colors.RESET}")

        # Step 3: Login
        print(f"{Colors.YELLOW}[Step 3/5] Logging in as admin...{Colors.RESET}")
        exit_code, login_output = self.run_command(
            'curl -s -X POST "http://localhost:8000/auth/jwt/login" '
            '-H "Content-Type: application/x-www-form-urlencoded" '
            '-d "username=admin@example.com&password=Admin1234!"',
            show_output=False,
        )

        try:
            login_json = json.loads(login_output)
            token = login_json.get("access_token")
        except json.JSONDecodeError:
            token = None

        if not token:
            self.write_fail("Login failed")
            self.cleanup_docker()
            return

        print(f"{Colors.GREEN}✓ Login successful{Colors.RESET}")

        # Step 4: Upload TIFF
        print(f"{Colors.YELLOW}[Step 4/5] Uploading TIFF to SFTP...{Colors.RESET}")
        tif_path = "app/classifier/eval/golden_images/memo_000103.tif"
        exit_code, _ = self.run_command(
            f'docker compose cp "{tif_path}" "sftp:/home/scanner/upload/smoke_test.tif"',
            show_output=False,
        )

        if exit_code != 0:
            self.write_fail("Failed to upload TIFF")
            self.cleanup_docker()
            return

        print(f"{Colors.GREEN}✓ TIFF uploaded{Colors.RESET}")

        # Step 5: Wait for prediction
        print(f"{Colors.YELLOW}[Step 5/5] Waiting for prediction (max 30 seconds)...{Colors.RESET}")
        found = False

        for i in range(1, 31):
            time.sleep(1)

            try:
                url = "http://localhost:8000/predictions/recent?limit=10"
                headers = {"Authorization": f"Bearer {token}"}
                req = urllib.request.Request(url, headers=headers)
                with urllib.request.urlopen(req, timeout=5) as response:
                    pred_data = json.loads(response.read().decode())

                    if isinstance(pred_data, list) and len(pred_data) > 0:
                        pred = pred_data[0]
                        print(
                            f"{Colors.GREEN}✓ Prediction appeared after {i}s{Colors.RESET}"
                        )
                        print(
                            f"  {Colors.CYAN}Label: {pred.get('predicted_class')}{Colors.RESET}"
                        )
                        print(
                            f"  {Colors.CYAN}Confidence: {pred.get('confidence')}{Colors.RESET}"
                        )
                        found = True
                        break
            except (urllib.error.URLError, json.JSONDecodeError, KeyError):
                pass

        # Cleanup
        print(f"\n{Colors.YELLOW}Cleaning up...{Colors.RESET}")
        self.cleanup_docker()

        if found:
            self.write_pass("Smoke test passed (full stack working)")
        else:
            self.write_fail("Smoke test failed (no prediction within 30s)")

    def cleanup_docker(self):
        """Clean up Docker resources"""
        self.run_command("docker compose down --volumes", show_output=False)

    def print_summary(self):
        """Print test summary"""
        self.write_section("TEST SUMMARY")

        total = self.tests_passed + self.tests_failed + self.tests_skipped
        elapsed = time.time() - self.start_time

        print(f"{Colors.CYAN}Results:{Colors.RESET}")
        print(
            f"  {Colors.GREEN}✅ Passed: {self.tests_passed}{Colors.RESET}"
        )
        print(f"  {Colors.RED}❌ Failed: {self.tests_failed}{Colors.RESET}")
        print(
            f"  {Colors.YELLOW}⊘ Skipped: {self.tests_skipped}{Colors.RESET}"
        )
        print(f"  {Colors.RESET}Total: {total}")
        print(f"\n{Colors.RESET}Time: {elapsed:.1f}s")

        if self.tests_failed == 0:
            print(
                f"\n{Colors.GREEN}{Colors.BOLD}✅✅✅ ALL TESTS PASSED ✅✅✅{Colors.RESET}\n"
            )
            return 0
        else:
            print(
                f"\n{Colors.RED}❌ {self.tests_failed} TEST(S) FAILED{Colors.RESET}\n"
            )
            return 1

    def run_all(self):
        """Run all tests"""
        print(f"{Colors.CYAN}{Colors.BOLD}Document Classifier - Complete Test Suite{Colors.RESET}")
        print(f"{Colors.CYAN}Working directory: {self.project_dir}{Colors.RESET}\n")

        self.test_lint()
        self.test_type_check()
        self.test_golden_set()
        self.test_smoke()

        return self.print_summary()


def main():
    """Main entry point"""
    parser = argparse.ArgumentParser(
        description="Run CI tests for Document Classifier",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python run_all_tests.py                    # Run all tests
  python run_all_tests.py --skip-lint        # Skip lint check
  python run_all_tests.py --only-smoke       # Run only smoke test
  python run_all_tests.py --skip-golden      # Skip golden-set test
        """,
    )

    parser.add_argument(
        "--skip-lint",
        action="store_true",
        help="Skip lint check",
    )
    parser.add_argument(
        "--skip-type-check",
        action="store_true",
        help="Skip type-check",
    )
    parser.add_argument(
        "--skip-golden",
        action="store_true",
        help="Skip golden-set test",
    )
    parser.add_argument(
        "--skip-smoke",
        action="store_true",
        help="Skip smoke test",
    )
    parser.add_argument(
        "--only-smoke",
        action="store_true",
        help="Run only smoke test",
    )

    args = parser.parse_args()

    # Handle --only-smoke
    if args.only_smoke:
        args.skip_lint = True
        args.skip_type_check = True
        args.skip_golden = True

    runner = TestRunner(
        skip_lint=args.skip_lint,
        skip_type_check=args.skip_type_check,
        skip_golden=args.skip_golden,
        skip_smoke=args.skip_smoke,
    )

    exit_code = runner.run_all()
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
