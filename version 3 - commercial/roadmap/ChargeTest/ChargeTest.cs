// ════════════════════════════════════════════════════════════════════════
//  BatteryClaw — ChargeTest (chan doan charge limit)
//  Charge limit KHONG co API Windows chuan — moi hang lam rieng. Test nay DO xem
//  may ban (MSI) expose co che WMI nao de gioi han sac, TRUOC khi viet code dieu khien.
//  Chay (PowerShell Admin):  cd E:\chargetest ; dotnet run -c Release
// ════════════════════════════════════════════════════════════════════════

using System;
using System.Management;

class ChargeTest
{
    static void Main()
    {
        Console.WriteLine("============================================================");
        Console.WriteLine("  BatteryClaw — CHARGE LIMIT PROBE (chay Admin)");
        Console.WriteLine("  Do xem may co co che gioi han sac qua WMI khong");
        Console.WriteLine("============================================================\n");

        DetectVendor();
        ProbeMsiAcpi();
        ProbeLenovo();
        ProbeGenericWmiBattery();
        ProbeRootWmiClasses();

        Console.WriteLine("\n============================================================");
        Console.WriteLine("  XONG. COPY toan bo gui lai. Chu y dong nao bao 'TIM THAY'.");
        Console.WriteLine("  Neu khong dong nao tim thay -> may khong cho gioi han sac");
        Console.WriteLine("  qua phan mem (phai dung app chinh hang nhu MSI Center).");
        Console.WriteLine("============================================================");
        Console.WriteLine("\n(Nhan Enter de thoat)");
        Console.ReadLine();
    }

    static void DetectVendor()
    {
        Console.WriteLine("[0] Nhan dien hang may:");
        try
        {
            using var s = new ManagementObjectSearcher(
                "SELECT Manufacturer, Model FROM Win32_ComputerSystem");
            foreach (ManagementObject mo in s.Get())
                Console.WriteLine($"    {mo["Manufacturer"]} | {mo["Model"]}");
        }
        catch (Exception e) { Console.WriteLine($"    loi: {e.Message}"); }
        Console.WriteLine();
    }

    static void ProbeMsiAcpi()
    {
        Console.WriteLine("[1] MSI — thu namespace root\\WMI class MSI_*:");
        bool found = false;
        foreach (var cls in new[] { "MSI_ACPI", "MSI_BatteryHealth", "MSI_HardwareMonitor" })
        {
            try
            {
                using var s = new ManagementObjectSearcher("root\\WMI", $"SELECT * FROM {cls}");
                int n = 0;
                foreach (ManagementObject mo in s.Get()) { n++; }
                if (n > 0) { Console.WriteLine($"    ✓ TIM THAY {cls} ({n} instance)"); found = true; }
            }
            catch { /* class khong ton tai */ }
        }
        if (!found) Console.WriteLine("    (khong thay class MSI_* — may co the khong expose qua WMI)");
        Console.WriteLine();
    }

    static void ProbeLenovo()
    {
        Console.WriteLine("[2] Lenovo — thu class LENOVO_* (neu may Lenovo):");
        bool found = false;
        foreach (var cls in new[] { "Lenovo_SetOtherMethod", "Lenovo_GetOtherMethod" })
        {
            try
            {
                using var s = new ManagementObjectSearcher("root\\WMI", $"SELECT * FROM {cls}");
                int n = 0; foreach (ManagementObject mo in s.Get()) n++;
                if (n > 0) { Console.WriteLine($"    ✓ TIM THAY {cls}"); found = true; }
            }
            catch { }
        }
        if (!found) Console.WriteLine("    (khong thay — bo qua neu khong phai Lenovo)");
        Console.WriteLine();
    }

    static void ProbeGenericWmiBattery()
    {
        Console.WriteLine("[3] WMI battery co field gioi han sac chuan khong:");
        try
        {
            using var s = new ManagementObjectSearcher("root\\WMI",
                "SELECT * FROM BatteryStaticData");
            int n = 0;
            foreach (ManagementObject mo in s.Get())
            {
                n++;
                foreach (var p in mo.Properties)
                    if (p.Name.ToLower().Contains("charge") || p.Name.ToLower().Contains("threshold"))
                        Console.WriteLine($"    field: {p.Name} = {p.Value}");
            }
            if (n == 0) Console.WriteLine("    (BatteryStaticData rong)");
        }
        catch (Exception e) { Console.WriteLine($"    (khong co: {e.Message})"); }
        Console.WriteLine();
    }

    static void ProbeRootWmiClasses()
    {
        Console.WriteLine("[4] Liet ke class root\\WMI chua tu 'Battery'/'Charge' (gian tiep):");
        try
        {
            var scope = new ManagementScope("root\\WMI");
            scope.Connect();
            var q = new ManagementObjectSearcher(scope,
                new ObjectQuery("SELECT * FROM meta_class"));
            int shown = 0;
            foreach (ManagementClass c in q.Get())
            {
                string name = c["__CLASS"]?.ToString() ?? "";
                if ((name.ToLower().Contains("batt") || name.ToLower().Contains("charg"))
                    && shown < 20)
                { Console.WriteLine($"    - {name}"); shown++; }
            }
            if (shown == 0) Console.WriteLine("    (khong thay class lien quan)");
        }
        catch (Exception e) { Console.WriteLine($"    loi liet ke: {e.Message}"); }
    }
}
