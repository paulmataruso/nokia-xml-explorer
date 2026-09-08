"""
Site Management: a virtual organization layer (folders, tags, site,
auto-detected namespace family) over the flat upload/scp/example file
sources -- purely metadata, never touches the actual files or their
locations, so read-only scp/example files can be organized right
alongside your own uploads without "moving" anything real. Dragging a
file into a folder is just a metadata update, not a filesystem operation.

Persisted as a single JSON file under SITE_MGMT_DIR (a writable runtime
mount, like uploads/ and snapshots/), keyed by filename -- filenames are
already guaranteed globally unique across all three sources (see
_unique_upload_name in main.py), so no separate id scheme is needed for
files. Folders get a short random id since folder names aren't unique.
"""
from __future__ import annotations

import json
import time
import uuid
from pathlib import Path
from typing import Optional

_SRAN_MARKER = b"com.nokia.srbts:"
_LEGACY_MARKERS = (b"NOKLTE:", b"com.nokia.mrbts:")


def detect_family(raw: bytes) -> str:
    """Cheap byte-level namespace scan -- no XML parsing needed, just
    substring presence -- to classify a file as the current unified SRAN
    AirScale object model vs. the older Flexi Zone/BTS Site Manager one.
    Real files can genuinely mix both (see README's note on this), so a
    file with both markers is "mixed" rather than forced into one bucket."""
    has_sran = _SRAN_MARKER in raw
    has_legacy = any(m in raw for m in _LEGACY_MARKERS)
    if has_sran and has_legacy:
        return "mixed"
    if has_sran:
        return "sran"
    if has_legacy:
        return "legacy"
    return "unknown"


def content_snippet(raw: bytes, query: str, context: int = 60) -> Optional[str]:
    """First case-insensitive match of `query` in the raw file text, with a
    little surrounding context for display -- None if it doesn't appear."""
    if not query:
        return None
    text = raw.decode("utf-8", errors="replace")
    idx = text.lower().find(query.lower())
    if idx == -1:
        return None
    start = max(0, idx - context)
    end = min(len(text), idx + len(query) + context)
    snippet = " ".join(text[start:end].split())
    return ("…" if start > 0 else "") + snippet + ("…" if end < len(text) else "")


