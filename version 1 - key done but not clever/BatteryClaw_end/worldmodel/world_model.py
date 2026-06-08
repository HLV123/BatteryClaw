"""
BatteryClaw — world_model.py  (PHASE 2 — mục 2.2: Learned World Model)

Thay vì simulator viết tay (số ước tính), HỌC luật vật lý của máy từ dữ liệu thật:

    f(state_15, action_7) -> Δstate_15      (dự đoán THAY ĐỔI trạng thái)
    next_state = state + Δstate

Học delta (thay vì next_state trực tiếp) ổn định hơn vì phần lớn state ít đổi
giữa hai bước; mạng chỉ cần học phần "động".

Điều model học được, ví dụ:
  • "khi gpu_switch=0 (tắt dGPU) lúc không game -> discharge_norm giảm bao nhiêu"
  • "khi refresh_mode=0 (60Hz) -> discharge_norm giảm bao nhiêu"

Kỹ thuật: Model-Based RL. World model này dùng cho:
  - Train policy nhanh hơn (rollout trong model thay vì máy thật)
  - Phase 4: Model-Based Planning (MCTS mô phỏng vài bước tới)

Dùng:
  python world_model.py --data ../datacollector/data --epochs 50
  python world_model.py --data ... --eval         # chỉ đánh giá model đã train
"""

import argparse
import os
import glob
import sys

import numpy as np

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "datacollector"))
from schema import STATE_COLUMNS, ACTION_COLUMNS, NEXT_STATE_COLUMNS

STATE_DIM  = len(STATE_COLUMNS)   # 15
ACTION_DIM = len(ACTION_COLUMNS)  # 7


def load_dataset(data_dir):
    """Đọc tất cả parquet/jsonl trong thư mục, trả (S, A, S_next) numpy arrays."""
    import pandas as pd
    files = sorted(glob.glob(os.path.join(data_dir, "*.parquet"))) + \
            sorted(glob.glob(os.path.join(data_dir, "*.jsonl")))
    if not files:
        raise FileNotFoundError(f"Không tìm thấy dữ liệu trong {data_dir}")

    frames = []
    for f in files:
        if f.endswith(".parquet"):
            frames.append(pd.read_parquet(f))
        else:
            frames.append(pd.read_json(f, lines=True))
    df = pd.concat(frames, ignore_index=True)

    # bỏ dòng next_state rỗng (chưa ghép được transition)
    df = df.dropna(subset=NEXT_STATE_COLUMNS)
    # chuẩn hóa workload_id về [0,1] để đồng nhất với input model
    if "workload_id" in df.columns:
        df["workload_id"] = df["workload_id"] / 4.0
    for c in NEXT_STATE_COLUMNS:
        if c == "next_workload_id":
            df[c] = df[c] / 4.0

    S      = df[STATE_COLUMNS].to_numpy(dtype=np.float32)
    A      = df[ACTION_COLUMNS].to_numpy(dtype=np.float32)
    S_next = df[NEXT_STATE_COLUMNS].to_numpy(dtype=np.float32)

    # chuẩn hóa action về thang hợp lý cho NN (gpu_switch 0..2, refresh 0..2)
    A = A.copy()
    A[:, 3] = A[:, 3] / 2.0   # gpu_switch
    A[:, 4] = A[:, 4] / 2.0   # refresh_mode
    return S, A, S_next


def build_model():
    import torch
    import torch.nn as nn

    class WorldModel(nn.Module):
        """MLP nhỏ: (state, action) -> Δstate. Đủ nhẹ để chạy trên laptop."""
        def __init__(self, state_dim=STATE_DIM, action_dim=ACTION_DIM, hidden=128):
            super().__init__()
            self.net = nn.Sequential(
                nn.Linear(state_dim + action_dim, hidden), nn.ReLU(),
                nn.Linear(hidden, hidden), nn.ReLU(),
                nn.Linear(hidden, state_dim),       # đầu ra = Δstate
            )

        def forward(self, state, action):
            x = torch.cat([state, action], dim=-1)
            delta = self.net(x)
            return state + delta            # next_state = state + Δ

    return WorldModel()


