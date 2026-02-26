import os
import sqlite3
from datetime import datetime, timezone

from fastapi import FastAPI, Request
import requests

TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = str(os.getenv("ADMIN_USER_ID", "")).strip()

app = FastAPI()

TELEGRAM_API = f"https://api.telegram.org/bot{TOKEN}"

DB_PATH = "bets.db"


def db():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS bets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            created_at TEXT NOT NULL,
            user_id TEXT NOT NULL,
            match TEXT NOT NULL,
            market TEXT NOT NULL,
            pick TEXT NOT NULL,
            odds REAL NOT NULL,
            stake_pct REAL NOT NULL,
            note TEXT,
            status TEXT NOT NULL DEFAULT 'open'  -- open | win | loss | void
        )
    """)
    conn.commit()
    return conn


@app.get("/")
def home():
    return {"status": "Bot activo"}


@app.post("/webhook")
async def webhook(request: Request):
    data = await request.json()

    if "message" not in data:
        return {"ok": True}

    msg = data["message"]
    chat_id = msg["chat"]["id"]
    user_id = str(msg["from"]["id"])
    text = (msg.get("text") or "").strip()

    # Solo tú
    if user_id != ADMIN_ID:
        return {"status": "No autorizado"}

    if text.startswith("/start"):
        send_message(chat_id,
                     "🤖 Analista Deportivo 1x2 activo.\n\n"
                     "Comandos:\n"
                     "/add Partido | Mercado | Selección | Cuota | Stake% | Nota(opc)\n"
                     "/open (ver apuestas abiertas)\n"
                     "/result ID win|loss|void\n"
                     "/stats (resumen)\n")

    elif text.startswith("/add"):
        payload = text.replace("/add", "", 1).strip()
        parsed = parse_add(payload)
        if not parsed:
            send_message(chat_id,
                         "Formato incorrecto.\n\nEjemplo:\n"
                         "/add Celta vs PAOK | Corners | Over 8.5 | 1.62 | 2.0 | Buen ritmo\n")
            return {"ok": True}

        match, market, pick, odds, stake_pct, note = parsed
        bet_id = insert_bet(user_id, match, market, pick, odds, stake_pct, note)
        send_message(chat_id,
                     f"📌 Apuesta guardada (ID {bet_id})\n"
                     f"Partido: {match}\nMercado: {market}\nSelección: {pick}\n"
                     f"Cuota: {odds}\nStake: {stake_pct}%\n"
                     f"Nota: {note or '-'}")

    elif text.startswith("/open"):
        open_bets = list_open_bets(user_id)
        if not open_bets:
            send_message(chat_id, "No tienes apuestas abiertas.")
        else:
            lines = ["📂 Apuestas abiertas:"]
            for b in open_bets:
                lines.append(
                    f"ID {b['id']} • {b['match']} • {b['market']} • {b['pick']} • {b['odds']} • {b['stake_pct']}%"
                )
            send_message(chat_id, "\n".join(lines))

    elif text.startswith("/result"):
        parts = text.split()
        if len(parts) != 3:
            send_message(chat_id, "Uso: /result ID win|loss|void\nEj: /result 12 win")
            return {"ok": True}

        bet_id = parts[1]
        status = parts[2].lower()
        if status not in ("win", "loss", "void"):
            send_message(chat_id, "Estado inválido. Usa: win, loss o void.")
            return {"ok": True}

        ok = set_result(user_id, bet_id, status)
        if ok:
            send_message(chat_id, f"✅ Resultado actualizado: ID {bet_id} → {status}")
        else:
            send_message(chat_id, f"❌ No encontré una apuesta abierta con ID {bet_id}")

    elif text.startswith("/stats"):
        s = stats(user_id)
        send_message(chat_id,
                     "📊 Estadísticas\n"
                     f"Total: {s['total']} | Abiertas: {s['open']}\n"
                     f"Win: {s['win']} | Loss: {s['loss']} | Void: {s['void']}\n"
                     f"Acierto (sin void): {s['hit_rate']}\n"
                     f"ROI aprox (stake%): {s['roi_pct']}")

    return {"ok": True}


def send_message(chat_id, text):
    requests.post(
        f"{TELEGRAM_API}/sendMessage",
        json={"chat_id": chat_id, "text": text}
    )


def now_iso():
    return datetime.now(timezone.utc).isoformat()


def parse_add(payload: str):
    # Formato: Partido | Mercado | Selección | Cuota | Stake% | Nota(opc)
    if not payload:
        return None
    parts = [p.strip() for p in payload.split("|")]
    if len(parts) < 5:
        return None

    match = parts[0]
    market = parts[1]
    pick = parts[2]

    try:
        odds = float(parts[3].replace(",", "."))
        stake_pct = float(parts[4].replace(",", "."))
    except ValueError:
        return None

    note = parts[5] if len(parts) >= 6 else ""
    return match, market, pick, odds, stake_pct, note


def insert_bet(user_id, match, market, pick, odds, stake_pct, note):
    conn = db()
    cur = conn.cursor()
    cur.execute(
        "INSERT INTO bets (created_at, user_id, match, market, pick, odds, stake_pct, note, status) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'open')",
        (now_iso(), user_id, match, market, pick, odds, stake_pct, note)
    )
    conn.commit()
    bet_id = cur.lastrowid
    conn.close()
    return bet_id


def list_open_bets(user_id):
    conn = db()
    cur = conn.cursor()
    cur.execute(
        "SELECT id, match, market, pick, odds, stake_pct FROM bets WHERE user_id=? AND status='open' ORDER BY id DESC",
        (user_id,)
    )
    rows = cur.fetchall()
    conn.close()
    return [
        {"id": r[0], "match": r[1], "market": r[2], "pick": r[3], "odds": r[4], "stake_pct": r[5]}
        for r in rows
    ]


def set_result(user_id, bet_id, status):
    conn = db()
    cur = conn.cursor()
    cur.execute(
        "UPDATE bets SET status=? WHERE user_id=? AND id=? AND status='open'",
        (status, user_id, bet_id)
    )
    conn.commit()
    updated = cur.rowcount
    conn.close()
    return updated == 1


def stats(user_id):
    conn = db()
    cur = conn.cursor()

    cur.execute("SELECT COUNT(*) FROM bets WHERE user_id=?", (user_id,))
    total = cur.fetchone()[0]

    cur.execute("SELECT COUNT(*) FROM bets WHERE user_id=? AND status='open'", (user_id,))
    open_ = cur.fetchone()[0]

    def count_status(st):
        cur.execute("SELECT COUNT(*) FROM bets WHERE user_id=? AND status=?", (user_id, st))
        return cur.fetchone()[0]

    win = count_status("win")
    loss = count_status("loss")
    void = count_status("void")

    # hit rate (sin void)
    denom = (win + loss)
    hit_rate = f"{(win / denom * 100):.1f}%" if denom > 0 else "-"

    # ROI aproximado con stake% como unidades:
    # win: +stake*(odds-1), loss: -stake, void: 0
    cur.execute("SELECT odds, stake_pct, status FROM bets WHERE user_id=?", (user_id,))
    rows = cur.fetchall()
    profit = 0.0
    staked = 0.0
    for odds, stake_pct, st in rows:
        if st == "open":
            continue
        if st == "void":
            continue
        staked += stake_pct
        if st == "win":
            profit += stake_pct * (odds - 1.0)
        elif st == "loss":
            profit -= stake_pct

    roi_pct = f"{(profit / staked * 100):.1f}%" if staked > 0 else "-"

    conn.close()
    return {
        "total": total,
        "open": open_,
        "win": win,
        "loss": loss,
        "void": void,
        "hit_rate": hit_rate,
        "roi_pct": roi_pct
    }
