from aiogram import Router, F
from aiogram.filters import Command
from aiogram.types import Message, CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from datetime import datetime

from dotenv import load_dotenv
from sqlalchemy import select

from keyboards import event_actions_kb, events_list_kb, edit_menu_kb, admin_main_menu, back_to_main_menu, \
    broadcast_mail_menu
from mailer import Mailer
from models import AsyncSessionLocal, Event
from crud import create_event, save_generated_link, get_event, get_registrations_for_event, get_events_by_owner, \
    delete_event, update_event, get_user_by_tg
from utils import make_deeplink
from scheduler import schedule_event_jobs_for_event
import os
import logging

from bot import bot, scheduler

load_dotenv()
logger = logging.getLogger(__name__)
router = Router()


class CreateEventSG(StatesGroup):
    await_title = State()
    await_publish = State()
    await_reminder_date = State()
    await_reminder_text = State()
    await_confirm_date = State()
    await_confirm_text = State()
    await_category = State()
    confirm = State()


class EditEventSG(StatesGroup):
    await_new_value = State()


class BroadcastSG(StatesGroup):
    await_event_id = State()
    await_text = State()
    await_schedule_choice = State()
    await_schedule_time = State()


@router.message(Command("admin"))
async def cmd_admin_menu(message: Message):
    await message.answer("Админ-меню:", reply_markup=admin_main_menu())


@router.callback_query(F.data == "admin:menu")
async def cq_admin_menu(callback: CallbackQuery):
    await callback.message.edit_text("Админ-меню:", reply_markup=admin_main_menu())


@router.message(F.text == "📋 Админ-меню")
async def show_admin_menu(message: Message):
    await message.answer(
        "Админ-меню:",
        reply_markup=admin_main_menu()
    )


@router.callback_query(F.data == "admin:broadcast")
async def cq_broadcast(callback: CallbackQuery, state: FSMContext):
    await callback.message.answer("Введите ID мероприятия для рассылки:")
    await state.set_state(BroadcastSG.await_event_id)
    await callback.answer()


# Создать мероприятие
@router.callback_query(F.data == "admin:create_event")
async def cq_admin_create_event(callback: CallbackQuery, state: FSMContext):
    await state.set_state(CreateEventSG.await_title)
    await callback.message.edit_text(
        "Введите название нового мероприятия:",
        reply_markup=back_to_main_menu()
    )

# Мои мероприятия
@router.callback_query(F.data == "admin:my_events")
async def cq_admin_my_events(callback: CallbackQuery):
    async with AsyncSessionLocal() as session:
        events = await get_events_by_owner(session, str(callback.from_user.id))

    if not events:
        await callback.message.edit_text(
            "У вас нет мероприятий.",
            reply_markup=admin_main_menu()
        )
        return

    text = "📋 Ваши мероприятия:\n\n"
    kb = []
    for ev in events:
        text += f"• {ev.title} — создан {ev.created_at}\n"
        kb.append([InlineKeyboardButton(text=ev.title, callback_data=f"event:{ev.id}")])

    kb.append([InlineKeyboardButton(text="⬅️ Назад", callback_data="admin:menu")])

    await callback.message.edit_text(text, reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))


@router.message(BroadcastSG.await_event_id)
async def broadcast_get_event(message: Message, state: FSMContext):
    await state.update_data(event_id=message.text.strip())
    await message.answer("Введите текст рассылки:")
    await state.set_state(BroadcastSG.await_text)


@router.message(BroadcastSG.await_text)
async def broadcast_get_text(message: Message, state: FSMContext):
    await state.update_data(text=message.text.strip())
    await message.answer("Когда отправить рассылку?", reply_markup=broadcast_mail_menu())
    await state.set_state(BroadcastSG.await_schedule_choice)


@router.callback_query(F.data == "broadcast:now")
async def broadcast_now(callback: CallbackQuery, state: FSMContext):
    data = await state.get_data()
    event_id = data["event_id"]
    text = data["text"]

    async with AsyncSessionLocal() as session:
        regs = await get_registrations_for_event(session, int(event_id))
        chat_ids = [r.tg_id for r in regs]

    mailer = Mailer(bot, concurrency=8)
    await mailer.send_batch(chat_ids, text)

    await callback.message.edit_text(
        f"✅ Сообщение отправлено ({len(chat_ids)} получателей).",
        reply_markup=admin_main_menu()
    )
    await state.clear()


