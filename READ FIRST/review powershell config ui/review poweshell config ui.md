# BatteryClaw — Review TỪNG DÒNG các file khác

Gồm: 3 script PowerShell, 2 file
giao diện HTML+JS, 2 file cấu hình build, 3 file requirements. Không bỏ sót file nào.

Định dạng: trích dòng (kèm số dòng) → giải thích ngay dưới.

Danh sách 10 file trong phần này:
1. install.ps1            (64)   — installer cho khách
2. build_business.ps1     (157)  — đóng gói bản thương mại
3. check_env.ps1          (222)  — kiểm môi trường máy
4. dashboard/static/index.html (252) — giao diện dashboard (HTML+JS)
5. server/templates/admin.html (253) — trang quản trị bán key (HTML+JS)
6. engine_dotnet/BatteryClaw.Engine.csproj (31) — cấu hình build engine C#
7. engine/CMakeLists.txt  (66)   — cấu hình build engine C++ (cũ)
8. app/requirements.txt          — deps Python cho app
9. datacollector/requirements.txt — deps Python cho data/train
10. server/requirements.txt      — deps Python cho server

═══════════════════════════════════════════════════════════════════════════════
# FILE A/10 — install.ps1  (64 dòng — INSTALLER CHO KHÁCH)
═══════════════════════════════════════════════════════════════════════════════

```
1-12  # comment: tạo shortcut Desktop + Start Menu, tùy chọn autostart; cách chạy + gỡ
12    param([switch]$Uninstall)
14-23 $ErrorActionPreference="Stop"; AppName; here; exe; đường dẫn shortcut + runKey (registry autostart)
```
**Dòng 1-23:** Installer chạy trên máy KHÁCH sau khi giải nén gói. Không cài gì thêm —
chỉ sắp shortcut. Tham số -Uninstall để gỡ. Lấy đường dẫn exe cạnh script, vị trí Desktop/
Start Menu, và khóa registry Run (autostart).

```
25-32 New-Shortcut($path, $target): tạo .lnk qua WScript.Shell COM (target + workdir + mô tả)
```
**Dòng 25-32:** Hàm tạo shortcut Windows bằng COM object WScript.Shell.

```
34-42 if Uninstall: xóa 2 shortcut + xóa registry autostart; nhắc config/license ở %APPDATA% xóa tay
```
**Dòng 34-42:** Nhánh gỡ cài: xóa shortcut + autostart. Lưu ý đúng: config/license nằm
%APPDATA%\BatteryClaw (khớp buy_business.py) nên báo người dùng xóa tay nếu muốn sạch hẳn.

```
44-47 nếu không thấy BatteryClaw.exe cạnh installer → báo lỗi đỏ
49-52 tạo shortcut Desktop + Start Menu
54-60 hỏi autostart (y/N) → ghi registry Run nếu đồng ý
62-64 thông báo xong: chạy Run as administrator, lần đầu nhập Server+Email+Key
```
**Dòng 44-64:** Kiểm exe tồn tại. Tạo 2 shortcut. Hỏi có khởi động cùng Windows không →
ghi registry HKCU\...\Run. Nhắc chạy với quyền Admin (app cần Admin để điều khiển phần
cứng) và luồng kích hoạt lần đầu.

**TÓM TẮT:** Installer nhẹ cho khách (shortcut + autostart tùy chọn). Khớp đúng với
buy_business (Admin, %APPDATA%, luồng activate). LIÊN KẾT: build_business.ps1 copy file
này vào gói, buy_business.py (app được shortcut trỏ tới).

═══════════════════════════════════════════════════════════════════════════════
# FILE B/10 — build_business.ps1  (157 dòng — ĐÓNG GÓI BẢN THƯƠNG MẠI)
═══════════════════════════════════════════════════════════════════════════════

```
1-21  <# comment #>: đóng gói bản thương mại có license gate; output dist\BatteryClaw\; yêu cầu máy build (.NET 8, Python, PyInstaller)
23-25 $ErrorActionPreference="Stop"; root=$PSScriptRoot; dist=dist\BatteryClaw_business
```
**Dòng 1-25:** Script đóng gói toàn bộ thành gói khách hàng. Entry point app\buy_business.py.
Output gồm BatteryClaw.exe + engine\ + models\. Yêu cầu MÁY BUILD (không phải máy khách):
.NET SDK 8, Python 3.10+, PyInstaller. dist ra thư mục BatteryClaw_business (khớp mô tả
đã build trong dự án).

