// BatteryClaw — State/SystemStateCollector.cs  (Phase 5 — thu thập state thật)
//
// Bổ sung bộ thu thập state đầy đủ cho engine C#, để chế độ --serve gửi đủ
// 15 trường mà rl_brain cần (pin, CPU, nhiệt độ, GPU, discharge, refresh...).
// Trước đây --serve chỉ gửi discharge từ ETW -> mọi giá trị khác = 0.
//
// Nguồn dữ liệu (không cần Admin cho phần lớn):
//   • Pin           : Win32 GetSystemPowerStatus + WMI BatteryStatus
//   • CPU load      : GetSystemTimes (Win32, on dinh, khong can registry counter)
//   • Nhiệt độ CPU  : WMI MSAcpi_ThermalZoneTemperature (có thể cần quyền; fallback 0)
//   • RAM           : GlobalMemoryStatusEx
//   • Foreground app: GetForegroundWindow + GetWindowThreadProcessId
//   • Discharge     : ưu tiên ETW (nếu Admin), fallback WMI DischargeRate
//   • GPU/refresh   : ước lượng cơ bản (đủ cho contract; tinh chỉnh sau)
//
// Tên trường JSON khớp rl_brain.state_to_obs: batt_pct, batt_mwh, batt_full,
// cpu_load, temp_c, brightness, cpu_max, gpu_type, gpu_power_mw, discharge_mw,
// refresh_hz, wifi, audio, ram_pct, tod, plugged, charging, fg_app.

using System.Diagnostics;
using System.Management;
using System.Runtime.InteropServices;
using BatteryClaw.Engine.Control;

namespace BatteryClaw.Engine.State;

public sealed class SystemStateCollector : IDisposable
{
    private int _fullChargeMwh;     // học một lần từ WMI

    // CPU load qua GetSystemTimes (on dinh hon PerformanceCounter, khong fail).
    private ulong _prevIdle, _prevKernel, _prevUser;
    private bool _cpuPrimed;

    public SystemStateCollector()
    {
        _fullChargeMwh = ReadFullChargeMwh();
        PrimeCpu();
    }

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool GetSystemTimes(out long idle, out long kernel, out long user);

    private void PrimeCpu()
    {
        if (GetSystemTimes(out long i, out long k, out long u))
        {
            _prevIdle = (ulong)i; _prevKernel = (ulong)k; _prevUser = (ulong)u;
            _cpuPrimed = true;
        }
    }

    private double ReadCpuLoad()
    {
        if (!_cpuPrimed) { PrimeCpu(); return 0; }
        if (!GetSystemTimes(out long i, out long k, out long u)) return 0;
        ulong idle = (ulong)i, kernel = (ulong)k, user = (ulong)u;
        ulong dIdle = idle - _prevIdle;
        ulong dKernel = kernel - _prevKernel;
        ulong dUser = user - _prevUser;
        _prevIdle = idle; _prevKernel = kernel; _prevUser = user;
        // kernel da bao gom idle -> tong = kernel + user; busy = tong - idle
        ulong total = dKernel + dUser;
        if (total == 0) return 0;
        double busy = (double)(total - dIdle) / total * 100.0;
        return Math.Clamp(Math.Round(busy, 1), 0, 100);
    }

    // ── Win32 power status ──────────────────────────────────────────────────
    [StructLayout(LayoutKind.Sequential)]
    private struct SYSTEM_POWER_STATUS
    {
        public byte ACLineStatus;        // 0=battery,1=plugged,255=unknown
        public byte BatteryFlag;
        public byte BatteryLifePercent;  // 0..100, 255=unknown
        public byte SystemStatusFlag;
        public int  BatteryLifeTime;
        public int  BatteryFullLifeTime;
    }
    [DllImport("kernel32.dll")]
    private static extern bool GetSystemPowerStatus(out SYSTEM_POWER_STATUS s);

    [StructLayout(LayoutKind.Sequential)]
    private struct MEMORYSTATUSEX
    {
        public uint dwLength;
        public uint dwMemoryLoad;        // % RAM đang dùng
        public ulong ullTotalPhys, ullAvailPhys, ullTotalPageFile, ullAvailPageFile;
        public ulong ullTotalVirtual, ullAvailVirtual, ullAvailExtendedVirtual;
    }
    [DllImport("kernel32.dll")]
    private static extern bool GlobalMemoryStatusEx(ref MEMORYSTATUSEX s);

