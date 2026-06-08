//  BatteryClaw Phase 1 — gpu_switch.cpp
//  1.3 — GPU Switching Action  (HÀNH ĐỘNG QUAN TRỌNG NHẤT)
//
//  Bật/tắt dGPU (RTX 3050) để tiết kiệm 3-8W liên tục.
//
//  ⚠️ TRẠNG THÁI: SAFE-STUB CÓ KIỂM SOÁT
//  ----------------------------------------------------------------------------
//  Phần PHÁT HIỆN và LỚP BẢO VỆ là THẬT và chạy được ngay:
//    - canDisableDgpu(): quét process đang dùng CUDA/render trên dGPU
//    - các guard: không tắt khi đang game, đang có tiến trình CUDA
//  Phần GHI cấu hình phần cứng (registry Optimus / PnP enable-disable /
//  ACPI MUX) bị KHOÁ sau cờ g_hardware_writes_enabled = false.
//
//  LÝ DO: tắt/disable sai dGPU qua PnP có thể gây mất hiển thị, treo máy,
//  hoặc cần khởi động lại. Cần kiểm thử trên đúng máy MSI trước khi mở khoá.
//  Khi đã test an toàn trên máy thật, build với -DBATTERYCLAW_ENABLE_HW_GPU_SWITCH
//  để bật các thao tác thật.
//
//  Build (test riêng):
//    cl gpu_switch.cpp /EHsc /DSW_TEST /link advapi32.lib psapi.lib
// ---------------------------------------------------------------------------

#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <psapi.h>
#include <tlhelp32.h>

#include <string>
#include <vector>
#include <algorithm>
#include <cctype>
#include <cstdio>

#include "system_state.h"

#pragma comment(lib, "advapi32.lib")
#pragma comment(lib, "psapi.lib")

namespace {

// Cờ tổng: có cho phép GHI cấu hình phần cứng thật hay không.
// Mặc định FALSE = safe-stub. Bật bằng macro lúc build.
#ifdef BATTERYCLAW_ENABLE_HW_GPU_SWITCH
constexpr bool g_hardware_writes_enabled = true;
#else
constexpr bool g_hardware_writes_enabled = false;
#endif

std::string toLower(std::string s) {
    std::transform(s.begin(), s.end(), s.begin(),
        [](unsigned char c){ return (char)std::tolower(c); });
    return s;
}

// Module DLL gợi ý một process đang dùng dGPU NVIDIA / CUDA.
// Nếu process nào đã nạp các DLL này -> KHÔNG được tắt dGPU.
const std::vector<std::string> DGPU_DLL_HINTS = {
    "nvcuda.dll", "cudart", "nvml.dll", "nvapi64.dll",
    "cublas", "cudnn", "d3d12.dll" /* nhiều game/đồ hoạ nặng */,
};

// Tên process nặng đồ hoạ điển hình (lớp bảo vệ thứ hai, rẻ hơn).
const std::vector<std::string> DGPU_PROC_HINTS = {
    "blender", "davinci", "premiere", "aftereffects", "obs64",
    "unrealeditor", "unity", "ollama", "python", // python có thể chạy CUDA
};

bool processUsesDgpu(DWORD pid) {
    HANDLE h = OpenProcess(PROCESS_QUERY_INFORMATION | PROCESS_VM_READ,
                           FALSE, pid);
    if (!h) return false;

    bool uses = false;
    HMODULE mods[1024]; DWORD needed = 0;
    if (EnumProcessModulesEx(h, mods, sizeof(mods), &needed, LIST_MODULES_ALL)) {
        DWORD n = needed / sizeof(HMODULE);
        for (DWORD i = 0; i < n && !uses; ++i) {
            char name[MAX_PATH] = {};
            if (GetModuleBaseNameA(h, mods[i], name, sizeof(name))) {
                std::string low = toLower(name);
                for (const auto& hint : DGPU_DLL_HINTS)
                    if (low.find(hint) != std::string::npos) { uses = true; break; }
            }
        }
    }
    CloseHandle(h);
    return uses;
}

} // namespace

