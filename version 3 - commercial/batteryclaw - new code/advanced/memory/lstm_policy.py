"""
BatteryClaw — advanced/memory/lstm_policy.py  (PHASE 4 — mục 4.2)

Thêm BỘ NHỚ cho policy. Hiện tại policy(s_t) -> a_t chỉ nhìn hiện tại.
Nâng cấp: policy(s_{t-29..t}) -> a_t nhìn chuỗi 30 state gần nhất.

Cho phép model nhận ra mẫu theo thời gian, ví dụ:
  • "vừa mở IDE -> sắp compile -> cần CPU cao"
  • "pin sắp hết -> cần tiết kiệm khẩn cấp"
  • "đã tiết kiệm đủ rồi -> có thể thoải mái hơn"

LSTM nhẹ (hidden 128) hợp chạy trên laptop. Đầu ra tanh-squashed [-1,1].

Kèm SequenceBuffer: tiện gom 30 state gần nhất lúc deploy (rolling window).
"""

import torch
import torch.nn as nn

SEQ_LEN = 30


class LSTMPolicy(nn.Module):
    """Input: (batch, seq_len, state_dim) -> action (batch, action_dim) tanh."""

    def __init__(self, state_dim=15, action_dim=7, hidden=128, seq_len=SEQ_LEN):
        super().__init__()
        self.seq_len = seq_len
        self.lstm = nn.LSTM(state_dim, hidden, batch_first=True)
        self.head = nn.Sequential(
            nn.Linear(hidden, hidden), nn.ReLU(),
            nn.Linear(hidden, action_dim),
        )

    def forward(self, seq, hidden_state=None):
        """seq: (batch, seq_len, state_dim). Trả (action, hidden_state)."""
        out, hidden_state = self.lstm(seq, hidden_state)
        last = out[:, -1, :]               # lấy hidden ở bước cuối
        action = torch.tanh(self.head(last))
        return action, hidden_state

    def act(self, seq):
        """Deploy: trả action (numpy) từ một chuỗi (seq_len, state_dim)."""
        self.eval()
        with torch.no_grad():
            if seq.dim() == 2:
                seq = seq.unsqueeze(0)     # thêm batch
            a, _ = self.forward(seq)
        return a.squeeze(0)


class SequenceBuffer:
    """Rolling window giữ SEQ_LEN state gần nhất để feed LSTM lúc deploy."""

    def __init__(self, state_dim=15, seq_len=SEQ_LEN):
        self.seq_len = seq_len
        self.state_dim = state_dim
        self.buf = torch.zeros(seq_len, state_dim)
        self.filled = 0

    def push(self, state_vec):
        s = torch.as_tensor(state_vec, dtype=torch.float32)
        self.buf = torch.roll(self.buf, shifts=-1, dims=0)
        self.buf[-1] = s
        self.filled = min(self.filled + 1, self.seq_len)

    def sequence(self):
        """Trả (seq_len, state_dim). Khi chưa đủ, các ô đầu là 0 (padding)."""
        return self.buf.clone()


if __name__ == "__main__":
    print("BatteryClaw 4.2 — LSTM policy self-test")
    pol = LSTMPolicy()

    # batch chuỗi
    seq = torch.randn(4, SEQ_LEN, 15)
    a, h = pol(seq)
    print("  forward:", a.shape, "| action range:",
          round(float(a.min()), 3), round(float(a.max()), 3))
    assert a.shape == (4, 7) and a.min() >= -1.0001 and a.max() <= 1.0001

    # sequence buffer rolling
    sb = SequenceBuffer()
    for i in range(40):                    # đẩy 40 > seq_len=30
        sb.push([float(i)] * 15)
    s = sb.sequence()
    assert s.shape == (SEQ_LEN, 15)
    # state mới nhất phải là 39, cũ nhất giữ lại là 10
    assert abs(float(s[-1, 0]) - 39) < 1e-4 and abs(float(s[0, 0]) - 10) < 1e-4
    print("  rolling window giữ đúng 30 state mới nhất (10..39)")

    # act từ buffer
    act = pol.act(sb.sequence())
    assert act.shape == (7,)
    print("PASS ✓")
