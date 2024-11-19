import os
from .  import TestBase, TEST_TARGET, TEST_DBNAME, unittest
from .. import dbxmirror

REMOTE_FOLDER    = os.environ.get("DBXMIRROR_TEST_FOLDER", "/tmp/test/sync")
REMOTE_TOKEN     = os.environ.get("DBXMIRROR_DEVELOPER_TOKEN")
ONLINE_TEST_ARGS = [ str(TEST_TARGET), REMOTE_FOLDER, f"--token={REMOTE_TOKEN}", f"--metadb={TEST_DBNAME}", "-vvv" ]

@unittest.skipIf(REMOTE_TOKEN is None, f"No Dropbox developer token available in DBXMIRROR_DEVELOPER_TOKEN")
class TestOnline(TestBase): # pragma: notoken-nocover
    def test_online(self):
        rc = dbxmirror.main(ONLINE_TEST_ARGS)

        self.assertEqual(0, rc)
        target = self.listTarget()
        meta = self.meta.db.execute("select count(*) from meta where type not like '%Deleted%'").fetchone()[0]
        self.assertGreaterEqual(len(target), 2, "There should be at least two files/directories in the test folder")
        self.assertEqual(len(target), meta, "Number of meta-db entries don't match")

    def setUpPatches(self):
        return super().setUpPatches(online=True)