    [DllImport("user32.dll")] private static extern IntPtr GetForegroundWindow();
    [DllImport("user32.dll")] private static extern uint GetWindowThreadProcessId(IntPtr h, out uint pid);

    // ── Thu thập một snapshot đầy đủ ─────────────────────────────────────────
    public Dictionary<string, object> Collect(double etwDischargeMw)
    {
        var d = new Dictionary<string, object> { ["type"] = "state" };

        // Pin + nguồn
        int battPct = 50; bool plugged = false, charging = false;
        if (GetSystemPowerStatus(out var ps))
        {
            if (ps.BatteryLifePercent != 255) battPct = ps.BatteryLifePercent;
            plugged  = ps.ACLineStatus == 1;
            charging = (ps.BatteryFlag & 0x08) != 0;
        }
        d["batt_pct"]  = battPct;
        d["plugged"]   = plugged;
        d["charging"]  = charging;
        _lastPlugged   = plugged;   // cho ReadBatteryWmi uoc luong discharge dung

        // Dung lượng pin hiện tại + đầy (mWh) từ WMI
        var (remainMwh, fullMwh, dischargeWmiMw) = ReadBatteryWmi();
        if (fullMwh > 0) { _fullChargeMwh = fullMwh; }
        d["batt_full"] = _fullChargeMwh;
        d["batt_mwh"]  = remainMwh > 0 ? remainMwh
                          : (int)(_fullChargeMwh * battPct / 100.0);

        // CPU load (GetSystemTimes — on dinh, khong fail nhu PerformanceCounter)
        d["cpu_load"] = ReadCpuLoad();

        // Nhiệt độ CPU (WMI thermal zone; nhiều máy chặn -> fallback 0)
        d["temp_c"] = ReadCpuTempC();

        // RAM
        var mem = new MEMORYSTATUSEX { dwLength = (uint)Marshal.SizeOf<MEMORYSTATUSEX>() };
        d["ram_pct"] = GlobalMemoryStatusEx(ref mem) ? (int)mem.dwMemoryLoad : 50;

        // Discharge: WMI DischargeRate dang tin tren may that (vd MSI tra 6-11W).
        //  ETW thuong tra ~0-1mW (gan nhu khong hoat dong) -> KHONG uu tien ETW nua.
        //  Uu tien: WMI > nguong -> dung WMI; neu WMI=0 ma ETW du lon -> dung ETW;
        //  con lai dung gia tri uoc luong (da tinh trong ReadBatteryWmi).
        double discharge;
        if (dischargeWmiMw > 1.0)
            discharge = dischargeWmiMw;                 // WMI that (uu tien)
        else if (etwDischargeMw > 100.0)
            discharge = etwDischargeMw;                 // ETW chi dung khi du lon
        else
            discharge = dischargeWmiMw;                 // gia tri uoc luong (ReadBatteryWmi)
        d["discharge_mw"] = discharge;

        // Foreground app
        d["fg_app"] = GetForegroundApp();
        d["fg_app_path"] = GetForegroundAppPath();   // [3.2] full path cho GPU preference

        // GPU + refresh + radio: giá trị hợp lý mặc định (tinh chỉnh sau nếu cần)
        d["gpu_type"]     = 1;        // laptop có dGPU (RTX) — engine có thể nâng cấp dò thật
        d["gpu_power_mw"] = 0;        // chưa đo GPU power ở C# -> 0 (an toàn cho obs)
        d["refresh_hz"]   = GetRefreshHz();
        int realBr = HardwareControl.ReadBrightness();
        d["brightness"]   = realBr >= 0 ? realBr : 80;   // doc that; fallback 80 neu khong doc duoc
        d["cpu_max"]      = 100;
        d["wifi"]         = true;
        d["audio"]        = false;

        // Thời điểm trong ngày (0..1)
        var now = DateTime.Now;
        d["tod"] = Math.Round((now.Hour * 3600 + now.Minute * 60 + now.Second) / 86400.0, 4);

        return d;
    }

    // ── WMI helpers ───────────────────────────────────────────────────────────
    private static int ReadFullChargeMwh()
    {
        try
        {
            using var s = new ManagementObjectSearcher(
                "root\\WMI", "SELECT FullChargedCapacity FROM BatteryFullChargedCapacity");
            foreach (ManagementObject mo in s.Get())
                return Convert.ToInt32(mo["FullChargedCapacity"]);
        }
        catch { }
        return 50000;   // fallback trung tính (rl_brain cũng tự học)
    }

