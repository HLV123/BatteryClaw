// BatteryClaw — Control/HardwareControl.cs  (PHASE 5 — thực thi action thật)
//
// Noi cac action cua AI vao phan cung that. Da xac nhan chay duoc tren may that
// (HardwareTest): brightness (WMI), CPU throttle (powercfg), refresh
// (ChangeDisplaySettingsEx), wifi adapter. Tat ca can quyen Admin.
//
// Co che AN TOAN: chi goi API khi gia tri MUC TIEU khac gia tri hien tai
// (tranh spam lenh moi 10s). Loi thi nuot, khong lam sap engine.

using System;
using System.Diagnostics;
using System.Management;
using System.Runtime.InteropServices;

namespace BatteryClaw.Engine.Control;

public static class HardwareControl
{
    // ── BRIGHTNESS (WMI) ────────────────────────────────────────────────────
    private static int _lastBrightness = -1;

    public static int ReadBrightness()
    {
        try
        {
            using var s = new ManagementObjectSearcher("root\\WMI",
                "SELECT CurrentBrightness FROM WmiMonitorBrightness");
            foreach (ManagementObject mo in s.Get())
                return Convert.ToInt32(mo["CurrentBrightness"]);
        }
        catch { }
        return -1;   // khong doc duoc (man ngoai / driver khong expose)
    }

    public static bool SetBrightness(int percent)
    {
        percent = Math.Clamp(percent, 0, 100);
        if (percent == _lastBrightness) return true;   // khong doi -> bo qua
        try
        {
            using var s = new ManagementObjectSearcher("root\\WMI",
                "SELECT * FROM WmiMonitorBrightnessMethods");
            foreach (ManagementObject mo in s.Get())
            {
                mo.InvokeMethod("WmiSetBrightness", new object[] { (uint)1, (byte)percent });
                _lastBrightness = percent;
                return true;
            }
        }
        catch { }
        return false;
    }

    // ── CPU THROTTLE (powercfg max processor state) ─────────────────────────
    private const string SubProcessor = "54533251-82be-4824-96c1-47b60b740d00";
    private const string MaxProcState = "bc5038f7-23e0-4960-96da-33abaf5935ec";
    private static int _lastCpuMax = -1;

    public static bool SetCpuMax(int percent)
    {
        percent = Math.Clamp(percent, 20, 100);   // khong duoi 20% (may treo)
        if (percent == _lastCpuMax) return true;
        try
        {
            int c1 = RunCmd("powercfg",
                $"/setacvalueindex SCHEME_CURRENT {SubProcessor} {MaxProcState} {percent}");
            int c2 = RunCmd("powercfg",
                $"/setdcvalueindex SCHEME_CURRENT {SubProcessor} {MaxProcState} {percent}");
            int c3 = RunCmd("powercfg", "/setactive SCHEME_CURRENT");
            if (c1 == 0 && c3 == 0) { _lastCpuMax = percent; return true; }
        }
        catch { }
        return false;
    }

