//  BatteryClaw Phase 4 — brightness_controller.cpp
//  Set do sang man hinh thuc su tren MSI laptop
//
//  Thu tu fallback:
//  1. WmiMonitorBrightnessMethods (WMI)     <- thu dau tien
//  2. SetMonitorBrightness (DDC/CI Win32)   <- fallback neu WMI bi chan
//  3. Gamma ramp (GDI)                      <- fallback cuoi cung, moi man hinh
//
//  Build: cl brightness_controller.cpp /EHsc /link wbemuuid.lib ole32.lib oleaut32.lib Dxva2.lib
// ---------------------------------------------------------------------------

#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <wbemidl.h>
#include <comdef.h>
#include <highlevelmonitorconfigurationapi.h>
#include <physicalmonitorenumerationapi.h>
#include <wingdi.h>

#include <vector>
#include <string>
#include <cstdio>

#pragma comment(lib, "wbemuuid.lib")
#pragma comment(lib, "ole32.lib")
#pragma comment(lib, "oleaut32.lib")
#pragma comment(lib, "Dxva2.lib")
#pragma comment(lib, "gdi32.lib")
#pragma comment(lib, "user32.lib")

// ── Method 1: WMI WmiMonitorBrightnessMethods ───────────────────────────────
// Hoat dong tren nhieu laptop, nhung MSI doi khi chan

bool setBrightnessWMI(int pct) {
    if (pct < 0 || pct > 100) return false;

    HRESULT hr = CoInitializeEx(nullptr, COINIT_MULTITHREADED);
    bool needUninit = SUCCEEDED(hr) || hr == RPC_E_CHANGED_MODE;

    IWbemLocator*  pLoc = nullptr;
    IWbemServices* pSvc = nullptr;
    bool success = false;

    hr = CoCreateInstance(CLSID_WbemLocator, nullptr,
        CLSCTX_INPROC_SERVER, IID_IWbemLocator, (void**)&pLoc);
    if (FAILED(hr)) goto wmi_cleanup;

    hr = pLoc->ConnectServer(_bstr_t(L"ROOT\\WMI"),
        nullptr, nullptr, nullptr, 0, nullptr, nullptr, &pSvc);
    if (FAILED(hr)) goto wmi_cleanup;

    CoSetProxyBlanket(pSvc, RPC_C_AUTHN_WINNT, RPC_C_AUTHZ_NONE, nullptr,
        RPC_C_AUTHN_LEVEL_CALL, RPC_C_IMP_LEVEL_IMPERSONATE, nullptr, EOAC_NONE);

    {
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
        if (pEnum) pEnum->Release();

        if (pObj && ret == 1) {
            IWbemClassObject* pClass   = nullptr;
            IWbemClassObject* pInClass = nullptr;
            IWbemClassObject* pInParams = nullptr;

            pSvc->GetObject(_bstr_t(L"WmiMonitorBrightnessMethods"),
                0, nullptr, &pClass, nullptr);

            if (pClass) {
                pClass->GetMethod(_bstr_t(L"WmiSetBrightness"), 0, &pInClass, nullptr);
                if (pInClass) pInClass->SpawnInstance(0, &pInParams);

                if (pInParams) {
                    VARIANT vTimeout; VariantInit(&vTimeout);
                    vTimeout.vt = VT_I4; vTimeout.lVal = 0;
                    pInParams->Put(L"Timeout", 0, &vTimeout, 0);
                    VariantClear(&vTimeout);

                    VARIANT vBright; VariantInit(&vBright);
                    vBright.vt = VT_UI1; vBright.bVal = (BYTE)pct;
                    pInParams->Put(L"Brightness", 0, &vBright, 0);
                    VariantClear(&vBright);

                    VARIANT vPath; VariantInit(&vPath);
                    pObj->Get(L"__PATH", 0, &vPath, nullptr, nullptr);

                    hr = pSvc->ExecMethod(_bstr_t(vPath.bstrVal),
                        _bstr_t(L"WmiSetBrightness"),
                        0, nullptr, pInParams, nullptr, nullptr);
                    success = SUCCEEDED(hr);
                    VariantClear(&vPath);
                    pInParams->Release();
                }
                if (pInClass) pInClass->Release();
                pClass->Release();
            }
            pObj->Release();
        }
    }

wmi_cleanup:
    if (pSvc) pSvc->Release();
    if (pLoc) pLoc->Release();
    if (needUninit) CoUninitialize();

    if (success) printf("[Bright] WMI: %d%%\n", pct);
    return success;
}

