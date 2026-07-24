"""Unit tests cho phần checksum/repair/verify của Makita LXT (modules/makita_lxt.py).

Đây là logic ghi VĨNH VIỄN vào BMS thật khi chạy qua UI (Frame repair), nên
được test tách biệt phần cứng. Frame dùng trong test là dữ liệu tự tạo (không
phải dump thật) — mục tiêu là bắt regression trong công thức checksum/nibble
packing, không phải xác nhận hành vi của BMS thật.
"""

from modules.makita_lxt import (
    LXT18_STANDARD,
    MODEL_SPECS,
    compute_checksum,
    estimate_soc,
    frame_cs0,
    frame_cs2,
    get_model_spec,
    get_profile,
    repair_frame,
    verify_frame,
)


def _set_nibble(byte_val, which, value):
    value &= 0xF
    if which == "high":
        return (byte_val & 0x0F) | (value << 4)
    return (byte_val & 0xF0) | value


def _sample_frame():
    """Frame 32-byte tự tạo, với checksum CS0/CS2 tính đúng và lock nibble != 0
    (mô phỏng 1 pin đang LOCKED) — dùng làm điểm khởi đầu cho các test dưới."""
    frame = bytearray(range(32))
    frame[17] = 0x35  # lock nibble (thấp) = 5 -> khác 0 -> LOCKED
    for cs in LXT18_STANDARD["checksums"]:
        val = compute_checksum(frame, cs)
        st = cs["store"]
        frame[st["byte"]] = _set_nibble(frame[st["byte"]], st["nibble"], val)
    return frame


def test_verify_frame_accepts_correct_checksums_but_reports_locked():
    frame = _sample_frame()
    result = verify_frame(frame, LXT18_STANDARD)
    assert result["checksums"] == {"CS0": True, "CS2": True}
    assert result["lock_ok"] is False
    assert result["all_ok"] is False


def test_verify_frame_detects_corrupted_checksum():
    frame = _sample_frame()
    frame[3] ^= 0xFF  # byte trong vùng phủ CS0 (bytes[0:8])
    result = verify_frame(frame, LXT18_STANDARD)
    assert result["checksums"]["CS0"] is False


def test_repair_frame_unlocks_and_fixes_checksums():
    frame = _sample_frame()
    assert frame[17] & 0x0F != 0  # locked trước khi repair

    repaired = repair_frame(frame, LXT18_STANDARD, clear_error_byte=True)

    result = verify_frame(repaired, LXT18_STANDARD)
    assert result["all_ok"] is True
    assert repaired[17] & 0x0F == 0
    assert repaired[LXT18_STANDARD["error_byte"]] == 0x00


def test_repair_frame_only_touches_expected_bytes():
    """repair_frame chỉ được đụng: lock nibble, error byte, và 2 byte lưu checksum —
    mọi byte khác (model/mfg/ROM...) phải giữ nguyên."""
    frame = _sample_frame()
    original = bytearray(frame)
    repaired = repair_frame(frame, LXT18_STANDARD, clear_error_byte=True)

    touched_bytes = {LXT18_STANDARD["lock"]["byte"], LXT18_STANDARD["error_byte"]}
    touched_bytes.update(cs["store"]["byte"] for cs in LXT18_STANDARD["checksums"])

    for i in range(32):
        if i not in touched_bytes:
            assert repaired[i] == original[i], f"byte {i} bị đổi ngoài dự kiến"


def test_frame_cs0_cs2_wrappers_match_compute_checksum():
    frame = _sample_frame()
    assert frame_cs0(frame) == compute_checksum(frame, LXT18_STANDARD["checksums"][0])
    assert frame_cs2(frame) == compute_checksum(frame, LXT18_STANDARD["checksums"][1])


def test_get_profile_standard_and_unknown():
    assert get_profile("") is LXT18_STANDARD
    assert get_profile(None) is LXT18_STANDARD
    assert get_profile("some-unknown-version") is None


def test_get_model_spec_standard_and_f0513():
    standard = get_model_spec("")
    f0513 = get_model_spec("F0513")

    assert standard is not None and standard["limited"] is False
    assert f0513 is not None and f0513["limited"] is True
    assert get_model_spec("unknown") is None
    assert MODEL_SPECS[0] is standard  # đời chuẩn được thử probe trước


def test_estimate_soc_boundaries_and_monotonic():
    assert estimate_soc(4.30) == 100   # trên đỉnh bảng OCV -> kẹp 100
    assert estimate_soc(3.00) == 0     # dưới đáy bảng OCV -> kẹp 0
    assert estimate_soc(4.20) == 100
    mid = estimate_soc(3.85)
    assert 0 < mid < 100               # điểm giữa bảng -> nội suy hợp lý
    assert estimate_soc(4.10) > estimate_soc(3.90)  # đơn điệu tăng theo điện áp
