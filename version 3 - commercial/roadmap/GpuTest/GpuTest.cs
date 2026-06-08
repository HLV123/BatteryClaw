// ════════════════════════════════════════════════════════════════════════
//  BatteryClaw — GpuTest (chan doan GPU switch)
//  Windows quan GPU PER-APP (Graphics Settings), khong cho ep tat dGPU toan cuc.
//  Cach hop le: dat preference per-app trong registry — dung cho Windows ghi khi
//  ban chon "Power saving" / "High performance" cho 1 app trong Settings.
//  Test nay DOC preference hien tai + THU ghi cho mot app vo hai (notepad) roi xoa.
//  Chay (PowerShell Admin):  cd E:\gputest ; dotnet run -c Release
// ════════════════════════════════════════════════════════════════════════

using System;
using Microsoft.Win32;

class GpuTest
{
    // Registry Windows luu GPU preference per-app o day:
    const string KEY = @"Software\Microsoft\DirectX\UserGpuPreferences";

    static void Main()
    {
        Console.WriteLine("============================================================");
        Console.WriteLine("  BatteryClaw — GPU PREFERENCE PROBE");
        Console.WriteLine("  Windows quan GPU per-app; test co che dat preference registry");
        Console.WriteLine("============================================================\n");

        ListGpus();
        ReadPreferences();
        TestWritePreference();

        Console.WriteLine("\n============================================================");
        Console.WriteLine("  XONG. COPY gui lai. Y nghia:");
        Console.WriteLine("   • Neu ghi/doc preference OK -> BatteryClaw co the GOI Y Windows");
        Console.WriteLine("     dung iGPU cho app tiet kiem pin (per-app, hop le).");
        Console.WriteLine("   • KHONG the ep tat dGPU toan cuc tu phan mem (Windows chan).");
        Console.WriteLine("============================================================");
        Console.WriteLine("\n(Nhan Enter de thoat)");
        Console.ReadLine();
    }

    static void ListGpus()
    {
        Console.WriteLine("[1] Cac GPU tren may (qua WMI):");
        try
        {
            using var s = new System.Management.ManagementObjectSearcher(
                "SELECT Name FROM Win32_VideoController");
            foreach (System.Management.ManagementObject mo in s.Get())
                Console.WriteLine($"    - {mo["Name"]}");
        }
        catch (Exception e) { Console.WriteLine($"    loi: {e.Message}"); }
        Console.WriteLine();
    }

    static void ReadPreferences()
    {
        Console.WriteLine("[2] GPU preference per-app hien tai (registry):");
        try
        {
            using var k = Registry.CurrentUser.OpenSubKey(KEY);
            if (k == null) { Console.WriteLine("    (chua co preference nao)"); Console.WriteLine(); return; }
            var names = k.GetValueNames();
            if (names.Length == 0) Console.WriteLine("    (rong)");
            foreach (var n in names)
                Console.WriteLine($"    {System.IO.Path.GetFileName(n)} = {k.GetValue(n)}");
        }
        catch (Exception e) { Console.WriteLine($"    loi: {e.Message}"); }
        Console.WriteLine();
    }

    static void TestWritePreference()
    {
        Console.WriteLine("[3] Thu GHI preference cho notepad (vo hai) roi XOA:");
        // GpuPreference=1 : power saving (iGPU); =2 : high performance (dGPU)
        string app = @"C:\Windows\System32\notepad.exe";
        try
        {
            using var k = Registry.CurrentUser.CreateSubKey(KEY);
            k.SetValue(app, "GpuPreference=1;");           // dat iGPU
            Console.WriteLine($"    ✓ Ghi OK: {app} -> GpuPreference=1 (iGPU)");
            var back = k.GetValue(app);
            Console.WriteLine($"    doc lai: {back}");
            k.DeleteValue(app);                            // xoa de tra nguyen trang
            Console.WriteLine("    ✓ Da xoa (tra nguyen trang)");
            Console.WriteLine("    KET LUAN: dat GPU preference per-app DUOC ✓");
        }
        catch (Exception e)
        {
            Console.WriteLine($"    ✗ Loi ghi: {e.Message}");
            Console.WriteLine("    KET LUAN: khong ghi duoc preference.");
        }
    }
}
