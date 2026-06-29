from fastapi import FastAPI, Depends, HTTPException, Header
from fastapi.middleware.cors import CORSMiddleware
from sqlmodel import SQLModel, Session, select, create_engine, Field
from pydantic import BaseModel
from typing import Optional, List
from datetime import datetime
import hmac
import hashlib
import json
from urllib.parse import parse_qs
import uvicorn
import asyncio

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import WebAppInfo, InlineKeyboardMarkup, InlineKeyboardButton

# ==================== КОНФИГ ====================
BOT_TOKEN = "8735697736:AAFZ52Ed0V5RZ3mwC4LqbRLFpQLY4oHJgUU"  # <-- ТВОЙ ТОКЕН
DB_PATH = "botdelixor.db"

# URL Mini App на GitHub Pages (замени после деплоя!)
WEBAPP_URL = "https://arseniy52610.github.io/DelixorMiniApp/"

# ==================== БАЗА ДАННЫХ ====================
class ChatMessage(SQLModel, table=True):
    __tablename__ = "chatmessage"
    id: Optional[int] = Field(default=None, primary_key=True)
    unique_chat_id: str
    message_id: int
    from_user_id: int
    from_username: Optional[str]
    from_name: str
    content: Optional[str]
    content_type: str
    file_id: Optional[str]
    caption: Optional[str]
    media_uid: Optional[str]
    is_deleted: bool = False
    edited_at: Optional[datetime] = None
    created_at: datetime

class Subscription(SQLModel, table=True):
    __tablename__ = "subscription"
    id: Optional[int] = Field(default=None, primary_key=True)
    user_id: int
    plan: str
    expires_at: Optional[datetime] = None
    is_active: bool = False

engine = create_engine(f"sqlite:///{DB_PATH}", connect_args={"check_same_thread": False})
SQLModel.metadata.create_all(engine)

def get_session():
    with Session(engine) as session:
        yield session

# ==================== БОТ ====================
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Открыть Mini App", web_app=WebAppInfo(url=WEBAPP_URL))]
    ])
    await message.answer(
        f"Привет, {message.from_user.first_name}!\n\n"
        "Я DelixorMod Bot - твой помощник.\n\n"
        "Нажми на кнопку ниже чтобы открыть Mini App 👇",
        reply_markup=keyboard
    )

@dp.message(Command("menu"))
async def cmd_menu(message: types.Message):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📱 Открыть меню", web_app=WebAppInfo(url=WEBAPP_URL))]
    ])
    await message.answer("Открываю меню...", reply_markup=keyboard)

