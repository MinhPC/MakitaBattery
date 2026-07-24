# Makita LXT — Ghi chú reverse-engineering frame (cho lần test pin khác)

Tài liệu này gom lại những gì đã xác nhận được qua test thực tế trên phần cứng
(Arduino + pin BL1830B, model command_version `""`, dùng profile
`LXT18_STANDARD` trong `modules/makita_lxt.py`). Đọc trước khi test/sửa thêm
để không lặp lại các bước đã kiểm chứng, và biết chỗ nào còn chưa test.

## Bản đồ byte trong `frame` (32 byte, `frame[i] = response[10+i]`)

| idx | Ý nghĩa | Ổn định? | Ghi chú |
|---|---|---|---|
| 17 | Lock nibble (low) | **Ổn định, lưu EEPROM thật** | 0 = charger cho sạc. Đây là bit duy nhất xác nhận ghi-là-giữ được lâu dài. |
| 19 | Error byte / "Status code" | **KHÔNG ổn định — BMS tự tính lại (live) mỗi lần đọc** | Ghi 0 vào đây chỉ có hiệu lực trong đúng khung ghi, đọc lại sau đó (dù chỉ < 1 giây) đã có thể khác. Xem "Phát hiện quan trọng" bên dưới. |
| 20 (nibble cao) | CS0 checksum store | Tính lại theo nội dung frame[0:8] | |
| 21 (nibble cao) | CS2 checksum store | Tính lại theo nội dung frame[16:20] + frame[20] nibble thấp | |
| 8, 9 | Cặp giá trị luôn giống nhau trong 1 lần đọc | **KHÔNG ổn định giữa các lần đọc** | Đổi giá trị dù không có tác động vật lý gì giữa 2 lần đọc liên tiếp trên cùng 1 pin. Nghi là raw ADC/telemetry live. |
| 16 | Capacity, `nibble_swap(byte)/10` = số Ah | **Ổn định khi ĐỌC, nhưng KHÔNG ghi được** | Xem mục "Capacity không ghi được" bên dưới — đây là ví dụ "ổn định qua nhiều lần đọc" KHÔNG đồng nghĩa "ghi lại được". |
| 24, 27, 29, 31 | Chưa rõ | **KHÔNG ổn định giữa các lần đọc** | Đã thấy tự đổi giữa 2 lần đọc cách nhau < 1 giây trên cùng 1 pin, không có thay đổi vật lý. **Không dùng các byte này để so sánh pin-vs-pin** — chênh lệch quan sát được không đáng tin, chỉ là nhiễu tự nhiên của dữ liệu live. |
| 0–7, 10–15, 18, 22–23, 25–26, 28, 30 | Model/mfg/ROM-liên-quan | Ổn định qua các lần đọc đã quan sát | Chưa test ghi (trừ 16), nên chưa biết byte nào trong nhóm này ghi được. |

## Phát hiện quan trọng — "error byte" không phải cờ lưu

Test: đọc frame → ghi frame với `frame[19] = 0x00` (đúng quy trình
`repair_frame`) → verify ngay lúc ghi báo `all_ok=True` → đọc lại (< 1s sau)
→ `frame[19]` đã quay về giá trị cũ (`0xA5`), và nhiều byte khác (8, 9, 20,
21, 24, 31) cũng khác so với frame vừa ghi.

**Kết luận: `error_byte` được BMS tự tính lại (live) mỗi lần được hỏi, không
phải giá trị đọc từ EEPROM.** Vì vậy:
- "Clear errors" (`RESET_ERROR_CMD`) không thể xóa vĩnh viễn cờ này nếu điều
  kiện sinh ra nó (dù là gì) vẫn đang tồn tại lúc đọc.
- "Frame repair" ghi 0 vào `error_byte` sẽ **không** có tác dụng lâu dài —
  đừng kỳ vọng nó "sửa" được error byte, chỉ nên dùng Frame repair cho mục
  đích lật `lock nibble`.

## `0xA5` không phải bằng chứng lỗi tự thân

