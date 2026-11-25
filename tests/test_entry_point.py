"""Check that a fresh checkout can run the package."""

import subprocess
import sys
import unittest


class EntryPointTest(unittest.TestCase):
    def test_module_runs(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "echelon"],
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertIn("Result:", result.stdout)


if __name__ == "__main__":
    unittest.main()
