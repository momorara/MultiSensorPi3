#!/usr/bin/env python
"""
iR信号を受信して符号化します。
irrpを使わずに、Linuxのカーネル機能を使ってラズパイ5でも実現できました。

"""
from pathlib import Path
import re
import subprocess


def capture_ir_signal(output_path: str | Path, timeout_sec: int = 5) -> None:
    """timeout コマンド経由で ir-ctl --receive を実行し、生データをファイルに保存する。"""
    out_path = Path(output_path)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    cmd = ["timeout", f"{timeout_sec}s", "ir-ctl", "-d", "/dev/lirc0", "--receive"]

    with open(out_path, "w", encoding="utf-8") as f:
        result = subprocess.run(cmd, stdout=f, stderr=subprocess.PIPE, text=True)

    if result.returncode == 124:
        print(f"{timeout_sec}秒経過したため受信を終了しました（保存先: {out_path}）。")
    elif result.returncode == 0:
        print(f"受信が完了しました（保存先: {out_path}）。")
    else:
        print(f"ir-ctl が終了コード {result.returncode} で終了しました。")
        if result.stderr:
            print(f"エラー内容: {result.stderr.strip()}")


def decode_ir_to_frames(raw_text: str, threshold_us: int = 1000) -> list[dict]:
    """
    ir-ctl 形式のパルス/スペース列（+パルス -スペース）をフレームごとの 0/1 列に変換する。
    スペース幅（負の値の絶対値）が threshold_us 未満なら '0'、以上なら '1' とする。
    """
    tokens = [int(x) for x in re.findall(r"[+-]\d+", raw_text)]

    frames = []
    current_bits = []
    has_header = False
    i = 0

    while i < len(tokens):
        val = tokens[i]

        # リーダー部（長いパルス + リーダースペース）の検出
        if val > 7000 and i + 1 < len(tokens) and tokens[i + 1] < 0:
            space = -tokens[i + 1]
            if current_bits:
                frames.append({"type": "data", "bits": "".join(current_bits)})
                current_bits = []

            if 3500 <= space <= 6000:
                has_header = True
                i += 2
                continue
            elif 1800 <= space < 3500:
                # リピートコードは読み飛ばす
                has_header = False
                i += 2
                continue

        # データビットの読み取り（+パルス のあとに -スペース が続く形）
        if has_header and val > 0 and i + 1 < len(tokens) and tokens[i + 1] < 0:
            pulse = val
            space = -tokens[i + 1]

            if 200 <= pulse <= 1200 and 200 <= space <= 2500:
                bit = "1" if space >= threshold_us else "0"
                current_bits.append(bit)
                i += 2
                continue
            else:
                if current_bits:
                    frames.append({"type": "data", "bits": "".join(current_bits)})
                    current_bits = []
                has_header = False

        i += 1

    if current_bits:
        frames.append({"type": "data", "bits": "".join(current_bits)})

    return frames


def save_bits_to_file(
    input_path: str | Path,
    output_path: str | Path,
    threshold_us: int = 1000,
) -> None:
    """入力ファイル（生パルス列）を読み込み、先頭の 0/1 データ1行のみを保存する。"""
    src_path = Path(input_path)
    dst_path = Path(output_path)
    dst_path.parent.mkdir(parents=True, exist_ok=True)

    if not src_path.exists() or src_path.stat().st_size == 0:
        print(f"変換対象のデータがありません（{src_path} が存在しないか空です）。")
        dst_path.write_text("受信データがありません\n", encoding="utf-8")
        return

    raw_text = src_path.read_text(encoding="utf-8")
    frames = decode_ir_to_frames(raw_text, threshold_us=threshold_us)

    first_bits = next(
        (frame["bits"] for frame in frames if frame["type"] == "data" and frame["bits"]),
        None,
    )

    if not first_bits:
        print(f"有効な信号データが見つかりませんでした（{src_path}）。")
        dst_path.write_text("受信データがありません\n", encoding="utf-8")
        return

    dst_path.write_text(f"{first_bits}\n", encoding="utf-8")
    print(f"0/1 変換結果（1行）を {dst_path} に保存しました。")


if __name__ == "__main__":
    raw_file = "/home/pi/sensorHAT/iR_signal.txt"
    bit_file = "/home/pi/sensorHAT/iR_command.txt"

    while True:
        # 1. 赤外線信号を受信して /home/pi/sensorHAT/iR_signal.txt に保存
        capture_ir_signal(output_path=raw_file, timeout_sec=5)

        # 2. /home/pi/sensorHAT/iR_signal.txt を 0/1 に変換して iR_command.txt に1行のみ保存
        save_bits_to_file(input_path=raw_file, output_path=bit_file, threshold_us=1000)

        # 保存内容の確認表示
        content = Path(bit_file).read_text(encoding="utf-8")
        print(f"--- {bit_file} の内容 ---")
        print(content.rstrip("\n"))