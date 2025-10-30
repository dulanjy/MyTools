import tkinter as tk  # 导入tkinter库

def create_main_window():
    root = tk.Tk()  # 创建主窗口
    root.title("悬浮球效果")  # 窗口标题
    root.geometry("300x300")  # 设置窗口大小
    return root  # 返回主窗口对象

class FloatingBall(tk.Canvas):
    def __init__(self, master, x, y, radius=30):
        super().__init__(master, width=radius*2, height=radius*2, bg='blue', highlightthickness=0)
        self.radius = radius
        self.place(x=x, y=y)
        self.create_oval(0, 0, radius*2, radius*2, fill='blue')

        self.bind("<Button-1>", self.on_left_click)  # 左键点击事件
        self.bind("<B1-Motion>", self.on_drag)  # 拖动事件
        self.bind("<ButtonRelease-1>", self.on_release)  # 左键释放事件

    def on_left_click(self, event):
        print("左键点击悬浮球")  # 点击悬浮球时输出信息

    def on_drag(self, event):
        # 在拖动过程中更新悬浮球的位置
        self.place(x=event.x - self.radius, y=event.y - self.radius)

    def on_release(self, event):
        print("释放悬浮球")  # 释放悬浮球时输出信息

if __name__ == "__main__":
    root = create_main_window()  # 创建主窗口
    ball = FloatingBall(root, 50, 50)  # 在窗口中创建悬浮球
    root.mainloop()  # 启动主循环