    // ── REFRESH RATE (ChangeDisplaySettingsEx) ──────────────────────────────
    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Ansi)]
    private struct DEVMODE
    {
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 32)] public string dmDeviceName;
        public short dmSpecVersion, dmDriverVersion, dmSize, dmDriverExtra;
        public int dmFields;
        public int dmPositionX, dmPositionY;
        public int dmDisplayOrientation, dmDisplayFixedOutput;
        public short dmColor, dmDuplex, dmYResolution, dmTTOption, dmCollate;
        [MarshalAs(UnmanagedType.ByValTStr, SizeConst = 32)] public string dmFormName;
        public short dmLogPixels;
        public int dmBitsPerPel, dmPelsWidth, dmPelsHeight, dmDisplayFlags, dmDisplayFrequency;
        public int dmICMMethod, dmICMIntent, dmMediaType, dmDitherType, dmReserved1, dmReserved2;
        public int dmPanningWidth, dmPanningHeight;
    }

    [DllImport("user32.dll")]
    private static extern bool EnumDisplaySettings(string devName, int modeNum, ref DEVMODE dm);
    [DllImport("user32.dll")]
    private static extern int ChangeDisplaySettingsEx(
        string devName, ref DEVMODE dm, IntPtr hwnd, uint flags, IntPtr lParam);

    private const int ENUM_CURRENT_SETTINGS = -1;
    private const int DM_DISPLAYFREQUENCY = 0x400000;
    private const uint CDS_UPDATEREGISTRY = 0x01;
    private static int _lastRefresh = -1;

    public static int ReadRefreshHz()
    {
        DEVMODE dm = new DEVMODE();
        dm.dmSize = (short)Marshal.SizeOf(typeof(DEVMODE));
        if (EnumDisplaySettings(null, ENUM_CURRENT_SETTINGS, ref dm))
            return dm.dmDisplayFrequency;
        return -1;
    }

    public static bool SetRefreshHz(int hz)
    {
        if (hz == _lastRefresh) return true;
        try
        {
            DEVMODE dm = new DEVMODE();
            dm.dmSize = (short)Marshal.SizeOf(typeof(DEVMODE));
            if (!EnumDisplaySettings(null, ENUM_CURRENT_SETTINGS, ref dm)) return false;
            // kiem tra hz co duoc ho tro o do phan giai hien tai khong
            if (!IsRefreshSupported(hz, dm.dmPelsWidth, dm.dmPelsHeight)) return false;
            dm.dmDisplayFrequency = hz;
            dm.dmFields = DM_DISPLAYFREQUENCY;
            int r = ChangeDisplaySettingsEx(null, ref dm, IntPtr.Zero, CDS_UPDATEREGISTRY, IntPtr.Zero);
            if (r == 0) { _lastRefresh = hz; return true; }   // 0 = DISP_CHANGE_SUCCESSFUL
        }
        catch { }
        return false;
    }

    private static bool IsRefreshSupported(int hz, int w, int h)
    {
        DEVMODE d = new DEVMODE(); d.dmSize = (short)Marshal.SizeOf(typeof(DEVMODE));
        int i = 0;
        while (EnumDisplaySettings(null, i, ref d))
        {
            if (d.dmPelsWidth == w && d.dmPelsHeight == h && d.dmDisplayFrequency == hz)
                return true;
            i++;
        }
        return false;
    }

    // ── WIFI POWER SAVE (netsh) ─────────────────────────────────────────────
    private static int _lastWifi = -1;   // 0 = max performance, 1 = power save

    public static bool SetWifiPowerSave(bool save)
    {
        int want = save ? 1 : 0;
        if (want == _lastWifi) return true;
        try
        {
            // doi power scheme cua wireless adapter (AC/DC). 0=Max Perf, 3=Max Power Save
            // dung powercfg sub_none cua wireless: 19cbb8fa-5279-450e-9fac-8a3d5fedd0c1
            string subWifi = "19cbb8fa-5279-450e-9fac-8a3d5fedd0c1";
            string setting = "12bbebe6-58d6-4636-95bb-3217ef867c1a";
            int val = save ? 3 : 0;
            RunCmd("powercfg", $"/setacvalueindex SCHEME_CURRENT {subWifi} {setting} {val}");
            RunCmd("powercfg", $"/setdcvalueindex SCHEME_CURRENT {subWifi} {setting} {val}");
            int c = RunCmd("powercfg", "/setactive SCHEME_CURRENT");
            if (c == 0) { _lastWifi = want; return true; }
        }
        catch { }
        return false;
    }

    // ── helper ──────────────────────────────────────────────────────────────
    private static int RunCmd(string exe, string args)
    {
        try
        {
            var psi = new ProcessStartInfo(exe, args)
            {
                RedirectStandardOutput = true,
                RedirectStandardError = true,
                UseShellExecute = false,
                CreateNoWindow = true
            };
            using var p = Process.Start(psi);
            p.WaitForExit(5000);
            return p.ExitCode;
        }
        catch { return -1; }
    }
}
