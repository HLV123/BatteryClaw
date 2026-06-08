"""
BatteryClaw — simulator/export_lstm_onnx.py  (Tầng 2.1 — giải bài toán LSTM + ONNX)

VẤN ĐỀ: ONNX/WinML deploy hiện nạp model (batch,15)->(batch,7) KHÔNG trạng thái,
trong khi LSTM cần chuỗi/hidden state -> trước đây LSTM không deploy được.

GIẢI PHÁP (cách khả thi nhất): export LSTM dạng NHẬN CẢ CHUỖI:
    input  (batch, 30, 15)   <- 30 state gần nhất (rl_brain giữ rolling window)
    output (batch, 7)
Không cần truyền hidden state qua ONNX (vốn rắc rối) -> ONNX vẫn "không trạng thái"
theo nghĩa mỗi lần gọi là độc lập, nhưng model VẪN thấy lịch sử 30 bước.

rl_brain dùng SequenceBuffer (đã có trong lstm_policy) để gom 30 state rồi feed.

LƯU Ý: script này export KIẾN TRÚC LSTM (trọng số ngẫu nhiên nếu chưa train, hoặc
nạp checkpoint nếu có). Để LSTM giỏi cần TRAIN thật (behavior cloning từ PPO/SAC hoặc
RL) — đó là bước riêng tốn tài nguyên. Ở đây ta bảo đảm ĐƯỜNG DEPLOY LSTM hoạt động.

Dùng:
    python simulator\\export_lstm_onnx.py                 # export kiến trúc (chưa train)
    python simulator\\export_lstm_onnx.py --ckpt lstm.pt  # export từ checkpoint đã train
"""

import os
import sys
import argparse

import torch

_SIM_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT    = os.path.dirname(_SIM_DIR)
MODELS_DIR = os.path.join(_SIM_DIR, "models")
os.makedirs(MODELS_DIR, exist_ok=True)
sys.path.insert(0, os.path.join(_ROOT, "advanced", "memory"))

from lstm_policy import LSTMPolicy, SEQ_LEN


def export(ckpt=None, out=None):
    out = out or os.path.join(MODELS_DIR, "batteryclaw_policy_lstm.onnx")
    pol = LSTMPolicy(state_dim=15, action_dim=7)
    if ckpt and os.path.exists(ckpt):
        pol.load_state_dict(torch.load(ckpt, map_location="cpu"))
        print(f"[ckpt] Nap trong so da train: {ckpt}")
    else:
        print("[ckpt] Khong co checkpoint -> export kien truc (trong so ngau nhien).")
    pol.eval()

    # Wrapper chỉ trả action (bỏ hidden_state) để ONNX gọn (batch,30,15)->(batch,7)
    class SeqOnly(torch.nn.Module):
        def __init__(self, p): super().__init__(); self.p = p
        def forward(self, seq):
            a, _ = self.p(seq)
            return a

    m = SeqOnly(pol).eval()
    dummy = torch.zeros(1, SEQ_LEN, 15)
    torch.onnx.export(
        m, dummy, out,
        input_names=["observation_seq"], output_names=["action"],
        dynamic_axes={"observation_seq": {0: "batch"}, "action": {0: "batch"}},
        opset_version=17,
    )
    print(f"[ONNX] LSTM export: {out}")
    print(f"    Input (batch,{SEQ_LEN},15) -> Output (batch,7) tanh [-1,1]")
    return out


def verify(path):
    import onnxruntime as ort
    import numpy as np
    s = ort.InferenceSession(path)
    inp = s.get_inputs()[0]
    out = s.get_outputs()[0]
    print(f"[verify] input {inp.name} {inp.shape} | output {out.name} {out.shape}")
    r = s.run(None, {inp.name: np.zeros((1, SEQ_LEN, 15), dtype=np.float32)})
    assert r[0].shape == (1, 7), f"shape sai: {r[0].shape}"
    print(f"[verify] infer OK shape {r[0].shape} "
          f"range {float(r[0].min()):.3f}..{float(r[0].max()):.3f}")
    print("[verify] LSTM ONNX deploy duoc (dang chuoi) ✓")


if __name__ == "__main__":
    p = argparse.ArgumentParser()
    p.add_argument("--ckpt", type=str, default=None)
    p.add_argument("--out", type=str, default=None)
    args = p.parse_args()
    path = export(ckpt=args.ckpt, out=args.out)
    verify(path)
