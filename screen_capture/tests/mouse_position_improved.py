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
        self.root.geometry("320x200")
        self.root.attributes("-topmost", True)
        self.root.resizable(False, False)
        
    def setup_variables(self):
        """初始化变量"""
        self.last_pos = (-1, -1)
        self.coordinate_format = tk.StringVar(value="Python")
        
    def create_widgets(self):
        """创建界面元素"""
        # 坐标显示
        self.lab_pos = tk.Label(self.root, text="X: 0 , Y: 0", font=("Consolas", 14))
        self.lab_pos.pack(pady=6)
        
        # 颜色信息
        self.lab_color = tk.Label(self.root, text="RGB: (0, 0, 0)  #000000", font=("Consolas", 12))
        self.lab_color.pack(pady=6)
        
        # 颜色预览
        self.color_canvas = tk.Canvas(self.root, width=60, height=30, bd=1, relief="solid")
        self.color_canvas.pack(pady=4)
        
        # 坐标格式选择
        formats = ["Python", "JavaScript", "CSS"]
        format_frame = ttk.Frame(self.root)
        format_frame.pack(pady=4)
        
        for fmt in formats:
            ttk.Radiobutton(format_frame, text=fmt, variable=self.coordinate_format, 
                          value=fmt).pack(side=tk.LEFT, padx=5)
        
        # 复制按钮
        self.btn_copy = tk.Button(self.root, text="复制坐标 (Ctrl+C)", 
                                command=self.copy_to_clipboard, width=20)
        self.btn_copy.pack(pady=4)
        
    def setup_bindings(self):
        """设置快捷键和事件绑定"""
        self.root.bind("<Control-c>", lambda e: self.copy_to_clipboard())
        self.root.bind("<Escape>", lambda e: self.root.destroy())
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
        
    def copy_to_clipboard(self):
        """复制坐标到剪贴板"""
        x, y = pyautogui.position()
        text = self.format_coordinates(x, y)
        pyperclip.copy(text)
        self.btn_copy.config(text="已复制!")
        self.root.after(800, lambda: self.btn_copy.config(text="复制坐标 (Ctrl+C)"))
        
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