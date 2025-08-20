import httpx
from shared_resources import WEBHOOK_ERROR_URL, WEBHOOK_URL

async def send_webhook(msg):
    payload = {
        'content': msg
    }

    headers = {
        "Content-Type": "application/json"
    }

    try:
        async with httpx.AsyncClient() as client:
            await client.post(WEBHOOK_URL, json=payload, headers=headers)
    except Exception as e:
        print("웹훅 전송 중 오류 발생")

async def send_error_webhook(msg):
    msg = f"⚠️{msg}"
    payload = {
        'content': msg
    }
    
    headers = {
        "Content-Type": "application/json"
    }

    try:
        async with httpx.AsyncClient() as client:
            await client.post(WEBHOOK_ERROR_URL, json=payload, headers=headers)
    except Exception as e:
        print("웹혹 전송 중 오류 발생")