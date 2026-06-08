// BatteryClaw — Etw/EtwPowerMonitor.cs  (PHASE 5 — mục 5.1)
//
// ETW (Event Tracing for Windows) là API duy nhất cho phép đọc power event
// ở độ phân giải cao (~ms), thay vì polling WMI mỗi 1-2 giây như Phase 1.
//
// Nguồn event:
//   • Microsoft-Windows-Kernel-Power            — chuyển trạng thái nguồn, throttle
//   • Microsoft-Windows-UserModePowerService    — thay đổi power scheme
//
// Lớp này chạy một session ETW nền, gom event và cập nhật ảnh chụp power mới nhất.
// Engine chính (Program.cs) đọc snapshot này khi cần — không chặn luồng IPC.
//
// Ghi chú: cần quyền Administrator để mở real-time ETW session.

using Microsoft.Diagnostics.Tracing;
using Microsoft.Diagnostics.Tracing.Session;
using Microsoft.Diagnostics.Tracing.Parsers;

namespace BatteryClaw.Engine.Etw;

/// <summary>Ảnh chụp power mới nhất từ ETW (đọc bởi engine chính).</summary>
public sealed class PowerSnapshot
{
    public double DischargeRateMw;     // tốc độ xả ước lượng (mW) — cập nhật realtime
    public int    ThrottleEvents;      // số lần CPU bị throttle gần đây
    public long   LastUpdateTicks;     // thời điểm cập nhật cuối (DateTime.Ticks)
}

public sealed class EtwPowerMonitor : IDisposable
{
    private const string SessionName = "BatteryClawPowerSession";
    private TraceEventSession? _session;
    private Thread? _thread;
    private volatile bool _running;

    private readonly object _lock = new();
    private readonly PowerSnapshot _snapshot = new();

    /// <summary>Bắt đầu session ETW nền. Trả false nếu không đủ quyền.</summary>
    public bool Start()
    {
        // ETW realtime cần Admin. IsElevated() trả bool? -> coi null là chưa rõ.
        if (TraceEventSession.IsElevated() != true)
            return false;

        try
        {
            _session = new TraceEventSession(SessionName);
            // Bật provider Kernel-Power. Keyword 0 = mặc định; lọc thêm ở handler.
            _session.EnableProvider("Microsoft-Windows-Kernel-Power");
            _session.EnableProvider("Microsoft-Windows-UserModePowerService");

            _session.Source.Dynamic.All += OnEvent;

            _running = true;
            _thread = new Thread(() =>
            {
                // Process() chặn cho tới khi session dừng -> chạy ở thread riêng.
                try { _session.Source.Process(); }
                catch { /* session bị dừng khi Dispose */ }
            }) { IsBackground = true, Name = "EtwPower" };
            _thread.Start();
            return true;
        }
        catch
        {
            return false;
        }
    }

    private void OnEvent(TraceEvent data)
    {
        // Mỗi event power liên quan -> cập nhật snapshot.
        // Tên event cụ thể thay đổi theo phiên bản Windows; ta nhận diện mềm dẻo
        // qua tên/đối số thay vì hard-code schema.
        var name = data.EventName ?? string.Empty;

        if (name.Contains("Throttle", StringComparison.OrdinalIgnoreCase))
        {
            lock (_lock) { _snapshot.ThrottleEvents++; _snapshot.LastUpdateTicks = DateTime.UtcNow.Ticks; }
        }

        // Một số phiên bản phát "RateMilliwatts" / "Power" trong payload.
        foreach (var pn in data.PayloadNames)
        {
            if (pn.Contains("Rate", StringComparison.OrdinalIgnoreCase) ||
                pn.Contains("Power", StringComparison.OrdinalIgnoreCase))
            {
                if (TryToDouble(data.PayloadByName(pn), out var mw) && mw > 0)
                {
                    lock (_lock)
                    {
                        _snapshot.DischargeRateMw = mw;
                        _snapshot.LastUpdateTicks = DateTime.UtcNow.Ticks;
                    }
                }
            }
        }
    }

    private static bool TryToDouble(object? o, out double val)
    {
        val = 0;
        if (o == null) return false;
        try { val = Convert.ToDouble(o); return true; }
        catch { return false; }
    }

    /// <summary>Lấy bản sao snapshot hiện tại (thread-safe).</summary>
    public PowerSnapshot GetSnapshot()
    {
        lock (_lock)
        {
            return new PowerSnapshot
            {
                DischargeRateMw = _snapshot.DischargeRateMw,
                ThrottleEvents  = _snapshot.ThrottleEvents,
                LastUpdateTicks = _snapshot.LastUpdateTicks,
            };
        }
    }

    public void Dispose()
    {
        _running = false;
        try { _session?.Dispose(); } catch { }
        _session = null;
    }
}