@router.callback_query(F.data == "broadcast:schedule")
async def broadcast_schedule(callback: CallbackQuery, state: FSMContext):
    await state.set_state(BroadcastSG.await_schedule_time)
    await callback.message.edit_text(
        "Введите дату и время отправки в формате `18:30 25.12.2025`",
        reply_markup=back_to_main_menu()
    )
    await callback.answer()


@router.message(BroadcastSG.await_schedule_time)
async def broadcast_get_time(message: Message, state: FSMContext):
    data = await state.get_data()
    event_id = data["event_id"]
    text = data["text"]

    try:
        dt = datetime.strptime(message.text.strip(), "%H:%M %d.%m.%Y")
    except ValueError:
        await message.answer("❌ Неверный формат. Укажите так: 18:30 25.12.2025")
        return

    async with AsyncSessionLocal() as session:
        regs = await get_registrations_for_event(session, int(event_id))
        chat_ids = [r.tg_id for r in regs]

    mailer = Mailer(bot, concurrency=8)

    # планируем отправку через APScheduler
    scheduler.add_job(
        mailer.send_batch,
        "date",
        run_date=dt,
        args=[chat_ids, text]
    )

    await message.answer(
        f"⏳ Рассылка по мероприятию {event_id} запланирована на {dt.strftime('%d.%m.%Y %H:%M')}",
        reply_markup=admin_main_menu()
    )
    await state.clear()


def parse_dt(text: str):
    try:
        tpart, dpart = text.strip().split()
        return datetime.strptime(f"{dpart} {tpart}", "%d.%m.%Y %H:%M")
    except Exception:
        return None


@router.message(BroadcastSG.await_schedule_time)
async def broadcast_schedule_time(message: Message, state: FSMContext):
    dt = parse_dt(message.text)
    if not dt:
        await message.answer("❌ Неверный формат. Используйте: `18:30 25.12.2025`")
        return

    data = await state.get_data()
    event_id = data["event_id"]
    text = data["text"]

    async with AsyncSessionLocal() as session:
        regs = await get_registrations_for_event(session, event_id)
        chat_ids = [r.tg_id for r in regs]

    mailer = Mailer(bot, concurrency=8)

    # планируем задачу
    scheduler.add_job(
        mailer.send_batch,
        trigger="date",
        run_date=dt,
        args=[chat_ids, text],
        id=f"broadcast_{event_id}_{dt.timestamp()}"
    )

    await message.answer(f"✅ Рассылка запланирована на {dt.strftime('%d.%m.%Y %H:%M')}", reply_markup=admin_main_menu())
    await state.clear()


@router.message(Command(commands=["create_event"]))
async def cmd_create_event(message: Message, state: FSMContext):
    # Проверка роли упрощена: предполагаем, что админами являются пользователи с role == 'event_admin' или super_admin
    tg_id = str(message.from_user.id)
    async with AsyncSessionLocal() as session:
        from crud import get_user_by_tg
        user = await get_user_by_tg(session, tg_id)
        if not user or user.role not in ("event_admin", "super_admin"):
            await message.answer("У вас нет прав администратора мероприятия.")
            return
    await state.set_state(CreateEventSG.await_title)
    await message.answer("Введите заголовок/название мероприятия:")


@router.message(CreateEventSG.await_title)
async def ce_title(message: Message, state: FSMContext):
    text = message.text.strip()
    if not text:
        await message.answer("Заголовок не может быть пустым.")
        return
    await state.update_data(title=text)
    await state.set_state(CreateEventSG.await_publish)
    await message.answer("Введите дату публикации в формате ЧЧ:ММ ДД.ММ.ГГГГ (например 18:30 25.12.2025)")


@router.message(CreateEventSG.await_publish)
async def ce_publish(message: Message, state: FSMContext):
    dt = parse_dt(message.text)
    if not dt:
        await message.answer("Неправильный формат даты. Попробуйте снова в формате ЧЧ:ММ ДД.ММ.ГГГГ.")
        return
    await state.update_data(publish_at=dt)
    await state.set_state(CreateEventSG.await_reminder_date)
    await message.answer("Введите дату напоминания (в том же формате) или напишите 'нет' если не нужно:")


@router.message(CreateEventSG.await_reminder_date)
async def ce_reminder_date(message: Message, state: FSMContext):
    text = message.text.strip().lower()
    if text in ("нет", "no", "skip", "-"):
        await state.update_data(reminder_at=None)
        await state.set_state(CreateEventSG.await_confirm_date)
        await message.answer("Пропущено. Теперь введите дату отправки запроса подтверждения или 'нет':")
        return
    dt = parse_dt(message.text)
    if not dt:
        await message.answer("Неправильный формат даты. Введите снова или 'нет':")
        return
    await state.update_data(reminder_at=dt)
    await state.set_state(CreateEventSG.await_reminder_text)
    await message.answer("Введите текст напоминания (лимит 4096 символов):")


