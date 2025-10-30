"""Mouse position & color monitor main window.
Extracted from original window_capture.py.
"""
from __future__ import annotations
import threading, time, json
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox

import pyautogui, mss
import pyperclip

from .constants import FPS_MOVE, FPS_STILL, MOVE_TH, MAX_HISTORY
from .capture import CapturePreviewDuoEnhanced
from .logging_utils import get_logger

logger = get_logger()

class MousePositionMonitor:
    def __init__(self):
        self.root = tk.Tk()
        self.setup_variables()
        self.load_config()
        self.setup_window()
        self.setup_widgets()
        self.bind_keys()
        self.monitor_thread = threading.Thread(target=self.monitor, daemon=True)
        self.monitor_thread.start()

    # ----------------- Setup -----------------
    def setup_variables(self):
        self.running = threading.Event(); self.running.set()
        self.pos_lock = threading.Lock()
        self.last_pos = (-999, -999)
        self.last_move_time = time.time()
        self.current_fps = FPS_MOVE
        self.saved_pos = None
        self.position_history = []
        self.coord_fmt = tk.StringVar(value="Python")
        self.relative_mode = tk.BooleanVar(value=False)
        self.relative_base = None
        self.capture_duo = None

    def setup_window(self):
        self.root.title("鼠标坐标 & 像素监控 v4")
        self.root.geometry("430x500")
        self.root.attributes("-topmost", True)
        self.root.resizable(False, False)

    def setup_widgets(self):
        self.lab_pos = tk.Label(self.root, text="X: 0 , Y: 0", font=("Consolas", 14)); self.lab_pos.pack(pady=6)
        color_frame = ttk.LabelFrame(self.root, text="颜色信息"); color_frame.pack(pady=4, padx=10, fill="x")
        self.lab_color = tk.Label(color_frame, text="RGB: (0, 0, 0)  #000000", font=("Consolas", 12)); self.lab_color.pack(pady=6)
        self.color_canvas = tk.Canvas(color_frame, width=60, height=30, bd=1, relief="solid"); self.color_canvas.pack(pady=4)
        self.lab_error = tk.Label(self.root, text="", fg="red", font=("Consolas", 10)); self.lab_error.pack(pady=2)
        mode_frame = ttk.LabelFrame(self.root, text="坐标模式"); mode_frame.pack(pady=4, padx=10, fill="x")
        ttk.Checkbutton(mode_frame, text="相对坐标模式（F8）", variable=self.relative_mode, command=self.toggle_relative_mode).pack(side=tk.LEFT, padx=5)
        self.lab_relative = tk.Label(mode_frame, text="基准点: 未设置", font=("Consolas", 10)); self.lab_relative.pack(side=tk.LEFT, padx=5)
        fmt_frame = ttk.LabelFrame(self.root, text="坐标格式"); fmt_frame.pack(pady=4, padx=10, fill="x")
        for txt in ["Python (x, y)", "JavaScript {x,y}", "CSS xpx ypx"]:
            ttk.Radiobutton(fmt_frame, text=txt, variable=self.coord_fmt, value=txt.split()[0]).pack(side=tk.LEFT, padx=5)
        history_frame = ttk.LabelFrame(self.root, text="历史记录"); history_frame.pack(pady=4, padx=10, fill="x")
        self.history_listbox = tk.Listbox(history_frame, height=3, font=("Consolas", 10))
        self.history_listbox.pack(side=tk.LEFT, fill="x", expand=True, padx=5, pady=5)
        self.history_listbox.bind('<Double-Button-1>', self.copy_from_history)
        btn_frame = ttk.Frame(self.root); btn_frame.pack(pady=4)
        self.btn_save = tk.Button(btn_frame, text="记录坐标 (F9)", command=self.save_pos, width=20); self.btn_save.pack(pady=2)
        self.btn_copy = tk.Button(btn_frame, text="复制记录 (F10)", command=self.copy_saved, width=20); self.btn_copy.pack(pady=2)
        cap_frame = ttk.Frame(self.root); cap_frame.pack(pady=4)
        self.btn_cap_open = tk.Button(cap_frame, text="开启捕获 (F5)", command=self.open_capture, width=20); self.btn_cap_open.pack(side=tk.LEFT, padx=2)
        self.btn_cap_close = tk.Button(cap_frame, text="关闭捕获 (F6)", command=self.close_capture, width=20); self.btn_cap_close.pack(side=tk.LEFT, padx=2)

    def bind_keys(self):
        self.root.bind("<F9>", lambda e: self.save_pos())
        self.root.bind("<F10>", lambda e: self.copy_saved())
        self.root.bind("<F8>", lambda e: self.set_relative_base())
        self.root.bind("<F5>", lambda e: self.open_capture())
        self.root.bind("<F6>", lambda e: self.close_capture())
        self.root.bind("<Escape>", lambda e: self.root.destroy())
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    # ----------------- Capture integration -----------------
    def open_capture(self):
        if not self.capture_duo:
            self.capture_duo = CapturePreviewDuoEnhanced()
            # 注册配置变更回调用于持久化
            try:
                self.capture_duo.on_config_changed = lambda: self.save_config()
            except Exception:
                pass
            # 如果有待导入配置
            try:
                if hasattr(self, '_pending_capture_cfg') and self._pending_capture_cfg:
                    self.capture_duo.import_config(self._pending_capture_cfg)
            except Exception as e:
                logger.warning('导入 capture 配置失败: %s', e)
            self.show_message("捕获窗口已开启")

    def close_capture(self):
        if self.capture_duo:
            try:
                self.capture_duo.close(); self.capture_duo = None
            except Exception as e:
                logger.warning('关闭捕获出错: %s', e)
            self.show_message("捕获窗口已关闭")

    # ----------------- Config -----------------
    def get_config_path(self):
        config_dir = Path.home() / ".mouse_position_monitor"; config_dir.mkdir(exist_ok=True)
        return config_dir / "config.json"

    def save_config(self):
        cfg = {
            'format': self.coord_fmt.get(),
            'window_geometry': self.root.geometry(),
            'relative_mode': self.relative_mode.get(),
            'relative_base': self.relative_base,
        }
        # 捕获窗口附加配置
        try:
            if self.capture_duo:
                cfg['capture'] = self.capture_duo.export_config()
        except Exception as e:
            logger.warning('导出 capture 配置失败: %s', e)
        try:
            with open(self.get_config_path(), 'w', encoding='utf-8') as f:
                json.dump(cfg, f, ensure_ascii=False, indent=2)
        except Exception as e:
            self.show_error(f"保存配置失败: {e}")
            logger.exception('保存配置失败')

    def load_config(self):
        try:
            p = self.get_config_path()
            if p.exists():
                with open(p, 'r', encoding='utf-8') as f:
                    cfg = json.load(f)
                self.coord_fmt.set(cfg.get('format', 'Python'))
                self.relative_mode.set(cfg.get('relative_mode', False))
                self.relative_base = cfg.get('relative_base', None)
                if 'window_geometry' in cfg:
                    self.root.geometry(cfg['window_geometry'])
                self._pending_capture_cfg = cfg.get('capture')  # 稍后在创建 capture_duo 后导入
        except Exception as e:
            self.show_error(f"加载配置失败: {e}")
            logger.exception('加载配置失败')

    # ----------------- Monitor loop -----------------
    def monitor(self):
        while self.running.is_set():
            try:
                x, y = pyautogui.position()
                with self.pos_lock:
                    dx, dy = x - self.last_pos[0], y - self.last_pos[1]
                    self.current_fps = self.adaptive_fps(dx, dy)
                    self.last_pos = (x, y)
                rgb = self.get_color_at(x, y)
                hex_color = f"#{rgb[0]:02x}{rgb[1]:02x}{rgb[2]:02x}"
                self.root.after(0, lambda x=x, y=y, rgb=rgb, hx=hex_color: self.update_gui(x, y, rgb, hx))
                time.sleep(1 / self.current_fps)
            except Exception as e:
                self.show_error(f"监控错误: {e}")
                time.sleep(1)

    def get_color_at(self, x, y):
        try:
            with mss.mss() as sct:
                pixel = sct.grab({"left": x, "top": y, "width": 1, "height": 1})
                return pixel.pixel(0, 0)[:3]
        except Exception:
            return (0, 0, 0)

    def adaptive_fps(self, dx, dy):
        if dx * dx + dy * dy > MOVE_TH * MOVE_TH:
            self.last_move_time = time.time(); return FPS_MOVE
        return FPS_MOVE if time.time() - self.last_move_time < 0.5 else FPS_STILL

    # ----------------- UI update helpers -----------------
    def update_gui(self, x, y, rgb, hex_color):
        try:
            rx, ry = self.get_relative_coords(x, y)
            if self.relative_mode.get():
                pos_text = f"X: {rx:4} , Y: {ry:4} (相对)"
            else:
                pos_text = f"X: {x:4} , Y: {y:4}"
            self.lab_pos.config(text=pos_text)
            self.lab_color.config(text=f"RGB: {rgb}  {hex_color}")
            self.color_canvas.config(bg=hex_color)
        except Exception as e:
            self.show_error(f"更新界面失败: {e}")

    def get_relative_coords(self, x, y):
        if not self.relative_mode.get() or self.relative_base is None:
            return x, y
        bx, by = self.relative_base
        return x - bx, y - by

    def toggle_relative_mode(self):
        if self.relative_mode.get() and self.relative_base is None:
            self.set_relative_base()
        elif not self.relative_mode.get():
            self.lab_relative.config(text="基准点: 未设置"); self.relative_base = None

    def set_relative_base(self):
        self.relative_base = pyautogui.position(); self.lab_relative.config(text=f"基准点: ({self.relative_base[0]}, {self.relative_base[1]})"); self.relative_mode.set(True)

    def format_coordinates(self, x, y):
        if self.relative_mode.get(): x, y = self.get_relative_coords(x, y)
        fmt = self.coord_fmt.get()
        if fmt == "Python": return f"{x}, {y}"
        if fmt == "JavaScript": return f"{{ x: {x}, y: {y} }}"
        return f"{x}px {y}px"

    # ----------------- Actions -----------------
    def save_pos(self):
        try:
            self.saved_pos = pyautogui.position()
            coords = self.format_coordinates(*self.saved_pos)
            self.position_history.insert(0, self.saved_pos)
            if len(self.position_history) > MAX_HISTORY: self.position_history.pop()
            self.history_listbox.delete(0, tk.END)
            for pos in self.position_history:
                self.history_listbox.insert(tk.END, self.format_coordinates(*pos))
            self.btn_save.config(text="已记录!")
            self.root.after(800, lambda: self.btn_save.config(text="记录坐标 (F9)"))
        except Exception as e:
            self.show_error(f"保存位置失败: {e}")

    def copy_saved(self):
        if not self.saved_pos:
            self.show_error("请先记录坐标位置"); return
        try:
            text = self.format_coordinates(*self.saved_pos)
            pyperclip.copy(text)
            self.btn_copy.config(text="已复制!")
            self.root.after(800, lambda: self.btn_copy.config(text="复制记录 (F10)"))
        except Exception as e:
            self.show_error(f"复制坐标失败: {e}")

    def copy_from_history(self, _e):
        try:
            sel = self.history_listbox.curselection()
            if sel:
                idx = sel[0]; pos = self.position_history[idx]
                pyperclip.copy(self.format_coordinates(*pos))
                self.show_message("已复制历史坐标")
        except Exception as e:
            self.show_error(f"复制历史记录失败: {e}")

    # ----------------- Messaging -----------------
    def show_error(self, msg):
        self.lab_error.config(text=msg, fg="red")
        self.root.after(2000, lambda: self.lab_error.config(text=""))

    def show_message(self, msg):
        self.lab_error.config(text=msg, fg="green")
        self.root.after(2000, lambda: self.lab_error.config(text="", fg="red"))

    # ----------------- Lifecycle -----------------
    def on_close(self):
        self.close_capture(); self.save_config(); self.running.clear()
        if self.monitor_thread.is_alive(): self.monitor_thread.join(timeout=1.0)
        self.root.destroy()

    def run(self):
        try:
            self.root.mainloop()
        except Exception as e:
            messagebox.showerror("错误", f"程序运行错误: {e}")

__all__ = ["MousePositionMonitor"]
