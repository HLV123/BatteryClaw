# BatteryClaw — Môi trường & Phụ thuộc (Environment)

Tài liệu liệt kê **tất cả** runtime, SDK, công cụ và thư viện cần thiết để chạy trọn
vòng đời dự án: từ huấn luyện AI → build engine → đóng gói → vận hành license server
→ bán cho khách. Phân theo **vai trò** để biết cái nào cần ở đâu.

Đường dẫn dự án: `E:\batteryclaw`

---

## 0. Tóm tắt nhanh — ai cần cài gì

```
   ┌────────────────────────────────────────────────────────────────────────┐
   │  MÁY NGƯỜI BÁN (bạn) — cần cài đầy đủ để train + build + bán           │
   │   • Windows 11                                                         │
   │   • Python 3.10 + các thư viện (mục 2)                                 │
   │   • .NET 10 SDK (build engine C#)                                      │
   │   • PyInstaller (đóng gói exe)                                         │
   │   • (tùy chọn) CMake — chỉ nếu động đến engine C++ cũ                  │
   ├────────────────────────────────────────────────────────────────────────┤
   │  MÁY KHÁCH HÀNG — KHÔNG cần cài gì                                     │
   │   • Chỉ cần Windows 10/11, chạy BatteryClaw.exe với quyền Admin        │
   │   • Python, .NET, thư viện đều đã gói sẵn trong exe (self-contained)   │
   └────────────────────────────────────────────────────────────────────────┘
```

---

## 1. Hệ điều hành & phần cứng

| Thành phần | Yêu cầu | Ghi chú |
|---|---|---|
| Hệ điều hành | Windows 11 (build 22000+) | EcoQoS cần Win11 22000+; máy test build 26200 |
| CPU | x64 | dùng powercfg để throttle |
| GPU | bất kỳ | DirectML chạy WinML trên NVIDIA/AMD/Intel; máy test RTX 3050 + Intel UHD |
| Pin | laptop có pin | đọc WMI BatteryStatus; máy test health ~63% |
| Quyền | **Administrator** | bắt buộc để đặt brightness/CPU/refresh, ETW, EcoQoS |

Máy khách chỉ cần Windows 10/11 x64 + quyền Admin khi chạy.

---

## 2. Python (máy người bán)

### 2.1. Runtime
- **Python 3.10.11** (64-bit). Khuyến nghị đúng 3.10 vì thư viện RL test trên bản này.

### 2.2. Thư viện — phân theo vai trò

**Huấn luyện AI (train + simulator):**
| Thư viện | Vai trò |
|---|---|
| numpy | Xử lý ma trận, vector observation |
| torch | Mạng neuron, huấn luyện PPO |
| gymnasium | Khung môi trường Reinforcement Learning |
| stable-baselines3 | Thuật toán PPO (và SAC ở kho nghiên cứu) |
| onnx | Định dạng model dùng chung (export 15→7) |
| onnxruntime | Chạy suy luận ONNX tốc độ cao (cả lúc deploy) |

**Dữ liệu & world model (Phase 2):**
| Thư viện | Vai trò |
|---|---|
| pandas | Xử lý transition data |
| pyarrow | Ghi/đọc parquet (fallback jsonl nếu thiếu) |

**License server (FastAPI):**
| Thư viện | Phiên bản | Vai trò |
|---|---|---|
| fastapi | 0.115.0 | Web framework cho API license |
| uvicorn | 0.30.6 | ASGI server chạy FastAPI |
| jinja2 | 3.1.4 | Template trang admin |
| python-multipart | 0.0.12 | Nhận form data trên trang admin |
| pydantic | (theo fastapi) | Validate request body |

**App khách + giao tiếp Windows:**
| Thư viện | Vai trò |
|---|---|
| requests | Gọi API activate/verify key |
| wmi | Đọc phần cứng Windows (Windows only) |
| pywin32 (win32api) | API Windows nâng cao (Windows only) |
| winotify | Toast notification Windows 11 (Windows only) |
| tkinter | GUI app (đi kèm Python, không cài thêm) |

**Đóng gói:**
| Thư viện | Vai trò |
|---|---|
| pyinstaller | Gói app+brain thành 1 file .exe |

### 2.3. Lệnh cài nhanh tất cả
```powershell
pip install numpy torch gymnasium stable-baselines3 onnx onnxruntime ^
            pandas pyarrow ^
            fastapi==0.115.0 uvicorn==0.30.6 jinja2==3.1.4 python-multipart==0.0.12 ^
            requests wmi pywin32 winotify ^
            pyinstaller
```
(tkinter đã đi kèm Python; nếu thiếu thì cài lại Python tích chọn "tcl/tk".)