```
33-45 [0] dọn dist cũ: cmd rmdir /s /q (mạnh hơn Remove-Item khi file bị lock); tạo lại dist + engine + models
```
**Dòng 33-45:** Dọn dist cũ. Dùng cmd rmdir vì mạnh hơn PowerShell Remove-Item khi có
file bị khóa (bài học thực tế khi build lại nhiều lần). Tạo cấu trúc thư mục.

```
47-62 [1] kiểm model: chưa có batteryclaw_policy.onnx → train 300k steps; copy model (+ .onnx.data) vào dist\models
```
**Dòng 47-62:** Bước model: nếu chưa có model balanced thì tự train 300k steps. Copy model
+ file .data (model ONNX lớn tách .data). Đây là model mặc định (balanced).

```
64-74 [1.1] copy thêm model profile battery_saver + performance nếu đã train
```
**Dòng 64-74:** Copy 2 model profile riêng (nếu đã train) — khớp Tầng 1.1 (3 model) và
_model_for_profile trong buy_business.

```
76-88 [2] build engine C# self-contained: dotnet publish -c Release -r win-x64 --self-contained PublishSingleFile → dist\engine
```
**Dòng 76-88:** Build engine C# thành 1 file exe tự chứa (không cần .NET trên máy khách).
PublishSingleFile + IncludeNativeLibrariesForSelfExtract. Đây là lý do khách không cần
cài .NET.

```
90-118 [3] build app GUI: --add-data 7 thư mục; [FIX] --paths cho từng thư mục con online + --collect-submodules online + --hidden-import 10 module
```
**Dòng 90-118:** Build app bằng PyInstaller. **Fix quan trọng:** online/ import submodule
qua sys.path.insert động → PyInstaller không tự thấy → phải khai báo --paths cho TỪNG
thư mục con online + --collect-submodules + --hidden-import 10 module. Đây chính là fix
"online learning chết trong exe" (bài học đóng gói — code chạy được ở source nhưng exe thiếu module).

```
120-136 lệnh pyinstaller: --onefile --windowed --uac-admin --name BatteryClaw; Invoke-Expression
```
**Dòng 120-136:** Dựng lệnh PyInstaller: 1 file, không console (--windowed), yêu cầu Admin
(--uac-admin). Đây là lý do app luôn xin quyền Admin lúc chạy.

```
138-143 [4.4] copy install.ps1 vào gói cho khách
145-157 in hướng dẫn: nén dist thành zip, gửi khách, giải nén + chạy install.ps1 + BatteryClaw.exe; nhắc key lock vào máy
```
**Dòng 138-157:** Copy installer vào gói. In hướng dẫn giao khách (nén zip, giải nén,
chạy, kích hoạt). Nhắc key khóa 1 máy.

**TÓM TẮT:** Script đóng gói end-to-end (model → engine C# self-contained → app exe →
installer). Chứa fix then chốt cho online learning trong exe (--paths/--hidden-import).
LIÊN KẾT: train.py (train model), engine_dotnet (publish), buy_business.py (entry point),
install.ps1 (kèm gói). Đây là script tạo ra sản phẩm thực tế đã bán.

═══════════════════════════════════════════════════════════════════════════════
# FILE C/10 — check_env.ps1  (222 dòng — KIỂM MÔI TRƯỜNG MÁY)
═══════════════════════════════════════════════════════════════════════════════

```
1-12  <# comment #>: kiểm máy Windows đủ môi trường chạy project chưa; không cần Admin để kiểm
14-22 $ErrorActionPreference=SilentlyContinue; mảng ok/miss/warn; Test-Cmd (kiểm lệnh tồn tại)
```
**Dòng 1-22:** Script chẩn đoán môi trường: báo cái gì ĐÃ CÓ / THIẾU / cảnh báo, kèm lệnh
cài. Không cần Admin. 3 nhóm kết quả: ok, miss (bắt buộc), warn (tùy chọn).

```
30-41 [1] HĐH: build ≥22000 → Win11 (EcoQoS đủ); <22000 → Win10 (EcoQoS per-process KHÔNG chạy)
```
**Dòng 30-41:** Kiểm Windows. Build ≥22000 = Win11 → EcoQoS (ProcessThrottler Phase 5.3)
chạy đủ; Win10 → cảnh báo EcoQoS không có (khớp _ecoQoSSupported trong ProcessThrottler.cs).

