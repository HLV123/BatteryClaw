//  BatteryClaw — state_collector.cpp
//  Thu thập trạng thái hệ thống từ WMI + WinAPI
//  Máy: MSI, i7-11800H, RTX 3050 Laptop, Windows 11
//
//  Build: cl state_collector.cpp /EHsc /link wbemuuid.lib ole32.lib oleaut32.lib
// ─────────────────────────────────────────────────────────────────────────────

#define WIN32_LEAN_AND_MEAN
#define NOMINMAX        // tránh macro min/max của windows.h xung đột với std::
#include <windows.h>
#include <wbemidl.h>
#include <comdef.h>
#include <psapi.h>
#include <highlevelmonitorconfigurationapi.h>
#include <physicalmonitorenumerationapi.h>

#include <string>
#include <vector>
#include <algorithm>
#include <iostream>

#include "system_state.h"

#pragma comment(lib, "wbemuuid.lib")
#pragma comment(lib, "ole32.lib")
#pragma comment(lib, "oleaut32.lib")
#pragma comment(lib, "psapi.lib")

// ─── Phase 1 — các collector trong module riêng ────────────────────────────
//  power_monitor.cpp   : đo discharge rate thật (ACPI)
//  gpu_monitor.cpp     : phát hiện loại GPU + công suất GPU
//  context_collector.cpp: refresh/wifi/audio/process/ram/time
float collectDischargeRateMw(int remaining_mwh, bool charging);
void  collectGpuState(SystemState& s);
void  collectContext(SystemState& s);

// ─── WMI helper ────────────────────────────────────────────────────────────

class WmiConnection {
public:
    IWbemLocator*  pLoc  = nullptr;
    IWbemServices* pSvc  = nullptr;
    bool           ready = false;

    bool init(const wchar_t* ns = L"ROOT\\CIMV2") {
        HRESULT hr = CoInitializeEx(nullptr, COINIT_MULTITHREADED);
        if (FAILED(hr)) return false;

        hr = CoInitializeSecurity(nullptr, -1, nullptr, nullptr,
            RPC_C_AUTHN_LEVEL_DEFAULT, RPC_C_IMP_LEVEL_IMPERSONATE,
            nullptr, EOAC_NONE, nullptr);

        hr = CoCreateInstance(CLSID_WbemLocator, nullptr,
            CLSCTX_INPROC_SERVER, IID_IWbemLocator, (void**)&pLoc);
        if (FAILED(hr)) return false;

        hr = pLoc->ConnectServer(_bstr_t(ns), nullptr, nullptr, nullptr,
            0, nullptr, nullptr, &pSvc);
        if (FAILED(hr)) { pLoc->Release(); return false; }

        hr = CoSetProxyBlanket(pSvc, RPC_C_AUTHN_WINNT, RPC_C_AUTHZ_NONE,
            nullptr, RPC_C_AUTHN_LEVEL_CALL, RPC_C_IMP_LEVEL_IMPERSONATE,
            nullptr, EOAC_NONE);

        ready = SUCCEEDED(hr);
        return ready;
    }

    // Query đơn giản — trả về 1 row đầu tiên
    IWbemClassObject* queryFirst(const wchar_t* wql) {
        if (!ready) return nullptr;
        IEnumWbemClassObject* pEnum = nullptr;
        HRESULT hr = pSvc->ExecQuery(
            _bstr_t(L"WQL"), _bstr_t(wql),
            WBEM_FLAG_FORWARD_ONLY | WBEM_FLAG_RETURN_IMMEDIATELY,
            nullptr, &pEnum);
        if (FAILED(hr) || !pEnum) return nullptr;

        IWbemClassObject* obj = nullptr;
        ULONG ret = 0;
        pEnum->Next(WBEM_INFINITE, 1, &obj, &ret);
        pEnum->Release();
        return (ret == 1) ? obj : nullptr;
    }

    ~WmiConnection() {
        if (pSvc) pSvc->Release();
        if (pLoc) pLoc->Release();
        CoUninitialize();
    }
};

// Helper lấy property VARIANT từ WMI object
VARIANT getVar(IWbemClassObject* obj, const wchar_t* prop) {
    VARIANT v; VariantInit(&v);
    if (obj) obj->Get(prop, 0, &v, nullptr, nullptr);
    return v;
}

