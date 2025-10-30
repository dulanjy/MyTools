import tkinter as tk
import pyautogui
import threading
import time
import pyperclip   # 跨平台剪贴板

# -------------------- 主窗口 --------------------
root = tk.Tk()
root.title("鼠标坐标 & 像素监控")
root.geometry("320x200")
root.attributes("-topmost", True)
root.resizable(False, False)

# -------------------- 变量 --------------------
running = True          # 线程控制标志
last_pos = (-1, -1)     # 缓存上一次坐标，避免重复截图

# -------------------- 标签 --------------------
lab_pos = tk.Label(root, text="X: 0 , Y: 0", font=("Consolas", 14))
lab_pos.pack(pady=6)

lab_color = tk.Label(root, text="RGB: (0, 0, 0)  #000000", font=("Consolas", 12))
lab_color.pack(pady=6)

# 颜色块画布
color_canvas = tk.Canvas(root, width=60, height=30, bd=1, relief="solid")
color_canvas.pack(pady=4)

# -------------------- 复制功能 --------------------
saved_pos = None  # 保存的坐标位置

def save_current_position():
    """保存当前鼠标位置"""
    global saved_pos
    saved_pos = pyautogui.position()
    btn_copy.config(text="已记录坐标!")
    lab_saved.config(text=f"已记录坐标: X: {saved_pos[0]:4} , Y: {saved_pos[1]:4}")
    root.after(800, lambda: btn_copy.config(text="记录当前坐标 (F9)"))

def copy_saved_position():
    """复制已保存的坐标位置"""
    if saved_pos is not None:
        text = f"{saved_pos[0]},{saved_pos[1]}"
        pyperclip.copy(text)
        btn_paste.config(text="已复制!")
        root.after(800, lambda: btn_paste.config(text="复制记录的坐标 (F10)"))

# 添加快捷键绑定
def setup_shortcuts():
    root.bind('<F9>', lambda e: save_current_position())  # F9 保存位置
    root.bind('<F10>', lambda e: copy_saved_position())   # F10 复制保存的位置

# 显示已保存的坐标
lab_saved = tk.Label(root, text="未记录坐标", font=("Consolas", 12))
lab_saved.pack(pady=4)

# 按钮
btn_copy = tk.Button(root, text="记录当前坐标 (F9)", command=save_current_position, width=20)
btn_copy.pack(pady=2)

btn_paste = tk.Button(root, text="复制记录的坐标 (F10)", command=copy_saved_position, width=20)
btn_paste.pack(pady=2)

# 设置快捷键
setup_shortcuts()

# -------------------- 后台线程 --------------------
def monitor():
    global last_pos
    while running:
        x, y = pyautogui.position()          # 自动支持多屏虚拟桌面
        lab_pos.config(text=f"X: {x:4} , Y: {y:4}")

        # 只有坐标变化才重新取色，节省 CPU
        if (x, y) != last_pos:
            last_pos = (x, y)
            try:
                rgb = pyautogui.screenshot(region=(x, y, 1, 1)).getpixel((0, 0))
            except Exception:
                rgb = (0, 0, 0)
            hex_color = "#%02x%02x%02x" % rgb
            lab_color.config(text=f"RGB: {rgb}  {hex_color}")
            color_canvas.config(bg=hex_color)

        time.sleep(0.05)   # 20 FPS 足够流畅

threading.Thread(target=monitor, daemon=True).start()

# -------------------- 退出处理 --------------------
def on_close():
    global running
    running = False
    root.destroy()

root.protocol("WM_DELETE_WINDOW", on_close)

# -------------------- 启动 --------------------
root.mainloop()