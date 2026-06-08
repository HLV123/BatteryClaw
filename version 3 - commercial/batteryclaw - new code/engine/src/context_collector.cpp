//  BatteryClaw Phase 1 — context_collector.cpp
//  1.4 — Expanded State Space (phần context ngoại vi)
//
//  Điền các trường mới của SystemState:
//    screen_refresh_hz, wifi_active, audio_active,
//    process_count, ram_pressure_pct, time_of_day_norm
//
//  Tất cả dùng WinAPI thuần (không WMI) -> nhẹ, không CoInitialize.
//
//  Build (test riêng):
//    cl context_collector.cpp /EHsc /DCTX_TEST /link user32.lib psapi.lib iphlpapi.lib ole32.lib
// ---------------------------------------------------------------------------

#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <psapi.h>
#include <iphlpapi.h>
#include <mmdeviceapi.h>
#include <audiopolicy.h>

#include <ctime>
#include <cstdio>
#include <vector>

#include "system_state.h"

#pragma comment(lib, "user32.lib")
#pragma comment(lib, "psapi.lib")
#pragma comment(lib, "iphlpapi.lib")
#pragma comment(lib, "ole32.lib")

// ── Refresh rate màn hình chính ─────────────────────────────────────────────
int collectRefreshHz() {
    DEVMODEA dm = {}; dm.dmSize = sizeof(dm);
    if (EnumDisplaySettingsA(nullptr, ENUM_CURRENT_SETTINGS, &dm))
        return (int)dm.dmDisplayFrequency;   // Hz
    return 60;
}

// ── WiFi đang kết nối & hoạt động ───────────────────────────────────────────
//  Heuristic nhẹ: có adapter loại IEEE80211 đang ở trạng thái operational.
bool collectWifiActive() {
    ULONG sz = 0;
    GetAdaptersAddresses(AF_UNSPEC, GAA_FLAG_SKIP_DNS_SERVER,
                         nullptr, nullptr, &sz);
    if (sz == 0) return false;

    std::vector<BYTE> buf(sz);
    auto* addrs = reinterpret_cast<IP_ADAPTER_ADDRESSES*>(buf.data());
    if (GetAdaptersAddresses(AF_UNSPEC, GAA_FLAG_SKIP_DNS_SERVER,
                             nullptr, addrs, &sz) != NO_ERROR)
        return false;

    for (auto* a = addrs; a; a = a->Next) {
        if (a->IfType == IF_TYPE_IEEE80211 &&
            a->OperStatus == IfOperStatusUp)
            return true;
    }
    return false;
}

// ── Có đang phát âm thanh không (session audio active) ──────────────────────
//  Dùng Core Audio: nếu endpoint render có session đang Active -> đang phát.
bool collectAudioActive() {
    bool active = false;
    HRESULT hr = CoInitializeEx(nullptr, COINIT_MULTITHREADED);
    bool needUninit = SUCCEEDED(hr);

    IMMDeviceEnumerator* pEnum = nullptr;
    if (SUCCEEDED(CoCreateInstance(__uuidof(MMDeviceEnumerator), nullptr,
            CLSCTX_ALL, __uuidof(IMMDeviceEnumerator), (void**)&pEnum))) {
        IMMDevice* pDev = nullptr;
        if (SUCCEEDED(pEnum->GetDefaultAudioEndpoint(eRender, eMultimedia, &pDev))) {
            IAudioSessionManager2* pMgr = nullptr;
            if (SUCCEEDED(pDev->Activate(__uuidof(IAudioSessionManager2),
                    CLSCTX_ALL, nullptr, (void**)&pMgr))) {
                IAudioSessionEnumerator* pSessEnum = nullptr;
                if (SUCCEEDED(pMgr->GetSessionEnumerator(&pSessEnum))) {
                    int count = 0; pSessEnum->GetCount(&count);
                    for (int i = 0; i < count && !active; ++i) {
                        IAudioSessionControl* pCtl = nullptr;
                        if (SUCCEEDED(pSessEnum->GetSession(i, &pCtl))) {
                            AudioSessionState st;
                            if (SUCCEEDED(pCtl->GetState(&st)) &&
                                st == AudioSessionStateActive)
                                active = true;
                            pCtl->Release();
                        }
                    }
                    pSessEnum->Release();
                }
                pMgr->Release();
            }
            pDev->Release();
        }
        pEnum->Release();
    }
    if (needUninit) CoUninitialize();
    return active;
}

// ── Số process đang chạy ────────────────────────────────────────────────────
int collectProcessCount() {
    DWORD pids[4096]; DWORD needed = 0;
    if (!EnumProcesses(pids, sizeof(pids), &needed)) return 0;
    return (int)(needed / sizeof(DWORD));
}

// ── % RAM đang dùng ─────────────────────────────────────────────────────────
float collectRamPressure() {
    MEMORYSTATUSEX ms = {}; ms.dwLength = sizeof(ms);
    if (GlobalMemoryStatusEx(&ms))
        return (float)ms.dwMemoryLoad;   // 0..100
    return 0.0f;
}

// ── Thời gian trong ngày (0..1) ─────────────────────────────────────────────
float collectTimeOfDayNorm() {
    SYSTEMTIME st; GetLocalTime(&st);
    int secs = st.wHour * 3600 + st.wMinute * 60 + st.wSecond;
    return (float)secs / 86400.0f;
}

// ── API chính ───────────────────────────────────────────────────────────────
void collectContext(SystemState& s) {
    s.screen_refresh_hz  = collectRefreshHz();
    s.wifi_active        = collectWifiActive();
    s.audio_active       = collectAudioActive();
    s.process_count      = collectProcessCount();
    s.ram_pressure_pct   = collectRamPressure();
    s.time_of_day_norm   = collectTimeOfDayNorm();
}

// ── Test riêng ──────────────────────────────────────────────────────────────
#ifdef CTX_TEST
int main() {
    printf("BatteryClaw — context_collector test\n\n");
    for (int i = 0; i < 5; ++i) {
        SystemState s = {};
        collectContext(s);
        printf("[%d] refresh=%dHz wifi=%d audio=%d procs=%d ram=%.0f%% tod=%.3f\n",
            i, s.screen_refresh_hz, s.wifi_active, s.audio_active,
            s.process_count, s.ram_pressure_pct, s.time_of_day_norm);
        Sleep(2000);
    }
    return 0;
}
#endif
