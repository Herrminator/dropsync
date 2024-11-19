import os, tempfile

_fs_case_sensitive = {}

# https://stackoverflow.com/a/36580834/10545609
def fs_case_sensitive(path):
    tmp = path if os.path.isdir(path) else os.path.dirname(path) # try to use parent dir if path is not yet created
    if not path in _fs_case_sensitive:
        with tempfile.NamedTemporaryFile(prefix="tmp_lower_", dir=tmp) as chk:
            _fs_case_sensitive[path] = not os.path.exists(chk.name.upper())
    return _fs_case_sensitive[path]

# https://stackoverflow.com/a/8462613/10545609
def path_insensitive(path):
    """
    Recursive part of path_insensitive to do the work.
    """

    if path == '' or os.path.exists(path):
        return path

    base = os.path.basename(path)  # may be a directory or a file
    dirname = os.path.dirname(path)

    suffix = ''
    if not base:  # dir ends with a slash?
        if len(dirname) < len(path): # pragma: nobranch
            suffix = path[:len(path) - len(dirname)]

        base = os.path.basename(dirname)
        dirname = os.path.dirname(dirname)

    if not os.path.exists(dirname):
        dirname = path_insensitive(dirname)
        if not dirname: # pragma: nobranch
            return None

    # at this point, the directory exists but not the file

    try:  # we are expecting dirname to be a directory, but it could be a file
        files = os.listdir(dirname)
    except OSError:
        return None

    baselow = base.lower()
    try:
        basefinal = next(fl for fl in files if fl.lower() == baselow)
    except StopIteration:
        return None

    if basefinal: # pragma: windows-nocover
        return os.path.join(dirname, basefinal) + suffix
    else: # pragma: nocover
        return None
