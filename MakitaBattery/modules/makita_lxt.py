from tkinter import ttk
from tkinter import messagebox
import tkinter as tk
import time
import sv_ttk

from async_utils import run_async
import history_log

def get_display_name():
    return "Makita LXT"

# Command Definitions
MODEL_CMD           = [0x01, 0x02, 0x10, 0xCC, 0xDC, 0x0C]
READ_DATA_REQUEST   = [0x01, 0x04, 0x1D, 0xCC, 0xD7, 0x00, 0x00, 0xFF]
TESTMODE_CMD        = [0x01, 0x03, 0x09, 0x33, 0xD9, 0x96, 0xA5]
LEDS_ON_CMD         = [0x01, 0x02, 0x09, 0x33, 0xDA, 0x31]
LEDS_OFF_CMD        = [0x01, 0x02, 0x09, 0x33, 0xDA, 0x34]
RESET_ERROR_CMD     = [0x01, 0x02, 0x09, 0x33, 0xDA, 0x04]
ROMID_CHARGER_CMD   = [0x01, 0x02, 0x28, 0x33, 0xF0, 0x00]
CHARGER_CMD         = [0x01, 0x02, 0x20, 0xCC, 0xF0, 0x00]
READ_MSG_CMD        = [0x01, 0x02, 0x28, 0x33, 0xAA, 0x00]
CLEAR_CMD           = [0x01, 0x02, 0x00, 0xCC, 0xF0, 0x00]
STORE_CMD           = [0x01, 0x02, 0x00, 0x33, 0x55, 0xA5]
# (CLEAN_FRAME_CMD gốc — frame cứng từ pin khác — đã bỏ; lệnh ghi giờ dựng động
#  từ frame thật + profile trong _build_write_frame_cmd.)


# Commands specific to the F0513 version
F0513_VCELL_1_CMD   = [0x01, 0x01, 0x02, 0xCC, 0x31]
F0513_VCELL_2_CMD   = [0x01, 0x01, 0x02, 0xCC, 0x32]
F0513_VCELL_3_CMD   = [0x01, 0x01, 0x02, 0xCC, 0x33]
F0513_VCELL_4_CMD   = [0x01, 0x01, 0x02, 0xCC, 0x34]
F0513_VCELL_5_CMD   = [0x01, 0x01, 0x02, 0xCC, 0x35]
F0513_TEMP_CMD      = [0x01, 0x01, 0x02, 0xCC, 0x52]
F0513_MODEL_CMD     = [0x01, 0x00, 0x02, 0x31]
F0513_VERSION_CMD   = [0x01, 0x00, 0x02, 0x32]
F0513_TESTMODE_CMD  = [0x01, 0x01, 0x00, 0xCC, 0x99]

# --- Model specs (kiến trúc theo data, giống FRAME_PROFILES bên dưới) ------
# Mỗi đời pin có bộ lệnh probe/đọc-dữ-liệu/LED-off riêng. Thêm model mới =
# thêm 1 hàm probe + 1 hàm read_data (nếu cần) + 1 entry vào MODEL_SPECS,
# KHÔNG cần sửa on_read_static_click/on_read_data_click/on_all_leds_off_click.

def _probe_standard(interface):
    """Probe cho đời chuẩn — trả về model string hoặc raise nếu không phải."""
    response = interface.request(MODEL_CMD)
    return response[2:9].decode('utf-8')

def _probe_f0513(interface):
    """Probe cho đời F0513 (chỉ hỗ trợ chẩn đoán, không frame-repair)."""
    response = interface.request(F0513_MODEL_CMD)
    interface.request(CLEAR_CMD)
    return f"BL{response[2]:X}{response[3]:X}"

def _read_data_standard(interface):
    response = interface.request(READ_DATA_REQUEST)
    v_pack = int.from_bytes(response[2:4], byteorder='little') / 1000
    v_cell1 = int.from_bytes(response[4:6], byteorder='little') / 1000
    v_cell2 = int.from_bytes(response[6:8], byteorder='little') / 1000
    v_cell3 = int.from_bytes(response[8:10], byteorder='little') / 1000
    v_cell4 = int.from_bytes(response[10:12], byteorder='little') / 1000
    v_cell5 = int.from_bytes(response[12:14], byteorder='little') / 1000
    voltages = [v_cell1, v_cell2, v_cell3, v_cell4, v_cell5]
    v_diff = round(max(voltages) - min(voltages), 2)
    t_cell = int.from_bytes(response[16:18], byteorder='little') / 100
    t_mosfet = int.from_bytes(response[18:20], byteorder='little') / 100
    return _build_battery_data(v_pack, voltages, v_diff, t_cell, t_mosfet)

def _read_data_f0513(interface):
    interface.request(CLEAR_CMD)
    interface.request(CLEAR_CMD)
    cell1 = interface.request(F0513_VCELL_1_CMD)
    cell2 = interface.request(F0513_VCELL_2_CMD)
    cell3 = interface.request(F0513_VCELL_3_CMD)
    cell4 = interface.request(F0513_VCELL_4_CMD)
    cell5 = interface.request(F0513_VCELL_5_CMD)
    temp = interface.request(F0513_TEMP_CMD)
    voltages = [int.from_bytes(c[2:4], byteorder='little') / 1000
                for c in (cell1, cell2, cell3, cell4, cell5)]
    v_pack = sum(voltages)
    v_diff = round(max(voltages) - min(voltages), 2)
    t_cell = int.from_bytes(temp[2:4], byteorder='little') / 100
    t_mosfet = ""
    return _build_battery_data(v_pack, voltages, v_diff, t_cell, t_mosfet)

def _build_battery_data(v_pack, voltages, v_diff, t_cell, t_mosfet):
    battery_data = {
        "Pack Voltage": v_pack,
        "Cell 1 Voltage": voltages[0],
        "Cell 2 Voltage": voltages[1],
        "Cell 3 Voltage": voltages[2],
        "Cell 4 Voltage": voltages[3],
        "Cell 5 Voltage": voltages[4],
        "Cell Voltage Difference": v_diff,
        "Temperature Sensor 1": t_cell,
        "Temperature Sensor 2": t_mosfet,
    }
    return battery_data, voltages, v_diff, t_cell, t_mosfet

# Danh sách model được hỗ trợ, theo thứ tự thử probe khi đọc "1. Đọc thông tin".
MODEL_SPECS = [
    {
        "command_version": "",
        "probe": _probe_standard,
        "limited": False,          # hỗ trợ đầy đủ: đọc dữ liệu + frame repair
        "read_data": _read_data_standard,
        "led_off_cmd": TESTMODE_CMD,
    },
    {
        "command_version": "F0513",
        "probe": _probe_f0513,
        "limited": True,           # chỉ hỗ trợ chẩn đoán (đọc), không frame repair
        "read_data": _read_data_f0513,
        "led_off_cmd": F0513_TESTMODE_CMD,
    },
]

def get_model_spec(command_version):
    """Tìm spec theo command_version đã xác định qua probe. None nếu chưa/không khớp."""
    for spec in MODEL_SPECS:
        if spec["command_version"] == command_version:
            return spec
    return None

# Ngưỡng đánh giá tình trạng pin Li-ion (Makita LXT 18V, 5 cell nối tiếp).
# Chỉnh các giá trị này để thay đổi mức độ nghiêm khắc của kết luận.
CELL_OVER     = 4.25   # V — điện áp 1 cell vượt mức này = quá áp
CELL_LOW      = 3.00   # V — cell dưới mức này = thấp, cần sạc
CELL_CRITICAL = 2.50   # V — cell dưới mức này = nguy hiểm, có thể đã hỏng
DIFF_WARN     = 0.15   # V — lệch giữa các cell vượt mức này = bắt đầu mất cân bằng
DIFF_SEVERE   = 0.30   # V — lệch giữa các cell vượt mức này = mất cân bằng nặng
TEMP_HOT      = 45.0   # °C — nhiệt độ khi đọc (trạng thái nghỉ) vượt mức này = nóng bất thường
CYCLE_HIGH    = 300    # số lần sạc vượt mức này = đã dùng nhiều

# "Error flags" (byte 29) là một BITFIELD — mỗi bit là một cờ lỗi riêng.
# Makita KHÔNG công bố ý nghĩa từng bit và cộng đồng chưa map đầy đủ, nên để trống.
# Cách tự xác định: đọc byte lỗi của nhiều pin (tốt/lỗi khác nhau), hoặc bấm
# "Clear errors" rồi đọc lại để biết bit nào là lỗi active vs lịch sử.
# Khi biết ý nghĩa một bit, điền vào đây để nó tự hiển thị trong phần đánh giá:
#   ERROR_FLAG_MEANINGS = {0: "xả kiệt (over-discharge)", 3: "quá dòng", ...}
#
# QUAN TRỌNG (đã kiểm chứng thực nghiệm): byte này KHÔNG phải cờ lưu tĩnh —
# BMS tự tính lại (live) mỗi lần đọc, nên "Clear errors"/"Frame repair" ghi 0
# vào đây chỉ có hiệu lực tức thời, không giữ được lâu dài. Đồng thời 1 giá
# trị cụ thể (VD 0xA5) có thể xuất hiện trên cả pin lỗi lẫn pin khỏe — không
# tự nó là bằng chứng lỗi. Trước khi so sánh byte giữa các pin để map ý
# nghĩa bit, PHẢI đọc cùng 1 pin nhiều lần liên tiếp để loại các byte "live"
# (tự đổi dù không tác động vật lý) khỏi phép so sánh. Chi tiết + phương
# pháp test: xem docs/makita-lxt-frame-notes.md.
ERROR_FLAG_MEANINGS = {}

