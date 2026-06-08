//  BatteryClaw — batteryclaw_main.cpp
//  IPC server chinh: doc state that + thuc thi lenh tu RL Brain
//
//  Fix: pipe security cho phep user thuong ket noi (khong can Admin cho Python)
//  Kien truc 2 thread:
//    Thread collector: thu thap WMI moi 1 giay (P1) -> g_state
//    Thread pipe: gui g_state cho Python, doc action

#define WIN32_LEAN_AND_MEAN
#define NOMINMAX
#include <windows.h>
#include <sddl.h>
#include <cstdio>
#include <string>
#include <sstream>
#include <atomic>
#include <thread>
#include <mutex>

#include "system_state.h"

SystemState collectState();
bool setCpuThrottleMax(int pct);
bool setCpuThrottleMin(int pct);
bool setBrightness(int pct);
bool deferBackgroundTasks(bool defer);

// ── Phase 1 actions ─────────────────────────────────────────────────────────
bool executeGpuSwitch(int mode, const SystemState& s);     // gpu_switch.cpp
bool setRefreshRate(int mode);                             // action_executor.cpp
bool setWifiPowerSave(bool on);                            // action_executor.cpp
bool setChargeLimit(int pct);                              // action_executor.cpp

#define PIPE_NAME    L"\\\\.\\pipe\\BatteryClaw"
#define PIPE_BUFSIZE 4096

// ── Shared state ─────────────────────────────────────────────────────────────
static SystemState       g_state  = {};
static std::mutex        g_mutex;
static std::atomic<bool> g_running{true};

// ── Collector thread ─────────────────────────────────────────────────────────
//  [Phase 1] cập nhật mỗi 1 giây (trước là 2 giây) để bám discharge rate sát hơn
void collectorThread() {
    while (g_running) {
        SystemState s = collectState();
        { std::lock_guard<std::mutex> lk(g_mutex); g_state = s; }
        Sleep(1000);
    }
}

// ── JSON helpers ─────────────────────────────────────────────────────────────
// [QUALITY-05] Escape chuoi truoc khi nhet vao JSON. fg_app (ten cua so) co the
//  chua dau nhay doi, backslash, ky tu dieu khien -> neu khong escape, JSON vo.
//  Vi du: fg_app = Video "Tutorial"  ->  "fg_app":"Video \"Tutorial\""
std::string jsonEscape(const std::string& in) {
    std::string out;
    out.reserve(in.size() + 8);
    for (unsigned char c : in) {
        switch (c) {
            case '"':  out += "\\\""; break;
            case '\\': out += "\\\\"; break;
            case '\b': out += "\\b";  break;
            case '\f': out += "\\f";  break;
            case '\n': out += "\\n";  break;
            case '\r': out += "\\r";  break;
            case '\t': out += "\\t";  break;
            default:
                if (c < 0x20) {                       // ky tu dieu khien khac
                    char buf[8];
                    std::snprintf(buf, sizeof(buf), "\\u%04x", c);
                    out += buf;
                } else {
                    out += static_cast<char>(c);
                }
        }
    }
    return out;
}

std::string stateToJson(const SystemState& s) {
    std::ostringstream o;
    o << "{\"type\":\"state\""
      << ",\"cpu_load\":"   << s.cpu_load_pct
      << ",\"cpu_mhz\":"    << s.cpu_clock_mhz
      << ",\"cpu_min\":"    << s.cpu_throttle_min
      << ",\"cpu_max\":"    << s.cpu_throttle_max
      << ",\"temp_c\":"     << s.cpu_temp_c
      << ",\"batt_pct\":"   << s.battery_pct
      << ",\"batt_mwh\":"   << s.remaining_mwh
      << ",\"batt_full\":"  << s.full_charge_mwh
      << ",\"charging\":"   << (s.is_charging  ? "true":"false")
      << ",\"plugged\":"    << (s.power_online ? "true":"false")
      << ",\"health\":"     << s.battery_health
      << ",\"brightness\":" << s.brightness_pct
      << ",\"dgpu\":"       << (s.dgpu_active  ? "true":"false")
      // ── Phase 1 — trường mới ───────────────────────────────────
      << ",\"discharge_mw\":"   << s.discharge_rate_mw
      << ",\"gpu_type\":"       << (int)s.gpu_active_type
      << ",\"gpu_power_mw\":"   << s.gpu_power_mw
      << ",\"gpu_load\":"       << s.gpu_load_pct
      << ",\"refresh_hz\":"     << s.screen_refresh_hz
      << ",\"wifi\":"           << (s.wifi_active  ? "true":"false")
      << ",\"audio\":"          << (s.audio_active ? "true":"false")
      << ",\"proc_count\":"     << s.process_count
      << ",\"ram_pct\":"        << s.ram_pressure_pct
      << ",\"tod\":"            << s.time_of_day_norm
      << ",\"fg_app\":\""   << jsonEscape(s.foreground_app) << "\""
      << ",\"workload\":\"browser\""
      << ",\"ts\":"         << s.timestamp_ms
      << "}\n";
    return o.str();
}

