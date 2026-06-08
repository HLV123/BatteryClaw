// BatteryClaw — Program.cs  (PHASE 5 — ghép + IPC)
//
// Engine C#/.NET đời mới: ghép 5 mảnh Phase 5 và GIỮ TƯƠNG THÍCH với rl_brain
// (cùng Named Pipe \\.\pipe\BatteryClaw, cùng JSON state/action).
//
//   ETW (5.1)        -> discharge realtime, đắp vào state
//   WinML (5.2)      -> có thể tự inference policy ONNX (không cần Python)
//   Throttle (5.3)   -> thực thi action throttle per-process
//   Tasks (5.4)      -> đắp "task nặng sắp chạy" vào quyết định
//   Battery (5.5)    -> health + cảnh báo
//
// Có 2 chế độ chạy:
//   --serve     : làm IPC server cho rl_brain Python (như engine C++ cũ)
//   --standalone: tự đọc state + tự inference WinML + tự thực thi (không cần Python)
//
// File này cố tình mỏng — mỗi tính năng đã nằm ở module riêng.

using System.IO.Pipes;
using System.Text;
using System.Text.Json;
using BatteryClaw.Engine.Etw;
using BatteryClaw.Engine.Ml;
using BatteryClaw.Engine.Throttle;
using BatteryClaw.Engine.Tasks;
using BatteryClaw.Engine.Battery;
using BatteryClaw.Engine.Control;
namespace BatteryClaw.Engine;

public static class Program
{
    private const string PipeName = "BatteryClaw";   // \\.\pipe\BatteryClaw

    // [FIND-01] Hang so chuan hoa discharge. PHAI KHOP voi commons/constants.py
    //  DISCHARGE_MAX_MW (Python). C# khong import duoc tu Python nen giu ban sao
    //  o day; neu doi ben Python thi doi ca o day de obs scale dong nhat.
    private const float DischargeMaxMw = 80000f;
    // [REMAIN-02] khop commons/constants.py GPU_POWER_MAX_MW
    private const float GpuPowerMaxMw = 38000f;

    public static async Task<int> Main(string[] args)
    {
        bool standalone = args.Contains("--standalone");
        string? modelPath = GetArg(args, "--model");

        Console.WriteLine("BatteryClaw .NET Engine (Phase 5)");
        Console.WriteLine(standalone ? "Mode: standalone (WinML self-inference)"
                                     : "Mode: serve (IPC cho rl_brain)");

        // 5.1 — ETW power monitor (cần Admin; thất bại thì vẫn chạy, dùng WMI)
        using var etw = new EtwPowerMonitor();
        bool etwOk = etw.Start();
        Console.WriteLine($"ETW power monitor: {(etwOk ? "ON" : "off (needs Admin)")}");

        // 5.5 — battery health (in cảnh báo lúc khởi động)
        TryPrintBatteryHealth();

        // 5.4 — task nặng sắp chạy
        var (heavySoon, heavyTask) = TaskSchedulerReader.NextHeavyTask(6);
        if (heavySoon && heavyTask != null)
            Console.WriteLine($"Note: '{heavyTask.Name}' will run at {heavyTask.NextRun:HH:mm} " +
                              "-> consider charging first or deferring until plugged in.");

        if (standalone)
        {
            if (modelPath == null || !File.Exists(modelPath))
            {
                Console.WriteLine("Standalone needs --model <onnx>. Exiting.");
                return 1;
            }
            await RunStandalone(etw, modelPath);
        }
        else
        {
            await RunServer(etw);
        }
        return 0;
    }

    // ── Chế độ serve: IPC cho rl_brain (giữ giao thức cũ) ────────────────────
    private static async Task RunServer(EtwPowerMonitor etw)
    {
        Console.WriteLine($"Pipe \\\\.\\pipe\\{PipeName} open, waiting for rl_brain...");
        while (true)
        {
            using var server = new NamedPipeServerStream(
                PipeName, PipeDirection.InOut, 1,
                PipeTransmissionMode.Byte, PipeOptions.Asynchronous);
            await server.WaitForConnectionAsync();
            Console.WriteLine("rl_brain connected.");

            try
            {
                using var reader = new StreamReader(server, Encoding.UTF8, false, 1024, true);
                using var writer = new StreamWriter(server, new UTF8Encoding(false)) { AutoFlush = true };

                // Vòng: gửi state (đắp ETW) định kỳ, đọc action -> thực thi.
                var sendTask = SendStatesLoop(writer, etw, server);
                string? line;
                while ((line = await reader.ReadLineAsync()) != null)
                {
                    HandleActionJson(line);
                }
                await sendTask;
            }
            catch (IOException) { Console.WriteLine("rl_brain disconnected."); }
        }
    }

