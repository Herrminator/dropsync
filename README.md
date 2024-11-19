# `dropsync`

A simple [Dropbox](https://dropbox.com) CLI-client written in [Python](https://python.org), using the
official [Dropbox-API](https://www.dropbox.com/developers/documentation).

## Installation

`pipx install git+https://github.com/Herrminator/dropsync.git`

You need Python with `pipx` installed (`python -m pip install pipx`).

## Usage

``` 
usage: dbxmirror [-h] [-d {download,upload,both}] [-x EXCLUDE] [-i INCLUDE]
                 [-k KEEP] [-y TRSYMLINK] [-n] [-l] [-t TOKEN] [-T TIMEOUT]
                 [-m METADB] [-R] [-Y] [-v] [-D] [--dry-run]
                 local [remote]

positional arguments:
  local
  remote

options:
  -h, --help            show this help message and exit
  -d {download,upload,both}, --direction {download,upload,both}
  -x EXCLUDE, --exclude EXCLUDE
                        RE matching remote path
  -i INCLUDE, --include INCLUDE
                        RE overriding exclude
  -k KEEP, --keep KEEP  RE prevent delete
  -y TRSYMLINK, --trsymlink TRSYMLINK
                        Translate path for symlinks: '<org>;<local>'
  -n, --no-delete
  -l, --login           Force new login
  -t TOKEN, --token TOKEN
                        Use existing token. E.g. from https://www.dropbox.com/
                        developers/apps/info/60ya9v6io1n23e5#settings
  -T TIMEOUT, --timeout TIMEOUT
  -m METADB, --metadb METADB
  -R, --resetmeta
  -Y, --ignsymlink      Ignore symlink errors
  -v, --verbose
  -D, --dir-only
  --dry-run
```

## Test Scripts

For convenience and platform compatibility testing, a script to run unit tests is included.
This script accepts the same parameters as `python -m unittest`.

For online test, you need a developer Token 😢, which can be set vie the environment variable
`DBXMIRROR_DEVELOPER_TOKEN`. Online tests work out-of-the-box, if your Dropbox has a folder
named `/tmp/test/sync`. Otherwise you can set it to any other folder using `DBXMIRROR_TEST_FOLDER`.

# Limitations

For now, `dbxmirror` is ***download*** only!
