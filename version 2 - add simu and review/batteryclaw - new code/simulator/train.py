"""
BatteryClaw — train.py
Train PPO agent trên BatteryClawEnv, sau đó export sang ONNX
Chạy trên PC có GPU — không tốn pin laptop

Dùng: python train.py [--steps 500000] [--export]
"""

import argparse
import os
import time
import numpy as np

from stable_baselines3 import PPO
from stable_baselines3.common.env_util import make_vec_env
from stable_baselines3.common.callbacks import (
    EvalCallback, CheckpointCallback, BaseCallback
)
from stable_baselines3.common.monitor import Monitor

from battery_env import BatteryClawEnv


# [FIX] Luu model CO DINH vao simulator/models/ bat ke dang dung o thu muc nao.
#  Truoc day dung "models/" tuong doi theo CWD -> file roi vao goc project khi
#  chay `python simulator/train.py` tu thu muc cha. Neo theo vi tri train.py:
_SIM_DIR    = os.path.dirname(os.path.abspath(__file__))
MODELS_DIR  = os.path.join(_SIM_DIR, "models")
LOGS_DIR    = os.path.join(_SIM_DIR, "logs")
os.makedirs(MODELS_DIR, exist_ok=True)
os.makedirs(LOGS_DIR, exist_ok=True)


# ── Callback in tiến trình ───────────────────────────────────────────────────

class ProgressCallback(BaseCallback):
    def __init__(self, print_every=10000):
        super().__init__()
        self.print_every = print_every
        self.t0 = time.time()

    def _on_step(self):
        if self.num_timesteps % self.print_every == 0:
            elapsed = time.time() - self.t0
            fps = self.num_timesteps / elapsed
            mean_reward = np.mean([
                ep["r"] for ep in self.model.ep_info_buffer
            ]) if self.model.ep_info_buffer else 0.0
            print(f"  Steps: {self.num_timesteps:>7,} | "
                  f"FPS: {fps:>5.0f} | "
                  f"Mean reward: {mean_reward:>7.2f} | "
                  f"Elapsed: {elapsed:.0f}s")
        return True


# ── Train ────────────────────────────────────────────────────────────────────

def _make_vec(n_envs, difficulty):
    """Tao vectorized env voi do kho cho truoc (cho curriculum)."""
    def _mk():
        env = BatteryClawEnv(difficulty=difficulty)
        env = Monitor(env)
        return env
    return make_vec_env(_mk, n_envs=n_envs)


