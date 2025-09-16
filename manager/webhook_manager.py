import httpx
from shared_resources import WEBHOOK_URL, WEBHOOK_ERROR_URL

async def send_webhook(message):
    # 일반적인 내용 전송
    payload = {
        'content': message
    }
    headers={
        "Content-Type": "application/json"
    }
    try:
        async with httpx.AsyncClient() as client:
            await client.post(WEBHOOK_URL, json=payload, headers=headers)
    except Exception as e:
        print("웹훅 전송 중 오류 발생")

async def send_error_webhook(message):
    # 오류 전송
    message= f"⚠️{message}"
    payload = {
        'content': message
    }
    headers={
        "Content-Type": "application/json"
    }
    try:
        async with httpx.AsyncClient() as client:
            await client.post(WEBHOOK_ERROR_URL, json=payload, headers=headers)
    except Exception as e:
        print("웹훅 전송 중 오류 발생")