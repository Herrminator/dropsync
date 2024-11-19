import os, io, re, platform
from .. import dbxmirror, dbxutil, dbxmeta
from . import data, TestBase, TEST_ARGS, TEST_TARGET, TEST_DBNAME, unittest, patch, MagicMock
from contextlib import redirect_stdout, redirect_stderr

class TestErrors(TestBase):

    def test_missing_token(self):
        """ login without stored token """
        self.dbx.set_data(data.SIMPLE_1)
        self.meta.db.executescript("delete from login"); self.meta.db.commit()
        mock_stderr = io.StringIO()

        with redirect_stderr(mock_stderr):
            rc = dbxmirror.main(TEST_ARGS)

        self.assertEqual(rc, 2)
        self.assertRegex(mock_stderr.getvalue(), r"ERROR: Could not log in.*")

    def test_invalid_pattern(self):
        """ invalid regular expression """
        self.dbx.set_data(data.SIMPLE_1)
        mock_stderr = io.StringIO()

        with redirect_stderr(mock_stderr):
            rc = dbxmirror.main(TEST_ARGS + [ r"--exclude=^invalid (RegEx" ])

        self.assertEqual(rc, 8)
        self.assertRegex(mock_stderr.getvalue(), r"ERROR: Exception.*")

    def test_symlink(self):
        """ symlinks with path translation
            not really an error, but also not really OK without admin rights
        """
        self.dbx.set_data(data.SIMPLE_SYMLINK_1)

        mock_stdout = io.StringIO()
        with self.subTest("as dry run"), redirect_stdout(mock_stdout):
            rc = dbxmirror.main(TEST_ARGS + ["--dry-run", rf"--trsymlink=C:\Test\;{TEST_TARGET.resolve() / 'Test'}{os.sep}" ])
            self.assertEqual(rc, 0)
            self.assertRegex(mock_stdout.getvalue(), "Dry-Run Symlink.*")

        with self.subTest("with error handling"):
            mock_stdout = io.StringIO()

            with redirect_stdout(mock_stdout):
                rc = dbxmirror.main(TEST_ARGS + [rf"--trsymlink=C:\Test\;{TEST_TARGET.resolve() / 'Test'}{os.sep}", "--ignsymlink"])
            self.assertEqual(rc, 0)

            self.assertRegex(mock_stdout.getvalue(), r"Leaving symlink.*") # one symlink already exists

            expect = expmeta = len(self.dbx.folders) + len(self.dbx.files)
            if platform.system() == "Windows" and not self.is_admin(): # pragma: linux-nocover # pragma: nobranch
                self.assertRegex(mock_stdout.getvalue(), r"WARNING: Cannot create symlink.*")
                expect -= 1

            all = self.listTarget()
            meta = self.meta.db.execute("select count(*) from meta").fetchone()[0]
            self.assertEqual(expect,  len(all))
            self.assertEqual(expmeta, meta)


        if platform.system() == "Windows" and not self.is_admin(): # pragma: linux-nocover # pragma: nobranch
            mock_stderr = io.StringIO()
            with self.subTest("without error handling"), redirect_stderr(mock_stderr):
                rc = dbxmirror.main(TEST_ARGS + [rf"--trsymlink=C:\Test\;{TEST_TARGET.resolve() / 'Test'}{os.sep}" ])
            self.assertEqual(rc, 8)
            self.assertRegex(mock_stderr.getvalue(), "ERROR: Exception.*")

    def test_symlink_not_found(self):
        """ symlinks without path translation """
        self.dbx.set_data(data.SIMPLE_SYMLINK_1)

        mock_stdout = io.StringIO()
        with redirect_stdout(mock_stdout):
            rc = dbxmirror.main(TEST_ARGS)
        self.assertEqual(rc, 0)

        expmeta = len(self.dbx.folders) + len(self.dbx.files)
        self.assertRegex(mock_stdout.getvalue(), r"WARNING: symbolic link target not found.*")

        all = self.listTarget()
        meta = self.meta.db.execute("select count(*) from meta").fetchone()[0]
        self.assertEqual(expmeta-1,  len(all))
        self.assertEqual(expmeta,    meta)

    def test_dry_run(self):
        """ sync data to an empty target (dry-run)
            see test_dbxmirror.TestDbxmirror.test_create_target()
            also no real error, see the TODOs below...
        """
        self.dbx.set_data(data.SIMPLE_1)

        rc = dbxmirror.main(TEST_ARGS + [ "--dry-run" ])

        self.assertEqual(rc, 0)
        self.assertEqual(0, len(self.dbx.downloaded))
        self.assertEqual(len(self.dbx.folders), self.dbx.makedirs_mock.call_count) # TODO: Folders ARE still created on dry-run
        all = self.listTarget()
        meta = self.meta.db.execute("select count(*) from meta").fetchone()[0]
        self.assertEqual(len(self.dbx.folders), len(all))
        self.assertEqual(len(self.dbx.folders) + len(self.dbx.files), meta) # TODO: Also, meta data ist also written to the database

    @unittest.skipIf(not dbxutil.fs_case_sensitive(str(TEST_TARGET.parent)), "Target is case insensitive")
    def test_Case_Sensitive(self): # pragma: windows-nocover
        """ test invalid case sensitivity detection """
        with patch.object(dbxmirror.dbxutil, "fs_case_sensitive") as mock_fs_cs:
            self.dbx.set_data(data.SIMPLE_CASE_SENSITIVITY_1)
            mock_fs_cs.return_value = False

            rc = dbxmirror.main(TEST_ARGS)

            self.assertEqual(rc, 0)
            target = self.listTarget()
            meta = self.meta.db.execute("select count(*) from meta").fetchone()[0]
            self.assertLess(len(self.dbx.existing), len(target), "Case sensitive files/dirs not created")
            self.assertLess(meta, len(target), "Case sensitive meta-db entries not created")
            self.assertLess(len(self.dbx.folders), self.dbx.makedirs_mock.call_count, "Case sensitive directories not created")


    def test_unused(self):
        """ functions that should be used
            e.g. for cleaning up the metadb
        """
        with self.subTest("DbxMetaDB.remove()"):
            self.dbx.set_data(data.SIMPLE_1)
            rc = dbxmirror.main(TEST_ARGS + [ "--dry-run" ])
            self.assertEqual(rc, 0)
            meta = self.meta.db.execute("select count(*) from meta").fetchone()[0]
            self.assertGreater(meta, 0)
            self.meta.remove("name <> ?", ("",))
            self.meta.db.commit()
            meta = self.meta.db.execute("select count(*) from meta").fetchone()[0]
            self.assertEqual(0, meta)

        with self.subTest("DbxMetaDB(reset=True)"):
            self.dbx.set_data(data.SIMPLE_1)
            rc = dbxmirror.main(TEST_ARGS + [ "--dry-run" ])
            self.assertEqual(rc, 0)
            meta = self.meta.db.execute("select count(*) from meta").fetchone()[0]
            self.assertGreater(meta, 0)
            self.meta.close()
            self.meta = dbxmeta.DbxMetaDB(TEST_TARGET, TEST_DBNAME, login=None, reset=True)
            meta = self.meta.db.execute("select count(*) from meta").fetchone()[0]
            self.assertEqual(0, meta)

        with self.subTest("DbxMetaDB.Row class"):
            row = self.meta.db.execute("select token, refresh_token from login").fetchone()
            self.assertEqual(row.keys(),   ["token", "refresh_token"]) # inherited
            self.assertEqual(row.values(), (None, "foobar"))
            self.assertEqual(row.items(),  (("token", None), ("refresh_token", "foobar")))

        with self.subTest("LocalMetadata equality"):
            from ..dbxmeta import LocalFileMeta
            self.assertGreaterEqual(len(self.dbx.files), 2)
            l0, l1 = LocalFileMeta(self.meta, self.dbx.files[0][0]), LocalFileMeta(self.meta, self.dbx.files[1][0])
            self.assertNotEqual(l0, l1)
            self.assertEqual(l0, l0)

        with self.subTest("Utility functions"):
            tgt  = str(TEST_TARGET)
            CS   = dbxutil.fs_case_sensitive(tgt)
            new  = os.path.join(tgt, "new")
            New  = os.path.join(tgt, "New")
            old  = os.path.join(tgt, "old")
            Old  = os.path.join(tgt, "Old")
            File = os.path.join(old, "File")
            os.makedirs(old)
            with open(File, "w") as f: f.write("I'm not a dricetory!")

            # cover some special cases
            self.assertIs(None, dbxutil.path_insensitive(New))
            self.assertIs(None, dbxutil.path_insensitive(os.path.join(New, "new")))
            self.assertIs(None, dbxutil.path_insensitive(os.path.join(New, "new") + os.sep))
            self.assertIs(None, dbxutil.path_insensitive(os.path.join(File, "dir")))
            self.assertEqual( old if CS else Old, dbxutil.path_insensitive(Old))
            self.assertEqual((old if CS else Old) + os.sep, dbxutil.path_insensitive(Old + os.sep))

        with self.subTest("lets get 100%"):
            from ..dbxmeta import LocalDeletedMeta, LocalFileMeta
            class FoobarMeta(LocalDeletedMeta):
                DEFAULT_ATTR = [ ("name", "foobar")]
            chk = FoobarMeta(self.meta)
            self.assertEqual(chk.name, "foobar")
            self.dbx.set_data(data.SIMPLE_DELETED_1)
            self.assertEqual(len(self.dbx.existing), len(self.dbx.files + self.dbx.folders))
            self.assertEqual(len(self.dbx.all), len(self.dbx.existing + self.dbx.deleted))

            md = LocalFileMeta(self.meta, self.dbx.files[0][0])
            self.assertNotEqual(md.path_lower, "path_is_key")
            md.key = "path_is_key"
            self.assertEqual(md.path_lower, "path_is_key")

            # fill meta DB again
            test_args = TEST_ARGS + [ "--exclude=FindMeNot"]; test_args.remove("-vvv") # coverage ;)
            rc = dbxmirror.main(test_args + [ "--dry-run" ]); self.assertEqual(rc, 0)
            meta = self.meta.db.execute("select count(*) from meta").fetchone()[0]
            self.assertGreater(meta, 0)
            self.assertEqual(meta, len(self.meta.find()))

            # Row.__str__ and Row.__repr__ are mainly for debugging...
            meta = self.meta.db.execute("select * from meta").fetchone()
            self.assertRegex(repr(meta), r"^<DbxMetaDB.Row\(.*\)>$")

            # again, again ;) see with self.subTest("DbxMetaDB.remove()")
            self.meta.remove("name like '%'"); self.meta.db.commit() # slightly different, no params
            self.assertEqual(0, self.meta.db.execute("select count(*) from meta").fetchone()[0])

            mock_stdout, mock_args = io.StringIO(), MagicMock(verbose=0, excl_patt=[re.compile(".*")])
            with redirect_stdout(mock_stdout):
                dbxmirror.log(mock_args, 1, "Hello Not!")
                self.assertEqual("", mock_stdout.getvalue())
                dbxmirror.log(mock_args, 0, "Hello Log!")
                self.assertEqual("Hello Log!\n", mock_stdout.getvalue())
            mock_stdout = io.StringIO()
            with redirect_stdout(mock_stdout):
                dbxmirror.dbx_list(mock_args, self.dbx, "")
                self.assertEqual("", mock_stdout.getvalue())
                mock_args.verbose = 3
                dbxmirror.dbx_list(mock_args, self.dbx, "")
                self.assertRegex(mock_stdout.getvalue(), r"^Excluded: .*")