# Màu verdict theo (light, dark) — chọn sắc đủ tương phản trên cả 2 nền.
VERDICT_COLORS = {
    'good': ("#16a34a", "#4ade80"),
    'warn': ("#c2740c", "#fbbf24"),
    'bad':  ("#dc2626", "#f87171"),
    'none': ("#6b6b6b", "#9a9a9a"),
}

# Màu nền/chữ hộp thông báo trạng thái (dạng "card" phẳng), theo (light, dark).
STATUS_BOX_COLORS = {
    'good': {'light': ("#eafbea", "#15803d"), 'dark': ("#1c2e1c", "#4ade80")},
    'warn': {'light': ("#fff7e6", "#b45309"), 'dark': ("#2e2410", "#fbbf24")},
    'bad':  {'light': ("#fdeaea", "#b91c1c"), 'dark': ("#2e1c1c", "#f87171")},
    'none': {'light': ("#f3f3f3", "#6b6b6b"), 'dark': ("#2b2b2b", "#9a9a9a")},
}

# Bảng OCV (điện áp hở mạch, không tải) -> % dung lượng cho 1 cell Li-ion —
# dùng để ước lượng "Tình trạng sạc" gần đúng khi đọc lúc pin đang nghỉ. Đây
# là bảng tham khảo phổ biến (không phải số hiệu chỉnh riêng cho BMS Makita),
# chỉ mang tính hiển thị tham khảo, không dùng để tính toán an toàn/bảo vệ.
_SOC_CURVE = [
    (4.20, 100), (4.15, 95), (4.11, 90), (4.08, 85), (4.02, 80),
    (3.98, 75), (3.95, 70), (3.91, 65), (3.87, 60), (3.85, 55),
    (3.84, 50), (3.82, 45), (3.80, 40), (3.79, 35), (3.77, 30),
    (3.75, 25), (3.73, 20), (3.71, 15), (3.69, 10), (3.61, 5),
    (3.27, 0),
]

def estimate_soc(avg_cell_voltage):
    """Ước lượng % dung lượng từ điện áp TRUNG BÌNH 1 cell, nội suy tuyến
    tính theo bảng OCV chuẩn ở trên. Chỉ mang tính tham khảo hiển thị."""
    pts = _SOC_CURVE
    if avg_cell_voltage >= pts[0][0]:
        return 100
    if avg_cell_voltage <= pts[-1][0]:
        return 0
    for (v_hi, p_hi), (v_lo, p_lo) in zip(pts, pts[1:]):
        if v_lo <= avg_cell_voltage <= v_hi:
            frac = (avg_cell_voltage - v_lo) / (v_hi - v_lo)
            return round(p_lo + frac * (p_hi - p_lo))
    return 0

def _round_rect(canvas, x1, y1, x2, y2, r=10, **kwargs):
    """Vẽ hình chữ nhật bo góc lên 1 tk.Canvas (dùng cho icon cell pin)."""
    points = [
        x1 + r, y1, x2 - r, y1, x2, y1, x2, y1 + r,
        x2, y2 - r, x2, y2, x2 - r, y2, x1 + r, y2,
        x1, y2, x1, y2 - r, x1, y1 + r, x1, y1,
    ]
    return canvas.create_polygon(points, smooth=True, **kwargs)

class BatteryCellWidget(tk.Canvas):
    """Icon 1 cell dạng hình TRỤ giống cell 18650 thật: thân trụ vỏ xanh
    (giống lớp vỏ co nhiệt phổ biến của cell 18650), nắp/đáy hình ellipse tạo
    cảm giác 3D, cực + nổi ở đỉnh, cực - phẳng ở đáy (cố định, không đảo
    chiều — vì cell 18650 thật luôn có + trên/- dưới, không phụ thuộc cách
    đấu nối tiếp trong pack). Điện áp hiển thị ngay trên thân."""
    WIDTH = 64
    HEIGHT = 130

    def __init__(self, parent, index, bg="#ffffff", **kwargs):
        super().__init__(parent, width=self.WIDTH, height=self.HEIGHT,
                          highlightthickness=0, bg=bg, **kwargs)
        self.index = index
        self._voltage = None
        self._redraw()

    def set_bg(self, bg):
        self.config(bg=bg)
        self._redraw()

    def set_voltage(self, voltage):
        self._voltage = voltage
        self._redraw()

    def _redraw(self):
        self.delete("all")
        w, h = self.WIDTH, self.HEIGHT
        has_v = self._voltage is not None and self._voltage != ""
        pct = (estimate_soc(self._voltage) / 100) if has_v else 0.0

        empty_fill = "#e6e6e6"
        tube_edge  = "#9a9a9a" if has_v else "#9a9a9a"
        cap_fill   = "#e2e2e2"
        cap_edge   = "#a0a0a0"
        term_fill  = "#d8b23a" if has_v else "#b5b5b5"   # cực + nổi trên đỉnh

        if not has_v:
            fill_color, highlight = "#c9c9c9", "#dedede"
        elif pct >= 0.5:
            fill_color, highlight = "#22a559", "#7bdb9e"   # còn nhiều -> xanh lá
        elif pct >= 0.2:
            fill_color, highlight = "#eab308", "#fde68a"   # trung bình -> vàng
        else:
            fill_color, highlight = "#dc2626", "#f3a5a5"   # sắp hết -> đỏ

        cx = w / 2
        r = w * 0.36
        body_top = 16
        body_bottom = h - 10
        body_height = body_bottom - body_top

        # Thân trụ: nền "rỗng" trước, rồi mực dâng từ đáy lên theo % dung lượng
        # (ước lượng từ điện áp qua estimate_soc) -> mô phỏng thước đo mức pin.
        self.create_rectangle(cx - r, body_top, cx + r, body_bottom,
                              fill=empty_fill, outline="")
        fill_top = body_bottom - pct * body_height
        if pct > 0:
            self.create_rectangle(cx - r, fill_top, cx + r, body_bottom,
                                  fill=fill_color, outline="")
            hi_top = max(fill_top, body_top)
            self.create_rectangle(cx - r * 0.5, hi_top + 2, cx - r * 0.1, body_bottom - 2,
                                  fill=highlight, outline="")
        self.create_rectangle(cx - r, body_top, cx + r, body_bottom,
                              outline=tube_edge, width=1)

        # Vạch chia 4 mức tham chiếu 25/50/75/100% (kiểu ống đong) — vạch nhỏ
        # nhô ra 2 bên thân trụ, không đè lên màu mực bên trong.
        for frac in (0.25, 0.5, 0.75, 1.0):
            ty = body_bottom - frac * body_height
            self.create_line(cx - r - 4, ty, cx - r, ty, fill=tube_edge, width=1)
            self.create_line(cx + r, ty, cx + r + 4, ty, fill=tube_edge, width=1)

        # Đáy (-) và nắp (+) dạng ellipse -> tạo cảm giác hình trụ 3D
        self.create_oval(cx - r, body_bottom - 6, cx + r, body_bottom + 6,
                         fill=cap_fill, outline=cap_edge)
        self.create_oval(cx - r, body_top - 6, cx + r, body_top + 6,
                         fill=cap_fill, outline=cap_edge)
        # Cực dương (nút nổi) trên đỉnh
        self.create_oval(cx - 7, body_top - 14, cx + 7, body_top - 2,
                         fill=term_fill, outline=cap_edge)

        # Nhãn +/- cố định đúng vị trí thật trên cell 18650
        sign_fg = "#333333"
        self.create_text(cx, body_top + 15, text="+",
                          font=('Segoe UI Semibold', 12), fill=sign_fg)
        self.create_text(cx, body_bottom - 13, text="-",
                          font=('Segoe UI Semibold', 13), fill=sign_fg)

        # Điện áp giữa thân — có nền chip trắng để luôn đọc rõ bất kể phần
        # mực màu gì đang nằm phía sau (đỏ/vàng/xanh/rỗng).
        value_text = f"{self._voltage:.3f}V" if has_v else "—"
        chip_w = 7.2 * len(value_text) + 8
        cy = h / 2 + 2
        _round_rect(self, cx - chip_w / 2, cy - 10, cx + chip_w / 2, cy + 10,
                    r=6, fill="#ffffff", outline="")
        self.create_text(cx, cy, text=value_text,
                         font=('Segoe UI Semibold', 9), fill="#1c1c1c")

