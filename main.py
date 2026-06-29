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
from fastapi.responses import HTMLResponse
import asyncio

# AIOPGRAM ИМПОРТЫ
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import WebAppInfo, InlineKeyboardMarkup, InlineKeyboardButton

# ==================== КОНФИГ ====================
BOT_TOKEN = "8735697736:AAFZ52Ed0V5RZ3mwC4LqbRLFpQLY4oHJgUU"  # <-- ТВОЙ ТОКЕН
DB_PATH = "botdelixor.db"

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

# ==================== AIOPGRAM БОТ ====================
bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# Обработчик команды /start
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🚀 Открыть Mini App", web_app=WebAppInfo(url="https://arseniy52610.github.io/DelixorMiniApp/"))]
    ])
    await message.answer(
        f"Привет, {message.from_user.first_name}!\n\n"
        "Я DelixorMod Bot - твой помощник.\n\n"
        "Нажми на кнопку ниже чтобы открыть Mini App 👇",
        reply_markup=keyboard
    )

# Обработчик команды /menu
@dp.message(Command("menu"))
async def cmd_menu(message: types.Message):
    keyboard = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📱 Открыть меню", web_app=WebAppInfo(url="https://arseniy52610.github.io/DelixorMiniApp/"))]
    ])
    await message.answer("Открываю меню...", reply_markup=keyboard)

# Сохранение всех сообщений в БД (твой существующий функционал)
@dp.message()
async def save_message(message: types.Message):
    user_id = message.from_user.id
    username = message.from_user.username or ""
    first_name = message.from_user.first_name or ""
    
    # Определяем тип контента
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
    
    # Создаем unique_chat_id (для личных сообщений с ботом)
    unique_chat_id = f"{user_id}_bot"
    
    # Сохраняем в БД
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
    
    # Ответ бота (можешь добавить свою логику)
    if content_type == "text":
        # Здесь твоя логика ответов
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

