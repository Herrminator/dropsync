#!/usr/bin/python3
import sys, os, argparse, re, shutil, stat, mmap, datetime, contextlib
import dropbox, dropbox.oauth, dropbox.files
from . import dropbox_content_hasher, dbxmeta, dbxutil


# OAuth2 access. (App: "dbxmirror-tj")
APPKEY     = "60ya9v6io1n23e5"
APPSECRET  = "qnqj19wdrvynwcc"

def log(args, lvl, msg):
  if args.verbose >= lvl:
    local = os.path.realpath(os.path.normpath(args.local)) + os.path.sep # strip local path prefix in log output
    out=sys.stdout if lvl >=0 else sys.stderr
    print(msg.replace(local, ""), file=out)

def dbx_path(path):
  return path.replace(os.path.sep, '/')

def isfile(meta):
  return isinstance(meta, dropbox.files.FileMetadata)

def isfolder(meta):
  return isinstance(meta, dropbox.files.FolderMetadata)

def isdeleted(meta):
  return isinstance(meta, dropbox.files.DeletedMetadata)

def excluded(args, meta):
  exclude = False
  for patt in args.excl_patt:
    if patt.match(meta.path_display):
      exclude = True
      break

  if exclude:
    for patt in args.incl_patt:
      if patt.match(meta.path_display):
        exclude = False
        break
  return exclude

def keep(args, path):
  keep = False
  for patt in args.keep_patt:
    if patt.match(path):
      keep = True
      break
  return keep

def dbx_list(args, dbx, folder):
  folders, files, deleted = [], [], []
  res = dbx.files_list_folder(dbx_path(folder), recursive=False, include_deleted=True)
  add = True
  while add:
    for e in res.entries:
      if not excluded(args, e):
        coll = files if isfile(e) else (folders if isfolder(e) else deleted)
        coll += [ e ]
      elif args.verbose >= 2:
        log(args, 2, "Excluded: {0}".format(e.path_display))

    add = res.has_more

    if add:
      res = dbx.files_list_folder_continue(res.cursor)

  sort_key = lambda meta: meta.path_lower
  return sorted(folders, key=sort_key), sorted(files, key=sort_key), sorted(deleted, key=sort_key)

def remove_readonly(func, path, _):
    "Clear the readonly bit and reattempt the removal"
    os.chmod(path, stat.S_IWRITE)
    func(path)

def download(args, dbx, meta, loc):
  dutc = meta.client_modified.replace(tzinfo=datetime.timezone.utc)
  dts  = dutc.timestamp()
  dl   = True

  if os.path.isfile(loc):
    hasher = dropbox_content_hasher.DropboxContentHasher()
    with open(loc, "rb") as f:
      try:
        with contextlib.closing(mmap.mmap(f.fileno(), 0, access=mmap.ACCESS_READ)) as mm:
          hasher.update(mm[:])
      except ValueError: # Windows cannot mmap empty files
          hasher.update(b"")
    fhash = hasher.hexdigest()
    if fhash == meta.content_hash:
      dl = False
      log(args, 3, "Identical {0}".format(loc))
    else:
      ts = os.stat(loc).st_mtime
      if ts > dts and meta.symlink_info is None:
        log(args, 0, "WARNING: Overwriting newer {0}".format(loc))
    

  if dl:
    if meta.symlink_info is None:
      log(args, 1, "Downloading {0}, {1}k".format(loc, int(meta.size/1024)))
      if not args.dry_run:
        _meta = dbx.files_download_to_file(loc, meta.path_lower)
      else:
        log(args, 1, "  Dry-run DL: {0}, {1}b".format(meta.path_lower, meta.size))
    elif not os.path.exists(loc): # TODO replace / update (or not, considering dbx symlink support :( )
      linktarget = symlink_target(args, meta)
      log(args, 1, "{2}Symlink {0}, {1}".format(loc, linktarget or meta.symlink_info.target, "Dry-Run " if args.dry_run else ""))
      if linktarget is not None:
        if not args.dry_run:
          make_symlink(args, linktarget, loc)
      else:
        log(args, 0, "WARNING: symbolic link target not found: {0}".format(linktarget or meta.symlink_info.target))
    else:
      log(args, 2, f"Leaving symlink {loc} alone...")

  if os.path.isfile(loc):
    st = os.stat(loc)
    ts = st.st_mtime
    if ts != dts:
      log(args, 2 if not dl else 3, "Adjusting timestamp {0} -> {1}".format(
           datetime.datetime.fromtimestamp(ts), dutc))
      os.utime(loc, (dts, dts))


def make_symlink(args, src, dst):
  # TODO: overwrite / replace... should be done by sync / download
  if os.path.exists(dst): # pragma: nocover # REMOVEME, is handled in download()
    log(args, 2, "Leaving symlink {0} alone...".format(dst))
    return

  try:
    os.symlink(src, dst)
  except Exception as exc: # pragma: linux-nocover
    if not args.ignsymlink:
      raise
    else:
      log(args, 0, "WARNING: Cannot create symlink: {0}".format(exc))