    private static async Task SendStatesLoop(StreamWriter writer,
        EtwPowerMonitor etw, NamedPipeServerStream server)
    {
        // [FIX] Thu thap state THAT bang WMI/Win32. Bao try/catch TOAN BO de mot
        //  loi WMI/PerformanceCounter le te KHONG lam chet ca vong (truoc day lam
        //  pipe dong/mo lap lien tuc).
        State.SystemStateCollector? collector = null;
        try { collector = new State.SystemStateCollector(); }
        catch (Exception e)
        {
            Console.WriteLine($"[warn] Could not init collector: {e.Message}");
        }

        while (server.IsConnected)
        {
            Dictionary<string, object> state;
            try
            {
                var snap = etw.GetSnapshot();
                state = collector != null
                    ? collector.Collect(snap.DischargeRateMw)
                    : new Dictionary<string, object>
                      { ["type"] = "state", ["discharge_mw"] = snap.DischargeRateMw };
            }
            catch (Exception e)
            {
                Console.WriteLine($"[warn] State collection error: {e.Message}");
                state = new Dictionary<string, object> { ["type"] = "state" };
            }

            try { await writer.WriteLineAsync(JsonSerializer.Serialize(state)); }
            catch (IOException) { break; }
            await Task.Delay(1000);
        }
        collector?.Dispose();
    }

    // ── Chế độ standalone: tự inference + thực thi (không cần Python) ─────────
    private static async Task RunStandalone(EtwPowerMonitor etw, string modelPath)
    {
        using var policy = new WinMlPolicy(modelPath);
        using var collector = new State.SystemStateCollector();
        Console.WriteLine($"WinML: {(policy.UsingDirectML ? "DirectML (GPU)" : "CPU")}");

        while (true)
        {
            // Thu thap state that -> dung obs 15 chieu (khop rl_brain.state_to_obs).
            var snap  = etw.GetSnapshot();
            var st    = collector.Collect(snap.DischargeRateMw);
            var obs   = StateToObs(st);

            float[] action = policy.Predict(obs);
            if (action[0] < 0)
                ProcessThrottler.ThrottleBackgroundByName(
                    new[] { "OneDrive", "Dropbox", "GoogleDriveFS" }, enable: true);

            await Task.Delay(1000);
        }
    }

    // Dung obs 15 chieu tu state dict — khop thu tu rl_brain.state_to_obs.
    private static float[] StateToObs(Dictionary<string, object> s)
    {
        float F(string k, float def = 0) =>
            s.TryGetValue(k, out var v) ? Convert.ToSingle(v) : def;

        float battPct = F("batt_pct", 50) / 100f;
        float cpu     = F("cpu_load", 0) / 100f;
        float tempC   = F("temp_c", 45);
        float tempN   = Math.Clamp((tempC - 30f) / 70f, 0f, 1f);
        float bright  = F("brightness", 80) / 100f;
        float throttle= F("cpu_max", 100) / 100f;
        float gpuType = (int)F("gpu_type", 0) switch { 0 => 0f, 1 => 0.5f, _ => 1f };
        float gpuPow  = Math.Clamp(F("gpu_power_mw", 0) / GpuPowerMaxMw, 0f, 1f);
        float disch   = Math.Clamp(F("discharge_mw", 0) / DischargeMaxMw, 0f, 1f);
        float refresh = Math.Clamp((F("refresh_hz", 60) - 60f) / (165f - 60f), 0f, 1f);
        float ram     = F("ram_pct", 50) / 100f;
        float tod     = F("tod", 0.5f);

        // workload tu CPU (giong rl_brain CPU-only cho obs)
        float cpl = F("cpu_load", 30);
        int wl = cpl < 10 ? 0 : cpl < 30 ? 1 : cpl < 55 ? 2 : cpl < 80 ? 3 : 4;

        return new float[]
        {
            battPct, cpu, tempN, wl / 4f, bright,
            throttle, tod, gpuType, gpuPow, disch,
            refresh, F("wifi", 1) > 0 ? 1f : 0f, F("audio", 0) > 0 ? 1f : 0f,
            ram, tod,
        };
    }

