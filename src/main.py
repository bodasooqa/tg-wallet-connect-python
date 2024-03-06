import sys
import logging
import asyncio
import time

import pytonconnect.exceptions
from pytoniq_core import Address
from pytonconnect import TonConnect

import config
from messages import get_comment_message
from connector import get_connector

from aiogram import Bot, Dispatcher, F
from aiogram.enums import ParseMode
from aiogram.filters import CommandStart, Command
from aiogram.types import Message, CallbackQuery
from aiogram.utils.keyboard import InlineKeyboardBuilder


logger = logging.getLogger(__file__)

dp = Dispatcher()
bot = Bot(config.TOKEN, parse_mode=ParseMode.HTML)


@dp.message(CommandStart())
async def command_start_handler(message: Message):
    chat_id = message.chat.id
    connector = get_connector(chat_id)
    connected = await connector.restore_connection()

    mk_b = InlineKeyboardBuilder()
    if connected:
        mk_b.button(text='Отправить 0.01 TON', callback_data='send_tr')
        mk_b.button(text='Отключиться', callback_data='disconnect')
        await message.answer(text='Вы подключены!', reply_markup=mk_b.as_markup())

    else:
        wallets_list = TonConnect.get_wallets()
        for wallet in wallets_list:
            mk_b.button(text=wallet['name'], callback_data=f'connect:{wallet["name"]}')
        mk_b.adjust(1, )
        await message.answer(text='Выберите кошелек для подключения:', reply_markup=mk_b.as_markup())


@dp.message(Command('transaction'))
async def send_transaction(message: Message):
    connector = get_connector(message.chat.id)
    connected = await connector.restore_connection()
    if not connected:
        await message.answer('Сначала подключите кошелек!')
        return

    transaction = {
        'valid_until': int(time.time() + 3600),
        'messages': [
            get_comment_message(
                destination_address=config.DESTINATION_ADDRESS,
                amount=int(0.01 * 10 ** 9),
                comment='Test 0.01 TON transaction'
            )
        ]
    }

    await message.answer(text='Подтвердите транзакцию в кошельке')
    try:
        await asyncio.wait_for(connector.send_transaction(
            transaction=transaction
        ), 300)
    except asyncio.TimeoutError:
        await message.answer(text='Время вышло :()')
    except pytonconnect.exceptions.UserRejectsError:
        await message.answer(text='Вы отклонили транзакцию')
    except Exception as e:
        await message.answer(text=f'Неизвестная ошибка: {e}')


async def connect_wallet(message: Message, wallet_name: str):
    connector = get_connector(message.chat.id)

    wallets_list = connector.get_wallets()
    wallet = None

    for w in wallets_list:
        if w['name'] == wallet_name:
            wallet = w

    if wallet is None:
        raise Exception(f'Неизвестный кошелек: {wallet_name}')

    generated_url = await connector.connect(wallet)

    mk_b = InlineKeyboardBuilder()
    mk_b.button(text='Подключить', url=generated_url)

    await message.answer(text='Подключите кошелек в течение 3 минут', reply_markup=mk_b.as_markup())

    mk_b = InlineKeyboardBuilder()
    mk_b.button(text='Начать', callback_data='start')

    for i in range(1, 180):
        await asyncio.sleep(1)
        if connector.connected:
            if connector.account.address:
                wallet_address = connector.account.address
                wallet_address = Address(wallet_address).to_str(is_bounceable=False)
                await message.answer(f'Вы подключили кошелек <code>{wallet_address}</code>', reply_markup=mk_b.as_markup())
                logger.info(f'Connected with address: {wallet_address}')
            return

    await message.answer(f'Время вышло. Попробуйте снова', reply_markup=mk_b.as_markup())


async def disconnect_wallet(message: Message):
    connector = get_connector(message.chat.id)
    await connector.restore_connection()
    await connector.disconnect()
    await message.answer('Вы успешно отключились')


@dp.callback_query(lambda call: True)
async def main_callback_handler(call: CallbackQuery):
    await call.answer()
    message = call.message
    data = call.data
    if data == "start":
        await command_start_handler(message)
    elif data == "send_tr":
        await send_transaction(message)
    elif data == 'disconnect':
        await disconnect_wallet(message)
    else:
        data = data.split(':')
        if data[0] == 'connect':
            await connect_wallet(message, data[1])


async def main() -> None:
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, stream=sys.stdout)
    asyncio.run(main())
