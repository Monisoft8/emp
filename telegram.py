import os, requests

def get_bot_token():
    return os.environ.get("8166976337:AAGyF-Hv35S4S5g0C2JA-OUclCjtqn9u7e0")

def send_telegram_message(chat_id: str, text: str):
    token = get_bot_token()
    if not token or not chat_id:
        return False
    url = f"https://api.telegram.org/bot{token}/sendMessage"
    try:
        r = requests.post(url, json={"chat_id": chat_id, "text": text})
        return r.status_code == 200
    except Exception:
        return False

def send_bulk(messages):
    """
    messages = [ (chat_id, text), ... ]
    """
    for chat_id, text in messages:
        send_telegram_message(chat_id, text)