```
43-65 [2] Python: kiểm có python + version ≥3.10; kiểm pip
```
**Dòng 43-65:** Kiểm Python ≥3.10 (project test trên 3.12). Thiếu → hướng dẫn tải kèm
nhắc "Add to PATH".

```
67-109 [3] thư viện Python: thử import 15 lib (numpy/torch/gymnasium/sb3/onnx/fastapi/wmi/pywin32...); thiếu → gợi ý pip install; gom lệnh cài
```
**Dòng 67-109:** Kiểm 15 thư viện bằng cách import thật (map tên import → tên pip). Thiếu
cái nào in lệnh cài cái đó, gom thành 1 lệnh pip ở cuối. Bao trùm cả deps train (torch/
sb3) lẫn deps app (wmi/pywin32/winotify).

```
111-128 [4] .NET 8 SDK (tùy chọn): kiểm dotnet + có SDK 8.x không
130-153 [5] C++ build (Phase 1): CMake + MSVC/Visual Studio (qua vswhere)
155-165 [6] GPU/DirectML (tùy chọn): liệt kê Win32_VideoController
```
**Dòng 111-165:** Kiểm .NET 8 (build engine C#), C++ tools (engine cũ), GPU (DirectML
tăng tốc WinML). Đều đánh dấu tùy chọn — chỉ cần cho một số phase.

```
167-221 TỔNG KẾT: in DA CÓ / THIẾU / CẢNH BÁO; LỆNH CÀI NHANH (pip install thiếu + 3 requirements); kết luận đủ/chưa đủ
```
**Dòng 167-221:** Tổng hợp 3 nhóm + lệnh cài nhanh (gợi ý cả pip install -r 3 requirements).
Kết luận máy đã đủ chạy phần Python chưa.

