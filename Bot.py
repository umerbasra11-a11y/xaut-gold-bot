import requests
import pandas as pd
from datetime import datetime
import time
import os
import threading
from flask import Flask

app = Flask(__name__)

print("Gold Signal Bot - ULTIMATE VERSION Render Pe...")
print("Multi-Timeframe | Volume | S/R | Score System")

ACCOUNT_BALANCE = 100
RISK_PERCENT = 1
ATR_MIN = 3
CHECK_INTERVAL = 900 # 15 min

TELEGRAM_TOKEN = "8730890284:AAFeHlDxc2fBX9xMh9E21KwZNyZ4vI3WXp8"
TELEGRAM_CHAT_ID = "8339681150"

def send_telegram_alert(message):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}
    try: requests.post(url, data=data, timeout=15)
    except Exception as e: print(f"Telegram Error: {e}")

def calculate_atr(df, period=14):
    high_low = df['high'] - df['low']
    high_close = abs(df['high'] - df['close'].shift())
    low_close = abs(df['low'] - df['close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = ranges.max(axis=1)
    return true_range.rolling(period).mean()

def calculate_rsi(df, period=14):
    delta = df['close'].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(span=period, adjust=False).mean()
    avg_loss = loss.ewm(span=period, adjust=False).mean()
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def get_support_resistance(df, window=40):
    recent = df.tail(window)
    support = round(recent['low'].min(), 2)
    resistance = round(recent['high'].max(), 2)
    return support, resistance

def get_data(interval, limit=200):
    url = f"https://contract.mexc.com/api/v1/contract/kline/XAUT_USDT?interval={interval}&limit={limit}"
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        response = requests.get(url, headers=headers, timeout=15)
        data = response.json()
        if data.get('success')!= True: return None
        df = pd.DataFrame(data['data'], columns=['time','open','close','high','low','vol','amount'])
        df['time'] = pd.to_datetime(df['time'], unit='ms')
        df = df.sort_values('time').reset_index(drop=True)
        for col in ['close','high','low','open','vol']: df[col] = pd.to_numeric(df[col])
        return df
    except Exception as e: print(f"Net ka masla: {e}"); return None

def check_signal():
    df_15m = get_data("Min15", 200)
    df_1h = get_data("Hour1", 100)
    if df_15m is None or df_15m.empty: return

    df_15m['EMA20'] = df_15m['close'].ewm(span=20, adjust=False).mean()
    df_15m['EMA50'] = df_15m['close'].ewm(span=50, adjust=False).mean()
    df_15m['ATR'] = calculate_atr(df_15m)
    df_15m['RSI'] = calculate_rsi(df_15m)
    df_15m = df_15m.dropna()
    if len(df_15m) < 2: return

    last = df_15m.iloc[-1]; prev = df_15m.iloc[-2]
    last_close, last_ema20, last_ema50 = last['close'], last['EMA20'], last['EMA50']
    last_atr, last_rsi, last_vol = last['ATR'], last['RSI'], last['vol']
    avg_vol = df_15m['vol'].tail(20).mean()

    support, resistance = get_support_resistance(df_15m, window=40)
    near_support = abs(last_close - support) / last_close < 0.003
    near_resistance = abs(last_close - resistance) / last_close < 0.003

    h1_trend = "NEUTRAL"
    if df_1h is not None and not df_1h.empty:
        df_1h['EMA20'] = df_1h['close'].ewm(span=20, adjust=False).mean()
        df_1h['EMA50'] = df_1h['close'].ewm(span=50, adjust=False).mean()
        df_1h = df_1h.dropna()
        if len(df_1h) >= 1:
            h1_last = df_1h.iloc[-1]
            if h1_last['EMA20'] > h1_last['EMA50']: h1_trend = "BULLISH"
            elif h1_last['EMA20'] < h1_last['EMA50']: h1_trend = "BEARISH"

    volume_ok = last_vol > avg_vol * 1.1
    atr_ok = last_atr > ATR_MIN
    signal = "WAIT"; reasons = []; score = 0

    ema_cross_up = prev['EMA20'] <= prev['EMA50'] and last_ema20 > last_ema50
    ema_bull_trend = last_ema20 > last_ema50 and last_close > last_ema20
    rsi_ok_long = 35 < last_rsi < 68

    ema_cross_down = prev['EMA20'] >= prev['EMA50'] and last_ema20 < last_ema50
    ema_bear_trend = last_ema20 < last_ema50 and last_close < last_ema20
    rsi_ok_short = 32 < last_rsi < 65

    if not atr_ok:
        msg = f"✅ <b>Bot Alive</b>\n\n⏳ SIGNAL : WAIT\n<b>Reason:</b> ATR {round(last_atr,2)} - Market slow\n<b>Price:</b> ${round(last_close,2)}"
        send_telegram_alert(msg); return

    # LONG Logic
    if ema_cross_up and rsi_ok_long: score += 3; reasons.append("EMA Cross Up ✅")
    elif ema_bull_trend and rsi_ok_long: score += 2; reasons.append("Uptrend Strong ✅")
    if h1_trend == "BULLISH" and score > 0: score += 2; reasons.append("1H Bullish ✅")
    if volume_ok and score > 0: score += 1; reasons.append("Volume High ✅")
    if near_support and score > 0: score += 1; reasons.append("Near Support ✅")
    if score >= 3 and (ema_cross_up or ema_bull_trend): signal = "LONG"

    # SHORT Logic
    if signal == "WAIT":
        score = 0; reasons = []
        if ema_cross_down and rsi_ok_short: score += 3; reasons.append("EMA Cross Down ✅")
        elif ema_bear_trend and rsi_ok_short: score += 2; reasons.append("Downtrend Strong ✅")
        if h1_trend == "BEARISH" and score > 0: score += 2; reasons.append("1H Bearish ✅")
        if volume_ok and score > 0: score += 1; reasons.append("Volume High ✅")
        if near_resistance and score > 0: score += 1; reasons.append("Near Resistance ✅")
        if score >= 3 and (ema_cross_down or ema_bear_trend): signal = "SHORT"

    if signal == "LONG":
        entry = last_close; sl = round(entry - (last_atr * 1.5), 2); tp = round(entry + (last_atr * 3), 2)
        msg = f"🚀 <b>XAUT/USDT BUY SIGNAL</b> 🟢\n<b>Score:</b> {score}/7\n" + "\n".join(reasons) + f"\n<b>Entry:</b> ${round(entry,2)}\n<b>SL:</b> ${sl}\n<b>TP:</b> ${tp}\n<b>ATR:</b> {round(last_atr,2)} | <b>RSI:</b> {round(last_rsi,1)}"
        send_telegram_alert(msg)
    elif signal == "SHORT":
        entry = last_close; sl = round(entry + (last_atr * 1.5), 2); tp = round(entry - (last_atr * 3), 2)
        msg = f"📉 <b>XAUT/USDT SELL SIGNAL</b> 🔴\n<b>Score:</b> {score}/7\n" + "\n".join(reasons) + f"\n<b>Entry:</b> ${round(entry,2)}\n<b>SL:</b> ${sl}\n<b>TP:</b> ${tp}\n<b>ATR:</b> {round(last_atr,2)} | <b>RSI:</b> {round(last_rsi,1)}"
        send_telegram_alert(msg)
    else:
        reason = "Volume kam" if not volume_ok else "Sideways"
        msg = f"✅ <b>Bot Alive</b>\n\n⏳ SIGNAL : WAIT\n<b>Reason:</b> {reason}\n<b>Price:</b> ${round(last_close,2)}\n<b>ATR:</b> {round(last_atr,2)} | <b>RSI:</b> {round(last_rsi,1)}"
        send_telegram_alert(msg)

def bot_loop():
    send_telegram_alert("✅ <b>Ultimate Gold Signal Bot Restarted</b>\n\n⏰ Har 15 Min baad market check ho ga\n📊 Timeframe: 15 Min")
    while True:
        try: check_signal(); time.sleep(CHECK_INTERVAL)
        except Exception as e: print(f"Error: {e}"); time.sleep(60)

@app.route('/')
def home(): return "Ultimate Bot is alive ✅"

if __name__ == "__main__":
    threading.Thread(target=bot_loop, daemon=True).start()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))
