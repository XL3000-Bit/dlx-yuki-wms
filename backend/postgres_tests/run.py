"""Explicit standalone runner. No discovery or application import on import."""
import sys
import unittest
from pathlib import Path


class SafeResult(unittest.TextTestResult):
    def _safe(self, err):
        exc = err[1]
        return type(exc).__name__ + "; details withheld (may contain SQL parameters)"

    def _exc_info_to_string(self, err, test):
        return self._safe(err)


def main():
    from guard import Refused, Target

    try:
        target = Target.from_environment()
        # Verify identity before importing application logic or running fixtures.
        connection = target.connect()
        connection.close()
    except Refused as exc:
        print(str(exc), file=sys.stderr)
        return 2
    sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
    from test_structure import StructureTests
    from test_readiness import ReadinessTests

    suite = unittest.TestSuite()
    for cls in (StructureTests, ReadinessTests):
        cls.target = target
        suite.addTests(unittest.defaultTestLoader.loadTestsFromTestCase(cls))
    result = unittest.TextTestRunner(verbosity=2, resultclass=SafeResult).run(suite)
    return 0 if result.wasSuccessful() else 1


if __name__ == "__main__":
    raise SystemExit(main())
