"""
BatteryClaw — advanced/sac/networks.py  (PHASE 4 — mục 4.1)

Mạng cho Soft Actor-Critic (SAC). Vì sao SAC thay PPO:
  • PPO on-policy, tốn nhiều sample -> không hợp online learning.
  • SAC off-policy -> học được từ experience replay (buffer Phase 3).
  • SAC tối ưu entropy -> tự nhiên explore tốt hơn, ổn định khi fine-tune liên tục.
  • Hợp continuous action (throttle, brightness...).

File này chỉ định nghĩa MẠNG (không chứa vòng train — xem sac_trainer.py):
  • GaussianActor: state -> phân phối action (mean, log_std) + reparameterized sample
  • TwinCritic:    (state, action) -> 2 giá trị Q (giảm overestimation)

Action gốc ở [-1,1] (tanh-squashed) — khớp contract 7 chiều của rl_brain.
"""

import torch
import torch.nn as nn
import torch.nn.functional as F

LOG_STD_MIN = -20
LOG_STD_MAX = 2


class GaussianActor(nn.Module):
    """state -> action (tanh-squashed Gaussian). Trả action + log_prob."""

    def __init__(self, state_dim=15, action_dim=7, hidden=128):
        super().__init__()
        self.body = nn.Sequential(
            nn.Linear(state_dim, hidden), nn.ReLU(),
            nn.Linear(hidden, hidden), nn.ReLU(),
        )
        self.mean_head    = nn.Linear(hidden, action_dim)
        self.log_std_head = nn.Linear(hidden, action_dim)

    def forward(self, state):
        h = self.body(state)
        mean = self.mean_head(h)
        log_std = torch.clamp(self.log_std_head(h), LOG_STD_MIN, LOG_STD_MAX)
        return mean, log_std

    def sample(self, state):
        """Reparameterization trick + tanh squash. Trả (action, log_prob)."""
        mean, log_std = self.forward(state)
        std = log_std.exp()
        normal = torch.distributions.Normal(mean, std)
        x = normal.rsample()                  # reparameterized
        action = torch.tanh(x)                # squash về [-1,1]
        # log_prob có hiệu chỉnh do tanh (công thức SAC chuẩn)
        log_prob = normal.log_prob(x) - torch.log(1 - action.pow(2) + 1e-6)
        log_prob = log_prob.sum(dim=-1, keepdim=True)
        return action, log_prob

    def act(self, state, deterministic=True):
        """Suy luận deploy: trả action tanh(mean) (deterministic)."""
        mean, _ = self.forward(state)
        return torch.tanh(mean)


class TwinCritic(nn.Module):
    """(state, action) -> Q1, Q2. Dùng min(Q1,Q2) để giảm overestimate."""

    def __init__(self, state_dim=15, action_dim=7, hidden=128):
        super().__init__()
        def make():
            return nn.Sequential(
                nn.Linear(state_dim + action_dim, hidden), nn.ReLU(),
                nn.Linear(hidden, hidden), nn.ReLU(),
                nn.Linear(hidden, 1),
            )
        self.q1 = make()
        self.q2 = make()

    def forward(self, state, action):
        x = torch.cat([state, action], dim=-1)
        return self.q1(x), self.q2(x)


if __name__ == "__main__":
    print("BatteryClaw 4.1 — SAC networks self-test")
    actor = GaussianActor()
    critic = TwinCritic()

    s = torch.randn(8, 15)
    a, logp = actor.sample(s)
    print("  actor sample:", a.shape, "log_prob:", logp.shape)
    assert a.shape == (8, 7) and logp.shape == (8, 1)
    assert a.min() >= -1.0001 and a.max() <= 1.0001, "action phải trong [-1,1]"

    det = actor.act(s)
    assert det.shape == (8, 7)

    q1, q2 = critic(s, a)
    print("  critic Q:", q1.shape, q2.shape)
    assert q1.shape == (8, 1) and q2.shape == (8, 1)
    print("PASS ✓")