// ─── Đọc CPU ───────────────────────────────────────────────────────────────

void collectCpu(WmiConnection& wmi, SystemState& s) {
    IWbemClassObject* obj = wmi.queryFirst(
        L"SELECT LoadPercentage, CurrentClockSpeed FROM Win32_Processor");
    if (!obj) return;

    VARIANT v = getVar(obj, L"LoadPercentage");
    s.cpu_load_pct = (v.vt == VT_I4) ? (float)v.lVal :
                     (v.vt == VT_UI4) ? (float)v.ulVal : 0.f;
    VariantClear(&v);

    v = getVar(obj, L"CurrentClockSpeed");
    s.cpu_clock_mhz = (v.vt == VT_I4) ? v.lVal :
                      (v.vt == VT_UI4) ? (int)v.ulVal : 2304;
    VariantClear(&v);

    obj->Release();
}

// ─── Đọc CPU Throttle từ Registry ─────────────────────────────────────────
//  powercfg /query viết vào registry
//  HKLM\SYSTEM\CurrentControlSet\Control\Power\User\PowerSchemes\...

void collectCpuThrottle(SystemState& s) {
    // PROCTHROTTLEMAX (DC = pin)
    const char* subkey =
        "SYSTEM\\CurrentControlSet\\Control\\Power\\User\\PowerSchemes\\"
        "381b4222-f694-41f0-9685-ff5bb260df2e\\"   // Balanced GUID
        "54533251-82be-4824-96c1-47b60b740d00\\"   // SUB_PROCESSOR
        "bc5038f7-23e0-4960-96da-33abaf5935ec";    // PROCTHROTTLEMAX

    HKEY hKey;
    if (RegOpenKeyExA(HKEY_LOCAL_MACHINE, subkey, 0, KEY_READ, &hKey) == ERROR_SUCCESS) {
        DWORD val = 0, sz = sizeof(val);
        // DCSettingIndex = dùng pin
        if (RegQueryValueExA(hKey, "DCSettingIndex", nullptr, nullptr,
            (LPBYTE)&val, &sz) == ERROR_SUCCESS) {
            s.cpu_throttle_max = (int)val;
        }
        sz = sizeof(val);
        RegCloseKey(hKey);
    } else {
        s.cpu_throttle_max = 100; // default
    }

    const char* subkeyMin =
        "SYSTEM\\CurrentControlSet\\Control\\Power\\User\\PowerSchemes\\"
        "381b4222-f694-41f0-9685-ff5bb260df2e\\"
        "54533251-82be-4824-96c1-47b60b740d00\\"
        "893dee8e-2bef-41e0-89c6-b55d0929964c";    // PROCTHROTTLEMIN

    if (RegOpenKeyExA(HKEY_LOCAL_MACHINE, subkeyMin, 0, KEY_READ, &hKey) == ERROR_SUCCESS) {
        DWORD val = 0, sz = sizeof(val);
        if (RegQueryValueExA(hKey, "DCSettingIndex", nullptr, nullptr,
            (LPBYTE)&val, &sz) == ERROR_SUCCESS) {
            s.cpu_throttle_min = (int)val;
        }
        RegCloseKey(hKey);
    } else {
        s.cpu_throttle_min = 5;
    }
}

// ─── Đọc Pin ───────────────────────────────────────────────────────────────
//  Dùng WMI namespace root\WMI — khớp với máy MSI BIF0_9

