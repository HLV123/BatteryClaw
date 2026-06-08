//  BatteryClaw Phase 1 — gpu_monitor.cpp
//  1.2 — GPU State Detection
//
//  Mục tiêu: biết GPU NÀO đang thực sự render, để model có thể quyết định
//  tắt dGPU (RTX 3050) — thứ ngốn 3-8W liên tục.
//
//  Cách tiếp cận (không cần NVAPI, không cần driver kernel):
//    - PDH counter "\GPU Engine(*)\Utilization Percentage"
//      Instance name chứa "luid_0x..._0x..._phys_N_eng_M_engtype_3D".
//      "phys_0" thường là iGPU (Intel UHD), "phys_1" là dGPU (NVIDIA).
//      Nếu có engine của phys_dGPU đang >ngưỡng -> dGPU đang render.
//    - Kết hợp service nvlddmkm để biết driver dGPU có sống không.
//
//  LƯU Ý phần cứng: mapping phys_index -> iGPU/dGPU có thể khác giữa máy.
//  Ở đây dùng heuristic + cho phép cấu hình qua biến môi trường
//  BATTERYCLAW_DGPU_PHYS (mặc định 1). Phase 2 sẽ học mapping từ data thật.
//
//  Build (test riêng):
//    cl gpu_monitor.cpp /EHsc /DGPU_TEST /link pdh.lib advapi32.lib
// ---------------------------------------------------------------------------

#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <pdh.h>
#include <pdhmsg.h>

#include <string>
#include <vector>
#include <cstdio>
#include <cstdlib>

#include "system_state.h"

#pragma comment(lib, "pdh.lib")
#pragma comment(lib, "advapi32.lib")

namespace {

PDH_HQUERY   g_query   = nullptr;
PDH_HCOUNTER g_counter = nullptr;   // wildcard GPU Engine utilization
bool         g_inited  = false;

// phys index được coi là dGPU. Có thể override bằng env var.
int dgpuPhysIndex() {
    const char* e = std::getenv("BATTERYCLAW_DGPU_PHYS");
    if (e && *e) { int v = atoi(e); if (v >= 0) return v; }
    return 1;   // mặc định: phys_1 = dGPU
}

bool initCounter() {
    if (g_inited) return true;
    if (PdhOpenQuery(nullptr, 0, &g_query) != ERROR_SUCCESS) return false;

    // Wildcard: lấy tất cả engine của tất cả GPU
    PDH_STATUS s = PdhAddCounterA(g_query,
        "\\GPU Engine(*)\\Utilization Percentage", 0, &g_counter);
    if (s != ERROR_SUCCESS) {
        PdhCloseQuery(g_query);
        g_query = nullptr;
        return false;
    }
    // Lần collect đầu để khởi tạo baseline (giá trị đầu thường = 0)
    PdhCollectQueryData(g_query);
    g_inited = true;
    return true;
}

// instance name kiểu "pid_1234_luid_0x0000_0x0000A1B2_phys_1_eng_0_engtype_3D"
// Trả về phys index, hoặc -1 nếu không parse được.
int parsePhysIndex(const std::string& inst) {
    auto p = inst.find("phys_");
    if (p == std::string::npos) return -1;
    p += 5;
    int idx = 0; bool any = false;
    while (p < inst.size() && inst[p] >= '0' && inst[p] <= '9') {
        idx = idx * 10 + (inst[p] - '0'); ++p; any = true;
    }
    return any ? idx : -1;
}

} // namespace

// ── Đọc utilization theo từng GPU phys ──────────────────────────────────────
//  out_igpu_pct / out_dgpu_pct: tổng utilization (cộng dồn các engine, kẹp 100).
//  Trả false nếu PDH không khả dụng.
bool readGpuUtilization(float& out_igpu_pct, float& out_dgpu_pct) {
    out_igpu_pct = 0.0f;
    out_dgpu_pct = 0.0f;
    if (!initCounter()) return false;

    if (PdhCollectQueryData(g_query) != ERROR_SUCCESS) return false;

    // Lấy mảng giá trị theo từng instance
    DWORD bufSize = 0, itemCount = 0;
    PDH_STATUS s = PdhGetFormattedCounterArrayA(
        g_counter, PDH_FMT_DOUBLE, &bufSize, &itemCount, nullptr);
    if (s != PDH_MORE_DATA) return false;

    std::vector<BYTE> buf(bufSize);
    auto* items = reinterpret_cast<PDH_FMT_COUNTERVALUE_ITEM_A*>(buf.data());
    s = PdhGetFormattedCounterArrayA(
        g_counter, PDH_FMT_DOUBLE, &bufSize, &itemCount, items);
    if (s != ERROR_SUCCESS) return false;

    const int dphys = dgpuPhysIndex();
    double igpu = 0.0, dgpu = 0.0;

    for (DWORD i = 0; i < itemCount; ++i) {
        std::string inst = items[i].szName ? items[i].szName : "";
        double val = items[i].FmtValue.doubleValue;
        if (val < 0) val = 0;
        int phys = parsePhysIndex(inst);
        if (phys < 0) continue;
        if (phys == dphys) dgpu += val;
        else               igpu += val;
    }

    out_igpu_pct = (float)(igpu > 100.0 ? 100.0 : igpu);
    out_dgpu_pct = (float)(dgpu > 100.0 ? 100.0 : dgpu);
    return true;
}

