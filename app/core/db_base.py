import os
import sqlite3

def migrate_legacy_fb_db(app_dir, legacy_name='socmint_lite.db', new_name='socmint_fb.db'):
    legacy = os.path.join(app_dir, legacy_name)
    new = os.path.join(app_dir, new_name)
    if os.path.exists(new):
        return new
    if os.path.exists(legacy):
        os.rename(legacy, new)
        return new
    return new

def connect(db_file):
    con = sqlite3.connect(db_file)
    con.row_factory = sqlite3.Row
    return con
