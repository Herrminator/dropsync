import unittest, shutil, json, io
from contextlib import redirect_stdout
from datetime import datetime
import dropbox
from .. import dbxmirror
from .  import data, TestBase, TEST_ARGS, TEST_TARGET, patch, MagicMock

class TestDbxmirror(TestBase):

    def test_create_target(self):
        """ sync data to an empty target """
        self.dbx.set_data(data.SIMPLE_1)

        rc = dbxmirror.main(TEST_ARGS)

        self.assertEqual(rc, 0)
        self.assertTargetMatchesRemote()

    def test_up_to_date(self):
        """ sync data to an up-to-date target """
        self.dbx.set_data(data.SIMPLE_EXIST_1)

        rc = dbxmirror.main(TEST_ARGS)

        self.assertEqual(rc, 0)
        self.assertEqual(0, len(self.dbx.downloaded))
        self.assertEqual(0, self.dbx.makedirs_mock.call_count)
        all = self.listTarget()
        self.assertEqual(len(self.dbx.existing), len(all))

    def test_overwrite(self):
        """ sync data overwriting a newer file """
        self.dbx.set_data(data.SIMPLE_OVERWRITE_1)
        mock_stdout = io.StringIO()

        with redirect_stdout(mock_stdout):
            rc = dbxmirror.main(TEST_ARGS)

        self.assertEqual(rc, 0)
        self.assertEqual(1, len(self.dbx.downloaded))
        all = self.listTarget()
        self.assertEqual(len(self.dbx.existing), len(all))

        self.assertRegex(mock_stdout.getvalue(), r"WARNING: Overwriting newer")

    def test_removal(self):
        """ remove files not found on remote """
        self.dbx.set_data(data.SIMPLE_REMOVE_1)
        before = self.listTarget()
        nremote = len(self.dbx.existing)
        self.assertLess(nremote, len(before))
        diff = len(before) - nremote

        rc = dbxmirror.main(TEST_ARGS)

        all = self.listTarget()
        self.assertEqual(nremote, len(all))
        self.assertEqual(len(all), len(before) - diff)
        self.assertEqual(len(all), self.meta.db.execute("select count(*) from meta").fetchone()[0])

    def test_removal_and_delete(self):
        """ remove files not found on remote but marked in meta """
        self.dbx.set_data(data.SIMPLE_REMOVE_AND_DELETE_1)
        files_in_deleted_folders = 1 # too lazy to calculate
        before = self.listTarget()
        nremote = len(self.dbx.existing)
        self.assertLess(nremote, len(before))
        diff = len(before) - nremote

        rc = dbxmirror.main(TEST_ARGS)

        all = self.listTarget()
        self.assertEqual(nremote, len(all))
        self.assertEqual(len(all), len(before) - diff)
        # now, the deleted metadata should have been added to the DB ("+ diff"), but for files in subdirs!
        self.assertEqual(len(all) + diff - files_in_deleted_folders,
                         self.meta.db.execute("select count(*) from meta").fetchone()[0])

    def test_remove_and_keep(self):
        """ remove files not found on remote but keep patterns """
        self.dbx.set_data(data.SIMPLE_REMOVE_1)
        before = self.listTarget()
        diff = len(before) - (len(self.dbx.existing))

        rc = dbxmirror.main(TEST_ARGS + [ r"--keep=removeme\.txt"])

        all = self.listTarget()
        self.assertEqual(len(all), len(before) - diff + 1)

    def test_exclude(self):
        """ simple exclude pattern """
        self.dbx.set_data(data.SIMPLE_1)

        # --exclude matches one file
        rc = dbxmirror.main( TEST_ARGS + [r"--exclude=/foo.*\.txt"]) # exclude matches one file

        self.assertEqual(rc, 0)
        self.assertEqual(len(self.dbx.files) - 1, len(self.dbx.downloaded))
        all = self.listTarget()
        self.assertEqual(len(self.dbx.existing) - 1, len(all))

    def test_include(self):
        """ exclude pattern with include pattern """
        self.dbx.set_data(data.SIMPLE_1)

        # --exclude matches three files, but --include matches one
        excluded = 2
        rc = dbxmirror.main( TEST_ARGS + [r"--exclude=.*\.txt", r"--include=.*/bar\.txt"])

        self.assertEqual(rc, 0)
        self.assertEqual(len(self.dbx.files) - excluded, len(self.dbx.downloaded))
        all = self.listTarget()
        self.assertEqual(len(self.dbx.existing) - excluded, len(all))

    def test_deleted(self):
        """ deleted remote files are ignored """
        self.dbx.set_data(data.SIMPLE_DELETED_1)

        rc = dbxmirror.main(TEST_ARGS)

        self.assertEqual(rc, 0)
        all = self.listTarget()
        meta = self.meta.db.execute("select count(*) from meta").fetchone()[0]
        self.assertEqual(len(self.dbx.existing), len(all))
        self.assertEqual(len(all) + len(self.dbx.deleted), meta)

    def test_no_deleted(self):
        """ deleted remote files are ignored (also in metadata) """
        self.dbx.set_data(data.SIMPLE_DELETED_1)

        rc = dbxmirror.main(TEST_ARGS + ["--no-delete"])

        self.assertEqual(rc, 0)
        all = self.listTarget()
        meta = self.meta.db.execute("select count(*) from meta").fetchone()[0]
        self.assertEqual(len(self.dbx.existing), len(all))
        self.assertEqual(len(all), meta)

    def test_dir_only(self):
        """ only directories are created """
        self.dbx.set_data(data.SIMPLE_1)

        rc = dbxmirror.main(TEST_ARGS + ["--dir-only"])

        self.assertEqual(rc, 0)
        target = self.listTarget()
        meta = self.meta.db.execute("select count(*) from meta").fetchone()[0]
        self.assertEqual(len(self.dbx.folders), len(target), "Number of existing dirs on remote differs from target")
        self.assertEqual(len(self.dbx.existing), meta, "Number of meta-db entries don't match") # TODO: file meta DB-entries are still written???
        self.assertEqual(0, len(self.dbx.downloaded), "Unexpected download")
        self.assertEqual(len(self.dbx.folders), self.dbx.makedirs_mock.call_count, "Directory create call mismatch")

    def test_Case_Sensitive(self):
        """ ignore case difference """
        self.dbx.set_data(data.SIMPLE_CASE_SENSITIVITY_1)

        rc = dbxmirror.main(TEST_ARGS)

        self.assertEqual(rc, 0)
        self.assertTargetMatchesRemote()

    def test_list_continue(self):
        """ folder list limit reached """
        self.dbx.set_data(data.MORE_FILES_1)
        self.dbx.max_return = 2

        rc = dbxmirror.main(TEST_ARGS)

        self.assertEqual(rc, 0)
        self.assertEqual(self.dbx.files_list_folder_continue.call_count, len(self.dbx.files) // self.dbx.max_return)
        dbx, dl = set([ f[0].path_display for f in self.dbx.files]), set([ f[1] for f in self.dbx.downloaded])
        self.assertEqual(dbx, dl)

    @patch.object(dbxmirror, "input", name="mock_input")
    @patch("webbrowser.open_new_tab", name="mock_browser_tab")
    @patch("dropbox.oauth.DropboxOAuth2FlowNoRedirect", name="mock_flow")
    def test_login(self, mock_flow : MagicMock, mock_browser_tab : MagicMock, mock_input : MagicMock):
        """ "interactive" login via OAuth for "offline" access """
        auth  = "https://dropbox.mock/auth"
        login = dropbox.oauth.OAuth2FlowNoRedirectResult("foobar", None, None, None, datetime(2100, 12, 31), None)
        mock_flow.return_value.start.return_value = auth
        mock_flow.return_value.finish.return_value = login

        with self.subTest("login succes"):
            mock_input.return_value = "mock-code-from-auth"

            self.dbx.set_data(data.SIMPLE_1)
            
            rc = dbxmirror.main(TEST_ARGS + [ "--login"])

            self.assertEqual(rc, 0)
            mock_flow.assert_called_once_with(dbxmirror.APPKEY, dbxmirror.APPSECRET, token_access_type="offline")
            mock_browser_tab.assert_called_once_with(auth)
            self.assertEqual(("foobar", None), self.meta.db.execute("select token, refresh_token from login").fetchone().values())

        with self.subTest("login cancel"):
            mock_flow.reset_mock(); mock_browser_tab.reset_mock()
            self.meta.db.execute("delete from login")
            mock_input.return_value = ""

            self.dbx.set_data(data.SIMPLE_1)
            
            rc = dbxmirror.main(TEST_ARGS + [ "--login"])

            self.assertEqual(rc, 2)
            mock_flow.assert_called_once_with(dbxmirror.APPKEY, dbxmirror.APPSECRET, token_access_type="offline")
            mock_browser_tab.assert_called_once_with(auth)
            self.assertEqual(0, self.meta.db.execute("select count(*) from login").fetchone()[0])

    def test_token(self):
        """ login with existing (mock) token """
        self.dbx.set_data(data.SIMPLE_1)

        rc = dbxmirror.main(TEST_ARGS + [ "--token=foobar"])

        self.assertEqual(rc, 0)
        self.assertEqual("foobar", self.meta.db.execute("select token from login").fetchone()[0])