def train(data_dir, epochs=50, lr=1e-3, batch=256, out="models/world_model.pt",
          val_frac=0.15, seed=0):
    import torch
    import torch.nn as nn

    torch.manual_seed(seed)
    np.random.seed(seed)

    S, A, Snext = load_dataset(data_dir)
    n = len(S)
    print(f"[1] Dataset: {n} transitions từ {data_dir}")
    if n < 50:
        print("    ⚠️ Quá ít dữ liệu — kết quả chỉ mang tính kiểm tra pipeline.")

    # chia train/val
    idx = np.random.permutation(n)
    nval = max(1, int(n * val_frac))
    val_idx, tr_idx = idx[:nval], idx[nval:]

    to_t = lambda a: torch.tensor(a, dtype=torch.float32)
    S_tr, A_tr, Y_tr = to_t(S[tr_idx]), to_t(A[tr_idx]), to_t(Snext[tr_idx])
    S_va, A_va, Y_va = to_t(S[val_idx]), to_t(A[val_idx]), to_t(Snext[val_idx])

    model = build_model()
    opt = torch.optim.Adam(model.parameters(), lr=lr)
    loss_fn = nn.MSELoss()

    print(f"[2] Train {epochs} epoch (train={len(tr_idx)}, val={len(val_idx)})")
    ntr = len(S_tr)
    for ep in range(1, epochs + 1):
        model.train()
        perm = torch.randperm(ntr)
        tot = 0.0
        for i in range(0, ntr, batch):
            b = perm[i:i+batch]
            pred = model(S_tr[b], A_tr[b])
            loss = loss_fn(pred, Y_tr[b])
            opt.zero_grad(); loss.backward(); opt.step()
            tot += loss.item() * len(b)
        if ep % max(1, epochs // 10) == 0 or ep == 1:
            model.eval()
            with torch.no_grad():
                vloss = loss_fn(model(S_va, A_va), Y_va).item()
            print(f"    ep {ep:3d} | train_mse={tot/ntr:.5f} | val_mse={vloss:.5f}")

    # đánh giá riêng chiều discharge (chiều quan trọng nhất, index 9)
    model.eval()
    with torch.no_grad():
        pred = model(S_va, A_va).numpy()
    disch_mae = float(np.mean(np.abs(pred[:, 9] - Snext[val_idx][:, 9])))
    print(f"[3] MAE discharge_norm (val): {disch_mae:.5f} "
          f"(~{disch_mae*80000:.0f} mW)")

    os.makedirs(os.path.dirname(out), exist_ok=True)
    torch.save(model.state_dict(), out)
    print(f"[4] Đã lưu world model: {out}")

    # export ONNX để engine/planning dùng (Phase 4)
    try:
        onnx_path = out.replace(".pt", ".onnx")
        dummy_s = torch.zeros(1, STATE_DIM)
        dummy_a = torch.zeros(1, ACTION_DIM)
        torch.onnx.export(
            model, (dummy_s, dummy_a), onnx_path,
            input_names=["state", "action"], output_names=["next_state"],
            dynamic_axes={"state": {0: "batch"}, "action": {0: "batch"},
                          "next_state": {0: "batch"}},
            opset_version=17)
        print(f"[5] Export ONNX: {onnx_path}  (state15, action7) -> next_state15")
    except Exception as e:
        print(f"[5] ONNX export bỏ qua: {e}")

    return model


def evaluate(data_dir, model_path="models/world_model.pt"):
    import torch
    import torch.nn as nn
    S, A, Snext = load_dataset(data_dir)
    model = build_model()
    model.load_state_dict(torch.load(model_path))
    model.eval()
    with torch.no_grad():
        pred = model(torch.tensor(S), torch.tensor(A)).numpy()
    mse = float(np.mean((pred - Snext) ** 2))
    # so với baseline ngây thơ "next = current" (không đổi)
    naive = float(np.mean((S - Snext) ** 2))
    print(f"World model MSE  : {mse:.5f}")
    print(f"Naive (giữ nguyên): {naive:.5f}")
    print(f"-> Model {'TỐT HƠN' if mse < naive else 'CHƯA TỐT HƠN'} baseline ngây thơ")


def main():
    ap = argparse.ArgumentParser(description="BatteryClaw Phase 2 — Learned World Model")
    ap.add_argument("--data", default="../datacollector/data", help="thư mục dữ liệu")
    ap.add_argument("--epochs", type=int, default=50)
    ap.add_argument("--lr", type=float, default=1e-3)
    ap.add_argument("--batch", type=int, default=256)
    ap.add_argument("--out", default="models/world_model.pt")
    ap.add_argument("--eval", action="store_true", help="chỉ đánh giá model có sẵn")
    args = ap.parse_args()

    if args.eval:
        evaluate(args.data, args.out)
    else:
        train(args.data, args.epochs, args.lr, args.batch, args.out)


if __name__ == "__main__":
    main()
