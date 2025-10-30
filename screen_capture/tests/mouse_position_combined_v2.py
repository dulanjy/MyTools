# mouse_position_combined_v2.py
import tkinter as tk
from tkinter import ttk
import threading
import functools
import time
import pyperclip
import ctypes
import mss
import math
import pyautogui

# -------------------- DPI 感知（仅 Windows） --------------------
if hasattr(ctypes.windll.user32, 'SetProcessDPIAware'):
    ctypes.windll.user32.SetProcessDPIAware()

GRID = 10          # 10×10 网格
MOVE_TH = 5        # 像素移动阈值，低于该值认为“静止”
FPS_MOVE = 20      # 移动时帧率
FPS_STILL = 2      # 静止时帧率

class MousePositionMonitor:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("鼠标坐标 & 像素监控  v2")
        self.root.geometry("320x300")
        self.root.attributes("-topmost", True)
        self.root.resizable(False, False)

        self.running = threading.Event()
        self.running.set()

        # 缓存：key=(grid_x, grid_y), value=(rgb, timestamp)
        self.cache = {}
        self.last_pos = (-999, -999)
        self.last_move_time = time.time()
        self.current_fps = FPS_MOVE

        self.setup_widgets()
        self.bind_keys()

        self.monitor_thread = threading.Thread(target=self.monitor, daemon=True)
        self.monitor_thread.start()

    # ---------- GUI 初始化（与原文件相同，略） ----------
    def setup_widgets(self):
        self.lab_pos = tk.Label(self.root, text="X: 0 , Y: 0", font=("Consolas", 14))
        self.lab_pos.pack(pady=6)
        self.lab_color = tk.Label(self.root, text="RGB: (0, 0, 0)  #000000", font=("Consolas", 12))
        self.lab_color.pack(pady=6)
        self.color_canvas = tk.Canvas(self.root, width=60, height=30, bd=1, relief="solid")
        self.color_canvas.pack(pady=4)

        self.saved_pos = None
        self.coord_fmt = tk.StringVar(value="Python")

        fmt_frame = ttk.LabelFrame(self.root, text="坐标格式")
        fmt_frame.pack(pady=4, padx=10, fill="x")
        for txt in ["Python (x, y)", "JavaScript {x,y}", "CSS xpx ypx"]:
            ttk.Radiobutton(fmt_frame, text=txt, variable=self.coord_fmt,
                          value=txt.split()[0]).pack(side=tk.LEFT, padx=5)

        # 按钮框架
        btn_frame = ttk.Frame(self.root)
        btn_frame.pack(pady=4)

        self.btn_save = tk.Button(btn_frame, text="记录坐标 (F9)",
                                command=self.save_pos, width=20)
        self.btn_save.pack(pady=2)

        self.btn_copy = tk.Button(btn_frame, text="复制记录 (F10)",
                                command=self.copy_saved, width=20)
        self.btn_copy.pack(pady=2)
        
    def bind_keys(self):
        self.root.bind("<F9>", lambda e: self.save_pos())
        self.root.bind("<F10>", lambda e: self.copy_saved())
        self.root.bind("<Escape>", lambda e: self.root.destroy())
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    # -------------------- 核心：区域哈希 + 自适应帧率 --------------------
    def grid_key(self, x, y):
        """10×10 网格 key"""
        return (int(x) // GRID, int(y) // GRID)

    def color_at(self, x, y):
        """带缓存的取色（mss）"""
        g = self.grid_key(x, y)
        now = time.time()
        if g in self.cache and now - self.cache[g][1] < 1.0:   # 缓存 1 s
            return self.cache[g][0]
        with mss.mss() as sct:
            try:
                pix = sct.grab({"left": x, "top": y, "width": 1, "height": 1}).pixel(0, 0)
                rgb = pix[:3]          # mss 返回 BGRA，取前 3
            except Exception:
                rgb = (0, 0, 0)
        self.cache[g] = (rgb, now)
        return rgb

    def adaptive_fps(self, dx, dy):
        """根据移动距离动态调整帧率"""
        if dx * dx + dy * dy > MOVE_TH * MOVE_TH:
            self.last_move_time = time.time()
            return FPS_MOVE
        return FPS_MOVE if time.time() - self.last_move_time < 0.5 else FPS_STILL

    # -------------------- 后台监控 --------------------
    def monitor(self):
        while self.running.is_set():
            x, y = pyautogui.position()
            dx, dy = x - self.last_pos[0], y - self.last_pos[1]
            self.current_fps = self.adaptive_fps(dx, dy)

            rgb = self.color_at(x, y)
            hex_color = "#%02x%02x%02x" % rgb
            self.root.after(0, lambda: self.update_gui(x, y, rgb, hex_color))
            self.last_pos = (x, y)

            time.sleep(1 / self.current_fps)

    def update_gui(self, x, y, rgb, hex_color):
        self.lab_pos.config(text=f"X: {x:4} , Y: {y:4}")
        self.lab_color.config(text=f"RGB: {rgb}  {hex_color}")
        self.color_canvas.config(bg=hex_color)

    # -------------------- 其余功能 --------------------
    def save_pos(self):
        self.saved_pos = pyautogui.position()
        self.lab_pos.config(text=f"已记录 X: {self.saved_pos[0]} Y: {self.saved_pos[1]}")
        self.btn_save.config(text="已记录!")
        self.root.after(800, lambda: self.btn_save.config(text="记录坐标 (F9)"))
        
    def copy_saved(self):
        if not self.saved_pos:
            return
        fmt = self.coord_fmt.get()
        x, y = self.saved_pos
        if fmt == "Python":
            text = f"{x}, {y}"
        elif fmt == "JavaScript":
            text = f"{{ x: {x}, y: {y} }}"
        else:  # CSS
            text = f"{x}px {y}px"
        pyperclip.copy(text)

    def on_close(self):
        self.running.clear()
        self.root.destroy()

    # -------------------- 启动 --------------------
    def run(self):
        self.root.mainloop()


if __name__ == "__main__":
    app = MousePositionMonitor()
    app.run()