**TÓM TẮT:** Script chẩn đoán môi trường thân thiện (báo rõ thiếu gì + lệnh cài). Hữu ích
khi cài project lên máy mới. LIÊN KẾT: 3 requirements.txt, khớp các phase (EcoQoS Win11,
.NET 8 cho engine C#, C++ cho engine cũ).

═══════════════════════════════════════════════════════════════════════════════
# FILE D/10 — dashboard/static/index.html  (252 dòng — GIAO DIỆN DASHBOARD)
═══════════════════════════════════════════════════════════════════════════════

```
1-7   DOCTYPE/head; title; nạp /static/chart.min.js (Chart.js offline)
8-90  <style>: design tokens (biến CSS) phỏng Task Manager/Fluent Win11 (nền tối mica, accent xanh, Segoe UI); grid card; gauge; chart-box
```
**Dòng 1-90:** Giao diện dashboard web. Nạp Chart.js cục bộ (offline, không CDN). CSS dùng
biến (--bg/--accent/--good...) mô phỏng Task Manager Windows 11 — chủ ý "giống công cụ hệ
thống, không màu mè". Lưới 4 cột card, gauge tròn cho sức khỏe pin.

```
92-97 titlebar: chấm + "BatteryClaw" + profile-pill
99-136 4 card: thời lượng pin hôm nay (+delta), dự đoán còn lại, tiết kiệm 30 ngày, sức khỏe pin (gauge SVG)
```
**Dòng 92-136:** Cấu trúc UI. 4 thẻ số chính. **Dòng 118-120 trung thực:** ghi rõ tiết
kiệm là "ước tính so với khi không dùng (chưa phải số đo tuyệt đối)" + comment DESIGN-01
— đúng tinh thần không thổi phồng con số. Gauge sức khỏe pin là SVG 2 vòng tròn (nền + arc).

```
138-149 2 card biểu đồ: discharge theo giờ + lịch sử tiết kiệm 30 ngày (canvas)
151-154 foot: thời điểm cập nhật + tier pill
```
**Dòng 138-154:** 2 biểu đồ (canvas cho Chart.js). Chân trang hiện giờ cập nhật + gói tier.

```
156-166 JS fmtDur (giây→"Xh YYp"); setDelta (▲/▼ phút so hôm qua, class up/down đổi màu)
```
**Dòng 156-166:** Hàm format thời lượng + delta. Tăng → xanh ▲, giảm → đỏ ▼ (so hôm qua).

```
168-196 areaChart(ctx, labels, data, color, yLabel): Chart.js line fill gradient, kiểu Performance tab (tension 0.35, pointRadius 0)
```
**Dòng 168-196:** Hàm vẽ biểu đồ vùng mượt (gradient mờ dần) giống tab Performance của
Task Manager. Không điểm tròn, đường cong nhẹ — thẩm mỹ hệ thống.

```
198-205 setGauge(pct): tính strokeDashoffset cho arc (chu vi 251=2πr, r=40); màu theo mức (≥60 xanh, ≥40 vàng, else đỏ)
```
**Dòng 198-205:** Vẽ gauge sức khỏe pin: tính độ lệch dash của vòng tròn theo %. Màu đổi
theo mức (≥60% xanh — khớp pin máy MSI 63.5%).

```
207-247 load(): fetch /api/dashboard; lỗi → dữ liệu demo hoặc báo "không kết nối engine"; điền số + gauge + 2 biểu đồ + profile/tier/giờ
248-249 load() ngay + setInterval 15s tự làm mới
```
**Dòng 207-249:** Nạp dữ liệu từ /api/dashboard (dashboard/server.py trả). Mất kết nối →
fallback demo hoặc báo lỗi nhẹ (không vỡ trang). Điền mọi thẻ + 2 biểu đồ. Tự làm mới mỗi
15s (khớp DESIGN-08: server chỉ reload khi file đổi).

**TÓM TẮT:** Giao diện dashboard hoàn chỉnh (HTML+CSS+JS), thẩm mỹ Task Manager Win11,
trung thực về con số ước tính. LIÊN KẾT: dashboard/server.py (API /api/dashboard +
chart.min.js), stats_store/profiles/tiers (nguồn dữ liệu). Đây là cái người dùng thấy
khi bấm "Mở Dashboard".

═══════════════════════════════════════════════════════════════════════════════
# FILE E/10 — server/templates/admin.html  (253 dòng — TRANG QUẢN TRỊ BÁN KEY)
═══════════════════════════════════════════════════════════════════════════════

```
1-37  head + <style>: giao diện bảng kiểu cổ điển (Tahoma, bảng viền xám, tab); badge on/off; stat-box
```
**Dòng 1-37:** Trang admin quản lý license (giao diện bảng đơn giản, gọn nhẹ, không
framework). Style cơ bản: tab, bảng, badge trạng thái, ô thống kê.

```
40-55 wrap: tiêu đề + ô nhập Admin token + 4 tab (Tổng quan/Danh sách Key/Tạo Key/Lịch sử)
```
**Dòng 40-55:** Ô nhập admin token (gửi qua header X-Admin-Token) + 4 tab chức năng.

```
57-77 tab Tổng quan (stat + key gần đây); tab Danh sách Key (search + bảng đầy đủ)
79-110 tab Tạo Key mới (zalo/days/price/note → nút tạo, hiện key mới + nút sao chép); tab Lịch sử (bảng log)
```
**Dòng 57-110:** 4 khu vực: thống kê + key gần đây; danh sách key có tìm kiếm; form tạo
key (số ngày/giá/zalo/ghi chú); lịch sử log. Cột zalo/price/note khớp schema bảng keys
trong server.py (dòng 130-132).

```
113-133 JS: token từ localStorage; setToken; H() (header X-Admin-Token); tab() chuyển khu vực + load tương ứng
```
**Dòng 113-133:** Lưu token ở localStorage trình duyệt. H() gắn token vào mọi request
admin. tab() chuyển tab + nạp dữ liệu.

```
134-163 daysLeft/statusBadge (badge hết hạn/thu hồi/hoạt động); loadDashboard: fetch /admin/stats + /admin/keys, đổ stat-box + 10 key gần đây
```
**Dòng 134-163:** Helper hiển thị hạn + trạng thái. loadDashboard gọi /admin/stats (tổng/
active/expired/doanh thu) + danh sách key. Các endpoint này có thật trong server.py (321
/admin/stats, 305 /admin/keys).

```
164-193 loadKeys/renderKeys (bảng đầy đủ + nút Thu hồi/Gia hạn/Xóa); filterKeys (tìm theo key/email/zalo)
```
**Dòng 164-193:** Liệt kê + lọc key. Mỗi dòng có nút thu hồi/gia hạn/xóa (gọi endpoint
admin tương ứng). machine_id hiển thị cắt 10 ký tự (gọn).

```
194-219 createKey (POST /admin/key/create với days/price/note/buyer_zalo); copyKey (sao chép tin nhắn Zalo gửi khách)
```
**Dòng 194-219:** Tạo key: gửi tham số qua query string tới /admin/key/create (khớp
server.py 263-266). Sai token → báo. copyKey tạo sẵn tin nhắn (key + hạn) để gửi khách
qua Zalo — chi tiết kinh doanh thực tế.

```
220-250 revokeKey/extendKey (prompt số ngày)/deleteKey (confirm 2 lần); loadLogs (bảng lịch sử 200 dòng)
```
**Dòng 220-250:** Thu hồi/gia hạn/xóa key (có confirm để tránh nhầm). extendKey hỏi số
ngày qua prompt. loadLogs hiện 200 log gần nhất (audit). Tất cả khớp endpoint server.py.

**TÓM TẮT:** Trang quản trị bán key đầy đủ (tạo/thu hồi/gia hạn/xóa key, thống kê doanh
thu, log, sao chép tin Zalo). Mọi endpoint JS gọi đều khớp server.py. LIÊN KẾT:
server.py (FastAPI phục vụ trang này qua Jinja2 + các API /admin/*). Đây là công cụ vận
hành kinh doanh thực tế của người bán.

═══════════════════════════════════════════════════════════════════════════════
# FILE F/10 — engine_dotnet/BatteryClaw.Engine.csproj  (31 dòng — CẤU HÌNH BUILD C#)
═══════════════════════════════════════════════════════════════════════════════

```
1-5   <Project Sdk="Microsoft.NET.Sdk">; comment: engine C# thay dần C++ ở tính năng cần API Windows cao cấp
7-17  PropertyGroup: OutputType Exe; TargetFramework net8.0-windows10.0.19041.0; Nullable+ImplicitUsings enable; AssemblyName BatteryClawEngine; x64; LangVersion latest
```
**Dòng 1-17:** Cấu hình build engine C#. Target **net8.0-windows10.0.19041.0** — cần API
Windows + WinML (TFM windows10). Đây là lý do trên máy chỉ có .NET 10 SDK phải đặt
DOTNET_ROLL_FORWARD=Major (engine target net8, chạy được trên runtime mới hơn — khớp fix
trong buy_business.py dòng 530). AssemblyName = BatteryClawEngine.exe (khớp build_business
+ buy_business dò exe).

```
19-29 ItemGroup PackageReference: TraceEvent 3.1.9 (ETW 5.1); OnnxRuntime.DirectML 1.18.0 (WinML 5.2); TaskScheduler 2.11.0 (5.4); System.Management 8.0.0 (WMI)
```
**Dòng 19-29:** 4 package: TraceEvent (EtwPowerMonitor.cs), OnnxRuntime.DirectML (WinMlPolicy.cs),
TaskScheduler (TaskSchedulerReader.cs), System.Management (SystemStateCollector.cs +
HardwareControl.cs dùng WMI). Mỗi package khớp đúng 1 module engine đã review — không dư.

**TÓM TẮT:** Cấu hình build engine C# — chốt target net8-windows + 4 dependency khớp các
module Phase 5. LIÊN KẾT: build_business.ps1 (dotnet publish), toàn bộ engine_dotnet/*.cs.
Giải thích vì sao cần DOTNET_ROLL_FORWARD trên máy .NET 10.

═══════════════════════════════════════════════════════════════════════════════
# FILE G/10 — engine/CMakeLists.txt  (66 dòng — BUILD ENGINE C++ CŨ)
═══════════════════════════════════════════════════════════════════════════════

LƯU Ý: engine C++ là bản CŨ (Phase 1), đã được thay bằng engine C# (Phase 5) ở bản
deploy. File này giữ lại cho tham khảo/build engine cũ. CMakeLists là file cấu hình build (không phải mã C++) nên vẫn review.

```
1-7   cmake 3.20; project CXX; C++17; chặn build nếu KHÔNG phải Windows (FATAL_ERROR)
9     WIN_LIBS: wbemuuid ole32 oleaut32 powrprof psapi advapi32 pdh iphlpapi (thư viện Windows)
```
**Dòng 1-9:** Cấu hình build C++17, chỉ Windows. Liên kết các thư viện Windows: WMI
(wbemuuid), power (powrprof), process (psapi), counter (pdh), mạng (iphlpapi).

```
11-28 batteryclaw.exe: 7 nguồn (main/state_collector/action_executor/power_monitor/gpu_monitor/gpu_switch/context_collector); link WIN_LIBS; MANIFESTUAC requireAdministrator
```
**Dòng 11-28:** Build engine chính từ 7 file C++. Đặt manifest yêu cầu Admin (giống engine
C# cần Admin). Đây là engine cũ trước khi chuyển sang C#.

```
30-33 tray.exe: tray icon autostart (user32/shell32/advapi32)
35-59 các test executable debug (test_state/action/brightness/appdetect/power/gpu/gpuswitch/context) với define riêng
61-65 MSVC: /W3 /O2 cho mọi target
```
**Dòng 30-65:** tray.exe (icon khay hệ thống). Nhiều executable test riêng từng module
(mỗi cái define cờ _TEST). MSVC bật cảnh báo mức 3 + tối ưu O2.

**TÓM TẮT:** Cấu hình build engine C++ cũ (Phase 1) — đã được engine C# thay thế ở bản
deploy hiện tại. Giữ tham khảo. Cho thấy engine cũ cũng cần Admin + cùng bộ thư viện
Windows. LIÊN KẾT: các file C++ trong engine/src/ (ngoài phạm vi review theo yêu cầu).

═══════════════════════════════════════════════════════════════════════════════
# FILE H/I/J — 3 file requirements.txt
═══════════════════════════════════════════════════════════════════════════════

## app/requirements.txt (5 dòng)
```
1-5  # GUI app; requests; wmi/pywin32/winotify (chỉ Windows)
```
Deps cho app GUI: requests (gọi server license). 3 gói chỉ-Windows (điều kiện
`platform_system=="Windows"` nên cài trên Linux không lỗi): wmi (đọc máy), pywin32
(WinAPI), winotify (toast — khớp Toaster trong app_integrations).

## datacollector/requirements.txt (10 dòng)
```
1-10 # Phase 2 deps: numpy/pandas/pyarrow/torch/gymnasium/stable-baselines3/onnx/onnxruntime/requests
```
Deps nặng cho train + thu thập: numpy/pandas/pyarrow (dữ liệu parquet), torch (mạng),
gymnasium + stable-baselines3 (RL/PPO), onnx + onnxruntime (export/chạy model). Đây là
môi trường máy DEV/train, không phải máy khách.

## server/requirements.txt (4 dòng)
```
1-4  fastapi==0.115.0; uvicorn==0.30.6; jinja2==3.1.4; python-multipart==0.0.12
```
Deps server license (ghim phiên bản chính xác — tốt cho deploy ổn định). FastAPI (API) +
uvicorn (chạy) + jinja2 (render admin.html) + python-multipart (form). Khớp server.py.

**TÓM TẮT 3 requirements:** Tách deps theo vai trò: app (nhẹ, chỉ-Windows), datacollector
(nặng, train), server (web). check_env.ps1 kiểm đúng các gói này. Việc ghim phiên bản chỉ
ở server (cần ổn định production) là hợp lý.

═══════════════════════════════════════════════════════════════════════════════
# HOÀN TẤT — ĐÃ REVIEW TOÀN BỘ CODEBASE
═══════════════════════════════════════════════════════════════════════════════

Tổng kết tài liệu review:
- 3 PowerShell, 2 HTML+JS, 2 config build, 3 requirements

ĐỐI CHIẾU:
- .csproj target net8 ↔ DOTNET_ROLL_FORWARD trong app (giải thích trọn vẹn).
- admin.html JS ↔ mọi endpoint /admin/* trong server.py đều khớp (price/note/zalo/stats/extend).
- index.html trung thực ghi rõ "tiết kiệm là ước tính" (DESIGN-01) — nhất quán thái độ
  không thổi phồng đã thấy xuyên suốt.
- build_business.ps1 chứa fix quan trọng "online learning chết trong exe" (--paths +
  --hidden-import cho module nạp động) — bài học đóng gói thực tế, không lộ ở mã Python.
