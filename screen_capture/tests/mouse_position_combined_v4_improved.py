# mouse_position_combined_v4_improved.py
import tkinter as tk
from tkinter import ttk, messagebox, filedialog
import threading, time, json, os, ctypes, functools
from pathlib import Path
import pyautogui, pyperclip, mss
from PIL import Image, ImageTk, ImageDraw
import numpy as np
from datetime import datetime


# -------------------- 常量定义 --------------------
GRID = 10
MOVE_TH = 5
FPS_MOVE = 20
FPS_STILL = 2
MAX_HISTORY = 10
PRESET_SIZES = [
    ("HD (1280×720)", (1280, 720)),
    ("Full HD (1920×1080)", (1920, 1080)),
    ("4K (3840×2160)", (3840, 2160)),
    ("Square (800×800)", (800, 800))
]

if hasattr(ctypes.windll.user32, 'SetProcessDPIAware'):
    ctypes.windll.user32.SetProcessDPIAware()

# =============================================================================
# 捕获-显示双窗口增强版
# =============================================================================
class CapturePreviewDuoEnhanced:
    def __init__(self, init_box=(200, 200, 600, 500)):
        self.box = list(init_box)
        self.drag_mode = None
        self.grip_size = 8
        self.aspect_ratio_lock = False
        self.grid_visible = False
        self.ruler_visible = True
        self.record_mode = False
        self.record_interval = 1.0  # 录制间隔（秒）
        self.record_path = None
        self.is_dragging = False  # 新增：跟踪拖拽状态
        self._build_capture_win()
        self._build_show_win()
        self.loop()
        
    def on_wheel(self, event):
        """处理鼠标滚轮事件来调整缩放"""
        if not hasattr(self, 'image') or not self.image:
            return
            
        # 获取当前缩放
        current_scale = self.scale
        
        # 根据滚轮方向调整缩放
        if event.delta > 0:
            self.scale *= 1.1  # 放大
        else:
            self.scale /= 1.1  # 缩小
            
        # 限制最小和最大缩放
        self.scale = max(0.1, min(5.0, self.scale))
        
        # 如果缩放未改变，直接返回
        if abs(current_scale - self.scale) < 0.001:
            return
            
        # 重新显示图像
        self._update_preview()
        
    def save_snapshot(self, event=None):
        """保存当前截图"""
        if not hasattr(self, 'image') or not self.image:
            messagebox.showwarning("提示", "没有可保存的截图！")
            return
            
        # 生成默认文件名
        default_name = f"screenshot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
        
        # 选择保存路径
        filepath = filedialog.asksaveasfilename(
            defaultextension=".png",
            initialfile=default_name,
            filetypes=[
                ("PNG图片", "*.png"),
                ("JPEG图片", "*.jpg;*.jpeg"),
                ("所有文件", "*.*")
            ]
        )
        
        if filepath:
            try:
                # 保存图片
                self.image.save(filepath)
                messagebox.showinfo("成功", f"截图已保存至：\n{filepath}")
            except Exception as e:
                messagebox.showerror("错误", f"保存失败：{str(e)}")
                
    def close(self):
        """关闭所有窗口并清理资源"""
        # 停止录制（如果在录制中）
        if hasattr(self, 'recording') and self.recording:
            self.recording = False
            if hasattr(self, 'record_thread') and self.record_thread.is_alive():
                self.record_thread.join()
                
        # 重置拖拽状态
        self.drag_mode = None
        if hasattr(self, 'drag_thread') and self.drag_thread.is_alive():
            self.drag_thread.join()
            
        # 关闭窗口
        if hasattr(self, 'cap') and self.cap:
            self.cap.destroy()
        if hasattr(self, 'show') and self.show:
            self.show.destroy()
            
        # 清理资源
        if hasattr(self, 'image'):
            del self.image

    def _apply_geometry(self):
        """应用窗口几何尺寸"""
        # 计算窗口尺寸
        w = self.box[2] - self.box[0]
        h = self.box[3] - self.box[1]
        
        # 限制最小尺寸
        if w < 100: w = 100
        if h < 100: h = 100
        
        # 确保窗口在屏幕内
        screen_width, screen_height = pyautogui.size()
        x = max(0, min(self.box[0], screen_width - w))
        y = max(0, min(self.box[1], screen_height - h))
        
        # 更新box以反映实际位置
        self.box[0] = x
        self.box[1] = y
        self.box[2] = x + w
        self.box[3] = y + h
        
        # 设置窗口位置和大小
        geometry = f"{w}x{h}+{x}+{y}"
        self.cap.geometry(geometry)

    def __init__(self, init_box=(200, 200, 600, 500)):
        self.box = list(init_box)
        self.drag_mode = None
        self.start_x = 0
        self.start_y = 0
        self.start_box = None
        self.grip_size = 8
        self.aspect_ratio_lock = False
        self.grid_visible = False
        self.ruler_visible = True
        self.record_mode = False
        self.record_interval = 1.0  # 录制间隔（秒）
        self.record_path = None
        self._build_capture_win()
        self._build_show_win()
        self.loop()
        
    def start_drag(self, corner_idx):
        """开始拖动调整大小"""
        self.drag_mode = corner_idx  # 0,1,2,3 分别代表左上、右上、左下、右下
        self.start_pos = pyautogui.position()
        self.start_box = self.box.copy()
        self._drag_loop()

    def _on_title_press(self, event):
        """处理标题栏按下事件"""
        self.drag_mode = 4  # 特殊模式：移动整个窗口
        self.start_pos = pyautogui.position()
        self.start_box = self.box.copy()
        self._drag_loop()

    def _on_drag_stop(self, event):
        """处理所有拖拽结束事件"""
        self.drag_mode = None
        self.start_pos = None
        self.start_box = None

    def _update_layout(self):
        """更新窗口布局"""
        w = self.box[2] - self.box[0]
        h = self.box[3] - self.box[1]
        
        # 更新边框位置
        self.border_top.place(x=0, y=0, width=w)
        self.border_bottom.place(x=0, y=h-2, width=w)
        self.border_left.place(x=0, y=0, height=h)
        self.border_right.place(x=w-2, y=0, height=h)
        
        # 更新标题栏位置
        self.title_bar.place(x=2, y=2, width=w-4)
        
        # 更新四角拖动点位置
        corners = [
            (0, 0),                    # 左上
            (w - self.grip_size, 0),   # 右上
            (0, h - self.grip_size),   # 左下
            (w - self.grip_size, h - self.grip_size)  # 右下
        ]
        
        for grip, (x, y) in zip(self.grips, corners):
            grip.place(x=x, y=y)
    
    def _drag_loop(self):
        """处理拖拽的主循环"""
        if self.drag_mode is None:
            return

        pos = pyautogui.position()
        dx = pos[0] - self.start_pos[0]
        dy = pos[1] - self.start_pos[1]

        if self.drag_mode == 4:  # 移动整个窗口
            self.box[0] = self.start_box[0] + dx
            self.box[1] = self.start_box[1] + dy
            self.box[2] = self.start_box[2] + dx
            self.box[3] = self.start_box[3] + dy
        else:  # 调整大小
            if self.drag_mode in [0, 2]:  # 左侧
                self.box[0] = min(self.start_box[0] + dx, self.start_box[2] - 100)
            if self.drag_mode in [1, 3]:  # 右侧
                self.box[2] = max(self.start_box[2] + dx, self.start_box[0] + 100)
            if self.drag_mode in [0, 1]:  # 上方
                self.box[1] = min(self.start_box[1] + dy, self.start_box[3] - 100)
            if self.drag_mode in [2, 3]:  # 下方
                self.box[3] = max(self.start_box[3] + dy, self.start_box[1] + 100)

        # 应用几何变化并更新布局
        self._apply_geometry()
        self._update_layout()

        if self.drag_mode is not None:
            self.cap.after(16, self._drag_loop)  # 约60FPS的更新频率

    def _build_capture_win(self):
        """构建捕获窗口"""
        self.cap = tk.Toplevel()
        self.cap.overrideredirect(True)
        self.cap.attributes("-topmost", True)
        self.cap.attributes("-transparentcolor", "magenta")
        self.cap.config(bg="magenta")
        
        # 初始化拖拽相关的属性
        self.drag_mode = None
        self.start_pos = None
        self.start_box = None
        self.grip_size = 8
        
        # 添加边框
        bw = 2  # 边框宽度
        self.border_top = tk.Frame(self.cap, bg="red", height=bw)
        self.border_bottom = tk.Frame(self.cap, bg="red", height=bw)
        self.border_left = tk.Frame(self.cap, bg="red", width=bw)
        self.border_right = tk.Frame(self.cap, bg="red", width=bw)
        
        # 标题栏（20像素高，用于拖动）
        self.title_h = 20
        self.title_bar = tk.Frame(self.cap, bg="grey20", height=self.title_h)
        self.title_bar.bind("<Button-1>", self._on_title_press)
        self.title_bar.bind("<ButtonRelease-1>", self._on_drag_stop)
        
        # 四角拖动点（8×8像素）
        self.grips = []
        colors = ["white", "green", "blue", "yellow"]  # 不同颜色区分四角
        
        def create_grip_handler(index):
            """创建拖动点事件处理器"""
            def on_press(event):
                self.start_drag(index)
            return on_press
            
        for i in range(4):
            grip = tk.Frame(self.cap, bg=colors[i], width=self.grip_size, height=self.grip_size)
            grip.bind("<Button-1>", create_grip_handler(i))
            grip.bind("<ButtonRelease-1>", self._on_drag_stop)
            self.grips.append(grip)
            
        # 应用初始布局
        self._update_layout()
        
        # 添加快捷键绑定
        self.cap.bind("<Shift-Left>", lambda e: self._adjust_size(-1, 0))
        self.cap.bind("<Shift-Right>", lambda e: self._adjust_size(1, 0))
        self.cap.bind("<Shift-Up>", lambda e: self._adjust_size(0, -1))
        self.cap.bind("<Shift-Down>", lambda e: self._adjust_size(0, 1))
        # 添加尺寸信息显示
        self.size_label = tk.Label(self.cap, 
                                 text="", 
                                 bg="black", 
                                 fg="white",
                                 font=("Consolas", 10))
        
        # 应用初始布局
        self._apply_geometry()
        self._update_layout()
        self._update_size_label()

        # 添加快捷键绑定
        self.cap.bind("<Shift-Left>", lambda e: self._adjust_size(-1, 0))
        self.cap.bind("<Shift-Right>", lambda e: self._adjust_size(1, 0))
        self.cap.bind("<Shift-Up>", lambda e: self._adjust_size(0, -1))
        self.cap.bind("<Shift-Down>", lambda e: self._adjust_size(0, 1))

    def _update_size_label(self):
        """更新尺寸显示"""
        w = self.box[2] - self.box[0]
        h = self.box[3] - self.box[1]
        self.size_label.config(text=f" {w}×{h} ")
        self.size_label.place(x=2, y=22)  # 放在标题栏下方

        # 尺寸标签
        self.size_label = tk.Label(self.cap, text="", bg="black", fg="white", 
                                 font=("Consolas", 10))
        self._update_size_label()

    def _update_size_label(self):
        """更新尺寸显示"""
        w = self.box[2] - self.box[0]
        h = self.box[3] - self.box[1]
        self.size_label.config(text=f" {w}×{h} ")
        self.size_label.place(x=2, y=22)  # 放在标题栏下方

    def _build_show_win(self):
        self.show = tk.Toplevel()
        self.show.title("增强显示窗口")
        self.show.attributes("-topmost", True)

        # 工具栏
        toolbar = ttk.Frame(self.show)
        toolbar.pack(fill=tk.X, padx=5, pady=2)

        # 预设尺寸下拉菜单
        ttk.Label(toolbar, text="预设:").pack(side=tk.LEFT, padx=2)
        self.preset_var = tk.StringVar()
        preset_cb = ttk.Combobox(toolbar, 
                                textvariable=self.preset_var, 
                                values=[size[0] for size in PRESET_SIZES],
                                width=15)
        preset_cb.pack(side=tk.LEFT, padx=2)
        preset_cb.bind('<<ComboboxSelected>>', self._apply_preset_size)

        self.ruler_var = tk.BooleanVar(value=self.ruler_visible) 
        # 控制按钮
        ttk.Checkbutton(toolbar, text="锁定比例", 
                       command=self._toggle_aspect_ratio).pack(side=tk.LEFT, padx=2)
        ttk.Checkbutton(toolbar, text="显示网格", 
                       command=self._toggle_grid).pack(side=tk.LEFT, padx=2)
        ttk.Checkbutton(toolbar, text="显示标尺", 
                       variable=self.ruler_var,
                       command=self._toggle_ruler).pack(side=tk.LEFT, padx=2)

        # 录制控制
        self.record_btn = ttk.Button(toolbar, text="开始录制", 
                                   command=self._toggle_recording)
        self.record_btn.pack(side=tk.LEFT, padx=2)

        # 显示区域
        self.lab = tk.Label(self.show, bg="black")
        self.lab.pack(fill=tk.BOTH, expand=True)
        
        # 绑定事件
        self.show.bind("<MouseWheel>", self.on_wheel)
        self.lab.bind("<Button-3>", self.save_snapshot)
        self.lab.bind("<Motion>", self._show_color_info)
        self.scale = 1.0

        # 颜色信息显示
        self.color_info = tk.Label(self.show, text="", 
                                 font=("Consolas", 10))
        self.color_info.pack(fill=tk.X, padx=5)

    def _show_color_info(self, event):
        """显示鼠标下方像素的颜色信息"""
        if hasattr(self, 'last_pil'):
            try:
                # 计算实际图像中的坐标
                x = int(event.x / self.scale)
                y = int(event.y / self.scale)
                if 0 <= x < self.last_pil.width and 0 <= y < self.last_pil.height:
                    rgb = self.last_pil.getpixel((x, y))
                    hex_color = "#{:02x}{:02x}{:02x}".format(*rgb)
                    self.color_info.config(
                        text=f"坐标: ({x}, {y})  RGB: {rgb}  HEX: {hex_color}")
            except Exception:
                pass

    def _toggle_recording(self):
        """切换录制状态"""
        if not self.record_mode:
            self.record_path = filedialog.askdirectory(title="选择保存目录")
            if self.record_path:
                self.record_mode = True
                self.record_btn.config(text="停止录制")
                self.last_record_time = 0
        else:
            self.record_mode = False
            self.record_btn.config(text="开始录制")
            messagebox.showinfo("提示", "录制已停止")

    def _save_recording(self):
        """保存录制的图像"""
        if self.record_mode and hasattr(self, 'last_pil'):
            current_time = time.time()
            if current_time - self.last_record_time >= self.record_interval:
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S_%f")
                filename = os.path.join(self.record_path, f"capture_{timestamp}.png")
                self.last_pil.save(filename)
                self.last_record_time = current_time

    def _toggle_aspect_ratio(self):
        """切换宽高比锁定"""
        self.aspect_ratio_lock = not self.aspect_ratio_lock
        if self.aspect_ratio_lock:
            # 记录当前比例
            w = self.box[2] - self.box[0]
            h = self.box[3] - self.box[1]
            self.aspect_ratio = w / h

    def _toggle_grid(self):
        """切换网格显示"""
        self.grid_visible = not self.grid_visible

    def _toggle_ruler(self):
        self.ruler_visible = self.ruler_var.get()   # 直接取变量值

    def start_move(self):
        """开始移动窗口"""
        self.drag_mode = 4  # 特殊模式：移动整个窗口
        self._drag_loop()

    def start_drag(self, corner_idx):
        """开始拖动调整大小"""
        self.drag_mode = corner_idx  # 0,1,2,3 分别代表左上、右上、左下、右下
        self._drag_loop()

    def stop_drag(self):
        """停止拖动"""
        self.drag_mode = None

    def _drag_loop(self):
        """拖动循环"""
        if self.drag_mode is None:
            return

        x, y = pyautogui.position()
        if self.drag_mode == 4:  # 移动整个窗口
            sw, sh = pyautogui.size()  # 屏幕尺寸
            w = self.box[2] - self.box[0]
            h = self.box[3] - self.box[1]
            
            # 确保窗口不会移出屏幕
            new_x = max(0, min(x - w//2, sw - w))
            new_y = max(0, min(y - 10, sh - h))
            
            self.box[0] = new_x
            self.box[1] = new_y
            self.box[2] = new_x + w
            self.box[3] = new_y + h
            
        else:  # 调整大小
            if self.drag_mode == 0:     # 左上
                self.box[0], self.box[1] = x, y
            elif self.drag_mode == 1:   # 右上
                self.box[2], self.box[1] = x, y
            elif self.drag_mode == 2:   # 左下
                self.box[0], self.box[3] = x, y
            elif self.drag_mode == 3:   # 右下
                self.box[2], self.box[3] = x, y

            # 限制最小尺寸
            self.box[2] = max(self.box[2], self.box[0] + 100)
            self.box[3] = max(self.box[3], self.box[1] + 100)

            # 保持宽高比（如果启用）
            if self.aspect_ratio_lock:
                self._maintain_aspect_ratio()

        # 应用新的位置和大小
        self._apply_geometry()
        self._update_layout()
        
        if self.drag_mode is not None:
            self.cap.after(10, self._drag_loop)

    def _apply_preset_size(self, event=None):
        """应用预设尺寸"""
        selected = self.preset_var.get()
        for name, (w, h) in PRESET_SIZES:
            if name == selected:
                # 保持左上角位置不变，调整右下角
                self.box[2] = self.box[0] + w
                self.box[3] = self.box[1] + h
                self._apply_geometry()
                self._update_layout()
                break

    def _adjust_size(self, dx, dy):
        """使用方向键微调大小"""
        if dx:
            self.box[2] += dx
        if dy:
            self.box[3] += dy
        self._apply_geometry()
        self._update_layout()

    def _maintain_aspect_ratio(self):
        """保持宽高比"""
        if self.aspect_ratio_lock:
            w = self.box[2] - self.box[0]
            h = self.box[3] - self.box[1]
            current_ratio = w / h
            if current_ratio > self.aspect_ratio:
                # 调整宽度
                new_w = int(h * self.aspect_ratio)
                if self.drag_mode in [1, 3]:  # 右边拖动
                    self.box[2] = self.box[0] + new_w
                else:  # 左边拖动
                    self.box[0] = self.box[2] - new_w
            else:
                # 调整高度
                new_h = int(w / self.aspect_ratio)
                if self.drag_mode in [2, 3]:  # 下边拖动
                    self.box[3] = self.box[1] + new_h
                else:  # 上边拖动
                    self.box[1] = self.box[3] - new_h

    def _add_grid_and_ruler(self, img):
        """添加网格和标尺"""
        draw = ImageDraw.Draw(img)
        w, h = img.size

        if self.grid_visible:
            # 绘制网格线
            for x in range(0, w, 50):
                draw.line([(x, 0), (x, h)], fill=(128, 128, 128, 128))
            for y in range(0, h, 50):
                draw.line([(0, y), (w, y)], fill=(128, 128, 128, 128))

        if self.ruler_visible:
            # 绘制标尺
            for x in range(0, w, 100):
                draw.text((x, 0), str(x), fill=(255, 255, 255))
            for y in range(0, h, 100):
                draw.text((0, y), str(y), fill=(255, 255, 255))

        return img

    def loop(self):
        """主循环：捕获和显示"""
        try:
            with mss.mss() as sct:
                img = sct.grab(tuple(self.box))
            
            # 转换为PIL图像
            self.last_pil = Image.frombytes("RGB", img.size, img.bgra, "raw", "BGRX")
            
            # 添加网格和标尺
            display_img = self.last_pil.copy()
            display_img = self._add_grid_and_ruler(display_img)
            
            # 缩放
            thumb = display_img.resize(
                (int(img.width * self.scale), int(img.height * self.scale)), 
                Image.LANCZOS)
            
            self.tkimg = ImageTk.PhotoImage(thumb)
            self.lab.config(image=self.tkimg)
            
            # 保存录制
            if self.record_mode:
                self._save_recording()
            
        except Exception as e:
            print(f"捕获错误: {e}")
        
        self.after_id = self.show.after(50, self.loop)

    # 其他方法保持不变...

# =============================================================================
# 主程序：鼠标坐标监控
# =============================================================================
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
        self.root.title("鼠标坐标 & 像素监控 v4")
        self.root.geometry("320x440")
        self.root.attributes("-topmost", True)
        self.root.resizable(False, False)

    def setup_widgets(self):
        """创建界面元素"""
        # 坐标 & 颜色
        self.lab_pos = tk.Label(self.root, text="X: 0 , Y: 0", font=("Consolas", 14))
        self.lab_pos.pack(pady=6)
        
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

        # 按钮区域
        btn_frame = ttk.Frame(self.root)
        btn_frame.pack(pady=4)
        
        self.btn_save = tk.Button(btn_frame, text="记录坐标 (F9)",
                                command=self.save_pos, width=20)
        self.btn_save.pack(pady=2)
        
        self.btn_copy = tk.Button(btn_frame, text="复制记录 (F10)",
                                command=self.copy_saved, width=20)
        self.btn_copy.pack(pady=2)

        # 捕获窗口控制
        cap_frame = ttk.Frame(self.root)
        cap_frame.pack(pady=4)
        
        self.btn_cap_open = tk.Button(cap_frame, text="开启捕获 (F5)", 
                                    command=self.open_capture, width=20)
        self.btn_cap_open.pack(side=tk.LEFT, padx=2)
        
        self.btn_cap_close = tk.Button(cap_frame, text="关闭捕获 (F6)", 
                                     command=self.close_capture, width=20)
        self.btn_cap_close.pack(side=tk.LEFT, padx=2)

    def bind_keys(self):
        """绑定快捷键"""
        self.root.bind("<F9>", lambda e: self.save_pos())
        self.root.bind("<F10>", lambda e: self.copy_saved())
        self.root.bind("<F8>", lambda e: self.set_relative_base())
        self.root.bind("<F5>", lambda e: self.open_capture())
        self.root.bind("<F6>", lambda e: self.close_capture())
        self.root.bind("<Escape>", lambda e: self.root.destroy())
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)

    def open_capture(self):
        """打开捕获窗口"""
        if not hasattr(self, 'capture_duo') or self.capture_duo is None:
            self.capture_duo = CapturePreviewDuoEnhanced()
            self.show_message("捕获窗口已开启")

    def close_capture(self):
        """关闭捕获窗口"""
        if hasattr(self, 'capture_duo') and self.capture_duo is not None:
            self.capture_duo.close()
            self.capture_duo = None
            self.show_message("捕获窗口已关闭")

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

    def monitor(self):
        """监控鼠标位置和颜色"""
        while self.running.is_set():
            try:
                x, y = pyautogui.position()
                with self.pos_lock:
                    dx, dy = x - self.last_pos[0], y - self.last_pos[1]
                    self.current_fps = self.adaptive_fps(dx, dy)
                    self.last_pos = (x, y)

                rgb = self.get_color_at(x, y)
                hex_color = "#%02x%02x%02x" % rgb
                
                self.root.after(0, lambda: self.update_gui(x, y, rgb, hex_color))
                
                time.sleep(1 / self.current_fps)
            except Exception as e:
                self.show_error(f"监控错误: {str(e)}")
                time.sleep(1)

    def get_color_at(self, x, y):
        """获取指定位置的颜色"""
        try:
            with mss.mss() as sct:
                pixel = sct.grab({"left": x, "top": y, "width": 1, "height": 1})
                return pixel.pixel(0, 0)[:3]  # 返回 RGB 值
        except:
            return (0, 0, 0)

    def adaptive_fps(self, dx, dy):
        """自适应帧率"""
        if dx * dx + dy * dy > MOVE_TH * MOVE_TH:
            self.last_move_time = time.time()
            return FPS_MOVE
        return FPS_MOVE if time.time() - self.last_move_time < 0.5 else FPS_STILL

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

    def get_relative_coords(self, x, y):
        """获取相对坐标"""
        if not self.relative_mode.get() or self.relative_base is None:
            return x, y
        base_x, base_y = self.relative_base
        return x - base_x, y - base_y

    def toggle_relative_mode(self):
        """切换相对坐标模式"""
        if self.relative_mode.get() and self.relative_base is None:
            self.set_relative_base()
        elif not self.relative_mode.get():
            self.lab_relative.config(text="基准点: 未设置")
            self.relative_base = None

    def set_relative_base(self):
        """设置相对坐标基准点"""
        self.relative_base = pyautogui.position()
        self.lab_relative.config(text=f"基准点: ({self.relative_base[0]}, {self.relative_base[1]})")
        self.relative_mode.set(True)

    def format_coordinates(self, x, y):
        """格式化坐标输出"""
        if self.relative_mode.get():
            x, y = self.get_relative_coords(x, y)
        
        fmt = self.coord_fmt.get()
        if fmt == "Python":
            return f"{x}, {y}"
        elif fmt == "JavaScript":
            return f"{{ x: {x}, y: {y} }}"
        else:  # CSS
            return f"{x}px {y}px"

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

    def show_error(self, message):
        """显示错误信息"""
        self.lab_error.config(text=message, fg="red")
        self.root.after(2000, lambda: self.lab_error.config(text=""))

    def show_message(self, message):
        """显示普通信息"""
        self.lab_error.config(text=message, fg="green")
        self.root.after(2000, lambda: self.lab_error.config(text="", fg="red"))

    def on_close(self):
        """关闭程序"""
        self.close_capture()
        self.save_config()
        self.running.clear()
        if self.monitor_thread.is_alive():
            self.monitor_thread.join(timeout=1.0)
        self.root.destroy()

    def run(self):
        """运行程序"""
        try:
            self.root.mainloop()
        except Exception as e:
            messagebox.showerror("错误", f"程序运行错误: {str(e)}")

if __name__ == "__main__":
    MousePositionMonitor().run()