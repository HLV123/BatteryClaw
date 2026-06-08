//  BatteryClaw Phase 5 — app_detector.cpp
//  Nhan dien workload thuc te: game / browser / video / IDE / compile / idle
//  Dung process name + cua so active + GPU load
//
//  Build: cl app_detector.cpp /EHsc /link psapi.lib user32.lib
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
#include <map>

#pragma comment(lib, "psapi.lib")
#pragma comment(lib, "user32.lib")

// ── Workload enum ────────────────────────────────────────────────────────────

enum WorkloadType {
    WL_IDLE    = 0,
    WL_BROWSER = 1,
    WL_OFFICE  = 2,
    WL_COMPILE = 3,
    WL_GAME    = 4,
    WL_VIDEO   = 5,   // Phase 5 them moi: xem video (YouTube, VLC, ...)
    WL_MEETING = 6,   // Phase 5 them moi: hop online (Zoom, Teams, ...)
};

const char* workloadName(WorkloadType wl) {
    switch(wl) {
        case WL_IDLE:    return "idle";
        case WL_BROWSER: return "browser";
        case WL_OFFICE:  return "office";
        case WL_COMPILE: return "compile";
        case WL_GAME:    return "game";
        case WL_VIDEO:   return "video";
        case WL_MEETING: return "meeting";
        default:         return "unknown";
    }
}

// ── Danh sach process theo loai ──────────────────────────────────────────────

// Browser
static const std::vector<std::string> BROWSER_PROCS = {
    "chrome", "msedge", "firefox", "opera", "brave", "vivaldi",
    "chromium", "iexplore", "browser"
};

// Game launchers & games pho bien
static const std::vector<std::string> GAME_PROCS = {
    // Launchers
    "steam", "epicgameslauncher", "gog", "battlenet", "origin",
    "upc", "uplay", "riotclientservices", "leagueclient",
    // Games pho bien
    "leagueoflegends", "valorant", "csgo", "cs2", "dota2",
    "genshinimpact", "minecraft", "robloxplayerbeta",
    "pubg", "fortnite", "apexlegends", "overwatch",
    "eldenring", "cyberpunk2077",
};

// IDE / Dev tools
static const std::vector<std::string> IDE_PROCS = {
    "code", "devenv", "pycharm64", "idea64", "clion64",
    "webstorm64", "rider64", "eclipse", "netbeans",
    "sublime_text", "notepad++", "atom",
};

// Compile / build
static const std::vector<std::string> COMPILE_PROCS = {
    "cl", "clang", "gcc", "g++", "msbuild", "cmake",
    "ninja", "make", "cargo", "rustc", "javac",
    "python", "node", "npm", "gradle", "mvn",
};

// Video players
static const std::vector<std::string> VIDEO_PROCS = {
    "vlc", "mpc-hc64", "mpc-be64", "mpv", "wmplayer",
    "movies.app",  // Windows Movies & TV
};

// Meeting apps
static const std::vector<std::string> MEETING_PROCS = {
    "zoom", "teams", "slack", "discord", "skype",
    "webex", "googlemeeting",
};

// Idle / system processes — khong phai workload thuc su
static const std::vector<std::string> IDLE_PROCS = {
    "cmd", "powershell", "pwsh", "explorer", "taskmgr",
    "regedit", "mmc", "services", "conhost", "wt",
    "windowsterminal", "bash", "sh",
};

// Office apps
static const std::vector<std::string> OFFICE_PROCS = {
    "winword", "excel", "powerpnt", "outlook", "onenote",
    "soffice", "acrobat", "acrord32", "foxitpdfeditor",
    "notepad", "wordpad",
};

// ── Helper: lowercase string ─────────────────────────────────────────────────

std::string toLower(const std::string& s) {
    std::string r = s;
    std::transform(r.begin(), r.end(), r.begin(),
        [](unsigned char c){ return std::tolower(c); });
    return r;
}

// ── Helper: kiem tra xem process name co match voi list khong ────────────────

bool matchList(const std::string& procLower,
               const std::vector<std::string>& list)
{
    for (const auto& p : list) {
        if (procLower.find(p) != std::string::npos) return true;
    }
    return false;
}

// ── Doc ten process tu PID ───────────────────────────────────────────────────

