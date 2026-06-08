// BatteryClaw — Ml/WinMlPolicy.cs  (PHASE 5 — mục 5.2)
//
// Chạy ONNX policy trực tiếp với tăng tốc GPU qua DirectML — KHÔNG cần CUDA.
// Dùng Microsoft.ML.OnnxRuntime + DirectML execution provider (ổn định, tương
// thích mọi GPU hỗ trợ DX12: Intel UHD, RTX 3050...).
//
// Giữ ĐÚNG contract của các phase trước:  observation (1,15) float32 -> action (1,7) float32.
// Inference nhanh hơn CPU ~3-5x, lại không phụ thuộc Python ở máy người dùng.
//
// Nếu DirectML không khả dụng (driver cũ), tự fallback về CPU EP.

using Microsoft.ML.OnnxRuntime;
using Microsoft.ML.OnnxRuntime.Tensors;

namespace BatteryClaw.Engine.Ml;

public sealed class WinMlPolicy : IDisposable
{
    public const int ObsDim    = 15;   // khớp Phase 1..4
    public const int ActionDim = 7;

    private readonly InferenceSession _session;
    private readonly string _inputName;
    private readonly string _outputName;
    public bool UsingDirectML { get; }

    public WinMlPolicy(string onnxPath)
    {
        var options = new SessionOptions();
        try
        {
            // Thử DirectML trước (GPU). deviceId 0 = GPU mặc định.
            options.AppendExecutionProvider_DML(0);
            UsingDirectML = true;
        }
        catch
        {
            // Driver/GPU không hỗ trợ -> CPU.
            options = new SessionOptions();
            UsingDirectML = false;
        }

        _session = new InferenceSession(onnxPath, options);
        _inputName  = _session.InputMetadata.Keys.First();
        _outputName = _session.OutputMetadata.Keys.First();
    }

    /// <summary>obs dài 15 -> action dài 7 (tanh-squashed [-1,1]).</summary>
    public float[] Predict(float[] obs)
    {
        if (obs.Length != ObsDim)
            throw new ArgumentException($"obs must be {ObsDim} dims, got {obs.Length}");

        var tensor = new DenseTensor<float>(obs, new[] { 1, ObsDim });
        var inputs = new List<NamedOnnxValue>
        {
            NamedOnnxValue.CreateFromTensor(_inputName, tensor)
        };

        using var results = _session.Run(inputs);
        var output = results.First(r => r.Name == _outputName)
                            .AsTensor<float>().ToArray();
        // output có shape (1,7) -> phẳng thành 7
        return output.Length >= ActionDim ? output[..ActionDim] : output;
    }

    public void Dispose() => _session.Dispose();
}