def symlink_target(args, meta):
  if meta.symlink_info is None or meta.symlink_info.target is None: # pragma: nocover # REMOVEME: not reached
    return None
  target = meta.symlink_info.target
  for tr in args.trsymlink:
    fr, to = tr.split(";", 1)
    target = target.replace(fr, to)
  if not os.path.exists(target):
    return None
  return target

def localpath(args, child=None):
  local = args.local
  if child: local = os.path.join(local, child)
  real = os.path.realpath(os.path.normpath(local))
  if dbxutil.fs_case_sensitive(args.local): # pragma: windows-nocover
    # Dropbox itself is case-IN-sensitive, but case-AWARE. This is a problem for case-sensitive filesystems...
    # So, we check if the path already exist in another case
    parent, target = os.path.dirname(real), os.path.basename(real)
    has = dbxutil.path_insensitive(parent)
    if has is not None: # pragma: nobranch
      real = os.path.join(has, target)
  return real

def sync(args, dbx, path=None, metadb=None):
  # Avoid recursive list...
  if path is None: folder = dpath = args.remote; parent = None
  else:            folder,  dpath = path.path_display, path.path_lower
  rel = re.compile(re.escape(args.remote), re.I).sub("", folder, 1) # remove prefix

  local = localpath(args, rel.lstrip("/"))

  log(args, 2, "Syncing {0}".format(local))
  log(args, 3, "Remote {0}".format(folder))

  # According to dropbox support, there's no way to just retrieve changes.
  # https://www.dropboxforum.com/t5/API-Support-Feedback/How-to-get-list-of-files-recently-modified-within-24-hours/td-p/284978

  folders, files, deleted = dbx_list(args, dbx, dpath)

  if metadb is None: # pragma: nocover
    metadb = dbxmeta.DbxMetaDB(localpath(args), args.metadb)
    meta_new = True
  else:
    meta_new = False

  parent = metadb.create_meta(path) if path is not None else None

  if not os.path.isdir(local):
    log(args, 2, "Creating {0}".format(local))
    os.makedirs(local)

  # remove (or upload) local files and folders
  if args.direction == "download" and not args.no_delete:
    remote_folders = {}
    for f in folders + files:
      remote_folders[f.path_lower] = f
    for key, loc in [ ("/".join([dpath, d.name.lower()]), d) for d in os.scandir(local)]:
      if key not in remote_folders:
        if not keep(args, key):
          log(args, 1, "Removing {0}".format(loc.path))
          if loc.is_dir():
            lmeta = metadb.create_meta(name=loc.name, path_lower=key, type=dbxmeta.LocalFolderMeta)
            shutil.rmtree(loc.path, onexc=remove_readonly)
          else:
            lmeta = metadb.create_meta(name=loc.name, path_lower=key)
            remove_readonly(os.remove, loc.path, None)
          lmeta.remove(children=loc.is_dir())
        else:
          log(args, 2, "Keeping {0}".format(loc.path))

  if not args.no_delete:
    for dlt in deleted:
      loc = os.path.join(local, dlt.name)
      if os.path.exists(loc): # pragma: nocover # probably never reached because it was removed a few lines above
        log(args, 1, "DELETED (ign.): {0}".format(loc))
      else:
        metadb.create_meta(dlt, parent=parent).save(args.synctime)


  for f in files:
    loc = os.path.join(local, f.name)

    if not args.dir_only:
      download(args, dbx, f, loc)

    metadb.create_meta(f, parent=parent).save(args.synctime if not args.dir_only else None)

  # Recurse
  for f in folders:
    sync(args, dbx, f, metadb)

    metadb.create_meta(f, parent=parent).save(args.synctime)

  if meta_new: # pragma: nocover
    metadb.close()

def set_patterns(args):
  meta = "/" + args.metadb
  if meta not in args.exclude: args.exclude += [ meta ]
  if meta not in args.keep:    args.keep    += [ meta ]

  args.excl_patt, args.incl_patt, args.keep_patt = [], [], []
  root = f"^{re.escape(args.remote)}" # if args.remote != "" else "/"
  for srcs, dst in ((args.exclude, args.excl_patt), (args.include, args.incl_patt), (args.keep, args.keep_patt)):
    for src in srcs:
      dst += [ re.compile("/".join([root, src.lstrip("/")]), re.I) ]

  # REMOVEME
  if 0:
    root = re.escape(os.path.normpath(os.path.expanduser(args.local)))
    sep  = re.escape(os.path.sep)
    for src in args.keep:
      args.keep_patt += [ re.compile(sep.join([root, src.lstrip("/")]), re.I) ]

  if args.verbose >= 3:
    for what, patterns in (("Exclude", args.excl_patt), ("Include", args.incl_patt), ("Keep", args.keep_patt)):
      for patt in patterns:
        log(args, 3, "{0}: {1}".format(what, patt.pattern))