# ==================== FRONTEND (HTML) ====================
HTML = '''<!DOCTYPE html>
<html lang="ru">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <meta name="theme-color" content="#0A0F1F">
    <title>DelixorMod</title>
    <script src="https://telegram.org/js/telegram-web-app.js"></script>
    <script src="https://cdn.tailwindcss.com"></script>
    <script src="https://unpkg.com/react@18/umd/react.production.min.js" crossorigin></script>
    <script src="https://unpkg.com/react-dom@18/umd/react-dom.production.min.js" crossorigin></script>
    <script src="https://unpkg.com/@babel/standalone/babel.min.js"></script>
    <style>
        * { -webkit-tap-highlight-color: transparent; }
        body { margin: 0; padding: 0; background: #0A0F1F; color: white; font-family: -apple-system, BlinkMacSystemFont, sans-serif; overflow: hidden; }
        body::before { content: ''; position: fixed; inset: 0; background: radial-gradient(circle at 20% 0%, rgba(61, 90, 254, 0.25), transparent 50%), radial-gradient(circle at 80% 100%, rgba(168, 85, 247, 0.25), transparent 50%); pointer-events: none; }
        .glass { background: rgba(255,255,255,0.05); backdrop-filter: blur(24px); border: 1px solid rgba(255,255,255,0.08); border-radius: 28px; }
        .glass-strong { background: rgba(16,25,46,0.7); backdrop-filter: blur(40px); border: 1px solid rgba(255,255,255,0.1); }
        .gradient-bg { background: linear-gradient(135deg, #3D5AFE 0%, #7C4DFF 50%, #A855F7 100%); }
        .gradient-text { background: linear-gradient(135deg, #3D5AFE 0%, #7C4DFF 50%, #A855F7 100%); -webkit-background-clip: text; -webkit-text-fill-color: transparent; }
        .neon-glow { box-shadow: 0 0 20px rgba(124,77,255,0.4); }
        ::-webkit-scrollbar { display: none; }
    </style>
</head>
<body>
    <div id="root"></div>
    <script type="text/babel">
        const { useState, useEffect } = React;
        const API_BASE = window.location.origin;
        
        async function request(endpoint, options = {}) {
            const tg = window.Telegram && window.Telegram.WebApp;
            const res = await fetch(API_BASE + endpoint, {
                ...options,
                headers: { 'Content-Type': 'application/json', 'Authorization': 'tma ' + (tg && tg.initData ? tg.initData : ''), ...options.headers }
            });
            if (!res.ok) throw new Error('API error: ' + res.status);
            return res.json();
        }
        
        const api = {
            user: { get: () => request('/api/user') },
            subscription: { get: () => request('/api/subscription') },
            chats: { list: () => request('/api/chats'), getHistory: (id) => request('/api/chat/' + encodeURIComponent(id)) },
            settings: { get: () => request('/api/settings'), save: (data) => request('/api/settings', { method: 'POST', body: JSON.stringify(data) }) },
            giveaway: { get: () => request('/api/giveaway') },
            delpn: { get: () => request('/api/delpn') }
        };
        
        function BottomNav({ page, setPage }) {
            const tabs = [
                { id: 'menu', icon: '🏠', label: 'Меню' },
                { id: 'chats', icon: '💬', label: 'Чаты' },
                { id: 'delpn', icon: '🛡️', label: 'DelPN' },
                { id: 'settings', icon: '⚙️', label: 'Настройки' }
            ];
            return React.createElement('nav', { className: 'fixed bottom-0 left-0 right-0 px-4 pb-5 pt-2 z-50' },
                React.createElement('div', { className: 'glass-strong rounded-[28px] px-2 py-2 flex justify-around items-center neon-glow' },
                    tabs.map(tab => React.createElement('button', {
                        key: tab.id,
                        onClick: () => setPage(tab.id),
                        className: 'flex flex-col items-center px-4 py-2'
                    },
                        React.createElement('span', { className: 'text-2xl' }, tab.icon),
                        React.createElement('span', { className: 'text-[10px] mt-1 ' + (page === tab.id ? 'text-white' : 'text-white/50') }, tab.label)
                    ))
                )
            );
        }
        
        function MenuPage() {
            const [user, setUser] = useState(null);
            const [sub, setSub] = useState(null);
            useEffect(() => {
                api.user.get().then(setUser).catch(() => {});
                api.subscription.get().then(setSub).catch(() => {});
            }, []);
            const tg = window.Telegram && window.Telegram.WebApp && window.Telegram.WebApp.initDataUnsafe && window.Telegram.WebApp.initDataUnsafe.user || {};
            const name = tg.first_name || user && user.first_name || 'Гость';
            const username = tg.username || user && user.username;
            return React.createElement('div', { className: 'px-4 pt-6 space-y-4' },
                React.createElement('div', { className: 'glass p-5 flex items-center gap-4' },
                    React.createElement('div', { className: 'w-16 h-16 rounded-full gradient-bg flex items-center justify-center text-2xl font-bold' }, name.charAt(0)),
                    React.createElement('div', null,
                        React.createElement('div', { className: 'text-xl font-semibold' }, name),
                        React.createElement('div', { className: 'text-sm text-white/50' }, '@' + (username || 'username'))
                    )
                ),
                React.createElement('div', { className: (sub && sub.is_active ? 'gradient-bg' : 'glass') + ' p-4 rounded-[28px] flex items-center gap-3' },
                    React.createElement('div', { className: 'w-10 h-10 rounded-full flex items-center justify-center ' + (sub && sub.is_active ? 'bg-white/20' : 'bg-red-500/20') },
                        sub && sub.is_active ? '✓' : '✕'
                    ),
                    React.createElement('div', null,
                        React.createElement('div', { className: 'font-semibold' }, sub && sub.is_active ? 'DelixorMod Plus активна' : 'Подписка неактивна'),
                        React.createElement('div', { className: 'text-xs text-white/60' }, sub && sub.is_active && sub.days_left ? 'Осталось ' + sub.days_left + ' дней' : 'Получите доступ ко всем функциям')
                    )
                ),
                React.createElement('div', { className: 'grid grid-cols-2 gap-3' },
                    React.createElement('div', { className: 'glass p-5' }, React.createElement('div', { className: 'text-[#3D5AFE] text-2xl mb-2' }, '📖'), React.createElement('div', { className: 'font-semibold' }, 'Инструкция')),
                    React.createElement('div', { className: 'glass p-5' }, React.createElement('div', { className: 'text-[#7C4DFF] text-2xl mb-2' }, '✨'), React.createElement('div', { className: 'font-semibold' }, 'Возможности'))
                ),
                React.createElement('div', { className: 'glass gradient-bg p-5' },
                    React.createElement('div', { className: 'text-lg font-bold' }, 'DelixorMod Plus'),
                    React.createElement('div', { className: 'text-sm opacity-80' }, 'Премиум подписка')
                ),
                React.createElement('div', { className: 'glass p-5 flex items-center gap-3' },
                    React.createElement('div', { className: 'text-2xl' }, '🎁'),
                    React.createElement('div', { className: 'flex-1' },
                        React.createElement('div', { className: 'font-semibold' }, 'Розыгрыш'),
                        React.createElement('div', { className: 'text-xs text-white/60' }, '142 участника')
                    )
                ),
                React.createElement('div', { className: 'grid grid-cols-2 gap-3' },
                    React.createElement('div', { className: 'glass p-5' }, React.createElement('div', { className: 'text-[#A855F7] text-2xl mb-2' }, '🎧'), React.createElement('div', { className: 'font-semibold' }, 'Поддержка')),
                    React.createElement('div', { className: 'glass p-5' }, React.createElement('div', { className: 'text-[#3D5AFE] text-2xl mb-2' }, '📻'), React.createElement('div', { className: 'font-semibold' }, 'Канал'))
                ),
                React.createElement('div', { className: 'glass p-5 flex items-center gap-3' },
                    React.createElement('div', { className: 'text-2xl' }, '🌙'),
                    React.createElement('div', { className: 'flex-1' },
                        React.createElement('div', { className: 'font-semibold' }, 'DelixorMod DarkMode'),
                        React.createElement('div', { className: 'text-xs text-white/60' }, 'Тёмная тема')
                    )
                )
            );
        }
        
        function ChatsPage() {
            const [chats, setChats] = useState([]);
            const [selectedChat, setSelectedChat] = useState(null);
            const [messages, setMessages] = useState([]);
            useEffect(() => {
                api.chats.list().then(setChats).catch(() => {});
            }, []);
            useEffect(() => {
                if (selectedChat) api.chats.getHistory(selectedChat).then(setMessages).catch(() => {});
            }, [selectedChat]);
            
            if (selectedChat) {
                const peerName = messages[0] && messages[0].from_name || 'Чат';
                const tg = window.Telegram && window.Telegram.WebApp && window.Telegram.WebApp.initDataUnsafe && window.Telegram.WebApp.initDataUnsafe.user || {};
                return React.createElement('div', { className: 'h-full flex flex-col' },
                    React.createElement('div', { className: 'glass-strong px-4 py-3 flex items-center gap-3 sticky top-0 z-20' },
                        React.createElement('button', { onClick: () => setSelectedChat(null), className: 'p-1' }, '←'),
                        React.createElement('div', { className: 'w-10 h-10 rounded-full gradient-bg flex items-center justify-center font-bold' }, peerName.charAt(0)),
                        React.createElement('div', { className: 'flex-1' },
                            React.createElement('div', { className: 'font-semibold' }, peerName),
                            React.createElement('div', { className: 'text-xs text-white/50' }, messages.length + ' сообщений')
                        )
                    ),
                    React.createElement('div', { className: 'flex-1 overflow-y-auto px-4 py-4 space-y-2' },
                        messages.map(msg => React.createElement('div', {
                            key: msg.message_id,
                            className: 'flex ' + (msg.from_user_id === tg.id ? 'justify-end' : 'justify-start')
                        },
                            React.createElement('div', {
                                className: 'max-w-[75%] px-4 py-2.5 rounded-[22px] text-sm ' + (msg.from_user_id === tg.id ? 'gradient-bg' : 'glass')
                            },
                                msg.content || '[' + msg.content_type + ']',
                                React.createElement('div', { className: 'text-[10px] mt-1 opacity-60' },
                                    new Date(msg.created_at).toLocaleTimeString('ru', {hour:'2-digit',minute:'2-digit'})
                                )
                            )
                        ))
                    )
                );
            }
            
            return React.createElement('div', { className: 'px-4 pt-6' },
                React.createElement('h1', { className: 'text-3xl font-bold mb-4 gradient-text' }, 'Чаты'),
                React.createElement('div', { className: 'space-y-2' },
                    chats.map(chat => React.createElement('div', {
                        key: chat.unique_chat_id,
                        onClick: () => setSelectedChat(chat.unique_chat_id),
                        className: 'glass p-4 flex items-center gap-3 cursor-pointer'
                    },
                        React.createElement('div', { className: 'w-12 h-12 rounded-full gradient-bg flex items-center justify-center font-bold' }, chat.peer_name.charAt(0)),
                        React.createElement('div', { className: 'flex-1 min-w-0' },
                            React.createElement('div', { className: 'font-semibold truncate' }, chat.peer_name),
                            React.createElement('div', { className: 'text-sm text-white/60 truncate' }, chat.last_message)
                        )
                    ))
                )
            );
        }
        
        function SettingsPage() {
            const [settings, setSettings] = useState({ theme: 'dark', notifications: true, language: 'ru' });
            useEffect(() => { api.settings.get().then(setSettings).catch(() => {}); }, []);
            const update = (patch) => { const next = {...settings, ...patch}; setSettings(next); api.settings.save(next).catch(() => {}); };
            return React.createElement('div', { className: 'px-4 pt-6 space-y-4' },
                React.createElement('h1', { className: 'text-3xl font-bold gradient-text' }, 'Настройки'),
                React.createElement('div', { className: 'glass p-5' },
                    React.createElement('div', { className: 'text-sm text-white/60 mb-3' }, 'Тема'),
                    React.createElement('div', { className: 'grid grid-cols-2 gap-2' },
                        React.createElement('button', { onClick: () => update({theme:'dark'}), className: 'py-3 rounded-2xl ' + (settings.theme==='dark'?'gradient-bg':'bg-white/5') }, 'Тёмная'),
                        React.createElement('button', { onClick: () => update({theme:'light'}), className: 'py-3 rounded-2xl ' + (settings.theme==='light'?'gradient-bg':'bg-white/5') }, 'Светлая')
                    )
                ),
                React.createElement('div', { className: 'glass p-5 flex items-center justify-between' },
                    React.createElement('span', null, 'Уведомления'),
                    React.createElement('button', {
                        onClick: () => update({notifications:!settings.notifications}),
                        className: 'w-12 h-7 rounded-full relative ' + (settings.notifications?'gradient-bg':'bg-white/10')
                    }, React.createElement('div', { className: 'absolute top-0.5 w-6 h-6 rounded-full bg-white transition-all ' + (settings.notifications?'left-5':'left-0.5') }))
                ),
                React.createElement('div', { className: 'glass p-5', onClick: () => { if(confirm('Очистить историю?')) alert('История очищена'); } },
                    React.createElement('div', { className: 'text-red-400' }, 'Очистить историю чатов')
                )
            );
        }
        
        function DelPNPage() {
            const [data, setData] = useState(null);
            useEffect(() => { api.delpn.get().then(setData).catch(() => {}); }, []);
            return React.createElement('div', { className: 'px-4 pt-6 space-y-4' },
                React.createElement('div', { className: 'glass p-6 relative overflow-hidden' },
                    React.createElement('div', { className: 'relative' },
                        React.createElement('div', { className: 'w-16 h-16 rounded-3xl gradient-bg flex items-center justify-center mb-4 neon-glow text-3xl' }, '🛡️'),
                        React.createElement('h1', { className: 'text-3xl font-bold gradient-text' }, 'DelPN'),
                        React.createElement('p', { className: 'text-white/70 mt-2' }, data && data.description || 'Защищённый VPN'),
                        React.createElement('div', { className: 'mt-4 inline-flex items-center gap-2 px-3 py-1.5 rounded-full text-sm ' + (data && data.is_connected?'bg-green-500/20 text-green-400':'bg-white/10') },
                            React.createElement('div', { className: 'w-2 h-2 rounded-full ' + (data && data.is_connected?'bg-green-400':'bg-white/40') }),
                            React.createElement('span', null, data && data.status || 'Не подключено')
                        )
                    )
                ),
                React.createElement('div', { className: 'glass p-5' },
                    React.createElement('div', { className: 'text-sm text-white/60 mb-3' }, 'Возможности'),
                    React.createElement('div', { className: 'space-y-2' },
                        data && data.features && data.features.map((f,i) => React.createElement('div', { key: i, className: 'flex items-center gap-2' },
                            React.createElement('div', { className: 'w-5 h-5 rounded-full gradient-bg flex items-center justify-center text-xs' }, '✓'),
                            React.createElement('span', { className: 'text-sm' }, f)
                        ))
                    )
                ),
                React.createElement('div', { className: 'glass gradient-bg p-5 flex items-center justify-between' },
                    React.createElement('div', null,
                        React.createElement('div', { className: 'text-xs opacity-80' }, 'Тариф'),
                        React.createElement('div', { className: 'text-2xl font-bold' }, data && data.tariff || '299 руб/мес')
                    ),
                    React.createElement('button', {
                        onClick: () => { if(data && data.connect_url) window.open(data.connect_url); },
                        className: 'bg-white text-[#7C4DFF] px-6 py-3 rounded-2xl font-semibold'
                    }, 'Подключить')
                )
            );
        }
        
        function App() {
            const [page, setPage] = useState('menu');
            useEffect(() => {
                if (window.Telegram && window.Telegram.WebApp) {
                    window.Telegram.WebApp.ready();
                    window.Telegram.WebApp.expand();
                }
            }, []);
            return React.createElement('div', { className: 'h-full w-full overflow-hidden relative' },
                React.createElement('main', { className: 'h-full w-full overflow-y-auto pb-24' },
                    page === 'menu' && React.createElement(MenuPage),
                    page === 'chats' && React.createElement(ChatsPage),
                    page === 'settings' && React.createElement(SettingsPage),
                    page === 'delpn' && React.createElement(DelPNPage)
                ),
                React.createElement(BottomNav, { page: page, setPage: setPage })
            );
        }
        
        ReactDOM.createRoot(document.getElementById('root')).render(React.createElement(App));
    </script>
</body>
</html>'''

@app.get("/")
def serve_frontend():
    return HTMLResponse(content=HTML)

# ==================== ЗАПУСК ====================
async def start_bot():
    """Запуск бота"""
    await dp.start_polling(bot)

async def start_server():
    """Запуск FastAPI сервера"""
    config = uvicorn.Config(app, host="0.0.0.0", port=8000, log_level="info")
    server = uvicorn.Server(config)
    await server.serve()

async def main():
    """Запуск обоих процессов"""
    import asyncio
    # Запускаем бот и сервер параллельно
    await asyncio.gather(
        start_bot(),
        start_server()
    )

if __name__ == "__main__":
    print("Запуск DelixorMod Bot + Mini App...")
    print("Бот запущен...")
    print("Mini App: https://arseniy52610.github.io/DelixorMiniApp/")
    asyncio.run(main())