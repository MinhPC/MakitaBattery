import tkinter as tk
from tkinter import ttk

class DefaultModule(ttk.Frame):
    def __init__(self, parent):
        super().__init__(parent)
        self.parent = parent
        self.create_widgets()

    def create_widgets(self):
        wrapper = ttk.Frame(self)
        wrapper.place(relx=0.5, rely=0.4, anchor='center')

        label = ttk.Label(wrapper, text="Makita Battery",
                          font=('Segoe UI Semibold', 20))
        label.pack(pady=(0, 12))

        message = ttk.Label(wrapper, text="Chọn một module từ thanh bên trái để bắt đầu.",
                            font=('Segoe UI', 11))
        message.pack(pady=4)

        info = ttk.Label(wrapper, text="Kết nối Arduino và gắn pin để đọc dữ liệu.",
                         font=('Segoe UI', 10), foreground="#8a8a8a")
        info.pack(pady=4)