class StateBadge(tk.Label):
    """Nhãn dạng badge màu (pill), dùng cho trạng thái khóa BMS."""
    def __init__(self, parent, bg_default="#9a9a9a", **kwargs):
        super().__init__(parent, text="—", font=('Segoe UI Semibold', 9),
                          fg="white", bg=bg_default, padx=10, pady=3, **kwargs)

    def set_state(self, text, bg):
        self.config(text=text, bg=bg)

class SocBar(tk.Canvas):
    """Thanh % dung lượng bo góc, tự vẽ bằng Canvas (không dùng
    ttk.Progressbar) để đảm bảo màu/độ dày hiển thị đúng trên mọi theme —
    nhiều theme ttk không tôn trọng màu/thickness tùy chỉnh cho Progressbar."""
    HEIGHT = 14

    def __init__(self, parent, bg="#ffffff", **kwargs):
        super().__init__(parent, height=self.HEIGHT, highlightthickness=0, bg=bg, **kwargs)
        self._value = 0
        self._color = "#16a34a"
        self._track = "#e5e5e5"
        self.bind("<Configure>", lambda e: self._redraw())

    def set_bg(self, bg):
        self.config(bg=bg)
        self._redraw()

    def set_track_color(self, color):
        self._track = color
        self._redraw()

    def set_value(self, value, color=None):
        self._value = max(0, min(100, value))
        if color:
            self._color = color
        self._redraw()

    def _redraw(self):
        self.delete("all")
        w = self.winfo_width()
        if w <= 1:
            w = 300
        h = self.HEIGHT
        r = h / 2
        _round_rect(self, 0, 0, w, h, r=r, fill=self._track, outline="")
        fill_w = max(h, w * self._value / 100) if self._value > 0 else 0
        if fill_w > 0:
            _round_rect(self, 0, 0, fill_w, h, r=r, fill=self._color, outline="")

# --- Frame repair / unlock (kiến trúc profile theo model) ------------------
# Mỗi đời/model pin có thể khác vị trí lock + công thức/vị trí checksum. Thay vì
# hardcode, ta mô tả từng model bằng một "frame profile". Thêm model mới =
# thêm 1 profile, không sửa logic lõi. Model chưa có profile -> từ chối an toàn.
#
# Cách crack profile cho model mới: dùng "Dump raw frame" gom vài frame thật của
# model đó rồi phân tích ra vị trí lock + công thức checksum (như đã làm cho đời
# phổ biến LXT 18V bên dưới, đã validate trên frame thật).

def _get_nibble(byte_val, which):
    return (byte_val >> 4) & 0xF if which == "high" else byte_val & 0xF

def _set_nibble(byte_val, which, value):
    value &= 0xF
    if which == "high":
        return (byte_val & 0x0F) | (value << 4)
    return (byte_val & 0xF0) | value

def _sum_nibbles(frame, covers):
    """Tổng các nibble theo mô tả 'covers':
      {"bytes":[lo,hi]}          -> mọi nibble của byte lo..hi-1
      {"byte":i,"nibble":"low"}  -> 1 nibble cụ thể
    """
    total = 0
    for c in covers:
        if "bytes" in c:
            lo, hi = c["bytes"]
            for i in range(lo, hi):
                total += _get_nibble(frame[i], "high") + _get_nibble(frame[i], "low")
        else:
            total += _get_nibble(frame[c["byte"]], c["nibble"])
    return total

# Bộ "reduce" biến tổng nibble thành giá trị checksum lưu vào frame.
CHECKSUM_REDUCERS = {
    "min255_and0F": lambda total: min(total, 0xFF) & 0x0F,
}

def compute_checksum(frame, cs_spec):
    return CHECKSUM_REDUCERS[cs_spec["reduce"]](_sum_nibbles(frame, cs_spec["covers"]))

# Profile cho LXT 18V đời phổ biến (đã validate CS0/CS2 trên frame thật).
LXT18_STANDARD = {
    "name": "LXT 18V (standard)",
    "command_versions": ["", None],       # khớp với self.command_version của đời chuẩn
    "lock": {"byte": 17, "nibble": "low"},  # nibble này = 0 thì charger cho sạc
    # error byte = response[29] = MSG[19] (nằm trong vùng CS2 nên repair tính lại CS sau khi zero)
    "error_byte": 19,
    "write_prefix": [0x33, 0x0F],           # sub-header của lệnh ghi frame
    "checksums": [
        {"name": "CS0",
         "covers": [{"bytes": [0, 8]}],
         "store": {"byte": 20, "nibble": "high"},
         "reduce": "min255_and0F"},
        {"name": "CS2",
         "covers": [{"bytes": [16, 20]}, {"byte": 20, "nibble": "low"}],
         "store": {"byte": 21, "nibble": "high"},
         "reduce": "min255_and0F"},
    ],
}

# Danh sách profile. Thêm model mới bằng cách nối thêm dict vào đây.
FRAME_PROFILES = [LXT18_STANDARD]

def get_profile(command_version):
    """Chọn profile theo command_version của model. None nếu chưa hỗ trợ."""
    for p in FRAME_PROFILES:
        if command_version in p.get("command_versions", []):
            return p
    return None

def repair_frame(frame, profile, clear_error_byte=True):
    """Trả về bản sao frame đã sửa theo profile: zero lock nibble, (tùy chọn)
    zero error byte, và tính lại toàn bộ checksum. Chỉ đụng các nibble được mô tả."""
    f = bytearray(frame)
    lk = profile["lock"]
    f[lk["byte"]] = _set_nibble(f[lk["byte"]], lk["nibble"], 0)
    if clear_error_byte and profile.get("error_byte") is not None:
        f[profile["error_byte"]] = 0x00
    # Tính tất cả checksum trên frame đã zero-lock TRƯỚC, rồi mới ghi vào -> tránh
    # checksum sau đọc nhầm nibble checksum vừa ghi của checksum trước.
    computed = [(cs["store"], compute_checksum(f, cs)) for cs in profile["checksums"]]
    for st, val in computed:
        f[st["byte"]] = _set_nibble(f[st["byte"]], st["nibble"], val)
    return f

def verify_frame(frame, profile):
    """Kiểm tra frame có thỏa profile không. Trả về dict {lock_ok, checksums, all_ok}."""
    lk = profile["lock"]
    lock_ok = _get_nibble(frame[lk["byte"]], lk["nibble"]) == 0
    cs_results = {}
    for cs in profile["checksums"]:
        stored = _get_nibble(frame[cs["store"]["byte"]], cs["store"]["nibble"])
        cs_results[cs["name"]] = (stored == compute_checksum(frame, cs))
    return {"lock_ok": lock_ok, "checksums": cs_results,
            "all_ok": lock_ok and all(cs_results.values())}

# Wrapper tiện dụng cho profile chuẩn (giữ tương thích code/test cũ).
def frame_cs0(frame):
    return compute_checksum(frame, LXT18_STANDARD["checksums"][0])

def frame_cs2(frame):
    return compute_checksum(frame, LXT18_STANDARD["checksums"][1])

initial_data = {
    "Model": "",
    "Charge count*": "",
    "State": "",
    "Status code": "",
    "Pack Voltage": "",
    "Cell 1 Voltage": "",
    "Cell 2 Voltage": "",
    "Cell 3 Voltage": "",
    "Cell 4 Voltage": "",
    "Cell 5 Voltage": "",
    "Cell Voltage Difference": "",
    "Temperature Sensor 1": "",
    "Temperature Sensor 2": "",
    "ROM ID": "",
    "Manufacturing date": "",
    "Battery message": "",
    "Capacity": "",
    "Battery type": "",
    "Kết luận": "",
}