// ── Method 2: DDC/CI SetMonitorBrightness ───────────────────────────────────
// Dung VESA DDC/CI protocol qua DXVA2 — hoat dong voi man hinh ngoai
// Tren laptop MSI, panel noi thuong khong ho tro DDC/CI -> se fail

bool setBrightnessDDC(int pct) {
    if (pct < 0 || pct > 100) return false;

    bool success = false;
    HWND desktop = GetDesktopWindow();
    HDC  hdc     = GetDC(desktop);
    if (!hdc) return false;

    HMONITOR hMon = MonitorFromWindow(desktop, MONITOR_DEFAULTTOPRIMARY);

    DWORD numPhys = 0;
    if (!GetNumberOfPhysicalMonitorsFromHMONITOR(hMon, &numPhys) || numPhys == 0) {
        ReleaseDC(desktop, hdc);
        return false;
    }

    std::vector<PHYSICAL_MONITOR> physMons(numPhys);
    if (!GetPhysicalMonitorsFromHMONITOR(hMon, numPhys, physMons.data())) {
        ReleaseDC(desktop, hdc);
        return false;
    }

    for (DWORD i = 0; i < numPhys; i++) {
        DWORD minBright = 0, curBright = 0, maxBright = 100;
        if (GetMonitorBrightness(physMons[i].hPhysicalMonitor,
                &minBright, &curBright, &maxBright))
        {
            // Scale pct ve range [minBright, maxBright]
            DWORD target = minBright + (DWORD)((maxBright - minBright) * pct / 100.0);
            if (SetMonitorBrightness(physMons[i].hPhysicalMonitor, target)) {
                success = true;
                printf("[Bright] DDC/CI monitor %lu: %d%% (raw=%lu)\n", i, pct, target);
            }
        }
    }

    DestroyPhysicalMonitors(numPhys, physMons.data());
    ReleaseDC(desktop, hdc);
    return success;
}

// ── Method 3: Gamma Ramp (GDI) ──────────────────────────────────────────────
// Fallback cuoi cung — khong set backlight that su
// Chi dieu chinh gamma (lam toi man hinh bang phan mem)
// Hoat dong 100% tren moi may

bool setBrightnessGamma(int pct) {
    if (pct < 10 || pct > 100) pct = (pct < 10) ? 10 : 100;

    HDC hdc = GetDC(nullptr);
    if (!hdc) return false;

    WORD gamma[3][256];
    float scale = pct / 100.0f;

    for (int i = 0; i < 256; i++) {
        WORD val = (WORD)(i * 256 * scale);
        val = (val > 65535) ? 65535 : val;
        gamma[0][i] = val;  // Red
        gamma[1][i] = val;  // Green
        gamma[2][i] = val;  // Blue
    }

    bool ok = (SetDeviceGammaRamp(hdc, gamma) != FALSE);
    ReleaseDC(nullptr, hdc);

    if (ok) printf("[Bright] Gamma ramp: %d%% (software dimming)\n", pct);
    return ok;
}

// ── Restore gamma ve binh thuong ────────────────────────────────────────────

void restoreGamma() {
    HDC hdc = GetDC(nullptr);
    if (!hdc) return;

    WORD gamma[3][256];
    for (int i = 0; i < 256; i++) {
        gamma[0][i] = gamma[1][i] = gamma[2][i] = (WORD)(i * 256);
    }
    SetDeviceGammaRamp(hdc, gamma);
    ReleaseDC(nullptr, hdc);
    printf("[Bright] Gamma restored to 100%%\n");
}

// ── Doc do sang hien tai ────────────────────────────────────────────────────

