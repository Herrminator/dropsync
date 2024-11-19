import os, datetime, pathlib, urllib.parse
try:    from pysqlite2 import dbapi2 as sql #@UnresolvedImport,@UnusedImport
except: from sqlite3   import dbapi2 as sql #@Reimport
import dropbox

# see Python 3.12 documentation for recipes to replace deprecated default adapters and converterrs
# these are compatible with Python <= 3.11
def register_compatible(): # pragma: nocover
  def convert_date(val):
      return datetime.date.fromisoformat(val.decode())
  def convert_timestamp(val):
      return datetime.datetime.fromisoformat(val.decode())
  def adapt_datetime(val):
      return val.isoformat(" ")
  def adapt_date(val):
      return val.isoformat()
  sql.register_converter("date", convert_date)
  sql.register_converter("timestamp", convert_timestamp)
  sql.register_adapter(datetime.datetime, adapt_datetime)
  sql.register_adapter(datetime.date, adapt_date)
register_compatible()
del register_compatible

class classproperty(object):
    def __init__(self, f):
        self.f = f
    def __get__(self, obj, owner):
        return self.f(owner)

class LocalMetadata(object):
  COPY_ATTR    = [ "name", "path_lower", "path_display" ]
  DEFAULT_ATTR = []
  SET_ATTR     = []

  def __init__(self, db, dbxmeta=None, parent=None, **kwargs):
    self.db = db
    self.parent = parent
    self.kwargs = kwargs
    self.syncts = None
    self.modts  = None
    if dbxmeta is not None:
      for attr in self.COPY_ATTR:
        val = getattr(dbxmeta, attr, None)
        self.kwargs[attr] = val
    for attr, val in self.DEFAULT_ATTR:
      if attr not in self.kwargs: self.kwargs[attr] = val
    for attr, val in self.SET_ATTR:
      if not hasattr(self, attr): setattr(self, attr, val)

  def save(self, ts=datetime.datetime.utcnow()):
    if ts is not None:     self.syncts = ts
    if self.modts is None: self.modts  = self.syncts

    prev = self.db.get(self.key)
    if prev is not None:
      if prev != self: self.modts = self.syncts
      else:            self.modts = prev.modts if prev.modts is not None else self.modts

    cur = self.db.cursor()
    cur.execute("insert or replace into meta values(?,?,?,?,?,?,?,?,?,?,?,?)",
                (self.key,         self.type,
                 self.name,        self.id,
                 self.size,        self.path_display,
                 self.parent.key if self.parent else "",
                 self.rev,
                 self.client_modified,
                 self.server_modified,
                 self.modts,
                 self.syncts))
    cur.close()

  def remove(self, children=False):
    cur = self.db.db.cursor()
    cur.execute("delete from meta where key = ?", (self.path_lower,))
    cur.close()
    if children and hasattr(self, "children"):
      for c in self.children(): c.remove(children=True)

  @classproperty
  def type(cls): return cls.__name__ #@NoSelf

  @property
  def key(self): return self.path_lower

  @key.setter
  def key(self, val): self.path_lower = val

  def _cmp_attr(self):
    return [ "type" ] + self.COPY_ATTR + self.DEFAULT_ATTR + [ k for k, _v in self.SET_ATTR ]

  def __eq__(self, rhs):
    for attr in self._cmp_attr():
      if getattr(self, attr, None) != getattr(rhs, attr, None):
        return False
    return True

class LocalFileMeta(LocalMetadata, dropbox.files.FileMetadata):
  COPY_ATTR = LocalMetadata.COPY_ATTR +\
              [ "id", "client_modified", "server_modified", "size", "rev" ]

  def __init__(self, db, dbxmeta=None, parent=None, *args, **kwargs):
    LocalMetadata.__init__(self, db, dbxmeta, parent, **kwargs)
    dropbox.files.FileMetadata.__init__(self, *args, **self.kwargs)


class LocalFolderMeta(LocalMetadata, dropbox.files.FolderMetadata):
  COPY_ATTR = LocalMetadata.COPY_ATTR + [ "id" ]
  SET_ATTR = [ ("client_modified", None), ("server_modified", None), ("size", None), ("rev", None) ]

  def __init__(self, db, dbxmeta=None, parent=None, *args, **kwargs):
    LocalMetadata.__init__(self, db, dbxmeta, parent, **kwargs)
    dropbox.files.FolderMetadata.__init__(self, *args, **self.kwargs)

  def children(self):
    return self.db.find("parent = ?", (self.key,))

class LocalDeletedMeta(dropbox.files.DeletedMetadata, LocalMetadata):
  SET_ATTR = [ ("client_modified", None), ("server_modified", None), ("size", None), ("rev", None) ]

  def __init__(self, db, dbxmeta=None, parent=None, id=None, *args, **kwargs):  # @ReservedAssignment
    LocalMetadata.__init__(self, db, dbxmeta, parent, **kwargs)
    dropbox.files.DeletedMetadata.__init__(self, *args, **self.kwargs)
    self.id = id