// ── LỚP BẢO VỆ: có an toàn để tắt dGPU bây giờ không? ───────────────────────
//  Trả false (KHÔNG tắt) nếu:
//    - đang ở workload game
//    - có process đang nạp CUDA/NVML/nvapi (đang tính toán/ render trên dGPU)
//  reason: điền lý do để log.
bool canDisableDgpu(const SystemState& s, std::string& reason) {
    // Guard 1: workload game (foreground app gợi ý)
    {
        std::string fg = toLower(s.foreground_app);
        for (const auto& g : DGPU_PROC_HINTS) {
            if (fg.find(g) != std::string::npos) {
                reason = "foreground app co the dung dGPU: " + s.foreground_app;
                return false;
            }
        }
    }

    // Guard 2: quét toàn hệ thống tìm process đang dùng CUDA/NVAPI
    DWORD pids[2048]; DWORD needed = 0;
    if (EnumProcesses(pids, sizeof(pids), &needed)) {
        DWORD count = needed / sizeof(DWORD);
        for (DWORD i = 0; i < count; ++i) {
            if (pids[i] == 0) continue;
            if (processUsesDgpu(pids[i])) {
                char buf[64];
                snprintf(buf, sizeof(buf), "PID %lu dang dung CUDA/NVAPI", pids[i]);
                reason = buf;
                return false;
            }
        }
    }

    reason = "an toan de tat dGPU";
    return true;
}

// ── Thao tác THẬT (bị khoá ở safe-stub) ─────────────────────────────────────
//  Cách Optimus: ghi profile NVIDIA để ép ứng dụng dùng iGPU.
//  Cách MUX: ghi ACPI vendor-specific (rất phụ thuộc MSI/BIOS).
//  Ở đây để dạng stub có log rõ ràng. Mở khoá bằng macro build.

static bool hwForceIgpu() {
    if (!g_hardware_writes_enabled) {
        printf("[GPU][STUB] (an toan) Se ep iGPU: ghi NVIDIA Optimus profile / MUX.\n");
        printf("           -> Hien bi khoa. Build voi -DBATTERYCLAW_ENABLE_HW_GPU_SWITCH de bat.\n");
        return true; // báo "thành công ở mức stub" để pipeline phía trên chạy tiếp
    }
    // ─────────────────────────────────────────────────────────────────────
    // THẬT: chỗ này sẽ ghi registry Optimus / gọi PnP / ACPI MUX.
    // CHƯA KÍCH HOẠT cho tới khi kiểm thử trên máy MSI thật.
    // Ví dụ hướng triển khai (cần xác thực phần cứng):
    //   - HKLM\SOFTWARE\NVIDIA Corporation\Global\NVTweak  (Optimus app profile)
    //   - SetupDiSetClassInstallParams + DICS_DISABLE  (PnP disable dGPU)
    //   - ACPI _DSM vendor method qua driver MSI
    // ─────────────────────────────────────────────────────────────────────
    printf("[GPU][HW] (CHUA TRIEN KHAI) ghi cau hinh ep iGPU.\n");
    return false;
}

static bool hwAllowDgpu() {
    if (!g_hardware_writes_enabled) {
        printf("[GPU][STUB] (an toan) Se cho phep dGPU hoat dong tro lai.\n");
        return true;
    }
    printf("[GPU][HW] (CHUA TRIEN KHAI) cho phep dGPU.\n");
    return false;
}

// ── API chính: thực thi gpu_switch action ───────────────────────────────────
//  mode: 0 = ép iGPU (tắt dGPU), 1 = cho phép dGPU, 2 = giữ nguyên.
//  Trả true nếu xử lý xong (kể cả khi quyết định KHÔNG đổi vì guard).
bool executeGpuSwitch(int mode, const SystemState& s) {
    if (mode == 2) return true;  // giữ nguyên

    if (mode == 0) {             // muốn tắt dGPU
        std::string reason;
        if (!canDisableDgpu(s, reason)) {
            printf("[GPU] BO QUA tat dGPU: %s\n", reason.c_str());
            return true;         // tôn trọng guard, không coi là lỗi
        }
        printf("[GPU] Tat dGPU (ly do an toan: %s)\n", reason.c_str());
        return hwForceIgpu();
    }

    if (mode == 1) {             // cho phép dGPU
        return hwAllowDgpu();
    }
    return false;
}

// ── Test riêng ──────────────────────────────────────────────────────────────
#ifdef SW_TEST
int main() {
    printf("BatteryClaw — gpu_switch test (safe-stub)\n\n");
    SystemState s = {};
    s.foreground_app = "chrome.exe";

    std::string reason;
    bool ok = canDisableDgpu(s, reason);
    printf("canDisableDgpu = %s (%s)\n\n", ok ? "true" : "false", reason.c_str());

    printf("--- mode 0 (ep iGPU) ---\n");
    executeGpuSwitch(0, s);
    printf("\n--- mode 1 (cho phep dGPU) ---\n");
    executeGpuSwitch(1, s);
    printf("\n--- mode 2 (giu nguyen) ---\n");
    executeGpuSwitch(2, s);
    return 0;
}
#endif
