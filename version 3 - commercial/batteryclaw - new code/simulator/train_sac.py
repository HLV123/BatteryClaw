"""
BatteryClaw — simulator/train_sac.py  (Tầng 2.2)

Train SAC (Soft Actor-Critic) TRÊN SIMULATOR như một lựa chọn thay PPO.
SAC off-policy: thu thập transition từ env vào replay buffer rồi học từ buffer.
Export actor (deterministic, tanh [-1,1]) sang ONNX (15->7) — KHỚP rl_brain y hệt PPO.

Dùng:
   python simulator\\train_sac.py --steps 300000
   python simulator\\train_sac.py --steps 300000 --profile battery_saver

So với PPO: SAC tối ưu entropy (explore tốt hơn), off-policy (dùng lại data) — có
thể ổn định hơn trên môi trường nhiễu. Đây là lựa chọn; PPO vẫn là mặc định.
"""

import os
import sys
import argparse
import time

import numpy as np

_SIM_DIR = os.path.dirname(os.path.abspath(__file__))
_ROOT    = os.path.dirname(_SIM_DIR)
MODELS_DIR = os.path.join(_SIM_DIR, "models")
os.makedirs(MODELS_DIR, exist_ok=True)

sys.path.insert(0, _SIM_DIR)
sys.path.insert(0, os.path.join(_ROOT, "advanced", "sac"))
sys.path.insert(0, os.path.join(_ROOT, "online", "buffer"))

from battery_env import BatteryClawEnv
from sac_trainer import SAC
from replay_buffer import ReplayBuffer


def collect_and_train(total_steps=300_000, profile=None,
                      warmup=5000, train_every=1, train_iters=1):
    print("BatteryClaw — Train SAC Agent")
    if profile:
        print(f"   >>> Profile co dinh: {profile}")
    print("=" * 50)

    # SAC off-policy: 1 env thu thap (curriculum bằng difficulty tăng dần theo tiến độ)
    import torch
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"   Device: {dev}")
    env = BatteryClawEnv(difficulty=2, force_profile=profile)
    buf = ReplayBuffer(capacity=100_000)
    sac = SAC(state_dim=15, action_dim=7, device=dev)

    obs, _ = env.reset()
    t0 = time.time()
    last_info = {}
    ep_reward, ep_rewards = 0.0, []

    for step in range(1, total_steps + 1):
        # curriculum đơn giản: nửa đầu difficulty 2, nửa sau difficulty 3
        if step == total_steps // 2:
            env = BatteryClawEnv(difficulty=3, force_profile=profile)
            obs, _ = env.reset()

        # warmup: action ngẫu nhiên để lấp buffer; sau đó dùng actor
        if step < warmup:
            action = env.action_space.sample()
            # đưa về [-1,1] cho buffer (actor xuất [-1,1])
            a_store = np.clip(action, -1, 1).astype(np.float32)
        else:
            import torch
            with torch.no_grad():
                obs_t = torch.tensor(obs, dtype=torch.float32, device=dev).unsqueeze(0)
                a = sac.actor.act(obs_t)
            a_store = a.cpu().numpy()[0].astype(np.float32)
            action = a_store   # env tự clip trong step

        next_obs, reward, term, trunc, info = env.step(action)
        buf.add(obs.astype(np.float32), a_store, float(reward), next_obs.astype(np.float32))
        ep_reward += reward
        obs = next_obs
        if term or trunc:
            ep_rewards.append(ep_reward); ep_reward = 0.0
            obs, _ = env.reset()

        # train định kỳ sau warmup
        if step >= warmup and step % train_every == 0:
            last_info = sac.train_from_buffer(buf, steps=train_iters, log_every=10_000)

        if step % 25_000 == 0:
            fps = step / (time.time() - t0)
            mr = np.mean(ep_rewards[-20:]) if ep_rewards else 0.0
            cl = last_info.get("critic_loss", 0.0)
            print(f"  Steps: {step:>8,} | FPS: {fps:5.0f} | "
                  f"Mean reward: {mr:7.2f} | critic={cl:.3f}")

    print(f"\nTrain xong! {time.time()-t0:.0f}s")

    # export ONNX theo tên profile (giống PPO)
    if profile in ("battery_saver", "performance"):
        out = os.path.join(MODELS_DIR, f"batteryclaw_policy_{profile}.onnx")
    else:
        out = os.path.join(MODELS_DIR, "batteryclaw_policy.onnx")
    sac.export_actor_onnx(out)
    print(f"[ONNX] SAC actor export: {out}")
    print("    Input (batch,15) -> Output (batch,7), tanh [-1,1] — khop rl_brain.")
    return out


if __name__ == "__main__":
    p = argparse.ArgumentParser(description="BatteryClaw SAC Trainer")
    p.add_argument("--steps", type=int, default=300_000)
    p.add_argument("--profile", type=str, default=None,
                   choices=["battery_saver", "balanced", "performance"])
    args = p.parse_args()
    collect_and_train(total_steps=args.steps, profile=args.profile)
