from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton, KeyboardButton, ReplyKeyboardMarkup
from aiogram.utils.keyboard import InlineKeyboardBuilder


def admin_reply_menu():
    return ReplyKeyboardMarkup(
        keyboard=[
            [KeyboardButton(text="📋 Админ-меню")]
        ],
        resize_keyboard=True,
        input_field_placeholder="Выберите действие..."
    )


# 1. Клавиатура для списка мероприятий
def events_list_kb(events):
    kb = InlineKeyboardBuilder()
    for ev in events:
        kb.row(
            InlineKeyboardButton(
                text=f"📌 {ev.title} ({ev.publish_at:%d.%m %H:%M})",
                callback_data=f"event:{ev.id}"
            )
        )
    return kb.as_markup()


# 2. Клавиатура для конкретного мероприятия
def event_actions_kb(event_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="✏️ Редактировать", callback_data=f"edit:{event_id}"),
            InlineKeyboardButton(text="❌ Удалить", callback_data=f"delete:{event_id}")
        ]
    ])


def edit_menu_kb(event_id: int):
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✏️ Название", callback_data=f"edit_field:title:{event_id}")],
        [InlineKeyboardButton(text="🕒 Дата/время", callback_data=f"edit_field:publish_at:{event_id}")],
        [InlineKeyboardButton(text="💬 Напоминание", callback_data=f"edit_field:reminder_text:{event_id}")],
        [InlineKeyboardButton(text="⬅️ Назад", callback_data=f"event:{event_id}")]
    ])


def admin_main_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Рассылка сообщений", callback_data="admin:broadcast")],
        [InlineKeyboardButton(text="➕ Создать мероприятие", callback_data="admin:create_event")],
        [InlineKeyboardButton(text="📋 Мои мероприятия", callback_data="admin:my_events")],
    ])


def broadcast_mail_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Отправить сейчас", callback_data="broadcast:now")],
        [InlineKeyboardButton(text="Запланировать", callback_data="broadcast:schedule")],
        [InlineKeyboardButton(text="⬅️ Вернуться в главное меню", callback_data="admin:menu")]
    ])


def back_to_main_menu():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="⬅️ Вернуться в главное меню", callback_data="admin:menu")]
    ])