int getCurrentBrightness() {
    // Thu WMI truoc
    HRESULT hr = CoInitializeEx(nullptr, COINIT_MULTITHREADED);
    bool needUninit = SUCCEEDED(hr) || hr == RPC_E_CHANGED_MODE;

    IWbemLocator*  pLoc = nullptr;
    IWbemServices* pSvc = nullptr;
    int result = -1;

    hr = CoCreateInstance(CLSID_WbemLocator, nullptr,
        CLSCTX_INPROC_SERVER, IID_IWbemLocator, (void**)&pLoc);
    if (FAILED(hr)) goto read_cleanup;

    hr = pLoc->ConnectServer(_bstr_t(L"ROOT\\WMI"),
        nullptr, nullptr, nullptr, 0, nullptr, nullptr, &pSvc);
    if (FAILED(hr)) goto read_cleanup;

    CoSetProxyBlanket(pSvc, RPC_C_AUTHN_WINNT, RPC_C_AUTHZ_NONE, nullptr,
        RPC_C_AUTHN_LEVEL_CALL, RPC_C_IMP_LEVEL_IMPERSONATE, nullptr, EOAC_NONE);

    {
        IEnumWbemClassObject* pEnum = nullptr;
        hr = pSvc->ExecQuery(
            _bstr_t(L"WQL"),
            _bstr_t(L"SELECT CurrentBrightness FROM WmiMonitorBrightness"),
            WBEM_FLAG_FORWARD_ONLY | WBEM_FLAG_RETURN_IMMEDIATELY,
            nullptr, &pEnum);

        IWbemClassObject* pObj = nullptr;
        ULONG ret = 0;
        if (SUCCEEDED(hr) && pEnum)
            pEnum->Next(WBEM_INFINITE, 1, &pObj, &ret);
        if (pEnum) pEnum->Release();

        if (pObj && ret == 1) {
            VARIANT v; VariantInit(&v);
            pObj->Get(L"CurrentBrightness", 0, &v, nullptr, nullptr);
            if (v.vt == VT_UI1) result = (int)v.bVal;
            VariantClear(&v);
            pObj->Release();
        }
    }

read_cleanup:
    if (pSvc) pSvc->Release();
    if (pLoc) pLoc->Release();
    if (needUninit) CoUninitialize();
    return result;
}

// ── setBrightness: tu dong chon phuong phap tot nhat ───────────────────────

enum BrightnessMethod { METHOD_NONE, METHOD_WMI, METHOD_DDC, METHOD_GAMMA };
static BrightnessMethod g_method = METHOD_NONE;

bool setBrightness(int pct) {
    // Lan dau: thu lan luot de tim phuong phap hoat dong
    if (g_method == METHOD_NONE) {
        if (setBrightnessWMI(pct)) {
            g_method = METHOD_WMI;
            return true;
        }
        printf("[Bright] WMI that bai, thu DDC/CI...\n");
        if (setBrightnessDDC(pct)) {
            g_method = METHOD_DDC;
            return true;
        }
        printf("[Bright] DDC/CI that bai, dung Gamma ramp (software)...\n");
        if (setBrightnessGamma(pct)) {
            g_method = METHOD_GAMMA;
            return true;
        }
        printf("[Bright] TAT CA phuong phap that bai!\n");
        return false;
    }

    // Lan sau: dung phuong phap da biet
    switch (g_method) {
        case METHOD_WMI:   return setBrightnessWMI(pct);
        case METHOD_DDC:   return setBrightnessDDC(pct);
        case METHOD_GAMMA: return setBrightnessGamma(pct);
        default: return false;
    }
}

const char* getMethodName() {
    switch (g_method) {
        case METHOD_WMI:   return "WMI (hardware backlight)";
        case METHOD_DDC:   return "DDC/CI (hardware backlight)";
        case METHOD_GAMMA: return "Gamma ramp (software dimming)";
        default:           return "chua xac dinh";
    }
}

// ── Test ────────────────────────────────────────────────────────────────────

#ifndef NO_MAIN_BC
int main() {
    printf("BatteryClaw Phase 4 — Brightness Controller Test\n");
    printf("Can quyen Admin\n\n");

    int cur = getCurrentBrightness();
    printf("Do sang hien tai: %d%%\n\n", cur);

    printf("[TEST 1] Set 50%%...\n");
    bool ok = setBrightness(50);
    printf("  Method dung: %s\n", getMethodName());
    printf("  Ket qua: %s\n\n", ok ? "OK" : "FAIL");

    if (ok) {
        Sleep(2000);
        printf("[TEST 2] Set 80%%...\n");
        setBrightness(80);
        Sleep(2000);
        printf("[TEST 3] Restore %d%%...\n", cur > 0 ? cur : 99);
        setBrightness(cur > 0 ? cur : 99);
    }

    if (g_method == METHOD_GAMMA) {
        printf("\nLUU Y: Dang dung Gamma (software) — khong tiet kiem backlight that su\n");
        printf("Nhung van co tac dung lam mat man hinh -> giam moi mat\n");
    }

    return 0;
}
#endif
