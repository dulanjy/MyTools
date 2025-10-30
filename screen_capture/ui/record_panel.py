"""录制/快照 页面的 UI mixin。"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk


class RecordPanelMixin:
    """封装 录制/快照 页面的构建与显示/隐藏逻辑。
    复用主类已有的 save_snapshot 与 _toggle_recording 行为。
    """

    def _ensure_record_page(self):
        if hasattr(self, '_record_container') and self._record_container and self._record_container.winfo_exists():
            return
        self._record_container = ttk.Frame(self._main_paned, width=300)
        frm = self._record_container
        head = ttk.Frame(frm); head.pack(fill=tk.X, padx=8, pady=(8,4))
        ttk.Label(head, text='录制/快照', font=('Segoe UI', 10, 'bold')).pack(side=tk.LEFT)
        ttk.Button(head, text='返回预览', command=lambda: self._navigate('preview')).pack(side=tk.RIGHT)

        body = ttk.Frame(frm); body.pack(fill=tk.BOTH, expand=True, padx=10, pady=6)
        # 快照
        ttk.Label(body, text='保存当前截图:').pack(anchor='w', pady=(4,2))
        ttk.Button(body, text='📷 保存快照', command=self.save_snapshot).pack(anchor='w')

        # 录制控制
        ttk.Separator(body).pack(fill=tk.X, pady=10)
        ttk.Label(body, text='序列帧录制:').pack(anchor='w', pady=(4,2))
        ttk.Button(body, text='开始/停止录制', command=self._toggle_recording).pack(anchor='w')
        # 简要说明
        help_txt = (
            '录制会按固定间隔将当前区域保存为 PNG 序列到 rec_YYYYMMDD_HHMMSS 目录\n'
            '在“设置”页可调整其它显示项；后续将支持视频编码选项。'
        )
        ttk.Label(body, text=help_txt, justify='left').pack(anchor='w', pady=6)

    def _show_record_page(self):
        self._ensure_record_page()
        try:
            idx = 1 if hasattr(self, '_drawer_ui') and self._drawer_ui else 0
            if str(self._record_container) not in self._main_paned.panes():
                self._main_paned.insert(idx, self._record_container, weight=0)
        except Exception:
            try: self._main_paned.add(self._record_container, weight=0)
            except Exception: pass
        # 隐藏其它页，避免叠加
        try: self._hide_process_page()
        except Exception: pass
        try: self._hide_settings_page()
        except Exception: pass

    def _hide_record_page(self):
        if hasattr(self, '_record_container') and self._record_container and self._record_container.winfo_exists():
            try: self._main_paned.forget(self._record_container)
            except Exception: pass

__all__ = ['RecordPanelMixin']