// [TODO-01] Tim vi tri VALUE cua mot key JSON mot cach an toan hon parse tho:
//  chi chap nhan key xuat hien o vi tri KEY (truoc no la '{' hoac ',', bo qua
//  khoang trang), tranh match nham khi key la prefix cua key khac
//  (vd tim "cpu_max" khong dinh "cpu_max_boost") hoac chuoi nam trong value.
//  Tra vi tri ngay sau dau ':' cua key, hoac npos.
static size_t jsonFindValuePos(const std::string& j, const std::string& k) {
    const std::string pat = "\"" + k + "\"";
    size_t from = 0;
    while (true) {
        size_t p = j.find(pat, from);
        if (p == std::string::npos) return std::string::npos;
        // ky tu khong-trang dung truoc phai la '{' hoac ',' (vi tri key)
        long b = (long)p - 1;
        while (b >= 0 && (j[b] == ' ' || j[b] == '\n' || j[b] == '\t')) b--;
        bool atKey = (b < 0) || (j[b] == '{' || j[b] == ',');
        // ngay sau key (bo qua trang) phai la ':'
        size_t a = p + pat.size();
        while (a < j.size() && (j[a] == ' ' || j[a] == '\t')) a++;
        if (atKey && a < j.size() && j[a] == ':') {
            return a + 1;   // ngay sau ':'
        }
        from = p + pat.size();
    }
}

// JSON float helper (cho cac truong moi)
float jsonFloat(const std::string& j, const std::string& k, float def=0.0f) {
    size_t p = jsonFindValuePos(j, k);
    if (p==std::string::npos) return def;
    try { return std::stof(j.substr(p)); } catch(...) { return def; }
}

int jsonInt(const std::string& j, const std::string& k, int def=-1) {
    size_t p = jsonFindValuePos(j, k);
    if (p==std::string::npos) return def;
    try { return std::stoi(j.substr(p)); } catch(...) { return def; }
}
bool jsonBool(const std::string& j, const std::string& k, bool def=false) {
    size_t p = jsonFindValuePos(j, k);
    if (p==std::string::npos) return def;
    while (p < j.size() && (j[p]==' '||j[p]=='\t')) p++;
    return j.compare(p, 4, "true") == 0;
}

// ── Execute action ────────────────────────────────────────────────────────────
void executeAction(const std::string& j) {
    int  cpu_max = jsonInt (j,"cpu_max",  -1);
    int  cpu_min = jsonInt (j,"cpu_min",  -1);
    int  bright  = jsonInt (j,"brightness",-1);
    bool defer   = jsonBool(j,"defer",   false);
    if (cpu_max>=20 && cpu_max<=100) setCpuThrottleMax(cpu_max);
    if (cpu_min>=0  && cpu_min<=30)  setCpuThrottleMin(cpu_min);
    if (bright >=0  && bright <=100) setBrightness(bright);
    deferBackgroundTasks(defer);

    // ── Phase 1 actions ───────────────────────────────────────
    int  gpu_switch  = jsonInt(j,"gpu_switch",   2);   // 2 = giữ nguyên
    int  refresh     = jsonInt(j,"refresh_rate", -1);  // -1 = không đổi
    int  charge_lim  = jsonInt(j,"charge_limit", -1);  // -1 = không giới hạn
    bool wifi_save   = jsonBool(j,"wifi_save",   false);

    if (gpu_switch != 2) {
        // cần state hiện tại cho lớp bảo vệ (không tắt khi đang dùng CUDA/game)
        SystemState s;
        { std::lock_guard<std::mutex> lk(g_mutex); s = g_state; }
        executeGpuSwitch(gpu_switch, s);
    }
    if (refresh   >= 0) setRefreshRate(refresh);
    if (charge_lim>= 0) setChargeLimit(charge_lim);
    setWifiPowerSave(wifi_save);

    printf("[ACT] cpu_max=%d bright=%d defer=%s gpu=%d refresh=%d charge=%d wifi_save=%s\n",
           cpu_max, bright, defer?"true":"false",
           gpu_switch, refresh, charge_lim, wifi_save?"true":"false");
}

