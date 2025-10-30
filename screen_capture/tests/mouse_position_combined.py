import tkinter as tk
from tkinter import ttk
import pyautogui
import threading
import functools
import pyperclip

class MousePositionMonitor:
    def __init__(self):
        self.root = tk.Tk()
        self.setup_window()
        self.setup_variables()
        self.create_widgets()
        self.setup_bindings()
        
        # 使用 Event 进行线程控制
        self.running = threading.Event()
        self.running.set()
        
        # 启动监控线程
        self.monitor_thread = threading.Thread(target=self.monitor, daemon=True)
        self.monitor_thread.start()
        
    def setup_window(self):
        """设置窗口属性"""
        self.root.title("鼠标坐标 & 像素监控")
        self.root.geometry("320x280")  # 增加高度以适应更多控件
        self.root.attributes("-topmost", True)
        self.root.resizable(False, False)
        
    def setup_variables(self):
        """初始化变量"""
        self.last_pos = (-1, -1)
        self.saved_pos = None  # 保存的坐标位置
        self.coordinate_format = tk.StringVar(value="Python")
        
    def create_widgets(self):
        """创建界面元素"""
        # 当前坐标显示
        self.lab_pos = tk.Label(self.root, text="X: 0 , Y: 0", font=("Consolas", 14))
        self.lab_pos.pack(pady=6)
        
        # 颜色信息
        self.lab_color = tk.Label(self.root, text="RGB: (0, 0, 0)  #000000", font=("Consolas", 12))
        self.lab_color.pack(pady=6)
        
        # 颜色预览
        self.color_canvas = tk.Canvas(self.root, width=60, height=30, bd=1, relief="solid")
        self.color_canvas.pack(pady=4)
        
        # 已保存的坐标显示
        self.lab_saved = tk.Label(self.root, text="未记录坐标", font=("Consolas", 12))
        self.lab_saved.pack(pady=4)
        
        # 坐标格式选择
        formats_frame = ttk.LabelFrame(self.root, text="坐标格式")
        formats_frame.pack(pady=4, padx=10, fill="x")
        
        formats = ["Python (x, y)", "JavaScript {x,y}", "CSS xpx ypx"]
        for fmt in formats:
            ttk.Radiobutton(formats_frame, text=fmt, variable=self.coordinate_format, 
                          value=fmt.split()[0]).pack(side=tk.LEFT, padx=5, pady=2)
        
        # 按钮框架
        button_frame = ttk.Frame(self.root)
        button_frame.pack(pady=4)
        
        # 记录和复制按钮
        self.btn_save = tk.Button(button_frame, text="记录坐标 (F9)", 
                                command=self.save_current_position, width=20)
        self.btn_save.pack(pady=2)
        
        self.btn_copy = tk.Button(button_frame, text="复制记录的坐标 (F10)", 
                                command=self.copy_saved_position, width=20)
        self.btn_copy.pack(pady=2)
        
    def setup_bindings(self):
        """设置快捷键和事件绑定"""
        self.root.bind('<F9>', lambda e: self.save_current_position())
        self.root.bind('<F10>', lambda e: self.copy_saved_position())
        self.root.bind('<Escape>', lambda e: self.root.destroy())
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        
    @functools.lru_cache(maxsize=100)
    def get_pixel_color(self, x, y):
        """获取指定坐标的颜色（带缓存）"""
        try:
            return pyautogui.screenshot(region=(x, y, 1, 1)).getpixel((0, 0))
        except pyautogui.FailSafeException:
            return None
        except Exception as e:
            self.show_error(f"获取颜色失败: {str(e)}")
            return None
            
    def format_coordinates(self, x, y):
        """根据选择的格式返回坐标字符串"""
        fmt = self.coordinate_format.get()
        if fmt == "Python":
            return f"{x}, {y}"
        elif fmt == "JavaScript":
            return f"{{ x: {x}, y: {y} }}"
        elif fmt == "CSS":
            return f"{x}px {y}px"
        return f"{x}, {y}"
        
    def save_current_position(self):
        """保存当前鼠标位置"""
        self.saved_pos = pyautogui.position()
        self.lab_saved.config(text=f"已记录坐标: X: {self.saved_pos[0]:4} , Y: {self.saved_pos[1]:4}")
        self.btn_save.config(text="已记录!")
        self.root.after(800, lambda: self.btn_save.config(text="记录坐标 (F9)"))
        
    def copy_saved_position(self):
        """复制已保存的坐标位置"""
        if self.saved_pos is not None:
            text = self.format_coordinates(self.saved_pos[0], self.saved_pos[1])
            pyperclip.copy(text)
            self.btn_copy.config(text="已复制!")
            self.root.after(800, lambda: self.btn_copy.config(text="复制记录的坐标 (F10)"))
        else:
            self.show_error("请先记录坐标位置")
            
    def show_error(self, message):
        """在界面上显示错误信息"""
        self.lab_color.config(text=message, fg="red")
        self.root.after(2000, lambda: self.lab_color.config(fg="black"))
        
    def update_gui(self, x, y, rgb):
        """在主线程中更新 GUI"""
        if rgb is None:
            return
            
        self.lab_pos.config(text=f"X: {x:4} , Y: {y:4}")
        hex_color = "#%02x%02x%02x" % rgb
        self.lab_color.config(text=f"RGB: {rgb}  {hex_color}")
        self.color_canvas.config(bg=hex_color)
        
    def monitor(self):
        """监控鼠标位置和颜色的后台线程"""
        while self.running.is_set():
            try:
                x, y = pyautogui.position()
                
                # 只在位置变化时更新
                if (x, y) != self.last_pos:
                    self.last_pos = (x, y)
                    rgb = self.get_pixel_color(x, y)
                    # 使用 after 确保在主线程中更新 GUI
                    self.root.after(0, lambda: self.update_gui(x, y, rgb))
                    
                # 使用 after 代替 sleep
                self.root.after(50)  # 20 FPS
                
            except Exception as e:
                self.root.after(0, lambda: self.show_error(f"监控错误: {str(e)}"))
                self.root.after(1000)  # 发生错误时降低刷新频率
                
    def on_close(self):
        """清理资源并关闭程序"""
        self.running.clear()  # 停止监控线程
        self.get_pixel_color.cache_clear()  # 清除缓存
        self.root.destroy()
        
    def run(self):
        """启动程序"""
        self.root.mainloop()

if __name__ == "__main__":
    app = MousePositionMonitor()
    app.run()