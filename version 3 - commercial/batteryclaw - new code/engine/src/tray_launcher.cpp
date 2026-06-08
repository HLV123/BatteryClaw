//  BatteryClaw — tray_launcher.cpp
//  System tray icon: tu dong chay batteryclaw.exe + rl_brain.py khi boot
//  Khong can mo terminal, chay ngam hoan toan
//
//  Cai autostart: tray.exe --install
//  Go autostart : tray.exe --uninstall

#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#define UNICODE
#include <windows.h>
#include <shellapi.h>
#include <string>
#include <atomic>

#pragma comment(lib,"user32.lib")
#pragma comment(lib,"shell32.lib")
#pragma comment(lib,"advapi32.lib")

#define WM_TRAYICON   (WM_USER+1)
#define ID_TOGGLE     1001
#define ID_OPEN_LOG   1002
#define ID_EXIT       1003
#define APP_NAME      L"BatteryClaw"
#define MUTEX_NAME    L"BatteryClaw_Tray_Instance"

// ── State ─────────────────────────────────────────────────────────────────────
static NOTIFYICONDATAW   g_nid      = {};
static HWND              g_hwnd     = nullptr;
static HANDLE            g_mutex    = nullptr;
static PROCESS_INFORMATION g_engine = {};
static PROCESS_INFORMATION g_brain  = {};
static std::atomic<bool> g_running  {false};

// ── Helper: lay duong dan thu muc chua tray.exe ───────────────────────────────
std::wstring exeDir() {
    wchar_t buf[MAX_PATH]={};
    GetModuleFileNameW(nullptr,buf,MAX_PATH);
    std::wstring p(buf);
    auto pos=p.rfind(L'\\');
    return pos!=std::wstring::npos ? p.substr(0,pos) : p;
}

// ── Khoi dong batteryclaw.exe voi quyen Admin (UAC) ───────────────────────────
bool startEngine() {
    std::wstring dir = exeDir();
    std::wstring exe = dir + L"\\batteryclaw.exe";

    SHELLEXECUTEINFOW sei={};
    sei.cbSize=sizeof(sei);
    sei.fMask =SEE_MASK_NOCLOSEPROCESS;
    sei.lpVerb=L"runas";
    sei.lpFile=exe.c_str();
    sei.nShow =SW_HIDE;

    if (!ShellExecuteExW(&sei)) {
        if (GetLastError()==ERROR_CANCELLED)
            MessageBoxW(nullptr,
                L"Can quyen Admin de dieu khien CPU va man hinh.\n"
                L"Vui long chap nhan UAC.",
                L"BatteryClaw",MB_ICONWARNING|MB_OK);
        return false;
    }
    g_engine.hProcess=sei.hProcess;
    return true;
}

// ── Khoi dong rl_brain.py (user thuong, an cua so) ───────────────────────────
bool startBrain() {
    std::wstring dir   = exeDir();
    // tray.exe nam trong engine/build/, brain nam trong brain/
    std::wstring base  = dir + L"\\..\\..";
    std::wstring script= base + L"\\brain\\rl_brain.py";
    std::wstring model = base + L"\\simulator\\models\\batteryclaw_policy.onnx";
    std::wstring cmd   = L"python \""+script+L"\" --model \""+model+L"\"";

    STARTUPINFOW si={};
    si.cb=sizeof(si);
    si.dwFlags=STARTF_USESHOWWINDOW;
    si.wShowWindow=SW_HIDE;

    return CreateProcessW(nullptr,
        const_cast<wchar_t*>(cmd.c_str()),
        nullptr,nullptr,FALSE,
        CREATE_NO_WINDOW,nullptr,nullptr,
        &si,&g_brain)!=FALSE;
}

// ── Dung tat ca ──────────────────────────────────────────────────────────────
void stopAll() {
    if (g_brain.hProcess) {
        TerminateProcess(g_brain.hProcess,0);
        CloseHandle(g_brain.hProcess);
        CloseHandle(g_brain.hThread);
        g_brain={};
    }
    if (g_engine.hProcess) {
        TerminateProcess(g_engine.hProcess,0);
        CloseHandle(g_engine.hProcess);
        g_engine={};
    }
    g_running=false;
}

// ── Bat / Tat BatteryClaw ────────────────────────────────────────────────────
void toggle() {
    if (g_running) {
        stopAll();
        wcscpy_s(g_nid.szTip,L"BatteryClaw - TAT");
        Shell_NotifyIconW(NIM_MODIFY,&g_nid);
    } else {
        if (startEngine()) {
            Sleep(4000); // cho engine khoi dong + state collector
            if (startBrain()) {
                g_running=true;
                wcscpy_s(g_nid.szTip,L"BatteryClaw - DANG CHAY");
                Shell_NotifyIconW(NIM_MODIFY,&g_nid);
            }
        }
    }
}

// ── Tray icon ────────────────────────────────────────────────────────────────
void addTray(HWND hwnd) {
    g_nid.cbSize          =sizeof(g_nid);
    g_nid.hWnd            =hwnd;
    g_nid.uID             =1;
    g_nid.uFlags          =NIF_ICON|NIF_MESSAGE|NIF_TIP;
    g_nid.uCallbackMessage=WM_TRAYICON;
    g_nid.hIcon           =LoadIconW(nullptr,IDI_APPLICATION);
    wcscpy_s(g_nid.szTip,L"BatteryClaw - DANG KHOI DONG");
    Shell_NotifyIconW(NIM_ADD,&g_nid);
}