std::string getProcessName(DWORD pid) {
    HANDLE h = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, FALSE, pid);
    if (!h) return "";
    char buf[260] = {};
    DWORD sz = sizeof(buf);
    QueryFullProcessImageNameA(h, 0, buf, &sz);
    CloseHandle(h);
    std::string full(buf);
    // Lay ten file thoi
    auto pos = full.rfind('\\');
    std::string name = (pos != std::string::npos) ? full.substr(pos+1) : full;
    // Bo phan mo rong .exe
    auto ext = name.rfind('.');
    if (ext != std::string::npos) name = name.substr(0, ext);
    return toLower(name);
}

// ── Doc foreground window process ────────────────────────────────────────────

std::string getForegroundProcessName() {
    HWND fg = GetForegroundWindow();
    if (!fg) return "";
    DWORD pid = 0;
    GetWindowThreadProcessId(fg, &pid);
    return getProcessName(pid);
}

// ── Kiem tra GPU load qua PDH (Performance Counter) ─────────────────────────
// Neu GPU load cao > 40% thi co kha nang la game hoac video rendering

#include <pdh.h>
#pragma comment(lib, "pdh.lib")

static PDH_HQUERY  g_gpuQuery  = nullptr;
static PDH_HCOUNTER g_gpuCounter = nullptr;
static bool g_pdh_init = false;

bool initGpuCounter() {
    if (g_pdh_init) return true;

    PDH_STATUS s = PdhOpenQuery(nullptr, 0, &g_gpuQuery);
    if (s != ERROR_SUCCESS) return false;

    // NVIDIA / AMD GPU engine utilization
    // "GPU Engine" tren Windows 10/11
    s = PdhAddCounterA(g_gpuQuery,
        "\\GPU Engine(*)\\Utilization Percentage",
        0, &g_gpuCounter);
    if (s != ERROR_SUCCESS) {
        PdhCloseQuery(g_gpuQuery);
        return false;
    }

    PdhCollectQueryData(g_gpuQuery);
    g_pdh_init = true;
    return true;
}

float getGpuLoadPct() {
    if (!g_pdh_init && !initGpuCounter()) return 0.0f;

    PdhCollectQueryData(g_gpuQuery);

    PDH_FMT_COUNTERVALUE val;
    DWORD type = 0;
    PDH_STATUS s = PdhGetFormattedCounterValue(
        g_gpuCounter, PDH_FMT_DOUBLE, &type, &val);

    if (s == ERROR_SUCCESS) {
        return (float)val.doubleValue;
    }
    return 0.0f;
}

// ── Kiem tra co process compile/build dang chay khong ───────────────────────

bool isCompiling() {
    HANDLE snap = CreateToolhelp32Snapshot(TH32CS_SNAPPROCESS, 0);
    if (snap == INVALID_HANDLE_VALUE) return false;

    PROCESSENTRY32 pe = {}; pe.dwSize = sizeof(pe);
    bool found = false;

    if (Process32First(snap, &pe)) {
        do {
            std::string name = toLower(pe.szExeFile);
            // Bo phan .exe
            auto ext = name.rfind('.');
            if (ext != std::string::npos) name = name.substr(0, ext);

            if (matchList(name, COMPILE_PROCS)) {
                // Kiem tra them: process nay dang dung CPU nhieu khong
                HANDLE ph = OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, FALSE, pe.th32ProcessID);
                if (ph) {
                    FILETIME c,e,k,u;
                    if (GetProcessTimes(ph, &c, &e, &k, &u)) {
                        ULARGE_INTEGER ui;
                        ui.LowPart = u.dwLowDateTime;
                        ui.HighPart = u.dwHighDateTime;
                        // Neu tong CPU time > 1 giay thi co kha nang dang chay
                        if (ui.QuadPart > 10000000ULL) {
                            found = true;
                        }
                    }
                    CloseHandle(ph);
                }
            }
        } while (!found && Process32Next(snap, &pe));
    }
    CloseHandle(snap);
    return found;
}

// ── Ham chinh: phat hien workload ────────────────────────────────────────────

struct AppInfo {
    WorkloadType workload;
    std::string  fg_process;
    float        gpu_load;
    bool         is_compiling;
    int          confidence;    // 0-100
};

