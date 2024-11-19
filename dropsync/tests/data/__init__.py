from collections import OrderedDict
from copy import deepcopy
import datetime

t = datetime.datetime

SIMPLE_1 = {
    "folders": {
        "Test": {
            "folders": {
                "empty": { },
            },
            "files": {
                "bar.txt":   { "data": b"Hello Test folder!", "client_modified": t(2007, 6, 19, 15, 0, 0) },
                "empty.txt": { "data": b"", "client_modified": t(1998, 12, 15, 15, 0, 0) },
            }
        }
    },
    "files": {
        "foo.txt": { "data": b"Hello World!", "client_modified": t(1972, 5, 8, 0, 0, 0)},
    }
}

SIMPLE_EXIST_1 = deepcopy(SIMPLE_1)
SIMPLE_EXIST_1.update({ "target": deepcopy(SIMPLE_1) }) # all files exist

SIMPLE_OVERWRITE_1 = deepcopy(SIMPLE_EXIST_1)
SIMPLE_OVERWRITE_1["target"]["files"]["foo.txt"].update({
    "data": b"Hello Chay-Chay!", "client_modified": t(2016, 1, 3, 13, 4, 0)
})

SIMPLE_REMOVE_1 = deepcopy(SIMPLE_EXIST_1)
SIMPLE_REMOVE_1["target"]["folders"].update({
    "Remove" : {
        "files": {
            "be_gone.txt": { "data": b"Bye bye!", "client_modified": t(2021, 10, 1, 15, 0, 0) },
        }
    }
})
SIMPLE_REMOVE_1["target"]["files"].update({
    "removeme.txt": { "data": b"Adios!", "client_modified": t(1972, 5, 8, 0, 0, 0)},
})

SIMPLE_REMOVE_AND_DELETE_1 = deepcopy(SIMPLE_REMOVE_1)
SIMPLE_REMOVE_AND_DELETE_1.update({
    "deleted": {
        "Remove": {
            # "deleted": { "be_gone.txt": {} }, # Dropbox doesn't return metadata for deleted subentries (yet?)
        },
        "removeme.txt": {},
    }
})

SIMPLE_SYMLINK_1 = deepcopy(SIMPLE_EXIST_1)
SIMPLE_SYMLINK_1["files"].update({
    "symlinked.txt": { "symlink": r"C:\Test\bar.txt", "data": b"", "client_modified": t(2007, 6, 19, 15, 0, 0)},
    "symexist.txt":  { "symlink": r"C:\Test\bar.txt", "data": b"", "client_modified": t(1995, 7, 24, 15, 0, 0)}
})
SIMPLE_SYMLINK_1["target"]["files"].update({
    "symexist.txt":  { "data": b"Leave me alone", "client_modified": t(1996, 11, 10, 15, 0, 0)}
})

SIMPLE_DELETED_1 = deepcopy(SIMPLE_EXIST_1)
SIMPLE_DELETED_1.update({
    "deleted": {
        "imgone.txt": {},
        "iWasAFolder": {},
    }
})

SIMPLE_CASE_SENSITIVITY_1 = {
    "folders": {    
        "Case": {
            "folders": {
                "Sensitive-1": {
                    "files": { "case.txt": { "data": b"Hello World!", "client_modified": t(1972, 5, 8, 0, 0, 0)} }
                }
            }
        },
        "case": {
            "folders": {
                "sensitive-1": {
                    "files": { "case.txt": { "data": b"Hello World!", "client_modified": t(1972, 5, 8, 0, 0, 0)} }
                },
                "sensitive-2": {
                    "files": { "sensitive.txt": { "data": b"Hello World!", "client_modified": t(1972, 5, 8, 0, 0, 0)} }
                }
            }
        },
    }
}

MORE_FILES_1 = {
    "files": {
        "f1.txt": { "data": b"Hello 1!", "client_modified": t(1972, 5, 8, 1, 0, 0)},
        "f2.txt": { "data": b"Hello 2!", "client_modified": t(1972, 5, 8, 2, 0, 0)},
        "f3.txt": { "data": b"Hello 3!", "client_modified": t(1972, 5, 8, 3, 0, 0)},
        "f4.txt": { "data": b"Hello 4!", "client_modified": t(1972, 5, 8, 4, 0, 0)},
        "f5.txt": { "data": b"Hello 5!", "client_modified": t(1972, 5, 8, 5, 0, 0)},
    }
}