@router.message(CreateEventSG.await_reminder_text)
async def ce_reminder_text(message: Message, state: FSMContext):
    text = message.text.strip()
    if len(text) > 4096:
        await message.answer("Текст слишком длинный.")
        return
    await state.update_data(reminder_text=text)
    await state.set_state(CreateEventSG.await_confirm_date)
    await message.answer("Введите дату отправки запроса подтверждения или 'нет':")


@router.message(CreateEventSG.await_confirm_date)
async def ce_confirm_date(message: Message, state: FSMContext):
    text = message.text.strip().lower()
    if text in ("нет", "no", "skip", "-"):
        await state.update_data(confirm_request_at=None)
        await state.set_state(CreateEventSG.await_category)
        await message.answer("Пропущено. Теперь введите ID категории или 'нет' (пока можно пропустить):")
        return
    dt = parse_dt(message.text)
    if not dt:
        await message.answer("Неправильный формат даты. Введите снова или 'нет':")
        return
    await state.update_data(confirm_request_at=dt)
    await state.set_state(CreateEventSG.await_confirm_text)
    await message.answer("Введите текст запроса подтверждения (лимит 4096 символов):")


@router.message(CreateEventSG.await_confirm_text)
async def ce_confirm_text(message: Message, state: FSMContext):
    text = message.text.strip()
    if len(text) > 4096:
        await message.answer("Слишком длинный текст.")
        return
    await state.update_data(confirm_text=text)
    await state.set_state(CreateEventSG.await_category)
    await message.answer("Введите ID категории (если есть) или 'нет':")


@router.message(CreateEventSG.await_category)
async def ce_category(message: Message, state: FSMContext):
    text = message.text.strip().lower()
    category_id = None
    if text not in ("нет", "no", "-"):
        try:
            category_id = int(text)
        except ValueError:
            await message.answer("Если у вас нет категории — напишите 'нет', иначе введите числовой ID категории.")
            return
    data = await state.get_data()
    title = data["title"]
    publish_at = data["publish_at"]
    reminder_at = data.get("reminder_at")
    reminder_text = data.get("reminder_text")
    confirm_request_at = data.get("confirm_request_at")
    confirm_text = data.get("confirm_text")
    owner_tg_id = str(message.from_user.id)

    async with AsyncSessionLocal() as session:
        ev = await create_event(session, owner_tg_id, title, title, publish_at, reminder_at,
                                reminder_text, confirm_request_at, confirm_text, category_id)
        # generate links and store them
        bot_username = os.getenv("BOT_USERNAME")
        join = await make_deeplink("join", ev.id, bot_username, session)
        speaker = await make_deeplink("speaker", ev.id, bot_username, session)
        await save_generated_link(session, ev.id, "join", join, expires_at=None)
        await save_generated_link(session, ev.id, "speaker", speaker, expires_at=None)

    # schedule jobs
    await schedule_event_jobs_for_event(ev, bot, scheduler)

    await message.answer(f"Мероприятие создано. ID={ev.id}\nСсылка для слушателей: {join}\nСсылка для докладчиков: {speaker}")
    await state.clear()


@router.message(Command(commands=["message_registrations"]))
async def cmd_message_registrations(message: Message, state: FSMContext):
    # Простой flow: /message_registrations <event_id>
    parts = message.text.strip().split()
    if len(parts) != 2:
        await message.answer("Использование: /message_registrations <event_id>")
        return
    try:
        event_id = int(parts[1])
    except ValueError:
        await message.answer("event_id должен быть числом.")
        return

    # проверка прав
    async with AsyncSessionLocal() as session:
        ev = await get_event(session, event_id)
        if not ev:
            await message.answer("Событие не найдено.")
            return
        if ev.owner_tg_id != message.from_user.id and (await get_user_by_tg(session, str(message.from_user.id))) is None:
            # упрощённая проверка: только владелец или супер-админ (проверку ролей можно улучшить)
            await message.answer("У вас нет прав на рассылку для этого события.")
            return
    await state.update_data(target_event_id=event_id)
    await state.set_state(CreateEventSG.confirm)
    await message.answer("Введите текст рассылки (будет отправлен всем зарегистрированным на событие):")


