// frame_repair.h — Makita LXT frame repair / unlock (port từ bản Python đã validate)
//
// Dùng cho firmware ESP32 (bản Wi-Fi) hoặc bất kỳ Arduino nào. Header-only,
// không phụ thuộc thư viện. Chỉ chứa LOGIC frame (checksum/lock/repair/verify)
// và bộ dựng lệnh ghi — phần gửi OneWire + STORE do firmware của bạn thực hiện.
//
// Charger LXT chỉ validate 3 thứ trong frame 32 byte (đã reverse-engineer +
// validate trên frame thật):
//   - lock nibble  = nibble thấp byte 17  (phải = 0 thì mới sạc được)
//   - CS0 = min(Σ nibble byte 0..7, 0xFF) & 0x0F   -> lưu nibble CAO byte 20
//   - CS2 = min(Σ nibble byte 16..19 + nibble thấp byte 20, 0xFF) & 0x0F
//                                                  -> lưu nibble CAO byte 21
//   - error byte = response[29] = MSG byte 19 (nằm TRONG vùng CS2 byte 16..19)
//     -> khi zero để clear lỗi, repair tính lại CS2 sau nên vẫn hợp lệ.
//
// Kiến trúc profile: thêm model mới = thêm một FrameProfile, không sửa logic lõi.

#ifndef FRAME_REPAIR_H
#define FRAME_REPAIR_H

#include <stdint.h>
#include <string.h>

namespace makita_battery {

static const uint8_t FRAME_LEN = 32;

struct NibbleRef { uint8_t byteIndex; bool highNibble; };

struct ChecksumSpec {
  uint8_t coverStart;          // byte đầu (gồm)
  uint8_t coverEnd;            // byte cuối (KHÔNG gồm) — cộng cả 2 nibble mỗi byte
  bool    includeExtraLow;     // cộng thêm nibble thấp của extraByte?
  uint8_t extraByte;
  NibbleRef store;             // vị trí lưu checksum
};

struct FrameProfile {
  NibbleRef    lock;           // nibble khóa (phải = 0)
  int8_t       errorByte;      // -1 nếu không có
  ChecksumSpec cs[4];
  uint8_t      csCount;
};

struct VerifyResult {
  bool lockOk;
  bool csOk[4];
  uint8_t csCount;
  bool allOk;
};

// ---- Helpers --------------------------------------------------------------
static inline uint8_t getNibble(uint8_t b, bool high) {
  return high ? ((b >> 4) & 0x0F) : (b & 0x0F);
}
static inline uint8_t setNibble(uint8_t b, bool high, uint8_t v) {
  v &= 0x0F;
  return high ? ((b & 0x0F) | (v << 4)) : ((b & 0xF0) | v);
}

static inline uint16_t sumNibbles(const uint8_t* frame, const ChecksumSpec& cs) {
  uint16_t total = 0;
  for (uint8_t i = cs.coverStart; i < cs.coverEnd; i++)
    total += getNibble(frame[i], true) + getNibble(frame[i], false);
  if (cs.includeExtraLow)
    total += getNibble(frame[cs.extraByte], false);
  return total;
}

// CS = min(sum, 0xFF) & 0x0F  (áp cho mọi profile hiện tại)
static inline uint8_t computeChecksum(const uint8_t* frame, const ChecksumSpec& cs) {
  uint16_t s = sumNibbles(frame, cs);
  if (s > 0xFF) s = 0xFF;
  return s & 0x0F;
}

// ---- Repair / verify ------------------------------------------------------
// Sửa frame tại chỗ (32 byte): zero lock nibble, (tùy chọn) zero error byte,
// tính lại toàn bộ checksum. Chỉ đụng đúng các nibble cần thiết.
static inline void repairFrame(uint8_t* frame, const FrameProfile& p, bool clearError = true) {
  frame[p.lock.byteIndex] = setNibble(frame[p.lock.byteIndex], p.lock.highNibble, 0);
  if (clearError && p.errorByte >= 0)
    frame[p.errorByte] = 0x00;
  // Tính tất cả checksum trên frame đã zero-lock TRƯỚC rồi mới ghi vào.
  uint8_t vals[4];
  for (uint8_t i = 0; i < p.csCount; i++)
    vals[i] = computeChecksum(frame, p.cs[i]);
  for (uint8_t i = 0; i < p.csCount; i++) {
    const NibbleRef& st = p.cs[i].store;
    frame[st.byteIndex] = setNibble(frame[st.byteIndex], st.highNibble, vals[i]);
  }
}

static inline VerifyResult verifyFrame(const uint8_t* frame, const FrameProfile& p) {
  VerifyResult r;
  r.csCount = p.csCount;
  r.lockOk = getNibble(frame[p.lock.byteIndex], p.lock.highNibble) == 0;
  r.allOk = r.lockOk;
  for (uint8_t i = 0; i < p.csCount; i++) {
    uint8_t stored = getNibble(frame[p.cs[i].store.byteIndex], p.cs[i].store.highNibble);
    r.csOk[i] = (stored == computeChecksum(frame, p.cs[i]));
    if (!r.csOk[i]) r.allOk = false;
  }
  return r;
}

// Dựng lệnh ghi frame về BMS:
//   [0x01, len, 0x00, 0x33] + [0x33, 0x0F] + <32 byte frame>
// out phải có ít nhất 38 byte. Trả về số byte đã ghi.
static inline uint8_t buildWriteCmd(const uint8_t* frame, uint8_t* out) {
  const uint8_t prefixLen = 2;                 // {0x33, 0x0F}
  const uint8_t dataLen = prefixLen + FRAME_LEN; // 34 = 0x22
  out[0] = 0x01; out[1] = dataLen; out[2] = 0x00; out[3] = 0x33;
  out[4] = 0x33; out[5] = 0x0F;
  memcpy(out + 6, frame, FRAME_LEN);
  return 4 + dataLen;                           // 38
}

// ---- Profile: LXT 18V (standard) -----------------------------------------
static const FrameProfile LXT18_STANDARD = {
  /* lock      */ { 17, false },   // nibble thấp byte 17
  /* errorByte */ 19,              // = response[29] = MSG[19] (trong vùng CS2)
  /* cs[]      */ {
    /* CS0 */ { 0, 8,  false, 0,  { 20, true } },   // Σ nibble byte0..7 -> byte20 hi
    /* CS2 */ { 16, 20, true, 20, { 21, true } },   // Σ nibble byte16..19 + byte20.lo -> byte21 hi
    {0,0,false,0,{0,false}}, {0,0,false,0,{0,false}}
  },
  /* csCount   */ 2
};

} // namespace makita_battery
#endif // FRAME_REPAIR_H
