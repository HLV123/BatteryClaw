"""
BatteryClaw — finetune/ewc.py  (PHASE 3 — mục 3.2)

Elastic Weight Consolidation (EWC): chống "catastrophic forgetting".
Khi fine-tune model trên dữ liệu mới của máy, ta không muốn nó QUÊN
kiến thức nền (đã học từ simulator/world model).

Ý tưởng: phạt việc thay đổi những trọng số QUAN TRỌNG với tác vụ cũ.
  penalty = Σ_i  F_i * (θ_i - θ*_i)^2
trong đó:
  θ*_i = trọng số gốc (sau khi học nền)
  F_i  = độ quan trọng (xấp xỉ đường chéo ma trận Fisher)

File này chỉ lo phần EWC, dùng được cho bất kỳ nn.Module nào.
"""

import torch


class EWC:
    # [DESIGN-05] Fisher matrix to bang so tham so model. MLP [128,128] ~25K
    #  (~100KB, ok). Neu model lon (LSTM/kien truc lon), canh bao vi Fisher
    #  co the ton nhieu RAM tren laptop dang chay game cung luc.
    PARAM_WARN_THRESHOLD = 500_000

    def __init__(self, model, importance=1000.0):
        import logging
        self.model = model
        self.importance = importance     # lambda — độ mạnh của ràng buộc
        # lưu ảnh chụp trọng số gốc (θ*)
        self.star = {n: p.detach().clone()
                     for n, p in model.named_parameters() if p.requires_grad}
        # Fisher diagonal — khởi tạo 0, ước lượng qua estimate_fisher()
        self.fisher = {n: torch.zeros_like(p) for n, p in self.star.items()}

        n_params = sum(p.numel() for p in self.star.values())
        if n_params > self.PARAM_WARN_THRESHOLD:
            logging.getLogger("ewc").warning(
                "Model co %d tham so (> %d). Fisher matrix se ton ~%.1f MB RAM. "
                "Can nhac dung Fisher thua (sparse) hoac giam tan suat fine-tune.",
                n_params, self.PARAM_WARN_THRESHOLD, n_params * 4 / 1e6)

    def estimate_fisher(self, states, actions, loss_fn):
        """Ước lượng độ quan trọng F_i từ một batch dữ liệu nền.
        states/actions: tensor. loss_fn(model, s, a) -> scalar loss."""
        self.model.eval()
        self.model.zero_grad()
        loss = loss_fn(self.model, states, actions)
        loss.backward()
        for n, p in self.model.named_parameters():
            if p.requires_grad and p.grad is not None:
                # F_i ≈ trung bình bình phương gradient
                self.fisher[n] = p.grad.detach().clone() ** 2
        self.model.zero_grad()

    def penalty(self):
        """Trả EWC penalty (scalar tensor) để cộng vào loss fine-tune."""
        loss = torch.tensor(0.0)
        for n, p in self.model.named_parameters():
            if n in self.star:
                loss = loss + (self.fisher[n] * (p - self.star[n]) ** 2).sum()
        return self.importance * loss


if __name__ == "__main__":
    import torch.nn as nn
    print("BatteryClaw 3.2 — EWC self-test")

    model = nn.Sequential(nn.Linear(4, 8), nn.ReLU(), nn.Linear(8, 2))

    def loss_fn(m, s, a):
        return ((m(s) - a) ** 2).mean()

    s = torch.randn(16, 4)
    a = torch.randn(16, 2)

    ewc = EWC(model, importance=100.0)
    ewc.estimate_fisher(s, a, loss_fn)

    # penalty ban đầu = 0 (trọng số chưa đổi)
    p0 = ewc.penalty().item()
    print("  penalty trước khi đổi trọng số:", round(p0, 6))
    assert abs(p0) < 1e-6

    # đổi trọng số -> penalty tăng
    with torch.no_grad():
        for p in model.parameters():
            p.add_(0.5)
    p1 = ewc.penalty().item()
    print("  penalty sau khi đổi trọng số:", round(p1, 4))
    assert p1 > p0
    print("PASS ✓")