@router.message(CreateEventSG.confirm)
async def do_message_registrations(message: Message, state: FSMContext):
    data = await state.get_data()
    event_id = data.get("target_event_id")
    text = message.text.strip()
    if not text:
        await message.answer("Текст пустой.")
        return
    async with AsyncSessionLocal() as session:
        regs = await get_registrations_for_event(session, event_id)
        chat_ids = [r.tg_id for r in regs]
    from mailer import Mailer
    mailer = Mailer(bot, concurrency=8)
    await mailer.send_batch(chat_ids, text)
    await message.answer(f"Рассылка отправлена ({len(chat_ids)} получателей).")
    await state.clear()


@router.message(Command("my_events"))
async def cmd_my_events(message: Message):
    tg_id = str(message.from_user.id)
    async with AsyncSessionLocal() as session:
        events = await get_events_by_owner(session, tg_id)

    if not events:
        await message.answer("У вас пока нет мероприятий.")
        return

    await message.answer(
        "Ваши мероприятия:",
        reply_markup=events_list_kb(events)
    )


@router.callback_query(F.data.startswith("event:"))
async def cq_event_selected(callback: CallbackQuery):
    event_id = int(callback.data.split(":")[1])
    async with AsyncSessionLocal() as session:
        result = await session.execute(select(Event).where(Event.id == event_id))
        ev = result.scalar_one_or_none()

    if not ev:
        await callback.answer("Мероприятие не найдено", show_alert=True)
        return

    await callback.message.edit_text(
        f"📌 {ev.title}\n"
        f"Дата: {ev.publish_at:%d.%m.%Y %H:%M}\n"
        f"Напоминание: {ev.reminder_text or '—'}",
        reply_markup=event_actions_kb(ev.id)
    )


# --- Callback для кнопки "Редактировать" ---
@router.callback_query(F.data.startswith("edit:"))
async def cq_edit_event(callback: CallbackQuery, state: FSMContext):
    # data вида: "edit:<event_id>"
    event_id = int(callback.data.split(":")[1])

    # получаем данные события
    async with AsyncSessionLocal() as session:
        event = await get_event(session, event_id)
        if not event:
            await callback.answer("Мероприятие не найдено", show_alert=True)
            return

    # сохраняем event_id в state
    await state.update_data(edit_event_id=event_id)

    await callback.message.edit_text(
        f"Вы редактируете мероприятие: {event.title}\nВыберите поле для изменения:",
        reply_markup=edit_menu_kb(event_id)
    )
    await callback.answer()  # чтобы убрать "часики" у кнопки


@router.callback_query(F.data.startswith(("edit_field:", "event:")))
async def cq_edit(callback: CallbackQuery, state: FSMContext):
    data = callback.data

    if data.startswith("edit_field:"):
        # edit_field:<field>:<event_id>
        _, field, event_id = data.split(":")
        event_id = int(event_id)
        await state.update_data(edit_field=field, edit_event_id=event_id)
        await state.set_state(EditEventSG.await_new_value)
        await callback.message.edit_text(f"Введите новое значение для {field}:")
        await callback.answer()

    elif data.startswith("event:"):
        # event:<event_id> — показать детали события
        event_id = int(data.split(":")[1])
        # здесь нужно достать событие и показать его текст + кнопки редактирования
        # например:
        async with AsyncSessionLocal() as session:
            event = await get_event(session, event_id)
            await callback.message.edit_text(f"Событие: {event.title}", reply_markup=edit_menu_kb(event_id))
            await callback.answer("Возврат к событию")


@router.message(EditEventSG.await_new_value)
async def save_new_value(message: Message, state: FSMContext):
    data = await state.get_data()
    event_id = data.get("edit_event_id")
    field = data.get("edit_field")
    new_value = message.text.strip()

    if not event_id or not field:
        await message.answer("Ошибка состояния, попробуйте снова.")
        await state.clear()
        return

    async with AsyncSessionLocal() as session:
        await update_event(session, event_id, **{field: new_value})

    await message.answer(f"Поле {field} успешно обновлено.")
    await state.clear()



@router.callback_query(F.data.startswith("delete:"))
async def cq_event_delete(callback: CallbackQuery):
    event_id = int(callback.data.split(":")[1])
    tg_id = str(callback.from_user.id)

    async with AsyncSessionLocal() as session:
        ok = await delete_event(session, event_id, tg_id)

    if ok:
        await callback.message.edit_text("✅ Мероприятие удалено")
    else:
        await callback.answer("Ошибка: нет доступа или не найдено", show_alert=True)

