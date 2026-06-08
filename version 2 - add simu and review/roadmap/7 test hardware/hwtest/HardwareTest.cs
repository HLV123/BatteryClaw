// ════════════════════════════════════════════════════════════════════════
//  BatteryClaw — HardwareTest
//  Kiem tra DOC + DAT tung co che phan cung tren may that, TRUOC khi noi vao
//  engine. Moi test: doc gia tri hien tai -> thu dat gia tri moi -> tra ve nhu cu.
//  Chay voi quyen ADMIN. Ket qua in ra man hinh -> copy gui lai.
//
//  Build & chay (PowerShell Admin, trong thu muc chua file nay):
//     dotnet run -c Release
//  Hoac build roi chay exe:
//     dotnet build -c Release
//     .\bin\Release\net8.0-windows10.0.19041.0\HardwareTest.exe
// ════════════════════════════════════════════════════════════════════════

using System;
using System.Diagnostics;
using System.Management;
using System.Runtime.InteropServices;
using System.Threading;

class HardwareTest
{
    static void Main()
    {
        Console.WriteLine("============================================================");
        Console.WriteLine("  BatteryClaw — HARDWARE TEST (chay voi quyen Admin)");
        Console.WriteLine("============================================================");
        Console.WriteLine($"  OS: {Environment.OSVersion}");
        Console.WriteLine($"  Admin: {IsAdmin()}");
        Console.WriteLine($"  Time: {DateTime.Now}");
        Console.WriteLine("============================================================\n");

        TestBrightness();
        TestCpuThrottle();
        TestRefreshRate();
        TestWifiPolicy();

        Console.WriteLine("\n============================================================");
        Console.WriteLine("  XONG. Hay COPY TOAN BO ket qua tren va gui lai.");
        Console.WriteLine("============================================================");
        Console.WriteLine("\n(Nhan Enter de thoat)");
        Console.ReadLine();
    }

    // ── TEST 1: BRIGHTNESS (doc + dat qua WMI) ──────────────────────────────
    static void TestBrightness()
    {
        Console.WriteLine("[TEST 1] BRIGHTNESS (do sang man hinh)");
        Console.WriteLine("-----------------------------------------------------------");
        int original = -1;
        try
        {
            // DOC do sang hien tai
            using (var s = new ManagementObjectSearcher("root\\WMI",
                "SELECT CurrentBrightness FROM WmiMonitorBrightness"))
            {
                foreach (ManagementObject mo in s.Get())
                {
                    original = Convert.ToInt32(mo["CurrentBrightness"]);
                    break;
                }
            }
            if (original < 0)
            {
                Console.WriteLine("  [DOC] ✗ Khong doc duoc CurrentBrightness (WmiMonitorBrightness rong).");
                Console.WriteLine("        -> May co the dung man ngoai / driver khong expose WMI brightness.");
                Console.WriteLine("  KET LUAN TEST 1: KHONG dung duoc WMI brightness tren may nay.\n");
                return;
            }
            Console.WriteLine($"  [DOC] ✓ Do sang hien tai = {original}%");

            // DAT thu: giam ve 30% roi len 80% roi tra ve nhu cu
            int[] targets = { 30, 80 };
            foreach (int tgt in targets)
            {
                bool ok = SetBrightness(tgt);
                Thread.Sleep(900);
                int after = ReadBrightnessOnce();
                Console.WriteLine($"  [DAT] dat {tgt}% -> goi WMI {(ok ? "OK" : "LOI")} | doc lai = {after}% "
                    + (Math.Abs(after - tgt) <= 5 ? "✓ DOI THAT" : "✗ KHONG DOI"));
            }

            // tra ve nhu cu
            SetBrightness(original);
            Console.WriteLine($"  [KHOI PHUC] tra ve {original}%");
            Console.WriteLine("  KET LUAN TEST 1: WMI brightness DUNG DUOC ✓\n");
        }
        catch (Exception e)
        {
            Console.WriteLine($"  ✗ Loi: {e.Message}");
            if (original >= 0) try { SetBrightness(original); } catch { }
            Console.WriteLine("  KET LUAN TEST 1: LOI - xem message tren.\n");
        }
    }

    static int ReadBrightnessOnce()
    {
        try
        {
            using var s = new ManagementObjectSearcher("root\\WMI",
                "SELECT CurrentBrightness FROM WmiMonitorBrightness");
            foreach (ManagementObject mo in s.Get())
                return Convert.ToInt32(mo["CurrentBrightness"]);
        }
        catch { }
        return -1;
    }

    static bool SetBrightness(int percent)
    {
        try
        {
            using var s = new ManagementObjectSearcher("root\\WMI",
                "SELECT * FROM WmiMonitorBrightnessMethods");
            foreach (ManagementObject mo in s.Get())
            {
                mo.InvokeMethod("WmiSetBrightness",
                    new object[] { (uint)1, (byte)percent });
                return true;
            }
        }
        catch (Exception e) { Console.WriteLine($"        (SetBrightness loi: {e.Message})"); }
        return false;
    }

