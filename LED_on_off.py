
#!/usr/bin/python

"""
2026/11/20
###########################################################################
# LEDを on off

テキストファイル LED_1_on.txt があれば、GPIO#27をHIGHに、なければLOWにする
テキストファイル LED_2_on.txt があれば、GPIO#17をHIGHに、なければLOWにする

テキストファイル LED_1_bres.txt があれば、GPIO#27をファイル内の数だけ点滅させる
テキストファイル LED_2_bres.txt があれば、GPIO#27をファイル内の数だけ点滅させる
############################################################################

LED_on_off.py
Raspberry Pi / gpiozero

GPIO27 : LED1
GPIO17 : LED2

LED_1_on.txt     : LED1点灯
LED_2_on.txt     : LED2点灯
LED_1_bres.txt   : LED1点滅開始
LED_2_bres.txt   : LED2点滅開始
LED_1_bres_n.txt : LED1点滅回数
LED_2_bres_n.txt : LED2点滅回数

・PWMLEDだけでGPIOを管理
・subprocess不使用
・LED1とLED2は独立して動作
・点滅中も両方のLEDを監視
・終了時にGPIOを解放
"""

import os
import time
from gpiozero import PWMLED

# --------------------------------------------------
# 設定
# --------------------------------------------------
LED1_PIN = 27
LED2_PIN = 17

POLL_INTERVAL = 0.02
START_WAIT = 1.0

START_DUTY = 0
STEP = 5
PWM_INTERVAL = 0.1
ON_WAIT = 0.5
OFF_WAIT = 0.7

BASE_DIR = os.path.dirname(os.path.abspath(__file__))

FILES = {
    1: {
        "on": os.path.join(BASE_DIR, "LED_1_on.txt"),
        "bres": os.path.join(BASE_DIR, "LED_1_bres.txt"),
        "count": os.path.join(BASE_DIR, "LED_1_bres_n.txt")
    },
    2: {
        "on": os.path.join(BASE_DIR, "LED_2_on.txt"),
        "bres": os.path.join(BASE_DIR, "LED_2_bres.txt"),
        "count": os.path.join(BASE_DIR, "LED_2_bres_n.txt")
    }
}

PINS = {
    1: LED1_PIN,
    2: LED2_PIN
}

# --------------------------------------------------
# PWM LED初期化
# --------------------------------------------------
pwm = {}

def setup():
    for n in (1, 2):
        pwm[n] = PWMLED(
            PINS[n],
            frequency=100,
            initial_value=0
        )

# --------------------------------------------------
# 点滅状態初期化
# --------------------------------------------------
state = {}

def init_state():
    for n in (1, 2):
        state[n] = {
            "active": False,
            "count": 0,
            "done": 0,
            "phase": "idle",
            "value": 0,
            "next": 0
        }

# --------------------------------------------------
# 点滅回数読み込み
# --------------------------------------------------
def read_count(path):
    for retry in range(5):
        try:
            with open(path, "r") as f:
                data = f.read().strip()

            if data:
                count = int(data)

                if count > 0:
                    return count

        except (OSError, ValueError) as e:
            print("点滅回数読み込みエラー:", repr(e))

        time.sleep(0.2)

    print("点滅回数を取得できません:", path)
    return None

# --------------------------------------------------
# 点滅開始
# --------------------------------------------------
def start_breathing(n):
    count = read_count(FILES[n]["count"])

    if count is None:
        return

    now = time.monotonic()

    state[n].update({
        "active": True,
        "count": count,
        "done": 0,
        "phase": "wait",
        "value": START_DUTY,
        "next": now + START_WAIT
    })

    print("LED", n, "点滅開始:", count, "回")

# --------------------------------------------------
# 点滅制御
# --------------------------------------------------
def update_breathing(n):
    s = state[n]

    if not s["active"]:
        return

    now = time.monotonic()

    if now < s["next"]:
        return

    # ----------------------------------------------
    # 開始待ち
    # ----------------------------------------------
    if s["phase"] == "wait":
        s["phase"] = "up"
        s["value"] = START_DUTY

    # ----------------------------------------------
    # 徐々に明るくする
    # ----------------------------------------------
    elif s["phase"] == "up":
        pwm[n].value = min(100, s["value"]) / 100.0
        s["value"] += STEP

        if s["value"] > 100:
            pwm[n].value = 1.0
            s["phase"] = "on_wait"
            s["next"] = now + ON_WAIT
            return

        s["next"] = now + PWM_INTERVAL
        return

    # ----------------------------------------------
    # 最大輝度で待つ
    # ----------------------------------------------
    elif s["phase"] == "on_wait":
        s["phase"] = "down"
        s["value"] = 100

    # ----------------------------------------------
    # 徐々に暗くする
    # ----------------------------------------------
    elif s["phase"] == "down":
        pwm[n].value = max(0, s["value"]) / 100.0
        s["value"] -= STEP

        if s["value"] < 0:
            pwm[n].value = 0.0
            s["phase"] = "off_wait"
            s["next"] = now + OFF_WAIT
            return

        s["next"] = now + PWM_INTERVAL
        return

    # ----------------------------------------------
    # 消灯待ち・回数カウント
    # ----------------------------------------------
    elif s["phase"] == "off_wait":
        s["done"] += 1

        remaining = s["count"] - s["done"]

        print("LED", n, "残り回数:", remaining)

        if s["done"] >= s["count"]:
            s["active"] = False
            s["phase"] = "idle"
            pwm[n].value = 0.0

            print("LED", n, "点滅終了")
            return

        s["phase"] = "up"
        s["value"] = START_DUTY

    s["next"] = now + PWM_INTERVAL

# --------------------------------------------------
# メイン処理
# --------------------------------------------------
try:
    setup()
    init_state()

    print("LED監視開始")

    while True:

        for n in (1, 2):
            f = FILES[n]
            s = state[n]

            # --------------------------------------
            # 点滅開始合図の確認
            # --------------------------------------
            if not s["active"] and os.path.exists(f["bres"]):

                # 点滅回数を読み込んで開始
                start_breathing(n)

                # 開始合図ファイル削除
                try:
                    os.remove(f["bres"])
                except OSError as e:
                    print("開始ファイル削除エラー:", repr(e))

            # --------------------------------------
            # 点滅中
            # --------------------------------------
            if s["active"]:
                update_breathing(n)

            # --------------------------------------
            # 通常点灯・消灯
            # --------------------------------------
            else:
                if os.path.exists(f["on"]):
                    pwm[n].value = 1.0
                else:
                    pwm[n].value = 0.0

        time.sleep(POLL_INTERVAL)

# --------------------------------------------------
# 終了処理
# --------------------------------------------------
except KeyboardInterrupt:
    print("終了します。")

except Exception as e:
    print("Program error:", repr(e))

finally:
    for n in (1, 2):
        try:
            if n in pwm:
                pwm[n].off()
                pwm[n].close()

        except Exception as e:
            print("GPIO cleanup error:", repr(e))

    print("Program end")