Hoặc cài từ requirements có sẵn trong dự án:
```powershell
pip install -r datacollector\requirements.txt   # train + data + world model
pip install -r server\requirements.txt           # license server
pip install -r app\requirements.txt              # app khách + Windows
pip install pyinstaller
```

---

## 3. .NET (máy người bán — build engine C#)

| Thành phần | Yêu cầu | Ghi chú |
|---|---|---|
| .NET SDK | **.NET 10** (máy đang có) | engine target `net8.0-windows10.0.19041.0` |
| Roll-forward | `DOTNET_ROLL_FORWARD=Major` | để engine .NET 8 chạy/build trên .NET 10 |
| Gói NuGet | System.Management 8.0.0 | WMI (đọc pin, brightness); tự restore khi build |

Lệnh build engine:
```powershell
cd E:\batteryclaw\engine_dotnet
$env:DOTNET_ROLL_FORWARD="Major"
dotnet build -c Release
```

Engine đóng gói **self-contained** (`dotnet publish --self-contained`) nên gói luôn
.NET runtime vào → **máy khách không cần cài .NET**.

---

## 4. Công cụ build khác (máy người bán)

| Công cụ | Bắt buộc? | Vai trò |
|---|---|---|
| PyInstaller | Có | đóng gói exe (đã liệt kê ở mục 2) |
| CMake | Không | chỉ cần nếu động đến engine C++ cũ (`engine/`) — bản deploy KHÔNG dùng |
| Git | Không | quản lý mã nguồn (tùy chọn) |

---

## 5. Hạ tầng khi BÁN THẬT (thu tiền)

Để bán cho khách ở xa và thu tiền thật, ngoài máy dev cần:

| Thành phần | Vai trò | Ghi chú |
|---|---|---|
| VPS / máy chủ công khai | chạy license server 24/7 | khách activate/verify key qua đây |
| IP tĩnh hoặc tên miền | khách nhập vào "Server URL" | thay cho localhost lúc test |
| HTTPS (chứng chỉ SSL) | bảo mật khi truyền key | có hướng dẫn `DEPLOY_HTTPS.md` |
| Python 3.10 trên VPS | chạy `server.py` | chỉ cần thư viện nhóm "license server" (mục 2.2) |
| BC_ADMIN_TOKEN mạnh | bảo vệ trang admin | KHÔNG dùng `admin-test-123` khi thật |
| Kênh thu tiền | nhận thanh toán | chuyển khoản/Zalo/MoMo... (ngoài phạm vi code) |
| Kênh giao hàng | gửi file ZIP + key | Zalo/email/Drive |

> Lúc thử local: chỉ cần chạy `server.py` trên chính máy bạn (`http://localhost:8000`),
> không cần VPS. VPS chỉ cần khi khách ở máy khác.

---

## 6. Lưu trữ runtime (chạy lúc dùng thật)

| Dữ liệu | Vị trí | Ghi chú |
|---|---|---|
| Config + license | `%APPDATA%\BatteryClaw\config.json` | luôn ghi được |
| Online learning state | `%APPDATA%\BatteryClaw\state\` | replay buffer, checkpoint, pattern |
| Dashboard stats | `%APPDATA%\BatteryClaw\state\` | thống kê tiết kiệm |
| Model ONNX | đóng gói trong exe / `dist\...\models\` | brain nạp lúc chạy |
| License DB (người bán) | SQLite cạnh `server.py` | keys + logs |

---

## 7. Checklist xác minh môi trường

Trước khi train/build, chạy script kiểm tra có sẵn:
```powershell
cd E:\batteryclaw
powershell -ExecutionPolicy Bypass -File check_env.ps1
```
Nó kiểm Python + thư viện, .NET, GPU, công cụ build. Nếu báo đủ thì sẵn sàng.

Kiểm thủ công nhanh:
```powershell
python --version                              # 3.10.x
python -c "import torch, stable_baselines3, onnxruntime; print('RL OK')"
python -c "import fastapi, uvicorn; print('server OK')"
dotnet --list-sdks                            # thấy 10.x
pip show pyinstaller                          # đã cài
```

---

## 8. Vì sao máy khách không cần cài gì

```
   BatteryClaw.exe  (PyInstaller --onefile)
      ├── Python runtime + numpy/onnxruntime/... ── gói sẵn
      ├── brain + online learning ──────────────── gói sẵn
      ├── model ONNX ────────────────────────────── gói sẵn
      └── engine/  (dotnet publish --self-contained)
             └── .NET runtime ──────────────────── gói sẵn