def train(total_steps=2_000_000, n_envs=8, export_onnx=True, curriculum=True):
    print("BatteryClaw — Train PPO Agent")
    print("=" * 50)

    # [F4] CURRICULUM LEARNING: train tu de -> kho de model hoi tu nhanh, khong "ngop".
    #  Phase 1 (15%): 1 may ultrabook, viec nhe, khong phá bĩnh  (difficulty 1)
    #  Phase 2 (35%): 6 may + 12 workload                        (difficulty 2)
    #  Phase 3 (50%): bat het spike/action-delay/sac/pin phi tuyen (difficulty 3)
    # [F4+F8] CURRICULUM LEARNING 4 PHASE: train tu de -> kho -> stress test.
    #  Phase 1 (15%): 1 may ultrabook, viec nhe, khong phá bĩnh        (difficulty 1)
    #  Phase 2 (30%): 6 may + 12 workload + lich sac + reward profile   (difficulty 2)
    #  Phase 3 (35%): bat F1/F2/F3 muc VUA (tre 1 step, spike thuong)    (difficulty 3)
    #  Phase 4 (20%): KICH KHUNG (tre 2 step, spike gap doi, pin chai nang) (difficulty 4)
    if curriculum:
        phases = [(1, 0.12), (2, 0.33), (3, 0.43), (4, 0.12)]
    else:
        phases = [(4, 1.00)]

    print(f"[1] Khoi tao {n_envs} environments song song...")
    vec_env  = _make_vec(n_envs, phases[0][0])
    eval_env = _make_vec(1, 3)        # danh gia o do kho THUC TE (diff 3), khong phai stress test diff 4

    # PPO hyperparameters — tuned cho BatteryClawEnv
    print("[2] Khoi tao PPO model...")
    model = PPO(
        policy          = "MlpPolicy",
        env             = vec_env,
        learning_rate   = 3e-4,
        n_steps         = 2048,
        batch_size      = 512,
        n_epochs        = 10,
        gamma           = 0.99,
        gae_lambda      = 0.95,
        clip_range      = 0.2,
        ent_coef        = 0.02,
        vf_coef         = 0.5,
        max_grad_norm   = 0.5,
        verbose         = 0,
        policy_kwargs   = dict(
            net_arch = [256, 256],
        )
    )

    # Callbacks
    checkpoint_cb = CheckpointCallback(
        save_freq  = 50_000,
        save_path  = MODELS_DIR,
        name_prefix= "batteryclaw_ppo"
    )
    eval_cb = EvalCallback(
        eval_env,
        best_model_save_path = os.path.join(MODELS_DIR, "best"),
        log_path             = os.path.join(LOGS_DIR, "eval"),
        eval_freq            = 25_000,
        n_eval_episodes      = 10,
        deterministic        = True,
        verbose              = 0
    )
    progress_cb = ProgressCallback(print_every=25_000)

    print(f"[3] Train {total_steps:,} steps...")
    print(f"    n_envs      = {n_envs}")
    print(f"    batch_size  = 512")
    print(f"    net_arch    = [256, 256]")
    print()

    t0 = time.time()
    for pi, (diff, frac) in enumerate(phases, 1):
        phase_steps = int(total_steps * frac)
        if pi > 1:
            # chuyen sang do kho moi: thay env cua model
            vec_env = _make_vec(n_envs, diff)
            model.set_env(vec_env)
        print(f"\n  >>> Phase {pi}/{len(phases)} | difficulty={diff} | "
              f"{phase_steps:,} steps")
        model.learn(
            total_timesteps = phase_steps,
            callback        = [checkpoint_cb, eval_cb, progress_cb],
            progress_bar    = False,
            reset_num_timesteps = (pi == 1),   # giu dem timestep qua cac phase
        )
    elapsed = time.time() - t0
    print(f"\nTrain xong! {elapsed:.0f}s ({total_steps/elapsed:.0f} steps/sec)")

    # Lưu model cuối
    _final = os.path.join(MODELS_DIR, "batteryclaw_ppo_final")
    model.save(_final)
    print(f"Model luu tai: {_final}.zip")

    # [FIX export best] EvalCallback da luu best model (theo eval o difficulty cao
    #  nhat). Model CUOI thuong bi "nhuom" boi phase 4 khac nghiet -> nap lai BEST
    #  de export, tranh deploy ban kem on dinh.
    best_path = os.path.join(MODELS_DIR, "best", "best_model.zip")
    export_model = model
    if os.path.exists(best_path):
        try:
            from stable_baselines3 import PPO as _PPO
            export_model = _PPO.load(best_path)
            print(f"[best] Dung best model de export: {best_path}")
        except Exception as e:
            print(f"[best] Khong nap duoc best model ({e}), dung model cuoi.")

    # ── Evaluation ──────────────────────────────────────────────────────────
    print("\n[4] Danh gia model (best)...")
    evaluate_model(export_model)

    # ── Export ONNX ─────────────────────────────────────────────────────────
    if export_onnx:
        # [FIX eval mode] dat policy ve eval truoc khi export (on dinh inference)
        try:
            export_model.policy.set_training_mode(False)
        except Exception:
            pass
        export_to_onnx(export_model)

    return model


# ── Đánh giá model ──────────────────────────────────────────────────────────

def evaluate_model(model, n_episodes=20):
    env = BatteryClawEnv(difficulty=3)
    rewards      = []
    battery_ends = []
    lag_totals   = []

    for ep in range(n_episodes):
        obs, _ = env.reset(seed=ep)
        ep_reward  = 0.0
        ep_lag     = 0.0
        done       = False

        while not done:
            action, _ = model.predict(obs, deterministic=True)
            obs, reward, terminated, truncated, info = env.step(action)
            ep_reward += reward
            ep_lag    += info["lag"]
            done = terminated or truncated

        rewards.append(ep_reward)
        battery_ends.append(info["battery_pct"])
        lag_totals.append(ep_lag)

    print(f"  Mean reward      : {np.mean(rewards):.2f} +/- {np.std(rewards):.2f}")
    print(f"  Mean battery end : {np.mean(battery_ends):.1f}%")
    print(f"  Mean lag total   : {np.mean(lag_totals):.2f}")
    print(f"  Best episode     : {max(rewards):.2f}")


