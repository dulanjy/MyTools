"""图像处理页相关的 UI mixin。"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk


class ProcessingPanelMixin:
    """封装 图像处理 页面的构建与显示/隐藏逻辑。"""

    # ---------- 图像处理“页面” ----------
    def _ensure_process_page(self):
        if hasattr(self, '_proc_ctrl_container') and self._proc_ctrl_container and self._proc_ctrl_container.winfo_exists():
            return
        # 创建左侧控件容器
        self._proc_ctrl_container = ttk.Frame(self._main_paned, width=280)
        frm = self._proc_ctrl_container
        # 头部
        head = ttk.Frame(frm); head.pack(fill=tk.X, padx=8, pady=(8,4))
        ttk.Label(head, text='图像处理', font=('Segoe UI', 10, 'bold')).pack(side=tk.LEFT)
        ttk.Button(head, text='返回预览', command=lambda: self._navigate('preview')).pack(side=tk.RIGHT)
        # 处理器列表
        list_frame = ttk.LabelFrame(frm, text='处理器'); list_frame.pack(fill=tk.BOTH, expand=True, padx=8, pady=6)
        for key, info in self.processors.items():
            var = tk.BooleanVar(value=info.get('enabled', False))
            def _mk_cb(k=key, v=var):
                def _toggle():
                    self.processors[k]['enabled'] = v.get()
                    if v.get() and k not in self.active_processors:
                        self.active_processors.append(k)
                    elif (not v.get()) and k in self.active_processors:
                        self.active_processors.remove(k)
                    self._update_preview()
                return _toggle
            ttk.Checkbutton(list_frame, text=info.get('name', key), variable=var, command=_mk_cb()).pack(anchor='w', padx=6, pady=2)
            # 参数：仅 edges.threshold 暴露
            if key == 'edges':
                thr_var = tk.IntVar(value=info.get('params', {}).get('threshold', 110))
                def _update_thr(_e=None, k=key, v=thr_var):
                    self.processors[k]['params']['threshold'] = v.get(); self._update_preview()
                ttk.Scale(list_frame, from_=10, to=250, orient='horizontal', variable=thr_var, command=lambda _e: _update_thr()).pack(fill=tk.X, padx=18, pady=(0,6))
        # OCR 来源（原/后）
        src_frame = ttk.LabelFrame(frm, text='OCR 来源'); src_frame.pack(fill=tk.X, padx=8, pady=(0,8))
        src_var = tk.StringVar(value='processed' if self.ocr_use_processed else 'raw')
        def _set_src():
            self.ocr_use_processed = (src_var.get() == 'processed')
            if hasattr(self, 'ocr_source_var'):
                self.ocr_source_var.set('后' if self.ocr_use_processed else '原')
        ttk.Radiobutton(src_frame, text='原始图像', value='raw', variable=src_var, command=_set_src).pack(anchor='w', padx=8)
        ttk.Radiobutton(src_frame, text='处理后图像', value='processed', variable=src_var, command=_set_src).pack(anchor='w', padx=8)

    def _show_process_page(self):
        self._ensure_process_page()
        panes = self._main_paned.panes()
        # 把控件容器插入到抽屉之后（index 1），若无抽屉则放最左
        try:
            idx = 1 if hasattr(self, '_drawer_ui') and self._drawer_ui else 0
            if str(self._proc_ctrl_container) not in panes:
                self._main_paned.insert(idx, self._proc_ctrl_container, weight=0)
        except Exception:
            try: self._main_paned.add(self._proc_ctrl_container, weight=0)
            except Exception: pass
        # 恢复处理页的 sash 位置（如果有）
        try:
            if hasattr(self, '_pending_proc_sash'):
                panes = self._main_paned.panes()
                proc_name = str(self._proc_ctrl_container)
                if proc_name in panes:
                    sash_idx = panes.index(proc_name)
                    self._main_paned.sashpos(sash_idx, int(self._pending_proc_sash))
                delattr(self, '_pending_proc_sash')
        except Exception:
            pass

    def _hide_process_page(self):
        if hasattr(self, '_proc_ctrl_container') and self._proc_ctrl_container and self._proc_ctrl_container.winfo_exists():
            try: self._main_paned.forget(self._proc_ctrl_container)
            except Exception: pass

__all__ = ['ProcessingPanelMixin']
