import requests
import pandas as pd
from datetime import datetime
import time
import os
import threading
from flask import Flask

app = Flask(__name__)

print("Gold Signal Bot Start Ho Gaya - Render Pe...")
print("MEXC Futures se XAUT_USDT ka rate laa raha hai...")
print("Timeframe: 15 Min | EMA20/50 | RSI Filter ON | ATR > 3")
print("Check: Har 1 Ghanta | Telegram Alerts: ON ✅")

ACCOUNT_BALANCE = 100
RISK_PERCENT = 1
ATR_MIN = 3
CHECK_INTERVAL = 3600 # 3600 seconds = 1 hour

# ENV se token lena best hai. Warna yahan daal do
TELEGRAM_TOKEN = os.environ.get("TELEGRAM_TOKEN", "8730890284:AAFeHlDxc2fBX9xMh9E21KwZNyZ4vI3WXp8")
TELEGRAM_CHAT_ID = os.environ.get("TELEGRAM_CHAT_ID", "8339681150")

def send_telegram_alert(message, retries=3):
    url = f"https://api.telegram.org/bot{TELEGRAM_TOKEN}/sendMessage"
    data = {"chat_id": TELEGRAM_CHAT_ID, "text": message, "parse_mode": "HTML"}
    for attempt in range(retries):
        try:
            response = requests.post(url, data=data, timeout=15)
            if response.status_code == 200:
                print("📲 Telegram alert bhej diya ✅")
                return True
            else:
                print(f"📲 Telegram Error - Retry {attempt+1}/{retries}... Status: {response.status_code}")
        except Exception as e:
            print(f"📲 Telegram Error - Retry {attempt+1}/{retries}... {e}")
        time.sleep(5)
    print("📲 Telegram pe message nahi gaya. Bot chalta rahe ga")
    return False

def calculate_atr(df, period=14):
    high_low = df['high'] - df['low']
    high_close = abs(df['high'] - df['close'].shift())
    low_close = abs(df['low'] - df['close'].shift())
    ranges = pd.concat([high_low, high_close, low_close], axis=1)
    true_range = ranges.max(axis=1)
    atr = true_range.rolling(period).mean()
    return atr

def calculate_rsi(df, period=14):
    delta = df['close'].diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(span=period, adjust=False).mean()
    avg_loss = loss.ewm(span=period, adjust=False).mean()
    rs = avg_gain / avg_loss
    rsi = 100 - (100 / (1 + rs))
    return rsi

def get_gold_data():
    url = "https://contract.mexc.com/api/v1/contract/kline/XAUT_USDT?interval=Min15&limit=200"
    headers = {'User-Agent': 'Mozilla/5.0'}
    try:
        response = requests.get(url, headers=headers, timeout=15)
        data = response.json()
        if data.get('success')!= True: return None
        df = pd.DataFrame(data['data'], columns=['time','open','close','high','low','vol','amount'])
        df['time'] = pd.to_datetime(df['time'], unit='ms')
        df = df.sort_values('time').reset_index(drop=True)
        for col in ['close','high','low','open']: df[col] = pd.to_numeric(df[col])
        return df
    except Exception as e:
        print(f"Net ka masla: {e}")
        return None

