"""Capture window + preview + processing + OCR logic.
Extracted from the original monolithic window_capture.py.
"""
from __future__ import annotations
import threading, time, os, json
from datetime import datetime
from typing import Callable, Dict, List
import numpy as _np
import time as _t
from logging import getLogger as _gl, Logger

import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import pyautogui, mss
from PIL import Image, ImageTk, ImageDraw, ImageFilter, ImageOps

from .constants import (
    PRESET_SIZES,
    MIN_CAPTURE_WIDTH, MIN_CAPTURE_HEIGHT,
    GRID_LINE_STEP, RULER_STEP,
    DEFAULT_RECORD_INTERVAL
)
from .logging_utils import get_logger
from .ocr_engine import OCREngineManager
from .ai_client import AIClient, AsyncCall
from .ui.toolkit import Tooltip
from .ui.toolkit import CollapsibleFrame
from .ui.ai_chat import AIChatMixin
from .ui.ocr_panel import OCRPanelMixin
from .ui.settings_panel import SettingsPanelMixin
from .ui.record_panel import RecordPanelMixin
from .state import OCRPanelState
from .ui.processing_panel import ProcessingPanelMixin

# Optional imports (lazy)
try:
    import pyperclip  # noqa: F401
except Exception:  # pragma: no cover
    pyperclip = None  # type: ignore

logger = get_logger()