void collectBattery(SystemState& s) {
    WmiConnection wmiPower;
    if (!wmiPower.init(L"ROOT\\WMI")) return;

    // BatteryStatus — trạng thái realtime
    IWbemClassObject* obj = wmiPower.queryFirst(
        L"SELECT Charging, Discharging, PowerOnline, RemainingCapacity, Voltage "
        L"FROM BatteryStatus");
    if (obj) {
        VARIANT v = getVar(obj, L"Charging");
        s.is_charging = (v.vt == VT_BOOL && v.boolVal != VARIANT_FALSE);
        VariantClear(&v);

        v = getVar(obj, L"PowerOnline");
        s.power_online = (v.vt == VT_BOOL && v.boolVal != VARIANT_FALSE);
        VariantClear(&v);

        v = getVar(obj, L"RemainingCapacity");
        s.remaining_mwh = (v.vt == VT_I4) ? v.lVal :
                          (v.vt == VT_UI4) ? (int)v.ulVal : 0;
        VariantClear(&v);

        obj->Release();
    }

    // BatteryFullChargedCapacity
    obj = wmiPower.queryFirst(
        L"SELECT FullChargedCapacity FROM BatteryFullChargedCapacity");
    if (obj) {
        VARIANT v = getVar(obj, L"FullChargedCapacity");
        s.full_charge_mwh = (v.vt == VT_I4) ? v.lVal :
                            (v.vt == VT_UI4) ? (int)v.ulVal : 33026;
        VariantClear(&v);
        obj->Release();
    }

    // Tính % pin
    if (s.full_charge_mwh > 0) {
        s.battery_pct = (int)(100.0f * s.remaining_mwh / s.full_charge_mwh);
        s.battery_pct = std::max(0, std::min(100, s.battery_pct));
    }

    // Sức khỏe pin (design = 52007 mWh — cứng cho máy MSI này)
    s.battery_health = (float)s.full_charge_mwh / 52007.0f * 100.0f;

    // [Phase 1] Tốc độ xả THẬT (mW) — ground truth thay cho baseline ảo
    s.discharge_rate_mw = collectDischargeRateMw(s.remaining_mwh, s.is_charging);
}

// ─── Đọc Nhiệt độ ──────────────────────────────────────────────────────────
//  MSAcpi_ThermalZoneTemperature: raw = tenths of Kelvin
//  °C = (raw - 2732) / 10

void collectTemperature(SystemState& s) {
    WmiConnection wmiAcpi;
    if (!wmiAcpi.init(L"ROOT\\WMI")) return;

    IWbemClassObject* obj = wmiAcpi.queryFirst(
        L"SELECT CurrentTemperature FROM MSAcpi_ThermalZoneTemperature");
    if (!obj) {
        s.cpu_temp_c = -1.f; // không đọc được
        return;
    }

    VARIANT v = getVar(obj, L"CurrentTemperature");
    DWORD raw = (v.vt == VT_I4) ? (DWORD)v.lVal :
                (v.vt == VT_UI4) ? v.ulVal : 2732;
    s.cpu_temp_c = (float)(raw - 2732) / 10.0f;
    VariantClear(&v);
    obj->Release();
}

// ─── Đọc Độ sáng màn hình ─────────────────────────────────────────────────
//  WmiMonitorBrightness — namespace root\WMI

void collectBrightness(SystemState& s) {
    WmiConnection wmiMon;
    if (!wmiMon.init(L"ROOT\\WMI")) { s.brightness_pct = -1; return; }

    IWbemClassObject* obj = wmiMon.queryFirst(
        L"SELECT CurrentBrightness FROM WmiMonitorBrightness");
    if (!obj) { s.brightness_pct = -1; return; }

    VARIANT v = getVar(obj, L"CurrentBrightness");
    s.brightness_pct = (v.vt == VT_UI1) ? (int)v.bVal :
                       (v.vt == VT_I4)  ? v.lVal  : -1;
    VariantClear(&v);
    obj->Release();
}

// ─── Đọc App đang active + top CPU process ─────────────────────────────────

void collectProcesses(SystemState& s) {
    // Foreground window
    HWND fg = GetForegroundWindow();
    if (fg) {
        DWORD pid = 0;
        GetWindowThreadProcessId(fg, &pid);
        HANDLE h = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, FALSE, pid);
        if (h) {
            char buf[256] = {};
            DWORD sz = sizeof(buf);
            if (QueryFullProcessImageNameA(h, 0, buf, &sz)) {
                std::string full(buf);
                auto pos = full.rfind('\\');
                s.foreground_app = (pos != std::string::npos)
                    ? full.substr(pos + 1) : full;
            }
            CloseHandle(h);
        }
    }

    // Top CPU process (snapshot đơn giản)
    DWORD pids[1024]; DWORD needed = 0;
    EnumProcesses(pids, sizeof(pids), &needed);
    DWORD count = needed / sizeof(DWORD);

    float maxCpu = 0;
    for (DWORD i = 0; i < count; i++) {
        HANDLE h = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, FALSE, pids[i]);
        if (!h) continue;
        FILETIME c, e, k, u;
        if (GetProcessTimes(h, &c, &e, &k, &u)) {
            ULARGE_INTEGER ui;
            ui.LowPart  = u.dwLowDateTime;
            ui.HighPart = u.dwHighDateTime;
            float cpu = (float)(ui.QuadPart / 10000.0);  // ms
            if (cpu > maxCpu) maxCpu = cpu;
        }
        CloseHandle(h);
    }
    s.top_process_cpu = maxCpu;
}