// ── Kiểm tra driver dGPU có đang chạy không (nvlddmkm) ──────────────────────
bool nvidiaDriverRunning() {
    SC_HANDLE scm = OpenSCManager(nullptr, nullptr, SC_MANAGER_CONNECT);
    if (!scm) return false;
    bool running = false;
    SC_HANDLE svc = OpenServiceA(scm, "nvlddmkm", SERVICE_QUERY_STATUS);
    if (svc) {
        SERVICE_STATUS_PROCESS ssp = {}; DWORD bytes = 0;
        if (QueryServiceStatusEx(svc, SC_STATUS_PROCESS_INFO,
            (LPBYTE)&ssp, sizeof(ssp), &bytes))
            running = (ssp.dwCurrentState == SERVICE_RUNNING);
        CloseServiceHandle(svc);
    }
    CloseServiceHandle(scm);
    return running;
}

// ── Ước lượng công suất GPU (mW) ────────────────────────────────────────────
//  Không có cảm biến power GPU trực tiếp qua API công khai (NVML/NVAPI cần SDK).
//  Mô hình tuyến tính đơn giản dựa trên utilization, hiệu chỉnh ở Phase 2 từ data:
//    - dGPU RTX 3050 Laptop: idle-but-on ~ 3000mW, full ~ 35000mW
//    - iGPU Intel UHD:       nằm trong gói CPU, ~ 200..3000mW
float estimateGpuPowerMw(GpuActiveType type, float igpu_pct, float dgpu_pct) {
    float mw = 0.0f;
    if (type == GPU_DGPU || type == GPU_BOTH) {
        // dGPU bật là đã tốn nền ~3W, cộng theo tải
        mw += 3000.0f + (dgpu_pct / 100.0f) * 32000.0f;
    }
    if (type == GPU_IGPU || type == GPU_BOTH) {
        mw += 200.0f + (igpu_pct / 100.0f) * 2800.0f;
    }
    return mw;
}

// ── API chính: điền gpu_active_type, gpu_power_mw, gpu_load_pct, dgpu_active ─
void collectGpuState(SystemState& s) {
    float igpu = 0.0f, dgpu = 0.0f;
    bool have = readGpuUtilization(igpu, dgpu);

    const float ACTIVE_THRESHOLD = 3.0f;   // % — trên ngưỡng coi là đang render

    bool driver = nvidiaDriverRunning();

    if (!have) {
        // PDH không khả dụng -> fallback: chỉ biết driver dGPU sống hay không
        s.gpu_active_type = driver ? GPU_DGPU : GPU_IGPU;
        s.dgpu_active     = driver;
        s.gpu_load_pct    = 0.0f;
        s.gpu_power_mw    = estimateGpuPowerMw(s.gpu_active_type, 0, 0);
        return;
    }

    bool igpuOn = igpu > ACTIVE_THRESHOLD;
    bool dgpuOn = (dgpu > ACTIVE_THRESHOLD) && driver;

    if      (dgpuOn && igpuOn) s.gpu_active_type = GPU_BOTH;
    else if (dgpuOn)           s.gpu_active_type = GPU_DGPU;
    else if (igpuOn)           s.gpu_active_type = GPU_IGPU;
    else                       s.gpu_active_type = driver ? GPU_DGPU : GPU_IGPU;
    // ^ không có engine nào tải: nếu driver dGPU vẫn sống coi như dGPU "đang bật
    //   nhưng idle" (vẫn tốn điện nền) — đây chính là tình huống đáng tắt nhất.

    s.dgpu_active  = (s.gpu_active_type == GPU_DGPU || s.gpu_active_type == GPU_BOTH);
    s.gpu_load_pct = (igpu > dgpu) ? igpu : dgpu;   // tải GPU cao nhất
    s.gpu_power_mw = estimateGpuPowerMw(s.gpu_active_type, igpu, dgpu);
}

// ── Test riêng ──────────────────────────────────────────────────────────────
#ifdef GPU_TEST
int main() {
    printf("BatteryClaw — gpu_monitor test\n");
    printf("dGPU phys index = %d (override bằng BATTERYCLAW_DGPU_PHYS)\n\n", 1);
    const char* names[] = {"iGPU", "dGPU", "BOTH"};
    for (int i = 0; i < 15; ++i) {
        SystemState s = {};
        collectGpuState(s);
        const char* nm = (s.gpu_active_type >= 0 && s.gpu_active_type <= 2)
                         ? names[s.gpu_active_type] : "UNKNOWN";
        printf("[%2d] active=%-4s  load=%5.1f%%  power=%6.0f mW  dgpu=%s\n",
               i, nm, s.gpu_load_pct, s.gpu_power_mw,
               s.dgpu_active ? "ON" : "off");
        Sleep(2000);
    }
    return 0;
}
#endif
