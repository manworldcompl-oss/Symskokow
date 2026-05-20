# flags_cache.py
# Shared PhotoImage cache for tiny flag icons in Tkinter.
# Usage:
#   from flags_cache import FLAG_CACHE
#   img = FLAG_CACHE.get("POL") or FLAG_CACHE.blank()

from pathlib import Path
import tkinter as tk

class _FlagCache:
    def __init__(self, folder: Path | str):
        self.folder = Path(folder)
        self._cache: dict[str, tk.PhotoImage] = {}
        self._blank: tk.PhotoImage | None = None

    def blank(self) -> tk.PhotoImage | None:
        if self._blank is None:
            try:
                img = tk.PhotoImage(width=1, height=1)
                img.put("{#FFFFFF}")
                self._blank = img
            except Exception:
                self._blank = None
        return self._blank

    def get(self, code: str | None):
        code = (code or "").strip().lower()
        if not code:
            return self.blank()
        p = self.folder / f"{code}.png"
        if not p.exists():
            return self.blank()
        key = str(p.resolve())
        if key not in self._cache:
            # Single PhotoImage per file path
            self._cache[key] = tk.PhotoImage(file=str(p))
        return self._cache[key]

    def clear(self):
        # Let Tk/GDI reclaim bitmaps when views are rebuilt
        self._cache.clear()
        self._blank = None

# Create a default, shared instance pointing at ./flags
FLAG_CACHE = _FlagCache("./flags")
