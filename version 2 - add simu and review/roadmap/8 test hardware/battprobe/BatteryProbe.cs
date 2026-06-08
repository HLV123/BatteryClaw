// ════════════════════════════════════════════════════════════════════════
//  BatteryClaw — BatteryProbe
//  Doc TRUC TIEP cac nguon pin tren may de biet may bao gia tri gi that.
//  Muc dich: xac dinh vi sao Disch luon ~0, va nguon nao dung de uoc luong.
//  Chay (PowerShell Admin):  cd E:\battprobe ; dotnet run -c Release
//  RUT SAC khi chay (de o che do BATTERY) thi moi do duoc discharge.
// ════════════════════════════════════════════════════════════════════════

using System;
using System.Management;
using System.Threading;

class BatteryProbe
{
    static void Main()
    {
        Console.WriteLine("============================================================");
        Console.WriteLine("  BATTERY PROBE — doc nguon pin that tren may");
        Console.WriteLine("  *** RUT SAC RA (chay pin) truoc khi chay de do discharge ***");
        Console.WriteLine("============================================================\n");

        // doc 3 lan cach nhau 15s de xem RemainingCapacity co tut khong
        for (int i = 1; i <= 3; i++)
        {
            Console.WriteLine($"--- Lan doc {i} ({DateTime.Now:HH:mm:ss}) ---");
            ProbeBatteryStatus();
            ProbeWin32Battery();
            if (i < 3) { Console.WriteLine("  (cho 15s...)\n"); Thread.Sleep(15000); }
        }

        Console.WriteLine("\n============================================================");
        Console.WriteLine("  XONG. COPY toan bo gui lai. Chu y:");
        Console.WriteLine("   • DischargeRate co > 0 khong?");
        Console.WriteLine("   • RemainingCapacity co GIAM dan qua 3 lan doc khong?");
        Console.WriteLine("============================================================");
        Console.WriteLine("\n(Nhan Enter de thoat)");
        Console.ReadLine();
    }

    static void ProbeBatteryStatus()
    {
        try
        {
            using var s = new ManagementObjectSearcher("root\\WMI",
                "SELECT * FROM BatteryStatus");
            bool found = false;
            foreach (ManagementObject mo in s.Get())
            {
                found = true;
                Console.WriteLine("  [BatteryStatus WMI]");
                Console.WriteLine($"    RemainingCapacity = {Safe(mo, "RemainingCapacity")} (mWh)");
                Console.WriteLine($"    DischargeRate     = {Safe(mo, "DischargeRate")} (mW)");
                Console.WriteLine($"    ChargeRate        = {Safe(mo, "ChargeRate")} (mW)");
                Console.WriteLine($"    Charging          = {Safe(mo, "Charging")}");
                Console.WriteLine($"    Discharging       = {Safe(mo, "Discharging")}");
                Console.WriteLine($"    Voltage           = {Safe(mo, "Voltage")} (mV)");
            }
            if (!found) Console.WriteLine("  [BatteryStatus WMI] (rong - khong co instance)");
        }
        catch (Exception e) { Console.WriteLine($"  [BatteryStatus WMI] LOI: {e.Message}"); }
    }

    static void ProbeWin32Battery()
    {
        try
        {
            using var s = new ManagementObjectSearcher(
                "SELECT * FROM Win32_Battery");
            foreach (ManagementObject mo in s.Get())
            {
                Console.WriteLine("  [Win32_Battery]");
                Console.WriteLine($"    EstimatedChargeRemaining = {Safe(mo, "EstimatedChargeRemaining")} (%)");
                Console.WriteLine($"    BatteryStatus            = {Safe(mo, "BatteryStatus")} (1=discharging,2=AC)");
                Console.WriteLine($"    DesignCapacity           = {Safe(mo, "DesignCapacity")}");
                Console.WriteLine($"    FullChargeCapacity       = {Safe(mo, "FullChargeCapacity")}");
            }
        }
        catch (Exception e) { Console.WriteLine($"  [Win32_Battery] LOI: {e.Message}"); }
        Console.WriteLine();
    }

    static string Safe(ManagementObject mo, string prop)
    {
        try { var v = mo[prop]; return v?.ToString() ?? "null"; }
        catch { return "(khong co)"; }
    }
}