Đã dump 1 pin đang gặp lỗi sạc (nháy đèn) và 1 pin sạc bình thường — **cả
hai đều có `error_byte = 0xA5`**. Vậy giá trị này (hoặc ít nhất giá trị
`0xA5` cụ thể) **không phải dấu hiệu đủ để kết luận pin lỗi**. Ý nghĩa từng
bit trong byte này (`ERROR_FLAG_MEANINGS` trong code) vẫn chưa được map —
xem mục "Cách test pin khác" bên dưới để thu thập đúng cách trước khi map.

## Frame repair — phạm vi đã test và CHƯA test

Đã xác nhận trên phần cứng thật (trước đây code ghi "chưa test trên phần
cứng" — nay đã test, cập nhật hiểu biết):
- Write sequence (`TESTMODE_CMD` → `CHARGER_CMD` → write frame → `STORE_CMD`)
  được BMS chấp nhận thật, không bị từ chối.
- Công thức checksum CS0/CS2 của `LXT18_STANDARD` đúng, verify khớp nhiều lần.
- `lock nibble` ghi 0 và giữ nguyên qua nhiều lần đọc sau đó → đây là phần
  ghi có tác dụng thật và bền.

**CHƯA test** (quan trọng, cần lưu ý khi thử pin khác):
- Pin dùng để test từ đầu đã đọc `UNLOCKED` (lock nibble = 0) **ngay từ lần
  đọc đầu tiên, trước khi chạy Frame repair lần nào**. Nghĩa là mọi lần
  chạy Frame repair chỉ ghi 0 vào ô vốn đã 0 — **chưa từng kiểm chứng khả
  năng lật 1 pin đang thực sự `LOCKED` (nibble ≠ 0) về `UNLOCKED` và sạc lại
  được**. Đây là use-case chính của tính năng, và tỉ lệ thành công cho đúng
  use-case này **vẫn hoàn toàn chưa có dữ liệu thực nghiệm**.
- Case pin đang gặp lỗi sạc (nháy đèn xanh-đỏ) trong lần test này **không
  phải do lock nibble hay error byte** (xem 2 mục trên) — nên Frame repair
  không giải quyết được đúng loại lỗi đó. Nguyên nhân thật nhiều khả năng
  chỉ xuất hiện lúc sạc thật (phản ứng điện áp dưới tải, dòng nạp, nhiệt
  tăng khi có dòng) — nằm ngoài phạm vi đọc/ghi tĩnh của tool này.

## Capacity (frame[16]) không ghi được — dù ổn định khi đọc

Trường `Capacity` hiển thị = `nibble_swap(response[26]) / 10` Ah, tức
`frame[16]` (`response[26]`, vì `frame[i] = response[10+i]`). Gặp trên 1 khối
pin đã thay mạch BMS khác (mạch thay vào vốn lập trình cho pack 3.0Ah, trong
khi khối cell thật là 6.0Ah) → tool hiển thị sai `3.0Ah`.

Test: đổi `frame[16]` từ `0xE1` (3.0Ah) sang `0xC3` (giải mã ra 6.0Ah), tính
lại checksum CS2 (byte 16 nằm trong vùng phủ `bytes[16,20)`), ghi theo đúng
quy trình `TESTMODE_CMD → CHARGER_CMD → write frame → STORE_CMD` (y hệt quy
trình Frame repair, chỉ khác byte bị đổi) → verify lúc ghi báo hợp lệ (checksum
khớp) → đọc lại → **`frame[16]` quay về đúng `0xE1` (3.0Ah) như cũ**.

**Khác với `error_byte`** (đọc lại ra giá trị *khác* mỗi lần — dấu hiệu live-
compute), ở đây đọc lại ra **đúng y hệt giá trị cũ** — dấu hiệu cho thấy
**BMS âm thầm từ chối/không commit ghi cho riêng byte này**, dù nó nằm cùng
vùng checksum với lock nibble (byte 17, ghi được). Khả năng cao đây là 1
giá trị cấu hình gốc của mạch (lập trình sẵn từ nhà sản xuất mạch, có thể ở
vùng nhớ được bảo vệ ghi riêng), không phải phần frame mà `STORE_CMD` thực
sự cho phép sửa.

**Bài học chung**: 1 byte "ổn định qua nhiều lần đọc" (không đổi tự nhiên
như byte live) **không có nghĩa là ghi lại được** — phải test ghi-rồi-đọc-lại
riêng cho từng byte trước khi kết luận, đừng suy ra từ tính ổn định khi đọc.

## Ngày sản xuất / ROM ID — ngoài phạm vi ghi hiện có

`Manufacturing date` đọc từ `response[2:4]`, nằm trong vùng **ROM ID**
(`response[2:10]`) — khác hẳn vùng `frame` (`response[10:42]`) mà mọi lệnh
ghi hiện có (`_build_write_frame_cmd`, `write_prefix=[0x33,0x0F]`) nhắm tới.
**Chưa có lệnh ghi nào được reverse-engineer cho vùng ROM ID này.** Nếu đây
là ROM code chuẩn 1-Wire (kiểu DS2431/DS28E...) thì theo thiết kế phần cứng
phổ biến, vùng này thường được khắc laser tại nhà máy — không ghi lại được
bằng bất kỳ lệnh nào. Không nên đoán mò 1 lệnh ghi mới cho vùng này trên
pin thật — không có checksum nào để tự kiểm chứng ghi đúng/sai như vùng
frame, rủi ro ghi nhầm vùng nhớ khác (kể cả chính ROM ID dùng để định danh
trên bus 1-Wire) cao hơn nhiều so với lợi ích.

## Model "F0513" (đời cũ, hiện đang giới hạn "chỉ chẩn đoán") — manh mối để mở khóa sau này

Pin test: ROM ID `11 05 08 02 D4 14 06 58`, SX 08/05/2017, 6.0Ah, đã sạc 145
lần. Probe bằng `MODEL_CMD` chuẩn thất bại → app fallback sang
`F0513_MODEL_CMD` và thành công → `command_version = "F0513"` →
`MODEL_SPECS` đánh dấu `"limited": True` (chỉ đọc model + cell voltage + 1
cảm biến nhiệt qua bộ lệnh riêng, không có nhiệt độ MOSFET) vì **chưa có
entry nào trong `FRAME_PROFILES` cho đời này** → nút "Frame repair" báo
"Chưa hỗ trợ".

**Phát hiện quan trọng**: dump frame tĩnh (`READ_MSG_CMD`) của pin F0513 này
—

```
F1 26 BD 13 14 58 00 00 74 74 40 21 D0 80 02 1B C3 D0 8E 67 60 F0 00 23 02 02 0E 19 00 F6 00 15
```

— khi áp **đúng công thức checksum của `LXT18_STANDARD`** (không đổi gì cả)
thì khớp 100%:
- CS0 (Σ nibble byte 0–7 = 70) → `min(70,0xFF)&0xF = 6` = nibble cao byte 20
  (`60`) ✅
- CS2 (Σ nibble byte 16–19 + nibble thấp byte20 = 63) → `min(63,0xFF)&0xF =
  F` = nibble cao byte 21 (`F0`) ✅
- Lock nibble (byte 17 = `D0` → 0 → UNLOCKED), capacity (byte 16 =
  `nibble_swap(C3)/10 = 6.0Ah`), battery type (byte 11 =
  `nibble_swap(21) = 18`) — tất cả đều đúng vị trí/công thức như đời chuẩn.

Đọc lại 2 lần cách nhau 26 phút cho ra **byte-for-byte giống hệt nhau** (không
có byte nào "nhiễu" khác với dump lần trước — xem thêm ghi chú mâu thuẫn ở
mục byte 24/27/29/31 phía trên, có vẻ độ "nhiễu" không phải đặc tính chung
của mọi pin/mọi lần đọc).

**Kết luận**: rất có khả năng đời "F0513" dùng **chung layout + công thức
checksum frame tĩnh** với `LXT18_STANDARD` — chỉ khác lệnh probe model
(`F0513_MODEL_CMD`) và lệnh đọc điện áp động (`F0513_VCELL_x`/`F0513_TEMP_CMD`
thay vì `READ_DATA_REQUEST`).

**CHƯA làm được / cần trước khi bật Frame repair cho đời này**:
1. Pin test hiện đã `UNLOCKED` sẵn — chưa có pin F0513 nào đang thật sự
   `LOCKED` để thử lật khóa (giống hạn chế chung đã ghi ở mục "Frame repair
   — phạm vi đã test và CHƯA test" phía trên).
2. **Chuỗi lệnh ghi chưa được test trên đời này.** F0513 đã biết là dùng
   `F0513_TESTMODE_CMD` khác với `TESTMODE_CMD` chuẩn — nên dù frame layout
   giống nhau, **không nên mặc định chuỗi `TESTMODE → CHARGER → write →
   STORE` hoạt động y hệt** cho tới khi test trực tiếp trên phần cứng.
3. Nếu muốn thử: thêm 1 profile mới vào `FRAME_PROFILES` (copy cấu trúc
   `LXT18_STANDARD`, `"command_versions": ["F0513"]`), rồi test cẩn thận
   trên 1 pin F0513 chấp nhận rủi ro — bắt đầu bằng verify (không ghi) trước
   khi thử ghi thật.

## Cách test pin khác cho đúng (tránh lặp lại nhầm lẫn đã gặp)

1. **Baseline trước khi so sánh bất kỳ điều gì**: đọc (Dump raw frame) cùng
   1 pin **3–5 lần liên tiếp**, không tác động gì giữa các lần. Byte nào đổi
   giá trị dù không có thay đổi vật lý → đánh dấu là "live/noisy", loại khỏi
   mọi so sánh pin-vs-pin sau này. Byte nào luôn giữ nguyên → mới đáng tin
   để so sánh.
2. **Chỉ so sánh các byte "ổn định"** giữa pin lỗi và pin khỏe (sau bước 1),
   không dùng byte live để kết luận.
3. **Muốn đánh giá đúng tỉ lệ thành công của Frame repair**: cần thử trên 1
   pin đang đọc `State = LOCKED` thật sự (không phải pin đã sẵn unlocked),
   rồi kiểm tra xem sau khi ghi + đọc lại nhiều lần, `State` có giữ được
   `UNLOCKED` không, và **quan trọng nhất: pin có sạc lại được thật không**
   (không chỉ dựa vào verify frame).
4. Nếu nghi ngờ lỗi liên quan đến sạc thật (không phải lock/error byte),
   ưu tiên kiểm tra vật lý (thermistor, mối hàn PCB, dây cân bằng cell)
   thay vì tiếp tục đào dữ liệu qua giao thức 1-wire tĩnh.
5. **Muốn biết 1 byte có ghi lại được không, phải test ghi-rồi-đọc-lại trực
   tiếp** (đổi giá trị, verify checksum lúc ghi, rồi đọc lại xem có giữ
   nguyên không) — không suy ra từ việc byte đó "ổn định qua nhiều lần đọc
   tĩnh". `frame[16]` (capacity) là ví dụ: ổn định khi đọc nhưng ghi bị
   BMS âm thầm từ chối.

## Tham khảo ngoài (đèn sạc, không đặc thù cho project này)

Nháy đỏ-xanh xen kẽ trên sạc Makita — nguồn công khai không thống nhất hoàn
toàn về nguyên nhân gốc, có 2 cách diễn giải phổ biến:
- Pin lỗi (mạch bảo vệ nội bộ báo cell có vấn đề).
- Lỗi phát hiện pack / charger không giao tiếp được với BMS (tiếp điểm bẩn,
  lắp lệch, pin không tương thích).

Không có tài liệu nào map được ý nghĩa bit-level của `error_byte` (byte 29
trong response, `frame[19]`) cho model Makita LXT — kể cả sau khi tìm kiếm
công khai. Việc map bit cụ thể vẫn cần thêm dữ liệu thực nghiệm theo đúng
phương pháp ở mục "Cách test pin khác" bên trên.