void showMenu(HWND hwnd) {
    HMENU m=CreatePopupMenu();
    AppendMenuW(m,MF_STRING|MF_GRAYED,0,
        g_running?L"Trang thai: DANG CHAY":L"Trang thai: TAT");
    AppendMenuW(m,MF_SEPARATOR,0,nullptr);
    AppendMenuW(m,MF_STRING,ID_TOGGLE,
        g_running?L"Tat BatteryClaw":L"Bat BatteryClaw");
    AppendMenuW(m,MF_STRING,ID_OPEN_LOG,L"Xem log...");
    AppendMenuW(m,MF_SEPARATOR,0,nullptr);
    AppendMenuW(m,MF_STRING,ID_EXIT,L"Thoat");

    POINT pt; GetCursorPos(&pt);
    SetForegroundWindow(hwnd);
    TrackPopupMenu(m,TPM_BOTTOMALIGN|TPM_LEFTALIGN,pt.x,pt.y,0,hwnd,nullptr);
    DestroyMenu(m);
}

// ── Window procedure ─────────────────────────────────────────────────────────
LRESULT CALLBACK WndProc(HWND hwnd,UINT msg,WPARAM wp,LPARAM lp) {
    switch(msg) {
    case WM_TRAYICON:
        if (lp==WM_RBUTTONUP||lp==WM_LBUTTONUP) showMenu(hwnd);
        break;
    case WM_COMMAND:
        switch(LOWORD(wp)) {
        case ID_TOGGLE: toggle(); break;
        case ID_OPEN_LOG: {
            std::wstring log=exeDir()+L"\\..\\..\\brain\\rl_brain.log";
            ShellExecuteW(nullptr,L"open",L"notepad.exe",log.c_str(),nullptr,SW_SHOW);
            break;
        }
        case ID_EXIT:
            stopAll();
            Shell_NotifyIconW(NIM_DELETE,&g_nid);
            PostQuitMessage(0);
            break;
        }
        break;
    case WM_DESTROY:
        stopAll();
        Shell_NotifyIconW(NIM_DELETE,&g_nid);
        PostQuitMessage(0);
        break;
    }
    return DefWindowProcW(hwnd,msg,wp,lp);
}

// ── Autostart registry ────────────────────────────────────────────────────────
bool installAutostart() {
    wchar_t exe[MAX_PATH]={};
    GetModuleFileNameW(nullptr,exe,MAX_PATH);
    HKEY hk;
    if (RegOpenKeyExW(HKEY_CURRENT_USER,
        L"SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Run",
        0,KEY_SET_VALUE,&hk)!=ERROR_SUCCESS) return false;
    LONG r=RegSetValueExW(hk,APP_NAME,0,REG_SZ,
        (BYTE*)exe,(DWORD)((wcslen(exe)+1)*sizeof(wchar_t)));
    RegCloseKey(hk);
    if (r==ERROR_SUCCESS)
        MessageBoxW(nullptr,
            L"BatteryClaw se tu dong chay khi bat may.\n"
            L"Icon se xuat hien o goc man hinh.",
            L"BatteryClaw - OK",MB_ICONINFORMATION|MB_OK);
    return r==ERROR_SUCCESS;
}

bool uninstallAutostart() {
    HKEY hk;
    if (RegOpenKeyExW(HKEY_CURRENT_USER,
        L"SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\Run",
        0,KEY_SET_VALUE,&hk)!=ERROR_SUCCESS) return false;
    RegDeleteValueW(hk,APP_NAME);
    RegCloseKey(hk);
    MessageBoxW(nullptr,L"Da xoa autostart.",L"BatteryClaw",MB_OK);
    return true;
}

// ── WinMain ──────────────────────────────────────────────────────────────────
int WINAPI WinMain(HINSTANCE hInst,HINSTANCE,LPSTR lpCmd,int) {
    std::string args(lpCmd?lpCmd:"");

    if (args.find("--install")!=std::string::npos)   { installAutostart();   return 0; }
    if (args.find("--uninstall")!=std::string::npos) { uninstallAutostart(); return 0; }

    // Single instance
    g_mutex=CreateMutexW(nullptr,TRUE,MUTEX_NAME);
    if (GetLastError()==ERROR_ALREADY_EXISTS) {
        MessageBoxW(nullptr,L"BatteryClaw dang chay roi!",
            APP_NAME,MB_ICONINFORMATION|MB_OK);
        return 0;
    }

    // Dang ky window class (an)
    WNDCLASSW wc={};
    wc.lpfnWndProc  =WndProc;
    wc.hInstance    =hInst;
    wc.lpszClassName=L"BatteryClawTray";
    RegisterClassW(&wc);

    g_hwnd=CreateWindowW(L"BatteryClawTray",L"BatteryClaw",
        WS_OVERLAPPEDWINDOW,0,0,0,0,nullptr,nullptr,hInst,nullptr);
    ShowWindow(g_hwnd,SW_HIDE);

    addTray(g_hwnd);

    // Tu dong bat ngay khi khoi dong
    toggle();

    // Popup hoi user khi mo may lan dau
    int ans=MessageBoxW(nullptr,
        L"BatteryClaw da san sang!\n\n"
        L"Ban co muon bat dau tiet kiem pin khong?",
        L"BatteryClaw",MB_YESNO|MB_ICONQUESTION);
    if (ans==IDNO) {
        stopAll();
        wcscpy_s(g_nid.szTip,L"BatteryClaw - TAT (click phai de bat)");
        Shell_NotifyIconW(NIM_MODIFY,&g_nid);
    }

    MSG msg;
    while(GetMessageW(&msg,nullptr,0,0)) {
        TranslateMessage(&msg);
        DispatchMessageW(&msg);
    }
    if (g_mutex) CloseHandle(g_mutex);
    return 0;
}
