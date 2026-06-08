// BatteryClaw — Battery/BatteryReport.cs  (PHASE 5 — mục 5.5)
//
// Windows có sẵn:  powercfg /batteryreport /xml /output report.xml
// File XML chứa: DesignCapacity, FullChargeCapacity, và lịch sử capacity theo
// thời gian. Từ đó:
//   • Tính health chính xác = FullCharge / Design
//   • Học đường cong xuống cấp (degradation curve) của CHÍNH máy này
//   • Dự đoán: "nếu dùng thêm 1 năm, pin còn ~Y%"
//   • Cảnh báo khi pin xuống dưới ngưỡng nguy hiểm
//
// Logic parse/ước lượng thuần (không phụ thuộc Windows ngoài việc gọi powercfg),
// nên thuật toán đã được kiểm chứng song song bằng script Python (xem
// engine_dotnet/Battery/test_degradation.py).

using System.Diagnostics;
using System.Xml.Linq;

namespace BatteryClaw.Engine.Battery;

public sealed record BatteryHealth(
    int DesignCapacityMwh,
    int FullChargeCapacityMwh,
    double HealthPct,                 // FullCharge/Design * 100
    double EstimatedHealthIn1YearPct, // dự đoán sau 1 năm
    bool   Warning,                   // dưới ngưỡng nguy hiểm?
    string Message
);

public static class BatteryReport
{
    private const double WarningThresholdPct = 50.0;  // dưới 50% sức khỏe -> cảnh báo

    /// <summary>Sinh battery report XML bằng powercfg, trả đường dẫn file.</summary>
    public static string Generate(string outDir)
    {
        Directory.CreateDirectory(outDir);
        var path = Path.Combine(outDir, "batteryreport.xml");
        var psi = new ProcessStartInfo("powercfg",
            $"/batteryreport /xml /output \"{path}\"")
        {
            CreateNoWindow = true,
            UseShellExecute = false,
            RedirectStandardOutput = true,
        };
        using var p = Process.Start(psi);
        p?.WaitForExit(10000);
        return path;
    }

    /// <summary>Phân tích file XML -> BatteryHealth.</summary>
    public static BatteryHealth Analyze(string xmlPath)
    {
        var doc = XDocument.Load(xmlPath);
        XNamespace ns = doc.Root?.GetDefaultNamespace() ?? "";

        int design = ReadFirstInt(doc, ns, "DesignCapacity");
        int full   = ReadFirstInt(doc, ns, "FullChargeCapacity");

        // Lịch sử để ước lượng tốc độ xuống cấp.
        var history = ReadCapacityHistory(doc, ns);
        return BuildHealth(design, full, history);
    }

    // Tách logic thuần để test được độc lập (xem test_degradation.py).
    public static BatteryHealth BuildHealth(
        int design, int full, List<(DateTime date, int fullCap)> history)
    {
        double healthPct = design > 0 ? (double)full / design * 100.0 : 0;

        // Ước lượng tuyến tính tốc độ mất dung lượng theo thời gian từ history.
        double pctPerYear = EstimateDegradationPctPerYear(design, history);
        double in1Year = Math.Max(0, healthPct - pctPerYear);

        bool warn = healthPct < WarningThresholdPct;
        string msg = warn
            ? $"Battery health only {healthPct:F0}% - consider replacing the battery."
            : $"Battery health {healthPct:F0}%. Estimated ~{in1Year:F0}% after 1 year.";

        return new BatteryHealth(design, full, Math.Round(healthPct, 1),
            Math.Round(in1Year, 1), warn, msg);
    }

    /// <summary>Tốc độ giảm sức khỏe (%/năm) từ lịch sử FullChargeCapacity.</summary>
    public static double EstimateDegradationPctPerYear(
        int design, List<(DateTime date, int fullCap)> history)
    {
        if (design <= 0 || history.Count < 2) return 0;

        history.Sort((a, b) => a.date.CompareTo(b.date));
        var first = history[0];
        var last  = history[^1];

        double days = (last.date - first.date).TotalDays;
        if (days < 1) return 0;

        double firstPct = (double)first.fullCap / design * 100.0;
        double lastPct  = (double)last.fullCap  / design * 100.0;
        double dropPct  = firstPct - lastPct;          // giảm bao nhiêu %
        return dropPct / days * 365.0;                  // quy ra mỗi năm
    }

    // ── helpers đọc XML ───────────────────────────────────────────────────────
    private static int ReadFirstInt(XDocument doc, XNamespace ns, string local)
    {
        foreach (var el in doc.Descendants())
        {
            var attr = el.Attribute(local) ?? el.Attribute(ns + local);
            if (attr != null && int.TryParse(StripUnits(attr.Value), out var v))
                return v;
            if (el.Name.LocalName == local && int.TryParse(StripUnits(el.Value), out var v2))
                return v2;
        }
        return 0;
    }

    private static List<(DateTime, int)> ReadCapacityHistory(XDocument doc, XNamespace ns)
    {
        var list = new List<(DateTime, int)>();
        foreach (var el in doc.Descendants())
        {
            if (!el.Name.LocalName.Contains("HistoryEntry", StringComparison.OrdinalIgnoreCase))
                continue;
            var fullAttr = el.Attribute("FullChargeCapacity");
            var dateAttr = el.Attribute("StartDate") ?? el.Attribute("Date");
            if (fullAttr != null && dateAttr != null &&
                int.TryParse(StripUnits(fullAttr.Value), out var cap) &&
                DateTime.TryParse(dateAttr.Value, out var dt))
            {
                list.Add((dt, cap));
            }
        }
        return list;
    }

    private static string StripUnits(string s) =>
        new string(s.Where(c => char.IsDigit(c)).ToArray());
}
