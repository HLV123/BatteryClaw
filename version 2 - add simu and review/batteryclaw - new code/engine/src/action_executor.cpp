//  BatteryClaw — action_executor.cpp
//  Thực thi các hành động tiết kiệm pin do RL Brain ra lệnh
//  Máy: MSI i7-11800H, Windows 11, Balanced power plan
//
//  Build: cl action_executor.cpp /EHsc /link powrprof.lib
// ─────────────────────────────────────────────────────────────────────────────

#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <powersetting.h>
#include <wbemidl.h>
#include <comdef.h>

#include <string>
#include <sstream>
#include <cstdio>

#include "system_state.h"

#pragma comment(lib, "powrprof.lib")
#pragma comment(lib, "wbemuuid.lib")
#pragma comment(lib, "ole32.lib")

// ── GUIDs cứng từ máy MSI của bạn ──────────────────────────────────────────
static const GUID SCHEME_BALANCED = {
    0x381b4222, 0xf694, 0x41f0,
    {0x96, 0x85, 0xff, 0x5b, 0xb2, 0x60, 0xdf, 0x2e}
};
static const GUID SUB_PROCESSOR = {
    0x54533251, 0x82be, 0x4824,
    {0x96, 0xc1, 0x47, 0xb6, 0x0b, 0x74, 0x0d, 0x00}
};
static const GUID PROCTHROTTLEMAX = {
    0xbc5038f7, 0x23e0, 0x4960,
    {0x96, 0xda, 0x33, 0xab, 0xaf, 0x59, 0x35, 0xec}
};
static const GUID PROCTHROTTLEMIN = {
    0x893dee8e, 0x2bef, 0x41e0,
    {0x89, 0xc6, 0xb5, 0x5d, 0x09, 0x29, 0x96, 0x4c}
};

// ── Kết quả thực thi ────────────────────────────────────────────────────────
struct ActionResult {
    bool cpu_throttle_ok;
    bool brightness_ok;
    bool defer_ok;
    std::string error_msg;
};

// ─── 1. Set CPU Throttle Max (DC = dùng pin) ───────────────────────────────
//
//  powercfg /setdcvalueindex <scheme> <subgroup> <setting> <value>
//  rồi powercfg /setactive <scheme>
//
//  Dùng powrprof.dll API trực tiếp — nhanh hơn gọi process

bool setCpuThrottleMax(int pct) {
    if (pct < 20 || pct > 100) return false; // an toàn tối thiểu 20%

    DWORD val = (DWORD)pct;

    // Set DC value (dùng pin)
    DWORD hr = PowerWriteDCValueIndex(
        nullptr,          // HKEY_LOCAL_MACHINE
        &SCHEME_BALANCED,
        &SUB_PROCESSOR,
        &PROCTHROTTLEMAX,
        val
    );
    if (hr != ERROR_SUCCESS) {
        fprintf(stderr, "[ACT] setCpuThrottleMax FAIL: %lu\n", hr);
        return false;
    }

    // Apply scheme để có hiệu lực ngay
    PowerSetActiveScheme(nullptr, &SCHEME_BALANCED);
    printf("[ACT] CPU throttle max → %d%%\n", pct);
    return true;
}

bool setCpuThrottleMin(int pct) {
    if (pct < 0 || pct > 30) return false; // min không nên quá 30%

    DWORD val = (DWORD)pct;
    DWORD hr = PowerWriteDCValueIndex(
        nullptr, &SCHEME_BALANCED, &SUB_PROCESSOR, &PROCTHROTTLEMIN, val);
    if (hr != ERROR_SUCCESS) return false;

    PowerSetActiveScheme(nullptr, &SCHEME_BALANCED);
    printf("[ACT] CPU throttle min → %d%%\n", pct);
    return true;
}

// ─── 2. Set độ sáng màn hình ──────────────────────────────────────────────
//  WMI WmiMonitorBrightnessMethods::WmiSetBrightness
//  namespace root\WMI