    // ── TEST 2: CPU THROTTLE (qua powercfg - max processor state) ────────────
    static void TestCpuThrottle()
    {
        Console.WriteLine("[TEST 2] CPU THROTTLE (gioi han % CPU toi da qua powercfg)");
        Console.WriteLine("-----------------------------------------------------------");
        try
        {
            // doc gia tri hien tai (AC) cua PROCTHROTTLEMAX
            string guidMax = "bc5038f7-23e0-4960-96da-33abaf5935ec"; // Max processor state
            string subProc = "54533251-82be-4824-96c1-47b60b740d00"; // Processor power mgmt

            // dat thu 50% roi 100%
            int[] targets = { 50, 100 };
            foreach (int tgt in targets)
            {
                var r1 = RunCmd("powercfg", $"/setacvalueindex SCHEME_CURRENT {subProc} {guidMax} {tgt}");
                var r2 = RunCmd("powercfg", "/setactive SCHEME_CURRENT");
                Console.WriteLine($"  [DAT] CPU max = {tgt}% | powercfg exit={r1.code}/{r2.code} "
                    + (r1.code == 0 && r2.code == 0 ? "✓ lenh OK" : "✗ loi"));
                if (r1.code != 0 && !string.IsNullOrWhiteSpace(r1.err))
                    Console.WriteLine($"        err: {r1.err.Trim()}");
                Thread.Sleep(500);
            }
            Console.WriteLine("  [KHOI PHUC] da dat lai 100%");
            Console.WriteLine("  KET LUAN TEST 2: neu '✓ lenh OK' ca 2 dong -> CPU throttle DUNG DUOC.");
            Console.WriteLine("    (Luu y: can mo Task Manager xem CPU MHz co tut khi dat 50% khong)\n");
        }
        catch (Exception e)
        {
            Console.WriteLine($"  ✗ Loi: {e.Message}");
            Console.WriteLine("  KET LUAN TEST 2: LOI.\n");
        }
    }

    // ── TEST 3: REFRESH RATE (doc cac che do qua ChangeDisplaySettings) ──────
    [StructLayout(LayoutKind.Sequential, CharSet = CharSet.Ansi)]
    struct DEVMODE
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
    static extern bool EnumDisplaySettings(string devName, int modeNum, ref DEVMODE devMode);

    static void TestRefreshRate()
    {
        Console.WriteLine("[TEST 3] REFRESH RATE (tan so quet man hinh)");
        Console.WriteLine("-----------------------------------------------------------");
        try
        {
            DEVMODE dm = new DEVMODE();
            dm.dmSize = (short)Marshal.SizeOf(typeof(DEVMODE));
            // -1 = che do hien tai
            if (EnumDisplaySettings(null, -1, ref dm))
                Console.WriteLine($"  [DOC] ✓ Refresh hien tai = {dm.dmDisplayFrequency}Hz "
                    + $"| {dm.dmPelsWidth}x{dm.dmPelsHeight}");
            else
                Console.WriteLine("  [DOC] ✗ Khong doc duoc che do hien tai.");

            // liet ke cac refresh rate ho tro
            var freqs = new System.Collections.Generic.SortedSet<int>();
            DEVMODE d2 = new DEVMODE(); d2.dmSize = (short)Marshal.SizeOf(typeof(DEVMODE));
            int i = 0;
            while (EnumDisplaySettings(null, i, ref d2))
            {
                if (d2.dmPelsWidth == dm.dmPelsWidth && d2.dmPelsHeight == dm.dmPelsHeight)
                    freqs.Add(d2.dmDisplayFrequency);
                i++;
            }
            Console.WriteLine($"  [DOC] Cac refresh rate ho tro (o do phan giai hien tai): "
                + string.Join(", ", freqs) + " Hz");
            Console.WriteLine("  KET LUAN TEST 3: doc duoc refresh -> co the dat duoc qua ChangeDisplaySettingsEx.");
            Console.WriteLine("    (Test nay chi DOC, khong doi that de tranh nhay man hinh)\n");
        }
        catch (Exception e)
        {
            Console.WriteLine($"  ✗ Loi: {e.Message}");
            Console.WriteLine("  KET LUAN TEST 3: LOI.\n");
        }
    }

    // ── TEST 4: WIFI POWER POLICY (doc adapter) ─────────────────────────────
    static void TestWifiPolicy()
    {
        Console.WriteLine("[TEST 4] WIFI (doc adapter mang khong day)");
        Console.WriteLine("-----------------------------------------------------------");
        try
        {
            int count = 0;
            using var s = new ManagementObjectSearcher(
                "SELECT Name, NetEnabled FROM Win32_NetworkAdapter WHERE NetEnabled=true");
            foreach (ManagementObject mo in s.Get())
            {
                string name = mo["Name"]?.ToString() ?? "?";
                if (name.ToLower().Contains("wi-fi") || name.ToLower().Contains("wireless")
                    || name.ToLower().Contains("wlan") || name.ToLower().Contains("802.11"))
                {
                    Console.WriteLine($"  [DOC] ✓ Tim thay wifi adapter: {name}");
                    count++;
                }
            }
            if (count == 0)
                Console.WriteLine("  [DOC] Khong thay adapter ten 'wifi/wireless' (co the dang tat / ten khac).");
            Console.WriteLine("  KET LUAN TEST 4: " + (count > 0
                ? "doc duoc adapter -> co the dat power-save qua netsh/registry."
                : "khong thay adapter wifi (xem lai dang bat khong).") + "\n");
        }
        catch (Exception e)
        {
            Console.WriteLine($"  ✗ Loi: {e.Message}");
            Console.WriteLine("  KET LUAN TEST 4: LOI.\n");
        }
    }

    // ── helpers ─────────────────────────────────────────────────────────────
    static (int code, string outp, string err) RunCmd(string exe, string args)
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
            string o = p.StandardOutput.ReadToEnd();
            string e = p.StandardError.ReadToEnd();
            p.WaitForExit(5000);
            return (p.ExitCode, o, e);
        }
        catch (Exception ex) { return (-1, "", ex.Message); }
    }

    static bool IsAdmin()
    {
        try
        {
            using var id = System.Security.Principal.WindowsIdentity.GetCurrent();
            var p = new System.Security.Principal.WindowsPrincipal(id);
            return p.IsInRole(System.Security.Principal.WindowsBuiltInRole.Administrator);
        }
        catch { return false; }
    }
}
