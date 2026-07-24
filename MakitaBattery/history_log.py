import datetime
import json
import os
import sys


def _log_dir():
    """Ghi cạnh file .exe khi đã đóng gói (không ghi vào thư mục tạm _MEIPASS,
    thứ sẽ bị xóa khi thoát app), hoặc cạnh main.py khi chạy dev."""
    base = os.path.dirname(sys.executable) if hasattr(sys, "_MEIPASS") else os.path.abspath(".")
    path = os.path.join(base, "logs")
    os.makedirs(path, exist_ok=True)
    return path


def append(module_name, kind, fields):
    """Ghi thêm 1 dòng JSON vào logs/<module_name>_history.jsonl: timestamp +
    loại bản ghi (status/data/frame_dump/frame_repair) + các field đã đọc
    được. Mỗi lần đọc/thao tác một dòng, để xem lại lịch sử qua nhiều lần
    kiểm tra hoặc so sánh khi debug các byte "nhiễu" (xem
    docs/makita-lxt-frame-notes.md).

    Best-effort — không bao giờ raise ra ngoài: ghi log không được phép làm
    hỏng luồng đọc/sửa pin chính (vd. thư mục chỉ-đọc, đĩa đầy...).
    """
    record = {
        "timestamp": datetime.datetime.now().isoformat(timespec="seconds"),
        "kind": kind,
        **fields,
    }
    path = os.path.join(_log_dir(), f"{module_name}_history.jsonl")
    try:
        with open(path, "a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
    except OSError:
        pass
