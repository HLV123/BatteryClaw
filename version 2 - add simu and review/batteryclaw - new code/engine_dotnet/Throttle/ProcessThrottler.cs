// BatteryClaw — Throttle/ProcessThrottler.cs  (PHASE 5 — mục 5.3)
//
// Windows Power Throttling API chính chủ: throttle CPU cho TỪNG process
// (EcoQoS) thay vì hạ throttle toàn bộ CPU như powercfg.
//
//   SetProcessInformation(handle, ProcessPowerThrottling, &state, size)
//   với PROCESS_POWER_THROTTLING_STATE:
//     • ControlMask = PROCESS_POWER_THROTTLING_EXECUTION_SPEED
//     • StateMask   = bật  -> process chạy ở chế độ tiết kiệm (EcoQoS)
//                     0     -> bỏ throttle (chạy bình thường)
//
// Nhờ vậy agent có thể "ghìm" tiến trình nền (telemetry, updater, sync...)
// mà KHÔNG làm chậm app người dùng đang dùng (foreground). Tinh tế hơn nhiều.
//
// Một số thao tác không cần Admin (throttle process của chính user).

using System.Diagnostics;
using System.Runtime.InteropServices;

namespace BatteryClaw.Engine.Throttle;

public static class ProcessThrottler
{
    // ── P/Invoke ────────────────────────────────────────────────────────────
    private const int ProcessPowerThrottling = 4;

    [Flags]
    private enum PowerThrottlingFlags : uint
    {
        ExecutionSpeed = 0x1,
    }

    [StructLayout(LayoutKind.Sequential)]
    private struct PROCESS_POWER_THROTTLING_STATE
    {
        public uint Version;
        public uint ControlMask;
        public uint StateMask;
    }

    private const uint PROCESS_POWER_THROTTLING_CURRENT_VERSION = 1;

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool SetProcessInformation(
        IntPtr hProcess, int informationClass,
        ref PROCESS_POWER_THROTTLING_STATE info, uint size);

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern IntPtr OpenProcess(uint access, bool inherit, uint pid);

    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool CloseHandle(IntPtr h);

    private const uint PROCESS_SET_INFORMATION = 0x0200;

    // [P5-02] EcoQoS (PROCESS_POWER_THROTTLING_EXECUTION_SPEED) chi co tu
    //  Windows 11 (build 22000+). Tren Win10 SetProcessInformation se fail im lang.
    //  Kiem tra mot lan, cache lai. Tren Win10 -> SetEcoQoS tra false som.
    private static readonly bool _ecoQoSSupported =
        Environment.OSVersion.Platform == PlatformID.Win32NT &&
        Environment.OSVersion.Version.Build >= 22000;

    /// <summary>EcoQoS co kha dung tren may nay khong (Windows 11+)?</summary>
    public static bool IsEcoQoSSupported => _ecoQoSSupported;

    // ── API công khai ─────────────────────────────────────────────────────────

    /// <summary>Bật/tắt EcoQoS (throttle tiết kiệm) cho một PID.</summary>
    public static bool SetEcoQoS(int pid, bool enable)
    {
        if (!_ecoQoSSupported) return false;   // [P5-02] Win10 khong ho tro
        IntPtr h = OpenProcess(PROCESS_SET_INFORMATION, false, (uint)pid);
        if (h == IntPtr.Zero) return false;
        try
        {
            var state = new PROCESS_POWER_THROTTLING_STATE
            {
                Version     = PROCESS_POWER_THROTTLING_CURRENT_VERSION,
                ControlMask = (uint)PowerThrottlingFlags.ExecutionSpeed,
                // enable -> set bit (EcoQoS); tắt -> StateMask=0 (chạy bình thường)
                StateMask   = enable ? (uint)PowerThrottlingFlags.ExecutionSpeed : 0,
            };
            return SetProcessInformation(h, ProcessPowerThrottling, ref state,
                (uint)Marshal.SizeOf<PROCESS_POWER_THROTTLING_STATE>());
        }
        finally { CloseHandle(h); }
    }

    /// <summary>Bỏ throttle, để Windows tự quyết (reset về mặc định).</summary>
    public static bool ResetToAuto(int pid)
    {
        IntPtr h = OpenProcess(PROCESS_SET_INFORMATION, false, (uint)pid);
        if (h == IntPtr.Zero) return false;
        try
        {
            // ControlMask=ExecutionSpeed, StateMask=0, nhưng để "auto" thực sự
            // ta clear cả ControlMask -> Windows quản lý.
            var state = new PROCESS_POWER_THROTTLING_STATE
            {
                Version = PROCESS_POWER_THROTTLING_CURRENT_VERSION,
                ControlMask = 0,
                StateMask = 0,
            };
            return SetProcessInformation(h, ProcessPowerThrottling, ref state,
                (uint)Marshal.SizeOf<PROCESS_POWER_THROTTLING_STATE>());
        }
        finally { CloseHandle(h); }
    }

    /// <summary>Throttle các process nền theo tên (vd updater, telemetry).
    /// Trả số process đã throttle thành công.</summary>
    public static int ThrottleBackgroundByName(IEnumerable<string> names, bool enable)
    {
        int count = 0;
        var set = new HashSet<string>(names, StringComparer.OrdinalIgnoreCase);
        foreach (var p in Process.GetProcesses())
        {
            try
            {
                if (set.Contains(p.ProcessName) && SetEcoQoS(p.Id, enable))
                    count++;
            }
            catch { /* process có thể đã thoát */ }
        }
        return count;
    }
}
