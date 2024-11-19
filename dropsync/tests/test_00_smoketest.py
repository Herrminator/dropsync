import unittest

class SmokeTest(unittest.TestCase):
    def test_00_smoketest(self):
        """ Check if all modules can be imported properly """
        with self.assertRaises(SystemExit) as thrown:
            from .. import dbxmirror
            dbxmirror.main(["--help"])
        self.assertEqual(thrown.exception.code, 0)