class ModuleApplication(ttk.Frame):
    def __init__(self, parent, interface_module=None, app_instance=None):
        super().__init__(parent)
        self.parent = parent
        self.interface = None
        self.interface_module = interface_module
        self.app_instance = app_instance
        self.command_version = None
        self.battery_present = False
        self.tree_items = {}  # parameter name -> Treeview item id, for O(1) updates
        self.frame_dumps = []  # các lần dump frame thô (read-only) để phân tích checksum
        # Giá trị đã đọc, dùng để đánh giá tình trạng pin (None = chưa đọc)
        self.lock_status = None
        self.error_byte = None
        self.charge_count = None
        self.voltages = None
        self.v_diff = None
        self.t_cell = None
        self.t_mosfet = None
        self.model = None
        self.mfg_date_str = None
        self.capacity_ah = None
        self._led_test_on = False
        self._action_button_colors = {}  # tk.Button -> màu nền gốc (để khôi phục khi enable)
        self.create_widgets()

    def set_interface(self, interface_instance):
        self.interface = interface_instance

    def create_widgets(self):
        label = ttk.Label(self, text=get_display_name(), font=('Segoe UI Semibold', 16))
        label.pack(anchor='w', pady=(0, 12))

        self.buttons = []
        self._action_buttons = {}
        self._action_captions = []

        # --- Nút thao tác chính: lưới 2x2 màu, giống bố cục app tham khảo ---
        actions_frame = ttk.Frame(self)
        actions_frame.pack(fill='x', pady=(0, 8))
        for col in range(2):
            actions_frame.grid_columnconfigure(col, weight=1, uniform="actions")

        action_specs = [
            (0, 0, "1. Đọc thông tin", "Model pin và đọc dữ liệu",
             "#2563eb", "#1d4ed8", self.on_read_static_click, False),
            (0, 1, "2. Cập nhật dữ liệu", "Đọc điện áp và nhiệt độ",
             "#2563eb", "#1d4ed8", self.on_read_data_click, True),
            (1, 0, "Xóa lỗi", "Đặt lại lỗi BMS",
             "#dc2626", "#b91c1c", self.on_reset_errors_click, True),
            (1, 1, "Kiểm tra LED", "Bật/tắt đèn báo dung lượng pin",
             "#16a34a", "#15803d", self.on_toggle_led_test, True),
        ]
        for row, col, text, caption, bg, active_bg, cmd, start_disabled in action_specs:
            cell = ttk.Frame(actions_frame)
            cell.grid(row=row, column=col, sticky='nsew', padx=6, pady=6)
            btn = tk.Button(cell, text=text, command=cmd, bg=bg, activebackground=active_bg,
                             fg="white", activeforeground="white", relief='flat', bd=0,
                             font=('Segoe UI Semibold', 10), padx=10, pady=8, cursor='hand2')
            btn.pack(fill='x')
            self._action_button_colors[btn] = bg
            if start_disabled:
                btn.config(state=tk.DISABLED, bg="#9a9a9a", disabledforeground="#e5e5e5")
            cap = tk.Label(cell, text=caption, font=('Segoe UI', 8), bd=0)
            cap.pack(anchor='w', pady=(4, 0))
            self._action_captions.append(cap)
            self.buttons.append(btn)
            self._action_buttons[text] = btn

        # --- Nâng cao (kỹ thuật): Dump raw frame + Frame repair + Chi tiết kỹ
        # thuật (popup), thu gọn mặc định ---
        self.advanced_expanded = False
        self.advanced_toggle = ttk.Button(self, text="▸  Nâng cao (kỹ thuật)",
                                          command=self.toggle_advanced)
        self.advanced_toggle.pack(anchor='w', pady=(0, 8))
        self.advanced_body = ttk.Frame(self)
        button_dump = ttk.Button(self.advanced_body, text="Dump raw frame",
                                 command=self.on_dump_frame_click, state=tk.DISABLED)
        button_dump.pack(side='left', padx=(0, 8))
        self.buttons.append(button_dump)
        button_repair = ttk.Button(self.advanced_body, text="Frame repair (unlock)",
                                   command=self.on_frame_repair_click, state=tk.DISABLED)
        button_repair.pack(side='left', padx=(0, 8))
        self.buttons.append(button_repair)
        details_open_btn = ttk.Button(self.advanced_body, text="Chi tiết kỹ thuật...",
                                      command=self.open_details_window)
        details_open_btn.pack(side='left')
        self._build_details_window()
        # advanced_body không pack ở đây -> mặc định thu gọn

        # --- Card "Thông số pin" ---
        self.info_card = tk.Frame(self, bd=0, highlightthickness=1)
        self.info_card.pack(fill='x', pady=(0, 12))
        self._info_inner = tk.Frame(self.info_card, bd=0)
        self._info_inner.pack(fill='both', expand=True, padx=14, pady=12)
        self._info_inner.grid_columnconfigure(1, weight=1)

        self.card_title_label = tk.Label(self._info_inner, text="Thông số pin",
                                         font=('Segoe UI Semibold', 12), bd=0)
        self.card_title_label.grid(row=0, column=0, columnspan=2, sticky='w', pady=(0, 8))

        info_rows = [
            ("Model", "card_model_val", False),
            ("Số lần sạc", "card_charge_val", False),
            ("Tình trạng", "card_state_badge", True),
            ("Ngày sản xuất", "card_mfg_val", False),
            ("Dung lượng", "card_capacity_val", False),
            ("Nhiệt độ BMS", "card_temp_val", False),
        ]
        self._info_row_widgets = []
        for i, (label_text, attr, is_badge) in enumerate(info_rows, start=1):
            name_lbl = tk.Label(self._info_inner, text=label_text, bd=0)
            name_lbl.grid(row=i, column=0, sticky='w', pady=3)
            if is_badge:
                value_widget = StateBadge(self._info_inner)
            else:
                value_widget = tk.Label(self._info_inner, text="—",
                                        font=('Segoe UI Semibold', 10), bd=0)
            value_widget.grid(row=i, column=1, sticky='e', pady=3)
            setattr(self, attr, value_widget)
            self._info_row_widgets.append((name_lbl, value_widget))

        # --- Card dãy cell + SoC ---
        self.cells_card = tk.Frame(self, bd=0, highlightthickness=1)
        self.cells_card.pack(fill='x', pady=(0, 12))
        self._cells_inner = tk.Frame(self.cells_card, bd=0)
        self._cells_inner.pack(fill='both', expand=True, padx=14, pady=12)

        self.cells_title_label = tk.Label(self._cells_inner, text="Điện áp từng cell",
                                          font=('Segoe UI Semibold', 12), bd=0)
        self.cells_title_label.pack(anchor='w', pady=(0, 8))

        self._cells_row = tk.Frame(self._cells_inner, bd=0)
        self._cells_row.pack()
        self.cell_widgets = []
        self.cell_number_labels = []
        self._cell_col_frames = []
        for i in range(5):
            col_frame = tk.Frame(self._cells_row, bd=0)
            col_frame.pack(side='left', padx=6)
            cw = BatteryCellWidget(col_frame, index=i)
            cw.pack()
            num_lbl = tk.Label(col_frame, text=str(i + 1), font=('Segoe UI', 8), bd=0)
            num_lbl.pack(pady=(2, 0))
            self.cell_widgets.append(cw)
            self.cell_number_labels.append(num_lbl)
            self._cell_col_frames.append(col_frame)

        self.pack_voltage_label = tk.Label(self._cells_inner, text="Tổng điện áp: — V",
                                           font=('Segoe UI Semibold', 10), bd=0)
        self.pack_voltage_label.pack(anchor='w', pady=(12, 0))
        self.soc_label = tk.Label(self._cells_inner, text="Tình trạng sạc: — %",
                                  font=('Segoe UI Semibold', 10), bd=0)
        self.soc_label.pack(anchor='w')

        self.soc_bar = SocBar(self._cells_inner)
        self.soc_bar.pack(fill='x', pady=(6, 8))

        self.imbalance_label = tk.Label(self._cells_inner, text="Mất cân bằng: — V", bd=0)
        self.imbalance_label.pack(anchor='w')

        # --- Hộp thông báo trạng thái tổng hợp ---
        self.status_box = tk.Frame(self, bd=0)
        self.status_box.pack(fill='x', pady=(0, 12))
        self.status_box_label = tk.Label(
            self.status_box, text="Chưa có dữ liệu — hãy đọc thông tin và dữ liệu pin.",
            anchor='w', justify='left', wraplength=520, padx=12, pady=10, bd=0)
        self.status_box_label.pack(fill='x')

        self.pack(fill='both', expand=True)

        self.insert_battery_data(initial_data)
        self.apply_theme()

    def toggle_advanced(self):
        self.advanced_expanded = not self.advanced_expanded
        if self.advanced_expanded:
            self.advanced_body.pack(fill='x', pady=(0, 12), after=self.advanced_toggle)
            self.advanced_toggle.config(text="▾  Nâng cao (kỹ thuật)")
        else:
            self.advanced_body.pack_forget()
            self.advanced_toggle.config(text="▸  Nâng cao (kỹ thuật)")

    def _build_details_window(self):
        """Dựng cửa sổ popup 'Chi tiết kỹ thuật' 1 lần duy nhất (bảng đầy đủ
        ROM ID/Battery message/... + lý do đánh giá chi tiết + Copy/Clear).
        Đóng cửa sổ (nút X) chỉ ẩn đi (withdraw) chứ không hủy, để self.tree/
        self.conclusion_label luôn tồn tại cho các hàm insert_battery_data/
        update_conclusion gọi bất kỳ lúc nào, kể cả khi popup đang đóng."""
        win = tk.Toplevel(self)
        win.title("Chi tiết kỹ thuật — Makita LXT")
        win.geometry("640x560")
        win.transient(self.winfo_toplevel())
        win.protocol("WM_DELETE_WINDOW", win.withdraw)
        self.details_window = win

        tree_frame = ttk.Frame(win, padding=(12, 12, 12, 0))
        tree_frame.pack(fill='both', expand=True)

        tree_scroll_y = ttk.Scrollbar(tree_frame, orient="vertical")
        tree_scroll_y.pack(side="right", fill="y")

        self.tree = ttk.Treeview(
            tree_frame,
            columns=("Value"),
            yscrollcommand=tree_scroll_y.set,
        )
        tree_scroll_y.config(command=self.tree.yview)

        self.tree.heading("#0", text="Parameter")
        self.tree.heading("Value", text="Value")

        # Row striping + verdict emphasis (colours applied per-theme in apply_theme)
        self.tree.tag_configure('conclusion', font=('Segoe UI Semibold', 10))

        self.tree.pack(side="left", fill='both', expand=True)

        conclusion_frame = ttk.LabelFrame(win, text="Chi tiết đánh giá tình trạng pin", padding=12)
        conclusion_frame.pack(fill='x', padx=12, pady=12)
        self.conclusion_label = ttk.Label(
            conclusion_frame,
            text="Chưa có dữ liệu — hãy đọc thông tin và dữ liệu pin.",
            justify='left', anchor='w', wraplength=600
        )
        self.conclusion_label.pack(fill='x')

        button_frame = ttk.Frame(win, padding=(12, 0, 12, 12))
        button_frame.pack(anchor='e')

        copy_button = ttk.Button(button_frame, text="Copy", command=self.copy_to_clipboard)
        copy_button.pack(side="left", padx=(0, 8))

        clear_button = ttk.Button(button_frame, text="Clear", command=self.clear_data)
        clear_button.pack(side="left")

        win.withdraw()  # ẩn ngay sau khi dựng — chỉ hiện khi bấm "Chi tiết kỹ thuật..."

    def open_details_window(self):
        self.details_window.deiconify()
        self.details_window.lift()
        self.details_window.focus_force()

    def on_toggle_led_test(self):
        """Nút 'Kiểm tra LED' dạng toggle: lần bấm 1 bật hết LED (test mode),
        lần bấm 2 tắt lại — gộp 2 thao tác LED test ON/OFF cũ thành 1 nút."""
        if not self.interface:
            tk.messagebox.showerror("Error", "No interface selected. Please select and connect an interface from the sidebar.")
            return
        if self._led_test_on:
            self.on_all_leds_off_click()
            self._led_test_on = False
            self._action_buttons["Kiểm tra LED"].config(text="Kiểm tra LED")
        else:
            self.on_all_leds_on_click()
            self._led_test_on = True
            self._action_buttons["Kiểm tra LED"].config(text="Tắt LED")

    def enable_all_buttons(self):
        """Enable all buttons (khôi phục lại màu gốc cho các nút màu chính)."""
        for button in self.buttons:
            button.config(state=tk.NORMAL)
            if button in self._action_button_colors:
                button.config(bg=self._action_button_colors[button])

    def _busy_start(self):
        """Khóa toàn bộ nút thao tác trong lúc có 1 lệnh serial đang chạy nền,
        để 2 lệnh không chồng lên nhau trên cùng 1 cổng serial."""
        for button in self.buttons:
            button.config(state=tk.DISABLED)

    def _busy_end(self):
        """Khôi phục lại đúng tập nút được phép bấm theo trạng thái hiện tại
        (đã đọc được model hay chưa)."""
        if self.battery_present:
            self.enable_all_buttons()
        else:
            read_info_btn = self._action_buttons.get("1. Đọc thông tin")
            for button in self.buttons:
                button.config(state=tk.NORMAL if button is read_info_btn else tk.DISABLED)

    def _run_async(self, work, on_success, on_error=None):
        """Chạy `work` (gọi self.interface.request(...), có thể block) trên
        1 thread nền để không treo UI, rồi áp kết quả lên state/UI qua
        `on_success`/`on_error` trên main thread khi xong. `work` không được
        đụng vào bất kỳ widget Tkinter nào — chỉ gọi network + tính toán
        thuần và trả về giá trị (hoặc raise)."""
        self._busy_start()

        def _success(result):
            self._busy_end()
            on_success(result)

        def _failure(exc):
            self._busy_end()
            if on_error:
                on_error(exc)

        run_async(self, work, _success, _failure)

    def nibble_swap(self, byte):
        upper_nibble = (byte & 0xF0) >> 4  # Extract the upper nibble and shift right by 4 bits
        lower_nibble = (byte & 0x0F) << 4  # Extract the lower nibble and shift left by 4 bits
        swapped_byte = upper_nibble | lower_nibble  # Combine the nibbles
        return swapped_byte

    def _fetch_status(self):
        """[An toàn để gọi trên background thread] Đọc frame tĩnh của pin
        (byte lỗi, trạng thái khóa, số lần sạc...) và parse thành dict thuần —
        không đụng Tkinter. Ném ngoại lệ để nơi gọi xử lý; áp kết quả bằng
        _apply_status trên main thread."""
        response = self.interface.request(READ_MSG_CMD)
        rom_id = ' '.join(f'{byte:02X}' for byte in response[2:10])
        raw_msg = ' '.join(f'{byte:02X}' for byte in response[10:42])
        swapped_bytes = bytearray([self.nibble_swap(response[37]), self.nibble_swap(response[36])])[::-1]
        charge_count = int.from_bytes(swapped_bytes, byteorder='big') & 0x0FFF
        lock_nibble = response[27] & 0x0F  # frame[17], khớp LXT18_STANDARD["lock"] (đã validate trên frame thật)
        error_byte = response[29]
        lock_status = "LOCKED" if lock_nibble > 0 else "UNLOCKED"
        data = {"ROM ID": rom_id,
                "Battery message": raw_msg,
                "Charge count*": charge_count,
                "State": lock_status,
                "Status code": f'{error_byte:02X}',
                "Manufacturing date": f'{response[4]:02}/{response[3]:02}/20{response[2]:02}',
                "Capacity": f'{self.nibble_swap(response[26])/10}Ah',
                "Battery type": self.nibble_swap(response[21]),
        }
        history_log.append("makita_lxt", "status", dict(data))
        return {
            "data": data,
            "lock_status": lock_status,
            "error_byte": error_byte,
            "charge_count": charge_count,
            "mfg_date_str": data["Manufacturing date"],
            "capacity_ah": self.nibble_swap(response[26]) / 10,
        }

    def _apply_status(self, status):
        """[Chỉ gọi trên main thread] Áp kết quả _fetch_status vào state + UI."""
        self.insert_battery_data(status["data"])
        self.battery_present = True
        self.lock_status = status["lock_status"]
        self.error_byte = status["error_byte"]
        self.charge_count = status["charge_count"]
        self.mfg_date_str = status["mfg_date_str"]
        self.capacity_ah = status["capacity_ah"]
        self.update_conclusion()

    def on_read_static_click(self):
        if not self.interface:
            tk.messagebox.showerror("Error", "No interface selected. Please select and connect an interface from the sidebar.")
            return

        def work():
            status = self._fetch_status()
            last_exception = None
            # Thử lần lượt từng model spec đã đăng ký (MODEL_SPECS) — thêm
            # model mới không cần sửa hàm này, chỉ cần thêm entry vào đó.
            for spec in MODEL_SPECS:
                try:
                    model = spec["probe"](self.interface)
                    return status, model, spec, None
                except Exception as e:
                    last_exception = e
            return status, None, None, last_exception

        def on_success(result):
            status, model, spec, last_exception = result
            # Áp status trước — dữ liệu tĩnh đã đọc được vẫn hiển thị dù model
            # dưới đây không nhận dạng được (khớp hành vi trước khi refactor).
            self._apply_status(status)

            if model is None:
                tk.messagebox.showerror(
                    "Unsupported Battery",
                    f"Battery is present but the model is not supported.\n\nLast error: {last_exception}")
                return

            self.model = model
            self.command_version = spec["command_version"]
            self.insert_battery_data({"Model": model})
            if spec["limited"]:
                self._action_buttons["2. Cập nhật dữ liệu"].config(state=tk.NORMAL)
                messagebox.showwarning("Limited", "This model only supports diagnostics")
            else:
                self.enable_all_buttons()
            self.update_pretty_card()

        def on_error(exc):
            if isinstance(exc, ConnectionError):
                tk.messagebox.showerror("Connection Error", f"Could not communicate with the battery:\n\n{exc}")
            elif isinstance(exc, (IndexError, ValueError)):
                tk.messagebox.showerror("Data Error", f"Received an unexpected response while reading battery info:\n\n{type(exc).__name__}: {exc}")
            else:
                tk.messagebox.showerror("Error", f"Failed to read battery static data:\n\n{type(exc).__name__}: {exc}")

        self._run_async(work, on_success, on_error)

    def on_read_data_click(self):
        if not self.interface:
            tk.messagebox.showerror("Error", "No interface selected. Please select and connect an interface from the sidebar.")
            return

        def work():
            spec = get_model_spec(self.command_version)
            if spec is None:
                raise RuntimeError(f"No model spec registered for command_version={self.command_version!r}")
            result = spec["read_data"](self.interface)
            history_log.append("makita_lxt", "data", dict(result[0]))
            return result

        def on_success(result):
            battery_data, voltages, v_diff, t_cell, t_mosfet = result
            self.insert_battery_data(battery_data)
            self.voltages = voltages
            self.v_diff = v_diff
            self.t_cell = t_cell
            self.t_mosfet = t_mosfet
            self.update_conclusion()

        def on_error(exc):
            if isinstance(exc, ConnectionError):
                tk.messagebox.showerror("Connection Error", f"Lost communication while reading battery data:\n\n{exc}")
            elif isinstance(exc, (IndexError, ValueError)):
                tk.messagebox.showerror("Data Error", f"Received an unexpected response while reading battery data:\n\n{type(exc).__name__}: {exc}")
            else:
                tk.messagebox.showerror("Error", f"Failed to read battery data:\n\n{type(exc).__name__}: {exc}")

        self._run_async(work, on_success, on_error)

    def on_dump_frame_click(self):
        """READ-ONLY: đọc frame thô của pin và lưu lại để phân tích checksum.
        KHÔNG ghi gì vào pin. Dùng để thu thập nhiều mẫu frame từ các pin khác nhau."""
        if not self.interface:
            tk.messagebox.showerror("Error", "No interface selected. Please select and connect an interface from the sidebar.")
            return

        def work():
            response = self.interface.request(READ_MSG_CMD)
            if len(response) < 42:
                raise ValueError(f"Frame quá ngắn ({len(response)} byte), cần 42.")
            raw = ' '.join(f'{b:02X}' for b in response)
            rom = ' '.join(f'{b:02X}' for b in response[2:10])
            msg = ' '.join(f'{b:02X}' for b in response[10:42])
            history_log.append("makita_lxt", "frame_dump", {
                "raw": raw, "rom": rom, "msg": msg,
                "error_byte": f"{response[29]:02X}",
                "lock_byte": f"{response[27]:02X}",
                "last_byte": f"{response[41]:02X}",
            })
            return len(response), raw, rom, msg, response[29], response[27], response[41]

        def on_success(result):
            resp_len, raw, rom, msg, error_byte, lock_byte, last_byte = result
            n = len(self.frame_dumps) + 1
            dump = (f"=== FRAME DUMP #{n} ===\n"
                    f"RAW ({resp_len}B): {raw}\n"
                    f"ROM  (8B): {rom}\n"
                    f"MSG (32B): {msg}\n"
                    f"  error(byte29)=0x{error_byte:02X}  "
                    f"lock(byte27)=0x{lock_byte:02X}  last=0x{last_byte:02X}")
            self.frame_dumps.append(dump)
            self.app_instance.update_debug(dump)

            # Copy toàn bộ các dump vào clipboard để dễ gửi đi phân tích
            all_dumps = "\n\n".join(self.frame_dumps)
            self.parent.clipboard_clear()
            self.parent.clipboard_append(all_dumps)

            tk.messagebox.showinfo(
                "Dump raw frame",
                f"Đã dump frame #{n} (READ-ONLY, không ghi gì vào pin).\n\n"
                f"Đã copy toàn bộ {n} frame vào clipboard.\n\n"
                "Hãy đọc thêm vài pin KHÁC NHAU (nhấn nút này với từng pin), "
                "rồi dán clipboard gửi lại để phân tích checksum."
            )

        def on_error(exc):
            if isinstance(exc, ConnectionError):
                tk.messagebox.showerror("Connection Error", f"Could not read frame:\n\n{exc}")
            elif isinstance(exc, ValueError):
                tk.messagebox.showerror("Data Error", str(exc))
            else:
                tk.messagebox.showerror("Error", f"Failed to dump frame:\n\n{type(exc).__name__}: {exc}")

        self._run_async(work, on_success, on_error)

    def on_all_leds_on_click(self):
        if not self.interface:
            tk.messagebox.showerror("Error", "No interface selected. Please select and connect an interface from the sidebar.")
            return

        def work():
            self.interface.request(TESTMODE_CMD)
            self.interface.request(LEDS_ON_CMD)

        def on_error(exc):
            if isinstance(exc, ConnectionError):
                tk.messagebox.showerror("Connection Error", f"Lost communication while turning LEDs on:\n\n{exc}")
            else:
                tk.messagebox.showerror("Error", f"Failed to turn LEDs on:\n\n{type(exc).__name__}: {exc}")

        self._run_async(work, lambda _result: None, on_error)

    def on_all_leds_off_click(self):
        if not self.interface:
            tk.messagebox.showerror("Error", "No interface selected. Please select and connect an interface from the sidebar.")
            return

        def work():
            spec = get_model_spec(self.command_version) or MODEL_SPECS[0]
            self.interface.request(spec["led_off_cmd"])
            self.interface.request(LEDS_OFF_CMD)

        def on_error(exc):
            if isinstance(exc, ConnectionError):
                tk.messagebox.showerror("Connection Error", f"Lost communication while turning LEDs off:\n\n{exc}")
            else:
                tk.messagebox.showerror("Error", f"Failed to turn LEDs off:\n\n{type(exc).__name__}: {exc}")

        self._run_async(work, lambda _result: None, on_error)

    def on_reset_errors_click(self):
        if not self.interface:
            tk.messagebox.showerror("Error", "No interface selected. Please select and connect an interface from the sidebar.")
            return

        def work():
            self.interface.request(TESTMODE_CMD)
            self.interface.request(RESET_ERROR_CMD)
            # Đọc lại ngay để thấy byte lỗi đã về 0x00 hay chưa
            return self._fetch_status()

        def on_success(status):
            self._apply_status(status)
            if self.error_byte:
                tk.messagebox.showinfo(
                    "Clear errors",
                    f"Đã gửi lệnh xóa nhưng error flags vẫn còn 0x{self.error_byte:02X}.\n\n"
                    "Nhiều khả năng đây là lỗi đang active (điều kiện lỗi vẫn tồn tại)."
                )
            else:
                tk.messagebox.showinfo("Clear errors", "Đã xóa lỗi thành công — error flags về 0x00.")

        def on_error(exc):
            if isinstance(exc, ConnectionError):
                tk.messagebox.showerror("Connection Error", f"Lost communication while resetting errors:\n\n{exc}")
            elif isinstance(exc, (IndexError, ValueError)):
                tk.messagebox.showerror("Data Error", f"Received an unexpected response while re-reading after clear:\n\n{type(exc).__name__}: {exc}")
            else:
                tk.messagebox.showerror("Error", f"Failed to reset errors:\n\n{type(exc).__name__}: {exc}")

        self._run_async(work, on_success, on_error)

    def _build_write_frame_cmd(self, frame, profile):
        """Dựng lệnh ghi 1 frame 32 byte về BMS.
        Cấu trúc: [0x01, len, rsp_len=0, cmd=0x33] + write_prefix + <32 byte frame>.
        Với profile chuẩn: prefix = [0x33, 0x0F], len = 2 + 32 = 34 (0x22)."""
        data = list(profile.get("write_prefix", [0x33, 0x0F])) + list(frame)
        return [0x01, len(data), 0x00, 0x33] + data

    def on_frame_repair_click(self):
        """CLEAR ALL ERRORS / UNLOCK bằng frame repair: đọc frame -> zero lock nibble
        + error byte -> tính lại CS0/CS2 -> ghi + STORE -> đọc lại verify.
        GHI VĨNH VIỄN vào BMS.

        Đã kiểm chứng trên phần cứng thật (không còn là "chưa test"):
        write sequence được BMS chấp nhận, checksum đúng, và lock nibble
        ghi 0 giữ được bền qua nhiều lần đọc sau đó. NHƯNG error byte KHÔNG
        giữ được (BMS tự tính lại live, xem ERROR_FLAG_MEANINGS ở trên) —
        đừng kỳ vọng nút này "sửa" được error byte, chỉ đáng tin cho việc
        lật lock nibble. Case lật 1 pin đang thực sự LOCKED (không phải đã
        sẵn unlocked) thì vẫn CHƯA được kiểm chứng thực nghiệm. Chi tiết:
        docs/makita-lxt-frame-notes.md."""
        if not self.interface:
            tk.messagebox.showerror("Error", "No interface selected. Please select and connect an interface from the sidebar.")
            return

        profile = get_profile(self.command_version)
        if profile is None:
            tk.messagebox.showwarning(
                "Chưa hỗ trợ",
                "Model pin này chưa có profile frame-repair.\n\n"
                "Hãy dùng \"Dump raw frame\" gom vài frame của model này để bổ sung profile.")
            return

        if not tk.messagebox.askyesno(
            "Frame repair — GHI VĨNH VIỄN",
            "Thao tác này GHI ĐÈ vào bộ nhớ BMS và KHÔNG THỂ HOÀN TÁC.\n\n"
            "• Chỉ nên chạy trên pin bạn CHẤP NHẬN RỦI RO hỏng.\n"
            "• Phần ghi frame chưa được kiểm chứng trên phần cứng.\n"
            "• Nếu cell hỏng thật, pin có thể tự khóa lại.\n\n"
            "Tiếp tục?",
            icon='warning', default='no'
        ):
            return

        def work():
            # 1. Đọc frame hiện tại
            response = self.interface.request(READ_MSG_CMD)
            if len(response) < 42:
                raise ValueError(f"Frame quá ngắn ({len(response)} byte), cần 42.")
            frame = bytearray(response[10:42])
            lk = profile["lock"]
            before = verify_frame(frame, profile)
            self.app_instance.update_debug(
                f"[Frame repair] profile={profile['name']} trước: "
                f"lock={_get_nibble(frame[lk['byte']], lk['nibble'])} "
                f"{ {k: ('OK' if v else 'SAI') for k, v in before['checksums'].items()} }")

            # 2. Sửa frame theo profile (chỉ đụng lock nibble, error byte, checksum)
            repaired = repair_frame(frame, profile, clear_error_byte=True)

            # 3. Ghi: testmode -> charger -> write frame -> store
            self.interface.request(TESTMODE_CMD)
            self.interface.request(CHARGER_CMD)
            self.interface.request(self._build_write_frame_cmd(repaired, profile))
            self.interface.request(STORE_CMD)

            # 4. Đọc lại và verify theo profile
            verify = self.interface.request(READ_MSG_CMD)
            if len(verify) < 42:
                raise ValueError(f"Verify frame quá ngắn ({len(verify)} byte).")
            vf = bytearray(verify[10:42])
            result = verify_frame(vf, profile)
            cs_txt = " ".join(f"{k}={'OK' if v else 'SAI'}" for k, v in result["checksums"].items())
            self.app_instance.update_debug(
                f"[Frame repair] sau: lock={_get_nibble(vf[lk['byte']], lk['nibble'])} {cs_txt}")

            # Ghi lại nhật ký GHI VĨNH VIỄN này ra file — thao tác duy nhất
            # trong app đụng vào EEPROM của BMS, nên cần dấu vết before/after
            # riêng để đối chiếu nếu có sự cố sau này.
            history_log.append("makita_lxt", "frame_repair", {
                "profile": profile["name"],
                "before_lock": _get_nibble(frame[lk["byte"]], lk["nibble"]),
                "before_checksums": before["checksums"],
                "after_lock": _get_nibble(vf[lk["byte"]], lk["nibble"]),
                "after_checksums": result["checksums"],
                "all_ok": result["all_ok"],
            })

            # Đọc lại status đầy đủ để áp lên bảng + kết luận trên main thread
            status = self._fetch_status()
            return status, result, cs_txt

        def on_success(payload):
            status, result, cs_txt = payload
            # Cập nhật bảng + kết luận theo dữ liệu mới
            self._apply_status(status)

            if result["all_ok"]:
                tk.messagebox.showinfo(
                    "Frame repair — THÀNH CÔNG",
                    "Lock nibble = 0 và toàn bộ checksum hợp lệ.\n\n"
                    "Pin đã thỏa điều kiện charger — nên sạc lại được. "
                    "Hãy thử cắm sạc để xác nhận thực tế.")
            else:
                lock_txt = "0 (OK)" if result["lock_ok"] else "VẪN KHÁC 0"
                tk.messagebox.showwarning(
                    "Frame repair — CHƯA XÁC NHẬN",
                    f"Sau khi ghi:\n"
                    f"  lock nibble = {lock_txt}\n  {cs_txt}\n\n"
                    "BMS có thể không chấp nhận ghi (pin có bảo mật, MCU đời cũ, "
                    "hoặc lệnh ghi chưa đúng với model này).")

        def on_error(exc):
            if isinstance(exc, ConnectionError):
                tk.messagebox.showerror("Connection Error", f"Lost communication during frame repair:\n\n{exc}")
            elif isinstance(exc, (IndexError, ValueError)):
                tk.messagebox.showerror("Data Error", f"Unexpected response during frame repair:\n\n{type(exc).__name__}: {exc}")
            else:
                tk.messagebox.showerror("Error", f"Frame repair failed:\n\n{type(exc).__name__}: {exc}")

        self._run_async(work, on_success, on_error)

    def evaluate_condition(self):
        """Đánh giá tình trạng pin từ dữ liệu đã đọc.

        Trả về (verdict, emoji, level, reasons) — level là 'good'/'warn'/'bad'/'none'
        (màu tra trong VERDICT_COLORS theo theme). Kết luận tổng hợp từ trạng thái
        khóa BMS, mã lỗi, điện áp/cân bằng cell, nhiệt độ và số lần sạc.
        Chỉ dùng dữ liệu hiện có; đọc càng nhiều thì kết luận càng đầy đủ.
        """
        reasons = []
        problems = 0
        warnings = 0

        have_static = self.lock_status is not None
        have_cells = self.voltages is not None

        if not have_static and not have_cells:
            return ("Chưa có dữ liệu", "⚪", "none",
                    ["Hãy bấm \"Read battery model\" và \"Read battery data\" trước."])

        # --- Khóa BMS ---
        if self.lock_status == "LOCKED":
            problems += 1
            reasons.append("🔴 BMS đang KHÓA — pin tự khóa do phát hiện lỗi.")
        elif self.lock_status == "UNLOCKED":
            reasons.append("🟢 BMS: UNLOCKED — không bị khóa.")

        # --- Error flags (byte 29, bitfield) ---
        # BMS đã khóa + có cờ lỗi = lỗi nghiêm trọng (🔴). Nếu chưa khóa thì cờ lỗi
        # nhiều khả năng là lịch sử nên chỉ cảnh báo (🟡).
        if self.error_byte is not None:
            if self.error_byte != 0:
                set_bits = [b for b in range(8) if self.error_byte & (1 << b)]
                if self.lock_status == "LOCKED":
                    problems += 1
                    reasons.append(f"🔴 Error flags 0x{self.error_byte:02X} (0b{self.error_byte:08b}) "
                                   f"— {len(set_bits)} cờ đang bật, BMS đã KHÓA:")
                else:
                    warnings += 1
                    reasons.append(f"🟡 Error flags 0x{self.error_byte:02X} (0b{self.error_byte:08b}) "
                                   f"— {len(set_bits)} cờ đang bật (BMS chưa khóa → nhiều khả năng là cờ lịch sử):")
                for b in set_bits:
                    meaning = ERROR_FLAG_MEANINGS.get(b, "chưa rõ ý nghĩa")
                    reasons.append(f"       • bit {b} (0x{1 << b:02X}) — {meaning}")
                reasons.append("       ℹ️ Bấm \"Clear errors\" rồi đọc lại: về 0x00 = lỗi lịch sử; "
                               "vẫn còn = lỗi đang active.")
            else:
                reasons.append("🟢 Error flags: 0x00 — không có lỗi ghi nhận.")

        # --- Điện áp & cân bằng cell ---
        if have_cells:
            crit_cells = [i + 1 for i, v in enumerate(self.voltages) if 0 < v < CELL_CRITICAL]
            low_cells = [i + 1 for i, v in enumerate(self.voltages)
                         if CELL_CRITICAL <= v < CELL_LOW]
            over_cells = [i + 1 for i, v in enumerate(self.voltages) if v > CELL_OVER]

            if crit_cells:
                problems += 1
                reasons.append(f"🔴 Cell {crit_cells} dưới {CELL_CRITICAL}V — nguy hiểm, "
                               f"có thể đã hỏng; cân nhắc KHÔNG sạc lại.")
            if low_cells:
                warnings += 1
                reasons.append(f"🟡 Cell {low_cells} thấp (<{CELL_LOW}V) — cần sạc.")
            if over_cells:
                problems += 1
                reasons.append(f"🔴 Cell {over_cells} trên {CELL_OVER}V — quá áp.")

            v_diff = self.v_diff if self.v_diff is not None else round(max(self.voltages) - min(self.voltages), 3)
            if v_diff > DIFF_SEVERE:
                problems += 1
                reasons.append(f"🔴 Lệch cell {v_diff:.2f}V — mất cân bằng nặng, "
                               f"nhiều khả năng có cell chai/hỏng.")
            elif v_diff > DIFF_WARN:
                warnings += 1
                reasons.append(f"🟡 Lệch cell {v_diff:.2f}V — mất cân bằng, cell bắt đầu yếu.")
            else:
                reasons.append(f"🟢 Lệch cell {v_diff:.2f}V — cân bằng tốt.")

        # --- Nhiệt độ (đọc ở trạng thái nghỉ) ---
        try:
            if self.t_cell not in (None, "") and float(self.t_cell) >= TEMP_HOT:
                warnings += 1
                reasons.append(f"🟡 Nhiệt độ {self.t_cell}°C — cao bất thường khi nghỉ.")
        except (TypeError, ValueError):
            pass

        # --- Số lần sạc (thông tin, không đổi verdict) ---
        try:
            if self.charge_count not in (None, "") and int(self.charge_count) >= CYCLE_HIGH:
                reasons.append(f"ℹ️ Số lần sạc* ~{self.charge_count} — pin đã dùng nhiều, "
                               f"dung lượng có thể suy giảm.")
        except (TypeError, ValueError):
            pass

        if problems:
            return ("CÓ VẤN ĐỀ", "🔴", "bad", reasons)
        if warnings:
            return ("CẦN CHÚ Ý", "🟡", "warn", reasons)
        return ("TỐT", "🟢", "good", reasons)

    def _verdict_color(self, level):
        """Màu verdict phù hợp theme hiện tại."""
        dark = sv_ttk.get_theme() == "dark"
        return VERDICT_COLORS.get(level, VERDICT_COLORS['none'])[1 if dark else 0]

    def update_conclusion(self):
        """Chạy đánh giá và cập nhật dòng 'Kết luận' + khu chi tiết."""
        verdict, emoji, level, reasons = self.evaluate_condition()
        # Khi chưa có dữ liệu để dòng trong bảng trống cho gọn; chi tiết hiện ở label
        row_text = "" if level == 'none' else f"{emoji} {verdict}"
        self.insert_battery_data({"Kết luận": row_text})
        item_id = self.tree_items.get("Kết luận")
        if item_id:
            self.tree.tag_configure('conclusion', foreground=self._verdict_color(level))
            self.tree.item(item_id, tags=('conclusion',))
        if hasattr(self, 'conclusion_label'):
            self.conclusion_label.config(text="\n".join(reasons))
        self.update_pretty_card()

    def update_pretty_card(self):
        """Đồng bộ view trực quan (thông số pin, ô cell, thanh SoC, badge
        trạng thái, hộp thông báo) từ dữ liệu đã đọc. Gọi sau mỗi lần dữ liệu
        thay đổi (đọc mới, xóa lỗi, frame repair, clear, đổi theme)."""
        if not hasattr(self, 'card_model_val'):
            return  # widget chưa dựng xong

        dark = sv_ttk.get_theme() == "dark"

        self.card_model_val.config(text=self.model or "—")
        self.card_charge_val.config(text=str(self.charge_count) if self.charge_count is not None else "—")
        self.card_mfg_val.config(text=self.mfg_date_str or "—")
        self.card_capacity_val.config(text=f"{self.capacity_ah}Ah" if self.capacity_ah is not None else "—")
        self.card_temp_val.config(text=f"{self.t_cell} °C" if self.t_cell not in (None, "") else "—")

        if self.lock_status == "LOCKED":
            self.card_state_badge.set_state("ĐÃ KHÓA", VERDICT_COLORS['bad'][1 if dark else 0])
        elif self.lock_status == "UNLOCKED":
            self.card_state_badge.set_state("ĐÃ MỞ KHÓA", VERDICT_COLORS['good'][1 if dark else 0])
        else:
            self.card_state_badge.set_state("—", "#9a9a9a")

        if self.voltages:
            for i, cw in enumerate(self.cell_widgets):
                cw.set_voltage(self.voltages[i])
            pack_v = sum(self.voltages)
            avg_v = pack_v / len(self.voltages)
            soc = estimate_soc(avg_v)
            self.pack_voltage_label.config(text=f"Tổng điện áp: {pack_v:.3f} V")
            self.soc_label.config(text=f"Tình trạng sạc: {soc}%")
            soc_color = "#16a34a" if soc >= 50 else ("#c2740c" if soc >= 20 else "#dc2626")
            self.soc_bar.set_value(soc, color=soc_color)

            v_diff = self.v_diff if self.v_diff is not None else 0
            if v_diff > DIFF_SEVERE:
                diff_fg = VERDICT_COLORS['bad'][1 if dark else 0]
            elif v_diff > DIFF_WARN:
                diff_fg = VERDICT_COLORS['warn'][1 if dark else 0]
            else:
                diff_fg = VERDICT_COLORS['good'][1 if dark else 0]
            self.imbalance_label.config(text=f"Mất cân bằng: {v_diff:.3f} V", fg=diff_fg)
        else:
            for cw in self.cell_widgets:
                cw.set_voltage(None)
            self.pack_voltage_label.config(text="Tổng điện áp: — V")
            self.soc_label.config(text="Tình trạng sạc: — %")
            self.soc_bar.set_value(0)
            self.imbalance_label.config(text="Mất cân bằng: — V",
                                        fg=VERDICT_COLORS['none'][1 if dark else 0])

        verdict, emoji, level, reasons = self.evaluate_condition()
        if level == 'good':
            msg = "Tất cả các thông số đều bình thường."
        elif level == 'none':
            msg = "Chưa có dữ liệu — hãy đọc thông tin và dữ liệu pin."
        else:
            first = reasons[0] if reasons else verdict
            msg = f"{emoji} {verdict} — {first}"
        colors = STATUS_BOX_COLORS.get(level, STATUS_BOX_COLORS['none'])
        bg, fg = colors['dark'] if dark else colors['light']
        self.status_box.config(bg=bg)
        self.status_box_label.config(text=msg, bg=bg, fg=fg)

    def apply_theme(self):
        """Cập nhật màu bảng/card/badge/cell theo theme sáng/tối hiện tại."""
        dark = sv_ttk.get_theme() == "dark"
        app_bg = "#1c1c1c" if dark else "#fbfbfb"
        card_bg = "#2b2b2b" if dark else "#f3f3f3"
        border_col = "#3a3a3a" if dark else "#e0e0e0"
        text_fg = "#e0e0e0" if dark else "#202020"
        muted_fg = VERDICT_COLORS['none'][1 if dark else 0]

        if dark:
            self.tree.tag_configure('evenrow', background="#2b2b2b")
            self.tree.tag_configure('oddrow', background="#1f1f1f")
        else:
            self.tree.tag_configure('evenrow', background="#f3f3f3")
            self.tree.tag_configure('oddrow', background="#ffffff")

        for frame in (self.info_card, self.cells_card):
            frame.config(bg=card_bg, highlightbackground=border_col, highlightcolor=border_col)
        for frame in (self._info_inner, self._cells_inner):
            frame.config(bg=card_bg)

        self.card_title_label.config(bg=card_bg, fg=text_fg)
        self.cells_title_label.config(bg=card_bg, fg=text_fg)

        for name_lbl, value_widget in self._info_row_widgets:
            name_lbl.config(bg=card_bg, fg=muted_fg)
            if not isinstance(value_widget, StateBadge):
                value_widget.config(bg=card_bg, fg=text_fg)

        self._cells_row.config(bg=card_bg)
        for cf in self._cell_col_frames:
            cf.config(bg=card_bg)
        for cw in self.cell_widgets:
            cw.set_bg(card_bg)
        for num_lbl in self.cell_number_labels:
            num_lbl.config(bg=card_bg, fg=muted_fg)

        self.pack_voltage_label.config(bg=card_bg, fg=text_fg)
        self.soc_label.config(bg=card_bg, fg=text_fg)
        self.imbalance_label.config(bg=card_bg)
        self.soc_bar.set_bg(card_bg)
        self.soc_bar.set_track_color("#3a3a3a" if dark else "#e5e5e5")

        for cap in self._action_captions:
            cap.config(bg=app_bg, fg=muted_fg)

        # Cập nhật lại màu chữ verdict + card/badge/status box theo dữ liệu hiện có
        self.update_conclusion()

    def insert_battery_data(self, data):
        for parameter, value in data.items():
            item_id = self.tree_items.get(parameter)
            if item_id and self.tree.exists(item_id):
                self.tree.item(item_id, values=(value,))
            else:
                tag = 'evenrow' if len(self.tree_items) % 2 == 0 else 'oddrow'
                item_id = self.tree.insert("", "end", text=parameter, values=(value,), tags=(tag,))
                self.tree_items[parameter] = item_id

    def copy_to_clipboard(self):
        selected_items = self.tree.selection()
        if not selected_items:
            messagebox.showwarning("No Selection", "No rows selected to copy!")
            return

        rows = []
        for item in selected_items:
            values = self.tree.item(item, 'values')
            row_text = '\t'.join(values)
            rows.append(row_text)

        self.parent.clipboard_clear()
        self.parent.clipboard_append('\n'.join(rows))
        messagebox.showinfo("Copied", "Selected rows have been copied to the clipboard.")

    def clear_data(self):
        self.lock_status = None
        self.error_byte = None
        self.charge_count = None
        self.voltages = None
        self.v_diff = None
        self.t_cell = None
        self.t_mosfet = None
        self.model = None
        self.mfg_date_str = None
        self.capacity_ah = None
        self.insert_battery_data(initial_data)
        item_id = self.tree_items.get("Kết luận")
        if item_id:
            self.tree.item(item_id, tags=('oddrow',))
        if hasattr(self, 'conclusion_label'):
            self.conclusion_label.config(text="Chưa có dữ liệu — hãy đọc thông tin và dữ liệu pin.")
        self.update_pretty_card()