def login(args):
  login = None

  if args.login:
    import webbrowser

    flow = dropbox.oauth.DropboxOAuth2FlowNoRedirect(APPKEY, APPSECRET, token_access_type="offline")

    auth_url = flow.start()
    webbrowser.open_new_tab(auth_url)
    print(f"\nIf your browser didn't open, please go to\n  {auth_url}", flush=True)
    code = input("Please enter the code: ")
    if not code: return None
    login = flow.finish(code)

  elif args.token:
    login = dropbox.oauth.OAuth2FlowNoRedirectResult(args.token, None, None, None, None, None) # mocked...

  return dbxmeta.DbxMetaDB(localpath(args), args.metadb, login=login, reset=args.resetmeta)

def utcnow():
  # TODO: Existing databases have TZ-UN-aware timestamps, so for compatibility reasons... :(
  now = datetime.datetime.now(tz=datetime.timezone.utc).replace(tzinfo=None)
  return now

def print_version():
    from .        import __version__
    from requests import __version__ as rq_version
    print(f"{sys.argv[0]} - dropsync {__version__}, using dropbox API {dropbox.__version__} with requests {rq_version}, Python {sys.version}")

def main(argv=sys.argv[1:]):
  ap = argparse.ArgumentParser()
  ap.add_argument(      "local",       default=None)
  ap.add_argument(      "remote",      default="",          nargs="?")
  ap.add_argument("-d", "--direction", default="download",  choices=["download", "upload", "both"])
  ap.add_argument("-x", "--exclude",   default=[],          action="append", help="RegEx matching remote path")
  ap.add_argument("-i", "--include",   default=[],          action="append", help="RegEx overriding exclude")
  ap.add_argument("-k", "--keep",      default=[],          action="append", help="RegEx preventing delete")
  ap.add_argument("-y", "--trsymlink", default=[],          action="append", help="Translate path for symlinks: '<org>;<local>'")
  ap.add_argument("-n", "--no-delete", default=False,       action="store_true", help="Only transfer, don't delete files")
  ap.add_argument("-l", "--login",     default=False,       action="store_true", help="Force new login")
  ap.add_argument("-t", "--token",     default=None,        help=f"Use an existing token. E.g. from https://www.dropbox.com/developers/apps/info/{APPKEY}#settings")
  ap.add_argument("-T", "--timeout",   default=120.0,       type=float, help="Timeout for remote dropbox operations")
  ap.add_argument("-m", "--metadb",    default=".~dropsync.py.db3", help="Metadata file. Always located in local folder")
  ap.add_argument("-R", "--resetmeta", default=False,       action="store_true")
  ap.add_argument("-Y", "--ignsymlink",default=False,       action="store_true", help="Ignore symlink errors")
  ap.add_argument("-D", "--dir-only",  default=False,       action="store_true", help="Only synchronize directory structure")
  ap.add_argument("-v", "--verbose",   default=0,           action="count", help="Specify multiple times to increase verbosity")
  ap.add_argument(      "--dry-run",   default=False,       action="store_true", help="Do not transfer or delete any files")
  ap.add_argument("-V", "--version",   default=False,       action="store_true", help="Print version and exit")
  ap.add_argument(      "--synctime",  default=utcnow(),    type=lambda dt:datetime.datetime.strptime(dt,"%Y%m%d%H%M%S"), help=argparse.SUPPRESS)
  args = ap.parse_args(argv)

  assert args.direction == "download", "Upload is not implemented yet"

  if args.version:
    print_version()
    return 0

  if args.verbose > 2:
    import logging # activates dropbox library logging
    logging.basicConfig(level=logging.DEBUG if args.verbose > 3 else logging.INFO)

  metadb = login(args)

  if not metadb or (not metadb.token and not metadb.refresh_token):
    log(args, -1, "ERROR: Could not log in. Try {0} --login {1}".format(ap.prog, args.local))
    return 2

  try:
    dbx = dropbox.Dropbox(
      oauth2_access_token=metadb.token, oauth2_refresh_token=metadb.refresh_token,
      app_key=APPKEY, app_secret=APPSECRET,
      timeout=args.timeout)

    set_patterns(args)

    sync(args, dbx, metadb=metadb)
  except Exception as exc:
    import traceback
    traceback.print_exc()
    metadb.close(commit=False)
    log(args, -1, f"ERROR: Exception during processing: {exc}")
    return getattr(exc, "code", 8)
  else:
    metadb.close()

  return 0

if __name__ == "__main__": # pragma: nocover
  sys.exit(main())
