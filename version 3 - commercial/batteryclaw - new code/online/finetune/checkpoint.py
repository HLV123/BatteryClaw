"""
BatteryClaw — finetune/checkpoint.py  (PHASE 3 — mục 3.5)

Quản lý checkpoint policy:
  • Lưu checkpoint mỗi ngày (đặt tên theo ngày).
  • Giữ tối đa 7 checkpoint gần nhất, tự xóa cũ hơn.
  • Cho phép rollback về checkpoint trước nếu model mới tệ hơn.

Chỉ thao tác file — không phụ thuộc torch (chép/đổi tên là đủ).
"""

import os
import shutil
import datetime
import glob

KEEP_DAYS = 7


class CheckpointManager:
    def __init__(self, ckpt_dir, keep=KEEP_DAYS):
        self.dir = ckpt_dir
        self.keep = keep
        os.makedirs(ckpt_dir, exist_ok=True)

    def _stamp(self):
        return datetime.datetime.now().strftime("%Y%m%d")

    def save(self, model_path, tag=None):
        """Sao lưu model_path thành checkpoint. Trả đường dẫn checkpoint."""
        tag = tag or self._stamp()
        ext = os.path.splitext(model_path)[1] or ".onnx"
        dst = os.path.join(self.dir, f"policy_{tag}{ext}")
        shutil.copy2(model_path, dst)
        self._prune()
        return dst

    def list(self):
        """Danh sách checkpoint, mới nhất trước."""
        files = glob.glob(os.path.join(self.dir, "policy_*"))
        return sorted(files, reverse=True)

    def latest(self):
        cks = self.list()
        return cks[0] if cks else None

    def previous(self):
        """Checkpoint trước cái mới nhất (để rollback)."""
        cks = self.list()
        return cks[1] if len(cks) >= 2 else None

    def rollback(self, model_path):
        """Khôi phục model_path từ checkpoint trước đó. Trả True nếu thành công."""
        prev = self.previous()
        if not prev:
            return False
        shutil.copy2(prev, model_path)
        return True

    def _prune(self):
        cks = self.list()
        for old in cks[self.keep:]:
            try:
                os.remove(old)
            except OSError:
                pass


if __name__ == "__main__":
    print("BatteryClaw 3.5 — CheckpointManager self-test")
    import tempfile
    d = tempfile.mkdtemp()
    mp = os.path.join(d, "policy.onnx")
    open(mp, "w").write("v0")

    cm = CheckpointManager(os.path.join(d, "ckpt"), keep=3)
    # tạo 5 checkpoint với tag khác nhau
    for i in range(5):
        open(mp, "w").write(f"v{i}")
        cm.save(mp, tag=f"day{i}")
    cks = cm.list()
    print("  giữ lại:", [os.path.basename(x) for x in cks])
    assert len(cks) == 3, "chỉ giữ 3 cái mới nhất"

    # rollback: model hiện tại v4 -> về previous (day3)
    open(mp, "w").write("v4-bad")
    ok = cm.rollback(mp)
    assert ok and open(mp).read() == "v3", "rollback phải khôi phục day3"
    print("  rollback OK ->", open(mp).read())
    print("PASS ✓")
