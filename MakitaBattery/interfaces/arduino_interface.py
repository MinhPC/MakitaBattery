import tkinter as tk
from tkinter import ttk
import threading
import serial
import serial.tools.list_ports

from async_utils import run_async

INTERFACE_VERSION_CMD   = [0x01, 0x00, 0x03, 0x01]

def get_display_name():
    return "Arduino"

class Interface(ttk.Frame):
    def __init__(self, parent, app_instance):
        super().__init__(parent)
        self.parent = parent
        self.app_instance = app_instance
        self.serial = serial.Serial()
        self.serial.timeout = 1
        # Serializes actual hardware access: request() may run on a background
        # thread (see async_utils.run_async), so concurrent reads/writes from
        # more than one in-flight operation must not interleave on the wire.
        self._lock = threading.Lock()
        self.create_widgets()

    def create_widgets(self):
        serial_label = ttk.Label(self, text="Serial Port")
        serial_label.pack(anchor='w', pady=(0, 4))

        ports = self.get_available_serial_ports()

        self.conf_port = ttk.Combobox(self, values=ports, state="readonly", width=22)
        if ports:
            self.conf_port.current(0)   # chọn sẵn port đầu tiên
        # nếu không có port -> để trống (null)
        self.conf_port.pack(fill='x', pady=(0, 8))
        self.conf_port.bind("<<ComboboxSelected>>", lambda e: self._update_connect_state())

        self.connect_button = ttk.Button(self, text="Connect", style="Accent.TButton",
                                         command=self.toggle_connection)
        self.connect_button.pack(fill='x', pady=4)

        self.refresh_button = ttk.Button(self, text="Refresh port list",
                                        command=self.refresh_serial_list)
        self.refresh_button.pack(fill='x', pady=4)

        self.version_label = ttk.Label(self, anchor="w", text="Version: —")
        self.version_label.pack(anchor='w', pady=(8, 0))

        self._update_connect_state()

    def _update_connect_state(self):
        """Nút Connect chỉ bật khi đã chọn serial port (hoặc đang kết nối để cho phép
        Disconnect). Chưa đủ setting (không có port) -> disable."""
        if self.serial.is_open or self.conf_port.get():
            self.connect_button.config(state="normal")
        else:
            self.connect_button.config(state="disabled")

    def refresh_serial_list(self):
        ports = self.get_available_serial_ports()
        self.conf_port["values"] = ports
        # Giữ lựa chọn hiện tại nếu còn; nếu không, chọn port đầu hoặc để trống (null)
        if self.conf_port.get() not in ports:
            if ports:
                self.conf_port.current(0)
            else:
                self.conf_port.set("")
        self._update_connect_state()


    def get_available_serial_ports(self):
        ports = [port.device for port in serial.tools.list_ports.comports()]
        return ports

    def toggle_connection(self):
        if self.serial.is_open:
            self.close_serial_port()
        else:
            self.open_serial_port()

    def open_serial_port(self):
        """Opens the port and queries the firmware version on a background
        thread — the version query can retry up to 5 times with a 1s serial
        timeout each, which would otherwise freeze the UI for up to ~5s."""
        selected_port = self.conf_port.get()
        if not selected_port:
            self.app_instance.update_debug("No serial port selected. Please select a port from the dropdown.")
            return
        self.serial.port = selected_port
        self.connect_button.config(state="disabled")

        def work():
            self.serial.open()
            return self.get_version()

        def on_success(version):
            self.version_label.config(text=f"Version: {version}")
            self.app_instance.update_debug(f"Opened serial port: {selected_port}")
            self.connect_button.config(text="Disconnect", command=self.close_serial_port)
            self._update_connect_state()

        def on_error(exc):
            self.serial.close()
            if isinstance(exc, serial.SerialException):
                self.app_instance.update_debug(f"Error opening serial port {selected_port}: {exc}. Check the port is not in use by another application.")
            else:
                self.app_instance.update_debug(f"Unexpected error opening serial port {selected_port}: {type(exc).__name__}: {exc}")
            self._update_connect_state()

        run_async(self, work, on_success, on_error)

    def close_serial_port(self):
        if self.serial.is_open:
            self.serial.close()
            self.app_instance.update_debug("Closed serial port")
            self.connect_button.config(text="Connect", command=self.open_serial_port)
        self._update_connect_state()

    def get_version(self):
        response = self.request(INTERFACE_VERSION_CMD, max_attempts=5)
        version_string = '.'.join(str(byte) for byte in response[2:])

        return version_string

    def request(self, request, max_attempts=2):
        if not self.serial.is_open:
            raise ConnectionError("Serial port is not open. Please connect to the Arduino first.")

        expected_length = request[2] + 2
        with self._lock:
            for attempt in range(1, max_attempts + 1):
                self.app_instance.update_debug(f">> {' '.join(f'{x:02X}' for x in request[3:])}")
                try:
                    self.serial.reset_input_buffer()
                    self.serial.write(request)

                    response = self.serial.read(expected_length)
                    self.app_instance.update_debug(f"<< {' '.join(f'{x:02X}' for x in response[2:])}")
                    if request[2] == 0:
                        return

                    if len(response) == 0:
                        raise TimeoutError(f"No response received from Arduino (expected {expected_length} bytes). Check that a battery is connected.")

                    if len(response) != expected_length:
                        raise ValueError(f"Incomplete response: received {len(response)} bytes, expected {expected_length}. The battery may not be seated correctly.")

                    if all(byte == 0xff for byte in response[2:]):
                        raise ValueError("Invalid response: all bytes are 0xFF. The battery may not be communicating correctly.")

                    return response

                except (TimeoutError, ValueError) as e:
                    self.app_instance.update_debug(f"Attempt {attempt}/{max_attempts} failed: {e}")
                except serial.SerialException as e:
                    self.app_instance.update_debug(f"Attempt {attempt}/{max_attempts} serial error: {e}. The Arduino may have been disconnected.")
                except Exception as e:
                    self.app_instance.update_debug(f"Attempt {attempt}/{max_attempts} unexpected error: {type(e).__name__}: {e}")
            raise ConnectionError(f"Failed to get a valid response after {max_attempts} attempts. Ensure the Arduino is connected and a battery is inserted.")