AppInfo detectWorkload(float cpu_load_pct) {
    AppInfo info = {};
    info.fg_process   = getForegroundProcessName();

    // GPU: poll 2 lan de PDH co so chinh xac (lan dau luon = 0)
    static bool gpu_warmed = false;
    if (!gpu_warmed) {
        getGpuLoadPct();   // warm-up
        Sleep(100);
        gpu_warmed = true;
    }
    info.gpu_load     = getGpuLoadPct();
    info.is_compiling = false;

    std::string proc = info.fg_process;

    // ── Uu tien 0: Idle/system process ──────────────────────────────────────
    if (matchList(proc, IDLE_PROCS) && cpu_load_pct < 30.0f) {
        info.workload   = WL_IDLE;
        info.confidence = 75;
        return info;
    }

    // ── Uu tien 1: Game (GPU cao + process la game) ──────────────────────────
    if (info.gpu_load > 40.0f || matchList(proc, GAME_PROCS)) {
        info.workload   = WL_GAME;
        info.confidence = (int)(50 + info.gpu_load / 2);
        if (info.confidence > 100) info.confidence = 100;
        return info;
    }

    // ── Uu tien 2: Meeting (video + audio real-time) ─────────────────────────
    if (matchList(proc, MEETING_PROCS)) {
        info.workload   = WL_MEETING;
        info.confidence = 90;
        return info;
    }

    // ── Uu tien 3: Video player ──────────────────────────────────────────────
    if (matchList(proc, VIDEO_PROCS)) {
        info.workload   = WL_VIDEO;
        info.confidence = 95;
        return info;
    }

    // ── Uu tien 4: Browser — co the la video (YouTube) ──────────────────────
    if (matchList(proc, BROWSER_PROCS)) {
        // GPU load trung binh -> co the dang xem video
        if (info.gpu_load > 15.0f && info.gpu_load <= 40.0f) {
            info.workload   = WL_VIDEO;   // YouTube/Netflix trong browser
            info.confidence = 70;
        } else {
            info.workload   = WL_BROWSER;
            info.confidence = 85;
        }
        return info;
    }

    // ── Uu tien 5: Compile (chay ngam, kiem tra background) ─────────────────
    if (cpu_load_pct > 60.0f) {
        info.is_compiling = isCompiling();
        if (info.is_compiling) {
            info.workload   = WL_COMPILE;
            info.confidence = 80;
            return info;
        }
    }

    // ── Uu tien 6: IDE ───────────────────────────────────────────────────────
    if (matchList(proc, IDE_PROCS)) {
        // IDE + CPU cao -> compile
        if (cpu_load_pct > 50.0f) {
            info.workload   = WL_COMPILE;
            info.confidence = 65;
        } else {
            info.workload   = WL_OFFICE;
            info.confidence = 75;
        }
        return info;
    }

    // ── Uu tien 7: Office ────────────────────────────────────────────────────
    if (matchList(proc, OFFICE_PROCS)) {
        info.workload   = WL_OFFICE;
        info.confidence = 90;
        return info;
    }

    // ── Default: dua tren CPU load ───────────────────────────────────────────
    if (cpu_load_pct < 10.0f) {
        info.workload   = WL_IDLE;
        info.confidence = 80;
    } else if (cpu_load_pct < 40.0f) {
        info.workload   = WL_BROWSER;
        info.confidence = 50;
    } else {
        info.workload   = WL_OFFICE;
        info.confidence = 40;
    }
    return info;
}

// ── Test ────────────────────────────────────────────────────────────────────

#ifndef NO_MAIN_AD
int main() {
    printf("BatteryClaw Phase 5 — App Detector Test\n");
    printf("==========================================\n\n");

    for (int i = 0; i < 5; i++) {
        // Gia lap cpu load (thuc te lay tu state_collector)
        float fake_cpu = 25.0f;
        AppInfo info = detectWorkload(fake_cpu);

        printf("[%d] Foreground : %s\n",   i+1, info.fg_process.c_str());
        printf("    GPU load   : %.1f%%\n", info.gpu_load);
        printf("    Compiling  : %s\n",    info.is_compiling ? "YES" : "no");
        printf("    Workload   : %s (confidence=%d%%)\n\n",
               workloadName(info.workload), info.confidence);

        Sleep(2000);
    }
    return 0;
}
#endif