class SiteManagementStore:
    def __init__(self, path: Path):
        self.path = path
        self._data: dict = {"folders": {}, "files": {}}
        self._load()

    def _load(self) -> None:
        if self.path.exists():
            try:
                self._data = json.loads(self.path.read_text())
            except (json.JSONDecodeError, OSError):
                self._data = {"folders": {}, "files": {}}
        self._data.setdefault("folders", {})
        self._data.setdefault("files", {})

    def _save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(self._data, indent=1, sort_keys=True))
        tmp.replace(self.path)

    # ---- folders ----

    def list_folders(self) -> list[dict]:
        return list(self._data["folders"].values())

    def create_folder(self, name: str, parent_id: Optional[str]) -> dict:
        if parent_id is not None and parent_id not in self._data["folders"]:
            raise KeyError(f"Unknown parent folder {parent_id!r}")
        folder_id = uuid.uuid4().hex[:12]
        folder = {"id": folder_id, "name": name, "parentId": parent_id, "createdAt": time.time()}
        self._data["folders"][folder_id] = folder
        self._save()
        return folder

    def update_folder(
        self, folder_id: str, name: Optional[str], parent_id: Optional[str], parent_id_set: bool
    ) -> dict:
        folder = self._data["folders"].get(folder_id)
        if folder is None:
            raise KeyError(f"Unknown folder {folder_id!r}")
        if name is not None:
            folder["name"] = name
        if parent_id_set:
            if parent_id is not None:
                if parent_id == folder_id:
                    raise ValueError("A folder can't be its own parent")
                if parent_id not in self._data["folders"]:
                    raise KeyError(f"Unknown parent folder {parent_id!r}")
                if self._is_descendant(parent_id, folder_id):
                    raise ValueError("Can't move a folder into its own descendant")
            folder["parentId"] = parent_id
        self._save()
        return folder

    def _is_descendant(self, candidate_id: str, ancestor_id: str) -> bool:
        """True if candidate_id is (transitively) inside ancestor_id --
        guards against creating a cycle when re-parenting a folder."""
        seen: set[str] = set()
        current = self._data["folders"].get(candidate_id)
        while current and current.get("parentId"):
            pid = current["parentId"]
            if pid == ancestor_id:
                return True
            if pid in seen:
                break
            seen.add(pid)
            current = self._data["folders"].get(pid)
        return False

    def delete_folder(self, folder_id: str) -> None:
        if folder_id not in self._data["folders"]:
            raise KeyError(f"Unknown folder {folder_id!r}")
        # Cascade to descendant folders; every file inside any of them goes
        # back to "unfiled" (folderId=None) -- deleting an organizational
        # folder never deletes real file data.
        to_delete = {folder_id}
        changed = True
        while changed:
            changed = False
            for fid, f in self._data["folders"].items():
                if f.get("parentId") in to_delete and fid not in to_delete:
                    to_delete.add(fid)
                    changed = True
        for fid in to_delete:
            self._data["folders"].pop(fid, None)
        for meta in self._data["files"].values():
            if meta.get("folderId") in to_delete:
                meta["folderId"] = None
        self._save()

    # ---- files ----
    #
    # Keyed by "source:filename", NOT filename alone. Real bug this fixes:
    # example/ is a curated copy of specific scp/ files, so several
    # filenames legitimately exist in BOTH sources at once (9 of them, as
    # of this writing) -- with a filename-only key, tagging/filing one
    # silently applied to both, AND (worse) the frontend's React list keyed
    # on bare filename had two elements sharing one key whenever both
    # copies were visible together (e.g. in "All files"), which corrupts
    # React's reconciliation for that list badly enough to leave stale rows
    # rendered even after switching to a view that computes a short,
    # correct list. `source` is never user-supplied -- callers already know
    # it from the file listing itself (GET /api/files, /sitemgmt/tree).

    @staticmethod
    def _key(source: str, filename: str) -> str:
        return f"{source}:{filename}"

    def get_file_meta(self, source: str, filename: str) -> dict:
        meta = self._data["files"].get(self._key(source, filename))
        if meta is None:
            return {"folderId": None, "tags": [], "site": None}
        return {"folderId": meta.get("folderId"), "tags": meta.get("tags", []), "site": meta.get("site")}

    def update_file_meta(
        self,
        source: str,
        filename: str,
        folder_id: Optional[str],
        folder_id_set: bool,
        tags: Optional[list[str]],
        site: Optional[str],
        site_set: bool,
    ) -> dict:
        key = self._key(source, filename)
        meta = self._data["files"].setdefault(key, {"folderId": None, "tags": [], "site": None})
        if folder_id_set:
            if folder_id is not None and folder_id not in self._data["folders"]:
                raise KeyError(f"Unknown folder {folder_id!r}")
            meta["folderId"] = folder_id
        if tags is not None:
            seen: dict[str, str] = {}
            for t in tags:
                t = t.strip()
                if t and t.lower() not in seen:
                    seen[t.lower()] = t
            meta["tags"] = list(seen.values())
        if site_set:
            meta["site"] = site.strip() if site else None
        self._save()
        return self.get_file_meta(source, filename)

    def forget_file(self, source: str, filename: str) -> None:
        """Called when an uploaded file is actually deleted, so metadata
        doesn't accumulate for files that no longer exist."""
        key = self._key(source, filename)
        if key in self._data["files"]:
            del self._data["files"][key]
            self._save()

    def all_tags(self) -> list[str]:
        seen: dict[str, str] = {}
        for meta in self._data["files"].values():
            for t in meta.get("tags", []):
                seen.setdefault(t.lower(), t)
        return sorted(seen.values(), key=str.lower)

    def all_sites(self) -> list[str]:
        seen: dict[str, str] = {}
        for meta in self._data["files"].values():
            s = meta.get("site")
            if s:
                seen.setdefault(s.lower(), s)
        return sorted(seen.values(), key=str.lower)