// ─── [Phase 1] dGPU detection chuyển sang gpu_monitor.cpp ──────────────────
//  Hàm collectGpu() cũ chỉ kiểm tra service nvlddmkm (không biết GPU nào render).
//  Phase 1 dùng collectGpuState() đọc PDH GPU Engine để phân biệt iGPU/dGPU,
//  ước lượng gpu_power_mw, và điền gpu_active_type. Xem gpu_monitor.cpp.

// ─── Entry point chính ─────────────────────────────────────────────────────

SystemState collectState() {
    SystemState s = {};
    s.timestamp_ms = GetTickCount64();

    WmiConnection wmiCimv2;
    wmiCimv2.init(L"ROOT\\CIMV2");

    collectCpu(wmiCimv2, s);
    collectCpuThrottle(s);
    collectBattery(s);
    collectTemperature(s);
    collectBrightness(s);
    collectProcesses(s);
    collectGpuState(s);   // [P1] phân biệt iGPU/dGPU + công suất + tải
    collectContext(s);    // [P1] refresh/wifi/audio/process/ram/time

    return s;
}

// ─── Debug print (bỏ khi tích hợp vào IPC) ────────────────────────────────

void printState(const SystemState& s) {
    const char* gpuNames[] = {"iGPU", "dGPU", "BOTH"};
    const char* gn = (s.gpu_active_type >= 0 && s.gpu_active_type <= 2)
                     ? gpuNames[s.gpu_active_type] : "?";
    printf("═══════ BatteryClaw State (Phase 1) ═══════\n");
    printf("CPU     : %.1f%%  @%d MHz  throttle=[%d%%~%d%%]\n",
        s.cpu_load_pct, s.cpu_clock_mhz, s.cpu_throttle_min, s.cpu_throttle_max);
    printf("Temp    : %.1f°C\n", s.cpu_temp_c);
    printf("Battery : %d%%  (%d/%d mWh)  %s  health=%.0f%%\n",
        s.battery_pct, s.remaining_mwh, s.full_charge_mwh,
        s.is_charging ? "CHARGING" : (s.power_online ? "PLUGGED" : "ON BATTERY"),
        s.battery_health);
    printf("Discharge: %.0f mW  (do that bang ACPI)\n", s.discharge_rate_mw);
    printf("Bright  : %d%%   Refresh: %d Hz\n", s.brightness_pct, s.screen_refresh_hz);
    printf("GPU     : active=%s  load=%.1f%%  power=%.0f mW  (dgpu=%s)\n",
        gn, s.gpu_load_pct, s.gpu_power_mw, s.dgpu_active ? "ON" : "off");
    printf("Context : wifi=%d audio=%d procs=%d ram=%.0f%% tod=%.3f\n",
        s.wifi_active, s.audio_active, s.process_count,
        s.ram_pressure_pct, s.time_of_day_norm);
    printf("FG App  : %s\n", s.foreground_app.c_str());
    printf("Time    : %llu ms\n", s.timestamp_ms);
    printf("═════════════════════════════════\n");
}

#if !defined(NO_MAIN_SC) && !defined(BUILDING_DLL)
int main() {
    printf("BatteryClaw — state_collector test\n");
    printf("Collecting system state...\n\n");

    SystemState state = collectState();
    printState(state);

    printf("\nPress Enter to collect again...\n");
    while (getchar() != EOF) {
        state = collectState();
        printState(state);
        printf("\nPress Enter...\n");
    }
    return 0;
}
#endif // NO_MAIN_SC / BUILDING_DLL
