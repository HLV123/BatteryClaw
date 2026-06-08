//  BatteryClaw Phase 1 — power_monitor.cpp
//  1.1 — Real Power Measurement
//
//  Mục tiêu: đo TỐC ĐỘ XẢ ĐIỆN THẬT (mW) thay vì baseline ảo 12000mW.
//  Đây là "ground truth" để tính reward thật ở Phase 2.
//
//  Hai nguồn dữ liệu, ưu tiên theo thứ tự:
//    (A) ACPI tức thời:  BatteryStatus.DischargeRate (root\WMI, lớp BatteryStatus)
//        -> nhiều laptop (gồm MSI) trả về mW xả tức thời. Chính xác & rẻ nhất.
//    (B) Sai phân dung lượng:  power = ΔRemainingCapacity / Δt
//        -> fallback khi (A) trả 0. Cần 2 mẫu cách nhau >= ~5s mới đủ phân giải.
//
//  Build (test riêng):
//    cl power_monitor.cpp /EHsc /DPM_TEST /link wbemuuid.lib ole32.lib oleaut32.lib
// ---------------------------------------------------------------------------

#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <wbemidl.h>
#include <comdef.h>

#include <cstdio>
#include <cstdint>

#pragma comment(lib, "wbemuuid.lib")
#pragma comment(lib, "ole32.lib")
#pragma comment(lib, "oleaut32.lib")

// ── WMI mini-helper (độc lập, không phụ thuộc state_collector) ──────────────
namespace {

struct WmiSession {
    IWbemLocator*  loc = nullptr;
    IWbemServices* svc = nullptr;
    bool           ok  = false;

    bool init(const wchar_t* ns) {
        // CoInitialize có thể đã được gọi bởi thread khác -> chấp nhận RPC_E_CHANGED_MODE
        HRESULT hr = CoInitializeEx(nullptr, COINIT_MULTITHREADED);
        if (FAILED(hr) && hr != RPC_E_CHANGED_MODE) return false;

        CoInitializeSecurity(nullptr, -1, nullptr, nullptr,
            RPC_C_AUTHN_LEVEL_DEFAULT, RPC_C_IMP_LEVEL_IMPERSONATE,
            nullptr, EOAC_NONE, nullptr);

        hr = CoCreateInstance(CLSID_WbemLocator, nullptr,
            CLSCTX_INPROC_SERVER, IID_IWbemLocator, (void**)&loc);
        if (FAILED(hr)) return false;

        hr = loc->ConnectServer(_bstr_t(ns), nullptr, nullptr, nullptr,
            0, nullptr, nullptr, &svc);
        if (FAILED(hr)) { loc->Release(); loc = nullptr; return false; }

        CoSetProxyBlanket(svc, RPC_C_AUTHN_WINNT, RPC_C_AUTHZ_NONE, nullptr,
            RPC_C_AUTHN_LEVEL_CALL, RPC_C_IMP_LEVEL_IMPERSONATE, nullptr, EOAC_NONE);
        ok = true;
        return true;
    }

    IWbemClassObject* queryFirst(const wchar_t* wql) {
        if (!ok) return nullptr;
        IEnumWbemClassObject* en = nullptr;
        HRESULT hr = svc->ExecQuery(_bstr_t(L"WQL"), _bstr_t(wql),
            WBEM_FLAG_FORWARD_ONLY | WBEM_FLAG_RETURN_IMMEDIATELY, nullptr, &en);
        if (FAILED(hr) || !en) return nullptr;
        IWbemClassObject* obj = nullptr; ULONG n = 0;
        en->Next(WBEM_INFINITE, 1, &obj, &n);
        en->Release();
        return (n == 1) ? obj : nullptr;
    }

    ~WmiSession() {
        if (svc) svc->Release();
        if (loc) loc->Release();
        // KHÔNG gọi CoUninitialize ở đây: thread chính quản lý vòng đời COM.
    }
};

long getLong(IWbemClassObject* o, const wchar_t* prop) {
    VARIANT v; VariantInit(&v);
    long r = 0;
    if (o && SUCCEEDED(o->Get(prop, 0, &v, nullptr, nullptr))) {
        if      (v.vt == VT_I4)  r = v.lVal;
        else if (v.vt == VT_UI4) r = (long)v.ulVal;
    }
    VariantClear(&v);
    return r;
}

bool getBool(IWbemClassObject* o, const wchar_t* prop) {
    VARIANT v; VariantInit(&v);
    bool r = false;
    if (o && SUCCEEDED(o->Get(prop, 0, &v, nullptr, nullptr)))
        r = (v.vt == VT_BOOL && v.boolVal != VARIANT_FALSE);
    VariantClear(&v);
    return r;
}

} // namespace