class DbxMetaDB(object):
  DBX_META_MAP = {
    dropbox.files.FileMetadata:    LocalFileMeta,
    "LocalFileMeta":               LocalFileMeta,
    dropbox.files.FolderMetadata:  LocalFolderMeta,
    "LocalFolderMeta":             LocalFolderMeta,
    dropbox.files.DeletedMetadata: LocalDeletedMeta,
    "LocalDeletedMeta":            LocalDeletedMeta,
  }

  class Row(sql.Row):
    # see https://github.com/python/cpython/issues/100450 et al.
    def values(self):
      return tuple(self[k] for k in self.keys()) # assume that the keys are properly ordered (by column no.)
    def items(self):
      return tuple((k, self[k]) for k in self.keys()) # assume that the keys are properly ordered (by column no.)
    def __str__(self):
      return f"""({', '.join([ f'"{str(v)}"' for v in self.values()])})""" # triple quotes for Python < 3.12
    def __repr__(self):
      return f"<DbxMetaDB.Row({str(self)})>"

  def __init__(self, path, dbname=".~dbxmeta.py.db3", login=None, reset=False):
    self.path     = path
    self.dbname   = dbname 
    self.db       = None
    self._token   = False
    self._refresh = False

    self.init_db(login=login, reset=reset)

  def __del__(self):
    self.close()

  def create_meta(self, dbxmeta=None, parent=None, type=LocalFileMeta, *args, **kwargs):  # @ReservedAssignment
    type        = self.DBX_META_MAP[type] if isinstance(type, str) else type  # @ReservedAssignment
    MetaFactory = self.DBX_META_MAP[dbxmeta.__class__] if dbxmeta is not None else type

    meta = MetaFactory(self, dbxmeta=dbxmeta, parent=parent, *args, **kwargs)

    # TODO: copy constructor...
    return meta

  @property
  def cursor(self): return self.db.cursor

  @property
  def token(self):
    if self._token is False:
      cur = self.db.cursor()
      cur.execute("select token, refresh_token from login where expires > ? or expires is null order by expires desc",
                  (datetime.datetime.now(),))
      row = cur.fetchone()
      cur.close()
      if row is None:
        self._token = self._refresh = None
        return None
      self._token   = row["token"]
      self._refresh = row["refresh_token"]
    return self._token

  @property
  def refresh_token(self):
    if self._refresh is False: self.token()
    return self._refresh

  def find(self, cond=None, param=None):
    result = []
    cur = self.db.cursor()
    cond  = "where " + cond if cond else ""
    if param is not None:
      param = param if isinstance(param, (tuple,list,dict)) else (param,)
    else:
      param = []
    cur.execute("select * from meta {0}".format(cond), param)
    for row in cur.fetchall():
      res = self.create_meta(type=row["type"], name=row["name"], id=row["id"],
                             path_lower=row["key"], path_display=row["path"])
      if row["client_ts"] is not None:
        res.client_modified = row["client_ts"]
      if row["server_ts"] is not None:
        res.server_modified = row["server_ts"]
      if row["size"] is not None:
        res.size = row["size"]
      if row["rev"] is not None:
        res.rev = row["rev"]
      res.syncts = row["sync_ts"]
      res.modts  = row["mod_ts"]
      result += [ res ]
    cur.close()
    return result

  def get(self, key):
    res = self.find("key = ?", key)
    assert len(res) <= 1, "Too many results"
    return res[0] if len(res) > 0 else None

  def remove(self, cond, param=None):
    cur = self.db.cursor()
    cond  = "where " + cond if cond else ""
    if param is not None:
      param = param if isinstance(param, (tuple,list,dict)) else (param,)
    else:
      param = []
    cur.execute("delete from meta {0}".format(cond), param)
    cur.close()

  def init_db(self, reset=False, login=None):
    if not os.path.isdir(self.path): os.makedirs(self.path)
    # HACK ALERT: separate sqlite URI-parameters from filename
    p = urllib.parse.urlparse(self.dbname)
    dburi = pathlib.Path(os.path.join(self.path, p.path)).resolve().as_uri()
    if p.query: dburi += f"?{p.query}"
    self.db = sql.connect(dburi, uri=True,
                          detect_types=sql.PARSE_DECLTYPES)
    self.db.row_factory = self.Row
    cur = self.db.cursor()
    if reset:
      cur.execute("""drop table if exists meta""")
      cur.execute("""vacuum""")
    cur.execute("""create table if not exists meta (
      key        text not null primary key,
      type       text not null,
      name       text not null,
      id         text,
      size       integer,
      path       text,
      parent     text,
      rev        text,
      client_ts  timestamp,
      server_ts  timestamp,
      mod_ts     timestamp,
      sync_ts    timestamp
    )""")
    cur.execute("""create table if not exists login (
      token         text,
      expires       timestamp,
      refresh_token text,
      account_id    text,
      user_id       text
    )""")

    if login is None:
      cur.execute("""delete from login where expires <= ?""", (datetime.datetime.now(),))
    else:
      expires = getattr(login, "expires_at", None) if login.refresh_token is None else None
      if expires is None:
        # see https://www.dropbox.com/developers/support#token-expiration
        # and https://www.dropboxforum.com/t5/API-Support-Feedback/OAuth-2-0-Access-Token-Validity/td-p/46533
        # "Access tokens effectively don't expire."
        expires = datetime.datetime.now() + datetime.timedelta(days=20*365)

      cur.execute("delete from login")
      cur.execute("insert into login values (?,?,?,?,?)",
                  (login.access_token if not login.refresh_token else None, expires,
                   login.refresh_token if login.refresh_token else None,
                   getattr(login, "account_id", None), getattr(login, "user_id", None)))
    cur.close()

    self.db.commit()

  def close(self, commit=True):
    if not self.db: return
    self.db.commit() if commit else self.db.rollback()
    self.db.close()
    self.db = None