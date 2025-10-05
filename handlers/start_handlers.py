from aiogram import Router
from aiogram.types import Message
from aiogram.filters import Command, CommandObject
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from dotenv import load_dotenv

from keyboards import admin_reply_menu
from utils import verify_payload
from crud import add_registration, mark_confirmed, create_user_if_not_exists, get_user_role
from models import AsyncSessionLocal
import logging

load_dotenv()
logger = logging.getLogger(__name__)
router = Router()


class RegListenerSG(StatesGroup):
    await_name = State()
    await_age = State()
    await_specialty = State()
    await_company = State()
    confirm = State()


class RegSpeakerSG(StatesGroup):
    await_name = State()
    await_age = State()
    await_specialty = State()
    await_company = State()
    await_topic = State()
    confirm = State()


@router.message(Command("start"))
async def cmd_start(message: Message, command: CommandObject, state: FSMContext):
    async with AsyncSessionLocal() as session:
        role = await get_user_role(session, str(message.from_user.id))

    if role in ["event_admin", "super_admin"]:
        await message.answer(
            "Добро пожаловать, админ! 📋 Кнопка меню всегда доступна снизу.",
            reply_markup=admin_reply_menu()
        )
    else:
        await message.answer("Привет! Это бот для мероприятий 👋")

    token = command.args
    if not token:
        await message.answer("Привет! Чтобы зарегистрироваться на мероприятие, используйте ссылку регистрации.")
        return

    async with AsyncSessionLocal() as session:
        payload = await verify_payload(token, session)

    if not payload:
        await message.answer("Неправильная или просроченная ссылка.")
        return

    kind = payload["kind"]
    event_id = payload["event_id"]

    if kind == "join":
        await state.update_data(event_id=event_id, kind=kind)
        await state.set_state(RegListenerSG.await_name)
        await message.answer("Регистрация слушателя.\nВведите ваше имя (как вы хотите, чтобы вас видели):")
    elif kind == "speaker":
        await state.update_data(event_id=event_id, kind=kind)
        await state.set_state(RegSpeakerSG.await_name)
        await message.answer("Регистрация докладчика.\nВведите ваше имя:")
    elif kind == "confirm":
        tg_id = str(message.from_user.id)
        async with AsyncSessionLocal() as session:
            ok = await mark_confirmed(session, event_id, tg_id)
            if ok:
                await message.answer("Спасибо! Вы подтвердили участие.")
            else:
                await message.answer("Не удалось найти вашу регистрацию для подтверждения.")
    else:
        await message.answer("Неизвестный тип ссылки.")


# --- Listener FSM ---
@router.message(RegListenerSG.await_name)
async def listener_name(message: Message, state: FSMContext):
    name = message.text.strip()
    if not name:
        await message.answer("Имя не может быть пустым. Введите снова:")
        return
    await state.update_data(name=name)
    await state.set_state(RegListenerSG.await_age)
    await message.answer("Укажите ваш возраст:")


@router.message(RegListenerSG.await_age)
async def listener_age(message: Message, state: FSMContext):
    text = message.text.strip()
    age = None
    if text.lower() not in ("пропустить", "skip", "-"):
        try:
            age = int(text)
            if age <= 0 or age > 120:
                raise ValueError()
        except ValueError:
            await message.answer("Возраст должен быть положительным целым. Попробуйте снова.")
            return
    await state.update_data(age=age)
    await state.set_state(RegListenerSG.await_specialty)
    await message.answer("Укажите вашу специальность:")


@router.message(RegListenerSG.await_specialty)
async def listener_specialty(message: Message, state: FSMContext):
    specialty = message.text.strip()
    if not specialty:
        await message.answer("Специальность не может быть пустой. Введите снова:")
        return
    await state.update_data(specialty=specialty)
    await state.set_state(RegListenerSG.await_company)
    await message.answer("Укажите компанию/учебное заведение (или '-', если хотите пропустить вопрос):")


@router.message(RegListenerSG.await_company)
async def listener_company(message: Message, state: FSMContext):
    text = message.text.strip()
    company = None if text.lower() in ("пропустить", "skip", "-") else text
    data = await state.get_data()
    event_id = data.get("event_id")
    name = data.get("name")
    age = data.get("age")
    specialty = data.get("specialty")
    tg_id = str(message.from_user.id)
    tg_username = message.from_user.username

    async with AsyncSessionLocal() as session:
        # ensure user exists
        await create_user_if_not_exists(session, tg_id, tg_username)
        await add_registration(session, event_id, tg_id, "listener", name, age, specialty, company, None)
    await message.answer("Спасибо — вы зарегистрированы как слушатель. До встречи!")
    await state.clear()


# --- Speaker FSM ---
@router.message(RegSpeakerSG.await_name)
async def speaker_name(message: Message, state: FSMContext):
    name = message.text.strip()
    if not name:
        await message.answer("Имя не может быть пустым. Введите снова:")
        return
    await state.update_data(name=name)
    await state.set_state(RegSpeakerSG.await_age)
    await message.answer("Укажите ваш возраст:")


@router.message(RegSpeakerSG.await_age)
async def speaker_age(message: Message, state: FSMContext):
    text = message.text.strip()
    try:
        age = int(text)
        if age <= 0 or age > 120:
            raise ValueError()
    except ValueError:
        await message.answer("Возраст должен быть положительным целым. Попробуйте снова.")
        return
    await state.update_data(age=age)
    await state.set_state(RegSpeakerSG.await_specialty)
    await message.answer("Укажите специальность (или '-', если хотите пропустить вопрос):")


@router.message(RegSpeakerSG.await_specialty)
async def speaker_specialty(message: Message, state: FSMContext):
    specialty = message.text.strip()
    if not specialty:
        await message.answer("Специальность не может быть пустой. Введите снова:")
        return
    await state.update_data(specialty=specialty)
    await state.set_state(RegSpeakerSG.await_company)
    await message.answer("Укажите компанию/учебное заведение где вы работаете/учитесь:")


@router.message(RegSpeakerSG.await_company)
async def speaker_company(message: Message, state: FSMContext):
    company = message.text.strip()
    if not company:
        await message.answer("Специальность не может быть пустой. Введите снова:")
        return
    await state.update_data(company=company)
    await state.set_state(RegSpeakerSG.await_topic)
    await message.answer("Укажите тему доклада (кратко):")


@router.message(RegSpeakerSG.await_topic)
async def speaker_topic(message: Message, state: FSMContext):
    topic = message.text.strip()
    if not topic:
        await message.answer("Тема не может быть пустой. Введите снова:")
        return
    data = await state.get_data()
    event_id = data.get("event_id")
    name = data.get("name")
    age = data.get("age")
    specialty = data.get("specialty")
    company = data.get("company")
    tg_id = str(message.from_user.id)
    tg_username = message.from_user.username

    async with AsyncSessionLocal() as session:
        await create_user_if_not_exists(session, tg_id, tg_username)
        await add_registration(session, event_id, tg_id, "speaker", name, age, specialty, company, topic)
    await message.answer("Спасибо — вы зарегистрированы как докладчик. Мы свяжемся при необходимости.")
    await state.clear()
