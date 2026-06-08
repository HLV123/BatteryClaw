"""
BatteryClaw — buffer/replay_buffer.py  (PHASE 3 — mục 3.1)

Bộ nhớ trải nghiệm của RIÊNG máy này. Mỗi transition: (s, a, r, s').
- Rolling buffer: giữ N transition gần nhất (mặc định 10.000), tự xóa cũ nhất.
- Lưu xuống đĩa (.npz) để không mất khi tắt máy.
- Lấy batch ngẫu nhiên cho fine-tuning (3.2).

Giữ thật ngắn gọn: chỉ lo việc chứa/đẩy/lấy mẫu/lưu/nạp.
"""

import os
import numpy as np

STATE_DIM  = 15
ACTION_DIM = 7


class ReplayBuffer:
    def __init__(self, capacity=10000, path=None):
        self.capacity = capacity
        self.path = path
        self.s  = np.zeros((capacity, STATE_DIM),  dtype=np.float32)
        self.a  = np.zeros((capacity, ACTION_DIM), dtype=np.float32)
        self.r  = np.zeros((capacity, 1),          dtype=np.float32)
        self.s2 = np.zeros((capacity, STATE_DIM),  dtype=np.float32)
        self.idx  = 0          # vị trí ghi tiếp theo (vòng tròn)
        self.size = 0          # số phần tử hiện có
        if path and os.path.exists(path):
            self.load()

    def add(self, state, action, reward, next_state):
        i = self.idx
        self.s[i]  = state
        self.a[i]  = action
        self.r[i]  = reward
        self.s2[i] = next_state
        self.idx  = (self.idx + 1) % self.capacity   # ghi đè cũ nhất khi đầy
        self.size = min(self.size + 1, self.capacity)

    def sample(self, batch_size, rng=None):
        rng = rng or np.random
        n = min(batch_size, self.size)
        ids = rng.integers(0, self.size, size=n) if hasattr(rng, "integers") \
              else rng.randint(0, self.size, size=n)
        return self.s[ids], self.a[ids], self.r[ids], self.s2[ids]

    def __len__(self):
        return self.size

    def save(self, path=None):
        p = path or self.path
        if not p:
            return
        os.makedirs(os.path.dirname(p) or ".", exist_ok=True)
        np.savez_compressed(
            p, s=self.s, a=self.a, r=self.r, s2=self.s2,
            idx=self.idx, size=self.size, capacity=self.capacity)

    def load(self, path=None):
        p = path or self.path
        d = np.load(p)
        cap = int(d["capacity"])
        # nếu capacity đổi, vẫn nạp tối đa có thể
        n = min(cap, self.capacity)
        self.s[:n]  = d["s"][:n]
        self.a[:n]  = d["a"][:n]
        self.r[:n]  = d["r"][:n]
        self.s2[:n] = d["s2"][:n]
        self.size = min(int(d["size"]), self.capacity)
        self.idx  = int(d["idx"]) % self.capacity


if __name__ == "__main__":
    print("BatteryClaw 3.1 — ReplayBuffer self-test")
    buf = ReplayBuffer(capacity=5)
    for i in range(8):                       # đẩy 8 vào buffer cap=5
        buf.add(np.full(STATE_DIM, i), np.full(ACTION_DIM, i),
                float(i), np.full(STATE_DIM, i + 1))
    assert len(buf) == 5, "phải giữ đúng capacity"
    # phần tử cũ nhất (0,1,2) đã bị đẩy ra
    rewards_in = set(int(buf.r[k, 0]) for k in range(buf.size))
    print("  rewards còn trong buffer:", sorted(rewards_in))
    assert rewards_in == {3, 4, 5, 6, 7}, "phải giữ 5 cái mới nhất"
    s, a, r, s2 = buf.sample(3)
    assert s.shape == (3, STATE_DIM) and a.shape == (3, ACTION_DIM)
    # lưu & nạp lại
    buf.save("/tmp/_bc_buf.npz")
    buf2 = ReplayBuffer(capacity=5, path="/tmp/_bc_buf.npz")
    assert len(buf2) == 5
    print("  save/load OK, sample shape OK")
    print("PASS ✓")
