import sys, os, unittest, shutil
from unittest.mock import patch, MagicMock
from pathlib import Path
from .mockbox import Mockbox

TEST_TARGET   = Path(__file__).parent.resolve() / 'data' / 'target'
TEST_DBNAME   = ".~dbxmirror.db" # ?mode=memory&cache=shared"
TEST_ARGS     = [ str(TEST_TARGET), f"--metadb={TEST_DBNAME}", "-vvv" ]

class TestBase(unittest.TestCase):
    def setUp(self):
        from .. import dbxmeta
        self.assertFalse(TEST_TARGET.exists(), f"Please make sure '{TEST_TARGET}' doesn't exist")
        self.addCleanup(self.cleanUp)
        self.meta = dbxmeta.DbxMetaDB(TEST_TARGET, TEST_DBNAME, login=None)
        self.db = self.meta.db
        self.db.execute("insert into login (refresh_token, expires) values ('foobar', '2200-01-01 00:00:00')")
        self.db.commit()
        self.setUpPatches()

    def setUpPatches(self, online=False): # we're not using the decorators, so we can use the same mock for multiple methods
        from .. import dbxmirror
        self.dbx = Mockbox(self, target=TEST_TARGET)
        if not online: # pragma: nobranch
            p = patch.object(dbxmirror.dropbox, "Dropbox", new=self.dbx); p.start()
        p = patch.object(dbxmirror.os, "makedirs", new=self.dbx.makedirs_mock); p.start()
        self.addCleanup(patch.stopall)

    def tearDown(self):
        self.meta.close()

    def cleanUp(self):
        shutil.rmtree(TEST_TARGET)

    def is_admin(self): # pragma: nocover # not my code ;)
        # https://stackoverflow.com/a/10671675/10545609
        if os.name == 'nt':
            try:
                # only windows users with admin privileges can read the C:\windows\temp
                temp = os.listdir(os.sep.join([os.environ.get('SystemRoot','C:\\windows'),'temp']))
            except: return False
            else:   return True
        else:
            return 'SUDO_USER' in os.environ and os.geteuid() == 0

    def listTarget(self, include_hidden: bool = False):
        result = list(TEST_TARGET.rglob("*"))
        if not include_hidden: # pragma: nobranch
            def hidden(p):
                b = os.path.basename(p)
                return b.startswith(".~")
            result = [ e for e in result if not hidden(e) ]
        return result
        
    def assertTargetMatchesRemote(self):
        target = self.listTarget()
        meta = self.meta.db.execute("select count(*) from meta").fetchone()[0]
        self.assertEqual(len(self.dbx.existing), len(target), "Number of existing files/dirs on remote differs from target")
        self.assertEqual(len(target), meta, "Number of meta-db entries don't match")
        self.assertEqual(len(self.dbx.files), len(self.dbx.downloaded), "Download call mismatch")
        self.assertEqual(len(self.dbx.folders), self.dbx.makedirs_mock.call_count, "Directory create call mismatch")

class Run(unittest.TestProgram): # pragma: nocover
    from .test_00_smoketest import SmokeTest
    from .test_dbxmirror import TestDbxmirror
    from .test_online import TestOnline
    from .test_errors import TestErrors
    
    def __init__(self, *args, **kwargs):
        kwargs.pop("module", None)
        super().__init__(module=self, *args, **kwargs)
