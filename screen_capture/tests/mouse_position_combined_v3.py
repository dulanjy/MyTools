import tkinter as tk
from tkinter import ttk, messagebox
import threading
import functools
import time
import pyperclip
import ctypes
import mss
import math
import pyautogui
import json
import os
from pathlib import Path

# -------------------- 常量定义 --------------------
GRID = 10          # 10×10 网格
MOVE_TH = 5        # 像素移动阈值，低于该值认为"静止"
FPS_MOVE = 20      # 移动时帧率
FPS_STILL = 2      # 静止时帧率
MAX_HISTORY = 10   # 最大历史记录数

# -------------------- DPI 感知（仅 Windows） --------------------
if hasattr(ctypes.windll.user32, 'SetProcessDPIAware'):
    ctypes.windll.user32.SetProcessDPIAware()

class MousePositionMonitor:
    def __init__(self):
        self.root = tk.Tk()
        self.setup_variables()
        self.load_config()  # 加载配置
        self.setup_window()
        self.setup_widgets()
        self.bind_keys()

        # 启动监控线程
        self.monitor_thread = threading.Thread(target=self.monitor, daemon=True)
        self.monitor_thread.start()

    def setup_variables(self):
        """初始化变量"""
        self.running = threading.Event()
        self.running.set()
        self.pos_lock = threading.Lock()  # 添加线程锁
        
        # 缓存和状态变量
        self.cache = {}
        self.last_pos = (-999, -999)
        self.last_move_time = time.time()
        self.current_fps = FPS_MOVE
        
        # 坐标相关
        self.saved_pos = None
        self.position_history = []  # 历史记录
        self.coord_fmt = tk.StringVar(value="Python")
        self.relative_mode = tk.BooleanVar(value=False)
        self.relative_base = None

    def setup_window(self):
        """设置窗口属性"""
        self.root.title("鼠标坐标 & 像素监控 v3")
        self.root.geometry("320x400")  # 增加高度以适应新控件
        self.root.attributes("-topmost", True)
        self.root.resizable(False, False)

    def setup_widgets(self):
        """创建界面元素"""
        # 当前坐标显示
        self.lab_pos = tk.Label(self.root, text="X: 0 , Y: 0", font=("Consolas", 14))
        self.lab_pos.pack(pady=6)

        # 颜色信息
        color_frame = ttk.LabelFrame(self.root, text="颜色信息")
        color_frame.pack(pady=4, padx=10, fill="x")
        
        self.lab_color = tk.Label(color_frame, text="RGB: (0, 0, 0)  #000000", font=("Consolas", 12))
        self.lab_color.pack(pady=6)
        
        self.color_canvas = tk.Canvas(color_frame, width=60, height=30, bd=1, relief="solid")
        self.color_canvas.pack(pady=4)

        # 错误信息显示
        self.lab_error = tk.Label(self.root, text="", fg="red", font=("Consolas", 10))
        self.lab_error.pack(pady=2)

        # 坐标模式选择
        mode_frame = ttk.LabelFrame(self.root, text="坐标模式")
        mode_frame.pack(pady=4, padx=10, fill="x")
        
        ttk.Checkbutton(mode_frame, text="相对坐标模式", 
                       variable=self.relative_mode,
                       command=self.toggle_relative_mode).pack(side=tk.LEFT, padx=5)
        
        self.lab_relative = tk.Label(mode_frame, text="基准点: 未设置", font=("Consolas", 10))
        self.lab_relative.pack(side=tk.LEFT, padx=5)

        # 坐标格式选择
        fmt_frame = ttk.LabelFrame(self.root, text="坐标格式")
        fmt_frame.pack(pady=4, padx=10, fill="x")
        
        formats = ["Python (x, y)", "JavaScript {x,y}", "CSS xpx ypx"]
        for txt in formats:
            ttk.Radiobutton(fmt_frame, text=txt, variable=self.coord_fmt,
                          value=txt.split()[0]).pack(side=tk.LEFT, padx=5)

        # 历史记录
        history_frame = ttk.LabelFrame(self.root, text="历史记录")
        history_frame.pack(pady=4, padx=10, fill="x")
        
        self.history_listbox = tk.Listbox(history_frame, height=3, font=("Consolas", 10))
        self.history_listbox.pack(side=tk.LEFT, fill="x", expand=True, padx=5, pady=5)
        self.history_listbox.bind('<Double-Button-1>', self.copy_from_history)

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
        """绑定快捷键"""
        self.root.bind("<F9>", lambda e: self.save_pos())
        self.root.bind("<F10>", lambda e: self.copy_saved())
        self.root.bind("<F8>", lambda e: self.set_relative_base())  # 新增：设置相对坐标基准点
        self.root.bind("<Escape>", lambda e: self.root.destroy())
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    # -------------------- 配置管理 --------------------
    def get_config_path(self):
        """获取配置文件路径"""
        config_dir = Path.home() / ".mouse_position_monitor"
        config_dir.mkdir(exist_ok=True)
        return config_dir / "config.json"

    def save_config(self):
        """保存配置"""
        config = {
            'format': self.coord_fmt.get(),
            'window_geometry': self.root.geometry(),
            'relative_mode': self.relative_mode.get(),
            'relative_base': self.relative_base
        }
        try:
            with open(self.get_config_path(), 'w') as f:
                json.dump(config, f)
        except Exception as e:
            self.show_error(f"保存配置失败: {str(e)}")

    def load_config(self):
        """加载配置"""
        try:
            if self.get_config_path().exists():
                with open(self.get_config_path(), 'r') as f:
                    config = json.load(f)
                    self.coord_fmt.set(config.get('format', 'Python'))
                    self.relative_mode.set(config.get('relative_mode', False))
                    self.relative_base = config.get('relative_base', None)
                    if 'window_geometry' in config:
                        self.root.geometry(config['window_geometry'])
        except Exception as e:
            self.show_error(f"加载配置失败: {str(e)}")

    # -------------------- 核心功能 --------------------
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
            except Exception as e:
                self.show_error(f"获取颜色失败: {str(e)}")
                rgb = (0, 0, 0)
        self.cache[g] = (rgb, now)
        return rgb

    def adaptive_fps(self, dx, dy):
        """根据移动距离动态调整帧率"""
        if dx * dx + dy * dy > MOVE_TH * MOVE_TH:
            self.last_move_time = time.time()
            return FPS_MOVE
        return FPS_MOVE if time.time() - self.last_move_time < 0.5 else FPS_STILL

    # -------------------- 坐标处理 --------------------
    def get_relative_coords(self, x, y):
        """获取相对坐标"""
        if not self.relative_mode.get() or self.relative_base is None:
            return x, y
        base_x, base_y = self.relative_base
        return x - base_x, y - base_y

    def toggle_relative_mode(self):
        """切换相对坐标模式"""
        if self.relative_mode.get() and self.relative_base is None:
            # 如果开启相对模式但没有基准点，自动设置当前位置为基准点
            self.set_relative_base()
        elif not self.relative_mode.get():
            # 如果关闭相对模式，清除基准点显示
            self.lab_relative.config(text="基准点: 未设置")
            self.relative_base = None

    def set_relative_base(self):
        """设置相对坐标基准点"""
        self.relative_base = pyautogui.position()
        self.lab_relative.config(text=f"基准点: ({self.relative_base[0]}, {self.relative_base[1]})")
        self.relative_mode.set(True)

    def format_coordinates(self, x, y):
        """格式化坐标"""
        if self.relative_mode.get():
            x, y = self.get_relative_coords(x, y)
        
        fmt = self.coord_fmt.get()
        if fmt == "Python":
            return f"{x}, {y}"
        elif fmt == "JavaScript":
            return f"{{ x: {x}, y: {y} }}"
        else:  # CSS
            return f"{x}px {y}px"

    # -------------------- 监控和更新 --------------------
    def monitor(self):
        """监控鼠标位置和颜色"""
        while self.running.is_set():
            try:
                x, y = pyautogui.position()
                with self.pos_lock:
                    dx, dy = x - self.last_pos[0], y - self.last_pos[1]
                    self.current_fps = self.adaptive_fps(dx, dy)
                    self.last_pos = (x, y)

                rgb = self.color_at(x, y)
                hex_color = "#%02x%02x%02x" % rgb
                
                # 使用 after 确保在主线程中更新 GUI
                self.root.after(0, lambda: self.update_gui(x, y, rgb, hex_color))
                
                time.sleep(1 / self.current_fps)
            except Exception as e:
                self.show_error(f"监控错误: {str(e)}")
                time.sleep(1)

    def update_gui(self, x, y, rgb, hex_color):
        """更新界面显示"""
        try:
            rel_x, rel_y = self.get_relative_coords(x, y)
            if self.relative_mode.get():
                pos_text = f"X: {rel_x:4} , Y: {rel_y:4} (相对)"
            else:
                pos_text = f"X: {x:4} , Y: {y:4}"
                
            self.lab_pos.config(text=pos_text)
            self.lab_color.config(text=f"RGB: {rgb}  {hex_color}")
            self.color_canvas.config(bg=hex_color)
        except Exception as e:
            self.show_error(f"更新界面失败: {str(e)}")

    # -------------------- 坐标记录和复制 --------------------
    def save_pos(self):
        """保存当前位置"""
        try:
            self.saved_pos = pyautogui.position()
            coords = self.format_coordinates(self.saved_pos[0], self.saved_pos[1])
            
            # 更新历史记录
            self.position_history.insert(0, self.saved_pos)
            if len(self.position_history) > MAX_HISTORY:
                self.position_history.pop()
            
            # 更新历史列表显示
            self.history_listbox.delete(0, tk.END)
            for pos in self.position_history:
                self.history_listbox.insert(tk.END, self.format_coordinates(*pos))
            
            self.btn_save.config(text="已记录!")
            self.root.after(800, lambda: self.btn_save.config(text="记录坐标 (F9)"))
        except Exception as e:
            self.show_error(f"保存位置失败: {str(e)}")

    def copy_saved(self):
        """复制已保存的坐标"""
        if not self.saved_pos:
            self.show_error("请先记录坐标位置")
            return
        try:
            text = self.format_coordinates(self.saved_pos[0], self.saved_pos[1])
            pyperclip.copy(text)
            self.btn_copy.config(text="已复制!")
            self.root.after(800, lambda: self.btn_copy.config(text="复制记录 (F10)"))
        except Exception as e:
            self.show_error(f"复制坐标失败: {str(e)}")

    def copy_from_history(self, event):
        """从历史记录中复制坐标"""
        try:
            selection = self.history_listbox.curselection()
            if selection:
                index = selection[0]
                pos = self.position_history[index]
                text = self.format_coordinates(pos[0], pos[1])
                pyperclip.copy(text)
                self.show_message("已复制历史坐标")
        except Exception as e:
            self.show_error(f"复制历史记录失败: {str(e)}")

    # -------------------- 错误处理和消息显示 --------------------
    def show_error(self, message):
        """显示错误信息"""
        self.lab_error.config(text=message)
        self.root.after(2000, lambda: self.lab_error.config(text=""))

    def show_message(self, message):
        """显示普通信息"""
        self.lab_error.config(text=message, fg="green")
        self.root.after(2000, lambda: self.lab_error.config(text="", fg="red"))

    # -------------------- 程序退出处理 --------------------
    def on_close(self):
        """清理资源并关闭程序"""
        try:
            self.save_config()  # 保存配置
            self.running.clear()
            if self.monitor_thread.is_alive():
                self.monitor_thread.join(timeout=1.0)
            self.root.destroy()
        except Exception as e:
            messagebox.showerror("错误", f"关闭程序时出错: {str(e)}")
            self.root.destroy()

    def run(self):
        """启动程序"""
        try:
            self.root.mainloop()
        except Exception as e:
            messagebox.showerror("错误", f"程序运行错误: {str(e)}")

if __name__ == "__main__":
    app = MousePositionMonitor()
    app.run()