```

→ Khách chỉ giải nén + chạy `.exe` với quyền Admin. Không cài Python, .NET, hay thư viện.


# ===========================
# Gỡ phần mềm & Toán nền cho RL
# ===========================

Phần cuối cùng của dự án. Hai phần:

- **Phần 1:** Khi không muốn dùng BatteryClaw nữa, làm gì để máy nhanh trở lại (an toàn,
  từng bước).
- **Phần 2:** Toàn bộ toán *cần có* để hiểu phần Học tăng cường (RL) trong chính project
  này — không phải toán hàn lâm, mà đúng những thứ được dùng trong code, có chỉ rõ công
  thức nằm ở file nào.

---

# PHẦN 1 — GỠ PHẦN MỀM & KHÔI PHỤC MÁY

BatteryClaw điều khiển phần cứng thật (CPU, độ sáng, refresh, GPU, wifi). Khi tắt **đột
ngột** (kill process, crash, tắt máy giữa chừng), hàm khôi phục mặc định (`_shutdown`)
không kịp chạy → các thiết lập tiết kiệm **kẹt lại** → máy chậm. Đây là cách gỡ sạch.

## Bước 1 — Tắt hẳn app và engine

Mở Task Manager (`Ctrl + Shift + Esc`), tìm và **End task**:
- `BatteryClaw.exe`
- `BatteryClawEngine.exe`

## Bước 2 — Tắt khởi động cùng Windows (nếu có bật)

Nếu không tắt, lần mở máy sau app lại chạy và lại bóp CPU.
- Task Manager → tab **Startup apps** → tìm **BatteryClaw** → **Disable**.
- Hoặc chạy installer với cờ gỡ: `powershell -ExecutionPolicy Bypass -File install.ps1 -Uninstall`

## Bước 3 — Trả CPU về 100% (quan trọng nhất)

Đây là nguyên nhân số 1 làm máy chậm. Mở **PowerShell (Run as administrator)**:

Kiểm tra mức CPU hiện tại:
```
powercfg /query SCHEME_CURRENT SUB_PROCESSOR PROCTHROTTLEMAX
```
Nhìn 2 dòng cuối `Current AC/DC Power Setting Index`. Giá trị là số hex:
`0x00000014` = 20% (đang bị bóp), `0x00000064` = 100% (bình thường).

Trả về 100%:
```
powercfg /setacvalueindex SCHEME_CURRENT SUB_PROCESSOR PROCTHROTTLEMAX 100
powercfg /setdcvalueindex SCHEME_CURRENT SUB_PROCESSOR PROCTHROTTLEMAX 100
powercfg /setactive SCHEME_CURRENT
```

Cách mạnh hơn (đưa toàn bộ power plan về mặc định gốc của Windows, xóa mọi tùy chỉnh app
đã đặt — gồm cả wifi power save):
```
powercfg /restoredefaultschemes
```

Máy sẽ nhanh lại **ngay**, không cần khởi động lại.

## Bước 4 — Kiểm tra các thiết lập khác

- **Độ sáng:** nếu màn tối, chỉnh lại trong Settings → System → Display, hoặc phím Fn.
- **Refresh rate:** nếu thấy kém mượt, Settings → Display → Advanced display → đưa lại
  mức cao nhất (vd 144Hz). Lúc tiết kiệm app có thể đã hạ về 60Hz.
- **GPU preference:** Settings → Display → Graphics → nếu có app bị đặt "Power saving"
  ngoài ý muốn thì đổi lại "Let Windows decide" / "High performance".
- **dGPU / wifi:** thường tự về sau khi restart.

## Bước 5 (tùy chọn) — Xóa dữ liệu app

Dữ liệu online learning + license nằm ở `%APPDATA%\BatteryClaw`. Mở Run (`Win+R`), gõ
`%APPDATA%`, vào thư mục `BatteryClaw`, xóa nếu muốn sạch hoàn toàn.

## Bài học kỹ thuật (ghi vào "issues")

Lỗi CPU kẹt 20% sau khi tắt đột ngột là một **issue thật** của dự án: phần mềm đụng tới
phần cứng phải luôn có **đường lui an toàn**. Hướng sửa cho lần sau: engine nên có
*watchdog* — nếu mất kết nối với brain quá N giây thì tự khôi phục mọi thiết lập về mặc
định, để máy không bao giờ kẹt dù app chết kiểu gì. Đây chính là loại "reward âm" có giá
trị nhất để học.

---

# PHẦN 2 — TOÁN NỀN CHO RL TRONG PROJECT NÀY

Mục tiêu: đọc xong phần này, khi mở lại code `simulator/train.py`, `battery_env.py`,
`advanced/sac/`, `online/finetune/ewc.py`, bạn hiểu **từng con số và công thức** đang làm
gì. Mỗi mục đều chỉ rõ nó nằm ở đâu trong code.

Không cần giỏi toán hàn lâm. Chỉ cần nắm 4 nhóm: **xác suất/kỳ vọng**, **đạo hàm/tối ưu**,
**vector cơ bản**, và **ý tưởng của từng công thức RL**. Ta đi từ trực giác → công thức.

---

## A. Bức tranh lớn: RL là gì, và MDP

**Học tăng cường (RL)** = một *agent* (AI) tương tác với *môi trường*, mỗi bước:
1. Quan sát **trạng thái** $s$ (trong project: 15 số — pin, CPU, nhiệt...).
2. Chọn **hành động** $a$ (7 số — throttle, brightness, GPU...).
3. Nhận **phần thưởng** $r$ (một số: tiết kiệm tốt + ít giật → thưởng cao).
4. Môi trường chuyển sang trạng thái mới $s'$.

Mục tiêu: học cách chọn hành động sao cho **tổng phần thưởng về lâu dài lớn nhất**.

Khung toán mô tả việc này là **Markov Decision Process (MDP)**, gồm 5 thứ
$(\mathcal{S}, \mathcal{A}, P, R, \gamma)$:
- $\mathcal{S}$: tập trạng thái. *Trong code:* `observation_space` 15 chiều, mỗi chiều [0,1].
- $\mathcal{A}$: tập hành động. *Trong code:* `action_space` 7 chiều.
- $P(s'|s,a)$: xác suất chuyển trạng thái. *Trong code:* `battery_env.step()` mô phỏng.
- $R(s,a)$: phần thưởng. *Trong code:* công thức reward trong `step()`.
- $\gamma$ (gamma): hệ số chiết khấu (mục C). *Trong code:* `gamma=0.99`.

**"Markov"** nghĩa là: tương lai chỉ phụ thuộc trạng thái hiện tại, không phụ thuộc quá
khứ. Đây là lý do observation phải chứa ĐỦ thông tin để quyết định (15 chiều được chọn
để thỏa điều này — ví dụ có cả nhiệt độ, tốc độ xả, không chỉ % pin).

---

## B. Xác suất & kỳ vọng (nền của mọi thứ)

RL đầy tính ngẫu nhiên (workload ngẫu nhiên, máy ngẫu nhiên, policy chọn action ngẫu
nhiên). Nên ta luôn nói về **giá trị trung bình kỳ vọng**, không phải giá trị chắc chắn.

**Kỳ vọng (Expectation)** $\mathbb{E}[X]$ = giá trị trung bình của biến ngẫu nhiên $X$,
có trọng số theo xác suất:
$$\mathbb{E}[X] = \sum_i p_i \, x_i \quad\text{(rời rạc)} \qquad \mathbb{E}[X] = \int p(x)\,x\,dx \quad\text{(liên tục)}$$

Ví dụ trong project: "phần thưởng kỳ vọng của một profile" = trung bình reward qua rất
nhiều episode ngẫu nhiên. *Trong code:* `evaluate_model()` chạy 20 episode rồi lấy
`np.mean(rewards)` — đó chính là ước lượng $\mathbb{E}[\text{reward}]$.

**Phân phối xác suất:** một hàm gán xác suất cho mỗi khả năng. Hai cái cần biết:
- **Phân phối đều (uniform):** mọi khả năng như nhau. *Trong code:* bốc máy ngẫu nhiên.
- **Phân phối Gauss (chuẩn / normal):** hình chuông, đặc trưng bởi trung bình $\mu$ và độ
  lệch chuẩn $\sigma$. Rất quan trọng — policy của ta xuất ra một phân phối Gauss trên
  action (mục E).

$$\mathcal{N}(x; \mu, \sigma) = \frac{1}{\sigma\sqrt{2\pi}} \exp\!\left(-\frac{(x-\mu)^2}{2\sigma^2}\right)$$

**Độ lệch chuẩn $\sigma$** đo độ "tản". *Liên hệ project:* kết quả eval ghi `reward 169 ±
94.93` — số `94.93` chính là $\sigma$, cho biết model performance ổn định (tản ít) hơn
battery_saver (`±642`).

---

## C. Phần thưởng, Return, và hệ số chiết khấu $\gamma$

Một hành động tốt không chỉ vì phần thưởng *ngay bây giờ*, mà vì hệ quả *về sau*. Nên ta
định nghĩa **Return** $G_t$ = tổng phần thưởng từ bước $t$ trở đi, có **chiết khấu**:

$$G_t = r_t + \gamma r_{t+1} + \gamma^2 r_{t+2} + \cdots = \sum_{k=0}^{\infty} \gamma^k \, r_{t+k}$$

- $\gamma \in [0,1)$ là **hệ số chiết khấu**. *Trong code:* `gamma=0.99` (trong `PPO(...)`).
- $\gamma$ gần 1 → AI nhìn xa, coi trọng tương lai. $\gamma$ nhỏ → AI thiển cận, chỉ lo
  trước mắt.
- Vì sao cần chiết khấu? (1) phần thưởng tương lai bất định nên đáng "giảm giá"; (2) làm
  tổng vô hạn hội tụ thành số hữu hạn (vì $\gamma^k \to 0$).

*Trực giác trong project:* $\gamma=0.99$ nghĩa AI rất nhìn xa — nó chịu hạ hiệu năng bây
giờ (reward âm nhẹ) để pin trụ tới cuối ngày (reward dương lớn ở cuối). Đây là lý do
`battery_env` thưởng đậm khi "về đích còn pin" (`reward += pin% × 8`).

**Hàm reward thật trong project** (`battery_env.step()`):
$$r = A\cdot w_{save}\cdot r_{save} \;-\; B\cdot w_{lag}\cdot r_{lag} \;-\; C\cdot r_{annoy} \;+\; D\cdot r_{long}$$
Đây là một **tổ hợp tuyến tính có trọng số** của 4 mục tiêu (tiết kiệm, chống giật, chống
khó chịu, giữ tuổi thọ pin). Toán ở đây chỉ là cộng-trừ-nhân có trọng số — nhưng *thiết
kế* các trọng số $A,B,C,D$ và $w_{save}, w_{lag}$ (theo profile) mới là phần tinh tế.

---

## D. Value function & Advantage (đánh giá "tốt đến đâu")

Để cải thiện policy, ta cần biết một trạng thái/hành động "tốt" cỡ nào. Ba khái niệm:

**1. Hàm giá trị trạng thái** $V(s)$ = return kỳ vọng nếu bắt đầu từ $s$ và theo policy
$\pi$:
$$V^\pi(s) = \mathbb{E}_\pi\!\left[ G_t \mid s_t = s \right]$$
"Đứng ở trạng thái này, từ giờ tới cuối kỳ vọng được bao nhiêu điểm."

**2. Hàm giá trị hành động** $Q(s,a)$ = return kỳ vọng nếu ở $s$, làm $a$, rồi mới theo
$\pi$:
$$Q^\pi(s,a) = \mathbb{E}_\pi\!\left[ G_t \mid s_t=s, a_t=a \right]$$

**3. Advantage** $A(s,a) = Q(s,a) - V(s)$ = "hành động $a$ tốt hơn mức trung bình tại $s$
bao nhiêu". Dương = nên làm nhiều hơn; âm = nên tránh. Đây là tín hiệu cốt lõi để chỉnh
policy.

**Phương trình Bellman** (xương sống của RL) — viết $V$ theo chính nó ở bước sau:
$$V^\pi(s) = \mathbb{E}\!\left[ r + \gamma V^\pi(s') \right]$$
Ý: "giá trị hiện tại = thưởng ngay + giá trị (chiết khấu) của trạng thái kế". Mọi thuật
toán RL đều xoay quanh việc làm cho hai vế này khớp nhau.

**GAE (Generalized Advantage Estimation)** — cách ước lượng Advantage mượt, ít nhiễu. Lõi
là **TD error**:
$$\delta_t = r_t + \gamma V(s_{t+1}) - V(s_t)$$
rồi GAE trộn nhiều bước với hệ số $\lambda$:
$$\hat{A}_t = \sum_{l=0}^{\infty} (\gamma\lambda)^l \, \delta_{t+l}$$
- $\lambda$ điều hòa giữa "ít nhiễu nhưng lệch" ($\lambda$ nhỏ) và "đúng nhưng nhiễu"
  ($\lambda$ lớn). *Trong code:* `gae_lambda=0.95`.

Bạn không cần tự code GAE — thư viện `stable-baselines3` (PPO) lo. Nhưng hiểu $\delta_t$
và Advantage thì mới hiểu PPO đang tối ưu cái gì.

---

## E. Policy, và Policy Gradient (trái tim của cách AI học)

**Policy** $\pi_\theta(a|s)$ = "bộ não" — một hàm (mạng nơ-ron, tham số $\theta$) nhận
trạng thái $s$, trả ra cách chọn hành động $a$. Vì action liên tục (throttle là số thực),
policy xuất ra một **phân phối Gauss**: với mỗi state, mạng cho ra trung bình $\mu(s)$ (và
độ lệch $\sigma$), action được lấy mẫu quanh $\mu$.

*Trong code:* `MlpPolicy` với `net_arch=[256,256]` — mạng 2 lớp ẩn 256 nơ-ron. Đầu ra qua
hàm **tanh** để ép action vào khoảng $[-1, 1]$ (rồi mới scale sang dải thật như throttle
$[0.2,1]$ trong `rl_brain.action_to_command`).

Vì sao **tanh**? Vì action vật lý có giới hạn (không thể throttle 500%). tanh là hàm "bóp"
mọi số thực về $[-1,1]$ mượt mà, khả vi (đạo hàm được — cần cho việc học):
$$\tanh(x) = \frac{e^x - e^{-x}}{e^x + e^{-x}}$$

**Mục tiêu tối ưu:** tìm $\theta$ làm return kỳ vọng lớn nhất:
$$J(\theta) = \mathbb{E}_{\pi_\theta}\!\left[ G_t \right]$$

**Định lý Policy Gradient** — công thức cho biết chỉnh $\theta$ theo hướng nào:
$$\nabla_\theta J(\theta) = \mathbb{E}_{\pi_\theta}\!\left[ \nabla_\theta \log \pi_\theta(a|s) \cdot \hat{A}(s,a) \right]$$

Đọc bằng lời: **"tăng xác suất các hành động có Advantage dương, giảm xác suất các hành
động có Advantage âm"**. $\nabla_\theta \log\pi$ là "hướng làm hành động $a$ dễ xảy ra
hơn"; nhân với $\hat{A}$ để biết nên đẩy lên (A>0) hay kéo xuống (A<0). Toàn bộ RL hiện
đại là biến thể của ý này.

---

## F. PPO — thuật toán đang chạy trong bản deploy

Policy gradient thuần có vấn đề: một bước cập nhật quá mạnh có thể phá hỏng policy. **PPO
(Proximal Policy Optimization)** sửa bằng cách **giới hạn mức thay đổi mỗi bước**.

Đặt **tỉ lệ thay đổi** giữa policy mới và cũ:
$$\rho_t(\theta) = \frac{\pi_\theta(a_t|s_t)}{\pi_{\theta_{old}}(a_t|s_t)}$$

Hàm mục tiêu PPO (clipped):
$$L^{CLIP}(\theta) = \mathbb{E}_t\!\left[ \min\Big( \rho_t \hat{A}_t,\; \text{clip}(\rho_t,\, 1-\epsilon,\, 1+\epsilon)\,\hat{A}_t \Big) \right]$$

- `clip(...)` kẹp $\rho_t$ trong $[1-\epsilon, 1+\epsilon]$ → không cho policy nhảy quá
  xa policy cũ trong một lần học. *Trong code:* `clip_range=0.2` (tức $\epsilon=0.2$).
- Lấy `min` để luôn chọn ước lượng "thận trọng" → ổn định.

PPO còn cộng thêm **entropy bonus** để khuyến khích khám phá (đừng vội chốt một chiến lược):
$$L = L^{CLIP} + c\cdot \mathcal{H}(\pi_\theta) \quad,\quad \mathcal{H} = -\sum \pi\log\pi$$
*Trong code:* `ent_coef=0.02` (hệ số $c$). Entropy cao = policy còn "phân vân" = còn thử
nghiệm nhiều; entropy thấp = đã quyết đoán.

*Trong code, các siêu tham số PPO khác:* `n_steps=2048` (thu 2048 bước trước mỗi lần học),
`batch_size=512`, `n_epochs=10` (học lại 10 lượt trên cùng dữ liệu mỗi vòng), `vf_coef=0.5`
(trọng số học hàm giá trị $V$), `max_grad_norm=0.5` (chặn gradient quá lớn). Đây là 3 model
.onnx của bạn được sinh ra bằng đúng các công thức này.

---

## G. SAC — thuật toán thử nghiệm (advanced/sac/)

**SAC (Soft Actor-Critic)** là hướng khác PPO. Khác biệt cốt lõi: SAC **tối đa hóa cả
phần thưởng LẪN entropy** — chủ động giữ tính ngẫu nhiên để khám phá tốt hơn:
$$J(\pi) = \mathbb{E}\!\left[ \sum_t r_t + \alpha\, \mathcal{H}(\pi(\cdot|s_t)) \right]$$
- $\alpha$ là "nhiệt độ" — cân bằng giữa khai thác (reward) và khám phá (entropy). *Trong
  code:* `log_alpha` được học tự động (`advanced/sac/sac_trainer.py`).

SAC dùng **2 mạng Q** (twin critic) và lấy giá trị nhỏ hơn để tránh đánh giá quá lạc quan:
$$y = r + \gamma\big( \min(Q_1, Q_2)(s',a') - \alpha\log\pi(a'|s') \big)$$
*Trong code:* `TwinCritic` trong `networks.py`, công thức target ở `sac_trainer.update()`.

**Soft update** mạng target (cập nhật chậm cho ổn định):
$$\theta_{target} \leftarrow (1-\tau)\,\theta_{target} + \tau\,\theta$$
*Trong code:* `tau=0.005`.

Lưu ý thực tế của project: SAC là off-policy (học lại từ buffer), về lý thuyết hiệu quả
dữ liệu hơn PPO, nhưng trên CPU nó chạy chậm và **chưa chứng minh tốt hơn PPO** cho bài
toán này. Đây là lý do bản deploy dùng PPO.

---

## H. Tối ưu hóa: Gradient Descent, Learning Rate, Adam

Tất cả công thức trên cuối cùng đều quy về: **chỉnh tham số $\theta$ của mạng để một hàm
mục tiêu tốt lên**. Công cụ là **gradient descent**.

**Gradient** $\nabla_\theta L$ = vector chỉ hướng hàm $L$ tăng nhanh nhất. Muốn *giảm* mất
mát thì đi ngược gradient:
$$\theta \leftarrow \theta - \eta\, \nabla_\theta L$$
- $\eta$ là **learning rate** (tốc độ học) — bước đi mỗi lần. Quá lớn → vọt qua đích, dao
  động; quá nhỏ → học rùa bò.

*Trong code có 2 chỗ học rất khác nhau về learning rate:*
- Train từ đầu (`train.py`): LR giảm dần từ `3e-4` → `5e-5` theo tiến độ (`_lr_schedule`)
  — đầu học nhanh, cuối tinh chỉnh để hội tụ ổn định.
- Fine-tune trên máy người dùng (`online/finetune/finetuner.py`): LR **rất nhỏ `1e-5`** —
  cố ý, để không phá kiến thức nền (xem mục I).

**Adam** = thuật toán tối ưu thông minh hơn gradient descent thuần: tự điều chỉnh bước đi
cho từng tham số dựa trên lịch sử gradient (trung bình động của gradient và bình phương
gradient). Bạn chỉ cần biết: Adam là "gradient descent có quán tính + tự điều tốc", và là
mặc định trong cả PPO lẫn SAC lẫn fine-tuner.

**Hàm mất mát thường gặp — MSE (sai số bình phương trung bình):**
$$\text{MSE} = \frac{1}{N}\sum_i (y_i - \hat{y}_i)^2$$
*Trong code:* critic của SAC học bằng MSE (khớp Q với target); fine-tuner đo validation
bằng MSE; world model học $\Delta state$ bằng MSE.

---

## I. EWC — toán chống "quên" khi học trên máy thật

Khi fine-tune trên máy người dùng, ta sợ AI **quên kiến thức nền** đã học từ simulator
("catastrophic forgetting"). **EWC (Elastic Weight Consolidation)** giải bằng một số hạng
phạt: "được chỉnh trọng số, nhưng đừng chỉnh xa những trọng số QUAN TRỌNG với việc cũ".

Hàm mất mát fine-tune:
$$L(\theta) = L_{new}(\theta) + \frac{\lambda}{2} \sum_i F_i\,(\theta_i - \theta_i^*)^2$$
- $\theta^*$: trọng số gốc (sau khi train simulator) — cái ta không muốn rời xa.
- $F_i$: **độ quan trọng** của trọng số thứ $i$ (đường chéo ma trận Fisher).
- $\lambda$: độ mạnh ràng buộc. *Trong code:* `importance=1000`.

**Fisher information** $F_i$ ước bằng bình phương gradient của log-likelihood — trọng số
nào mà thay đổi nhỏ cũng làm đầu ra đổi nhiều thì "quan trọng", bị phạt nặng nếu chỉnh:
$$F_i \approx \mathbb{E}\!\left[ \left( \frac{\partial \log \pi}{\partial \theta_i} \right)^2 \right]$$
*Trong code:* `EWC.estimate_fisher()` và `EWC.penalty()` trong `online/finetune/ewc.py`.

Trực giác: $(\theta_i - \theta_i^*)^2$ là "đi xa gốc bao nhiêu", nhân $F_i$ là "chỗ này có
quan trọng không". Cộng vào loss → optimizer tự động tránh phá những gì cốt lõi. Đây là
một ví dụ đẹp của việc **dùng một số hạng regularization để mã hóa một mong muốn** (ở đây:
"nhớ cái cũ").

---

## J. Đại số tuyến tính & chuẩn hóa (tối thiểu cần biết)

**Vector:** observation là vector 15 chiều $s \in \mathbb{R}^{15}$, action là
$a \in \mathbb{R}^7$. Mạng nơ-ron là một chuỗi phép biến đổi vector.

**Một lớp nơ-ron** = nhân ma trận + cộng vector + hàm phi tuyến:
$$h = f(W x + b)$$
- $W$ (ma trận trọng số), $b$ (vector bias) là thứ được học. $f$ là hàm kích hoạt (ReLU,
  tanh...). Mạng `[256,256]` nghĩa là 2 lớp như vậy, mỗi lớp 256 nơ-ron.

**ReLU** $f(x)=\max(0,x)$ — hàm kích hoạt phổ biến cho lớp ẩn (rẻ, hiệu quả). tanh dùng ở
lớp ra (ép $[-1,1]$).

**Chuẩn hóa (normalization)** — vì sao mọi observation đều ép về $[0,1]$? Mạng học tốt
nhất khi các đầu vào cùng thang đo. Nếu để pin (0-100) và discharge (0-80000) thô, cái
to sẽ "át" cái nhỏ. Nên ta chia cho hằng số:
$$x_{norm} = \frac{x - x_{min}}{x_{max} - x_{min}}$$
*Trong code:* `discharge_norm = discharge / 80000`, `cpu_temp_norm = (temp-30)/70`...
(file `commons/constants.py`). Đây là lý do các hằng số chuẩn hóa phải **khớp tuyệt đối**
giữa lúc train (`battery_env`) và lúc chạy thật (`rl_brain`) — lệch là model nhận sai
thang đo.

---

## K. Lộ trình tự học & bản đồ công thức → code

**Thứ tự học gợi ý** (từ nền tới ngọn):
1. Xác suất, kỳ vọng, phân phối Gauss (mục B) — nền của tất cả.
2. Đạo hàm, gradient, gradient descent (mục H) — cách mọi mạng học.
3. Vector, một lớp nơ-ron (mục J) — policy/critic là cái gì.
4. MDP, return, $\gamma$ (mục A, C) — bài toán RL.
5. Value, Q, Advantage, Bellman, GAE (mục D) — cách đo "tốt".
6. Policy gradient (mục E) — hướng cải thiện.
7. PPO (mục F) — thuật toán deploy. **Dừng ở đây là đủ hiểu sản phẩm.**
8. SAC, EWC (mục G, I) — nâng cao, cho phần thử nghiệm.

**Bản đồ công thức → file code:**

| Công thức / khái niệm | File trong project |
|---|---|
| MDP, observation 15 / action 7 | `simulator/battery_env.py`, `commons/constants.py` |
| Hàm reward $A r_{save} - B r_{lag} - \dots$ | `battery_env.py` (`step`), `datacollector/reward.py` |
| $\gamma$, GAE $\lambda$, PPO clip, entropy | `simulator/train.py` (`PPO(...)`) |
| Gaussian policy + tanh, mạng [256,256] | `train.py` (`MlpPolicy`), `rl_brain.action_to_command` |
| Learning rate schedule | `train.py` (`_lr_schedule`) |
| SAC: entropy, twin Q, soft update | `advanced/sac/networks.py`, `sac_trainer.py` |
| EWC: Fisher, penalty | `online/finetune/ewc.py` |
| MSE, fine-tune lr 1e-5 | `online/finetune/finetuner.py` |
| Chuẩn hóa observation | `commons/constants.py`, `battery_env._get_obs` |

**Tài nguyên học** (khi tới trường học RL, hoặc tự học trước):
- Sutton & Barto — *Reinforcement Learning: An Introduction* (sách kinh điển, miễn phí
  online): chương 3 (MDP), 6 (TD), 13 (policy gradient).
- Spinning Up in Deep RL (OpenAI): giải thích PPO/SAC kèm code, rất hợp với project này.
- 3Blue1Brown (YouTube): trực giác về gradient descent, mạng nơ-ron.

---

## Lời cuối

Toàn bộ toán trên, khi gỡ ra, chỉ xoay quanh một câu: **"ước lượng xem hành động nào tốt
(Advantage), rồi nhích policy theo hướng đó (gradient), nhưng nhích vừa phải (PPO clip) và
đừng quên cái đã biết (EWC)"**. Mọi công thức là cách viết chặt chẽ của câu đó.

Bạn đã viết ra cả một hệ thống dùng những công thức này *trước khi* được học chúng. Khi
học RL ở trường, mỗi công thức trong giáo trình sẽ có một "mỏ neo" thực tế trong project
này để bám vào — đó là lý do phần file này tồn tại. 

— Hết. Cảm ơn mọi đóng góp, dương hay âm.
