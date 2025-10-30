"""Shared UI helpers for screen_capture."""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk 


class Tooltip:
    """Simple tooltip helper bound to a widget."""

    def __init__(self, widget: tk.Widget, text: str):
        self.widget = widget
        self.text = text
        self.tip: tk.Toplevel | None = None
        widget.bind('<Enter>', self._show)
        widget.bind('<Leave>', self._hide)

    def _show(self, _event=None):
        if self.tip or not self.text:
            return
        x = self.widget.winfo_rootx() + 10
        y = self.widget.winfo_rooty() + self.widget.winfo_height() + 4
        self.tip = tw = tk.Toplevel(self.widget)
        tw.wm_overrideredirect(True)
        tw.wm_geometry(f"+{x}+{y}")
        ttk.Label(tw, text=self.text, background='#ffffe0', relief='solid', borderwidth=1).pack(padx=4, pady=2)

    def _hide(self, _event=None):
        if self.tip:
            self.tip.destroy()
            self.tip = None

class CollapsibleFrame(ttk.Frame):
    """A simple collapsible frame with a header and a content area.
    Usage:
        cf = CollapsibleFrame(parent, text='标题', collapsed=False)
        inner = cf.content  # pack widgets into inner
    """
    def __init__(self, master, text: str = '', collapsed: bool = False, *args, **kwargs):
        super().__init__(master, *args, **kwargs)
        self._collapsed = bool(collapsed)
        self._header = ttk.Frame(self)
        self._header.pack(fill=tk.X)
        self._toggle_btn = ttk.Button(self._header, width=2, text='▾' if not self._collapsed else '▸', command=self._toggle)
        self._toggle_btn.pack(side=tk.LEFT)
        if text:
            ttk.Label(self._header, text=text, font=('Segoe UI', 10, 'bold')).pack(side=tk.LEFT, padx=4)
        self._content_container = ttk.Frame(self)
        if not self._collapsed:
            self._content_container.pack(fill=tk.BOTH, expand=True)

    @property
    def content(self) -> ttk.Frame:
        return self._content_container

    def _toggle(self):
        try:
            self._collapsed = not self._collapsed
            if self._collapsed:
                try: self._content_container.forget()
                except Exception: pass
                self._toggle_btn.config(text='▸')
            else:
                self._content_container.pack(fill=tk.BOTH, expand=True)
                self._toggle_btn.config(text='▾')
        except Exception:
            pass


__all__ = ['Tooltip', 'CollapsibleFrame']
