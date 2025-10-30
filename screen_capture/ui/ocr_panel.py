"""OCR 面板相关的 UI mixin。"""
from __future__ import annotations

from typing import Any, Dict, List

import tkinter as tk
from tkinter import ttk, messagebox
from PIL import Image, ImageTk

from .toolkit import Tooltip
from ..state import OCRPanelState


class OCRPanelMixin:
    """封装 OCR 面板展示与相关交互逻辑。"""

    ocr_state: OCRPanelState

    # ----------------- OCR 面板核心构建 -----------------
    def _ensure_ocr_panel(self, focus_text: bool = False) -> None:
        """懒加载 / 复用 OCR 面板, 嵌入主工作区中部。"""
        if getattr(self, '_ocr_panel_container', None) and self._ocr_panel_container.winfo_exists():
            try:
                panes = self._main_paned.panes()
                if str(self._ocr_panel_container) not in panes:
                    self._main_paned.add(self._ocr_panel_container, weight=5)
                    if hasattr(self, '_ocr_panel_visible'):
                        self._ocr_panel_visible.set(True)
                if focus_text and hasattr(self, '_ocr_text_widget'):
                    self._ocr_text_widget.focus_set()
            except Exception:
                pass
            return

        container = ttk.Frame(self._main_paned)
        self._ocr_panel_container = container
        self._main_paned.add(container, weight=5)

        # 第一行：按钮栏
        btn_bar = ttk.Frame(container)
        btn_bar.pack(fill=tk.X, side=tk.TOP, padx=4, pady=2)
        ttk.Button(btn_bar, text='重新识别', command=self._ocr_rerun).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_bar, text='复制', command=self._ocr_copy_text).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_bar, text='另存为', command=self._ocr_save_text).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_bar, text='过滤空行', command=self._ocr_filter_empty).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_bar, text='统计', command=self._ocr_show_stats).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_bar, text='AI编排', command=self._ocr_ai_refine).pack(side=tk.LEFT, padx=4)
        # 缓存 AI 编排按钮引用，便于根据 AI 可用性启用/禁用
        try:
            self._btn_ocr_ai_refine = btn_bar.winfo_children()[-1]
        except Exception:
            self._btn_ocr_ai_refine = None
        ttk.Button(btn_bar, text='从文件识别…', command=lambda: self._ocr_from_file_via_panel()).pack(side=tk.LEFT, padx=6)
        ttk.Button(btn_bar, text='从文件夹识别…', command=self._perform_ocr_from_folder).pack(side=tk.LEFT, padx=2)
        ttk.Button(btn_bar, text='隐藏面板', command=self.hide_ocr_panel).pack(side=tk.RIGHT, padx=2)

        # 第二行：预览开关 & 置信度过滤
        topbar2 = ttk.Frame(container)
        topbar2.pack(fill=tk.X, side=tk.TOP, padx=4, pady=(0, 2))
        self._preview_visible = True
        self._toggle_preview_btn = ttk.Button(topbar2, text='隐藏预览', command=self._toggle_ocr_preview)
        self._toggle_preview_btn.pack(side=tk.LEFT, padx=2)
        Tooltip(self._toggle_preview_btn, '显示/隐藏左侧预览缩略图区域')

        self._conf_threshold = tk.DoubleVar(value=getattr(self.ocr_state, 'conf_threshold', 0.0))
        ttk.Label(topbar2, text='置信度≥').pack(side=tk.LEFT, padx=(12, 2))
        self._conf_scale = ttk.Scale(
            topbar2,
            from_=0.0,
            to=1.0,
            orient='horizontal',
            length=120,
            variable=self._conf_threshold,
            command=lambda _e: self._apply_conf_filter(),
        )
        self._conf_scale.pack(side=tk.LEFT, padx=2)
        self._conf_label = ttk.Label(topbar2, text=f"{self._conf_threshold.get():.2f}")
        self._conf_label.pack(side=tk.LEFT, padx=2)
        Tooltip(self._conf_scale, '拖动设置最低置信度阈值，低于该值的行不显示 (实时)')

        # 主体：左侧预览 + 右侧 Notebook
        self._ocr_paned = ttk.Panedwindow(container, orient=tk.HORIZONTAL)
        self._ocr_paned.pack(fill=tk.BOTH, expand=True)
        self._ocr_preview_frame = ttk.Frame(self._ocr_paned)
        self._ocr_preview_canvas = tk.Canvas(self._ocr_preview_frame, bg='#111')
        self._ocr_preview_canvas.pack(fill=tk.BOTH, expand=True)
        self._ocr_paned.add(self._ocr_preview_frame, weight=2)

        right = ttk.Frame(self._ocr_paned)
        self._ocr_paned.add(right, weight=3)
        self._ocr_notebook = ttk.Notebook(right)
        self._ocr_notebook.pack(fill=tk.BOTH, expand=True)

        text_tab = ttk.Frame(self._ocr_notebook)
        ocr_text_frame = ttk.Frame(text_tab)
        ocr_text_frame.pack(fill=tk.BOTH, expand=True)
        ocr_scroll = ttk.Scrollbar(ocr_text_frame, orient='vertical')
        self._ocr_text_widget = tk.Text(ocr_text_frame, wrap='word', yscrollcommand=ocr_scroll.set)
        ocr_scroll.config(command=self._ocr_text_widget.yview)
        self._ocr_text_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        ocr_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self._ocr_notebook.add(text_tab, text='结果')

        meta_tab = ttk.Frame(self._ocr_notebook)
        self._ocr_meta_label = ttk.Label(meta_tab, text='无结果', anchor='w', justify='left')
        self._ocr_meta_label.pack(fill=tk.X, padx=6, pady=4)
        self._ocr_notebook.add(meta_tab, text='元信息')

        self._refresh_ocr_meta()
        self._update_ocr_preview_thumb()
        if hasattr(self, '_initial_conf_threshold'):
            try:
                self._conf_threshold.set(float(self._initial_conf_threshold))
                self._apply_conf_filter()
            except Exception:
                pass

        if hasattr(self, '_ocr_panel_visible'):
            try:
                self._ocr_panel_visible.set(True)
            except Exception:
                pass

        if focus_text:
            try:
                self._ocr_text_widget.focus_set()
            except Exception:
                pass

        state = self._ensure_ocr_state()
        state.panel_visible = True
        state.preview_visible = True
        state.conf_threshold = float(self._conf_threshold.get())

        # 初次构建时根据 AI 可用性更新一次按钮状态
        try:
            self.refresh_ai_controls_enabled()
        except Exception:
            pass

    def _ensure_ocr_state(self) -> OCRPanelState:
        if not hasattr(self, 'ocr_state') or not isinstance(self.ocr_state, OCRPanelState):
            self.ocr_state = OCRPanelState()
        return self.ocr_state

    # ----------------- 面板显隐控制 -----------------
    def hide_ocr_panel(self) -> None:
        if getattr(self, '_ocr_panel_container', None) and self._ocr_panel_container.winfo_exists():
            try:
                self._main_paned.forget(self._ocr_panel_container)
            except Exception:
                pass
        if hasattr(self, '_ocr_panel_visible'):
            try:
                self._ocr_panel_visible.set(False)
            except Exception:
                pass
        self._ensure_ocr_state().panel_visible = False
        self._schedule_config_changed()

    def show_ocr_panel(self, focus_text: bool = False) -> None:
        if not getattr(self, '_ocr_panel_container', None) or not self._ocr_panel_container.winfo_exists():
            self._ensure_ocr_panel(focus_text=focus_text)
            return
        panes = self._main_paned.panes()
        if str(self._ocr_panel_container) not in panes:
            try:
                self._main_paned.add(self._ocr_panel_container, weight=5)
            except Exception:
                pass
        if focus_text and hasattr(self, '_ocr_text_widget'):
            try:
                self._ocr_text_widget.focus_set()
            except Exception:
                pass
        if hasattr(self, '_ocr_panel_visible'):
            try:
                self._ocr_panel_visible.set(True)
            except Exception:
                pass
        if hasattr(self, '_pending_ocr_preview_visible'):
            try:
                self._set_ocr_preview_visible(bool(self._pending_ocr_preview_visible))
            except Exception:
                pass
            delattr(self, '_pending_ocr_preview_visible')
        self._ensure_ocr_state().panel_visible = True
        self._schedule_config_changed()

    def _toggle_ocr_panel_visibility(self) -> None:
        try:
            if self._ocr_panel_visible.get():
                self.show_ocr_panel(focus_text=False)
            else:
                self.hide_ocr_panel()
        except Exception:
            pass

    def _toggle_ocr_panel_visibility_kb(self) -> None:
        try:
            cur = False
            if hasattr(self, '_ocr_panel_visible'):
                cur = bool(self._ocr_panel_visible.get())
                self._ocr_panel_visible.set(not cur)
            if cur:
                self.hide_ocr_panel()
            else:
                self.show_ocr_panel(focus_text=False)
        except Exception:
            pass
        if hasattr(self, '_ocr_panel_visible'):
            try:
                self._ocr_panel_visible.set(True)
            except Exception:
                pass

    def _set_ocr_preview_visible(self, flag: bool) -> None:
        try:
            if not hasattr(self, '_ocr_paned') or not hasattr(self, '_ocr_preview_frame'):
                return
            if flag and not getattr(self, '_preview_visible', True):
                try:
                    self._ocr_paned.insert(0, self._ocr_preview_frame, weight=1)
                except Exception:
                    try:
                        self._ocr_paned.add(self._ocr_preview_frame, weight=1)
                    except Exception:
                        pass
                self._preview_visible = True
                if hasattr(self, '_toggle_preview_btn'):
                    self._toggle_preview_btn.config(text='隐藏预览')
                if hasattr(self, '_ocr_preview_visible_var'):
                    self._ocr_preview_visible_var.set(True)
                self._update_ocr_preview_thumb()
            elif (not flag) and getattr(self, '_preview_visible', True):
                try:
                    self._ocr_paned.forget(self._ocr_preview_frame)
                except Exception:
                    pass
                self._preview_visible = False
                if hasattr(self, '_toggle_preview_btn'):
                    self._toggle_preview_btn.config(text='显示预览')
                if hasattr(self, '_ocr_preview_visible_var'):
                    self._ocr_preview_visible_var.set(False)
            self._ensure_ocr_state().preview_visible = bool(self._preview_visible)
            self._schedule_config_changed()
        except Exception:
            pass

    def _toggle_ocr_preview(self) -> None:
        try:
            target = not getattr(self, '_preview_visible', True)
            if not getattr(self, '_ocr_panel_container', None) or not self._ocr_panel_container.winfo_exists():
                self._pending_ocr_preview_visible = target
                if hasattr(self, '_toggle_preview_btn'):
                    self._toggle_preview_btn.config(text='隐藏预览' if target else '显示预览')
                self._ensure_ocr_state().pending_preview_visible = target
                return
            self._set_ocr_preview_visible(target)
        except Exception:
            pass

    # ----------------- 数据刷新 -----------------
    def _apply_conf_filter(self) -> None:
        try:
            if not hasattr(self, '_ocr_text_widget'):
                return
            thr = float(self._conf_threshold.get()) if hasattr(self, '_conf_threshold') else 0.0
            if hasattr(self, '_conf_label'):
                self._conf_label.config(text=f"{thr:.2f}")
            self._ensure_ocr_state().conf_threshold = thr
            all_lines: List[Dict[str, Any]] | None = getattr(self, '_all_ocr_lines', None)
            if all_lines is None:
                return
            kept = [ln for ln in all_lines if (ln.get('score') or 0) >= thr and ln.get('text')]
            self._ocr_text_widget.delete('1.0', tk.END)
            self._ocr_text_widget.insert('1.0', '\n'.join(ln.get('text', '') for ln in kept))
            if hasattr(self, '_ocr_meta_label') and isinstance(self.last_ocr_result, dict):
                meta = self.last_ocr_result.get('meta', {})
                timing = meta.get('timing', {})
                txt = (
                    f"后端: {meta.get('backend')} 模型: {meta.get('model')}\n"
                    f"行数: {len(kept)}/{len(all_lines)} 输入: {timing.get('input_size')}\n"
                    f"耗时: {timing.get('total'):.3f}s (infer {timing.get('infer'):.3f}s post {timing.get('post'):.3f}s)\n"
                )
                self._ocr_meta_label.config(text=txt)
            self._schedule_config_changed()
        except Exception:
            pass

    def _refresh_ocr_meta(self) -> None:
        if not hasattr(self, '_ocr_meta_label'):
            return
        data = self.last_ocr_result or {}
        meta = data.get('meta') if isinstance(data, dict) else None
        lines = data.get('results', []) if isinstance(data, dict) else []
        if not meta:
            self._ocr_meta_label.config(text='无结果')
            return
        timing = meta.get('timing', {})
        txt = (
            f"后端: {meta.get('backend')} 模型: {meta.get('model')}\n"
            f"行数: {len(lines)} 输入: {timing.get('input_size')}\n"
            f"耗时: {timing.get('total'):.3f}s (infer {timing.get('infer'):.3f}s post {timing.get('post'):.3f}s)\n"
        )
        self._ocr_meta_label.config(text=txt)

    def _update_ocr_preview_thumb(self) -> None:
        try:
            if not hasattr(self, '_ocr_preview_canvas'):
                return
            self._ocr_preview_canvas.delete('all')
            raw = getattr(self, 'last_ocr_raw_img', None)
            processed = getattr(self, 'last_ocr_processed_img', None)
            if raw is None and processed is None:
                self._ocr_preview_canvas.create_text(10, 10, anchor='nw', fill='#ccc', text='无缩略')
                return
            w = self._ocr_preview_canvas.winfo_width() or 10
            h = self._ocr_preview_canvas.winfo_height() or 10
            imgs = []
            labels = []
            if raw:
                imgs.append(raw)
                labels.append('原')
            if processed and processed is not raw:
                imgs.append(processed)
                labels.append('后')
            thumb_tks: List[ImageTk.PhotoImage] = []
            cols = max(1, len(imgs))
            cell_w = max(1, w // cols)
            for idx, im in enumerate(imgs):
                iw, ih = im.size
                scale = min(cell_w / iw, h / ih, 1.0)
                tw, th = int(iw * scale), int(ih * scale)
                thumb = im.resize((max(1, tw), max(1, th)), Image.LANCZOS)
                tkimg = ImageTk.PhotoImage(thumb)
                thumb_tks.append(tkimg)
                x = idx * cell_w + (cell_w - tw) // 2
                y = (h - th) // 2
                self._ocr_preview_canvas.create_image(x, y, anchor='nw', image=tkimg)
                self._ocr_preview_canvas.create_text(x + 10, y + 10, anchor='nw', fill='white', text=labels[idx])
            self._ocr_preview_canvas._thumb_refs = thumb_tks  # type: ignore[attr-defined]
        except Exception:
            pass

    # ----------------- AI 辅助功能 -----------------
    def _ocr_ai_refine(self) -> None:
        if not getattr(self, 'ai_client', None) or not self.ai_client or not self.ai_client.ready:
            messagebox.showwarning('AI', 'AI 客户端不可用 (缺少密钥或依赖)')
            return
        if not hasattr(self, '_ocr_text_widget'):
            messagebox.showinfo('AI', '请先完成一次 OCR')
            return
        raw_text = self._ocr_text_widget.get('1.0', tk.END).strip()
        if not raw_text:
            messagebox.showinfo('AI', '无可编排文本')
            return

        dlg = tk.Toplevel(self.ocr_text_window if getattr(self, 'ocr_text_window', None) else self.show)
        dlg.title('AI 编排设置')
        dlg.geometry('360x240+120+120')
        dlg.transient(self.show)
        tk.Label(dlg, text='选择需要的处理:').pack(anchor='w', padx=10, pady=(10, 4))
        v_correct = tk.BooleanVar(value=True)
        v_polish = tk.BooleanVar(value=True)
        v_summary = tk.BooleanVar(value=False)
        ttk.Checkbutton(dlg, text='纠正错别字 / 明显 OCR 误识别', variable=v_correct).pack(anchor='w', padx=16)
        ttk.Checkbutton(dlg, text='润色语句（保持语义不改变）', variable=v_polish).pack(anchor='w', padx=16)
        ttk.Checkbutton(dlg, text='生成要点摘要', variable=v_summary).pack(anchor='w', padx=16)
        tk.Label(dlg, text='可追加指令(可空):').pack(anchor='w', padx=10, pady=(10, 2))
        extra = tk.Text(dlg, height=3, wrap='word')
        extra.pack(fill=tk.BOTH, expand=True, padx=10)
        action_state = {'confirmed': False, 'extra_text': ''}

        def _ok() -> None:
            try:
                action_state['extra_text'] = extra.get('1.0', tk.END).strip()
            except Exception:
                action_state['extra_text'] = ''
            action_state['confirmed'] = True
            dlg.destroy()

        ttk.Button(dlg, text='开始', command=_ok).pack(pady=6)
        dlg.wait_window(dlg)
        if not action_state['confirmed']:
            return

        ops = []
        if v_correct.get():
            ops.append('纠错')
        if v_polish.get():
            ops.append('润色')
        if v_summary.get():
            ops.append('总结要点')
        ops_str = '、'.join(ops) if ops else '保留原文'
        extra_text = action_state.get('extra_text', '')
        prompt = (
            '请对以下 OCR 文本执行:'
            + ops_str
            + '。要求: 如进行纠错需只改明显错误; 润色保持含义; 若有摘要则放在末尾 "摘要:" 段。输出保持原段落结构, 使用 UTF-8。\n'
        )
        if extra_text:
            prompt += f"附加指令: {extra_text}\n"
        MAX_CHARS = 8000
        if len(raw_text) > MAX_CHARS:
            prompt += f"(注意: 文本已截断，仅处理前 {MAX_CHARS} 字)\n"
            raw_clip = raw_text[:MAX_CHARS]
        else:
            raw_clip = raw_text
        messages = [
            {'role': 'user', 'content': [{'type': 'text', 'text': prompt + '\n====OCR原文====\n' + raw_clip}]}
        ]

        if not hasattr(self, '_ocr_notebook'):
            messagebox.showwarning('AI', 'Notebook 未初始化')
            return

        if not hasattr(self, '_ocr_refine_widget') or not getattr(self, '_ocr_refine_widget').winfo_exists():
            refine_tab = ttk.Frame(self._ocr_notebook)
            refine_frame = ttk.Frame(refine_tab)
            refine_frame.pack(fill=tk.BOTH, expand=True)
            refine_scroll = ttk.Scrollbar(refine_frame, orient='vertical')
            self._ocr_refine_widget = tk.Text(refine_frame, wrap='word', yscrollcommand=refine_scroll.set)
            refine_scroll.config(command=self._ocr_refine_widget.yview)
            self._ocr_refine_widget.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
            refine_scroll.pack(side=tk.RIGHT, fill=tk.Y)
            self._ocr_tab_refine = refine_tab
            self._ocr_notebook.add(refine_tab, text='AI编排')
        else:
            if not hasattr(self, '_ocr_tab_refine') or not getattr(self, '_ocr_tab_refine').winfo_exists():
                try:
                    for t in self._ocr_notebook.tabs():
                        if self._ocr_notebook.tab(t, 'text') == 'AI编排':
                            self._ocr_tab_refine = self._ocr_notebook.nametowidget(t)
                            break
                except Exception:
                    pass

        refine_text = self._ocr_refine_widget
        refine_text.delete('1.0', tk.END)
        refine_text.insert('1.0', 'AI 编排中，请稍候...')
        try:
            if hasattr(self, '_ocr_tab_refine') and getattr(self, '_ocr_tab_refine').winfo_exists():
                self._ocr_notebook.select(self._ocr_tab_refine)
            else:
                tabs = self._ocr_notebook.tabs()
                if tabs:
                    self._ocr_notebook.select(tabs[-1])
        except Exception:
            pass

        from ..ai_client import AsyncCall

        def _call() -> Any:
            return self.ai_client.chat(messages)

        def _done(res: Dict[str, Any]) -> None:
            refine_text.delete('1.0', tk.END)
            if 'content' in res:
                refine_text.insert('1.0', res['content'])
            else:
                refine_text.insert('1.0', f"[错误] {res.get('error')}")

        AsyncCall(_call, lambda r: self.show.after(0, lambda: _done(r))).start()

    # 供主类调用，根据 AI 可用性启用/禁用 OCR 面板内的 AI 按钮
    def refresh_ai_controls_enabled(self) -> None:
        try:
            ready = bool(getattr(self, 'ai_client', None) and self.ai_client and getattr(self.ai_client, 'ready', False))
            if hasattr(self, '_btn_ocr_ai_refine') and self._btn_ocr_ai_refine:
                try:
                    self._btn_ocr_ai_refine.config(state=(tk.NORMAL if ready else tk.DISABLED))
                except Exception:
                    pass
        except Exception:
            pass

    # ----------------- 常用操作（按钮回调） -----------------
    def _ocr_rerun(self) -> None:
        """基于当前画面或最近载入的图片重新执行 OCR。"""
        try:
            # 若有最近一次外部图片（via panel），优先使用 perform_ocr() 的常规路径
            # 这里复用主类的 perform_ocr，保持一致的流程与状态更新
            if hasattr(self, 'perform_ocr') and callable(self.perform_ocr):
                self.perform_ocr()
        except Exception:
            pass

    def _ocr_copy_text(self) -> None:
        try:
            if not hasattr(self, '_ocr_text_widget'):
                return
            text = self._ocr_text_widget.get('1.0', tk.END).strip()
            if not text:
                return
            try:
                import pyperclip  # type: ignore
                pyperclip.copy(text)
                messagebox.showinfo('复制', '已复制到剪贴板')
            except Exception:
                # 退回到 Tk 的剪贴板
                try:
                    self.show.clipboard_clear()
                    self.show.clipboard_append(text)
                    messagebox.showinfo('复制', '已复制到剪贴板')
                except Exception:
                    pass
        except Exception:
            pass

    def _ocr_save_text(self) -> None:
        try:
            if not hasattr(self, '_ocr_text_widget'):
                return
            text = self._ocr_text_widget.get('1.0', tk.END).strip()
            if not text:
                messagebox.showinfo('另存为', '没有可保存的文本')
                return
            from tkinter import filedialog
            path = filedialog.asksaveasfilename(defaultextension='.txt', filetypes=[('Text','*.txt'),('All','*.*')])
            if not path:
                return
            with open(path, 'w', encoding='utf-8') as f:
                f.write(text)
            messagebox.showinfo('另存为', f'已保存到\n{path}')
        except Exception:
            pass

    def _ocr_filter_empty(self) -> None:
        try:
            if not hasattr(self, '_ocr_text_widget'):
                return
            text = self._ocr_text_widget.get('1.0', tk.END)
            lines = [ln for ln in text.splitlines() if ln.strip()]
            self._ocr_text_widget.delete('1.0', tk.END)
            self._ocr_text_widget.insert('1.0', '\n'.join(lines))
        except Exception:
            pass

    def _ocr_show_stats(self) -> None:
        try:
            data = getattr(self, 'last_ocr_result', None)
            if not isinstance(data, dict):
                messagebox.showinfo('统计', '暂无结果')
                return
            lines = data.get('results') or []
            meta = data.get('meta') or {}
            cnt = len([ln for ln in lines if (ln.get('text') or '').strip()])
            avg_conf = 0.0
            if lines:
                scores = [float(ln.get('score') or 0) for ln in lines]
                if scores:
                    avg_conf = sum(scores)/len(scores)
            info = (
                f"行数: {cnt}\n"
                f"平均置信度: {avg_conf:.3f}\n"
                f"模型: {meta.get('model')}  后端: {meta.get('backend')}"
            )
            messagebox.showinfo('统计', info)
        except Exception:
            pass


__all__ = ['OCRPanelMixin']
