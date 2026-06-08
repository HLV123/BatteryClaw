// ════════════════════════════════════════════════════════════════════════
//  BatteryClaw — HardwareTest2
//  Test này dùng ĐÚNG file HardwareControl.cs mà engine thật sẽ dùng, gọi y hệt
//  cách engine gọi khi nhận action tu AI. Muc dich: xac nhan duong day "lenh AI
//  -> phan cung that" chay dung TRUOC khi build engine full (lau hon).
//
//  Chay (PowerShell Admin):
//     cd E:\hwtest2
//     dotnet run -c Release
// ════════════════════════════════════════════════════════════════════════

using System;
using System.Threading;
using BatteryClaw.Engine.Control;

class HardwareTest2
{
    static void Main()
    {
        Console.WriteLine("============================================================");
        Console.WriteLine("  BatteryClaw — HARDWARE TEST 2 (dung HardwareControl that)");
        Console.WriteLine("  Mo phong dung cach engine goi khi nhan action tu AI");
        Console.WriteLine("============================================================\n");

        // ── 1. ĐỌC trạng thái thật (giống engine collect) ───────────────────
        Console.WriteLine("[1] DOC trang thai that:");
        int br0 = HardwareControl.ReadBrightness();
        int hz0 = HardwareControl.ReadRefreshHz();
        Console.WriteLine($"    brightness hien tai = {br0}%  " + (br0 >= 0 ? "✓" : "✗ khong doc duoc"));
        Console.WriteLine($"    refresh hien tai    = {hz0}Hz {(hz0 >= 0 ? "✓" : "✗")}\n");

        // ── 2. Mô phỏng AI ra lệnh "tiết kiệm pin" (giống lúc BATTERY) ──────
        Console.WriteLine("[2] Mo phong AI lenh TIET KIEM (brightness 35%, CPU 40%, 60Hz):");
        Console.WriteLine($"    SetBrightness(35) = {HardwareControl.SetBrightness(35)}");
        Console.WriteLine($"    SetCpuMax(40)     = {HardwareControl.SetCpuMax(40)}");
        Console.WriteLine($"    SetRefreshHz(60)  = {HardwareControl.SetRefreshHz(60)}");
        Console.WriteLine($"    SetWifiPowerSave(true) = {HardwareControl.SetWifiPowerSave(true)}");
        Thread.Sleep(1500);
        Console.WriteLine($"    -> doc lai brightness = {HardwareControl.ReadBrightness()}% "
            + "(ky vong ~35)");
        Console.WriteLine($"    -> doc lai refresh = {HardwareControl.ReadRefreshHz()}Hz (ky vong 60)\n");

        // ── 3. Mô phỏng AI ra lệnh "hiệu năng" (giống lúc PLUGGED) ──────────
        Console.WriteLine("[3] Mo phong AI lenh HIEU NANG (brightness 90%, CPU 100%, 144Hz):");
        Console.WriteLine($"    SetBrightness(90)  = {HardwareControl.SetBrightness(90)}");
        Console.WriteLine($"    SetCpuMax(100)     = {HardwareControl.SetCpuMax(100)}");
        Console.WriteLine($"    SetRefreshHz(144)  = {HardwareControl.SetRefreshHz(144)}");
        Console.WriteLine($"    SetWifiPowerSave(false) = {HardwareControl.SetWifiPowerSave(false)}");
        Thread.Sleep(1500);
        Console.WriteLine($"    -> doc lai brightness = {HardwareControl.ReadBrightness()}% "
            + "(ky vong ~90)");
        Console.WriteLine($"    -> doc lai refresh = {HardwareControl.ReadRefreshHz()}Hz (ky vong 144)\n");

        // ── 4. Khôi phục về trạng thái ban đầu ──────────────────────────────
        Console.WriteLine("[4] KHOI PHUC ve trang thai ban dau:");
        if (br0 >= 0) HardwareControl.SetBrightness(br0);
        HardwareControl.SetCpuMax(100);
        if (hz0 >= 60) HardwareControl.SetRefreshHz(hz0);
        HardwareControl.SetWifiPowerSave(false);
        Console.WriteLine($"    da tra brightness={br0}%, CPU=100%, refresh={hz0}Hz\n");

        Console.WriteLine("============================================================");
        Console.WriteLine("  XONG. Kiem 2 dieu:");
        Console.WriteLine("   • Buoc [2]: brightness co tut ve ~35 va man hinh co toi di khong?");
        Console.WriteLine("   • Buoc [3]: brightness co len ~90 va refresh len 144Hz khong?");
        Console.WriteLine("  COPY toan bo ket qua nay gui lai.");
        Console.WriteLine("============================================================");
        Console.WriteLine("\n(Nhan Enter de thoat)");
        Console.ReadLine();
    }
}
