// BatteryClaw — Tasks/TaskSchedulerReader.cs  (PHASE 5 — mục 5.4)
//
// Đọc Windows Task Scheduler để agent BIẾT TRƯỚC việc sắp xảy ra, ví dụ:
//   • "Windows Update sẽ chạy lúc 3h sáng"  -> sạc đầy trước, hoặc delay tới khi cắm điện
//   • "Antivirus scan lúc 12h trưa"          -> chuẩn bị CPU
//
// Dùng thư viện TaskScheduler (Microsoft.Win32.TaskScheduler) — wrapper sạch
// quanh COM API của Windows. Chỉ ĐỌC, không sửa task của hệ thống.
//
// Trả danh sách task sắp chạy trong N giờ tới, để Program.cs đưa vào quyết định.

using Microsoft.Win32.TaskScheduler;

namespace BatteryClaw.Engine.Tasks;

public sealed record UpcomingTask(
    string Name,
    DateTime NextRun,
    bool LikelyHeavy   // có vẻ nặng (update/scan/backup) -> đáng lên kế hoạch
);

public static class TaskSchedulerReader
{
    // Từ khóa gợi ý task nặng pin/CPU.
    private static readonly string[] HeavyHints =
    {
        "update", "windowsupdate", "defender", "scan", "backup",
        "telemetry", "compatappraiser", "diskcleanup", "defrag",
    };

    /// <summary>Liệt kê task sẽ chạy trong <paramref name="withinHours"/> giờ tới.</summary>
    public static List<UpcomingTask> GetUpcoming(double withinHours = 12)
    {
        var result = new List<UpcomingTask>();
        var now = DateTime.Now;
        var horizon = now.AddHours(withinHours);

        try
        {
            using var ts = new TaskService();
            CollectFromFolder(ts.RootFolder, now, horizon, result);
        }
        catch
        {
            // Không đọc được (quyền/COM) -> trả rỗng, engine vẫn chạy bình thường.
        }

        result.Sort((a, b) => a.NextRun.CompareTo(b.NextRun));
        return result;
    }

    private static void CollectFromFolder(TaskFolder folder, DateTime now,
        DateTime horizon, List<UpcomingTask> outList)
    {
        foreach (var task in folder.Tasks)
        {
            try
            {
                if (task.State == TaskState.Disabled) continue;
                var next = task.NextRunTime;
                if (next > now && next <= horizon)
                {
                    bool heavy = IsHeavy(task.Name) || IsHeavy(task.Path);
                    outList.Add(new UpcomingTask(task.Name, next, heavy));
                }
            }
            catch { /* một số task ném lỗi khi đọc NextRunTime */ }
        }

        foreach (var sub in folder.SubFolders)
            CollectFromFolder(sub, now, horizon, outList);
    }

    private static bool IsHeavy(string s)
    {
        s = (s ?? string.Empty).ToLowerInvariant();
        return HeavyHints.Any(h => s.Contains(h));
    }

    /// <summary>Gợi ý cho engine: có task nặng nào sắp chạy trong N giờ không?</summary>
    public static (bool heavySoon, UpcomingTask? task) NextHeavyTask(double withinHours = 6)
    {
        var t = GetUpcoming(withinHours).FirstOrDefault(x => x.LikelyHeavy);
        return (t != null, t);
    }
}