def check_signal():
    df = get_gold_data()
    if df is None or df.empty:
        send_telegram_alert("⚠️ Bot Alive\nData nahi mila. Next check: 1 ghante baad")
        print("Data nahi mila")
        return

    df['EMA20'] = df['close'].ewm(span=20, adjust=False).mean()
    df['EMA50'] = df['close'].ewm(span=50, adjust=False).mean()
    df['ATR'] = calculate_atr(df)
    df['RSI'] = calculate_rsi(df)
    df = df.dropna()
    if len(df) < 2: return

    last, prev = df.iloc[-1], df.iloc[-2]
    last_close, last_ema20, last_ema50 = last['close'], last['EMA20'], last['EMA50']
    last_atr, last_rsi = last['ATR'], last['RSI']
    prev_ema20, prev_ema50 = prev['EMA20'], prev['EMA50']

    print(f"\n{'='*48}")
    print(f"Time : {datetime.now().strftime('%H:%M:%S')}")
    print(f"Price : ${last_close}")
    print(f"EMA20: {round(last_ema20,2)} | EMA50: {round(last_ema50,2)} | ATR: {round(last_atr,2)}")
    print(f"RSI : {round(last_rsi, 1)}")

    signal = "WAIT"
    atr_ok = last_atr > ATR_MIN
    ema_cross_up = prev_ema20 <= prev_ema50 and last_ema20 > last_ema50
    ema_bull_trend = last_ema20 > last_ema50 and last_close > last_ema20
    rsi_ok_long = 35 < last_rsi < 68
    ema_cross_down = prev_ema20 >= prev_ema50 and last_ema20 < last_ema50
    ema_bear_trend = last_ema20 < last_ema50 and last_close < last_ema20
    rsi_ok_short = 32 < last_rsi < 65

    if not atr_ok: reason = f"ATR {round(last_atr,2)} hai — slow market"
    elif ema_cross_up and rsi_ok_long:
        signal, reason = "LONG", "EMA20 ne EMA50 ko cross kiya upar!"
    elif ema_bull_trend and rsi_ok_long and last_rsi < 55:
        signal, reason = "LONG", "Uptrend chal raha hai"
    elif ema_cross_down and rsi_ok_short:
        signal, reason = "SHORT", "EMA20 ne EMA50 ko cross kiya neeche!"
    elif ema_bear_trend and rsi_ok_short and last_rsi > 45:
        signal, reason = "SHORT", "Downtrend chal raha hai"
    else: reason = "Market sideways hai. Wait karo."

    if signal == "LONG":
        entry = last_close
        stop_loss = round(entry - (last_atr * 1.5), 2)
        take_profit = round(entry + (last_atr * 3), 2)
        if entry!= stop_loss:
            risk_amount = ACCOUNT_BALANCE * (RISK_PERCENT / 100)
            pos_size = risk_amount / abs(entry - stop_loss)
            telegram_msg = f"🚀 <b>XAUT/USDT BUY SIGNAL</b> 🟢\n\n<b>Entry:</b> ${round(entry, 2)}\n<b>Stop Loss:</b> ${stop_loss}\n<b>Take Profit:</b> ${take_profit}\n<b>R:R:</b> 1 : 2.0\n\n<b>ATR:</b> {round(last_atr, 2)} | <b>RSI:</b> {round(last_rsi, 1)}\n\n<i>{reason}</i>"
            send_telegram_alert(telegram_msg)
    elif signal == "SHORT":
        entry = last_close
        stop_loss = round(entry + (last_atr * 1.5), 2)
        take_profit = round(entry - (last_atr * 3), 2)
        if entry!= stop_loss:
            risk_amount = ACCOUNT_BALANCE * (RISK_PERCENT / 100)
            pos_size = risk_amount / abs(stop_loss - entry)
            telegram_msg = f"📉 <b>XAUT/USDT SELL SIGNAL</b> 🔴\n\n<b>Entry:</b> ${round(entry, 2)}\n<b>Stop Loss:</b> ${stop_loss}\n<b>Take Profit:</b> ${take_profit}\n<b>R:R:</b> 1 : 2.0\n<b>ATR:</b> {round(last_atr, 2)} | <b>RSI:</b> {round(last_rsi, 1)}\n\n<i>{reason}</i>"
            send_telegram_alert(telegram_msg)
    else:
        alive_msg = f"✅ <b>Bot Alive</b>\n\n⏳ SIGNAL : WAIT 🟡\n<b>Reason:</b> {reason}\n<b>Price:</b> ${round(last_close,2)}\n<b>ATR:</b> {round(last_atr,2)} | <b>RSI:</b> {round(last_rsi,1)}\n\nNext check: 1 ghante baad"
        send_telegram_alert(alive_msg)
        print(f"\n⏳ SIGNAL : WAIT 🟡 - {reason}")
    print(f"{'='*48}")

def bot_loop():
    send_telegram_alert("✅ <b>Gold Signal Bot Started</b>\n\n⏰ Har 1 ghante baad market check ho ga\n📊 Timeframe: 15 Min")
    while True:
        try:
            check_signal()
            print(f"Agla check 1 ghante baad... {datetime.now().strftime('%H:%M:%S')}")
            time.sleep(CHECK_INTERVAL)
        except Exception as e:
            print(f"Error: {e}")
            send_telegram_alert(f"⚠️ Bot Error: {e}\n5 min me restart ho raha...")
            time.sleep(300)

@app.route('/')
def home():
    return "Bot is alive and checking XAUT/USDT every 1 hour ✅"

if __name__ == "__main__":
    threading.Thread(target=bot_loop, daemon=True).start()
    app.run(host="0.0.0.0", port=int(os.environ.get("PORT", 10000)))