"""AI 对话侧栏相关的 mixin。"""
from __future__ import annotations

import threading
from typing import Any, Dict, List
import os, json, time

import tkinter as tk
from tkinter import ttk, messagebox, filedialog

from ..ai_client import AsyncCall
from ..logging_utils import get_logger

logger = get_logger()


class AIChatMixin:
    """封装 AI 对话侧栏与多模态分析逻辑。"""

    def _init_ai_chat(self) -> None:
        self._ai_chat_window = None
        self._chat_sidebar_frame = None
        self._chat_sidebar_hidden = True
        self._ai_docked_in_right = False
        self._ai_chat_history: List[Dict[str, Any]] = []
        self._ai_busy = False
        self._ai_cancel_flag: threading.Event | None = None
        self._ai_cancel_btn: ttk.Button | None = None
        self._ai_status_var: tk.StringVar | None = None
        self._ai_input: tk.Text | None = None
        self._ai_chat_text: tk.Text | None = None
        self._ai_ctx_var: tk.StringVar | None = None
        self._tpl_visible: tk.BooleanVar | None = None
        self._system_prompt = getattr(self, '_system_prompt', '')
        # 图像分析最近一次 Prompt
        self._analysis_prompt_last: str = (
            '请描述这张图片的关键信息，并提取可见文字要点（不必逐字转录），如果发现界面元素请概括其用途。'
        )
        # Watchdog 超时时长（毫秒），用于文本/图像请求 UI 级别防卡死；可根据需要调整
        self._ai_watchdog_ms: int = 60000

    # ---- 显示控制 ----
    def open_ai_chat_window(self) -> None:
        """显示 AI 对话：独立窗口（Toplevel），不再占用主界面布局。"""
        try:
            # 若已存在窗口则聚焦
            if getattr(self, '_ai_chat_window', None) and self._ai_chat_window.winfo_exists():
                try:
                    self._ai_chat_window.deiconify(); self._ai_chat_window.lift(); self._ai_chat_window.focus_force()
                except Exception:
                    pass
                if self._ai_input:
                    try: self._ai_input.focus_set()
                    except Exception: pass
                return
        except Exception:
            pass
        # 构建新窗口
        host = getattr(self, 'show', None)
        win = tk.Toplevel(host)
        self._ai_chat_window = win
        win.title('AI 对话')
        try:
            win.geometry('520x560+120+80')
            win.attributes('-topmost', True)
        except Exception:
            pass
        # 关闭回调
        def _on_close():
            try:
                if hasattr(self, '_ai_sidebar_visible') and self._ai_sidebar_visible is not None:
                    self._ai_sidebar_visible.set(False)
            except Exception:
                pass
            try:
                win.destroy()
            except Exception:
                pass
            self._ai_chat_window = None
        try:
            win.protocol('WM_DELETE_WINDOW', _on_close)
        except Exception:
            pass
        # 内容容器
        container = ttk.Frame(win)
        container.pack(fill=tk.BOTH, expand=True)
        self._build_ai_chat_ui(container)
        # 状态同步：关闭侧栏/右卡片标记
        self._ai_docked_in_right = False
        self._chat_sidebar_hidden = True
        try:
            self._refresh_ai_chat(); self._update_ai_context_stats()
        except Exception:
            pass

    def show_ai_sidebar(self) -> None:
        # 语义替换为“显示 AI 对话窗口”
        try:
            self.open_ai_chat_window()
            if hasattr(self, '_ai_sidebar_visible') and self._ai_sidebar_visible is not None:
                self._ai_sidebar_visible.set(True)
            self._schedule_config_changed()
        except Exception:
            pass

    def hide_ai_sidebar(self) -> None:
        # 语义替换为“隐藏/关闭 AI 对话窗口”
        try:
            if getattr(self, '_ai_chat_window', None) and self._ai_chat_window.winfo_exists():
                try:
                    self._ai_chat_window.destroy()
                except Exception:
                    pass
                self._ai_chat_window = None
            # 同时清理侧栏与右卡片（如曾使用过）
            try:
                if self._chat_sidebar_frame:
                    self._chat_sidebar_frame.forget()
            except Exception:
                pass
            if hasattr(self, '_show_right_card'):
                try: self._show_right_card(None)
                except Exception: pass
            self._chat_sidebar_hidden = True
            if hasattr(self, '_ai_sidebar_visible') and self._ai_sidebar_visible is not None:
                self._ai_sidebar_visible.set(False)
            self._schedule_config_changed()
        except Exception:
            pass

    def _toggle_ai_sidebar_visibility(self) -> None:
        try:
            visible = bool(self._ai_sidebar_visible.get()) if hasattr(self, '_ai_sidebar_visible') else not getattr(self, '_chat_sidebar_hidden', True)
            if visible:
                self.show_ai_sidebar()
            else:
                self.hide_ai_sidebar()
        except Exception:
            pass

    def _toggle_ai_sidebar_visibility_kb(self) -> None:
        try:
            current = not getattr(self, '_chat_sidebar_hidden', True)
            if hasattr(self, '_ai_sidebar_visible') and self._ai_sidebar_visible is not None:
                self._ai_sidebar_visible.set(not current)
            if current:
                self.hide_ai_sidebar()
            else:
                self.show_ai_sidebar()
        except Exception:
            pass

    # ---- 侧栏构建 ----
    def _ensure_chat_sidebar(self) -> None:
        if self._chat_sidebar_frame and self._chat_sidebar_frame.winfo_exists():
            return
        host = getattr(self, 'show')
        side_frame = ttk.Frame(host, width=360)
        side_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=2, pady=2)
        self._chat_sidebar_frame = side_frame
        top_bar = ttk.Frame(side_frame)
        top_bar.pack(fill=tk.X, padx=4, pady=4)
        ttk.Label(top_bar, text='AI 对话').pack(side=tk.LEFT)
        ttk.Button(top_bar, text='系统指令', command=self._open_system_prompt_dialog).pack(side=tk.LEFT, padx=2)
        self._ai_cancel_btn = ttk.Button(top_bar, text='取消', state=tk.DISABLED, command=self._ai_cancel_request)
        self._ai_cancel_btn.pack(side=tk.RIGHT, padx=2)
        ttk.Button(top_bar, text='发送OCR', command=self._ai_send_ocr_text).pack(side=tk.RIGHT, padx=2)
        ttk.Button(top_bar, text='发送', command=self._ai_chat_send).pack(side=tk.RIGHT, padx=2)
        status = '就绪' if getattr(self, 'ai_client', None) and self.ai_client and self.ai_client.ready else '不可用'
        self._ai_status_var = tk.StringVar(value=status)
        ttk.Label(top_bar, textvariable=self._ai_status_var).pack(side=tk.LEFT, padx=4)

        chat_frame = ttk.Frame(side_frame)
        chat_frame.pack(fill=tk.BOTH, expand=True, padx=4, pady=(0, 4))
        chat_scroll = ttk.Scrollbar(chat_frame, orient='vertical')
        self._ai_chat_text = tk.Text(chat_frame, wrap='word', state='disabled', yscrollcommand=chat_scroll.set)
        chat_scroll.config(command=self._ai_chat_text.yview)
        self._ai_chat_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        chat_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        try:
            self._ai_chat_text.tag_config('user', foreground='#1a4b7a')
            self._ai_chat_text.tag_config('assistant', foreground='#2d6630')
            self._ai_chat_text.tag_config('error', foreground='#b50000')
            self._ai_chat_text.tag_config('meta', foreground='#666666', font=('Consolas', 9, 'italic'))
        except Exception:
            pass

        tpl_container = ttk.Frame(side_frame)
        tpl_container.pack(fill=tk.X, padx=4, pady=(0, 2))
        self._tpl_visible = tk.BooleanVar(value=True)

        def _toggle_tpl():
            if not self._tpl_visible:
                return
            vis = self._tpl_visible.get()
            if vis:
                tpl_frame.pack(fill=tk.X, padx=2, pady=(0, 2))
                btn_toggle.config(text='隐藏模板')
            else:
                tpl_frame.pack_forget()
                btn_toggle.config(text='显示模板')

        btn_toggle = ttk.Checkbutton(tpl_container, text='隐藏模板', command=_toggle_tpl, variable=self._tpl_visible, onvalue=True, offvalue=False)
        btn_toggle.pack(side=tk.LEFT)
        tpl_frame = ttk.Frame(tpl_container)
        tpl_frame.pack(fill=tk.X, padx=2)
        templates = [
            ('总结', '请用要点总结以上 OCR 内容。'),
            ('翻译EN', '请将以上文本翻译成英文，并保持原意。'),
            ('提取关键', '从以上文本中提取关键信息(人物/时间/数字/结论)。'),
            ('待办', '请把以上内容整理成可执行的TODO列表。'),
            ('润色', '请润色以上文本，使其更通顺专业。'),
        ]

        def _apply_template(text: str) -> None:
            if not self._ai_input:
                return
            current = self._ai_input.get('1.0', tk.END).strip()
            insert_text = text if not current else '\n' + text
            self._ai_input.insert(tk.END, insert_text)
            self._ai_input.focus()

        for label, txt in templates:
            ttk.Button(tpl_frame, text=label, width=6, command=lambda s=txt: _apply_template(s)).pack(side=tk.LEFT, padx=2)

        entry_frame = ttk.Frame(side_frame)
        entry_frame.pack(fill=tk.X, padx=4, pady=(0, 4))
        input_scroll = ttk.Scrollbar(entry_frame, orient='vertical')
        self._ai_input = tk.Text(entry_frame, height=4, wrap='word', yscrollcommand=input_scroll.set)
        input_scroll.config(command=self._ai_input.yview)
        self._ai_input.pack(side=tk.LEFT, fill=tk.X, expand=True)
        input_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self._ai_input.bind('<Control-Return>', lambda _e: (self._ai_chat_send(), 'break'))

        ctx_bar = ttk.Frame(side_frame)
        ctx_bar.pack(fill=tk.X, padx=4, pady=(0, 4))
        self._ai_ctx_var = tk.StringVar(value='上下文: 0 msg / 0 chars')
        ttk.Label(ctx_bar, textvariable=self._ai_ctx_var).pack(side=tk.LEFT)
        ttk.Button(ctx_bar, text='清理历史', command=self._ai_clear_history).pack(side=tk.RIGHT)

        def _collapse():
            try:
                side_frame.forget()
                self._chat_sidebar_hidden = True
                if hasattr(self, '_ai_sidebar_visible') and self._ai_sidebar_visible is not None:
                    self._ai_sidebar_visible.set(False)
            except Exception:
                pass

        ttk.Button(top_bar, text='折叠', command=_collapse).pack(side=tk.LEFT, padx=2)

    def _build_ai_chat_ui(self, cont: ttk.Frame) -> None:
        """在给定容器中构建 AI 聊天 UI（供窗口/侧栏/卡片复用）。"""
        # 先清空容器（以便复用）
        try:
            for w in cont.winfo_children():
                w.destroy()
        except Exception:
            pass

        top_bar = ttk.Frame(cont)
        top_bar.pack(fill=tk.X, padx=4, pady=4)
        ttk.Label(top_bar, text='AI 对话').pack(side=tk.LEFT)
        ttk.Button(top_bar, text='系统指令', command=self._open_system_prompt_dialog).pack(side=tk.LEFT, padx=2)
        # 图像分析下拉按钮
        analyze_mb = tk.Menubutton(top_bar, text='图像分析', relief='raised')
        analyze_menu = tk.Menu(analyze_mb, tearoff=False)
        # 使用 after 延迟执行，避免菜单的 grab 与后续弹窗/文件对话框发生冲突
        analyze_menu.add_command(
            label='分析当前画面',
            command=lambda: self.show.after_idle(lambda: self.show.after(0, self._cmd_analyze_current_with_prompt))
        )
        analyze_menu.add_command(
            label='选择图片分析...',
            command=lambda: self.show.after_idle(lambda: self.show.after(0, self._cmd_analyze_file_with_prompt))
        )
        analyze_menu.add_command(
            label='粘贴板图片分析',
            command=lambda: self.show.after_idle(lambda: self.show.after(0, self._cmd_analyze_clipboard_with_prompt))
        )
        analyze_menu.add_separator()
        analyze_menu.add_command(
            label='课堂行为分析（智能一键）...',
            command=lambda: self.show.after_idle(lambda: self.show.after(0, self._cmd_analyze_classroom_smart))
        )
        analyze_menu.add_command(
            label='从 JSON 渲染可视化...',
            command=lambda: self.show.after_idle(lambda: self.show.after(0, self._cmd_render_visual_from_json))
        )
        analyze_mb.config(menu=analyze_menu)
        analyze_mb.pack(side=tk.LEFT, padx=2)
        # 置顶开关（仅在独立窗口下有效）
        def _toggle_topmost():
            try:
                win = getattr(self, '_ai_chat_window', None)
                if win and win.winfo_exists():
                    win.attributes('-topmost', bool(self._ai_topmost_var.get()))
            except Exception:
                pass
        self._ai_topmost_var = tk.BooleanVar(value=True)
        ttk.Checkbutton(top_bar, text='置顶', variable=self._ai_topmost_var, command=_toggle_topmost).pack(side=tk.LEFT, padx=6)
        self._ai_cancel_btn = ttk.Button(top_bar, text='取消', state=tk.DISABLED, command=self._ai_cancel_request)
        self._ai_cancel_btn.pack(side=tk.RIGHT, padx=2)
        ttk.Button(top_bar, text='发送OCR', command=self._ai_send_ocr_text).pack(side=tk.RIGHT, padx=2)
        ttk.Button(top_bar, text='发送', command=self._ai_chat_send).pack(side=tk.RIGHT, padx=2)
        status = '就绪' if getattr(self, 'ai_client', None) and self.ai_client and self.ai_client.ready else '不可用'
        self._ai_status_var = tk.StringVar(value=status)
        ttk.Label(top_bar, textvariable=self._ai_status_var).pack(side=tk.LEFT, padx=4)

        # 模板快捷区（与侧栏一致的逻辑）
        tpl_container = ttk.Frame(cont)
        tpl_container.pack(fill=tk.X, padx=4, pady=(0, 2))
        # 可见性状态
        self._tpl_visible = tk.BooleanVar(value=True)
        def _toggle_tpl():
            if not self._tpl_visible:
                return
            vis = self._tpl_visible.get()
            if vis:
                tpl_frame.pack(fill=tk.X, padx=2, pady=(0, 2))
                btn_toggle.config(text='隐藏模板')
            else:
                tpl_frame.pack_forget()
                btn_toggle.config(text='显示模板')
        btn_toggle = ttk.Checkbutton(tpl_container, text='隐藏模板', command=_toggle_tpl, variable=self._tpl_visible, onvalue=True, offvalue=False)
        btn_toggle.pack(side=tk.LEFT)
        tpl_frame = ttk.Frame(tpl_container)
        tpl_frame.pack(fill=tk.X, padx=2)
        templates = [
            ('总结', '请用要点总结以上 OCR 内容。'),
            ('翻译EN', '请将以上文本翻译成英文，并保持原意。'),
            ('提取关键', '从以上文本中提取关键信息(人物/时间/数字/结论)。'),
            ('待办', '请把以上内容整理成可执行的TODO列表。'),
            ('润色', '请润色以上文本，使其更通顺专业。'),
        ]
        def _apply_template(text: str) -> None:
            if not self._ai_input:
                return
            current = self._ai_input.get('1.0', tk.END).strip()
            insert_text = text if not current else '\n' + text
            self._ai_input.insert(tk.END, insert_text)
            self._ai_input.focus()
        for label, txt in templates:
            ttk.Button(tpl_frame, text=label, width=6, command=lambda s=txt: _apply_template(s)).pack(side=tk.LEFT, padx=2)

        chat_frame = ttk.Frame(cont)
        chat_frame.pack(fill=tk.BOTH, expand=True, padx=4, pady=(0, 4))
        chat_scroll = ttk.Scrollbar(chat_frame, orient='vertical')
        self._ai_chat_text = tk.Text(chat_frame, wrap='word', state='disabled', yscrollcommand=chat_scroll.set, height=12)
        chat_scroll.config(command=self._ai_chat_text.yview)
        self._ai_chat_text.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        chat_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        try:
            self._ai_chat_text.tag_config('user', foreground='#1a4b7a')
            self._ai_chat_text.tag_config('assistant', foreground='#2d6630')
            self._ai_chat_text.tag_config('error', foreground='#b50000')
            self._ai_chat_text.tag_config('meta', foreground='#666666', font=('Consolas', 9, 'italic'))
        except Exception:
            pass

        entry_frame = ttk.Frame(cont)
        entry_frame.pack(fill=tk.X, padx=4, pady=(0, 4))
        input_scroll = ttk.Scrollbar(entry_frame, orient='vertical')
        self._ai_input = tk.Text(entry_frame, height=4, wrap='word', yscrollcommand=input_scroll.set)
        input_scroll.config(command=self._ai_input.yview)
        self._ai_input.pack(side=tk.LEFT, fill=tk.X, expand=True)
        input_scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self._ai_input.bind('<Control-Return>', lambda _e: (self._ai_chat_send(), 'break'))

        ctx_bar = ttk.Frame(cont)
        ctx_bar.pack(fill=tk.X, padx=4, pady=(0, 4))
        self._ai_ctx_var = tk.StringVar(value='上下文: 0 msg / 0 chars')
        ttk.Label(ctx_bar, textvariable=self._ai_ctx_var).pack(side=tk.LEFT)
        ttk.Button(ctx_bar, text='清理历史', command=self._ai_clear_history).pack(side=tk.RIGHT)

    # ---- 工具：从 JSON 文件直接渲染可视化 ----
    def _cmd_render_visual_from_json(self) -> None:
        host = getattr(self, '_ai_chat_window', None) or self.show
        try:
            from tkinter import filedialog
            json_path = filedialog.askopenfilename(
                parent=host,
                title='选择课堂分析 JSON（将生成 _summary.png）',
                filetypes=[('JSON Files', '*.json'), ('All Files', '*.*')]
            )
        except Exception:
            json_path = ''
        if not json_path:
            return
        try:
            base = os.path.splitext(os.path.basename(json_path))[0]
            default_dir = self._get_analyze_images_dir()
            default_png = os.path.join(default_dir, f"{base}_summary.png")
            from tkinter import filedialog
            out_path = filedialog.asksaveasfilename(
                parent=host,
                title='选择输出 PNG 路径',
                defaultextension='.png',
                filetypes=[('PNG Image', '*.png')],
                initialdir=default_dir,
                initialfile=os.path.basename(default_png)
            )
        except Exception:
            out_path = ''
        if not out_path:
            return
        try:
            try:
                from ...student_behavior_ai.visualize import render_report_image_from_file
            except Exception:
                from student_behavior_ai.visualize import render_report_image_from_file
            render_report_image_from_file(json_path, out_path, title='课堂行为分析')
            messagebox.showinfo('完成', f'已生成：\n{out_path}')
        except Exception as e:
            messagebox.showerror('渲染失败', str(e))

    # ---- 聊天逻辑 ----
    def _append_ai_chat(self, role: str, content: str) -> None:
        self._ai_chat_history.append({'role': role, 'content': content})
        self._refresh_ai_chat()

    def _refresh_ai_chat(self) -> None:
        if not self._ai_chat_text:
            return
        try:
            history = self._ai_chat_history[-200:]
            self._ai_chat_text.config(state='normal')
            self._ai_chat_text.delete('1.0', tk.END)
            for msg in history:
                role = msg.get('role', 'assistant')
                raw_content = str(msg.get('content', '')).strip()
                prefix = '你: ' if role == 'user' else 'AI: '
                start = self._ai_chat_text.index(tk.END)
                self._ai_chat_text.insert(tk.END, prefix + raw_content + '\n')
                end = self._ai_chat_text.index(tk.END)
                tag = 'assistant'
                if role == 'user':
                    tag = 'user'
                if raw_content.startswith('[错误]'):
                    tag = 'error'
                try:
                    self._ai_chat_text.tag_add(tag, start, end)
                except Exception:
                    pass
            self._ai_chat_text.config(state='disabled')
            self._ai_chat_text.see(tk.END)
        except Exception:
            pass

    def _ai_chat_send(self, allow_resend_last: bool = False):  # type: ignore[override]
        if not getattr(self, 'ai_client', None) or not self.ai_client or not self.ai_client.ready:
            messagebox.showwarning('AI', 'AI 客户端不可用 (缺少密钥或依赖)')
            return
        if self._ai_busy:
            return
        raw_input = self._ai_input.get('1.0', tk.END).strip() if self._ai_input else ''
        if raw_input:
            if self._ai_input:
                self._ai_input.delete('1.0', tk.END)
            self._append_ai_chat('user', raw_input)
        else:
            if not (allow_resend_last and self._ai_chat_history and self._ai_chat_history[-1]['role'] == 'user'):
                return
        self._ai_busy = True
        if self._ai_status_var:
            self._ai_status_var.set('生成中...')
        if self._ai_cancel_btn:
            self._ai_cancel_btn.config(state=tk.NORMAL)
        self._ai_cancel_flag = threading.Event()

        def _call():
            messages: List[Dict[str, Any]] = []
            if getattr(self, '_system_prompt', ''):
                messages.append({'role': 'system', 'content': [{'type': 'text', 'text': self._system_prompt}]})
            for msg in self._ai_chat_history:
                messages.append({'role': msg['role'], 'content': [{'type': 'text', 'text': msg['content']}]} )
            return self.ai_client.chat(messages)

        def _finalize(result: Dict[str, Any], cancelled: bool = False):
            self._ai_busy = False
            if self._ai_cancel_btn:
                self._ai_cancel_btn.config(state=tk.DISABLED)
            if self._ai_status_var:
                self._ai_status_var.set('就绪' if not cancelled else '已取消')
            if cancelled:
                self._append_ai_chat('assistant', '[错误] 用户已取消')
            else:
                if 'content' in result:
                    self._append_ai_chat('assistant', result['content'])
                    try:
                        from ..event_bus import get_global_bus
                        get_global_bus().emit('ai_reply', {
                            'ok': True,
                            'content': result.get('content', ''),
                            'total_messages': len(self._ai_chat_history),
                        })
                    except Exception:
                        pass
                else:
                    err_msg = f"[错误] {result.get('error')}"
                    self._append_ai_chat('assistant', err_msg)
                    try:
                        from ..event_bus import get_global_bus
                        get_global_bus().emit('ai_reply', {
                            'ok': False,
                            'error': result.get('error'),
                            'total_messages': len(self._ai_chat_history),
                        })
                    except Exception:
                        pass
            self._update_status_bar('AI', '就绪' if not cancelled else '取消')
            self._update_ai_context_stats()

        def _wrapped(res: Dict[str, Any]):
            # 取消看门狗
            try:
                if hasattr(self, '_ai_watchdog_after_id') and self._ai_watchdog_after_id:
                    self.show.after_cancel(self._ai_watchdog_after_id)
                    self._ai_watchdog_after_id = None
            except Exception:
                pass
            if self._ai_cancel_flag and self._ai_cancel_flag.is_set():
                _finalize(res, cancelled=True)
            else:
                _finalize(res, cancelled=False)

        # 启动后台调用
        AsyncCall(_call, lambda r: self.show.after(0, lambda: _wrapped(r))).start()

        # 看门狗：若 35s 仍未返回，则主动结束为超时，避免 UI 长时间处于忙碌
        def _watchdog_timeout():
            try:
                self._ai_watchdog_after_id = None
            except Exception:
                pass
            if self._ai_busy:
                _finalize({"error": "分析超时"}, cancelled=False)

        try:
            self._ai_watchdog_after_id = self.show.after(getattr(self, '_ai_watchdog_ms', 60000), _watchdog_timeout)
        except Exception:
            self._ai_watchdog_after_id = None

    def _ai_send_ocr_text(self) -> None:
        lines = []
        if hasattr(self, '_all_ocr_lines') and getattr(self, '_all_ocr_lines'):
            lines = [ln.get('text', '') for ln in self._all_ocr_lines if ln.get('text')]
        if not lines:
            messagebox.showinfo('AI', '无可用 OCR 文本，请先执行 OCR')
            return
        content = '\n'.join(lines)[:4000]
        self._append_ai_chat('user', f"以下为OCR结果，请帮我总结或回答问题：\n{content}")
        self._ai_chat_send(allow_resend_last=True)

    def _ai_clear_history(self) -> None:
        if self._ai_busy:
            messagebox.showinfo('AI', '正在生成中，稍后再清理')
            return
        self._ai_chat_history = []
        self._refresh_ai_chat()
        self._update_ai_context_stats()

    def _update_ai_context_stats(self) -> None:
        if not self._ai_ctx_var:
            return
        try:
            chars = sum(len(str(m.get('content', ''))) for m in self._ai_chat_history)
            self._ai_ctx_var.set(f'上下文: {len(self._ai_chat_history)} msg / {chars} chars')
        except Exception:
            pass

    def _ai_cancel_request(self) -> None:
        if self._ai_cancel_flag and not self._ai_cancel_flag.is_set():
            self._ai_cancel_flag.set()
        if self._ai_cancel_btn:
            self._ai_cancel_btn.config(state=tk.DISABLED)
        if self._ai_status_var:
            self._ai_status_var.set('取消中')

    def _open_system_prompt_dialog(self) -> None:
        host = self._ai_chat_window if getattr(self, '_ai_chat_window', None) else self.show
        win = tk.Toplevel(host)
        win.title('系统指令设置')
        win.geometry('420x260+140+120')
        win.transient(self.show)
        ttk.Label(win, text='为本会话设定系统指令 (角色/风格/输出格式):').pack(anchor='w', padx=8, pady=(8, 4))
        txt = tk.Text(win, height=8, wrap='word')
        txt.pack(fill=tk.BOTH, expand=True, padx=8)
        if getattr(self, '_system_prompt', ''):
            txt.insert('1.0', self._system_prompt)

        def _apply():
            self._system_prompt = txt.get('1.0', tk.END).strip()
            win.destroy()

        btn_bar = ttk.Frame(win)
        btn_bar.pack(fill=tk.X, padx=8, pady=6)
        ttk.Button(btn_bar, text='清空', command=lambda: txt.delete('1.0', tk.END)).pack(side=tk.LEFT)
        ttk.Button(btn_bar, text='应用', command=_apply).pack(side=tk.RIGHT)

    def analyze_current_frame(self, prompt: str | None = None) -> None:
        """分析当前捕获的画面(self.last_pil)。"""
        if not getattr(self, 'ai_client', None) or not self.ai_client or not self.ai_client.ready:
            try:
                logger.warning("[AI] 客户端未就绪：缺少密钥或依赖。")
            except Exception:
                pass
            messagebox.showwarning('AI', 'AI 客户端未就绪（缺少密钥或依赖），已取消。')
            return
        img = getattr(self, 'last_pil', None)
        if not img:
            messagebox.showinfo('AI', '当前无画面')
            return
        # 没有可用文件路径，自动可视化时将回退到工作目录
        self._auto_viz_hint_path = None
        self.analyze_image_pil(img, prompt=prompt, title='AI 图像分析 - 当前画面')

    # ---- 图像分析扩展 ----
    def analyze_text_prompt(self, prompt: str, title: str = 'AI 文本分析') -> None:
        """仅文本分析弹窗（当没有图片，只有 JSON/计数/空间分布时）。"""
        if not getattr(self, 'ai_client', None) or not self.ai_client or not self.ai_client.ready:
            try:
                logger.warning("[AI] 客户端未就绪：缺少密钥或依赖。")
            except Exception:
                pass
            messagebox.showwarning('AI', 'AI 客户端未就绪（缺少密钥或依赖），已取消。')
            return
        if self._ai_busy:
            return
        self._ai_busy = True
        if hasattr(self, '_ai_cancel_btn') and self._ai_cancel_btn:
            try:
                self._ai_cancel_btn.config(state=tk.NORMAL)
            except Exception:
                pass
        self._ai_cancel_flag = threading.Event()
        if hasattr(self, '_ai_status_var') and self._ai_status_var:
            try:
                self._ai_status_var.set('生成中...')
            except Exception:
                pass
        top = tk.Toplevel(self.show)
        top.title(title)
        top.geometry('540x380+140+140')
        try:
            top.attributes('-topmost', True)
        except Exception:
            pass
        info = tk.Text(top, wrap='word')
        info.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)
        info.insert('1.0', '生成中，请稍候...')
        btn_bar_main = ttk.Frame(top)
        btn_bar_main.pack(fill=tk.X, padx=6, pady=(0, 6))
        def _copy_content():
            try:
                text = info.get('1.0', tk.END).strip()
                top.clipboard_clear(); top.clipboard_append(text)
            except Exception:
                pass
        def _save_as():
            try:
                from tkinter import filedialog
                path = filedialog.asksaveasfilename(
                    parent=top,
                    title='另存为',
                    defaultextension='.md',
                    filetypes=[('Markdown', '*.md'), ('Text', '*.txt'), ('All Files', '*.*')]
                )
            except Exception:
                path = ''
            if not path:
                return
            try:
                with open(path, 'w', encoding='utf-8') as f:
                    f.write(info.get('1.0', tk.END))
            except Exception as e:
                messagebox.showerror('保存失败', str(e))
        ttk.Button(btn_bar_main, text='复制内容', command=_copy_content).pack(side=tk.RIGHT, padx=4)
        ttk.Button(btn_bar_main, text='另存为...', command=_save_as).pack(side=tk.RIGHT)

        def _save_json_and_visualize():
            try:
                raw = info.get('1.0', tk.END).strip()
                if not raw:
                    messagebox.showwarning('保存 JSON', '当前内容为空')
                    return
                try:
                    data = json.loads(raw)
                except Exception:
                    # 与 analyze_image_pil 同步的 JSON 提取逻辑
                    def _try_extract_json(text: str):
                        try:
                            import re
                            m = re.search(r"```json\s*(\{[\s\S]*?\})\s*```", text, re.IGNORECASE)
                            if not m:
                                m = re.search(r"```\s*(\{[\s\S]*?\})\s*```", text, re.IGNORECASE)
                            if m:
                                return json.loads(m.group(1))
                        except Exception:
                            pass
                        try:
                            first = text.find('{')
                            while first != -1:
                                depth = 0; in_str = False; esc = False
                                for i in range(first, len(text)):
                                    ch = text[i]
                                    if in_str:
                                        if esc:
                                            esc = False
                                        elif ch == '\\':
                                            esc = True
                                        elif ch == '"':
                                            in_str = False
                                    else:
                                        if ch == '"':
                                            in_str = True
                                        elif ch == '{':
                                            depth += 1
                                        elif ch == '}':
                                            depth -= 1
                                            if depth == 0:
                                                cand = text[first:i+1]
                                                try:
                                                    return json.loads(cand)
                                                except Exception:
                                                    break
                                first = text.find('{', first + 1)
                        except Exception:
                            pass
                        return None
                    data = _try_extract_json(raw)
                    if data is None:
                        messagebox.showerror('保存 JSON', '内容不是合法 JSON，且未能从文本中提取有效的 JSON。')
                        return
                try:
                    # 预填建议文件名
                    base_hint = getattr(self, '_auto_viz_hint_path', None)
                    base = self._suggest_report_basename(data, base_hint)
                    jp, pp = self._ensure_unique_pair(base)
                    # 指向默认 analyze_images 目录
                    initialdir = self._get_analyze_images_dir()
                    initialfile = os.path.basename(jp)
                    json_path = filedialog.asksaveasfilename(
                        parent=top,
                        title='另存为 JSON 并生成可视化图',
                        defaultextension='.json',
                        filetypes=[('JSON', '*.json'), ('All Files', '*.*')],
                        initialdir=initialdir,
                        initialfile=initialfile
                    )
                except Exception:
                    json_path = ''
                if not json_path:
                    return
                try:
                    # 注入 provenance：AI 文本
                    if isinstance(data, dict):
                        try:
                            prov = data.get('provenance') if isinstance(data.get('provenance'), dict) else None
                        except Exception:
                            prov = None
                        if not prov:
                            data['provenance'] = {
                                'generated_by': 'ai',
                                'model': getattr(self.ai_client, 'model_text', ''),
                                'timestamp': time.strftime('%Y-%m-%d %H:%M:%S')
                            }
                    with open(json_path, 'w', encoding='utf-8') as f:
                        f.write(json.dumps(data, ensure_ascii=False, indent=2))
                except Exception as e:
                    messagebox.showerror('保存 JSON', f'写入失败：{e}')
                    return
                base, _ = os.path.splitext(json_path)
                png_path = base + '_summary.png'
                try:
                    from ...student_behavior_ai.visualize import render_report_image
                except Exception:
                    try:
                        from student_behavior_ai.visualize import render_report_image
                    except Exception as e:
                        messagebox.showerror('生成可视化图', f'找不到可视化模块：{e}')
                        return
                try:
                    title_text = title if isinstance(title, str) else '课堂行为分析'
                    render_report_image(data, png_path, title=title_text)
                except Exception as e:
                    messagebox.showerror('生成可视化图', f'渲染失败：{e}')
                    return
                messagebox.showinfo('完成', f'已保存：\nJSON: {json_path}\n图像: {png_path}')
            except Exception as e:
                messagebox.showerror('保存 JSON / 可视化', str(e))
        ttk.Button(btn_bar_main, text='另存为 JSON → 生成可视化图', command=_save_json_and_visualize).pack(side=tk.RIGHT, padx=4)

        def _call():
            if self._ai_cancel_flag and self._ai_cancel_flag.is_set():
                return {"error": "已取消"}
            try:
                logger.info(f"[AI-TXT] {time.strftime('%Y-%m-%d %H:%M:%S')} SEND text chat")
            except Exception:
                pass
            messages = [{'role': 'user', 'content': [{'type': 'text', 'text': prompt}]}]
            return self.ai_client.chat(messages)

        def _finalize(result: Dict[str, Any], cancelled: bool = False):
            self._ai_busy = False
            if hasattr(self, '_ai_cancel_btn') and self._ai_cancel_btn:
                try:
                    self._ai_cancel_btn.config(state=tk.DISABLED)
                except Exception:
                    pass
            if hasattr(self, '_ai_status_var') and self._ai_status_var:
                try:
                    self._ai_status_var.set('已取消' if cancelled else '就绪')
                except Exception:
                    pass
            info.delete('1.0', tk.END)
            if cancelled:
                info.insert('1.0', '已取消')
                return
            if 'content' in result:
                info.insert('1.0', result['content'])
                # 若期望严格 JSON 而模型未输出 JSON，则使用本地模板回退弹窗
                try:
                    parsed = self._extract_json_from_text(result['content'])
                except Exception:
                    parsed = None
                try:
                    fb = getattr(self, '_json_enforce_fallback', None)
                    if parsed is None and isinstance(fb, dict) and fb:
                        # 立即弹出本地模板结果窗口，用户仍可在当前窗口查看原始回答
                        self._show_json_result_window(fb, title=(title + '（本地模板）') if isinstance(title, str) else '本地模板', base_hint=getattr(self, '_auto_viz_hint_path', None))
                except Exception:
                    pass
                finally:
                    try:
                        self._json_enforce_fallback = None
                    except Exception:
                        pass
            else:
                err_text = f"[错误] {result.get('error')}"
                info.insert('1.0', err_text)
                btn_bar = ttk.Frame(top)
                btn_bar.pack(fill=tk.X, padx=6, pady=(0, 6))
                def _copy_err():
                    try:
                        top.clipboard_clear(); top.clipboard_append(err_text)
                    except Exception:
                        pass
                ttk.Button(btn_bar, text='复制错误信息', command=_copy_err).pack(side=tk.RIGHT)

        def _wrapped(res: Dict[str, Any]):
            try:
                if hasattr(self, '_ai_watchdog_after_id') and self._ai_watchdog_after_id:
                    self.show.after_cancel(self._ai_watchdog_after_id)
                    self._ai_watchdog_after_id = None
            except Exception:
                pass
            try:
                logger.info(f"[AI-TXT] {time.strftime('%Y-%m-%d %H:%M:%S')} RECV text chat response")
            except Exception:
                pass
            if self._ai_cancel_flag and self._ai_cancel_flag.is_set():
                _finalize(res, cancelled=True)
            else:
                _finalize(res, cancelled=False)

        AsyncCall(_call, lambda r: self.show.after(0, lambda: _wrapped(r))).start()

        def _watchdog_timeout():
            try:
                self._ai_watchdog_after_id = None
            except Exception:
                pass
            if self._ai_busy:
                try:
                    logger.info(f"[AI-TXT] {time.strftime('%Y-%m-%d %H:%M:%S')} WATCHDOG timeout -> finalize")
                except Exception:
                    pass
                _finalize({"error": "分析超时"}, cancelled=False)

        try:
            self._ai_watchdog_after_id = self.show.after(getattr(self, '_ai_watchdog_ms', 60000), _watchdog_timeout)
            logger.info(f"[AI-TXT] {time.strftime('%Y-%m-%d %H:%M:%S')} WATCHDOG start {getattr(self, '_ai_watchdog_ms', 60000)}ms")
        except Exception:
            self._ai_watchdog_after_id = None

    def analyze_image_pil(self, img, prompt: str | None = None, title: str = 'AI 图像分析') -> None:
        """用通用逻辑分析一张 PIL 图像。"""
        if not getattr(self, 'ai_client', None) or not self.ai_client or not self.ai_client.ready:
            try:
                logger.warning("[AI] 客户端未就绪：缺少密钥或依赖。")
            except Exception:
                pass
            messagebox.showwarning('AI', 'AI 客户端未就绪（缺少密钥或依赖），已取消。')
            return
        if self._ai_busy:
            return
        ts = time.strftime('%Y-%m-%d %H:%M:%S')
        try:
            logger.info(f"[AI-IMG] {ts} analyze_image_pil enter title={title}")
        except Exception:
            pass
        try:
            from PIL import Image
            if isinstance(img, Image.Image):
                pil_img = img
            else:
                messagebox.showerror('AI', '无效的图像对象')
                return
        except Exception:
            pil_img = img  # 尝试继续
        self._ai_busy = True
        # 启用取消按钮并设置取消标志
        if hasattr(self, '_ai_cancel_btn') and self._ai_cancel_btn:
            try:
                self._ai_cancel_btn.config(state=tk.NORMAL)
            except Exception:
                pass
        self._ai_cancel_flag = threading.Event()
        if hasattr(self, '_ai_status_var') and self._ai_status_var:
            try:
                self._ai_status_var.set('分析中...')
            except Exception:
                pass
        use_prompt = prompt or '请描述这张图片的关键信息，并提取可见文字要点（不必逐字转录），如果发现界面元素请概括其用途。'
        try:
            logger.info(f"[AI-IMG] {ts} prompt_len={len(use_prompt) if isinstance(use_prompt, str) else 0} image_size={getattr(pil_img, 'size', None)}")
        except Exception:
            pass
        top = tk.Toplevel(self.show)
        top.title(title)
        top.geometry('540x380+120+120')
        try:
            top.attributes('-topmost', True)
        except Exception:
            pass
        # 顶部信息栏（显示图像元信息）
        meta_bar = ttk.Frame(top)
        meta_bar.pack(fill=tk.X, padx=6, pady=(6, 0))
        meta_var = tk.StringVar(value='')
        ttk.Label(meta_bar, textvariable=meta_var).pack(side=tk.LEFT, anchor='w')

        # 内容区
        info = tk.Text(top, wrap='word')
        info.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)
        info.insert('1.0', '分析中，请稍候...')

        # 底部操作栏：复制/另存为（分析结果准备好后也可使用）
        btn_bar_main = ttk.Frame(top)
        btn_bar_main.pack(fill=tk.X, padx=6, pady=(0, 6))
        def _copy_content():
            try:
                text = info.get('1.0', tk.END).strip()
                top.clipboard_clear(); top.clipboard_append(text)
            except Exception:
                pass
        def _save_as():
            try:
                from tkinter import filedialog
                path = filedialog.asksaveasfilename(
                    parent=top,
                    title='另存为',
                    defaultextension='.md',
                    filetypes=[('Markdown', '*.md'), ('Text', '*.txt'), ('All Files', '*.*')]
                )
            except Exception:
                path = ''
            if not path:
                return
            try:
                with open(path, 'w', encoding='utf-8') as f:
                    f.write(info.get('1.0', tk.END))
            except Exception as e:
                messagebox.showerror('保存失败', str(e))
        ttk.Button(btn_bar_main, text='复制内容', command=_copy_content).pack(side=tk.RIGHT, padx=4)
        ttk.Button(btn_bar_main, text='另存为...', command=_save_as).pack(side=tk.RIGHT)

        def _save_json_and_visualize():
            try:
                raw = info.get('1.0', tk.END).strip()
                if not raw:
                    messagebox.showwarning('保存 JSON', '当前内容为空')
                    return
                try:
                    data = json.loads(raw)
                except Exception as e:
                    # 尝试从文本中提取 JSON 片段（支持 ```json fenced 或最大花括号块）
                    def _try_extract_json(text: str):
                        # 1) fenced code block ```json ... ``` 或 ``` ... ```
                        try:
                            import re
                            m = re.search(r"```json\s*(\{[\s\S]*?\})\s*```", text, re.IGNORECASE)
                            if not m:
                                m = re.search(r"```\s*(\{[\s\S]*?\})\s*```", text, re.IGNORECASE)
                            if m:
                                return json.loads(m.group(1))
                        except Exception:
                            pass
                        # 2) 扫描最大平衡花括号块
                        try:
                            first = text.find('{')
                            while first != -1:
                                depth = 0
                                in_str = False
                                esc = False
                                for i in range(first, len(text)):
                                    ch = text[i]
                                    if in_str:
                                        if esc:
                                            esc = False
                                        elif ch == '\\':
                                            esc = True
                                        elif ch == '"':
                                            in_str = False
                                    else:
                                        if ch == '"':
                                            in_str = True
                                        elif ch == '{':
                                            depth += 1
                                        elif ch == '}':
                                            depth -= 1
                                            if depth == 0:
                                                cand = text[first:i+1]
                                                try:
                                                    return json.loads(cand)
                                                except Exception:
                                                    break
                                first = text.find('{', first + 1)
                        except Exception:
                            pass
                        return None

                    data = _try_extract_json(raw)
                    if data is None:
                        messagebox.showerror(
                            '保存 JSON',
                            '内容不是合法 JSON，且未能从文本中提取有效的 JSON。\n\n'
                            '建议：\n- 使用“课堂行为分析（JSON 输出）…”菜单项\n- 或在 docs/behavior_prompts.md 使用严格 JSON 模板，再重试'
                        )
                        return
                # 选择保存 JSON 的路径
                try:
                    base_hint = getattr(self, '_auto_viz_hint_path', None)
                    base = self._suggest_report_basename(data, base_hint)
                    jp, pp = self._ensure_unique_pair(base)
                    initialdir = self._get_analyze_images_dir()
                    initialfile = os.path.basename(jp)
                    json_path = filedialog.asksaveasfilename(
                        parent=top,
                        title='另存为 JSON 并生成可视化图',
                        defaultextension='.json',
                        filetypes=[('JSON', '*.json'), ('All Files', '*.*')],
                        initialdir=initialdir,
                        initialfile=initialfile
                    )
                except Exception:
                    json_path = ''
                if not json_path:
                    return
                # 保存 JSON（注入 provenance：AI 视觉）
                try:
                    if isinstance(data, dict):
                        try:
                            prov = data.get('provenance') if isinstance(data.get('provenance'), dict) else None
                        except Exception:
                            prov = None
                        if not prov:
                            data['provenance'] = {
                                'generated_by': 'ai',
                                'model': getattr(self.ai_client, 'model_vision', ''),
                                'timestamp': time.strftime('%Y-%m-%d %H:%M:%S')
                            }
                    with open(json_path, 'w', encoding='utf-8') as f:
                        f.write(json.dumps(data, ensure_ascii=False, indent=2))
                except Exception as e:
                    messagebox.showerror('保存 JSON', f'写入失败：{e}')
                    return
                # 生成 PNG 路径（同名 _summary.png）
                base, _ = os.path.splitext(json_path)
                png_path = base + '_summary.png'
                # 调用渲染
                try:
                    from ...student_behavior_ai.visualize import render_report_image
                except Exception:
                    try:
                        # 相对导入失败时退回绝对导入（根据项目结构）
                        from student_behavior_ai.visualize import render_report_image
                    except Exception as e:
                        messagebox.showerror('生成可视化图', f'找不到可视化模块：{e}')
                        return
                try:
                    title_text = title if isinstance(title, str) else '课堂行为分析'
                    render_report_image(data, png_path, title=title_text)
                except Exception as e:
                    messagebox.showerror('生成可视化图', f'渲染失败：{e}')
                    return
                messagebox.showinfo('完成', f'已保存：\nJSON: {json_path}\n图像: {png_path}')
            except Exception as e:
                messagebox.showerror('保存 JSON / 可视化', str(e))

        ttk.Button(btn_bar_main, text='另存为 JSON → 生成可视化图', command=_save_json_and_visualize).pack(side=tk.RIGHT, padx=4)

        def _call():
            # 无法真正中断 SDK 调用，这里仅在开始前做一次快速检查
            if self._ai_cancel_flag and self._ai_cancel_flag.is_set():
                return {"error": "已取消"}
            try:
                logger.info(f"[AI-IMG] {time.strftime('%Y-%m-%d %H:%M:%S')} SEND vision request")
            except Exception:
                pass
            return self.ai_client.analyze_image(pil_img, use_prompt)

        def _finalize(result: Dict[str, Any], cancelled: bool = False):
            self._ai_busy = False
            if hasattr(self, '_ai_cancel_btn') and self._ai_cancel_btn:
                try:
                    self._ai_cancel_btn.config(state=tk.DISABLED)
                except Exception:
                    pass
            if hasattr(self, '_ai_status_var') and self._ai_status_var:
                try:
                    self._ai_status_var.set('已取消' if cancelled else '就绪')
                except Exception:
                    pass
            info.delete('1.0', tk.END)
            # 显示元信息
            try:
                meta = result.get('meta') if isinstance(result, dict) else None
            except Exception:
                meta = None
            if meta:
                try:
                    w0, h0 = meta.get('orig', {}).get('w'), meta.get('orig', {}).get('h')
                    w1, h1 = meta.get('resized', {}).get('w'), meta.get('resized', {}).get('h')
                    ratio = meta.get('ratio')
                    fmt = meta.get('format')
                    byt = meta.get('bytes')
                    meta_var.set(f"原始: {w0}x{h0}  缩放后: {w1}x{h1}  比例: {ratio:.3f}  格式: {fmt}  大小: {byt}B")
                except Exception:
                    pass
            if cancelled:
                info.insert('1.0', '已取消')
                return
            if 'content' in result:
                info.insert('1.0', result['content'])
            else:
                err_text = f"[错误] {result.get('error')}"
                info.insert('1.0', err_text)
                # 底部错误操作区
                btn_bar = ttk.Frame(top)
                btn_bar.pack(fill=tk.X, padx=6, pady=(0, 6))
                def _copy_err():
                    try:
                        top.clipboard_clear(); top.clipboard_append(err_text)
                    except Exception:
                        pass
                ttk.Button(btn_bar, text='复制错误信息', command=_copy_err).pack(side=tk.RIGHT)

        def _wrapped(res: Dict[str, Any]):
            # 取消看门狗
            try:
                if hasattr(self, '_ai_watchdog_after_id') and self._ai_watchdog_after_id:
                    self.show.after_cancel(self._ai_watchdog_after_id)
                    self._ai_watchdog_after_id = None
            except Exception:
                pass
            try:
                logger.info(f"[AI-IMG] {time.strftime('%Y-%m-%d %H:%M:%S')} RECV vision response")
            except Exception:
                pass
            if self._ai_cancel_flag and self._ai_cancel_flag.is_set():
                _finalize(res, cancelled=True)
            else:
                _finalize(res, cancelled=False)

        AsyncCall(_call, lambda r: self.show.after(0, lambda: _wrapped(r))).start()

        # 看门狗：若 35s 仍未返回，则主动结束为超时，避免 UI 长时间处于忙碌
        def _watchdog_timeout():
            try:
                self._ai_watchdog_after_id = None
            except Exception:
                pass
            if self._ai_busy:
                try:
                    logger.info(f"[AI-IMG] {time.strftime('%Y-%m-%d %H:%M:%S')} WATCHDOG timeout -> finalize as timeout")
                except Exception:
                    pass
                _finalize({"error": "分析超时"}, cancelled=False)

        try:
            self._ai_watchdog_after_id = self.show.after(getattr(self, '_ai_watchdog_ms', 60000), _watchdog_timeout)
        except Exception:
            self._ai_watchdog_after_id = None
        try:
            logger.info(f"[AI-IMG] {time.strftime('%Y-%m-%d %H:%M:%S')} WATCHDOG start {getattr(self, '_ai_watchdog_ms', 60000)}ms")
        except Exception:
            pass

    # ---- 自动可视化辅助 ----
    def _get_analyze_images_dir(self) -> str:
        """返回默认的输出目录 screen_capture/analyze_images，并确保存在。"""
        try:
            here = os.path.abspath(__file__)
            ui_dir = os.path.dirname(here)
            sc_dir = os.path.dirname(ui_dir)
            proj_dir = os.path.dirname(sc_dir)
            out_dir = os.path.join(proj_dir, 'screen_capture', 'analyze_images')
            os.makedirs(out_dir, exist_ok=True)
            return out_dir
        except Exception:
            # 回退到当前工作目录
            try:
                os.makedirs(os.path.join(os.getcwd(), 'analyze_images'), exist_ok=True)
                return os.path.join(os.getcwd(), 'analyze_images')
            except Exception:
                return os.getcwd()
    def _extract_json_from_text(self, text: str):
        try:
            return json.loads(text)
        except Exception:
            pass
        try:
            import re
            m = re.search(r"```json\s*(\{[\s\S]*?\})\s*```", text, re.IGNORECASE)
            if not m:
                m = re.search(r"```\s*(\{[\s\S]*?\})\s*```", text, re.IGNORECASE)
            if m:
                return json.loads(m.group(1))
        except Exception:
            pass
        try:
            first = text.find('{')
            while first != -1:
                depth = 0; in_str = False; esc = False
                for i in range(first, len(text)):
                    ch = text[i]
                    if in_str:
                        if esc:
                            esc = False
                        elif ch == '\\':
                            esc = True
                        elif ch == '"':
                            in_str = False
                    else:
                        if ch == '"':
                            in_str = True
                        elif ch == '{':
                            depth += 1
                        elif ch == '}':
                            depth -= 1
                            if depth == 0:
                                cand = text[first:i+1]
                                try:
                                    return json.loads(cand)
                                except Exception:
                                    break
                first = text.find('{', first + 1)
        except Exception:
            pass
        return None

    # ---- 命名与路径辅助 ----
    def _sanitize_filename(self, name: str, max_len: int = 100) -> str:
        bad = '<>:"/\\|?*\n\r\t'
        out = ''.join('_' if ch in bad else ch for ch in name)
        out = out.strip().strip('.')
        if len(out) > max_len:
            out = out[:max_len].rstrip('. ')
        return out or 'report'

    def _suggest_report_basename(self, data: dict, base_hint: str | None) -> str:
        # 目录：默认使用 screen_capture/analyze_images
        dir_path = self._get_analyze_images_dir()
        # 名称提示
        if base_hint and isinstance(base_hint, str) and base_hint.strip():
            stem_hint = os.path.splitext(os.path.basename(base_hint))[0]
        else:
            stem_hint = 'report'
        # 优先从 source.image_path 获取原图名
        src_img = None
        try:
            src_img = data.get('source', {}).get('image_path') if isinstance(data, dict) else None
        except Exception:
            src_img = None
        if isinstance(src_img, str) and src_img.strip():
            stem = os.path.splitext(os.path.basename(src_img.strip()))[0]
        else:
            stem = stem_hint
        # 选择关键标签（per_class 按 count 排序取前2个）
        label_part = ''
        try:
            pc = data.get('per_class') if isinstance(data, dict) else None
            if isinstance(pc, dict):
                items = []
                for k, v in pc.items():
                    try:
                        c = int(v.get('count', 0)) if isinstance(v, dict) else 0
                    except Exception:
                        c = 0
                    items.append((k, c))
                items.sort(key=lambda x: x[1], reverse=True)
                keys = [k for k, _ in items[:2] if k]
                if keys:
                    label_part = '_cls-' + '-'.join(self._sanitize_filename(k, 20) for k in keys)
        except Exception:
            pass
        # 交互与分数
        ilvl = ''
        fscore = ''
        try:
            m = data.get('metrics', {}) if isinstance(data, dict) else {}
            lvl = m.get('interaction_level')
            if isinstance(lvl, str) and lvl:
                ilvl = f"_il-{self._sanitize_filename(lvl, 8)}"
            fs = m.get('focus_score')
            if isinstance(fs, (int, float)):
                try:
                    fscore = f"_f{int(round(fs))}"
                except Exception:
                    fscore = ''
        except Exception:
            pass
        # 时间戳
        ts = time.strftime('%Y%m%d_%H%M%S')
        base_name = f"{self._sanitize_filename(stem, 60)}{label_part}{ilvl}{fscore}_{ts}"
        return os.path.join(dir_path, base_name)

    def _ensure_unique_pair(self, base: str, json_ext: str = '.json', png_suffix: str = '_summary.png') -> tuple[str, str]:
        idx = 0
        while True:
            b = base if idx == 0 else f"{base}_{idx}"
            jp = b + json_ext
            pp = b + png_suffix
            if not os.path.exists(jp) and not os.path.exists(pp):
                return jp, pp
            idx += 1

    def _auto_generate_visualization(self, content: str, title: str) -> None:
        data = self._extract_json_from_text(content)
        if data is None or not isinstance(data, dict):
            return
        # 生成保存建议并让用户确认路径
        try:
            base_hint = getattr(self, '_auto_viz_hint_path', None)
        except Exception:
            base_hint = None
        try:
            base = self._suggest_report_basename(data, base_hint)
        except Exception:
            base = os.path.join(self._get_analyze_images_dir(), f"report_{int(time.time())}")

        try:
            from tkinter import filedialog
            initialdir = self._get_analyze_images_dir()
            jp_suggest, pp_suggest = self._ensure_unique_pair(base)
            json_path = filedialog.asksaveasfilename(
                parent=self._ai_chat_window or self.show,
                title='保存 JSON（将同时生成可视化图）',
                defaultextension='.json',
                filetypes=[('JSON', '*.json'), ('All Files', '*.*')],
                initialdir=initialdir,
                initialfile=os.path.basename(jp_suggest)
            )
        except Exception:
            json_path = ''
        if not json_path:
            return
        try:
            with open(json_path, 'w', encoding='utf-8') as f:
                f.write(json.dumps(data, ensure_ascii=False, indent=2))
        except Exception as e:
            try:
                messagebox.showerror('保存 JSON', f'写入失败：{e}')
            except Exception:
                pass
            return
        base_noext, _ = os.path.splitext(json_path)
        png_path = base_noext + '_summary.png'
        try:
            from ...student_behavior_ai.visualize import render_report_image
        except Exception:
            try:
                from student_behavior_ai.visualize import render_report_image
            except Exception:
                return
        try:
            title_text = title if isinstance(title, str) else '课堂行为分析'
            render_report_image(data, png_path, title=title_text)
            try:
                messagebox.showinfo('可视化完成', f'已生成：\nJSON: {json_path}\n图像: {png_path}')
            except Exception:
                pass
        except Exception as e:
            try:
                messagebox.showerror('生成可视化图', f'渲染失败：{e}')
            except Exception:
                pass

    def _infer_counts_path(self, image_path: str) -> str | None:
        try:
            base, _ = os.path.splitext(image_path)
            cand = base + '_counts.json'
            if os.path.exists(cand):
                return cand
        except Exception:
            pass
        return None

    # ---- 统一 JSON 结果弹窗（提供“另存为 JSON → 生成可视化图”按钮） ----
    def _show_json_result_window(self, data: dict, title: str = '结果预览', base_hint: str | None = None) -> None:
        host = getattr(self, '_ai_chat_window', None) or self.show
        top = tk.Toplevel(host)
        try:
            top.title(title)
            top.geometry('540x380+140+140')
            top.attributes('-topmost', True)
        except Exception:
            pass
        info = tk.Text(top, wrap='word')
        info.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)
        try:
            info.insert('1.0', json.dumps(data, ensure_ascii=False, indent=2))
        except Exception:
            info.insert('1.0', str(data))
        btn_bar = ttk.Frame(top)
        btn_bar.pack(fill=tk.X, padx=6, pady=(0, 6))
        def _copy_content():
            try:
                s = info.get('1.0', tk.END)
                top.clipboard_clear(); top.clipboard_append(s)
            except Exception:
                pass
        def _save_as_md():
            try:
                path = filedialog.asksaveasfilename(
                    parent=top,
                    title='另存为...',
                    defaultextension='.md',
                    filetypes=[('Markdown', '*.md'), ('Text', '*.txt'), ('All Files', '*.*')]
                )
            except Exception:
                path = ''
            if not path:
                return
            try:
                with open(path, 'w', encoding='utf-8') as f:
                    f.write(info.get('1.0', tk.END))
            except Exception as e:
                messagebox.showerror('保存失败', str(e))
        def _save_json_and_visualize_local():
            try:
                data_local = json.loads(info.get('1.0', tk.END))
            except Exception:
                try:
                    data_local = data if isinstance(data, dict) else {}
                except Exception:
                    data_local = {}
            try:
                base = self._suggest_report_basename(data_local if isinstance(data_local, dict) else {}, base_hint)
            except Exception:
                base = os.path.join(self._get_analyze_images_dir(), f'report_{int(time.time())}')
            try:
                initialdir = self._get_analyze_images_dir()
                jp, _pp = self._ensure_unique_pair(base)
                json_path = filedialog.asksaveasfilename(
                    parent=top,
                    title='另存为 JSON 并生成可视化图',
                    defaultextension='.json',
                    filetypes=[('JSON', '*.json'), ('All Files', '*.*')],
                    initialdir=initialdir,
                    initialfile=os.path.basename(jp)
                )
            except Exception:
                json_path = ''
            if not json_path:
                return
            try:
                # 注入 provenance：本地回退/规范化
                if isinstance(data_local, dict):
                    try:
                        prov = data_local.get('provenance') if isinstance(data_local.get('provenance'), dict) else None
                    except Exception:
                        prov = None
                    if not prov:
                        data_local['provenance'] = {
                            'generated_by': 'local_fallback',
                            'model': '',
                            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S')
                        }
                with open(json_path, 'w', encoding='utf-8') as f:
                    f.write(json.dumps(data_local, ensure_ascii=False, indent=2))
            except Exception as e:
                messagebox.showerror('保存 JSON', f'写入失败：{e}')
                return
            base_noext, _ = os.path.splitext(json_path)
            png_path = base_noext + '_summary.png'
            try:
                from ...student_behavior_ai.visualize import render_report_image
            except Exception:
                try:
                    from student_behavior_ai.visualize import render_report_image
                except Exception as e:
                    messagebox.showerror('生成可视化图', f'找不到可视化模块：{e}')
                    return
            try:
                render_report_image(data_local, png_path, title=title)
                messagebox.showinfo('完成', f'已保存：\nJSON: {json_path}\n图像: {png_path}')
            except Exception as e:
                messagebox.showerror('生成可视化图', f'渲染失败：{e}')
        ttk.Button(btn_bar, text='复制内容', command=_copy_content).pack(side=tk.RIGHT, padx=4)
        ttk.Button(btn_bar, text='另存为...', command=_save_as_md).pack(side=tk.RIGHT)
        ttk.Button(btn_bar, text='另存为 JSON → 生成可视化图', command=_save_json_and_visualize_local).pack(side=tk.RIGHT, padx=4)

    # ---- 结构化 JSON 的规则化归一：规范到 schema v1.1 ----
    def _normalize_schema_v11(self, obj: dict) -> dict:
        def _as_int01(x):
            try:
                v = int(round(float(x)))
                if v < 0: v = 0
                if v > 100: v = 100
                return v
            except Exception:
                return None
        def _as_list_str(x):
            if isinstance(x, list):
                return [str(i) for i in x if isinstance(i, (str, int, float))]
            return []
        metrics_in = obj.get('metrics', {}) if isinstance(obj, dict) else {}
        pc_in = obj.get('per_class', {}) if isinstance(obj, dict) else {}
        spatial_in = obj.get('spatial', {}) if isinstance(obj, dict) else {}
        src_in = obj.get('source', {}) if isinstance(obj, dict) else {}
        # metrics 归一
        interaction_level = metrics_in.get('interaction_level') if isinstance(metrics_in, dict) else None
        if interaction_level not in ('low', 'medium', 'high'):
            interaction_level = 'medium'
        metrics = {
            'head_down_rate': _as_int01(metrics_in.get('head_down_rate')) if isinstance(metrics_in, dict) else None,
            'phone_usage_rate': _as_int01(metrics_in.get('phone_usage_rate')) if isinstance(metrics_in, dict) else None,
            'reading_rate': _as_int01(metrics_in.get('reading_rate')) if isinstance(metrics_in, dict) else None,
            'hand_raise_rate': _as_int01(metrics_in.get('hand_raise_rate')) if isinstance(metrics_in, dict) else None,
            'looking_around_rate': _as_int01(metrics_in.get('looking_around_rate')) if isinstance(metrics_in, dict) else None,
            'writing_rate': _as_int01(metrics_in.get('writing_rate')) if isinstance(metrics_in, dict) else None,
            'sleeping_rate': _as_int01(metrics_in.get('sleeping_rate')) if isinstance(metrics_in, dict) else None,
            'distracted_rate': _as_int01(metrics_in.get('distracted_rate')) if isinstance(metrics_in, dict) else None,
            'interaction_level': interaction_level,
            'focus_score': _as_int01(metrics_in.get('focus_score')) if isinstance(metrics_in, dict) else 0,
            'activity_score': _as_int01(metrics_in.get('activity_score')) if isinstance(metrics_in, dict) else 0,
        }
        # per_class 归一
        per_class: dict[str, dict] = {}
        if isinstance(pc_in, dict):
            for k, v in pc_in.items():
                count = None
                rate = None
                if isinstance(v, dict):
                    count = v.get('count')
                    rate = v.get('rate')
                else:
                    count = v
                try:
                    count = int(count) if count is not None else 0
                except Exception:
                    count = 0
                rate = _as_int01(rate)
                per_class[str(k)] = {'count': count, 'rate': rate}
        # spatial 归一
        spatial = {}
        try:
            g = spatial_in.get('grid3x3') if isinstance(spatial_in, dict) else None
            if isinstance(g, list) and len(g) == 3 and all(isinstance(r, list) and len(r) == 3 for r in g):
                # 尝试把元素转成 int
                gg = []
                for r in g:
                    gg.append([int(x) if isinstance(x, (int, float, str)) and str(x).isdigit() else 0 for x in r])
                spatial = {'grid3x3': gg}
            else:
                spatial = {'grid3x3': [[0,0,0],[0,0,0],[0,0,0]]}
        except Exception:
            spatial = {'grid3x3': [[0,0,0],[0,0,0],[0,0,0]]}
        # source 归一
        src_path = src_in.get('image_path') if isinstance(src_in, dict) else ''
        try:
            size_in = src_in.get('image_size') if isinstance(src_in, dict) else {}
            if isinstance(size_in, dict):
                w = int(size_in.get('width') or 0)
                h = int(size_in.get('height') or 0)
            else:
                w, h = 0, 0
        except Exception:
            w, h = 0, 0
        out = {
            'schema_version': '1.1',
            'summary': str(obj.get('summary') or ''),
            'observations': _as_list_str(obj.get('observations')),
            'metrics': metrics,
            'per_class': per_class,
            'spatial': spatial,
            'risks': _as_list_str(obj.get('risks')),
            'suggestions': _as_list_str(obj.get('suggestions')),
            'limitations': _as_list_str(obj.get('limitations')),
            'confidence': str(obj.get('confidence') or 'medium'),
            'source': {'image_path': src_path if isinstance(src_path, str) else '', 'image_size': {'width': w, 'height': h}},
        }
        return out

    # ---- 行为标签词汇表（读取 student_behavior_ai/class_names.txt） ----
    def _load_behavior_classes(self) -> list[str]:
        try:
            if hasattr(self, '_behavior_classes_cache') and isinstance(self._behavior_classes_cache, list):
                return self._behavior_classes_cache
        except Exception:
            pass
        candidates: list[str] = []
        try:
            here = os.path.abspath(__file__)
            ui_dir = os.path.dirname(here)
            sc_dir = os.path.dirname(ui_dir)
            proj_dir = os.path.dirname(sc_dir)
            p1 = os.path.join(proj_dir, 'student_behavior_ai', 'class_names.txt')
            p2 = os.path.join(os.getcwd(), 'student_behavior_ai', 'class_names.txt')
            for p in [p1, p2]:
                if os.path.exists(p):
                    with open(p, 'r', encoding='utf-8') as f:
                        for line in f:
                            name = line.strip()
                            if name:
                                candidates.append(name)
                    break
        except Exception:
            candidates = []
        try:
            self._behavior_classes_cache = candidates
        except Exception:
            pass
        return candidates

    def _build_labels_glossary_text(self, labels: list[str]) -> str:
        if not labels:
            return ''
        zh_map = {
            'upright': '坐姿端正/抬头看前方',
            'bend': '弯腰/身体前倾',
            'book': '出现书本/教材（不代表一定在阅读）',
            'raise_head': '抬头/视线抬起',
            'turn_head': '转头/侧头',
            'bow_head': '低头（可能在看书/手机或书写）',
            'reading': '阅读（关注书本/屏幕内容）',
            'Using_phone': '使用手机',
            'sleep': '打瞌睡/闭眼休息',
            'phone': '手机出现（未必在使用）',
            'hand-raising': '举手',
            'writing': '书写/做笔记',
        }
        lines = []
        for name in labels:
            key = name.strip()
            if not key:
                continue
            desc = zh_map.get(key, None)
            if not desc:
                # 简单回退：用原名提示
                desc = f'标签：{key}'
            lines.append(f'- {key}：{desc}')
        return '\n'.join(lines)

    def analyze_classroom_from_files(self, prompt: str | None = None) -> None:
        """选择课堂图片与可选 JSON 计数，拼 Prompt 调用多模态分析。"""
        host = getattr(self, '_ai_chat_window', None) or self.show

        def _proceed(img_path: str, counts_path: str | None):
            # 读取图片
            try:
                logger.info(f"[AI-CLS] {time.strftime('%Y-%m-%d %H:%M:%S')} READ image begin")
                from PIL import Image
                img = Image.open(img_path).convert('RGB')
                try:
                    logger.info(f"[AI-CLS] {time.strftime('%Y-%m-%d %H:%M:%S')} READ image done size={getattr(img, 'size', None)}")
                except Exception:
                    pass
            except Exception as e:
                messagebox.showerror('AI', f'无法打开图片: {e}')
                try:
                    logger.exception(f"[AI-CLS] READ image failed: {e}")
                except Exception:
                    pass
                return
            # 读取 JSON
            counts_obj = None
            if counts_path:
                try:
                    logger.info(f"[AI-CLS] {time.strftime('%Y-%m-%d %H:%M:%S')} READ counts JSON begin")
                    with open(counts_path, 'r', encoding='utf-8') as f:
                        counts_obj = json.load(f)
                    try:
                        logger.info(f"[AI-CLS] {time.strftime('%Y-%m-%d %H:%M:%S')} READ counts JSON done keys={list(counts_obj.keys()) if isinstance(counts_obj, dict) else 'list'}")
                    except Exception:
                        pass
                except Exception as e:
                    messagebox.showwarning('AI', f'计数 JSON 读取失败，将继续仅基于图片分析。\n{e}')
                    try:
                        logger.exception(f"[AI-CLS] READ counts JSON failed: {e}")
                    except Exception:
                        pass
                    counts_obj = None
            # 构建 Prompt
            prompt_head = prompt if prompt else (
                '你是一名教学观察与课堂行为分析助手。基于图片内容和给定的统计计数，'
                '请客观评估本次课堂的学生专注度与行为特征，按以下结构输出：\n'
                '1) 关键观察要点（要点列表）\n'
                '2) 指标评估（低头率、看手机、阅读/举手/环顾等，以0~100%估算并简述依据）\n'
                "3) 风险与建议，风险点（2~4 条），改进建议（从教学节奏/互动设计/座位与视线管理/课堂规范等维度给出 3~6 条）\n"
                "可以适当结合json中的数据进行风险与建议，不一定要局限在图片内容\n"
                '请谨慎，不要臆测不可见细节；若图片信息不足，请明确说明。'
            )
            if counts_obj is not None:
                try:
                    counts_str = json.dumps(counts_obj, ensure_ascii=False)
                except Exception:
                    counts_str = str(counts_obj)
                prompt_head += '\n\n以下是针对该画面的计数字段(JSON)：\n' + counts_str + '\n'
            try:
                logger.info(f"[AI-CLS] {time.strftime('%Y-%m-%d %H:%M:%S')} BUILD prompt len={len(prompt_head)} with_counts={counts_obj is not None}")
            except Exception:
                pass
            # 直接复用通用图像分析弹窗
            try:
                logger.info(f"[AI-CLS] {time.strftime('%Y-%m-%d %H:%M:%S')} CALL analyze_image_pil")
            except Exception:
                pass
            self.analyze_image_pil(img, prompt=prompt_head, title='课堂行为分析')
            try:
                logger.info(f"[AI-CLS] {time.strftime('%Y-%m-%d %H:%M:%S')} analyze_image_pil invoked")
            except Exception:
                pass

        def _pick_counts_then_proceed(img_path: str, inferred: str | None):
            if inferred is not None:
                _proceed(img_path, inferred)
                return
            # 异步打开可选 JSON 文件对话框
            def _do_counts_pick():
                try:
                    logger.info(f"[AI-CLS] {time.strftime('%Y-%m-%d %H:%M:%S')} OPEN counts JSON file dialog (optional)")
                except Exception:
                    pass
                try:
                    cpath = filedialog.askopenfilename(
                        parent=host,
                        title='选择计数 JSON（可跳过）',
                        filetypes=[('JSON Files', '*.json'), ('All Files', '*.*')]
                    ) or None
                except Exception:
                    cpath = None
                try:
                    logger.info(f"[AI-CLS] {time.strftime('%Y-%m-%d %H:%M:%S')} SELECT counts path={cpath}")
                except Exception:
                    pass
                _proceed(img_path, cpath)
            try:
                host.after(0, _do_counts_pick)
            except Exception:
                _do_counts_pick()

        # 异步打开图片文件对话框
        def _do_image_pick():
            try:
                logger.info(f"[AI-CLS] {time.strftime('%Y-%m-%d %H:%M:%S')} OPEN image file dialog")
            except Exception:
                pass
            try:
                img_path = filedialog.askopenfilename(
                    parent=host,
                    title='选择课堂图片',
                    filetypes=[('Image Files', '*.png;*.jpg;*.jpeg;*.bmp;*.webp'), ('All Files', '*.*')]
                )
            except Exception:
                img_path = ''
            if not img_path:
                try:
                    logger.info(f"[AI-CLS] {time.strftime('%Y-%m-%d %H:%M:%S')} CANCEL image selection")
                except Exception:
                    pass
                return
            try:
                logger.info(f"[AI-CLS] {time.strftime('%Y-%m-%d %H:%M:%S')} SELECT image path={img_path}")
            except Exception:
                pass
            inferred = self._infer_counts_path(img_path)
            try:
                logger.info(f"[AI-CLS] {time.strftime('%Y-%m-%d %H:%M:%S')} infer counts path -> {inferred}")
            except Exception:
                pass
            # 自动可视化输出的默认保存位置提示
            try:
                self._auto_viz_hint_path = img_path
            except Exception:
                pass
            _pick_counts_then_proceed(img_path, inferred)

        try:
            host.after(0, _do_image_pick)
        except Exception:
            _do_image_pick()

    # ---- 菜单命令包装：课堂分析 + Prompt ----
    def _cmd_analyze_classroom_with_prompt(self) -> None:
        try:
            logger.info(f"[AI-CLS] {time.strftime('%Y-%m-%d %H:%M:%S')} MENU '课堂行为分析…' clicked")
        except Exception:
            pass
        p = self._ask_analysis_prompt()
        try:
            logger.info(f"[AI-CLS] {time.strftime('%Y-%m-%d %H:%M:%S')} PROMPT returned len={len(p) if p else 0}")
        except Exception:
            pass
        if p is not None:
            try:
                logger.info(f"[AI-CLS] {time.strftime('%Y-%m-%d %H:%M:%S')} RUN analyze_classroom_from_files (with prompt)")
            except Exception:
                pass
            self.analyze_classroom_from_files(prompt=p)

    # ---- JSON-only Prompt 构造与菜单包装 ----
    def _build_json_only_prompt(self, base_prompt: str | None) -> str:
        """基于用户可选的 base_prompt，附加严格 JSON 输出规范与字段定义（无注释、仅 JSON 对象）。

        JSON-first 约束：
        - 若存在结构化 JSON（检测/统计/已有分析），以 JSON 为主、图片为辅；
        - 冲突时优先保留 JSON 结论，并在 limitations 说明取舍依据；
        - 引导输出 3~6 条 observations，并使用 schema v1.1 字段命名。
        """
        rules = (
            '请严格遵守：\n'
            '- 仅输出一个 JSON 对象，且不包含任何 Markdown、前后缀文本或注释；\n'
            '- JSON 优先：若提供了结构化 JSON（检测/统计/已有分析），以 JSON 为主、图片为辅；不可见证据不臆测；\n'
            '- 如与图片或直觉冲突，优先保留 JSON 结论，并在 limitations 说明冲突与取舍依据；\n'
            '- observations 建议 3~6 条短句，结合计数与 3×3 空间分布归纳显著现象；\n'
            '- 所有百分比或评分统一为 0~100 的整数；无法判断时使用 null；\n'
            '- interaction_level 取值必须是 "low"、"medium" 或 "high"；\n'
            '- per_class 仅包含实际出现的标签；rate 不确定可设为 null；\n'
            '- 不要逐条罗列检测框，聚焦总体归类与显著现象；\n'
            '- 若与输入数据矛盾，请在 limitations 简述原因与取舍依据。\n\n'
            '输出格式（schema v1.1，示例模板；示例值可被覆盖）：\n'
            '{\n'
            '  "schema_version": "1.1",\n'
            '  "summary": "",\n'
            '  "observations": [],\n'
            '  "metrics": {\n'
            '    "head_down_rate": null,\n'
            '    "phone_usage_rate": null,\n'
            '    "reading_rate": null,\n'
            '    "hand_raise_rate": null,\n'
            '    "looking_around_rate": null,\n'
            '    "writing_rate": null,\n'
            '    "sleeping_rate": null,\n'
            '    "distracted_rate": null,\n'
            '    "interaction_level": "medium",\n'
            '    "focus_score": 0,\n'
            '    "activity_score": 0\n'
            '  },\n'
            '  "per_class": {},\n'
            '  "spatial": {"grid3x3": [[0,0,0],[0,0,0],[0,0,0]]},\n'
            '  "risks": [],\n'
            '  "suggestions": [],\n'
            '  "limitations": [],\n'
            '  "confidence": "medium",\n'
            '  "source": {"image_path": "", "image_size": {"width": 0, "height": 0}}\n'
            '}\n'
        )
        head = (base_prompt.strip() + '\n\n' if base_prompt else '')
        return head + rules

    def _cmd_analyze_classroom_json_with_prompt(self) -> None:
        try:
            logger.info(f"[AI-CLS] {time.strftime('%Y-%m-%d %H:%M:%S')} MENU '课堂行为分析（JSON 输出）…' clicked")
        except Exception:
            pass
        p = self._ask_analysis_prompt()
        json_prompt = self._build_json_only_prompt(p)
        try:
            logger.info(f"[AI-CLS] {time.strftime('%Y-%m-%d %H:%M:%S')} PROMPT returned len={len(p) if p else 0} json_prompt_len={len(json_prompt)}")
        except Exception:
            pass
        self.analyze_classroom_from_files(prompt=json_prompt)

    def _cmd_analyze_classroom_detjson_with_prompt(self) -> None:
        try:
            logger.info(f"[AI-CLS] {time.strftime('%Y-%m-%d %H:%M:%S')} MENU '课堂行为分析（检测JSON）…' clicked")
        except Exception:
            pass
        p = self._ask_analysis_prompt()
        if p is None:
            return
        self.analyze_classroom_from_detjson(base_prompt=p, enforce_json=False)

    def _cmd_analyze_classroom_detjson_json_with_prompt(self) -> None:
        try:
            logger.info(f"[AI-CLS] {time.strftime('%Y-%m-%d %H:%M:%S')} MENU '课堂行为分析（检测JSON，JSON 输出）…' clicked")
        except Exception:
            pass
        p = self._ask_analysis_prompt()
        json_prompt = self._build_json_only_prompt(p)
        self.analyze_classroom_from_detjson(base_prompt=json_prompt, enforce_json=True)

    # ---- 纯 JSON 输入 → AI 化处理 ----
    def _cmd_analyze_pure_json_with_prompt(self) -> None:
        try:
            logger.info(f"[AI-CLS] {time.strftime('%Y-%m-%d %H:%M:%S')} MENU '课堂行为分析（纯JSON）…' clicked")
        except Exception:
            pass
        p = self._ask_analysis_prompt()
        self.analyze_pure_json_from_file(base_prompt=p)

    def analyze_pure_json_from_file(self, base_prompt: str | None = None) -> None:
        """选择一个已结构化的课堂 JSON，强制规整到严格模板(schema v1.1)并自动可视化。"""
        host = getattr(self, '_ai_chat_window', None) or self.show
        try:
            from tkinter import filedialog
            path = filedialog.askopenfilename(
                parent=host,
                title='选择课堂分析 JSON（纯 JSON 输入）',
                filetypes=[('JSON Files', '*.json'), ('All Files', '*.*')]
            )
        except Exception:
            path = ''
        if not path:
            try:
                logger.info(f"[AI-CLS] {time.strftime('%Y-%m-%d %H:%M:%S')} CANCEL pure JSON selection")
            except Exception:
                pass
            return
        try:
            with open(path, 'r', encoding='utf-8') as f:
                obj = json.load(f)
            json_text = json.dumps(obj, ensure_ascii=False, indent=2)
            try:
                logger.info(f"[AI-CLS] {time.strftime('%Y-%m-%d %H:%M:%S')} READ pure JSON ok len={len(json_text)}")
            except Exception:
                pass
        except Exception as e:
            messagebox.showerror('AI', f'无法读取 JSON：{e}')
            return
        # 构建严格 JSON 输出提示词（将原始 JSON 作为输入，要求仅输出严格 JSON）
        head = ''
        if base_prompt:
            try:
                head = base_prompt.strip()
            except Exception:
                head = ''
        try:
            labels = self._load_behavior_classes()
        except Exception:
            labels = []
        glossary = self._build_labels_glossary_text(labels)
        intro = (
            '以下是已有的课堂分析 JSON。请在保持字段(schema)与取值约束的前提下进行规整与一致化：\n'
            '- 若缺失字段请补齐（可用 null/空结构作为默认）；\n'
            '- 数值统一到 0~100 的整数；不确定用 null；\n'
            '- 不逐条罗列检测框，聚焦总体归类；\n'
            '- 仅输出严格 JSON。\n'
        )
        if glossary:
            intro += '常见行为标签含义（参考理解，不作强制判断）：\n' + glossary + '\n\n'
        json_prompt = self._build_json_only_prompt(head + ('\n\n' if head else '') + intro)
        prompt = json_prompt + '\n原始 JSON：\n' + json_text + '\n'
        try:
            self._auto_viz_hint_path = path
        except Exception:
            pass
        # 若 AI 未就绪：直接对输入 JSON 进行 schema v1.1 归一化并展示
        if not getattr(self, 'ai_client', None) or not self.ai_client or not self.ai_client.ready:
            try:
                src = obj if isinstance(obj, dict) else {}
                normalized = self._normalize_schema_v11(src)
            except Exception:
                normalized = obj if isinstance(obj, dict) else {}
            self._show_json_result_window(normalized, title='课堂行为分析（纯JSON→严格JSON-回退）', base_hint=path)
            return
        # 走文本分析弹窗；不再自动可视化，只在结果页提供按钮
        self.analyze_text_prompt(prompt=prompt, title='课堂行为分析（纯JSON→严格JSON）')

    def analyze_classroom_from_detjson(self, base_prompt: str | None = None, *, enforce_json: bool = False) -> None:
        """从检测JSON启动课堂分析：解析标签框与位置信息，构建 Prompt；可选配图片走多模态，否则文本分析。"""
        host = getattr(self, '_ai_chat_window', None) or self.show
        # 选择检测 JSON
        def _pick_det_json():
            try:
                logger.info(f"[AI-CLS] {time.strftime('%Y-%m-%d %H:%M:%S')} OPEN detection JSON file dialog")
            except Exception:
                pass
            try:
                det_path = filedialog.askopenfilename(
                    parent=host,
                    title='选择检测 JSON（包含标签与bbox）',
                    filetypes=[('JSON Files', '*.json'), ('All Files', '*.*')]
                )
            except Exception:
                det_path = ''
            if not det_path:
                try:
                    logger.info(f"[AI-CLS] {time.strftime('%Y-%m-%d %H:%M:%S')} CANCEL detection JSON selection")
                except Exception:
                    pass
                return
            try:
                logger.info(f"[AI-CLS] {time.strftime('%Y-%m-%d %H:%M:%S')} SELECT detection JSON path={det_path}")
            except Exception:
                pass
            # 将自动可视化默认保存位置指向检测JSON所在目录
            try:
                self._auto_viz_hint_path = det_path
            except Exception:
                pass
            # 解析检测 JSON
            try:
                try:
                    from ...student_behavior_ai.analyze import parse_detection_json, spatial_summary
                except Exception:
                    from student_behavior_ai.analyze import parse_detection_json, spatial_summary
                counts, boxes, img_size = parse_detection_json(det_path)
                sp = spatial_summary(boxes, img_size)
                # 从检测 JSON 中尝试读取原图路径（键：image）
                det_image_path = None
                try:
                    with open(det_path, 'r', encoding='utf-8') as _f:
                        _obj = json.load(_f)
                    _ip = _obj.get('image') if isinstance(_obj, dict) else None
                    if isinstance(_ip, str) and _ip.strip():
                        _cand = _ip.strip()
                        if not os.path.isabs(_cand):
                            _cand = os.path.normpath(os.path.join(os.path.dirname(det_path), _cand))
                        det_image_path = _cand
                except Exception:
                    det_image_path = None
            except Exception as e:
                messagebox.showerror('AI', f'检测 JSON 解析失败：{e}')
                return
            # 构建 Prompt（附 counts 与空间分布）
            head = base_prompt.strip() if base_prompt else (
                '你是一名教学观察与课堂行为分析助手。以检测 JSON（标签计数与空间分布）为主进行评估，'
                '若提供图片，仅作为辅证核对。请按以下结构输出（严格 JSON 模式下仅输出 JSON）：\n'
                '1) 关键观察要点（要点列表）\n'
                '2) 指标评估（低头率、看手机、阅读/举手/环顾等，以0~100%估算并简述依据）\n'
                '3) 风险与建议（教学节奏、互动、座位与视线管理等）\n'
                '请谨慎，不要臆测不可见细节；若信息不足，请明确说明。'
            )
            if counts:
                try:
                    head += '\n\n计数字段(JSON)：\n' + json.dumps(counts, ensure_ascii=False) + '\n'
                except Exception:
                    head += '\n\n计数字段(JSON)：\n' + str(counts) + '\n'
            if sp:
                try:
                    head += '\n空间分布(3x3) JSON：\n' + json.dumps(sp, ensure_ascii=False) + '\n'
                except Exception:
                    head += '\n空间分布(3x3) JSON：\n' + str(sp) + '\n'
            # 询问是否选择图片走多模态
            use_img = False
            try:
                use_img = messagebox.askyesno('课堂行为分析', '是否选择对应课堂图片以进行多模态分析？')
            except Exception:
                use_img = False
            if use_img:
                # 若 JSON 中包含原图路径且可用，则直接使用；否则再让用户选择图片
                if det_image_path and os.path.exists(det_image_path):
                    try:
                        logger.info(f"[AI-CLS] {time.strftime('%Y-%m-%d %H:%M:%S')} USE image from JSON: {det_image_path}")
                    except Exception:
                        pass
                    try:
                        from PIL import Image
                        img = Image.open(det_image_path).convert('RGB')
                        try:
                            self._auto_viz_hint_path = det_image_path
                        except Exception:
                            pass
                        self.analyze_image_pil(img, prompt=head, title='课堂行为分析（检测JSON）')
                        return
                    except Exception as e:
                        # 打不开则退回手动选择
                        try:
                            logger.exception(f"[AI-CLS] open image from JSON failed: {e}")
                        except Exception:
                            pass
                def _pick_image():
                    try:
                        logger.info(f"[AI-CLS] {time.strftime('%Y-%m-%d %H:%M:%S')} OPEN image file dialog (for det json)")
                    except Exception:
                        pass
                    try:
                        ipath = filedialog.askopenfilename(
                            parent=host,
                            title='选择课堂图片',
                            filetypes=[('Image Files', '*.png;*.jpg;*.jpeg;*.bmp;*.webp'), ('All Files', '*.*')]
                        )
                    except Exception:
                        ipath = ''
                    if not ipath:
                        try:
                            logger.info(f"[AI-CLS] {time.strftime('%Y-%m-%d %H:%M:%S')} CANCEL image selection (for det json)")
                        except Exception:
                            pass
                        # 退回文本分析
                        self.analyze_text_prompt(head, title='课堂行为分析（检测JSON）')
                        return
                    try:
                        from PIL import Image
                        img = Image.open(ipath).convert('RGB')
                    except Exception as e:
                        messagebox.showerror('AI', f'无法打开图片: {e}')
                        self.analyze_text_prompt(head, title='课堂行为分析（检测JSON）')
                        return
                    try:
                        self._auto_viz_hint_path = ipath
                    except Exception:
                        pass
                    self.analyze_image_pil(img, prompt=head, title='课堂行为分析（检测JSON）')
                try:
                    host.after(0, _pick_image)
                except Exception:
                    _pick_image()
            else:
                self.analyze_text_prompt(head, title='课堂行为分析（检测JSON）')

        try:
            host.after(0, _pick_det_json)
        except Exception:
            _pick_det_json()

    # ---- 智能一键：一个按钮完成（检测JSON或结构化JSON自动识别） ----
    def _cmd_analyze_classroom_smart(self) -> None:
        try:
            logger.info(f"[AI-CLS] {time.strftime('%Y-%m-%d %H:%M:%S')} MENU '课堂行为分析（智能一键）…' clicked")
        except Exception:
            pass
        self.analyze_classroom_smart()

    def analyze_classroom_smart(self) -> None:
        host = getattr(self, '_ai_chat_window', None) or self.show
        # 选择 JSON（可能是检测JSON，也可能是已结构化的分析JSON）
        try:
            path = filedialog.askopenfilename(
                parent=host,
                title='选择课堂 JSON（检测JSON 或 结构化JSON）',
                filetypes=[('JSON Files', '*.json'), ('All Files', '*.*')]
            )
        except Exception:
            path = ''
        if not path:
            return
        try:
            with open(path, 'r', encoding='utf-8') as f:
                obj = json.load(f)
        except Exception as e:
            messagebox.showerror('AI', f'无法读取 JSON：{e}')
            return
        # 类型判定
        is_detection = isinstance(obj, dict) and (('counts' in obj) or ('boxes' in obj) or ('objects' in obj))
        # 构建标签词汇表
        try:
            labels = self._load_behavior_classes()
        except Exception:
            labels = []
        glossary = self._build_labels_glossary_text(labels)

        if is_detection:
            # 解析检测 JSON
            try:
                try:
                    from ...student_behavior_ai.analyze import parse_detection_json, spatial_summary
                except Exception:
                    from student_behavior_ai.analyze import parse_detection_json, spatial_summary
                counts, boxes, img_size = parse_detection_json(path)
                sp = spatial_summary(boxes, img_size)
            except Exception as e:
                messagebox.showerror('AI', f'检测 JSON 解析失败：{e}')
                return
            # 多模态选择
            use_img = False
            try:
                use_img = messagebox.askyesno('课堂行为分析', '是否使用图片进行多模态分析？')
            except Exception:
                use_img = False
            # 尝试从 JSON 中获取 image
            det_image_path = None
            if isinstance(obj, dict) and isinstance(obj.get('image'), str) and obj.get('image').strip():
                _ip = obj.get('image').strip()
                if not os.path.isabs(_ip):
                    _ip = os.path.normpath(os.path.join(os.path.dirname(path), _ip))
                det_image_path = _ip
            # 构建提示词（聚类/归纳，不逐条列框；输出严格 JSON 模板）
            head = (
                '你将接收课堂检测的计数与空间分布信息。请以 JSON 文本为主进行归类与总结，'
                '避免逐条罗列检测框，聚焦总体规律与显著现象；若提供图片，仅作为辅证辅助判断，更谨慎地给出评估。\n'
            )
            # 注：若 counts 中包含学生总数（head）或可由 counts 汇总得到，请将其写入 Prompt 便于模型引用
            try:
                head_est = None
                if isinstance(counts, dict) and 'head' in counts and isinstance(counts.get('head'), int):
                    head_est = int(counts.get('head'))
                else:
                    s = 0
                    for v in counts.values():
                        try:
                            if isinstance(v, int):
                                s += int(v)
                        except Exception:
                            pass
                    head_est = s if s > 0 else None
                if head_est is not None:
                    head += f"\n学生总数(head): {head_est}\n"
            except Exception:
                pass
            if glossary:
                head += '常见行为标签含义（参考理解，不作强制判断）：\n' + glossary + '\n\n'
            json_prompt = self._build_json_only_prompt(head)
            # 将 counts 与空间分布附加到 Prompt
            try:
                counts_str = json.dumps(counts, ensure_ascii=False)
            except Exception:
                counts_str = str(counts)
            try:
                sp_str = json.dumps(sp, ensure_ascii=False)
            except Exception:
                sp_str = str(sp)
            prompt_text = (
                json_prompt
                + '\n计数字段(JSON)：\n' + counts_str + '\n'
                + '空间分布(3x3) JSON：\n' + sp_str + '\n'
            )
            # 运行
            if use_img:
                # 优先使用 JSON 的 image
                ip = det_image_path
                if not ip or not os.path.exists(ip):
                    try:
                        ip = filedialog.askopenfilename(
                            parent=host,
                            title='选择课堂图片',
                            filetypes=[('Image Files', '*.png;*.jpg;*.jpeg;*.bmp;*.webp'), ('All Files', '*.*')]
                        )
                    except Exception:
                        ip = ''
                if ip:
                    try:
                        from PIL import Image
                        img = Image.open(ip).convert('RGB')
                        self._auto_viz_hint_path = ip
                        self.analyze_image_pil(img, prompt=prompt_text, title='课堂行为分析（智能一键）')
                        return
                    except Exception as e:
                        messagebox.showwarning('AI', f'打开图片失败，将改为仅 JSON 分析：{e}')
                # 回退文本分析
                try:
                    self._auto_viz_hint_path = path
                except Exception:
                    pass
                # 若 AI 未就绪，回退：基于 counts 生成基础严格 JSON，并在结果弹窗中提供保存按钮
                if not getattr(self, 'ai_client', None) or not self.ai_client or not self.ai_client.ready:
                    base_json = {
                        'schema_version': '1.1',
                        'summary': '（规则）基于检测计数与空间分布的初步整理',
                        'head': int(sum(counts.values())) if isinstance(counts, dict) and counts else None,
                        'observations': [],
                        'metrics': {
                            'head_down_rate': None,
                            'phone_usage_rate': None,
                            'reading_rate': None,
                            'hand_raise_rate': None,
                            'looking_around_rate': None,
                            'writing_rate': None,
                            'sleeping_rate': None,
                            'distracted_rate': None,
                            'interaction_level': 'medium',
                            'focus_score': 0,
                            'activity_score': 0,
                        },
                        'per_class': {k: {'count': int(v), 'rate': None} for k, v in (counts or {}).items()},
                        'spatial': sp or {},
                        'risks': [],
                        'suggestions': [],
                        'limitations': ['AI 未就绪，使用输入检测 JSON 的计数与空间分布直接整理；数值仅供参考'],
                        'confidence': 'low',
                        'source': {
                            'image_path': obj.get('image') if isinstance(obj, dict) else '',
                            'image_size': {'width': (img_size or (0, 0))[0] if img_size else 0, 'height': (img_size or (0, 0))[1] if img_size else 0},
                        },
                        'provenance': {
                            'generated_by': 'local_fallback',
                            'model': '',
                            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S')
                        }
                    }
                    self._show_json_result_window(base_json, title='课堂行为分析（智能一键-回退）', base_hint=path)
                else:
                    # 设置本地模板作为兜底（严格 JSON 预期），若模型未输出 JSON，将弹出本地模板窗口
                    try:
                        self._json_enforce_fallback = {
                            'schema_version': '1.1',
                            'summary': '（模板）基于检测计数/空间分布的课堂行为归纳',
                            'head': int(sum(counts.values())) if isinstance(counts, dict) and counts else None,
                            'observations': [],
                            'metrics': {
                                'head_down_rate': None,
                                'phone_usage_rate': None,
                                'reading_rate': None,
                                'hand_raise_rate': None,
                                'looking_around_rate': None,
                                'writing_rate': None,
                                'sleeping_rate': None,
                                'distracted_rate': None,
                                'interaction_level': 'medium',
                                'focus_score': 0,
                                'activity_score': 0,
                            },
                            'per_class': {k: {'count': int(v), 'rate': None} for k, v in (counts or {}).items()},
                            'spatial': sp or {},
                            'risks': [],
                            'suggestions': [],
                            'limitations': ['模型未输出严格 JSON，本地模板作为兜底。'],
                            'confidence': 'medium',
                            'source': {'image_path': obj.get('image') if isinstance(obj, dict) else '', 'image_size': {'width': (img_size or (0, 0))[0] if img_size else 0, 'height': (img_size or (0, 0))[1] if img_size else 0}},
                            'provenance': {'generated_by': 'local_fallback', 'model': '', 'timestamp': time.strftime('%Y-%m-%d %H:%M:%S')},
                        }
                    except Exception:
                        self._json_enforce_fallback = None
                    self.analyze_text_prompt(prompt=prompt_text, title='课堂行为分析（智能一键）')
            else:
                try:
                    self._auto_viz_hint_path = path
                except Exception:
                    pass
                # 若 AI 未就绪，回退同上：弹窗确认保存
                if not getattr(self, 'ai_client', None) or not self.ai_client or not self.ai_client.ready:
                    base_json = {
                        'schema_version': '1.1',
                        'summary': '（规则）基于检测计数与空间分布的初步整理',
                        'observations': [],
                        'metrics': {
                            'head_down_rate': None,
                            'phone_usage_rate': None,
                            'reading_rate': None,
                            'hand_raise_rate': None,
                            'looking_around_rate': None,
                            'writing_rate': None,
                            'sleeping_rate': None,
                            'distracted_rate': None,
                            'interaction_level': 'medium',
                            'focus_score': 0,
                            'activity_score': 0,
                        },
                        'per_class': {k: {'count': int(v), 'rate': None} for k, v in (counts or {}).items()},
                        'spatial': sp or {},
                        'risks': [],
                        'suggestions': [],
                        'limitations': ['AI 未就绪，使用输入检测 JSON 的计数与空间分布直接整理；数值仅供参考'],
                        'confidence': 'low',
                        'source': {
                            'image_path': obj.get('image') if isinstance(obj, dict) else '',
                            'image_size': {'width': (img_size or (0, 0))[0] if img_size else 0, 'height': (img_size or (0, 0))[1] if img_size else 0},
                        },
                        'provenance': {
                            'generated_by': 'local_fallback',
                            'model': '',
                            'timestamp': time.strftime('%Y-%m-%d %H:%M:%S')
                        }
                    }
                    self._show_json_result_window(base_json, title='课堂行为分析（智能一键-回退）', base_hint=path)
                else:
                    self.analyze_text_prompt(prompt=prompt_text, title='课堂行为分析（智能一键）')
        else:
            # 已结构化 JSON：要求在同一模板下进行优化/规整，仅输出 JSON
            try:
                json_text = json.dumps(obj, ensure_ascii=False, indent=2)
            except Exception:
                json_text = str(obj)
            head = (
                '以下是已有的课堂分析 JSON。请以该 JSON 内容为主进行优化与规整（更清晰、更一致），'
                '允许对估计数值做小幅度校准，但必须谨慎并说明依据；无需逐条罗列检测框，聚焦总体归类与结论。'
                '若提供图片，仅作为辅证帮助核对，不应覆盖 JSON 主体信息。\n'
            )
            if glossary:
                head += '常见行为标签含义（参考理解，不作强制判断）：\n' + glossary + '\n\n'
            json_prompt = self._build_json_only_prompt(head)
            prompt_text = json_prompt + '\n原始 JSON：\n' + json_text + '\n'
            try:
                self._auto_viz_hint_path = path
            except Exception:
                pass
            # 是否多模态（可选）：若用户选择图片，结合视觉再优化
            use_img = False
            det_image_path = None
            if isinstance(obj, dict) and isinstance(obj.get('image'), str) and obj.get('image').strip():
                _ip = obj.get('image').strip()
                if not os.path.isabs(_ip):
                    _ip = os.path.normpath(os.path.join(os.path.dirname(path), _ip))
                det_image_path = _ip
            try:
                use_img = messagebox.askyesno('课堂行为分析', '是否使用图片进行多模态优化？')
            except Exception:
                use_img = False
            if use_img:
                ip = det_image_path
                if not ip or not os.path.exists(ip):
                    try:
                        ip = filedialog.askopenfilename(
                            parent=host,
                            title='选择课堂图片',
                            filetypes=[('Image Files', '*.png;*.jpg;*.jpeg;*.bmp;*.webp'), ('All Files', '*.*')]
                        )
                    except Exception:
                        ip = ''
                if ip:
                    try:
                        from PIL import Image
                        img = Image.open(ip).convert('RGB')
                        self._auto_viz_hint_path = ip
                        self.analyze_image_pil(img, prompt=prompt_text, title='课堂行为分析（智能一键）')
                        return
                    except Exception as e:
                        messagebox.showwarning('AI', f'打开图片失败，将改为仅 JSON 分析：{e}')
            # 文本分析；若 AI 未就绪，则对输入 JSON 进行 schema v1.1 归一化后展示
            if not getattr(self, 'ai_client', None) or not self.ai_client or not self.ai_client.ready:
                src = obj if isinstance(obj, dict) else {}
                try:
                    normalized = self._normalize_schema_v11(src)
                except Exception:
                    normalized = src
                self._show_json_result_window(normalized, title='课堂行为分析（智能一键-回退）', base_hint=path)
            else:
                try:
                    # 结构化 JSON 分支：以输入为主，作为兜底模板（已归一化 normalized 或原 obj）
                    src = obj if isinstance(obj, dict) else {}
                    try:
                        normalized = self._normalize_schema_v11(src)
                    except Exception:
                        normalized = src
                    normalized.setdefault('limitations', [])
                    if isinstance(normalized['limitations'], list):
                        normalized['limitations'].append('模型未输出严格 JSON，本地模板作为兜底。')
                    self._json_enforce_fallback = normalized
                except Exception:
                    self._json_enforce_fallback = None
                self.analyze_text_prompt(prompt=prompt_text, title='课堂行为分析（智能一键）')

    def analyze_image_from_file(self, prompt: str | None = None) -> None:
        """选择一张图片文件进行分析。"""
        if not getattr(self, 'ai_client', None) or not self.ai_client or not self.ai_client.ready:
            try:
                logger.warning("[AI] 客户端未就绪：缺少密钥或依赖。")
            except Exception:
                pass
            messagebox.showwarning('AI', 'AI 客户端未就绪（缺少密钥或依赖），已取消。')
            return
        try:
            path = filedialog.askopenfilename(
                title='选择图片文件',
                filetypes=[('Image Files', '*.png;*.jpg;*.jpeg;*.bmp;*.webp'), ('All Files', '*.*')]
            )
        except Exception:
            path = ''
        if not path:
            return
        try:
            from PIL import Image
            img = Image.open(path).convert('RGB')
        except Exception as e:
            messagebox.showerror('AI', f'无法打开图片: {e}')
            return
        try:
            self._auto_viz_hint_path = path
        except Exception:
            pass
        self.analyze_image_pil(img, prompt=prompt, title='AI 图像分析 - 文件')

    def analyze_image_from_clipboard(self, prompt: str | None = None) -> None:
        """从剪贴板获取图片进行分析（若可用）。"""
        if not getattr(self, 'ai_client', None) or not self.ai_client or not self.ai_client.ready:
            try:
                logger.warning("[AI] 客户端未就绪：缺少密钥或依赖。")
            except Exception:
                pass
            messagebox.showwarning('AI', 'AI 客户端未就绪（缺少密钥或依赖），已取消。')
            return
        try:
            from PIL import ImageGrab, Image
            clip = ImageGrab.grabclipboard()
            img = None
            if isinstance(clip, Image.Image):
                img = clip
            elif isinstance(clip, list) and clip:
                # 有些情况下剪贴板返回文件路径列表
                try:
                    img = Image.open(clip[0]).convert('RGB')
                except Exception:
                    img = None
        except Exception:
            img = None
        if img is None:
            messagebox.showinfo('AI', '剪贴板中未检测到图片')
            return
        self.analyze_image_pil(img, prompt=prompt, title='AI 图像分析 - 剪贴板')

    # ---- Prompt 交互 ----
    def _ask_analysis_prompt(self) -> str | None:
        """弹窗询问分析 Prompt，支持记住上次输入。返回 None 表示取消。"""
        host = getattr(self, '_ai_chat_window', None) or self.show
        try:
            logger.info(f"[AI-CLS] {time.strftime('%Y-%m-%d %H:%M:%S')} PROMPT open begin")
        except Exception:
            pass
        win = tk.Toplevel(host)
        try:
            win.title('设置分析 Prompt')
        except Exception:
            pass
        try:
            win.geometry('520x240+140+120')
        except Exception:
            pass
        try:
            win.attributes('-topmost', True)
        except Exception:
            pass
        ttk.Label(win, text='为图像分析设置 Prompt (可留空使用默认)：').pack(anchor='w', padx=8, pady=(8, 4))
        txt = tk.Text(win, height=6, wrap='word')
        txt.pack(fill=tk.BOTH, expand=True, padx=8)
        if self._analysis_prompt_last:
            txt.insert('1.0', self._analysis_prompt_last)
        remember_var = tk.BooleanVar(value=True)
        chk = ttk.Checkbutton(win, text='记住本次输入', variable=remember_var)
        chk.pack(anchor='w', padx=8, pady=(4, 0))

        result: dict[str, str | None] = {'prompt': None}

        def _ok():
            val = txt.get('1.0', tk.END).strip()
            if remember_var.get():
                if val:
                    self._analysis_prompt_last = val
            # 注意：OK 即使为空也返回空字符串''，让上层继续执行并使用默认提示词
            result['prompt'] = val  # '' 表示用户确认但留空；取消将设置为 None
            try:
                logger.info(f"[AI-CLS] {time.strftime('%Y-%m-%d %H:%M:%S')} PROMPT ok len={len(val)}")
            except Exception:
                pass
            win.destroy()

        def _cancel():
            result['prompt'] = None
            win.destroy()

        bar = ttk.Frame(win)
        bar.pack(fill=tk.X, padx=8, pady=8)
        ttk.Button(bar, text='取消', command=_cancel).pack(side=tk.RIGHT, padx=4)
        ttk.Button(bar, text='确定', command=_ok).pack(side=tk.RIGHT)

        # 模态：直接同步等待（菜单回调已使用 after_idle 错峰，因此 grab 冲突概率极低）
        try:
            win.transient(host)
        except Exception:
            pass
        try:
            win.grab_set()
        except Exception:
            pass
        try:
            logger.info(f"[AI-CLS] {time.strftime('%Y-%m-%d %H:%M:%S')} PROMPT modal begin")
        except Exception:
            pass
        try:
            host.wait_window(win)
        except Exception:
            try:
                win.wait_window()
            except Exception:
                pass
        try:
            logger.info(f"[AI-CLS] {time.strftime('%Y-%m-%d %H:%M:%S')} PROMPT modal end")
        except Exception:
            pass
        try:
            logger.info(f"[AI-CLS] {time.strftime('%Y-%m-%d %H:%M:%S')} PROMPT close")
        except Exception:
            pass
        return result['prompt']

    # ---- 菜单命令包装：先问 Prompt，再执行 ----
    def _cmd_analyze_current_with_prompt(self) -> None:
        p = self._ask_analysis_prompt()
        if p is not None:
            self.analyze_current_frame(prompt=p)

    def _cmd_analyze_file_with_prompt(self) -> None:
        p = self._ask_analysis_prompt()
        if p is not None:
            self.analyze_image_from_file(prompt=p)

    def _cmd_analyze_clipboard_with_prompt(self) -> None:
        p = self._ask_analysis_prompt()
        if p is not None:
            self.analyze_image_from_clipboard(prompt=p)


__all__ = ['AIChatMixin']
