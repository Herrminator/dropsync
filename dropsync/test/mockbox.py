import unittest, os, json, shutil, datetime
from os import makedirs as os_makedirs
from unittest.mock import MagicMock, NonCallableMagicMock
from dropbox.files import FolderMetadata, FileMetadata, DeletedMetadata, ListFolderResult, Metadata, SymlinkInfo
from ..dropbox_content_hasher import DropboxContentHasher
from ..dbxmirror import isfile, isfolder, isdeleted
from ..dbxmeta import LocalFolderMeta, LocalFileMeta, LocalDeletedMeta
from typing import Optional

def chash(data):
    hasher = DropboxContentHasher()
    hasher.update(data)
    return hasher.hexdigest()

class Mockbox(NonCallableMagicMock):
    def __init__(self, testcase : unittest.TestCase, test_data : Optional[dict] = None, max_return=None, target=None, **kwargs):
        super().__init__(**kwargs)
        self.testcase = testcase
        self.test_data = {}
        self.files_list_folder.side_effect = self._files_list_folder
        self.files_download_to_file.side_effect = self._files_download_to_file
        self.files_list_folder_continue.side_effect = self._files_list_folder_continue
        self.makedirs_mock = MagicMock()
        self.makedirs_mock.side_effect = self._makedirs
        self.target = target
        self.remote = {}
        self.downloaded = []
        self.dirs_made = []
        self.max_return = max_return
        if test_data: # pragma: nocover
            self.set_data(test_data)

    def set_data(self, test_data):
        self.test_data = test_data
        self.remote[""] = (None, self.build(self.test_data, all=self.remote))
        self.create_target()

    def _files_list_folder(self, path, _cursor=None, *args, **kwars):
        next    = 0
        if _cursor is not None:
            path, next = json.loads(_cursor)
        _meta, local = self.remote[path]
        entries = [ l[0] for l in local ]
        start, end = (0, len(entries))
        if self.max_return is not None:
            start, end = (next, next + self.max_return)
            _cursor = json.dumps([path, end])
        return ListFolderResult(entries=entries[start:end], cursor=_cursor, has_more=(end < len(entries)))

    def _files_list_folder_continue(self, cursor, *args, **kwargs):
        return self._files_list_folder(None, _cursor=cursor)

    def _files_download_to_file(self, local : str, remote : str):
        self.testcase.assertIn(remote, self.remote)
        meta, data = self.remote[remote]
        with open(local, "wb") as f:
            f.write(data)
        self.downloaded += [ (local, remote) ]
        return meta

    def _makedirs(self, dir, *args, **kwargs):
        os_makedirs(dir, *args, **kwargs)
        self.dirs_made += [ dir ]

    def __call__(self, *args, **kwargs):
        return self

    def build(self, data, path="", all={},
              folder_class=FolderMetadata, file_class=FileMetadata, deleted_class=DeletedMetadata,
              allowed=["folders", "files", "deleted"]):
        local = []
        for f, d in data.get("folders", {}).items():
            self.testcase.assertIn("folders", allowed)
            pth = path + "/" + f
            subentries = self.build(d, pth, all)
            if not pth.lower() in all:
                meta = folder_class(name=f, id=str(hash(pth)), path_lower=pth.lower(), path_display=pth)
                entry = (meta, subentries)
            else: # handle case sensitivity
                entry = all[pth.lower()]
                meta, oldsub = entry
                local = [ l for l in local if l != entry ]
                entry = (meta, oldsub + subentries)
            local += [ entry ]
            all[pth.lower()] = entry

        for f, d in data.get("files", {}).items():
            self.testcase.assertIn("files", allowed)
            pth = path + "/" + f
            cmod = d["client_modified"]
            smod = d.get("server_modified", cmod)
            slnk = SymlinkInfo(target=d["symlink"]) if d.get("symlink") else None
            meta = file_class(name=f, id=str(hash(pth)), path_lower=pth.lower(), path_display=pth,
                              client_modified=cmod, server_modified=cmod, content_hash=chash(d["data"]),
                              rev=str(cmod).encode("utf-8").hex(), size=len(d["data"]),
                              symlink_info=slnk, is_downloadable=True)
            entry = (meta, d["data"])
            local += [ entry ]
            all[pth.lower()] = entry
        for f, d in data.get("deleted", {}).items():
            self.testcase.assertIn("deleted", allowed)
            pth = path + "/" + f
            meta = deleted_class(name=f, path_lower=pth.lower(), path_display=pth)
            entry = (meta,  self.build(d, pth, all, allowed=["deleted"])) # Dropbox doesn't return metadata for deleted subentries (yet?). Nevermind...
            local += [ entry ]
            all[pth.lower()] = entry
        return local

    def create_target(self):
        if self.target is None or self.test_data.get("target") is None: return
        local = {}
        target = self.build(self.test_data["target"], all=local) # , folder_class=LocalFolderMeta, file_class=LocalFileMeta)
        self.testcase.assertTrue(self.target.exists()) # was created by testcase metadb
        for key, entry in local.items():
            meta, data = entry
            dest = self.target / meta.path_display.lstrip("/")
            path = dest if isfolder(meta) else dest.parent
            if not path.exists(): path.mkdir(parents=True) # might already exist, from another file
            if isfile(meta):
                with open(dest, "wb") as f: f.write(data)
                ts = meta.client_modified.replace(tzinfo=datetime.timezone.utc).timestamp()
                os.utime(dest, (ts, ts))

    def matching(self, pred, repo=None):
        if repo is None: repo = self.remote
        match = [ f for f in repo.values() if pred(f[0]) ]
        return sorted(match, key=lambda f: f[0].path_lower)

    @property
    def all(self, repo=None):
        return self.matching(lambda f: f is not None, repo=repo)

    @property
    def existing(self, repo=None):
        return self.matching(lambda f: f is not None and not isdeleted(f) , repo=repo)

    @property
    def files(self, repo=None):
        return self.matching(isfile, repo=repo)

    @property
    def folders(self, repo=None):
        return self.matching(isfolder, repo=repo)

    @property
    def deleted(self, repo=None):
        return self.matching(isdeleted, repo=repo)