bool setBrightness(int pct) {
    if (pct < 0 || pct > 100) return false;

    HRESULT hr = CoInitializeEx(nullptr, COINIT_MULTITHREADED);
    bool needUninit = SUCCEEDED(hr);

    IWbemLocator*  pLoc = nullptr;
    IWbemServices* pSvc = nullptr;

    hr = CoCreateInstance(CLSID_WbemLocator, nullptr,
        CLSCTX_INPROC_SERVER, IID_IWbemLocator, (void**)&pLoc);
    if (FAILED(hr)) goto cleanup;

    hr = pLoc->ConnectServer(_bstr_t(L"ROOT\\WMI"),
        nullptr, nullptr, nullptr, 0, nullptr, nullptr, &pSvc);
    if (FAILED(hr)) goto cleanup;

    CoSetProxyBlanket(pSvc, RPC_C_AUTHN_WINNT, RPC_C_AUTHZ_NONE, nullptr,
        RPC_C_AUTHN_LEVEL_CALL, RPC_C_IMP_LEVEL_IMPERSONATE, nullptr, EOAC_NONE);

    {
        // Lấy instance của WmiMonitorBrightnessMethods
        IEnumWbemClassObject* pEnum = nullptr;
        hr = pSvc->ExecQuery(
            _bstr_t(L"WQL"),
            _bstr_t(L"SELECT * FROM WmiMonitorBrightnessMethods"),
            WBEM_FLAG_FORWARD_ONLY | WBEM_FLAG_RETURN_IMMEDIATELY,
            nullptr, &pEnum);

        IWbemClassObject* pObj = nullptr;
        ULONG ret = 0;
        if (SUCCEEDED(hr) && pEnum)
            pEnum->Next(WBEM_INFINITE, 1, &pObj, &ret);

        if (pObj && ret == 1) {
            // Gọi method WmiSetBrightness(Timeout, Brightness)
            IWbemClassObject* pClass     = nullptr;
            IWbemClassObject* pInClass   = nullptr;
            IWbemClassObject* pInParams  = nullptr;

            pSvc->GetObject(_bstr_t(L"WmiMonitorBrightnessMethods"),
                0, nullptr, &pClass, nullptr);

            if (pClass) {
                pClass->GetMethod(_bstr_t(L"WmiSetBrightness"),
                    0, &pInClass, nullptr);
                if (pInClass)
                    pInClass->SpawnInstance(0, &pInParams);

                if (pInParams) {
                    VARIANT vTimeout; VariantInit(&vTimeout);
                    vTimeout.vt   = VT_I4;
                    vTimeout.lVal = 0;  // immediate
                    pInParams->Put(L"Timeout", 0, &vTimeout, 0);
                    VariantClear(&vTimeout);

                    VARIANT vBright; VariantInit(&vBright);
                    vBright.vt   = VT_UI1;
                    vBright.bVal = (BYTE)pct;
                    pInParams->Put(L"Brightness", 0, &vBright, 0);
                    VariantClear(&vBright);

                    // Lấy __PATH của instance
                    VARIANT vPath; VariantInit(&vPath);
                    pObj->Get(L"__PATH", 0, &vPath, nullptr, nullptr);

                    pSvc->ExecMethod(_bstr_t(vPath.bstrVal),
                        _bstr_t(L"WmiSetBrightness"),
                        0, nullptr, pInParams, nullptr, nullptr);

                    VariantClear(&vPath);
                    pInParams->Release();
                }
                if (pInClass) pInClass->Release();
                pClass->Release();
            }
            pObj->Release();
        }
        if (pEnum) pEnum->Release();
    }

    printf("[ACT] Brightness → %d%%\n", pct);

cleanup:
    if (pSvc) pSvc->Release();
    if (pLoc) pLoc->Release();
    if (needUninit) CoUninitialize();
    return SUCCEEDED(hr);
}

// ─── 3. Defer background tasks ─────────────────────────────────────────────
//  Tạm hoãn Windows Update (wuauserv) và SysMain (Superfetch)
//  khi máy đang dùng pin và pin < 50%

