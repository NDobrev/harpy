from __future__ import annotations

from harpy.git.diff import parse_unified_diff

DIFF = """\
diff --git a/src/auth/permissions.py b/src/auth/permissions.py
index 111..222 100644
--- a/src/auth/permissions.py
+++ b/src/auth/permissions.py
@@ -10,3 +10,4 @@
 def can_delete(user):
-    return user.is_project_admin
+    return user.is_project_admin or user.is_org_admin
+    # extra
diff --git a/pnpm-lock.yaml b/pnpm-lock.yaml
new file mode 100644
index 000..333
--- /dev/null
+++ b/pnpm-lock.yaml
@@ -0,0 +1,2 @@
+lockfile
+v9
diff --git a/old.bin b/new.bin
Binary files a/old.bin and b/new.bin differ
diff --git a/src/a.py b/src/b.py
rename from src/a.py
rename to src/b.py
--- a/src/a.py
+++ b/src/b.py
@@ -1,1 +1,1 @@
-x
+y
"""


def test_parse_hunk_ids_and_rename() -> None:
    files = parse_unified_diff(DIFF)
    paths = {item.path: item for item in files}
    assert "src/auth/permissions.py" in paths
    auth = paths["src/auth/permissions.py"]
    assert auth.hunks[0].id == "H1"
    assert auth.additions >= 1
    assert paths["pnpm-lock.yaml"].status == "added"
    binary = next(item for item in files if item.is_binary)
    assert binary.is_binary
    renamed = paths["src/b.py"]
    assert renamed.status == "renamed"
    assert renamed.old_path == "src/a.py"
    ids = [hunk.id for file in files for hunk in file.hunks]
    assert ids == ["H1", "H2", "H3"]