# ── Export ONNX ─────────────────────────────────────────────────────────────

def export_to_onnx(model, path=None):
    """
    Export policy network sang ONNX để chạy trên laptop bằng onnxruntime
    Input : (1, 15) float32 — observation vector
    Output: (1, 7) float32 — action vector
    """
    if path is None:
        path = os.path.join(MODELS_DIR, "batteryclaw_policy.onnx")
    try:
        import torch
        import torch.onnx

        obs_example = torch.zeros(1, 15, dtype=torch.float32)  # [P1] 7 -> 15

        # Lấy policy network từ SB3
        policy = model.policy
        policy.eval()

        # Wrapper chỉ lấy mean action (deterministic)
        class PolicyWrapper(torch.nn.Module):
            def __init__(self, policy):
                super().__init__()
                self.policy = policy

            def forward(self, obs):
                with torch.no_grad():
                    features = self.policy.extract_features(
                        obs, self.policy.pi_features_extractor)
                    latent_pi = self.policy.mlp_extractor.forward_actor(features)
                    mean_actions = self.policy.action_net(latent_pi)
                    # Squash về action space
                    return torch.tanh(mean_actions)

        wrapper = PolicyWrapper(policy)

        torch.onnx.export(
            wrapper,
            obs_example,
            path,
            input_names  = ["observation"],
            output_names = ["action"],
            dynamic_axes = {
                "observation": {0: "batch"},
                "action"     : {0: "batch"}
            },
            opset_version = 17
        )
        print(f"\n[5] ONNX export: {path}")
        print(f"    Input  : (batch, 15) float32")  # [P1]
        print(f"    Output : (batch, 7) float32")  # [P1]

        # Verify
        import onnxruntime as ort
        sess = ort.InferenceSession(path)
        out  = sess.run(None, {"observation": np.zeros((1, 15), dtype=np.float32)})  # [P1]
        print(f"    Test run OK: {out[0]}")

    except ImportError as e:
        print(f"\n[5] ONNX export skip: {e}")
        print("    Cai them: pip install onnx onnxruntime")
    except Exception as e:
        print(f"\n[5] ONNX export loi: {e}")
        # Fallback: luu dang SB3 zip
        print("    Model da duoc luu dang .zip (dung stable-baselines3 de load)")


# ── Inference test — mô phỏng RL Brain trên laptop ──────────────────────────

def inference_demo(model_path="models/batteryclaw_ppo_final"):
    """Demo: load model và chạy 1 episode với render"""
    print("\nBatteryClaw — Inference Demo")
    print("=" * 50)

    model = PPO.load(model_path)
    env   = BatteryClawEnv(render_mode="human")
    obs, _ = env.reset(seed=0)

    print(f"{'Step':>4} | {'Batt%':>6} | {'Throttle':>8} | {'Bright':>6} | "
          f"{'Temp':>5} | {'Workload':>8} | {'Reward':>7}")
    print("-" * 70)

    total_reward = 0.0
    done = False
    while not done:
        action, _ = model.predict(obs, deterministic=True)
        obs, reward, terminated, truncated, info = env.step(action)
        total_reward += reward
        done = terminated or truncated

    print(f"\nTotal reward: {total_reward:.2f}")
    print(f"Final battery: {info['battery_pct']:.1f}%")


# ── CLI ──────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="BatteryClaw PPO Trainer")
    parser.add_argument("--steps",   type=int,  default=3_000_000,
                        help="Tong so steps train (default: 3000000)")
    parser.add_argument("--envs",    type=int,  default=8,
                        help="So environments song song (default: 8)")
    parser.add_argument("--export",  action="store_true", default=True,
                        help="Export ONNX sau khi train")
    parser.add_argument("--no-curriculum", action="store_true",
                        help="Tat curriculum learning (train thang o do kho full)")
    parser.add_argument("--demo",    action="store_true",
                        help="Chay demo inference (can model da train)")
    args = parser.parse_args()

    if args.demo:
        inference_demo()
    else:
        train(
            total_steps = args.steps,
            n_envs      = args.envs,
            export_onnx = args.export,
            curriculum  = not args.no_curriculum,
        )