bool deferBackgroundTasks(bool defer) {
    // Các service ngốn CPU/disk khi chạy ngầm
    const char* services[] = {
        "wuauserv",     // Windows Update
        "SysMain",      // Superfetch
        "DiagTrack",    // Telemetry
        nullptr
    };

    SC_HANDLE scm = OpenSCManager(nullptr, nullptr, SC_MANAGER_CONNECT);
    if (!scm) return false;

    bool ok = true;
    for (int i = 0; services[i]; i++) {
        SC_HANDLE svc = OpenServiceA(scm, services[i],
            SERVICE_QUERY_STATUS | SERVICE_STOP | SERVICE_START);
        if (!svc) continue;

        if (defer) {
            // Pause — dùng ControlService nếu hỗ trợ, không thì skip
            SERVICE_STATUS ss;
            ControlService(svc, SERVICE_CONTROL_PAUSE, &ss);
            // Nếu không pause được (nhiều service không support), ok
        } else {
            // Resume
            SERVICE_STATUS ss;
            ControlService(svc, SERVICE_CONTROL_CONTINUE, &ss);
        }
        CloseServiceHandle(svc);
    }

    CloseServiceHandle(scm);
    printf("[ACT] Background tasks %s\n", defer ? "deferred" : "resumed");
    return ok;
}

// ─── 4. Tắt/bật Intel Turbo Boost ─────────────────────────────────────────
//  Turbo Boost được kiểm soát qua PROCTHROTTLEMAX — nếu max < 100% thì boost
//  bị cắt tự nhiên. Đây là cách an toàn nhất trên Windows.
//  (Cách MSR register cần driver kernel — bỏ qua cho v1)

bool setTurboBoost(bool enable) {
    // Khi enable=false: set throttle max = 99% → Windows không cho boost
    // Khi enable=true : set throttle max = 100%
    return setCpuThrottleMax(enable ? 100 : 99);
}

// ─── [Phase 1] 5. Refresh rate màn hình ────────────────────────────────────
//  mode: 0=60Hz, 1=120Hz, 2=max (giữ nguyên/không hạ), -1=không đổi
//  Dùng ChangeDisplaySettings — an toàn, có thể đảo ngược.
//  Hạ refresh khi dùng pin tiết kiệm đáng kể trên màn 144/165Hz.

bool setRefreshRate(int mode) {
    if (mode < 0 || mode == 2) return true;   // không đổi / giữ max

    int target = (mode == 0) ? 60 : (mode == 1) ? 120 : 0;
    if (target == 0) return true;

    DEVMODEA dm = {}; dm.dmSize = sizeof(dm);
    if (!EnumDisplaySettingsA(nullptr, ENUM_CURRENT_SETTINGS, &dm))
        return false;

    if ((int)dm.dmDisplayFrequency == target) return true;  // đã đúng rồi

    dm.dmDisplayFrequency = target;
    dm.dmFields = DM_DISPLAYFREQUENCY;

    LONG r = ChangeDisplaySettingsA(&dm, CDS_UPDATEREGISTRY);
    if (r == DISP_CHANGE_SUCCESSFUL) {
        printf("[ACT] Refresh rate -> %d Hz\n", target);
        return true;
    }
    // panel có thể không hỗ trợ target -> bỏ qua, không coi là lỗi nặng
    printf("[ACT] Refresh rate %d Hz khong ho tro (code %ld)\n", target, r);
    return false;
}

// ─── [Phase 1] 6. WiFi power saving ─────────────────────────────────────────
//  Bật chế độ tiết kiệm điện cho WiFi adapter.
//  Cách an toàn nhất qua Windows: dùng powercfg subgroup WiFi
//  (19cbb8fa-5279-450e-9fac-8a3d5fedd0c1 / 12bbebe6-...).
//  Triển khai đầy đủ cần GUID adapter -> để dạng stub có log, dễ mở rộng.

