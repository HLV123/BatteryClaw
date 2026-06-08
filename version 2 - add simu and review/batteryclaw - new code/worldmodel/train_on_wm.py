"""
BatteryClaw — train_on_wm.py  (PHASE 2)

Train policy PPO trên WorldModelEnv (động học học từ data thật + reward thật),
rồi export ONNX (1,15)->(1,7) đúng contract mà rl_brain.py dùng để deploy.

So với simulator/train.py (Phase 1, simulator viết tay), điểm khác:
  • Môi trường là world model học được từ dữ liệu máy thật (Phase 2 mục 2.2)
  • Reward là công thức thật α/β/γ/δ (Phase 2 mục 2.3)

Dùng:
  python train_on_wm.py --steps 200000 --wm models/world_model.pt
"""

import argparse
import os
import sys

import numpy as np
import torch
import torch.nn as nn

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from wm_env import WorldModelEnv, STATE_DIM, ACTION_DIM

sys.path.insert(0, os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "datacollector"))
from reward import RewardWeights


def main():
    ap = argparse.ArgumentParser(description="Train policy trên world model")
    ap.add_argument("--wm",    default="models/world_model.pt")
    ap.add_argument("--steps", type=int, default=200000)
    ap.add_argument("--out",   default="models/policy_wm.onnx")
    ap.add_argument("--alpha", type=float, default=1.0)
    ap.add_argument("--beta",  type=float, default=2.0)
    ap.add_argument("--gamma", type=float, default=0.5)
    ap.add_argument("--delta", type=float, default=0.5)
    args = ap.parse_args()

    if not os.path.exists(args.wm):
        print(f"Chưa có world model {args.wm}. Hãy chạy world_model.py trước.")
        return

    from stable_baselines3 import PPO
    from stable_baselines3.common.vec_env import DummyVecEnv

    weights = RewardWeights(args.alpha, args.beta, args.gamma, args.delta)
    make = lambda: WorldModelEnv(model_path=args.wm, weights=weights)
    venv = DummyVecEnv([make, make])

    print(f"[1] Train PPO {args.steps} steps trên WorldModelEnv "
          f"(α={args.alpha} β={args.beta} γ={args.gamma} δ={args.delta})")
    model = PPO("MlpPolicy", venv, verbose=0,
                policy_kwargs=dict(net_arch=[128, 128]),
                batch_size=256, n_steps=512)
    model.learn(total_timesteps=args.steps)
    print("[2] Train xong.")

    # ── export ONNX khớp rl_brain (1,15)->(1,7) ─────────────────
    class PolicyWrapper(nn.Module):
        def __init__(self, policy):
            super().__init__()
            self.policy = policy
        def forward(self, obs):
            # trả mean action (deterministic) — tanh-squashed như Phase 1
            features = self.policy.extract_features(obs)
            latent_pi = self.policy.mlp_extractor.forward_actor(features)
            mean = self.policy.action_net(latent_pi)
            return torch.tanh(mean)

    wrapper = PolicyWrapper(model.policy).eval()
    dummy = torch.zeros(1, STATE_DIM)
    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    torch.onnx.export(
        wrapper, dummy, args.out,
        input_names=["observation"], output_names=["action"],
        dynamic_axes={"observation": {0: "batch"}, "action": {0: "batch"}},
        opset_version=17)
    print(f"[3] Export ONNX policy: {args.out}  (batch,15)->(batch,7)")
    print("    -> deploy bằng: python ../brain/rl_brain.py --model "
          f"{os.path.abspath(args.out)}")


if __name__ == "__main__":
    main()