// ── (A) Đọc discharge rate tức thời từ ACPI ─────────────────────────────────
//  Trả về mW xả (>0). Trả 0 nếu đang sạc hoặc lớp không cung cấp DischargeRate.
//
//  Lớp BatteryStatus (root\WMI) có:
//    - Discharging (bool), Charging (bool)
//    - DischargeRate (mW)  <- không phải máy nào cũng điền, nên có fallback (B)
float readAcpiDischargeRateMw() {
    WmiSession w;
    if (!w.init(L"ROOT\\WMI")) return 0.0f;

    IWbemClassObject* o = w.queryFirst(
        L"SELECT Discharging, Charging, DischargeRate FROM BatteryStatus");
    if (!o) return 0.0f;

    bool discharging = getBool(o, L"Discharging");
    long rate        = getLong(o, L"DischargeRate");  // mW
    o->Release();

    if (!discharging) return 0.0f;          // đang sạc/cắm điện -> không tính xả
    return (rate > 0) ? (float)rate : 0.0f; // 0 -> để caller dùng fallback (B)
}

// ── (B) Fallback: ước lượng power qua sai phân dung lượng ───────────────────
//  power_mw = ΔRemainingCapacity(mWh) / Δt(h)
//  Giữ trạng thái tĩnh giữa hai lần gọi. Cần Δt đủ lớn (>= 5s) để bớt nhiễu.
//
//  s_prev_mwh / s_prev_tick là mẫu trước. Trả 0 nếu chưa đủ dữ liệu.
float estimateDischargeBySampling(int remaining_mwh, bool charging) {
    static int      s_prev_mwh  = -1;
    static uint64_t s_prev_tick = 0;
    static float    s_last_good = 0.0f;

    uint64_t now = GetTickCount64();

    if (charging) {                 // đang sạc -> reset, không ước lượng xả
        s_prev_mwh  = remaining_mwh;
        s_prev_tick = now;
        s_last_good = 0.0f;
        return 0.0f;
    }

    if (s_prev_mwh < 0) {           // mẫu đầu tiên
        s_prev_mwh  = remaining_mwh;
        s_prev_tick = now;
        return 0.0f;
    }

    uint64_t dt_ms = now - s_prev_tick;
    if (dt_ms < 5000) return s_last_good;   // chưa đủ thời gian -> trả giá trị cũ

    int delta_mwh = s_prev_mwh - remaining_mwh;   // xả -> dương
    double dt_h   = dt_ms / 3600000.0;
    float power   = (dt_h > 0) ? (float)(delta_mwh / dt_h) : 0.0f;

    // cập nhật mẫu
    s_prev_mwh  = remaining_mwh;
    s_prev_tick = now;

    if (power < 0) power = 0.0f;     // dung lượng tăng nhẹ do nhiễu -> kẹp 0
    s_last_good = power;
    return power;
}

// ── API chính: gọi từ state_collector ──────────────────────────────────────
//  Ưu tiên ACPI tức thời (A); nếu 0 thì fallback sai phân (B).
float collectDischargeRateMw(int remaining_mwh, bool charging) {
    if (charging) return 0.0f;

    float acpi = readAcpiDischargeRateMw();
    if (acpi > 0.0f) return acpi;

    return estimateDischargeBySampling(remaining_mwh, charging);
}

// ── Test riêng ──────────────────────────────────────────────────────────────
#ifdef PM_TEST
int main() {
    printf("BatteryClaw — power_monitor test\n");
    printf("Đang đo discharge rate thật (rút sạc ra để thấy số dương)...\n\n");
    CoInitializeEx(nullptr, COINIT_MULTITHREADED);
    for (int i = 0; i < 20; ++i) {
        float acpi = readAcpiDischargeRateMw();
        printf("[%2d] ACPI DischargeRate = %.0f mW\n", i, acpi);
        Sleep(2000);
    }
    CoUninitialize();
    return 0;
}
#endif
