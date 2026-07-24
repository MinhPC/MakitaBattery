import os
import sys
import tkinter as tk
from tkinter import ttk
import tkinter.font as tkfont
import importlib.util
import pkgutil
import sv_ttk
import darkdetect
from components.default_module import DefaultModule

# Lựa chọn mặc định load sẵn khi khởi động (theo display name).
# Nếu không tìm thấy tên này thì tự lấy mục đầu tiên có sẵn.
DEFAULT_MODULE = "Makita LXT"
DEFAULT_INTERFACE = "Arduino"

class MakitaBatteryApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Makita Battery")
        self.geometry("1270x760")
        self.minsize(1024, 640)
        self.set_icon("icon.png")
        self._setup_fonts()

        # Follow the Windows light/dark setting on startup (falls back to light)
        sv_ttk.set_theme("dark" if darkdetect.theme() == "Dark" else "light")

        self.main_app = None
        self.default_module = None
        self.loaded_modules = {}
        self.loaded_interfaces = {}
        self.module_names = {}
        self.interface_names = {}
        self.current_interface = None

        self.setup_sidebar()
        self.setup_main_window()
        self.setup_debug_frame()

        self.display_default_content()
        self.apply_theme_colors()
        self._select_defaults()

        # Close the serial port cleanly when the window is closed so the
        # COM port isn't left locked on Windows.
        self.protocol("WM_DELETE_WINDOW", self.on_close)

    def _select_defaults(self):
        """Chọn sẵn Interface + Module mặc định khi khởi động (không tự kết nối).
        Interface chọn trước để khi Module hiển thị đã có interface sẵn sàng."""
        interfaces = list(self.interface_combobox['values'])
        if interfaces:
            name = DEFAULT_INTERFACE if DEFAULT_INTERFACE in interfaces else interfaces[0]
            self.interface_var.set(name)
            self.display_interface_settings()

        modules = list(self.module_combobox['values'])
        if modules:
            name = DEFAULT_MODULE if DEFAULT_MODULE in modules else modules[0]
            self.module_var.set(name)
            self.display_module()

    def _setup_fonts(self):
        """Use Segoe UI (Windows 11 system font) for all default widgets."""
        for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont",
                     "TkHeadingFont", "TkTooltipFont"):
            try:
                tkfont.nametofont(name).configure(family="Segoe UI", size=10)
            except tk.TclError:
                pass

    def set_icon(self, icon_path):
        if hasattr(sys, '_MEIPASS'):
            # When running from a PyInstaller bundle
            icon_path = os.path.join(sys._MEIPASS, icon_path)

        icon = tk.PhotoImage(file=icon_path)
        self.iconphoto(False, icon)

    def setup_sidebar(self):
        self.sidebar = ttk.Frame(self, padding=(12, 12))
        self.sidebar.pack(fill='y', side='left')

        header = ttk.Label(self.sidebar, text="Settings",
                           font=('Segoe UI Semibold', 14))
        header.pack(anchor='w', pady=(0, 8))

        self.setup_module_frame()
        self.setup_interface_frame()
        self.setup_theme_switch()

    def setup_module_frame(self):
        module_frame = ttk.LabelFrame(self.sidebar, text="Module", padding=12)
        module_frame.pack(fill='x', pady=(0, 12))

        self.module_var = tk.StringVar()
        self.module_combobox = ttk.Combobox(module_frame, textvariable=self.module_var,
                                            width=24, state="readonly")
        self.module_combobox.pack(fill='x')

        self.load_modules()
        self.module_combobox.bind("<<ComboboxSelected>>", self.display_module)

    def setup_interface_frame(self):
        interface_frame = ttk.LabelFrame(self.sidebar, text="Interface", padding=12)
        interface_frame.pack(fill='x', pady=(0, 12))

        self.interface_var = tk.StringVar()
        self.interface_combobox = ttk.Combobox(interface_frame, textvariable=self.interface_var,
                                               width=24, state="readonly")
        self.interface_combobox.pack(fill='x')

        self.load_interfaces()
        self.interface_combobox.bind("<<ComboboxSelected>>", self.display_interface_settings)

        self.interface_wireframe = ttk.Frame(interface_frame, padding=(0, 12, 0, 0))
        self.interface_wireframe.pack(fill='both', expand=True)

    def setup_theme_switch(self):
        theme_frame = ttk.Frame(self.sidebar)
        theme_frame.pack(side='bottom', fill='x', pady=(12, 0))

        self.dark_var = tk.BooleanVar(value=(sv_ttk.get_theme() == "dark"))
        switch = ttk.Checkbutton(theme_frame, text="Chế độ tối", style="Switch.TCheckbutton",
                                 variable=self.dark_var, command=self.on_toggle_theme)
        switch.pack(anchor='w')

    def on_toggle_theme(self):
        sv_ttk.set_theme("dark" if self.dark_var.get() else "light")
        self.apply_theme_colors()

    def apply_theme_colors(self):
        """Style the non-ttk widgets (debug Text, Treeview rows) to match the theme."""
        dark = sv_ttk.get_theme() == "dark"
        text_bg = "#1c1c1c" if dark else "#fbfbfb"
        text_fg = "#e0e0e0" if dark else "#202020"
        if hasattr(self, "debug_text"):
            self.debug_text.config(bg=text_bg, fg=text_fg, insertbackground=text_fg,
                                   highlightthickness=0, borderwidth=0,
                                   selectbackground="#0067c0", selectforeground="#ffffff")
        if self.main_app and hasattr(self.main_app, "apply_theme"):
            self.main_app.apply_theme()

    def setup_main_window(self):
        self.main_window = ttk.Frame(self, padding=(20, 16))
        self.main_window.pack(fill='both', expand=True, side='top')

    def setup_debug_frame(self):
        self.debug_container = ttk.Frame(self)
        self.debug_container.pack(fill='x', side='top', padx=12, pady=(0, 12))

        self.debug_expanded = False
        self.debug_toggle = ttk.Button(self.debug_container, text="▸  Debug Information",
                                       command=self.toggle_debug)
        self.debug_toggle.pack(anchor='w')

        self.debug_body = ttk.Frame(self.debug_container)
        self.debug_text = tk.Text(self.debug_body, height=6, wrap='word',
                                  relief='flat', font=('Consolas', 9))
        self.debug_text.pack(fill='both', expand=True, pady=(6, 0))
        self.debug_text.config(state='disabled')
        # Mặc định thu gọn: không pack debug_body

    def toggle_debug(self):
        self.debug_expanded = not self.debug_expanded
        if self.debug_expanded:
            self.debug_body.pack(fill='both', expand=True)
            self.debug_toggle.config(text="▾  Debug Information")
        else:
            self.debug_body.pack_forget()
            self.debug_toggle.config(text="▸  Debug Information")

    def get_resource_path(self, relative_path):
        """ Get the absolute path to the resource, works for dev and for PyInstaller """
        if hasattr(sys, '_MEIPASS'):
            return os.path.join(sys._MEIPASS, relative_path)
        return os.path.join(os.path.abspath("."), relative_path)

    def _discover_plugins(self, package, name_map, combobox):
        """Import every plugin in a package, register its display name and
        populate the combobox. Shared by modules and interfaces."""
        plugin_dir = self.get_resource_path(package)
        plugin_names = sorted({name for _, name, _ in pkgutil.iter_modules([plugin_dir])})

        display_names = []
        for plugin_name in plugin_names:
            try:
                plugin = self.import_module(f"{package}.{plugin_name}")
                display_name = plugin.get_display_name()
                name_map[display_name] = plugin_name
                display_names.append(display_name)
            except Exception as e:
                self.update_debug(f"Failed to load {package} '{plugin_name}': {e}")

        combobox['values'] = display_names

    def load_modules(self):
        self._discover_plugins('modules', self.module_names, self.module_combobox)

    def load_interfaces(self):
        self._discover_plugins('interfaces', self.interface_names, self.interface_combobox)

    def _load_cached(self, package, name, cache):
        """Import a plugin once and reuse it on subsequent selections."""
        if name not in cache:
            cache[name] = self.import_module(f"{package}.{name}")
            self.update_debug(f"Imported {package}: {name}")
        else:
            self.update_debug(f"Using cached {package}: {name}")
        return cache[name]

    def display_default_content(self):
        self.clear_main_window()
        self.default_module = DefaultModule(self.main_window)
        self.default_module.pack(fill='both', expand=True)

    def display_module(self, event=None):
        display_name = self.module_var.get()
        selected_module = self.module_names.get(display_name, None)

        if selected_module:
            module_to_display = self._load_cached('modules', selected_module, self.loaded_modules)
            self.clear_main_window()
            self.main_app = module_to_display.ModuleApplication(self.main_window, None, self)
            self.main_app.set_interface(self.current_interface)

    def display_interface_settings(self, event=None):
        display_name = self.interface_var.get()
        selected_interface = self.interface_names.get(display_name, None)

        if selected_interface:
            interface_module = self._load_cached('interfaces', selected_interface, self.loaded_interfaces)
            self._teardown_current_interface()
            self.current_interface = interface_module.Interface(self.interface_wireframe, self)
            self.current_interface.pack(fill='both', expand=True)
            if self.main_app:
                self.main_app.set_interface(self.current_interface)

    def _teardown_current_interface(self):
        """Close the open serial port and destroy the previous interface so its
        COM port isn't left locked when switching interfaces."""
        if not self.current_interface:
            return
        serial_conn = getattr(self.current_interface, "serial", None)
        if serial_conn is not None and serial_conn.is_open:
            self.current_interface.close_serial_port()
        self.current_interface.destroy()
        self.current_interface = None

    def import_module(self, module_path):
        return importlib.import_module(module_path)

    def clear_main_window(self):
        for widget in self.main_window.winfo_children():
            widget.destroy()
        self.main_app = None
        self.default_module = None

    def update_debug(self, message):
        """Safe to call from any thread: the actual widget mutation always
        runs on the main thread via `after`, since background workers (serial
        I/O) log through this too."""
        self.after(0, self._append_debug, message)

    def _append_debug(self, message):
        if hasattr(self, 'debug_text'):  # Check if debug_text is initialized
            self.debug_text.config(state='normal')
            self.debug_text.insert('end', message + '\n')
            self.debug_text.see('end')
            self.debug_text.config(state='disabled')
        else:
            print("Debug:", message)  # Fallback if debug_text isn't initialized

    def on_close(self):
        self._teardown_current_interface()
        self.destroy()

if __name__ == "__main__":
    app = MakitaBatteryApp()
    app.mainloop()