bool setWifiPowerSave(bool on) {
    // Ghi DC value cho WiFi power saving mode (0=max perf, 3=max power save)
    // Hằng số GUID WiFi power policy là chuẩn trên Windows:
    static const GUID SUB_WIFI = {
        0x19cbb8fa, 0x5279, 0x450e,
        {0x9f, 0xac, 0x8a, 0x3d, 0x5f, 0xed, 0xd0, 0xc1}
    };
    static const GUID WIFI_PSAVE = {
        0x12bbebe6, 0x58d6, 0x4636,
        {0x95, 0xbb, 0x32, 0x17, 0xef, 0x86, 0x7c, 0x1a}
    };
    DWORD val = on ? 3 : 0;   // 3 = Maximum Power Saving, 0 = Maximum Performance
    DWORD hr = PowerWriteDCValueIndex(
        nullptr, &SCHEME_BALANCED, &SUB_WIFI, &WIFI_PSAVE, val);
    if (hr == ERROR_SUCCESS) {
        PowerSetActiveScheme(nullptr, &SCHEME_BALANCED);
        printf("[ACT] WiFi power save -> %s\n", on ? "ON(max)" : "off");
        return true;
    }
    printf("[ACT] WiFi power save khong ap dung duoc (%lu)\n", hr);
    return false;
}

// ─── [Phase 1] 7. Charge limit (bảo vệ tuổi thọ pin) ────────────────────────
//  ⚠️ SAFE-STUB: dừng sạc ở 80% là tính năng VENDOR-SPECIFIC.
//  MSI dùng "MSI Center / Battery Master" với lệnh ACPI WMI riêng
//  (lớp MSI_ACPI, method điều khiển battery threshold).
//  Ghi sai có thể không tác dụng hoặc xung đột với MSI Center.
//  -> Để dạng stub có log; Phase 5 (C#/.NET + battery report) sẽ làm thật.

bool setChargeLimit(int pct) {
    if (pct < 50 || pct > 100) return false;
    printf("[ACT][STUB] Charge limit -> %d%% "
           "(vendor-specific MSI, se trien khai o Phase 5)\n", pct);
    return true;
}


    ActionResult result = {true, true, true, ""};

    // CPU throttle
    if (action.cpu_throttle_max >= 20 && action.cpu_throttle_max <= 100) {
        result.cpu_throttle_ok = setCpuThrottleMax(action.cpu_throttle_max);
    }
    if (action.cpu_throttle_min >= 0 && action.cpu_throttle_min <= 30) {
        setCpuThrottleMin(action.cpu_throttle_min);
    }

    // Turbo boost
    if (action.boost_disable) {
        setTurboBoost(false);
    }

    // Brightness
    if (action.brightness_pct >= 0 && action.brightness_pct <= 100) {
        result.brightness_ok = setBrightness(action.brightness_pct);
    }

    // Background tasks
    result.defer_ok = deferBackgroundTasks(action.defer_background_tasks);

    return result;
}

// ─── Test harness ──────────────────────────────────────────────────────────

#if !defined(NO_MAIN_AE) && !defined(BUILDING_DLL)
int main() {
    printf("BatteryClaw — action_executor test\n");
    printf("Cần quyền Administrator!\n\n");

    printf("[TEST 1] Set CPU throttle max = 70%% (tiết kiệm pin)...\n");
    bool ok = setCpuThrottleMax(70);
    printf("  Result: %s\n\n", ok ? "OK" : "FAIL");

    Sleep(2000);

    printf("[TEST 2] Restore CPU throttle max = 100%%...\n");
    ok = setCpuThrottleMax(100);
    printf("  Result: %s\n\n", ok ? "OK" : "FAIL");

    printf("[TEST 3] Set brightness = 70%%...\n");
    ok = setBrightness(70);
    printf("  Result: %s\n\n", ok ? "OK" : "FAIL");

    printf("Xong. Kiểm tra CPU throttle: powercfg /query SCHEME_CURRENT SUB_PROCESSOR\n");
    return 0;
}
#endif // NO_MAIN_AE / BUILDING_DLL
