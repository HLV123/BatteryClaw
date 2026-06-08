"""
BatteryClaw — dataset_uploader.py  (PHASE 2 — mục 2.4: Multi-Device Dataset)

Gửi dữ liệu thu thập (parquet) lên server dưới dạng ẨN DANH để gom thành
dataset chung. KHÔNG gửi email, không gửi machine_id gốc, không gửi tên app.

Ẩn danh thế nào:
  • device_hash = sha256(machine_id + salt)[:16]  — không thể đảo ngược ra máy
  • device_class = mô tả phần cứng chung (vd "i7-11800H+RTX3050") để gom nhóm
  • bỏ cột fg_app / session_id trước khi gửi (server cũng lọc lại lần nữa)

Dùng:
  python dataset_uploader.py --server https://your-server --data ../datacollector/data
  python dataset_uploader.py --dry-run    # chỉ in ra, không gửi
"""

import argparse
import glob
import hashlib
import json
import os
import sys

DROP_COLS = {"fg_app", "session_id"}


def device_hash(machine_id: str, salt: str = "batteryclaw-v1") -> str:
    return hashlib.sha256((machine_id + salt).encode()).hexdigest()[:16]


def load_rows(data_dir):
    rows = []
    files = sorted(glob.glob(os.path.join(data_dir, "*.parquet"))) + \
            sorted(glob.glob(os.path.join(data_dir, "*.jsonl")))
    for f in files:
        if f.endswith(".parquet"):
            try:
                import pandas as pd
                df = pd.read_parquet(f)
                rows.extend(df.to_dict(orient="records"))
            except ImportError:
                print("Cần pandas để đọc parquet. Bỏ qua:", f)
        else:
            with open(f, encoding="utf-8") as fh:
                for line in fh:
                    line = line.strip()
                    if line:
                        rows.append(json.loads(line))
    return rows


def anonymize(rows):
    out = []
    for r in rows:
        rr = {k: v for k, v in r.items() if k not in DROP_COLS}
        out.append(rr)
    return out


def main():
    ap = argparse.ArgumentParser(description="BatteryClaw Phase 2 — Dataset Uploader")
    ap.add_argument("--server", default="", help="URL server (vd https://abc.ngrok.io)")
    ap.add_argument("--data",   default="../datacollector/data")
    ap.add_argument("--machine-id", default="UNKNOWN-MACHINE",
                    help="machine_id thật (sẽ được băm, KHÔNG gửi gốc)")
    ap.add_argument("--device-class", default="i7-11800H+RTX3050")
    ap.add_argument("--batch", type=int, default=2000, help="số dòng mỗi lần gửi")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    rows = anonymize(load_rows(args.data))
    if not rows:
        print("Không có dữ liệu để gửi.")
        return

    dh = device_hash(args.machine_id)
    print(f"Tổng {len(rows)} dòng | device_hash={dh} | class={args.device_class}")

    if args.dry_run:
        print("[dry-run] mẫu 1 dòng đã ẩn danh:")
        print(json.dumps(rows[0], ensure_ascii=False, indent=2)[:600])
        print(f"[dry-run] sẽ gửi {len(rows)} dòng tới {args.server or '(chưa đặt --server)'}")
        return

    if not args.server:
        print("Thiếu --server. Dùng --dry-run để xem trước, hoặc cung cấp URL.")
        return

    import requests
    sent = 0
    for i in range(0, len(rows), args.batch):
        chunk = rows[i:i+args.batch]
        try:
            r = requests.post(args.server.rstrip("/") + "/api/dataset/upload",
                              json={"device_hash": dh,
                                    "device_class": args.device_class,
                                    "rows": chunk}, timeout=30)
            res = r.json()
            sent += res.get("received", 0)
            print(f"  gửi {len(chunk)} dòng -> server nhận {res.get('received')}")
        except Exception as e:
            print(f"  Lỗi gửi batch {i}: {e}")
            break
    print(f"Hoàn tất. Tổng đã gửi: {sent} dòng.")


if __name__ == "__main__":
    main()
