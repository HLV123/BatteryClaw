#pragma once
#include <string>
#include <cstdint>

// ─────────────────────────────────────────────
//  BatteryClaw — SystemState  (Phase 1)
//  Snapshot trạng thái máy tại một thời điểm.
//  Được chia sẻ qua Named Pipe tới RL Brain.
//
//  PHASE 1 — mở rộng so với bản gốc:
//    + Đo discharge rate THẬT bằng ACPI (ground truth, không còn baseline ảo)
//    + Phát hiện loại GPU đang render (iGPU / dGPU / cả hai)
//    + Đo công suất GPU riêng (gpu_power_mw)
//    + Thêm context: refresh rate, wifi, audio, process_count, ram, time_of_day
//  Observation vector mở rộng 7 → 15 chiều (xem rl_brain.state_to_obs)
// ─────────────────────────────────────────────

// Loại GPU đang thực sự render khung hình
enum GpuActiveType {
    GPU_UNKNOWN = -1,
    GPU_IGPU    = 0,   // chỉ Intel UHD (iGPU) — tiết kiệm nhất
    GPU_DGPU    = 1,   // chỉ RTX 3050 (dGPU) — tốn 3-8W
    GPU_BOTH    = 2,   // cả hai cùng hoạt động (Optimus đang chuyển tiếp)
};

struct SystemState {
    // ── CPU ──────────────────────────────────
    float   cpu_load_pct;       // 0‒100 %  (LoadPercentage WMI)
    int     cpu_clock_mhz;      // xung nhịp hiện tại (MHz)
    int     cpu_throttle_min;   // PROCTHROTTLEMIN hiện tại (%)
    int     cpu_throttle_max;   // PROCTHROTTLEMAX hiện tại (%)

    // ── GPU ──────────────────────────────────
    bool          dgpu_active;       // RTX 3050 đang dùng hay không (giữ cho tương thích)
    float         gpu_load_pct;      // 0‒100 % (PDH GPU Engine utilization)
    GpuActiveType gpu_active_type;   // [P1] iGPU / dGPU / cả hai
    float         gpu_power_mw;      // [P1] công suất GPU ước lượng (mW)

    // ── Pin ──────────────────────────────────
    int     battery_pct;        // 0‒100 %  tính từ Remaining/Full
    int     remaining_mwh;      // mWh còn lại (RemainingCapacity)
    int     full_charge_mwh;    // mWh đầy (FullChargedCapacity)
    bool    is_charging;        // đang sạc?
    bool    power_online;       // cắm điện?
    float   battery_health;     // Remaining/Designed * 100 %
    float   discharge_rate_mw;  // [P1] tốc độ XẢ THẬT (mW) đo bằng ACPI — GROUND TRUTH
                                //      >0 = đang xả; <=0 = đang sạc / không xác định

    // ── Nhiệt độ ─────────────────────────────
    float   cpu_temp_c;         // °C — từ MSAcpi (raw - 2732) / 10

    // ── Màn hình ─────────────────────────────
    int     brightness_pct;     // 0‒100 % (WMI WmiMonitorBrightness)
    int     screen_refresh_hz;  // [P1] 60 / 120 / 144 / 165 (EnumDisplaySettings)

    // ── Context ngoại vi (Phase 1) ───────────
    bool    wifi_active;        // [P1] WiFi adapter đang kết nối & truyền
    bool    audio_active;       // [P1] đang phát âm thanh (session active)
    int     process_count;      // [P1] số process đang chạy
    float   ram_pressure_pct;   // [P1] % RAM đang dùng (0‒100)
    float   time_of_day_norm;   // [P1] 0‒1 trong ngày (0=00:00, 1=24:00)

    // ── App đang chạy ─────────────────────────
    std::string foreground_app; // tên process cửa sổ đang active
    float   top_process_cpu;    // CPU% của process nặng nhất

    // ── Timestamp ────────────────────────────
    uint64_t timestamp_ms;      // GetTickCount64()
};

// Action mà RL Brain gửi xuống cho engine.
//
// PHASE 1 — mở rộng action space:
//   + gpu_switch     : điều khiển dGPU (iGPU / dGPU / giữ nguyên)
//   + refresh_rate   : ép tần số quét màn hình
//   + wifi_power_save: bật chế độ tiết kiệm điện WiFi
//   + charge_limit   : giới hạn % sạc để bảo vệ tuổi thọ pin
struct PolicyAction {
    int  cpu_throttle_max;      // 0‒100 % — set PROCTHROTTLEMAX
    int  cpu_throttle_min;      // 0‒100 % — set PROCTHROTTLEMIN
    int  brightness_pct;        // -1 = không đổi, 0‒100 = set
    bool defer_background_tasks;// tạm hoãn Windows Update, telemetry
    bool boost_disable;         // tắt Intel Turbo Boost

    // ── Phase 1 ──────────────────────────────
    int  gpu_switch;            // 0=ép iGPU, 1=cho phép dGPU, 2=giữ nguyên
    int  refresh_rate_mode;     // 0=60Hz, 1=120Hz, 2=max(giữ nguyên), -1=không đổi
    bool wifi_power_save;       // true = bật WiFi power saving
    int  charge_limit_pct;      // dừng sạc ở mức này (vd 80). -1=không giới hạn
};