@dp.message()
async def save_message(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or ""
    first_name = message.from_user.first_name or ""
    
    content_type = "text"
    content = message.text or ""
    file_id = None
    
    if message.photo:
        content_type = "photo"
        file_id = message.photo[-1].file_id
        content = message.caption or ""
    elif message.video:
        content_type = "video"
        file_id = message.video.file_id
        content = message.caption or ""
    elif message.document:
        content_type = "document"
        file_id = message.document.file_id
        content = message.caption or ""
    elif message.voice:
        content_type = "voice"
        file_id = message.voice.file_id
    elif message.audio:
        content_type = "audio"
        file_id = message.audio.file_id
        content = message.caption or ""
    elif message.sticker:
        content_type = "sticker"
        file_id = message.sticker.file_id
    elif message.animation:
        content_type = "animation"
        file_id = message.animation.file_id
    
    unique_chat_id = f"{user_id}_bot"
    
    with Session(engine) as session:
        chat_message = ChatMessage(
            unique_chat_id=unique_chat_id,
            message_id=message.message_id,
            from_user_id=user_id,
            from_username=username,
            from_name=first_name,
            content=content,
            content_type=content_type,
            file_id=file_id,
            caption=content if content_type in ["photo", "video", "document", "audio"] else None,
            media_uid=None,
            is_deleted=False,
            created_at=datetime.now()
        )
        session.add(chat_message)
        session.commit()
    
    if content_type == "text":
        await message.answer(f"Получил твое сообщение: {content[:50]}...")

# ==================== AUTH ====================
def validate_telegram_init_data(init_data: str) -> dict:
    if not init_data:
        raise HTTPException(status_code=401, detail="No init data")
    parsed = parse_qs(init_data)
    received_hash = parsed.get("hash", [None])[0]
    if not received_hash:
        raise HTTPException(status_code=401, detail="No hash")
    
    items = []
    for key, value in parsed.items():
        if key != "hash":
            items.append(f"{key}={value[0]}")
    items.sort()
    data_check_string = "\n".join(items)
    
    secret_key = hmac.new(b"WebAppData", BOT_TOKEN.encode(), hashlib.sha256).digest()
    calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
    
    if calculated_hash != received_hash:
        raise HTTPException(status_code=401, detail="Invalid signature")
    
    return json.loads(parsed.get("user", ["{}"])[0])

def get_current_user(authorization: str = Header(...)) -> dict:
    if not authorization.startswith("tma "):
        raise HTTPException(status_code=401, detail="Invalid auth")
    return validate_telegram_init_data(authorization[4:])

# ==================== MODELS ====================
class UserResponse(BaseModel):
    telegram_id: int
    username: Optional[str]
    first_name: str
    avatar_url: Optional[str]
    is_premium: bool
    total_messages: int

class ChatListItem(BaseModel):
    unique_chat_id: str
    peer_name: str
    peer_username: Optional[str]
    last_message: str
    last_message_time: datetime
    unread_count: int = 0

class MessageItem(BaseModel):
    message_id: int
    from_user_id: int
    from_name: str
    content: str
    content_type: str
    file_id: Optional[str]
    created_at: datetime
    is_deleted: bool
    edited_at: Optional[datetime]

class SubscriptionResponse(BaseModel):
    is_active: bool
    plan: str
    expires_at: Optional[str]
    days_left: Optional[int]

class Settings(BaseModel):
    theme: str = "dark"
    notifications: bool = True
    language: str = "ru"

# ==================== FASTAPI ====================
app = FastAPI()
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

_settings_store = {}

@app.get("/api/user", response_model=UserResponse)
def get_user(tg_user: dict = Depends(get_current_user), session: Session = Depends(get_session)):
    telegram_id = tg_user["id"]
    messages = session.exec(select(ChatMessage).where(ChatMessage.from_user_id == telegram_id)).all()
    return UserResponse(
        telegram_id=telegram_id,
        username=tg_user.get("username"),
        first_name=tg_user.get("first_name", ""),
        avatar_url=f"https://t.me/i/userpic/320/{tg_user.get('username', '')}.jpg",
        is_premium=tg_user.get("is_premium", False),
        total_messages=len(messages),
    )

@app.get("/api/subscription", response_model=SubscriptionResponse)
def get_subscription(tg_user: dict = Depends(get_current_user), session: Session = Depends(get_session)):
    sub = session.exec(select(Subscription).where(Subscription.user_id == tg_user["id"]).where(Subscription.is_active == True)).first()
    if sub and sub.expires_at:
        days_left = (sub.expires_at - datetime.now()).days
        return SubscriptionResponse(is_active=True, plan=sub.plan, expires_at=sub.expires_at.isoformat(), days_left=max(0, days_left))
    return SubscriptionResponse(is_active=False, plan="free", expires_at=None, days_left=None)

@app.get("/api/chats", response_model=List[ChatListItem])
def list_chats(tg_user: dict = Depends(get_current_user), session: Session = Depends(get_session)):
    user_id = str(tg_user["id"])
    messages = session.exec(
        select(ChatMessage).where(
            (ChatMessage.unique_chat_id.like(f"{user_id}_%")) | (ChatMessage.unique_chat_id.like(f"%_{user_id}"))
        ).order_by(ChatMessage.created_at.desc())
    ).all()
    
    chats = {}
    for msg in messages:
        cid = msg.unique_chat_id
        if cid not in chats:
            parts = cid.split("_")
            peer_id = parts[1] if parts[0] == user_id else parts[0]
            chats[cid] = {"unique_chat_id": cid, "peer_name": msg.from_name, "peer_username": msg.from_username, "messages": []}
        chats[cid]["messages"].append(msg)
    
    result = []
    for cid, data in chats.items():
        last_msg = data["messages"][0]
        result.append(ChatListItem(
            unique_chat_id=cid, peer_name=data["peer_name"], peer_username=data["peer_username"],
            last_message=last_msg.content or f"[{last_msg.content_type}]", last_message_time=last_msg.created_at
        ))
    return result

@app.get("/api/chat/{unique_chat_id}", response_model=List[MessageItem])
def get_chat_history(unique_chat_id: str, tg_user: dict = Depends(get_current_user), session: Session = Depends(get_session)):
    user_id = str(tg_user["id"])
    if user_id not in unique_chat_id.split("_"):
        return []
    messages = session.exec(select(ChatMessage).where(ChatMessage.unique_chat_id == unique_chat_id).order_by(ChatMessage.created_at.asc())).all()
    return [MessageItem(
        message_id=m.message_id, from_user_id=m.from_user_id, from_name=m.from_name,
        content=m.content or "", content_type=m.content_type, file_id=m.file_id,
        created_at=m.created_at, is_deleted=m.is_deleted, edited_at=m.edited_at
    ) for m in messages]

@app.get("/api/settings", response_model=Settings)
def get_settings(tg_user: dict = Depends(get_current_user)):
    return _settings_store.get(tg_user["id"], Settings())

@app.post("/api/settings", response_model=Settings)
def save_settings(settings: Settings, tg_user: dict = Depends(get_current_user)):
    _settings_store[tg_user["id"]] = settings
    return settings

@app.get("/api/giveaway")
def get_giveaway():
    return {
        "title": "Розыгрыш DelixorMod Plus",
        "description": "3 подписки на месяц",
        "ends_at": "2026-07-31T23:59:59",
        "participants": 142,
        "is_active": True
    }

@app.get("/api/delpn")
def get_delpn():
    return {
        "is_connected": False,
        "status": "Не подключено",
        "description": "DelPN — защищённый VPN",
        "features": ["Шифрование", "Быстрые серверы", "Без логов"],
        "tariff": "299 руб/мес",
        "connect_url": "https://t.me/DelixorModBot"
    }

# ==================== ЗАПУСК ====================
async def start_bot():
    print("Запуск бота...")
    await dp.start_polling(bot)

async def start_server():
    print("Запуск API сервера...")
    config = uvicorn.Config(app, host="0.0.0.0", port=8000, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()

async def main():
    print("=" * 50)
    print("DelixorMod Bot + API")
    print("=" * 50)
    print(f"Mini App URL: {WEBAPP_URL}")
    print("=" * 50)
    await asyncio.gather(start_bot(), start_server())

if __name__ == "__main__":
    asyncio.run(main())