    // ── Thực thi action JSON từ rl_brain ──────────────────────────────────────
    private static void HandleActionJson(string json)
    {
        try
        {
            using var doc = JsonDocument.Parse(json);
            var root = doc.RootElement;
            if (root.TryGetProperty("type", out var t) && t.GetString() != "action")
                return;

            int F(string k, int def) =>
                root.TryGetProperty(k, out var v) && v.ValueKind == JsonValueKind.Number
                    ? v.GetInt32() : def;

            // 5.3: defer -> throttle process nền (EcoQoS)
            if (root.TryGetProperty("defer", out var defer) &&
                defer.ValueKind == JsonValueKind.True)
            {
                int n = ProcessThrottler.ThrottleBackgroundByName(
                    new[] { "OneDrive", "Dropbox", "GoogleDriveFS", "Teams", "Slack" },
                    enable: true);
                Console.WriteLine($"[5.3] throttled {n} background process(es) (EcoQoS).");
            }

            // BRIGHTNESS: AI gui 30..100 (%)
            int br = F("brightness", -1);
            if (br >= 0)
            {
                bool ok = HardwareControl.SetBrightness(br);
                Console.WriteLine($"[HW] brightness -> {br}% : {(ok ? "OK" : "skip/loi")}");
            }

            // CPU MAX (throttle): AI gui 20..100 (%)
            int cpu = F("cpu_max", -1);
            if (cpu >= 0)
            {
                bool ok = HardwareControl.SetCpuMax(cpu);
                Console.WriteLine($"[HW] cpu_max -> {cpu}% : {(ok ? "OK" : "skip/loi")}");
            }

            // REFRESH: AI gui Hz (60/120/144)
            int hz = F("refresh_hz", -1);
            if (hz >= 60)
            {
                bool ok = HardwareControl.SetRefreshHz(hz);
                Console.WriteLine($"[HW] refresh -> {hz}Hz : {(ok ? "OK" : "skip/khong ho tro")}");
            }

            // WIFI power save: 1 = tiet kiem
            if (root.TryGetProperty("wifi_save", out var ws))
            {
                bool save = ws.ValueKind == JsonValueKind.True ||
                            (ws.ValueKind == JsonValueKind.Number && ws.GetInt32() == 1);
                HardwareControl.SetWifiPowerSave(save);
            }

            // GPU preference per-app (0=iGPU tiet kiem, 1=dGPU): dat cho app foreground
            int gpu = F("gpu_switch", 2);   // 2 = giu nguyen, khong dat
            if (gpu == 0 || gpu == 1)
            {
                string appPath = root.TryGetProperty("fg_app_path", out var ap)
                    ? ap.GetString() : "";
                if (!string.IsNullOrEmpty(appPath))
                {
                    bool ok = HardwareControl.SetAppGpuPreference(appPath, powerSaving: gpu == 0);
                    if (ok)
                        Console.WriteLine($"[HW] gpu pref -> {(gpu==0?"iGPU":"dGPU")} for "
                                          + System.IO.Path.GetFileName(appPath));
                }
            }
        }
        catch (JsonException) { /* JSON lỗi -> bỏ qua */ }
    }

    private static void TryPrintBatteryHealth()
    {
        try
        {
            var xml = BatteryReport.Generate(Path.GetTempPath());
            var h = BatteryReport.Analyze(xml);
            Console.WriteLine($"[5.5] {h.Message}");
        }
        catch { /* powercfg có thể cần quyền; bỏ qua nếu lỗi */ }
    }

    private static string? GetArg(string[] args, string name)
    {
        int i = Array.IndexOf(args, name);
        return (i >= 0 && i + 1 < args.Length) ? args[i + 1] : null;
    }
}