class CapturePreviewDuoEnhanced(OCRPanelMixin, SettingsPanelMixin, RecordPanelMixin, ProcessingPanelMixin, AIChatMixin):
    """Encapsulates the capture rectangle window and the preview/control window.

    Responsibilities:
    - Manage a draggable/resizable capture region (transparent overlay window)
    - Periodically grab the region using mss
    - Provide a preview window with: zoom, grid/ruler overlay, processing pipeline, OCR, snapshot & frame recording
    - Allow dynamic registration of image processors
    """

    def __init__(self, init_box=(200, 200, 600, 500)):
        # Geometry (left, top, right, bottom)
        self.box = list(init_box)
        self.grip_size = 8
        self.drag_mode = None  # 0..3 corners, 4 move
        self.start_pos = None
        self.start_box = None

        # Flags / state
        self.aspect_ratio_lock = False
        self.aspect_ratio = 1.0
        self.grid_visible = False
        self.ruler_visible = True
        self.record_mode = False
        self.record_interval = DEFAULT_RECORD_INTERVAL
        self.record_path = None
        self.last_record_time = 0.0

        # Image & zoom
        self.last_pil = None
        self.scale = 1.0

        # Processing pipeline
        self.processors: Dict[str, Dict] = {}
        self.active_processors: List[str] = []
        self.processing_panel = None
        self._register_builtin_processors()

        # OCR related
        self.ocr_in_progress = False
        self.ocr_use_processed = False
        self.last_ocr_result = None
        self.show_ocr_boxes = False
        self.ocr_boxes_valid = False
        self.ocr_lang = tk.StringVar(value="ch")  # (B) 语言选择
        self.ocr_auto_warm = True  # (A) 是否自动后台预热
        # (D) OCR 状态指示变量
        self.ocr_status_var = tk.StringVar(value="未加载")
        # (B 扩展) 最近一次 OCR 图像缓存（原始 / 处理后）供缩略展示
        self.last_ocr_raw_img = None
        self.last_ocr_processed_img = None
        # 额外 OCR 优化配置
        self.ocr_max_side = 1280  # 超过该最大边则按比例下采样，加速检测
        self.ocr_last_timing = {}  # 保存本次识别各阶段耗时
        # 缩略图缓存 (ImageTk.PhotoImage 引用防止被回收)
        self._ocr_thumb_raw = None
        self._ocr_thumb_processed = None
        # 是否强制使用本地 inference 目录下的轻量模型
        self.use_local_ocr_models = True
        self.local_ocr_base = os.path.join(os.path.dirname(os.path.abspath(__file__)), '..', 'PaddleOCR-main', 'inference')
        # 新增: OCR 管理器实例
        try:
            self.ocr_manager = OCREngineManager(lang=self.ocr_lang.get(), use_local_models=self.use_local_ocr_models, local_base=self.local_ocr_base)
        except Exception as e:
            logger.warning("初始化 OCREngineManager 失败: %s", e)
            self.ocr_manager = None
        # 初始化 OCR 结果窗口引用
        self.ocr_text_window = None
        self.ocr_state = OCRPanelState()
        # Windows
        self._build_capture_win()
        self._build_show_win()
        self.loop()  # start periodic capture
        # (A) 预热：避免首次点击识别时长时间阻塞
        if self.ocr_auto_warm:
            try:
                self.show.after(1200, self._warmup_ocr_async)
            except Exception:
                pass
        # 初始化 AI 客户端
        try:
            self.ai_client = AIClient()
        except Exception as _e:
            self.ai_client = None
        # 记录当前 AI 模型（与 AIClient 默认保持一致）
        self._ai_model_text = getattr(self.ai_client, 'model_text', 'glm-4') if self.ai_client else 'glm-4'
        self._ai_model_vision = getattr(self.ai_client, 'model_vision', 'glm-4.5v') if self.ai_client else 'glm-4.5v'
        self._system_prompt = ''
        self._init_ai_chat()
        # 根据 AI 可用性更新相关按钮与提示
        try:
            self._update_ai_availability_ui()
        except Exception:
            pass
        # 状态栏占位字典
        self._status_bar = None
        self._status_slots = {}
        try:
            self._init_status_bar()
        except Exception:
            pass
        # Drawer UI (MVP) 开关与状态
        self._drawer_ui = True
        self._active_page = 'preview'  # preview | ocr | ai | process | record | settings
        self._drawer_collapsed = False
        # Float button state
        self._float_btn_win = None
        self._float_drag = None  # (mouse_x, mouse_y, win_x, win_y)
        # 全局单例引用，避免重复悬浮球（多个实例或重复初始化时）
        if not hasattr(CapturePreviewDuoEnhanced, '_GLOBAL_FLOAT_BTN_WIN'):
            CapturePreviewDuoEnhanced._GLOBAL_FLOAT_BTN_WIN = None

    # ----------------- Processing pipeline (builtins) -----------------
    def _register_builtin_processors(self):
        """注册内置图像处理器。
        processors 结构: {
            key: { 'name': str, 'enabled': bool, 'params': dict, 'fn': Callable[[PIL.Image, dict], PIL.Image] }
        }
        UI 会修改 enabled/params，本方法仅负责初始化。
        """
        self.processors.clear()

        def _add(key: str, name: str, fn: Callable[[Image.Image, Dict], Image.Image], params: Dict|None=None, enabled: bool=False):
            self.processors[key] = {
                'name': name,
                'enabled': enabled,
                'params': (params or {}).copy(),
                'fn': fn
            }

        # 灰度
        _add('gray', '灰度', lambda im, p: ImageOps.grayscale(im).convert('RGB'))
        # 反相
        _add('invert', '反相', lambda im, p: ImageOps.invert(im.convert('RGB')))
        # 高斯模糊
        _add('blur', '高斯模糊', lambda im, p: im.filter(ImageFilter.GaussianBlur(radius=float(p.get('radius', 1.5)))), params={'radius': 1.5})
        # 锐化（简单版）
        _add('sharpen', '锐化', lambda im, p: im.filter(ImageFilter.SHARPEN))

        # 边缘 + 阈值（强调边缘，便于 OCR 前预处理的可选项）
        def _edges(im: Image.Image, p: Dict) -> Image.Image:
            thr = int(p.get('threshold', 110))
            try:
                g = im.convert('L')
                e = g.filter(ImageFilter.FIND_EDGES)
                e = e.point(lambda x: 255 if x > thr else 0)
                # 反相以突出前景（可按需调整）
                e = ImageOps.invert(e)
                return e.convert('RGB')
            except Exception:
                return im
        _add('edges', '边缘增强', _edges, params={'threshold': 110})

        # 二值化（简单阈值）
        def _binarize(im: Image.Image, p: Dict) -> Image.Image:
            th = int(p.get('th', 150))
            try:
                g = im.convert('L')
                b = g.point(lambda x: 255 if x >= th else 0)
                return b.convert('RGB')
            except Exception:
                return im
        _add('binarize', '二值化', _binarize, params={'th': 150})

    def _apply_processing(self, img: Image.Image) -> Image.Image:
        """按当前启用的处理器顺序应用处理。
        - 使用 active_processors 作为顺序来源；若为空，则使用 processors 的声明顺序中 enabled=True 的项。
        - 每个处理器接收 (PIL.Image, params) 并返回新的 PIL.Image。
        - 任一处理器失败时跳过并记录日志。
        """
        try:
            if not self.processors:
                return img
            order: List[str] = []
            if self.active_processors:
                # 仅包含仍存在于 processors 且标记启用的键
                order = [k for k in self.active_processors if k in self.processors and self.processors[k].get('enabled')]
            else:
                # 使用 processors 中启用的键（插入顺序）
                order = [k for k, v in self.processors.items() if v.get('enabled')]
            out = img
            for key in order:
                meta = self.processors.get(key)
                if not meta:
                    continue
                if not meta.get('enabled'):
                    continue
                fn = meta.get('fn')
                params = meta.get('params', {})
                if callable(fn):
                    try:
                        out = fn(out, params) or out
                    except Exception as e:
                        logger.warning('处理器 %s 失败: %s', key, e)
                else:
                    logger.debug('处理器 %s 缺少可调用的 fn', key)
            return out
        except Exception:
            return img

    # ----------------- Window / geometry helpers -----------------
    def _apply_geometry(self):
        w = max(MIN_CAPTURE_WIDTH, self.box[2] - self.box[0])
        h = max(MIN_CAPTURE_HEIGHT, self.box[3] - self.box[1])
        screen_w, screen_h = pyautogui.size()
        x = max(0, min(self.box[0], screen_w - w))
        y = max(0, min(self.box[1], screen_h - h))
        self.box = [x, y, x + w, y + h]
        self.cap.geometry(f"{w}x{h}+{x}+{y}")
        # 更新尺寸标签（如果使用独立窗口，放在框外上方，避免进入截图区域）
        if hasattr(self, 'size_label_host') and self.size_label_host is not None:
            try:
                offset_x = 6
                offset_y = -24  # 放在框上方
                lx = max(0, x + offset_x)
                ly = max(0, y + offset_y)
                label_w = 90
                label_h = 20
                self.size_label_host.geometry(f"{label_w}x{label_h}+{lx}+{ly}")
            except Exception:
                pass

    # ----------------- Status Bar (Phase 1 minimal) -----------------
    def _init_status_bar(self):
        if not hasattr(self, 'show'):
            return
        # 底部简单 Frame 占位
        bar = ttk.Frame(self.show)
        bar.pack(side=tk.BOTTOM, fill=tk.X)
        self._status_bar = bar
        # 预置三个槽位: OCR / AI / Info
        for key in ('OCR','AI','Info'):
            lbl = ttk.Label(bar, text=f"{key}: -", anchor='w')
            lbl.pack(side=tk.LEFT, padx=6)
            self._status_slots[key] = lbl
        self._update_status_bar('Info', '初始化完成')

        # 订阅事件总线 (如果可用)
        try:
            from .event_bus import get_global_bus
            bus = get_global_bus()
            bus.on('ocr_finished', lambda payload: self._update_status_bar('OCR', f"完成 {payload.get('count','?')} 行"))
            bus.on('ai_reply', lambda payload: self._update_status_bar('AI', 'OK' if payload.get('ok') else 'ERR'))
        except Exception:
            pass

    def _update_status_bar(self, slot: str, text: str):
        try:
            if slot in self._status_slots:
                self._status_slots[slot].config(text=f"{slot}: {text}")
        except Exception:
            pass
    def _update_layout(self):
        w = self.box[2] - self.box[0]
        h = self.box[3] - self.box[1]
        self.border_top.place(x=0, y=0, width=w)
        self.border_bottom.place(x=0, y=h-2, width=w)
        self.border_left.place(x=0, y=0, height=h)
        self.border_right.place(x=w-2, y=0, height=h)
        self.title_bar.place(x=2, y=2, width=w-4)
        corners = [
            (0, 0),
            (w - self.grip_size, 0),
            (0, h - self.grip_size),
            (w - self.grip_size, h - self.grip_size)
        ]
        for grip, (xg, yg) in zip(self.grips, corners):
            grip.place(x=xg, y=yg)
    # 旧的内嵌尺寸标签布局移除，改为独立顶层（见 _build_capture_win）

    def start_drag(self, corner_idx):
        self.drag_mode = corner_idx
        self.start_pos = pyautogui.position()
        self.start_box = self.box.copy()
        self._drag_loop()

    def _on_title_press(self, _e):
        self.drag_mode = 4
        self.start_pos = pyautogui.position()
        self.start_box = self.box.copy()
        self._drag_loop()

    def _on_drag_stop(self, _e):
        self.drag_mode = None
        self.start_pos = None
        self.start_box = None

    def _drag_loop(self):
        if self.drag_mode is None:
            return
        pos = pyautogui.position()
        dx = pos[0] - self.start_pos[0]
        dy = pos[1] - self.start_pos[1]
        if self.drag_mode == 4:  # move
            self.box = [
                self.start_box[0] + dx,
                self.start_box[1] + dy,
                self.start_box[2] + dx,
                self.start_box[3] + dy,
            ]
        else:  # resize
            if self.drag_mode in [0, 2]:
                self.box[0] = min(self.start_box[0] + dx, self.start_box[2] - MIN_CAPTURE_WIDTH)
            if self.drag_mode in [1, 3]:
                self.box[2] = max(self.start_box[2] + dx, self.start_box[0] + MIN_CAPTURE_WIDTH)
            if self.drag_mode in [0, 1]:
                self.box[1] = min(self.start_box[1] + dy, self.start_box[3] - MIN_CAPTURE_HEIGHT)
            if self.drag_mode in [2, 3]:
                self.box[3] = max(self.start_box[3] + dy, self.start_box[1] + MIN_CAPTURE_HEIGHT)
            if self.aspect_ratio_lock:
                self._maintain_aspect_ratio()
        self._apply_geometry()
        self._update_layout()
        if self.drag_mode is not None:
            self.cap.after(16, self._drag_loop)

    def _maintain_aspect_ratio(self):
        w = self.box[2] - self.box[0]
        h = self.box[3] - self.box[1]
        current = w / h
        if abs(current - self.aspect_ratio) < 1e-6:
            return
        if current > self.aspect_ratio:
            # too wide -> adjust width
            new_w = int(h * self.aspect_ratio)
            if self.drag_mode in [1, 3]:  # right edges
                self.box[2] = self.box[0] + new_w
            else:
                self.box[0] = self.box[2] - new_w
        else:
            # too tall -> adjust height
            new_h = int(w / self.aspect_ratio)
            if self.drag_mode in [2, 3]:
                self.box[3] = self.box[1] + new_h
            else:
                self.box[1] = self.box[3] - new_h

    # ----------------- Build windows -----------------
    def _build_capture_win(self):
        self.cap = tk.Toplevel()
        self.cap.overrideredirect(True)
        self.cap.attributes("-topmost", True)
        # Transparent color on Windows; on other platforms may be ignored
        try:
            self.cap.attributes("-transparentcolor", "magenta")
            self.cap.config(bg="magenta")
        except Exception:
            self.cap.config(bg="#550000FF")
        bw = 2
        self.border_top = tk.Frame(self.cap, bg="red", height=bw)
        self.border_bottom = tk.Frame(self.cap, bg="red", height=bw)
        self.border_left = tk.Frame(self.cap, bg="red", width=bw)
        self.border_right = tk.Frame(self.cap, bg="red", width=bw)
        self.title_bar = tk.Frame(self.cap, bg="grey20", height=20)
        self.title_bar.bind("<Button-1>", self._on_title_press)
        self.title_bar.bind("<ButtonRelease-1>", self._on_drag_stop)
        # 右键快捷：隐藏/显示“增强显示窗口”
        self.title_bar.bind("<Button-3>", lambda e: self._toggle_show_visibility())
        self.grips = []
        colors = ["white", "green", "blue", "yellow"]
        for i in range(4):
            g = tk.Frame(self.cap, bg=colors[i], width=self.grip_size, height=self.grip_size)
            g.bind("<Button-1>", lambda e, idx=i: self.start_drag(idx))
            g.bind("<ButtonRelease-1>", self._on_drag_stop)
            self.grips.append(g)
        # 尺寸标签使用独立顶层，避免被截入 OCR 图像
        self.size_label_host = tk.Toplevel()
        self.size_label_host.overrideredirect(True)
        self.size_label_host.attributes("-topmost", True)
        try:
            self.size_label_host.attributes("-transparentcolor", "magenta")
            self.size_label_host.config(bg="magenta")
        except Exception:
            self.size_label_host.config(bg="black")
        self.size_label = tk.Label(self.size_label_host, text="", bg="black", fg="white", font=("Consolas", 10))
        self.size_label.pack()
        # key binds for fine resize
        self.cap.bind("<Shift-Left>", lambda e: self._adjust_size(-1, 0))
        self.cap.bind("<Shift-Right>", lambda e: self._adjust_size(1, 0))
        self.cap.bind("<Shift-Up>", lambda e: self._adjust_size(0, -1))
        self.cap.bind("<Shift-Down>", lambda e: self._adjust_size(0, 1))
        self._apply_geometry()
        self._update_layout()

    def _adjust_size(self, dx, dy):
        if dx:
            self.box[2] += dx
        if dy:
            self.box[3] += dy
        self._apply_geometry()
        self._update_layout()

    def _build_show_win(self):
        self.show = tk.Toplevel()
        self.show.title("增强显示窗口")
        self.show.attributes("-topmost", True)
        # 显示窗口可见性状态
        self._show_visible = True
        # 顶部工具栏
        self._toolbar_frame = ttk.Frame(self.show)
        self._toolbar_frame.pack(fill=tk.X, padx=4, pady=2)
        # 核心按钮: OCR / 处理 / 录制 / 预设 / Overflow
        self._core_buttons = []
        def _add(btn):
            self._core_buttons.append(btn); return btn
        # 预设尺寸
        ttk.Label(self._toolbar_frame, text="预设:").pack(side=tk.LEFT, padx=2)
        self.preset_var = tk.StringVar()
        self.preset_cb = ttk.Combobox(self._toolbar_frame, textvariable=self.preset_var, values=[s[0] for s in PRESET_SIZES], width=10)
        self.preset_cb.pack(side=tk.LEFT, padx=2)
        self.preset_cb.bind('<<ComboboxSelected>>', self._apply_preset_size)
        _add(self.preset_cb)
        # 图像处理按钮
        _add(ttk.Button(self._toolbar_frame, text="图像处理", command=self.open_processing_panel)).pack(side=tk.LEFT, padx=2)
        # 录制（点击弹出选择菜单）
        self.record_btn = _add(ttk.Button(self._toolbar_frame, text="录制", command=lambda: self._on_record_menu()))
        self.record_btn.pack(side=tk.LEFT, padx=2)
        try:
            self.record_btn.bind('<Button-3>', lambda e: self._on_record_menu(event=e))
        except Exception:
            pass
        # OCR
        self.ocr_btn = _add(ttk.Button(self._toolbar_frame, text="OCR", command=self.perform_ocr))
        self.ocr_btn.pack(side=tk.LEFT, padx=2)
        # AI 对话
        self.ai_chat_btn = _add(ttk.Button(self._toolbar_frame, text="AI对话", command=self.open_ai_chat_window))
        self.ai_chat_btn.pack(side=tk.LEFT, padx=2)
    # (移除) AI 图像分析按钮已迁至 AI 窗口
        # Overflow 菜单
        self._overflow_btn = ttk.Menubutton(self._toolbar_frame, text='设置')
        self._overflow_menu = tk.Menu(self._overflow_btn, tearoff=0)
        # 放入次要控件
        self.ruler_var = tk.BooleanVar(value=self.ruler_visible)
        self._grid_var = tk.BooleanVar(value=self.grid_visible)
        self._overflow_menu.add_checkbutton(label='网格', variable=self._grid_var, command=self._toggle_grid)
        self._overflow_menu.add_checkbutton(label='标尺', variable=self.ruler_var, command=self._toggle_ruler)
        self._aspect_var = tk.BooleanVar(value=self.aspect_ratio_lock)
        self._overflow_menu.add_checkbutton(label='锁定比例', variable=self._aspect_var, command=self._toggle_aspect_ratio)
        # 最大边设置子菜单
        self._overflow_menu.add_separator()
        self.ocr_max_side_var = tk.StringVar(value=str(self.ocr_max_side))
        def _set_max_side():
            v = self.ocr_max_side_var.get().strip()
            if not v: self.ocr_max_side = 0
            else:
                try:
                    num = int(v); assert num>=0; self.ocr_max_side = num
                except Exception:
                    messagebox.showwarning('最大边','请输入非负整数或留空');
                    self.ocr_max_side_var.set(str(self.ocr_max_side)); return
            self.show.title(f"增强显示窗口  OCR最大边:{self.ocr_max_side or '∞'}")
        self._overflow_menu.add_command(label='设置最大边', command=lambda: self._prompt_simple('最大边', self.ocr_max_side_var, _set_max_side))
        # 语言切换
        self._overflow_menu.add_command(label='切换语言', command=self._show_lang_dialog)
        # 释放OCR
        self._overflow_menu.add_command(label='释放 OCR', command=self.release_ocr_engine)
        # 日志级别
        import logging as _logging
        self._log_level_var = tk.StringVar(value=_logging.getLevelName(logger.level))
        def _cycle_log():
            levels = ['DEBUG','INFO','WARNING','ERROR','CRITICAL']
            cur = self._log_level_var.get().upper()
            nxt = levels[(levels.index(cur)+1)%len(levels)] if cur in levels else 'INFO'
            self._log_level_var.set(nxt)
            # 使用数值级别，兼容所有 Python 版本
            numeric = getattr(_logging, nxt, _logging.INFO)
            try:
                logger.setLevel(numeric)
            except Exception:
                try:
                    logger.setLevel(_logging.INFO)
                    nxt = 'INFO'
                except Exception:
                    pass
            # 立刻输出一条 INFO 提示，确保用户看到切换反馈
            try:
                logger.info('日志级别已切换为 %s', nxt)
                # 同步到状态栏
                self._update_status_bar('Info', f'日志级别: {nxt}')
                # 更新菜单项文本与窗口标题尾标
                if getattr(self, '_overflow_log_menu_index', None) is not None:
                    try:
                        self._overflow_menu.entryconfigure(self._overflow_log_menu_index, label=f'日志级别(循环: {nxt})')
                    except Exception:
                        pass
                try:
                    base = '增强显示窗口'
                    self.show.title(f"{base}  [Log:{nxt}]")
                except Exception:
                    pass
                # 声音提示一下
                try:
                    self.show.bell()
                except Exception:
                    pass
            except Exception:
                pass
        # 日志级别切换（记录索引，用于动态更新菜单文本）
        self._overflow_menu.add_command(label='日志级别(循环)', command=_cycle_log)
        try:
            self._overflow_log_menu_index = self._overflow_menu.index('end')
        except Exception:
            self._overflow_log_menu_index = None
        # 帧延迟显示
        self._show_delay_var = tk.BooleanVar(value=False)
        self._overflow_menu.add_checkbutton(label='显示帧延迟', variable=self._show_delay_var)
        # 视图：显示/隐藏 OCR 面板
        self._overflow_menu.add_separator()
        self._ocr_panel_visible = tk.BooleanVar(value=False)
        self._overflow_menu.add_checkbutton(label='显示 OCR 面板', variable=self._ocr_panel_visible, command=self._toggle_ocr_panel_visibility)
        # 显示/隐藏主界面
        self._show_visible_var = tk.BooleanVar(value=True)
        self._overflow_menu.add_checkbutton(label='显示主界面', variable=self._show_visible_var, command=self._toggle_show_visibility)
        # 打开/关闭捕获窗口（按钮式）
        self._cap_open = True
        self._overflow_menu.add_command(label='关闭捕获窗口', command=lambda: self._toggle_capture_open())
        try:
            self._cap_toggle_menu_index = self._overflow_menu.index('end')
        except Exception:
            self._cap_toggle_menu_index = None
        # 悬浮按钮开关（默认关闭）
        self._float_btn_visible_var = tk.BooleanVar(value=False)
        self._overflow_menu.add_checkbutton(label='显示悬浮按钮', variable=self._float_btn_visible_var, command=lambda: self._toggle_float_button_visibility(self._float_btn_visible_var.get()))
        self._overflow_btn['menu'] = self._overflow_menu
        self._overflow_btn.pack(side=tk.LEFT, padx=4)
        # 视图菜单（独立 Menubutton）
        self._view_btn = ttk.Menubutton(self._toolbar_frame, text='视图')
        self._view_menu = tk.Menu(self._view_btn, tearoff=0)
        # OCR 面板
        self._view_menu.add_checkbutton(label='显示 OCR 面板', variable=self._ocr_panel_visible, command=self._toggle_ocr_panel_visibility)
        # AI 对话侧栏
        self._ai_sidebar_visible = tk.BooleanVar(value=not getattr(self, '_chat_sidebar_hidden', True))
        self._view_menu.add_checkbutton(label='显示 AI 对话', variable=self._ai_sidebar_visible, command=lambda: self._toggle_ai_sidebar_visibility())
        # OCR 预览区
        self._ocr_preview_visible_var = tk.BooleanVar(value=True)
        self._view_menu.add_checkbutton(label='显示 OCR 预览', variable=self._ocr_preview_visible_var, command=lambda: self._set_ocr_preview_visible(self._ocr_preview_visible_var.get()))
        self._view_btn['menu'] = self._view_menu
        self._view_btn.pack(side=tk.LEFT, padx=4)
        # OCR 来源标签 (压缩为短标签)
        self.ocr_source_var = tk.StringVar(value=("后" if self.ocr_use_processed else "原"))
        ttk.Label(self._toolbar_frame, textvariable=self.ocr_source_var, width=2, relief='groove').pack(side=tk.LEFT, padx=2)
        # 状态微标签
        self.ocr_status_label = ttk.Label(self._toolbar_frame, textvariable=self.ocr_status_var, width=4)
        self.ocr_status_label.pack(side=tk.LEFT, padx=2)
        # 自适应绑定
        self.show.bind('<Configure>', self._adaptive_toolbar)
        # 主工作区: 左侧图像区域 + 中部(未来: OCR Notebook) + 右侧 AI 面板(已存在确保函数)
        # 使用 Panedwindow 便于用户调整比例
        self._main_paned = ttk.Panedwindow(self.show, orient=tk.HORIZONTAL)
        self._main_paned.pack(fill=tk.BOTH, expand=True)
        # Drawer (紧凑图标侧栏)：左侧仅图标按钮
        if getattr(self, '_drawer_ui', False):
            try:
                self._drawer_frame = ttk.Frame(self._main_paned, width=56)
                # 将抽屉插入到第一个位置
                self._main_paned.insert(0, self._drawer_frame, weight=0)
                self._build_drawer_nav(self._drawer_frame)
            except Exception:
                self._drawer_ui = False
        # 左: 图像显示容器
        self._image_frame = ttk.Frame(self._main_paned)
        self.lab = tk.Label(self._image_frame, bg='black')
        self.lab.pack(fill=tk.BOTH, expand=True)
        self._main_paned.add(self._image_frame, weight=3)
        # 右侧：折叠卡片容器宿主（方案A）
        try:
            self._right_host = ttk.Frame(self._main_paned, width=360)
            self._main_paned.add(self._right_host, weight=2)
            # 构建右侧折叠卡片（初版：提供快捷入口，逐步迁移完整 UI）
            self._build_right_accordion(self._right_host)
        except Exception:
            self._right_host = None
        # OCR 面板占位 (延迟创建, 需要时调用 _ensure_ocr_panel)
        self._ocr_panel_container = None
        # 状态栏
        self._status_bar = ttk.Frame(self.show)
        self._status_bar.pack(fill=tk.X, side=tk.BOTTOM, padx=4, pady=(0,2))
        self._sb_state = ttk.Label(self._status_bar, text='状态: 未加载', width=14, anchor='w')
        self._sb_state.pack(side=tk.LEFT)
        self._sb_delay = ttk.Label(self._status_bar, text='延迟: -', width=12, anchor='w')
        self._sb_delay.pack(side=tk.LEFT)
        self._sb_size = ttk.Label(self._status_bar, text='区域: -', width=14, anchor='w')
        self._sb_size.pack(side=tk.LEFT)
        self._sb_lang = ttk.Label(self._status_bar, text=f'Lang: {self.ocr_lang.get()}', width=10, anchor='w')
        self._sb_lang.pack(side=tk.LEFT)
        self.color_info = tk.Label(self.show, text="", font=("Consolas", 9))
        self.color_info.pack(fill=tk.X, padx=4)
        # 快捷键
        self.show.bind_all('<Control-p>', lambda e: self.open_processing_panel())
        self.show.bind_all('<Control-o>', lambda e: self.perform_ocr())
        # 仅在图像区域响应滚轮缩放，避免文本或 Notebook 上滚动时误触发缩放
        self.lab.bind('<MouseWheel>', self.on_wheel)
        # F2 切换 OCR 面板可见性
        self.show.bind_all('<F2>', lambda e: self._toggle_ocr_panel_visibility_kb())
        # F3 切换 AI 侧栏
        self.show.bind_all('<F3>', lambda e: self._toggle_ai_sidebar_visibility_kb())
        # F12 切换增强显示窗口可见性
        self.show.bind_all('<F12>', lambda e: self._toggle_show_visibility())
        # 右键：弹出图像区菜单（仅保存截图）
        self.lab.bind('<Button-3>', self._on_lab_context_menu)
        self.lab.bind('<Motion>', self._show_color_info)
        self._update_ocr_status('未加载')

        # 初始导航：若有待应用的页面或抽屉折叠状态，这里应用
        try:
            if getattr(self, '_drawer_ui', False):
                if hasattr(self, '_pending_drawer_collapsed'):
                    self._set_drawer_collapsed(bool(self._pending_drawer_collapsed))
                    delattr(self, '_pending_drawer_collapsed')
                if hasattr(self, '_pending_active_page'):
                    self._navigate(self._pending_active_page)
                    delattr(self, '_pending_active_page')
                else:
                    self._navigate(getattr(self, '_active_page', 'preview'))
            # 应用窗口可见性
            if hasattr(self, '_pending_show_visible'):
                if not bool(self._pending_show_visible):
                    try:
                        self.show.withdraw(); self._show_visible = False
                        if hasattr(self, '_show_visible_var'): self._show_visible_var.set(False)
                    except Exception: pass
                delattr(self, '_pending_show_visible')
            # 构建悬浮按钮并应用持久化
            try:
                # 构建浮窗（默认隐藏），随后根据配置决定显示/隐藏
                self._ensure_float_button()
                want_visible = None
                if hasattr(self, '_pending_float_btn_visible'):
                    want_visible = bool(self._pending_float_btn_visible)
                    delattr(self, '_pending_float_btn_visible')
                else:
                    want_visible = bool(self._float_btn_visible_var.get())
                # 应用几何（即便隐藏也应用，便于恢复）
                if hasattr(self, '_pending_float_btn_geometry'):
                    geo = self._pending_float_btn_geometry
                    try:
                        self._float_btn_win.geometry(geo)
                    except Exception:
                        pass
                    delattr(self, '_pending_float_btn_geometry')
                # 根据期望状态显示/隐藏
                self._toggle_float_button_visibility(bool(want_visible))
            except Exception:
                pass
        except Exception:
            pass

    # 显示/隐藏增强显示窗口
    def _toggle_show_visibility(self):
        try:
            if getattr(self, '_show_visible', True):
                try:
                    self.show.withdraw()
                except Exception:
                    pass
                self._show_visible = False
                # 主窗隐藏时，恢复捕获层为 topmost，便于继续覆盖录屏/取色
                try:
                    if getattr(self, 'cap', None):
                        self.cap.attributes('-topmost', True)
                except Exception:
                    pass
            else:
                # 使用更稳健的置顶逻辑
                try:
                    self._raise_show_window()
                except Exception:
                    pass
            if hasattr(self, '_show_visible_var'):
                try: self._show_visible_var.set(self._show_visible)
                except Exception: pass
            # 同步悬浮按钮显示（主界面隐藏时悬浮按钮通常应可见）
            try:
                if getattr(self, '_float_btn_win', None) and self._float_btn_win.winfo_exists():
                    if not self._show_visible and not self._float_btn_visible_var.get():
                        self._toggle_float_button_visibility(True)
            except Exception:
                pass
            self._schedule_config_changed()
        except Exception:
            pass

    def _toggle_capture_visibility(self):
        """显示/隐藏捕获窗口（cap 顶层）。"""
        try:
            if not getattr(self, 'cap', None):
                return
            if bool(self._cap_visible_var.get()):
                try:
                    self.cap.deiconify(); self.cap.lift(); self.cap.attributes('-topmost', True)
                except Exception:
                    pass
            else:
                try:
                    self.cap.withdraw()
                except Exception:
                    pass
            self._schedule_config_changed()
        except Exception:
            pass

    def _toggle_capture_open(self):
        """打开/关闭捕获窗口（与显示/隐藏不同，关闭后不响应拖拽，打开时重建必要状态）。"""
        try:
            self._cap_open = not getattr(self, '_cap_open', True)
            if self._cap_open:
                # 打开：确保显示并置顶
                try:
                    self.cap.deiconify(); self.cap.lift(); self.cap.attributes('-topmost', True)
                    if getattr(self, 'size_label_host', None):
                        self.size_label_host.deiconify(); self.size_label_host.lift(); self.size_label_host.attributes('-topmost', True)
                except Exception:
                    pass
                # 重建事件绑定
                try:
                    self._bind_capture_events()
                except Exception:
                    pass
                # 更新菜单文字
                try:
                    if getattr(self, '_cap_toggle_menu_index', None) is not None:
                        self._overflow_menu.entryconfigure(self._cap_toggle_menu_index, label='关闭捕获窗口')
                except Exception:
                    pass
            else:
                # 关闭：隐藏并禁用交互（简单实现：withdraw 即可）
                try:
                    self.cap.withdraw()
                    if getattr(self, 'size_label_host', None):
                        self.size_label_host.withdraw()
                except Exception:
                    pass
                # 解绑事件，彻底禁用交互
                try:
                    self._unbind_capture_events()
                except Exception:
                    pass
                try:
                    if getattr(self, '_cap_toggle_menu_index', None) is not None:
                        self._overflow_menu.entryconfigure(self._cap_toggle_menu_index, label='打开捕获窗口')
                except Exception:
                    pass
            self._schedule_config_changed()
        except Exception:
            pass

    def _bind_capture_events(self):
        """绑定捕获窗口（cap/title_bar/grips）的交互事件（先解绑再绑定，避免重复）。"""
        try:
            if not getattr(self, 'cap', None):
                return
            # 先解绑
            self._unbind_capture_events()
            # 重新绑定 title_bar
            try:
                self.title_bar.bind("<Button-1>", self._on_title_press)
                self.title_bar.bind("<ButtonRelease-1>", self._on_drag_stop)
                self.title_bar.bind("<Button-3>", lambda e: self._toggle_show_visibility())
            except Exception:
                pass
            # 重新绑定四个角的 grip
            try:
                for i, g in enumerate(getattr(self, 'grips', []) or []):
                    g.bind("<Button-1>", lambda e, idx=i: self.start_drag(idx))
                    g.bind("<ButtonRelease-1>", self._on_drag_stop)
            except Exception:
                pass
            # 键盘微调
            try:
                self.cap.bind("<Shift-Left>", lambda e: self._adjust_size(-1, 0))
                self.cap.bind("<Shift-Right>", lambda e: self._adjust_size(1, 0))
                self.cap.bind("<Shift-Up>", lambda e: self._adjust_size(0, -1))
                self.cap.bind("<Shift-Down>", lambda e: self._adjust_size(0, 1))
            except Exception:
                pass
            self._cap_bound = True
        except Exception:
            pass

    def _unbind_capture_events(self):
        """解绑捕获窗口相关事件，彻底禁用交互。"""
        try:
            if not getattr(self, 'cap', None):
                return
            # 取消进行中的拖拽/缩放
            try:
                self.drag_mode = None
                self.start_pos = None
                self.start_box = None
            except Exception:
                pass
            # title_bar
            try:
                self.title_bar.unbind("<Button-1>")
                self.title_bar.unbind("<ButtonRelease-1>")
                self.title_bar.unbind("<Button-3>")
            except Exception:
                pass
            # grips
            try:
                for g in getattr(self, 'grips', []) or []:
                    g.unbind("<Button-1>")
                    g.unbind("<ButtonRelease-1>")
            except Exception:
                pass
            # 键盘微调
            try:
                self.cap.unbind("<Shift-Left>")
                self.cap.unbind("<Shift-Right>")
                self.cap.unbind("<Shift-Up>")
                self.cap.unbind("<Shift-Down>")
            except Exception:
                pass
            self._cap_bound = False
        except Exception:
            pass

    def _on_record_menu(self, event=None):
        """录制按钮的选择菜单：
        - 保存当前屏幕为图片（快照）
        - 从文件选择图片进行 OCR
        - 从文件夹批量选择进行 OCR
        - 录制为视频（占位，后续可实现）
        """
        try:
            menu = tk.Menu(self.show, tearoff=0)
            menu.add_command(label='📷 保存当前屏幕为图片', command=self.save_snapshot)
            # 文件/文件夹识别入口迁移到 OCR 工作台
            menu.add_separator()
            menu.add_command(label='🎞️ 录制为视频（即将支持）', command=self._record_video_stub)
            if event is not None and hasattr(event, 'x_root'):
                x = int(event.x_root); y = int(event.y_root)
            else:
                x = self.record_btn.winfo_rootx()
                y = self.record_btn.winfo_rooty() + self.record_btn.winfo_height()
            menu.post(x, y)
        except Exception:
            pass

    def _perform_ocr_from_folder(self):
        try:
            folder = filedialog.askdirectory(title='选择文件夹进行 OCR 识别')
            if not folder:
                return
            exts = {'.png','.jpg','.jpeg','.bmp','.webp'}
            paths = []
            for name in os.listdir(folder):
                p = os.path.join(folder, name)
                if os.path.isfile(p) and os.path.splitext(p)[1].lower() in exts:
                    paths.append(p)
            if not paths:
                messagebox.showinfo('OCR','该文件夹没有可识别的图片'); return
            # 简单串行处理（后续可加进度与并发）
            if self.ocr_manager is None:
                messagebox.showwarning('OCR','OCR 模块初始化失败'); return
            if self.ocr_status_var.get() in ('未加载','已释放'):
                self._warmup_ocr_async()
            if self.ocr_status_var.get() != '就绪':
                messagebox.showinfo('OCR','OCR 引擎未就绪'); return
            results = []
            def _run_folder():
                try:
                    self._update_ocr_status('识别中')
                    for p in paths:
                        try:
                            img = Image.open(p).convert('RGB')
                            meta, lines = self.ocr_manager.perform(img, use_processed=False, max_side=self.ocr_max_side)
                            results.append((p, lines))
                        except Exception as e:
                            logger.warning('识别失败 %s: %s', p, e)
                    # 展示最后一张的文本，并简单统计
                    if results:
                        last_lines = results[-1][1]
                        self.last_ocr_result = {'meta': {}, 'results': last_lines}
                        self._open_ocr_text_window()
                        text_lines = [ln.get('text','') for ln in last_lines if ln.get('text')]
                        if hasattr(self, '_ocr_text_widget'):
                            self._ocr_text_widget.delete('1.0', tk.END)
                            self._ocr_text_widget.insert('1.0', '\n'.join(text_lines))
                            try: self._apply_conf_filter()
                            except Exception: pass
                        self._update_status_bar('OCR', f'完成 {len(results)} 张')
                finally:
                    if self.ocr_manager and self.ocr_manager.is_loaded:
                        self._update_ocr_status('就绪')
                    else:
                        self._update_ocr_status('未加载')
            threading.Thread(target=_run_folder, daemon=True).start()
        except Exception:
            pass

    def _record_video_stub(self):
        try:
            messagebox.showinfo('录制','视频录制功能将很快提供（可选择编码器/帧率/区域），当前可先使用“保存当前屏幕为图片”。')
        except Exception:
            pass

    def _raise_show_window(self):
        """强力将主窗显示并置于捕获层之上（兼容 Windows 覆盖与焦点问题）。"""
        try:
            # 显示并恢复正常状态
            try:
                self.show.deiconify()
            except Exception:
                pass
            try:
                self.show.state('normal')
            except Exception:
                pass
            # 标记可见
            self._show_visible = True
            if hasattr(self, '_show_visible_var'):
                try:
                    self._show_visible_var.set(True)
                except Exception:
                    pass
            # 主窗显示时，将捕获层取消 topmost，避免其压住主窗
            try:
                if getattr(self, 'cap', None):
                    self.cap.attributes('-topmost', False)
            except Exception:
                pass
            # 设主窗为 topmost 并抬到最前
            try:
                self.show.attributes('-topmost', True)
            except Exception:
                pass
            try:
                self.show.lift()
            except Exception:
                pass
            try:
                self.show.focus_force()
            except Exception:
                pass
            try:
                self.show.update_idletasks()
            except Exception:
                pass
        except Exception:
            pass

    # ----------------- Float Button (单图标悬浮按钮) -----------------
    def _ensure_float_button(self):
        # 悬浮状态变量（点击/拖拽判定与起始信息）初始化
        if not hasattr(self, '_float_drag'):
            self._float_drag = None  # (press_x, press_y, win_x, win_y)
        self._float_press_pos = None  # (press_x, press_y)
        self._float_moved = False
        self._float_handled_release = False  # 防止释放事件被重复处理
        # 悬浮球配置默认值
        if not hasattr(self, '_float_alpha'):
            self._float_alpha = 0.9
        if not hasattr(self, '_float_snap_enabled'):
            self._float_snap_enabled = True
        if not hasattr(self, '_float_base_size'):
            self._float_base_size = 64
        # 复用全局浮窗（若已存在），避免重复创建
        try:
            gfb = getattr(CapturePreviewDuoEnhanced, '_GLOBAL_FLOAT_BTN_WIN', None)
            if gfb is not None and gfb.winfo_exists():
                self._float_btn_win = gfb
                return
        except Exception:
            pass
        if getattr(self, '_float_btn_win', None) and self._float_btn_win.winfo_exists():
            # 本实例已有
            return
        # 独立顶层，不隶属于 show，避免主窗 withdraw 时一并隐藏
        fb = tk.Toplevel()
        fb.overrideredirect(True)
        fb.attributes('-topmost', True)
        try:
            fb.lift()
        except Exception:
            pass
        # 外观：半透明与更大尺寸
        try:
            fb.attributes('-alpha', float(self._float_alpha))
        except Exception:
            pass
        fb.geometry(f'{self._float_base_size}x{self._float_base_size}+40+80')
        try:
            fb.title('SC-FLOAT-BTN')  # 唯一标识，便于排查
        except Exception:
            pass
        # 设置顶层背景与透明色，营造圆形效果
        try:
            fb.attributes('-transparentcolor', 'black')
        except Exception:
            pass
        try:
            fb.configure(bg='black')
        except Exception:
            pass
        # 简单风格：圆形按钮
        frm = ttk.Frame(fb)
        frm.pack(fill=tk.BOTH, expand=True)
        btn = tk.Canvas(frm, width=self._float_base_size, height=self._float_base_size, highlightthickness=0, bg='black', bd=0)
        btn.pack(fill=tk.BOTH, expand=True)
        self._float_canvas = btn
        try:
            # 初始绘制
            self._redraw_float_canvas()
        except Exception:
            pass
        # 交互：拖动与点击
        # 悬停视觉反馈
        def _hover_enter(_e=None):
            try:
                fb.attributes('-alpha', min(float(self._float_alpha) + 0.05, 1.0))
            except Exception:
                pass
        def _hover_leave(_e=None):
            try:
                fb.attributes('-alpha', float(self._float_alpha))
            except Exception:
                pass
        btn.bind('<Enter>', _hover_enter)
        btn.bind('<Leave>', _hover_leave)
        # 绑定到 Canvas、Frame 与 顶层窗口，避免窗口几何变化时子控件丢失 B1-Motion 事件
        btn.bind('<Button-1>', self._on_float_press)
        btn.bind('<B1-Motion>', self._on_float_drag)
        btn.bind('<ButtonRelease-1>', self._on_float_release)
        # 点击改为在释放时判定（避免按下即弹出主窗遮挡拖拽）
        btn.bind('<ButtonRelease-1>', self._float_btn_release_click, add='+')
        # 右键弹出菜单
        btn.bind('<Button-3>', self._show_float_button_menu)

        frm.bind('<Button-1>', self._on_float_press)
        frm.bind('<B1-Motion>', self._on_float_drag)
        frm.bind('<ButtonRelease-1>', self._on_float_release)
        frm.bind('<ButtonRelease-1>', self._float_btn_release_click, add='+')
        frm.bind('<Button-3>', self._show_float_button_menu)

        fb.bind('<Button-1>', self._on_float_press)
        fb.bind('<B1-Motion>', self._on_float_drag)
        fb.bind('<ButtonRelease-1>', self._on_float_release)
        fb.bind('<ButtonRelease-1>', self._float_btn_release_click, add='+')
        fb.bind('<Button-3>', self._show_float_button_menu)
        self._float_btn_win = fb
        try:
            CapturePreviewDuoEnhanced._GLOBAL_FLOAT_BTN_WIN = fb
        except Exception:
            pass

    def _toggle_float_button_visibility(self, flag: bool):
        try:
            self._ensure_float_button()
            if flag:
                try: self._float_btn_win.deiconify(); self._float_btn_win.lift()
                except Exception: pass
            else:
                try: self._float_btn_win.withdraw()
                except Exception: pass
            if hasattr(self, '_float_btn_visible_var'):
                try: self._float_btn_visible_var.set(bool(flag))
                except Exception: pass
            self._schedule_config_changed()
        except Exception:
            pass

    def _on_float_press(self, event):
        try:
            win = self._float_btn_win
            if not win: return
            self._float_drag = (event.x_root, event.y_root, win.winfo_x(), win.winfo_y())
            self._float_press_pos = (event.x_root, event.y_root)
            self._float_moved = False
            self._float_handled_release = False
            # 记录按下时间（用于长按判定）
            try:
                self._float_press_time = getattr(event, 'time', int(time.time()*1000))
            except Exception:
                self._float_press_time = int(time.time()*1000)
            # 鼠标捕获，避免拖拽过程中指针移出按钮后事件丢失
            try:
                win.lift(); win.attributes('-topmost', True)
                # 优先使用全局捕获，避免事件丢失；失败则退回到本窗捕获
                try:
                    win.grab_set_global()
                except Exception:
                    win.grab_set()
                win.config(cursor='fleur')
            except Exception:
                pass
            try:
                logger.debug('float_press at (%s,%s), win=(%s,%s)', event.x_root, event.y_root, win.winfo_x(), win.winfo_y())
            except Exception:
                pass
        except Exception:
            pass

    def _on_float_drag(self, event):
        try:
            if not self._float_drag: return
            x0, y0, wx, wy = self._float_drag
            dx, dy = event.x_root - x0, event.y_root - y0
            nx, ny = wx + dx, wy + dy
            # 屏幕边界约束（基于当前窗口尺寸）
            try:
                sw = self._float_btn_win.winfo_screenwidth()
                sh = self._float_btn_win.winfo_screenheight()
                try:
                    w = int(self._float_btn_win.winfo_width()) or self._float_base_size
                    h = int(self._float_btn_win.winfo_height()) or self._float_base_size
                except Exception:
                    w, h = self._float_base_size, self._float_base_size
                nx = max(0, min(nx, sw - w))
                ny = max(0, min(ny, sh - h))
            except Exception:
                pass
            # 只更新位置，保持当前大小
            self._float_btn_win.geometry(f"+{int(nx)}+{int(ny)}")
            # 立即刷新，避免拖动视觉延迟
            try:
                self._float_btn_win.update_idletasks()
            except Exception:
                pass
            # 超过阈值视为拖拽
            try:
                px, py = getattr(self, '_float_press_pos', (x0, y0))
                if abs(event.x_root - px) + abs(event.y_root - py) > 3:
                    self._float_moved = True
                try:
                    logger.debug('float_drag to (%s,%s) -> geom %s', event.x_root, event.y_root, self._float_btn_win.geometry())
                except Exception:
                    pass
            except Exception:
                pass
        except Exception:
            pass

    def _on_float_release(self, _event):
        try:
            self._float_drag = None
            try:
                if getattr(self, '_float_btn_win', None):
                    self._float_btn_win.grab_release()
                    self._float_btn_win.config(cursor='')
            except Exception:
                pass
            try:
                logger.debug('float_release, moved=%s, geom=%s', getattr(self, '_float_moved', False), self._float_btn_win.geometry() if getattr(self, '_float_btn_win', None) else 'n/a')
            except Exception:
                pass
            # 边缘吸附（可配置）：释放时若靠近边缘自动贴边
            if getattr(self, '_float_snap_enabled', True):
                try:
                    win = self._float_btn_win
                    sw = win.winfo_screenwidth(); sh = win.winfo_screenheight()
                    w = int(win.winfo_width()) or self._float_base_size
                    h = int(win.winfo_height()) or self._float_base_size
                    x, y = win.winfo_x(), win.winfo_y()
                    SNAP = 20
                    # X方向
                    if x < SNAP:
                        x = 0
                    elif x > sw - w - SNAP:
                        x = sw - w
                    # Y方向
                    if y < SNAP:
                        y = 0
                    elif y > sh - h - SNAP:
                        y = sh - h
                    win.geometry(f'+{x}+{y}')
                except Exception:
                    pass
            # 释放后持久化几何
            try:
                self._schedule_config_changed()
            except Exception:
                pass
        except Exception:
            pass

    def _float_btn_release_click(self, event=None):
        # 仅在未发生拖拽时才认定为“点击”
        try:
            # 防重复处理（Canvas 与 Toplevel 均绑定了释放事件）
            if getattr(self, '_float_handled_release', False):
                return
            self._float_handled_release = True
            if getattr(self, '_float_moved', False):
                self._float_moved = False
                # 清理一次按压起点
                self._float_press_pos = None
                return
            # 轻微点击动画反馈
            try:
                win = self._float_btn_win
                gx = win.winfo_x(); gy = win.winfo_y()
                for dx in (1,-1,1,-1,0):
                    win.geometry(f"+{gx+dx}+{gy}"); win.update_idletasks()
            except Exception:
                pass
            # 点击展开主界面：如果隐藏则显示；若已显示则置顶聚焦
            try:
                self._raise_show_window()
            except Exception:
                pass
            # 释放清理
            self._float_press_pos = None
            self._float_drag = None
        except Exception:
            pass

    def _show_float_button_menu(self, event=None):
        """显示悬浮球快捷菜单（右键）。支持事件坐标。"""
        try:
            if not getattr(self, '_float_btn_win', None):
                return
            menu = tk.Menu(self._float_btn_win, tearoff=0)
            try:
                # 基础外观（深色）
                menu.configure(bg='#2d3748', fg='white', activebackground='#4a5568', activeforeground='white')
            except Exception:
                pass
            menu.add_command(label='📷 截图', command=self.save_snapshot)
            menu.add_command(label='🔍 OCR识别', command=self.perform_ocr)
            menu.add_command(label='🤖 AI分析', command=self.analyze_current_frame)
            menu.add_separator()
            menu.add_command(label='⚙️ 悬浮球设置', command=lambda: self._open_float_settings(event))
            menu.add_command(label='❌ 隐藏悬浮球', command=lambda: self._toggle_float_button_visibility(False))
            # 菜单位置：优先使用右键事件位置；否则在悬浮球下方
            if event is not None and hasattr(event, 'x_root'):
                x = int(event.x_root); y = int(event.y_root)
            else:
                x = self._float_btn_win.winfo_rootx()
                y = self._float_btn_win.winfo_rooty() + (int(self._float_btn_win.winfo_height()) or self._float_base_size)
            menu.post(x, y)
        except Exception:
            pass

    # ---------- 悬浮球设置（就地弹窗） ----------
    def _open_float_settings(self, event=None):
        try:
            # 若已有设置窗，先销毁
            if hasattr(self, '_float_settings_win') and self._float_settings_win and self._float_settings_win.winfo_exists():
                try: self._float_settings_win.destroy()
                except Exception: pass
            win = tk.Toplevel(self._float_btn_win)
            self._float_settings_win = win
            win.overrideredirect(True)
            try:
                win.attributes('-topmost', True)
            except Exception:
                pass
            frm = ttk.Frame(win, padding=8)
            frm.pack(fill=tk.BOTH, expand=True)
            ttk.Label(frm, text='悬浮球设置', font=('Segoe UI', 9, 'bold')).pack(anchor='w')
            # Alpha
            alpha_row = ttk.Frame(frm); alpha_row.pack(fill=tk.X, pady=(6,2))
            ttk.Label(alpha_row, text='透明度:').pack(side=tk.LEFT)
            alpha_var = tk.DoubleVar(value=float(getattr(self, '_float_alpha', 0.9)))
            alpha_scale = ttk.Scale(alpha_row, from_=0.5, to=1.0, orient='horizontal', variable=alpha_var)
            alpha_scale.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=6)
            # Size
            size_row = ttk.Frame(frm); size_row.pack(fill=tk.X, pady=(6,2))
            ttk.Label(size_row, text='尺寸:').pack(side=tk.LEFT)
            size_var = tk.IntVar(value=int(getattr(self, '_float_base_size', 64)))
            size_cb = ttk.Combobox(size_row, width=6, state='readonly', values=['48','56','64','72','80'], textvariable=tk.StringVar(value=str(size_var.get())))
            size_cb.pack(side=tk.LEFT, padx=6)
            # Snap
            snap_var = tk.BooleanVar(value=bool(getattr(self, '_float_snap_enabled', True)))
            ttk.Checkbutton(frm, text='释放吸边', variable=snap_var).pack(anchor='w', pady=(6,2))
            # Action row
            act = ttk.Frame(frm); act.pack(fill=tk.X, pady=(8,0))
            def _apply():
                try:
                    self._float_alpha = float(alpha_var.get())
                except Exception:
                    self._float_alpha = 0.9
                try:
                    self._float_snap_enabled = bool(snap_var.get())
                except Exception:
                    self._float_snap_enabled = True
                try:
                    sel = size_cb.get().strip()
                    self._apply_float_size(int(sel) if sel else int(size_var.get()))
                except Exception:
                    pass
                # 应用 alpha
                try:
                    self._float_btn_win.attributes('-alpha', float(self._float_alpha))
                except Exception:
                    pass
                # 关闭窗口
                try: win.destroy()
                except Exception: pass
                # 持久化
                self._schedule_config_changed()
            ttk.Button(act, text='应用', command=_apply).pack(side=tk.RIGHT)
            ttk.Button(act, text='关闭', command=lambda: win.destroy()).pack(side=tk.RIGHT, padx=(0,6))
            # 定位：靠近鼠标或球下方
            try:
                if event is not None and hasattr(event, 'x_root'):
                    x = int(event.x_root); y = int(event.y_root)
                else:
                    x = self._float_btn_win.winfo_rootx()
                    y = self._float_btn_win.winfo_rooty() + (int(self._float_btn_win.winfo_height()) or self._float_base_size)
                win.update_idletasks()
                # 偏移一点以避免遮挡
                win.geometry(f"+{x+6}+{y+6}")
            except Exception:
                pass
        except Exception:
            pass

    def _apply_float_size(self, sz: int):
        try:
            sz = max(40, min(120, int(sz)))
            self._float_base_size = sz
            # 更新几何
            try:
                x = self._float_btn_win.winfo_x(); y = self._float_btn_win.winfo_y()
                self._float_btn_win.geometry(f"{sz}x{sz}+{x}+{y}")
            except Exception:
                pass
            # 更新画布尺寸与重绘
            try:
                self._float_canvas.config(width=sz, height=sz)
            except Exception:
                pass
            self._redraw_float_canvas()
        except Exception:
            pass

    def _redraw_float_canvas(self):
        try:
            if not getattr(self, '_float_canvas', None):
                return
            c = self._float_canvas
            sz = int(getattr(self, '_float_base_size', 64))
            c.delete('all')
            # 边距与视觉元素基于尺寸自适应
            pad = max(2, int(sz*0.03))
            c.create_oval(pad, pad, sz-pad, sz-pad, fill='#4a7aff', outline='#2b6cb0', width=max(1, int(sz*0.03)))
            c.create_oval(pad+2, pad+2, sz-(pad+2), sz-(pad+2), fill='#2b6cb0', outline='#1e4e8c', width=max(1, int(sz*0.02)))
            # 内部小高光
            hi = int(sz*0.375)
            c.create_oval(pad+int(sz*0.125), pad+int(sz*0.125), pad+int(sz*0.125)+hi, pad+int(sz*0.125)+hi, fill='#63b3ed', outline='')
            # 图标（保持居中）
            c.create_text(sz//2, sz//2, text='⚲', fill='white', font=('Segoe UI Symbol', max(12, int(sz*0.25)), 'bold'))
        except Exception:
            pass

        # after core buttons creation, attach tooltips
        for btn in getattr(self, '_core_buttons', []):
            if isinstance(btn, ttk.Combobox):
                Tooltip(btn, '选择预设尺寸')
            else:
                label = btn.cget('text')
                if label.startswith('处理'): Tooltip(btn, '打开处理器面板 (Ctrl+P)')
                elif label.startswith('录制'): Tooltip(btn, '开始/停止序列帧录制')
                elif label.startswith('OCR'): Tooltip(btn, '执行OCR (Ctrl+O)')
                elif label.startswith('AI对话'): Tooltip(btn, '打开 AI 对话窗口 (发送 OCR 文本或自定义问题)')
                # 移除 AI图像分析 的工具提示绑定（按钮已删除）
        if hasattr(self, '_overflow_btn'):
            Tooltip(self._overflow_btn, '更多...')

    # ----------------- AI 可用性 UI 同步 -----------------
    def _update_ai_availability_ui(self):
        try:
            ready = bool(getattr(self, 'ai_client', None) and self.ai_client and getattr(self.ai_client, 'ready', False))
            # 顶部工具栏按钮：AI 对话、AI 图像分析
            try:
                if hasattr(self, 'ai_chat_btn') and self.ai_chat_btn:
                    self.ai_chat_btn.config(state=(tk.NORMAL if ready else tk.DISABLED))
                    Tooltip(self.ai_chat_btn, 'AI 已就绪' if ready else 'AI 客户端不可用：请配置 API Key 或安装依赖')
            except Exception:
                pass
            try:
                if hasattr(self, 'ai_vision_btn') and self.ai_vision_btn:
                    self.ai_vision_btn.config(state=(tk.NORMAL if ready else tk.DISABLED))
                    Tooltip(self.ai_vision_btn, '对当前截取图像进行多模态分析' if ready else 'AI 客户端不可用：请配置 API Key 或安装依赖')
            except Exception:
                pass
            # OCR 面板中的“AI编排”按钮
            try:
                if hasattr(self, 'refresh_ai_controls_enabled') and callable(self.refresh_ai_controls_enabled):
                    self.refresh_ai_controls_enabled()
            except Exception:
                pass
            # 状态栏反馈
            try:
                self._update_status_bar('AI', 'OK' if ready else '未就绪')
            except Exception:
                pass
        except Exception:
            pass

    def _prompt_simple(self, title, var: tk.StringVar, on_ok: Callable):
        win = tk.Toplevel(self.show); win.title(title); win.transient(self.show); win.grab_set()
        ttk.Label(win, text=title).pack(padx=8, pady=(8,4))
        entry = ttk.Entry(win, textvariable=var, width=12); entry.pack(padx=8, pady=4); entry.focus()
        def _ok():
            on_ok(); win.destroy()
        ttk.Button(win, text='确定', command=_ok).pack(pady=(4,8))
        win.bind('<Return>', lambda e: _ok())

    # ----------------- Drawer Navigation (MVP) -----------------
    def _build_drawer_nav(self, host: ttk.Frame):
        # 图标侧栏头部（窄宽度，不显示标题，仅保留汉堡）
        head = ttk.Frame(host)
        head.pack(fill=tk.X, padx=6, pady=(6,4))
        ttk.Button(head, text='≡', width=3, command=self._toggle_drawer_collapsed).pack(side=tk.LEFT)

        # 菜单项（仅图标+提示）
        body = ttk.Frame(host)
        body.pack(fill=tk.BOTH, expand=True, padx=4)

        def add_icon_button(text: str, route: str, hotkey: str|None=None):
            def _nav(): self._navigate(route)
            btn = ttk.Button(body, text=text[:2], width=4, command=_nav)
            btn.pack(padx=2, pady=2)
            try:
                Tooltip(btn, text)
            except Exception:
                pass
            if hotkey:
                try: self.show.bind_all(hotkey, lambda e: _nav())
                except Exception: pass
            return btn

        add_icon_button('预览', 'preview', '<Control-Key-1>')
        add_icon_button('OCR 工作台', 'ocr', '<Control-Key-2>')
        add_icon_button('AI 助手', 'ai', '<Control-Key-3>')
        add_icon_button('图像处理', 'process', '<Control-Key-4>')
        add_icon_button('录制/快照', 'record', '<Control-Key-5>')
        add_icon_button('设置', 'settings', '<Control-Key-6>')

        # 底部状态最简化（点）
        foot = ttk.Frame(host)
        foot.pack(fill=tk.BOTH, expand=True)
        self._drawer_status = ttk.Label(foot, text='·', anchor='center')
        self._drawer_status.pack(side=tk.BOTTOM, pady=4)

    def _set_drawer_collapsed(self, collapsed: bool):
        self._drawer_collapsed = bool(collapsed)
        if hasattr(self, '_drawer_frame') and self._drawer_frame.winfo_exists():
            try:
                if self._drawer_collapsed:
                    self._main_paned.forget(self._drawer_frame)  # 临时简单实现：移除
                else:
                    # 重新插回最左
                    self._main_paned.insert(0, self._drawer_frame, weight=0)
                self._schedule_config_changed()
            except Exception:
                pass

    def _toggle_drawer_collapsed(self):
        self._set_drawer_collapsed(not getattr(self, '_drawer_collapsed', False))

    def _navigate(self, route: str):
        # 记录与状态栏
        self._active_page = route
        try:
            if hasattr(self, '_drawer_status'):
                self._drawer_status.config(text=f"Page: {route}")
        except Exception:
            pass
        # 路由到对应视图（MVP：用现有视图的显示/隐藏来模拟）
        if route == 'preview':
            # 预览页：仅显示左侧图像，不强制显示 OCR/AI
            # 隐藏 OCR 面板（可保留用户偏好：此处选择隐藏，保证页面语义）
            try: self.hide_ocr_panel()
            except Exception: pass
            # 隐藏 AI 侧栏
            try: self.hide_ai_sidebar()
            except Exception: pass
            # 隐藏处理页控件
            try: self._hide_process_page()
            except Exception: pass
            # 右侧卡片全部收起
            try: self._show_right_card(None)
            except Exception: pass
        elif route == 'ocr':
            # OCR 工作台：显示 OCR 面板，AI 侧栏默认隐藏（用户可 F3 弹出）
            try: self.show_ocr_panel(focus_text=False)
            except Exception: pass
            try: self.hide_ai_sidebar()
            except Exception: pass
            try: self._hide_process_page()
            except Exception: pass
            try: self._show_right_card('ocr')
            except Exception: pass
        elif route == 'ai':
            # AI 助手页：以整页心智为主，隐藏 OCR 面板；允许 F3 停靠侧栏
            try: self.hide_ocr_panel()
            except Exception: pass
            # 整页模式：简单做法——显示侧栏以替代整页（MVP）。后续可为 AI 构建专用页 Frame。
            try: self.show_ai_sidebar()
            except Exception: pass
            try: self._hide_process_page()
            except Exception: pass
            try: self._show_right_card('ai')
            except Exception: pass
        elif route == 'process':
            # 图像处理页：左控件，右预览；隐藏 OCR 与 AI
            try: self.hide_ocr_panel()
            except Exception: pass
            try: self.hide_ai_sidebar()
            except Exception: pass
            try: self._show_process_page()
            except Exception: pass
            try: self._show_right_card('process')
            except Exception: pass
        elif route == 'record':
            # 录制/快照页：隐藏 OCR 与 AI，显示录制页
            try: self.hide_ocr_panel()
            except Exception: pass
            try: self.hide_ai_sidebar()
            except Exception: pass
            try: self._show_record_page()
            except Exception: pass
            try: self._show_right_card('record')
            except Exception: pass
        elif route == 'settings':
            # 设置页：显示设置页，隐藏其它页
            try: self.hide_ocr_panel()
            except Exception: pass
            try: self.hide_ai_sidebar()
            except Exception: pass
            try: self._show_settings_page()
            except Exception: pass
            try: self._show_right_card('settings')
            except Exception: pass
        else:
            # 其它页暂为占位：回到预览语义
            try:
                self.hide_ocr_panel(); self.hide_ai_sidebar(); self._hide_process_page()
            except Exception:
                pass
        # 通知配置变更
        self._schedule_config_changed()

    # ----------------- 右侧折叠卡片（方案A骨架） -----------------
    def _build_right_accordion(self, host: ttk.Frame):
        self._right_cards = {}

        def _add_card(key: str, title: str):
            cf = CollapsibleFrame(host, text=title, collapsed=True)
            cf.pack(fill=tk.X, padx=6, pady=4)
            self._right_cards[key] = cf
            return cf.content

        # Processing 快捷卡
        cont = _add_card('process', '图像处理 (快捷)')
        ttk.Label(cont, text='打开完整处理器窗口以管理处理链。').pack(anchor='w')
        ttk.Button(cont, text='打开处理器窗口', command=self.open_processing_panel).pack(anchor='w', pady=4)
        ttk.Button(cont, text='切换到处理页', command=lambda: self._navigate('process')).pack(anchor='w')

        # OCR 快捷卡
        cont = _add_card('ocr', 'OCR 工作台 (快捷)')
        ttk.Button(cont, text='执行 OCR', command=self.perform_ocr).pack(anchor='w')
        ttk.Button(cont, text='显示/隐藏 OCR 面板', command=self._toggle_ocr_panel_visibility).pack(anchor='w', pady=4)
        ttk.Button(cont, text='AI 编排', command=lambda: getattr(self, '_ocr_ai_refine', lambda: None)()).pack(anchor='w')

        # AI 快捷卡
        cont = _add_card('ai', 'AI 助手 (快捷)')
        ttk.Button(cont, text='打开 AI 对话', command=self.open_ai_chat_window).pack(anchor='w')

        # 录制/快照 卡
        cont = _add_card('record', '录制与快照 (快捷)')
        ttk.Button(cont, text='开始/停止录制', command=self._toggle_recording).pack(anchor='w')
        ttk.Button(cont, text='保存快照', command=self.save_snapshot).pack(anchor='w', pady=4)

        # 设置 卡
        cont = _add_card('settings', '设置 (快捷)')
        ttk.Button(cont, text='打开设置页', command=lambda: self._navigate('settings')).pack(anchor='w')

    def _show_right_card(self, key: str | None):
        if not hasattr(self, '_right_cards'):
            return
        for k, cf in self._right_cards.items():
            try:
                # 展开所选，收起其他
                want_open = (key == k)
                is_open = bool(cf._content_container.winfo_ismapped())
                if want_open and not is_open:
                    cf._toggle()
                elif (not want_open) and is_open:
                    cf._toggle()
            except Exception:
                pass

    # 图像处理页逻辑已迁移到 ProcessingPanelMixin

    # 设置页逻辑已迁移到 SettingsPanelMixin

    def _show_lang_dialog(self):
        win = tk.Toplevel(self.show); win.title('切换语言'); win.transient(self.show); win.grab_set()
        langs = ["ch","en","chinese_cht","japan","korean"]
        var = tk.StringVar(value=self.ocr_lang.get())
        for lg in langs:
            ttk.Radiobutton(win, text=lg, value=lg, variable=var).pack(anchor='w', padx=8, pady=2)
        def _apply():
            new_l = var.get()
            if new_l != self.ocr_lang.get():
                self.ocr_lang.set(new_l); self.release_ocr_engine(); self._sb_lang.config(text=f'Lang: {new_l}')
            win.destroy()
        ttk.Button(win, text='应用', command=_apply).pack(pady=6)

    def _adaptive_toolbar(self, _e=None):
        try:
            avail = self._toolbar_frame.winfo_width()
            total = sum(w.winfo_reqwidth() for w in self._core_buttons) + 80
            # 阈值压缩: 如果空间不足, 使用短文本
            compact = avail < total
            for btn in self._core_buttons:
                txt = btn.cget('text')
                if compact and len(txt) > 2:
                    if not hasattr(btn, '_orig_text'): btn._orig_text = txt
                    btn.config(text=txt[:2])
                elif (not compact) and hasattr(btn, '_orig_text'):
                    btn.config(text=btn._orig_text)
        except Exception:
            pass

    # ----------------- OCR 状态更新 -----------------
    def _update_ocr_status(self, status: str):
        try:
            self.ocr_status_var.set(status)
            color_map = {"未加载":"#888","加载中":"#d89000","就绪":"#0a960a","识别中":"#0077cc","缺依赖":"#cc0000","已释放":"#555"}
            if hasattr(self, 'ocr_status_label'):
                self.ocr_status_label.config(foreground=color_map.get(status,'#333'))
            if hasattr(self, '_sb_state'):
                self._sb_state.config(text=f'状态: {status}')
        except Exception:
            pass

    # ----------------- Preview update loop -----------------
    def _update_preview(self):
        if not self.last_pil: return
        display = self.last_pil.copy()
        display = self._apply_processing(display)
        display = self._add_grid_and_ruler(display)
        w, h = display.size
        thumb = display.resize((int(w*self.scale), int(h*self.scale)), Image.LANCZOS)
        self.tkimg = ImageTk.PhotoImage(thumb)
        self.lab.config(image=self.tkimg)

    def _show_color_info(self, event):
        if not self.last_pil: return
        try:
            x = int(event.x / self.scale)
            y = int(event.y / self.scale)
            if 0 <= x < self.last_pil.width and 0 <= y < self.last_pil.height:
                rgb = self.last_pil.getpixel((x,y))
                hex_c = f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"
                self.color_info.config(text=f"坐标: ({x},{y})  RGB: {rgb}  HEX: {hex_c}")
        except Exception:
            pass

    def _calc_next_delay_ms(self):
        try:
            w = max(1, self.box[2]-self.box[0])
            h = max(1, self.box[3]-self.box[1])
            area = w * h
            # 基准: 1280x720 ~ 921600 设为 50ms (20fps)
            base_area = 1280*720
            ratio = area / base_area
            # 处理器越多适度增大延迟
            proc_penalty = 1 + 0.15 * len(self.active_processors)
            # 缩放本身不影响截取, 但放大后用户主观需求帧率可稍降
            scale_penalty = 1 + max(0, (self.scale - 1) * 0.1)
            delay = 50 * ratio ** 0.4 * proc_penalty * scale_penalty
            # 约束范围 35ms ~ 180ms
            delay = max(35, min(180, delay))
            return int(delay)
        except Exception:
            return 50

    def loop(self):
        try:
            with mss.mss() as sct:
                img = sct.grab(tuple(self.box))
            self.last_pil = Image.frombytes("RGB", img.size, img.bgra, "raw", "BGRX")
            self._update_preview()
            if self.record_mode: self._save_recording()
        except Exception as e:
            logger.warning("捕获错误: %s", e)
        delay = self._calc_next_delay_ms()
        if self._show_delay_var.get():
            if hasattr(self, '_sb_delay'): self._sb_delay.config(text=f'延迟: {delay}ms (~{int(1000/max(delay,1)) if delay>0 else 0}fps)')
        else:
            if hasattr(self, '_sb_delay'): self._sb_delay.config(text='延迟: -')
        if hasattr(self, '_sb_size'):
            w = self.box[2]-self.box[0]; h = self.box[3]-self.box[1]
            self._sb_size.config(text=f'区域: {w}x{h}')
        self.after_id = self.show.after(delay, self.loop)

    # ----------------- Lifecycle -----------------
    def close(self):
        if hasattr(self, 'after_id') and self.after_id:
            try: self.show.after_cancel(self.after_id)
            except Exception: pass
        if self.cap: self.cap.destroy()
        # 销毁悬浮按钮
        try:
            if getattr(self, '_float_btn_win', None):
                self._float_btn_win.destroy()
                try:
                    CapturePreviewDuoEnhanced._GLOBAL_FLOAT_BTN_WIN = None
                except Exception:
                    pass
        except Exception:
            pass
        if self.show: self.show.destroy()
        self.last_pil = None

    # ----------------- Config persistence -----------------
    def export_config(self):
        """导出当前可持久化状态供主程序写入 JSON。"""
        try:
            proc_cfg = {}
            for k, info in self.processors.items():
                proc_cfg[k] = {
                    'enabled': info.get('enabled', False),
                    'params': info.get('params', {}).copy()
                }
            # 视图状态
            try:
                panes = self._main_paned.panes() if hasattr(self, '_main_paned') else []
                ocr_visible = hasattr(self, '_ocr_panel_container') and self._ocr_panel_container and str(self._ocr_panel_container) in panes
            except Exception:
                ocr_visible = False
            state = getattr(self, 'ocr_state', None)
            if state:
                if hasattr(self, '_conf_threshold'):
                    try:
                        state.conf_threshold = float(self._conf_threshold.get())
                    except Exception:
                        pass
                state.panel_visible = bool(ocr_visible)
                state.preview_visible = bool(getattr(self, '_preview_visible', True))
            ui_state = {
                'ocr_panel_visible': bool(state.panel_visible if state else ocr_visible),
                'ocr_preview_visible': bool(state.preview_visible if state else getattr(self, '_preview_visible', True)),
                'ai_sidebar_visible': bool(not getattr(self, '_chat_sidebar_hidden', True)),
                'main_window_geometry': self.show.geometry() if hasattr(self, 'show') else '',
                'active_page': getattr(self, '_active_page', 'preview'),
                'drawer_collapsed': bool(getattr(self, '_drawer_collapsed', False)),
                'show_visible': bool(getattr(self, '_show_visible', True)),
            }
            # 悬浮按钮状态
            try:
                if getattr(self, '_float_btn_win', None) and self._float_btn_win.winfo_exists():
                    ui_state['float_btn_visible'] = bool(self._float_btn_visible_var.get() if hasattr(self, '_float_btn_visible_var') else True)
                    ui_state['float_btn_geometry'] = self._float_btn_win.geometry()
            except Exception:
                pass
            # 处理页 sash（位于处理控件与图像预览之间）
            try:
                if hasattr(self, '_proc_ctrl_container') and self._proc_ctrl_container and hasattr(self, '_main_paned'):
                    panes = self._main_paned.panes()
                    proc_name = str(self._proc_ctrl_container)
                    if proc_name in panes:
                        sash_idx = panes.index(proc_name)
                        ui_state['proc_sash'] = int(self._main_paned.sashpos(sash_idx))
            except Exception:
                pass
            # sash 位置（仅当 OCR 面板存在时记录第一个分隔条）
            try:
                if ocr_visible and hasattr(self, '_main_paned'):
                    ui_state['sash0'] = int(self._main_paned.sashpos(0))
            except Exception:
                pass
            return {
                'box': self.box[:],
                'scale': self.scale,
                'ocr': {
                    'use_processed': self.ocr_use_processed,
                    'max_side': self.ocr_max_side,
                    'lang': self.ocr_lang.get(),
                    'conf_threshold': (state.conf_threshold if state else (float(self._conf_threshold.get()) if hasattr(self, '_conf_threshold') else 0.0))
                },
                'ai': {
                    'model_text': getattr(self, '_ai_model_text', 'glm-4'),
                    'model_vision': getattr(self, '_ai_model_vision', 'glm-4.5v')
                },
                'processors': proc_cfg,
                'ui': ui_state
            }
        except Exception:
            return {}

    def import_config(self, cfg: dict):
        """从 JSON 恢复状态（在窗口与变量创建后调用）。"""
        try:
            if not isinstance(cfg, dict): return
            if 'box' in cfg and isinstance(cfg['box'], (list, tuple)) and len(cfg['box'])==4:
                self.box = list(cfg['box']); self._apply_geometry(); self._update_layout()
            # processors
            for k, meta in cfg.get('processors', {}).items():
                if k in self.processors:
                    self.processors[k]['enabled'] = bool(meta.get('enabled', False))
                    if self.processors[k]['enabled'] and k not in self.active_processors:
                        self.active_processors.append(k)
                    for pk, pv in meta.get('params', {}).items():
                        if pk in self.processors[k]['params']:
                            self.processors[k]['params'][pk] = pv
            ocr_cfg = cfg.get('ocr', {})
            if 'use_processed' in ocr_cfg:
                self.ocr_use_processed = bool(ocr_cfg['use_processed'])
            if 'max_side' in ocr_cfg:
                try: self.ocr_max_side = int(ocr_cfg['max_side'])
                except Exception: pass
            if 'lang' in ocr_cfg and ocr_cfg['lang']:
                if ocr_cfg['lang'] != self.ocr_lang.get():
                    self.ocr_lang.set(ocr_cfg['lang'])
            if 'conf_threshold' in ocr_cfg:
                # 可能 OCR 窗口尚未打开, 先保存到占位变量
                self._initial_conf_threshold = float(ocr_cfg['conf_threshold'])
                if hasattr(self, 'ocr_state'):
                    self.ocr_state.conf_threshold = float(ocr_cfg['conf_threshold'])
            # 同步工具栏来源标签
            if hasattr(self, 'ocr_source_var'):
                self.ocr_source_var.set('后' if self.ocr_use_processed else '原')

            # AI 模型（可选配置）
            ai_cfg = cfg.get('ai', {})
            if isinstance(ai_cfg, dict):
                mt = ai_cfg.get('model_text')
                mv = ai_cfg.get('model_vision')
                if mt:
                    self._ai_model_text = str(mt)
                if mv:
                    self._ai_model_vision = str(mv)
                # 若 ai_client 存在，更新模型字段
                try:
                    if getattr(self, 'ai_client', None):
                        if mt: self.ai_client.model_text = self._ai_model_text
                        if mv: self.ai_client.model_vision = self._ai_model_vision
                        # 刷新可用性 UI
                        self._update_ai_availability_ui()
                except Exception:
                    pass

            # UI 状态恢复
            ui = cfg.get('ui', {})
            if isinstance(ui, dict):
                try:
                    geo = ui.get('main_window_geometry')
                    if geo:
                        try: self.show.geometry(geo)
                        except Exception: pass
                except Exception:
                    pass
                # AI 侧栏
                try:
                    if ui.get('ai_sidebar_visible', False):
                        self.show_ai_sidebar()
                    else:
                        self.hide_ai_sidebar()
                except Exception:
                    pass
                # OCR 面板与预览
                try:
                    want_ocr = ui.get('ocr_panel_visible', False)
                    if want_ocr:
                        self.show_ocr_panel(focus_text=False)
                        if hasattr(self, 'ocr_state'):
                            self.ocr_state.panel_visible = True
                    else:
                        # 若未创建则保持隐藏意图
                        if hasattr(self, '_ocr_panel_visible'):
                            self._ocr_panel_visible.set(False)
                        if hasattr(self, 'ocr_state'):
                            self.ocr_state.panel_visible = False
                    # 预览可见性：若面板尚未创建，则延迟应用
                    if 'ocr_preview_visible' in ui:
                        flag = bool(ui.get('ocr_preview_visible', True))
                        if hasattr(self, '_ocr_paned') and hasattr(self, '_ocr_preview_frame'):
                            self._set_ocr_preview_visible(flag)
                        else:
                            self._pending_ocr_preview_visible = flag
                        if hasattr(self, 'ocr_state'):
                            self.ocr_state.preview_visible = flag
                            if not (hasattr(self, '_ocr_paned') and hasattr(self, '_ocr_preview_frame')):
                                self.ocr_state.pending_preview_visible = flag
                except Exception:
                    pass
                # 抽屉折叠与活动页面（延迟到窗口构建后应用）
                try:
                    if 'drawer_collapsed' in ui:
                        self._pending_drawer_collapsed = bool(ui['drawer_collapsed'])
                    if 'active_page' in ui and ui['active_page']:
                        self._pending_active_page = ui['active_page']
                    if 'proc_sash' in ui:
                        self._pending_proc_sash = int(ui['proc_sash'])
                    if 'show_visible' in ui:
                        self._pending_show_visible = bool(ui['show_visible'])
                    if 'float_btn_visible' in ui:
                        self._pending_float_btn_visible = bool(ui['float_btn_visible'])
                    if 'float_btn_geometry' in ui and ui['float_btn_geometry']:
                        self._pending_float_btn_geometry = ui['float_btn_geometry']
                except Exception:
                    pass
                # 分割条位置（延迟，待布局完成）
                try:
                    if 'sash0' in ui:
                        pos = int(ui['sash0'])
                        def _apply_sash():
                            try:
                                if hasattr(self, '_main_paned'):
                                    self._main_paned.sashpos(0, pos)
                            except Exception:
                                pass
                        self.show.after(200, _apply_sash)
                except Exception:
                    pass
        except Exception:
            pass

    # ----------------- OCR 结果窗口 -----------------
    def _open_ocr_text_window(self):
        # 显示 OCR 面板（若已隐藏则恢复），并聚焦文本
        self.show_ocr_panel(focus_text=True)

    # 视图：AI 侧栏显示/隐藏
    def show_ai_sidebar(self):
        try:
            self._ensure_chat_sidebar()
            if getattr(self, '_chat_sidebar_hidden', False):
                self._chat_sidebar_frame.pack(side=tk.RIGHT, fill=tk.Y, padx=2, pady=2)
                self._chat_sidebar_hidden = False
            if hasattr(self, '_ai_sidebar_visible'):
                self._ai_sidebar_visible.set(True)
            self._schedule_config_changed()
        except Exception:
            pass

    def hide_ai_sidebar(self):
        try:
            if hasattr(self, '_chat_sidebar_frame') and self._chat_sidebar_frame:
                self._chat_sidebar_frame.forget()
                self._chat_sidebar_hidden = True
            if hasattr(self, '_ai_sidebar_visible'):
                self._ai_sidebar_visible.set(False)
            self._schedule_config_changed()
        except Exception:
            pass

    def _toggle_ai_sidebar_visibility(self):
        try:
            if self._ai_sidebar_visible.get():
                self.show_ai_sidebar()
            else:
                self.hide_ai_sidebar()
        except Exception:
            pass

    def _toggle_ai_sidebar_visibility_kb(self):
        try:
            cur = False
            if hasattr(self, '_ai_sidebar_visible'):
                cur = bool(self._ai_sidebar_visible.get())
                self._ai_sidebar_visible.set(not cur)
            if cur:
                self.hide_ai_sidebar()
            else:
                self.show_ai_sidebar()
        except Exception:
            pass


    def _schedule_config_changed(self):
        try:
            if not hasattr(self, 'on_config_changed') or not callable(getattr(self, 'on_config_changed')):
                return
            if hasattr(self, '_cfg_timer') and self._cfg_timer:
                self.show.after_cancel(self._cfg_timer)
            self._cfg_timer = self.show.after(800, lambda: self.on_config_changed())
        except Exception:
            pass

    def open_processing_panel(self):
        if self.processing_panel and tk.Toplevel.winfo_exists(self.processing_panel):
            self.processing_panel.lift(); return
        win = self.processing_panel = tk.Toplevel(self.show)
        win.title('处理器')
        win.geometry('280x360+40+40')
        frm = ttk.Frame(win); frm.pack(fill=tk.BOTH, expand=True, padx=6, pady=6)
        for key, info in self.processors.items():
            var = tk.BooleanVar(value=info['enabled'])
            def _mk_cb(k=key, v=var):
                def _toggle():
                    self.processors[k]['enabled'] = v.get()
                    if v.get() and k not in self.active_processors:
                        self.active_processors.append(k)
                    elif (not v.get()) and k in self.active_processors:
                        self.active_processors.remove(k)
                    self._update_preview()
                return _toggle
            cb = ttk.Checkbutton(frm, text=info['name'], variable=var, command=_mk_cb())
            cb.pack(anchor='w')
            if key == 'edges':
                thr_var = tk.IntVar(value=info['params']['threshold'])
                def _update_thr(_ev=None, k=key, v=thr_var):
                    self.processors[k]['params']['threshold'] = v.get()
                    self._update_preview()
                ttk.Scale(frm, from_=10, to=250, orient='horizontal', variable=thr_var, command=lambda _e: _update_thr()).pack(fill=tk.X, padx=12, pady=(0,4))
        ttk.Separator(frm).pack(fill=tk.X, pady=6)
        ttk.Label(frm, text='OCR 来源:').pack(anchor='w')
        src_var = tk.StringVar(value='processed' if self.ocr_use_processed else 'raw')
        def _set_src():
            self.ocr_use_processed = (src_var.get() == 'processed')
            self.ocr_source_var.set('后' if self.ocr_use_processed else '原')
        for val, text in [('raw','原始图像'), ('processed','处理后图像')]:
            ttk.Radiobutton(frm, text=text, value=val, variable=src_var, command=_set_src).pack(anchor='w', padx=8)
        ttk.Button(frm, text='关闭', command=win.destroy).pack(pady=8)

    def _add_grid_and_ruler(self, img):
        if not (self.grid_visible or self.ruler_visible):
            return img
        draw = ImageDraw.Draw(img)
        w, h = img.size
        if self.grid_visible:
            step = GRID_LINE_STEP
            for x in range(0, w, step):
                draw.line([(x,0),(x,h)], fill=(60,60,60))
            for y in range(0, h, step):
                draw.line([(0,y),(w,y)], fill=(60,60,60))
        if self.ruler_visible:
            # top ruler
            for x in range(0, w, RULER_STEP):
                draw.line([(x,0),(x,10)], fill=(255,0,0))
            for y in range(0, h, RULER_STEP):
                draw.line([(0,y),(10,y)], fill=(0,255,0))
        return img

    def _toggle_grid(self):
        self.grid_visible = self._grid_var.get(); self._update_preview()
    def _toggle_ruler(self):
        self.ruler_visible = self.ruler_var.get(); self._update_preview()
    def _toggle_aspect_ratio(self):
        self.aspect_ratio_lock = self._aspect_var.get()
        if self.aspect_ratio_lock:
            w = self.box[2]-self.box[0]; h = self.box[3]-self.box[1]
            if h>0: self.aspect_ratio = w/h
    def on_wheel(self, event):
        if event.delta > 0: self.scale = min(4.0, self.scale*1.1)
        else: self.scale = max(0.25, self.scale/1.1)
        self._update_preview()

    def _toggle_recording(self):
        self.record_mode = not self.record_mode
        if self.record_mode:
            ts = datetime.now().strftime('%Y%m%d_%H%M%S')
            self.record_path = os.path.join(os.getcwd(), f'rec_{ts}')
            os.makedirs(self.record_path, exist_ok=True)
            self.last_record_time = 0
            if hasattr(self, 'record_btn'): self.record_btn.config(text='停止')
            logger.info('开始录制到 %s', self.record_path)
        else:
            if hasattr(self, 'record_btn'): self.record_btn.config(text='录制')
            logger.info('停止录制')

    def _save_recording(self):
        if not (self.record_mode and self.last_pil): return
        now = time.time()
        if now - self.last_record_time < self.record_interval: return
        self.last_record_time = now
        fname = datetime.now().strftime('%H%M%S_%f') + '.png'
        try:
            self.last_pil.save(os.path.join(self.record_path, fname))
        except Exception as e:
            logger.warning('保存录制帧失败: %s', e)

    def save_snapshot(self, _e=None):
        if not self.last_pil: return
        ts = datetime.now().strftime('%Y%m%d_%H%M%S')
        path = filedialog.asksaveasfilename(defaultextension='.png', initialfile=f'shot_{ts}.png')
        if not path: return
        try:
            self.last_pil.save(path)
            logger.info('快照保存: %s', path)
        except Exception as e:
            messagebox.showerror('保存失败', str(e))

    def _warmup_ocr_async(self):
        if self.ocr_manager is None:
            return
        if self.ocr_status_var.get() not in ('未加载','已释放'):
            return
        def _load():
            self._update_ocr_status('加载中')
            try:
                self.ocr_manager.load(); self._update_ocr_status('就绪')
            except Exception as e:
                logger.warning('OCR 预热失败: %s', e); self._update_ocr_status('缺依赖')
        threading.Thread(target=_load, daemon=True).start()

    def release_ocr_engine(self):
        if self.ocr_manager:
            try:
                self.ocr_manager.release()
                self._update_ocr_status('已释放')
            except Exception as e:
                logger.warning('释放OCR失败: %s', e)

    def perform_ocr(self):
        if not self.last_pil:
            messagebox.showinfo('提示','当前无画面'); return
        if self.ocr_manager is None:
            messagebox.showwarning('OCR','OCR 模块初始化失败'); return
        if self.ocr_status_var.get() in ('未加载','已释放'):
            self._warmup_ocr_async()
        if self.ocr_status_var.get() != '就绪':
            messagebox.showinfo('OCR','OCR 引擎未就绪'); return
        if self.ocr_in_progress:
            return
        self.ocr_in_progress = True
        self._update_ocr_status('识别中')
        base_img = self.last_pil.copy()
        use_img = self._apply_processing(base_img.copy()) if self.ocr_use_processed else base_img.copy()
        max_side = self.ocr_max_side
        def _run():
            try:
                # 缓存原始/处理后图像供缩略显示
                self.last_ocr_raw_img = base_img
                self.last_ocr_processed_img = use_img if self.ocr_use_processed else None
                meta, lines = self.ocr_manager.perform(use_img, use_processed=self.ocr_use_processed, max_side=max_side)
                # 统一存储结构
                self.last_ocr_result = {'meta': meta, 'results': lines}
                self._update_status_bar('OCR', f"完成 {len(lines)} 行")
                try:
                    from .event_bus import get_global_bus
                    get_global_bus().emit('ocr_finished', {
                        'meta': meta,
                        'lines': lines,
                        'count': len(lines)
                    })
                except Exception:
                    pass
                # 保存完整行列表供置信度过滤
                self._all_ocr_lines = lines
                self._open_ocr_text_window()
                text_lines = [ln.get('text','') for ln in lines if ln.get('text')]
                if hasattr(self, '_ocr_text_widget'):
                    self._ocr_text_widget.delete('1.0', tk.END)
                    self._ocr_text_widget.insert('1.0', '\n'.join(text_lines))
                    # 应用当前阈值过滤（若阈值>0 会立即重新过滤）
                    try: self._apply_conf_filter()
                    except Exception: pass
                self._update_ocr_preview_thumb()
            except Exception as e:
                logger.error('OCR 失败: %s', e)
            finally:
                self.ocr_in_progress = False
                if self.ocr_manager and self.ocr_manager.is_loaded:
                    self._update_ocr_status('就绪')
                else:
                    self._update_ocr_status('未加载')
                self._update_status_bar('OCR', self.ocr_status_var.get())
        threading.Thread(target=_run, daemon=True).start()

    def _on_lab_context_menu(self, event=None):
        try:
            m = tk.Menu(self.show, tearoff=0)
            m.add_command(label='保存当前截图', command=self.save_snapshot)
            x = int(event.x_root) if event and hasattr(event, 'x_root') else self.show.winfo_rootx()+50
            y = int(event.y_root) if event and hasattr(event, 'y_root') else self.show.winfo_rooty()+50
            m.post(x, y)
        except Exception:
            pass

    def _perform_ocr_from_file(self):
        try:
            path = filedialog.askopenfilename(title='选择图片进行识别', filetypes=[('Image','*.png;*.jpg;*.jpeg;*.bmp;*.webp'),('All','*.*')])
            if not path:
                return
            img = Image.open(path).convert('RGB')
            # 直接以文件图像为输入，不走当前捕获区域
            if self.ocr_manager is None:
                messagebox.showwarning('OCR','OCR 模块初始化失败'); return
            if self.ocr_status_var.get() in ('未加载','已释放'):
                self._warmup_ocr_async()
            if self.ocr_status_var.get() != '就绪':
                messagebox.showinfo('OCR','OCR 引擎未就绪'); return
            # 启动后台识别
            def _run_file():
                try:
                    self._update_ocr_status('识别中')
                    meta, lines = self.ocr_manager.perform(img, use_processed=False, max_side=self.ocr_max_side)
                    self.last_ocr_result = {'meta': meta, 'results': lines}
                    self._update_status_bar('OCR', f"完成 {len(lines)} 行")
                    self._open_ocr_text_window()
                    text_lines = [ln.get('text','') for ln in lines if ln.get('text')]
                    if hasattr(self, '_ocr_text_widget'):
                        self._ocr_text_widget.delete('1.0', tk.END)
                        self._ocr_text_widget.insert('1.0', '\n'.join(text_lines))
                        try: self._apply_conf_filter()
                        except Exception: pass
                except Exception as e:
                    logger.error('文件 OCR 失败: %s', e)
                finally:
                    if self.ocr_manager and self.ocr_manager.is_loaded:
                        self._update_ocr_status('就绪')
                    else:
                        self._update_ocr_status('未加载')
                    self._update_status_bar('OCR', self.ocr_status_var.get())
            threading.Thread(target=_run_file, daemon=True).start()
        except Exception:
            pass

    def _ocr_from_file_via_panel(self):
        """在 OCR 工作台中触发：
        - 选择图片
        - 将所选图片显示到 OCR 预览（作为“原”图）
        - 调用 OCR 引擎识别并把结果写入文本页
        """
        try:
            path = filedialog.askopenfilename(title='选择图片进行识别', filetypes=[('Image','*.png;*.jpg;*.jpeg;*.bmp;*.webp'),('All','*.*')])
            if not path:
                return
            img = Image.open(path).convert('RGB')
            # 确保 OCR 面板可见
            try:
                self.show_ocr_panel(focus_text=False)
            except Exception:
                pass
            # 将该图片作为最近一次 OCR 的原始图，刷新左侧预览
            self.last_ocr_raw_img = img
            self.last_ocr_processed_img = None
            try:
                self._update_ocr_preview_thumb()
            except Exception:
                pass
            # 运行 OCR
            if self.ocr_manager is None:
                messagebox.showwarning('OCR','OCR 模块初始化失败'); return
            if self.ocr_status_var.get() in ('未加载','已释放'):
                self._warmup_ocr_async()
            if self.ocr_status_var.get() != '就绪':
                messagebox.showinfo('OCR','OCR 引擎未就绪'); return
            def _run_file():
                try:
                    self._update_ocr_status('识别中')
                    meta, lines = self.ocr_manager.perform(img, use_processed=False, max_side=self.ocr_max_side)
                    self.last_ocr_result = {'meta': meta, 'results': lines}
                    self._update_status_bar('OCR', f"完成 {len(lines)} 行")
                    self._open_ocr_text_window()
                    text_lines = [ln.get('text','') for ln in lines if ln.get('text')]
                    if hasattr(self, '_ocr_text_widget'):
                        self._ocr_text_widget.delete('1.0', tk.END)
                        self._ocr_text_widget.insert('1.0', '\n'.join(text_lines))
                        try: self._apply_conf_filter()
                        except Exception: pass
                    try:
                        self._refresh_ocr_meta(); self._update_ocr_preview_thumb()
                    except Exception:
                        pass
                except Exception as e:
                    logger.error('文件 OCR 失败: %s', e)
                finally:
                    if self.ocr_manager and self.ocr_manager.is_loaded:
                        self._update_ocr_status('就绪')
                    else:
                        self._update_ocr_status('未加载')
                    self._update_status_bar('OCR', self.ocr_status_var.get())
            threading.Thread(target=_run_file, daemon=True).start()
        except Exception:
            pass

    def _on_close_ocr_text_window(self):
        try:
            if self.ocr_text_window: self.ocr_text_window.destroy()
        finally:
            self.ocr_text_window = None

    def _apply_preset_size(self, _e=None):
        name = self.preset_var.get()
        for item in PRESET_SIZES:
            # 兼容两种结构: (label, (w,h)) 或 (label, w, h)
            try:
                label, w, h = item  # type: ignore[misc]
            except Exception:
                try:
                    label, wh = item
                    w, h = (wh if isinstance(wh, (list, tuple)) and len(wh) == 2 else (None, None))
                except Exception:
                    label, w, h = (None, None, None)
            if not label or w is None or h is None:
                continue
            if label == name:
                # 锁中心缩放
                cx = (self.box[0] + self.box[2]) // 2
                cy = (self.box[1] + self.box[3]) // 2
                try:
                    w = int(w); h = int(h)
                except Exception:
                    break
                if w <= 0 or h <= 0:
                    break
                self.box[0] = cx - w // 2
                self.box[2] = self.box[0] + w
                self.box[1] = cy - h // 2
                self.box[3] = self.box[1] + h
                self._apply_geometry(); self._update_layout()
                if self.aspect_ratio_lock:
                    self.aspect_ratio = w / h if h else self.aspect_ratio
                break

__all__ = ["CapturePreviewDuoEnhanced"]
