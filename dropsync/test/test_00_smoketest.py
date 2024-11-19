import unittest, io, sys, re
from contextlib import redirect_stdout
from .. import dbxmirror, __version__

class SmokeTest(unittest.TestCase):
    def test_00_smoketest(self):
        """ Check if all modules can be imported properly """
        with self.assertRaises(SystemExit) as thrown:
            dbxmirror.main(["--help"])
        self.assertEqual(thrown.exception.code, 0)

    def test_01_version(self):
        mock_stdout = io.StringIO()
        with redirect_stdout(mock_stdout):
            dbxmirror.main(["--version", "."])
        self.assertRegex(mock_stdout.getvalue(), f".*dropsync {re.escape(__version__)}.*Python {re.escape(sys.version)}.*")