// ── Tao pipe voi security cho phep moi user ket noi ─────────────────────────
//  SDDL: D:(A;;GRGW;;;WD) = Allow Everyone Read+Write
HANDLE createPipeAllowAll() {
    SECURITY_ATTRIBUTES sa = {};
    sa.nLength = sizeof(sa);
    sa.bInheritHandle = FALSE;

    // "D:(A;;GRGW;;;WD)" = Discretionary ACL: Allow Generic Read+Write to World (Everyone)
    if (!ConvertStringSecurityDescriptorToSecurityDescriptorA(
            "D:(A;;GRGW;;;WD)",
            SDDL_REVISION_1,
            &sa.lpSecurityDescriptor,
            nullptr))
    {
        // Fallback: dung NULL security (chi Admin)
        printf("[IPC] WARN: Khong set duoc security, chi Admin ket noi duoc\n");
        sa.lpSecurityDescriptor = nullptr;
    }

    HANDLE h = CreateNamedPipeW(
        PIPE_NAME,
        PIPE_ACCESS_DUPLEX,
        PIPE_TYPE_BYTE | PIPE_READMODE_BYTE | PIPE_WAIT,
        1, PIPE_BUFSIZE, PIPE_BUFSIZE, 0,
        &sa
    );

    if (sa.lpSecurityDescriptor)
        LocalFree(sa.lpSecurityDescriptor);

    return h;
}

// ── Pipe server loop ──────────────────────────────────────────────────────────
void runServer() {
    printf("BatteryClaw — IPC Server\n");
    printf("Pipe: \\\\.\\pipe\\BatteryClaw\n\n");

    std::thread ct(collectorThread);
    ct.detach();

    printf("Khoi dong state collector...\n");
    Sleep(3000);
    printf("San sang. Moi user deu co the ket noi.\n\n");

    while (true) {
        HANDLE hPipe = createPipeAllowAll();
        if (hPipe==INVALID_HANDLE_VALUE) {
            fprintf(stderr,"CreateNamedPipe FAIL: %lu\n",GetLastError());
            Sleep(1000); continue;
        }

        printf("[IPC] Waiting for RL Brain to connect...\n");
        ConnectNamedPipe(hPipe, nullptr);
        printf("[IPC] RL Brain connected!\n");

        char buf[PIPE_BUFSIZE];
        while (true) {
            SystemState s;
            { std::lock_guard<std::mutex> lk(g_mutex); s = g_state; }

            std::string msg = stateToJson(s);
            DWORD written=0;
            if (!WriteFile(hPipe,msg.c_str(),(DWORD)msg.size(),&written,nullptr)) {
                printf("[IPC] Client disconnected.\n");
                break;
            }

            DWORD avail=0;
            if (PeekNamedPipe(hPipe,nullptr,0,nullptr,&avail,nullptr) && avail>0) {
                DWORD nread=0;
                memset(buf,0,sizeof(buf));
                ReadFile(hPipe,buf,sizeof(buf)-1,&nread,nullptr);
                if (nread>0) {
                    std::string act(buf,nread);
                    while(!act.empty()&&(act.back()=='\n'||act.back()=='\r'))
                        act.pop_back();
                    if (act.find("\"type\":\"action\"")!=std::string::npos)
                        executeAction(act);
                }
            }
            Sleep(1000);
        }
        DisconnectNamedPipe(hPipe);
        CloseHandle(hPipe);
        printf("[IPC] Disconnected. Waiting again...\n");
    }
}

int main() {
    runServer();
    return 0;
}