    private (int remain, int full, double dischargeMw) ReadBatteryWmi()
    {
        int remain = 0, full = 0; double disch = 0;
        try
        {
            using var s = new ManagementObjectSearcher(
                "root\\WMI", "SELECT RemainingCapacity, ChargeRate, DischargeRate FROM BatteryStatus");
            foreach (ManagementObject mo in s.Get())
            {
                remain = Convert.ToInt32(mo["RemainingCapacity"]);
                var dr = mo["DischargeRate"];
                if (dr != null) disch = Convert.ToDouble(dr);
            }
        }
        catch { }
        try
        {
            using var s2 = new ManagementObjectSearcher(
                "root\\WMI", "SELECT FullChargedCapacity FROM BatteryFullChargedCapacity");
            foreach (ManagementObject mo in s2.Get())
                full = Convert.ToInt32(mo["FullChargedCapacity"]);
        }
        catch { }

        // [FIX Disch=0 v2] Nhieu laptop (MSI) bao DischargeRate=0 du dang xa.
        //  Uoc luong tu toc do tut RemainingCapacity. LUU Y: pin tut 1% mat vai phut,
        //  giua 2 lan doc cach 10s thuong CHUA doi -> phai chi cap nhat moc khi gia
        //  tri THAT SU doi, va GIU lai discharge uoc luong gan nhat cho cac lan chua doi.
        var now = DateTime.UtcNow;
        if (disch <= 1.0 && remain > 0 && !_lastPlugged)
        {
            if (_prevRemain <= 0)
            {
                _prevRemain = remain; _prevRemainTime = now;   // mốc đầu
            }
            else if (remain < _prevRemain)                     // pin VỪA tụt 1 nấc
            {
                double dtSec = (now - _prevRemainTime).TotalSeconds;
                if (dtSec >= 1.0)
                {
                    double dropMwh = _prevRemain - remain;
                    _estDischargeMw = dropMwh / (dtSec / 3600.0);
                }
                _prevRemain = remain; _prevRemainTime = now;   // chỉ update khi đã đổi
            }
            // dùng giá trị ước lượng gần nhất (giữ giữa các nấc); fallback nếu chưa có
            disch = _estDischargeMw > 0 ? _estDischargeMw : disch;
        }
        else if (_lastPlugged)
        {
            _prevRemain = 0; _estDischargeMw = 0;   // cắm sạc -> reset mốc
        }
        return (remain, full, disch);
    }
    private double _estDischargeMw = 0;
    private int _prevRemain = 0;
    private DateTime _prevRemainTime = DateTime.UtcNow;
    private bool _lastPlugged = false;

    private static double ReadCpuTempC()
    {
        try
        {
            using var s = new ManagementObjectSearcher(
                "root\\WMI", "SELECT CurrentTemperature FROM MSAcpi_ThermalZoneTemperature");
            foreach (ManagementObject mo in s.Get())
            {
                // CurrentTemperature unit is 1/10 Kelvin
                double tenthKelvin = Convert.ToDouble(mo["CurrentTemperature"]);
                double c = tenthKelvin / 10.0 - 273.15;
                // Sanity check: many laptops (e.g. MSI) block this WMI class and
                // return 0 -> would give -273C. Treat out-of-range as "no data".
                if (c < 0 || c > 120) return -1;   // -1 = no reading
                return Math.Round(c, 1);
            }
        }
        catch { }
        return -1;   // no reading available
    }

    private static int GetRefreshHz()
    {
        try
        {
            using var s = new ManagementObjectSearcher(
                "SELECT CurrentRefreshRate FROM Win32_VideoController");
            foreach (ManagementObject mo in s.Get())
            {
                var r = mo["CurrentRefreshRate"];
                if (r != null) return Convert.ToInt32(r);
            }
        }
        catch { }
        return 60;
    }

    private static string GetForegroundApp()
    {
        try
        {
            IntPtr h = GetForegroundWindow();
            if (h == IntPtr.Zero) return "";
            GetWindowThreadProcessId(h, out uint pid);
            if (pid == 0) return "";
            using var p = Process.GetProcessById((int)pid);
            return p.ProcessName + ".exe";
        }
        catch { return ""; }
    }

    private static string GetForegroundAppPath()
    {
        try
        {
            IntPtr h = GetForegroundWindow();
            if (h == IntPtr.Zero) return "";
            GetWindowThreadProcessId(h, out uint pid);
            if (pid == 0) return "";
            using var p = Process.GetProcessById((int)pid);
            return p.MainModule?.FileName ?? "";   // full path (.exe)
        }
        catch { return ""; }
    }

    public void Dispose() { }
}
