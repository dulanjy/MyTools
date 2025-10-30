"""设置页相关的 UI mixin。"""
from __future__ import annotations

import tkinter as tk
from tkinter import ttk
from ..ai_client import AIClient, DEFAULT_MODEL_TEXT, DEFAULT_MODEL_VISION


class SettingsPanelMixin:
    """封装 设置 页面的构建与显示/隐藏逻辑。"""

    def _ensure_settings_page(self):
        if hasattr(self, '_settings_container') and self._settings_container and self._settings_container.winfo_exists():
            return
        self._settings_container = ttk.Frame(self._main_paned, width=320)
        frm = self._settings_container
        head = ttk.Frame(frm); head.pack(fill=tk.X, padx=8, pady=(8,4))
        ttk.Label(head, text='设置', font=('Segoe UI', 10, 'bold')).pack(side=tk.LEFT)
        ttk.Button(head, text='返回预览', command=lambda: self._navigate('preview')).pack(side=tk.RIGHT)
        body = ttk.Frame(frm); body.pack(fill=tk.BOTH, expand=True, padx=10, pady=6)
        # 常用切换项
        ttk.Checkbutton(body, text='显示网格', variable=self._grid_var, command=self._toggle_grid).pack(anchor='w', pady=2)
        ttk.Checkbutton(body, text='显示标尺', variable=self.ruler_var, command=self._toggle_ruler).pack(anchor='w', pady=2)
        ttk.Checkbutton(body, text='锁定比例', variable=self._aspect_var, command=self._toggle_aspect_ratio).pack(anchor='w', pady=2)
        ttk.Checkbutton(body, text='显示主界面', variable=self._show_visible_var, command=self._toggle_show_visibility).pack(anchor='w', pady=2)
        ttk.Checkbutton(body, text='显示悬浮按钮', variable=self._float_btn_visible_var, command=lambda: self._toggle_float_button_visibility(self._float_btn_visible_var.get())).pack(anchor='w', pady=2)
        # OCR 最大边设置入口
        ocr_row = ttk.Frame(body); ocr_row.pack(fill=tk.X, pady=(8,2))
        ttk.Label(ocr_row, text='OCR 最大边:').pack(side=tk.LEFT)
        entry = ttk.Entry(ocr_row, textvariable=self.ocr_max_side_var, width=8); entry.pack(side=tk.LEFT, padx=6)
        ttk.Button(ocr_row, text='应用', command=lambda: self._prompt_simple('最大边', self.ocr_max_side_var, lambda: None)).pack(side=tk.LEFT)

        # --- AI 配置 ---
        ai_group = ttk.LabelFrame(body, text='AI 配置 (Zhipu)')
        ai_group.pack(fill=tk.X, pady=(12,4))
        # 可见状态
        cur_ready = bool(getattr(self, 'ai_client', None) and self.ai_client and getattr(self.ai_client, 'ready', False))
        self._ai_status_label = ttk.Label(ai_group, text=f"状态: {'就绪' if cur_ready else '未就绪'}")
        self._ai_status_label.pack(anchor='w', padx=6, pady=(6,2))
        # Key 输入 + 操作
        key_row = ttk.Frame(ai_group); key_row.pack(fill=tk.X, padx=6, pady=(2,8))
        ttk.Label(key_row, text='API Key:').pack(side=tk.LEFT)
        self._ai_key_var = tk.StringVar(value='')
        key_entry = ttk.Entry(key_row, textvariable=self._ai_key_var, show='*')
        key_entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=6)
        # 按钮区
        btns = ttk.Frame(ai_group); btns.pack(fill=tk.X, padx=6, pady=(0,6))
        def _test_key():
            key = self._ai_key_var.get().strip()
            if not key:
                from tkinter import messagebox
                messagebox.showinfo('AI', '请输入 API Key 再测试')
                return
            try:
                # 临时实例测试
                cli = AIClient()
                res = cli.set_api_key(key, persist=False)
                ok = res.get('ok', False)
                if ok and getattr(cli, 'ready', False):
                    from tkinter import messagebox
                    messagebox.showinfo('AI', '测试通过：客户端已就绪（未保存）')
                else:
                    from tkinter import messagebox
                    messagebox.showwarning('AI', f"测试失败：{res.get('error','未知错误')}")
            except Exception as e:
                from tkinter import messagebox
                messagebox.showwarning('AI', f'测试异常：{e}')
        def _save_key():
            key = self._ai_key_var.get().strip()
            if not key:
                from tkinter import messagebox
                messagebox.showinfo('AI', '请输入 API Key 再保存')
                return
            try:
                if not getattr(self, 'ai_client', None):
                    self.ai_client = AIClient()
                res = self.ai_client.set_api_key(key, persist=True)
                ok = res.get('ok', False)
                if ok:
                    from tkinter import messagebox
                    messagebox.showinfo('AI', '已保存到 keyring，客户端已就绪')
                    try:
                        self._update_ai_availability_ui()
                        if hasattr(self, '_ai_status_label'):
                            self._ai_status_label.config(text='状态: 就绪')
                    except Exception:
                        pass
                else:
                    from tkinter import messagebox
                    messagebox.showwarning('AI', f"保存失败：{res.get('error','未知错误')}")
            except Exception as e:
                from tkinter import messagebox
                messagebox.showwarning('AI', f'保存异常：{e}')
        def _clear_key():
            try:
                if getattr(self, 'ai_client', None):
                    self.ai_client.clear_api_key()
                from tkinter import messagebox
                messagebox.showinfo('AI', '已清除本地保存的 API Key')
                try:
                    self._update_ai_availability_ui()
                    if hasattr(self, '_ai_status_label'):
                        self._ai_status_label.config(text='状态: 未就绪')
                except Exception:
                    pass
            except Exception:
                pass
        ttk.Button(btns, text='测试', command=_test_key).pack(side=tk.LEFT)
        ttk.Button(btns, text='保存', command=_save_key).pack(side=tk.LEFT, padx=6)
        ttk.Button(btns, text='清除', command=_clear_key).pack(side=tk.LEFT)

        # 模型选择
        model_group = ttk.Frame(ai_group)
        model_group.pack(fill=tk.X, padx=6, pady=(6,2))
        ttk.Label(model_group, text='文本模型:').grid(row=0, column=0, sticky='w')
        ttk.Label(model_group, text='视觉模型:').grid(row=1, column=0, sticky='w', pady=(4,0))
        # 默认值来源于主类当前字段或默认常量
        text_default = getattr(self, '_ai_model_text', DEFAULT_MODEL_TEXT)
        vision_default = getattr(self, '_ai_model_vision', DEFAULT_MODEL_VISION)
        self._ai_model_text_var = tk.StringVar(value=text_default)
        self._ai_model_vision_var = tk.StringVar(value=vision_default)
        text_values = [DEFAULT_MODEL_TEXT, 'glm-4-air', 'glm-4-long']
        vision_values = [DEFAULT_MODEL_VISION, 'glm-4v']
        ttk.Combobox(model_group, textvariable=self._ai_model_text_var, values=text_values, state='readonly', width=20).grid(row=0, column=1, padx=6, sticky='we')
        ttk.Combobox(model_group, textvariable=self._ai_model_vision_var, values=vision_values, state='readonly', width=20).grid(row=1, column=1, padx=6, sticky='we', pady=(4,0))
        model_group.grid_columnconfigure(1, weight=1)

        # 模型按钮区：应用 + 重新检测
        model_btns = ttk.Frame(ai_group); model_btns.pack(fill=tk.X, padx=6, pady=(6,8))
        def _apply_models():
            mt = (self._ai_model_text_var.get() or DEFAULT_MODEL_TEXT).strip()
            mv = (self._ai_model_vision_var.get() or DEFAULT_MODEL_VISION).strip()
            # 写回主类与客户端
            self._ai_model_text = mt
            self._ai_model_vision = mv
            if getattr(self, 'ai_client', None):
                try:
                    self.ai_client.model_text = mt
                    self.ai_client.model_vision = mv
                except Exception:
                    pass
            # 持久化
            try:
                self._schedule_config_changed()
            except Exception:
                pass
            from tkinter import messagebox
            messagebox.showinfo('AI', f'已应用模型配置\n文本: {mt}\n视觉: {mv}')
        def _recheck_ai():
            # 重新加载客户端（按当前模型与 keyring/env）
            try:
                mt = getattr(self, '_ai_model_text', DEFAULT_MODEL_TEXT)
                mv = getattr(self, '_ai_model_vision', DEFAULT_MODEL_VISION)
                self.ai_client = AIClient(model_text=mt, model_vision=mv)
            except Exception:
                self.ai_client = None
            # 刷新 UI
            ready = bool(getattr(self, 'ai_client', None) and self.ai_client and getattr(self.ai_client, 'ready', False))
            try:
                self._update_ai_availability_ui()
            except Exception:
                pass
            if hasattr(self, '_ai_status_label'):
                self._ai_status_label.config(text=f"状态: {'就绪' if ready else '未就绪'}")
            from tkinter import messagebox
            messagebox.showinfo('AI', f"重新检测：{'就绪' if ready else '未就绪'}")
        ttk.Button(model_btns, text='应用模型', command=_apply_models).pack(side=tk.LEFT)
        ttk.Button(model_btns, text='重新检测', command=_recheck_ai).pack(side=tk.LEFT, padx=6)

    def _show_settings_page(self):
        self._ensure_settings_page()
        # 插入到最左或抽屉之后
        try:
            idx = 1 if hasattr(self, '_drawer_ui') and self._drawer_ui else 0
            if str(self._settings_container) not in self._main_paned.panes():
                self._main_paned.insert(idx, self._settings_container, weight=0)
        except Exception:
            try: self._main_paned.add(self._settings_container, weight=0)
            except Exception: pass
        # 隐藏处理页，避免并存
        try: self._hide_process_page()
        except Exception: pass

    def _hide_settings_page(self):
        if hasattr(self, '_settings_container') and self._settings_container and self._settings_container.winfo_exists():
            try: self._main_paned.forget(self._settings_container)
            except Exception: pass

__all__ = ['SettingsPanelMixin']
