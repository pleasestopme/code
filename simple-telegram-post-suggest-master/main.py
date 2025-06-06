import os
import logging
import random
from datetime import datetime
from dotenv import load_dotenv
from sqlalchemy import create_engine, Column, Integer, String, Boolean, DateTime
from sqlalchemy.orm import sessionmaker, scoped_session, declarative_base
from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters
)

# Загрузка переменных окружения
load_dotenv()

# Настройка логгирования
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

# База данных
Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    user_id = Column(Integer, primary_key=True)
    username = Column(String)
    first_name = Column(String)
    last_name = Column(String)
    is_admin = Column(Boolean, default=False)
    is_banned = Column(Boolean, default=False)
    join_date = Column(DateTime, default=datetime.now)

class Post(Base):
    __tablename__ = 'posts'
    post_id = Column(Integer, primary_key=True, autoincrement=True)
    owner_id = Column(Integer)
    owner_name = Column(String)
    attachment_path = Column(String)
    text = Column(String)
    post_date = Column(DateTime, default=datetime.now)
    is_published = Column(Boolean, default=False)

class Settings(Base):
    __tablename__ = 'settings'
    id = Column(Integer, primary_key=True)
    initialized = Column(Boolean, default=False)
    target_channel = Column(String)
    initializer_id = Column(Integer)

# Инициализация базы данных
engine = create_engine('sqlite:///database.db')
Base.metadata.create_all(engine)
Session = scoped_session(sessionmaker(bind=engine))

# Очистка временной папки
def clear_temp_folder():
    if os.path.exists('temp'):
        for filename in os.listdir('temp'):
            file_path = os.path.join('temp', filename)
            try:
                if os.path.isfile(file_path):
                    os.unlink(file_path)
            except Exception as e:
                logger.error(f'Ошибка при удалении файла {file_path}: {e}')
    else:
        os.makedirs('temp', exist_ok=True)

clear_temp_folder()

# Проверка прав администратора
async def is_admin(user_id: int) -> bool:
    with Session() as session:
        user = session.query(User).filter_by(user_id=user_id).first()
        return user.is_admin if user else False

# Проверка бана пользователя
async def is_banned(user_id: int) -> bool:
    with Session() as session:
        user = session.query(User).filter_by(user_id=user_id).first()
        return user.is_banned if user else False

# Обработчики команд
async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    with Session() as session:
        if not session.query(User).filter_by(user_id=user.id).first():
            new_user = User(
                user_id=user.id,
                username=user.username,
                first_name=user.first_name,
                last_name=user.last_name
            )
            session.add(new_user)
            session.commit()
    
    await update.message.reply_text(
        'здарова братишка, скидывай СВОй постец, '
        'я как раздуплюсь, так сразу запосчу.'
    )

async def init_bot(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user_id = update.effective_user.id
    with Session() as session:
        settings = session.query(Settings).first()
        
        # Если бот уже инициализирован - проверяем права администратора
        if settings and settings.initialized:
            if not await is_admin(user_id):
                await update.message.reply_text('❌ Только администратор может изменять настройки бота!')
                return
        
        try:
            args = context.args
            if len(args) != 1:
                raise ValueError
                
            target_channel = args[0]
            
            # Обновление или создание настроек
            if not settings:
                settings = Settings(
                    initialized=True,
                    target_channel=target_channel,
                    initializer_id=user_id
                )
                session.add(settings)
            else:
                settings.target_channel = target_channel
                settings.initialized = True
            
            # Назначение/обновление прав администратора
            user = session.query(User).filter_by(user_id=user_id).first()
            if not user:
                user = User(
                    user_id=user_id,
                    username=update.effective_user.username,
                    first_name=update.effective_user.first_name,
                    last_name=update.effective_user.last_name,
                    is_admin=True
                )
                session.add(user)
            else:
                user.is_admin = True
            
            session.commit()
            await update.message.reply_text('✅ Настройки бота успешно обновлены!')
            
        except Exception as e:
            logger.error(f"Ошибка при инициализации: {e}")
            await update.message.reply_text('Использование: /init <ID_канала>')
            return

async def ban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update.effective_user.id):
        await update.message.reply_text('❌ Только администратор может банить пользователей!')
        return
    
    try:
        user_id = int(context.args[0])
        with Session() as session:
            user = session.query(User).filter_by(user_id=user_id).first()
            if user:
                user.is_banned = True
                session.commit()
                await update.message.reply_text(f'✅ Пользователь {user_id} забанен!')
            else:
                await update.message.reply_text('❌ Пользователь не найден!')
    except:
        await update.message.reply_text('Использование: /ban <ID_пользователя>')

async def unban_user(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update.effective_user.id):
        await update.message.reply_text('❌ Только администратор может разбанивать пользователей!')
        return
    
    try:
        user_id = int(context.args[0])
        with Session() as session:
            user = session.query(User).filter_by(user_id=user_id).first()
            if user:
                user.is_banned = False
                session.commit()
                await update.message.reply_text(f'✅ Пользователь {user_id} разбанен!')
            else:
                await update.message.reply_text('❌ Пользователь не найден!')
    except:
        await update.message.reply_text('Использование: /unban <ID_пользователя>')

async def media_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    
    if await is_banned(user.id):
        await update.message.reply_text('❌ Вы заблокированы и не можете отправлять посты!')
        return
    
    if update.message.photo:
        file = await update.message.photo[-1].get_file()
        file_ext = 'jpg'
    elif update.message.video:
        file = await update.message.video.get_file()
        file_ext = 'mp4'
    else:
        return
    
    filename = f'temp/{random.randint(1, 10**12)}.{file_ext}'
    await file.download_to_drive(filename)
    
    with Session() as session:
        db_user = session.query(User).filter_by(user_id=user.id).first()
        if not db_user:
            db_user = User(
                user_id=user.id,
                username=user.username,
                first_name=user.first_name,
                last_name=user.last_name
            )
            session.add(db_user)
        
        post = Post(
            owner_id=user.id,
            owner_name=user.full_name,
            attachment_path=filename,
            text=update.message.caption
        )
        session.add(post)
        session.commit()
        
        admins = session.query(User).filter_by(is_admin=True).all()
        if admins:
            keyboard = [
                [
                    InlineKeyboardButton("✅ Одобрить", callback_data=f"approve_{post.post_id}"),
                    InlineKeyboardButton("❌ Отклонить", callback_data=f"reject_{post.post_id}")
                ]
            ]
            reply_markup = InlineKeyboardMarkup(keyboard)
            
            caption = f"Новый пост от {user.full_name}"
            if post.text:
                caption += f"\n\n{post.text}"
            
            for admin in admins:
                try:
                    if filename.endswith('.jpg'):
                        await context.bot.send_photo(
                            chat_id=admin.user_id,
                            photo=open(filename, 'rb'),
                            caption=caption,
                            reply_markup=reply_markup
                        )
                    else:
                        await context.bot.send_video(
                            chat_id=admin.user_id,
                            video=open(filename, 'rb'),
                            caption=caption,
                            reply_markup=reply_markup
                        )
                except Exception as e:
                    logger.error(f"Ошибка при отправке поста админу {admin.user_id}: {e}")
    
    await update.message.reply_text('✅ ну всё, епте, тудом сюдом и гляну че ты скинул')

async def moderation_handler(update: Update, context: ContextTypes.DEFAULT_TYPE):
    query = update.callback_query
    await query.answer()
    
    if not await is_admin(query.from_user.id):
        await query.edit_message_text('❌ У вас нет прав для модерации!')
        return
    
    action, post_id = query.data.split('_')
    post_id = int(post_id)
    
    with Session() as session:
        post = session.query(Post).filter_by(post_id=post_id).first()
        if not post:
            await query.edit_message_text('❌ Пост не найден!')
            return
        
        settings = session.query(Settings).first()
        
        if action == 'approve':
            try:
                caption = ""
                if post.text:
                    caption = post.text
                
                # Добавляем автора
                author_text = f"Автор: {post.owner_name}"
                if caption:
                    caption += f"\n\n{author_text}"
                else:
                    caption = author_text
                
                # Отправляем в канал
                if post.attachment_path.endswith('.jpg'):
                    await context.bot.send_photo(
                        chat_id=settings.target_channel,
                        photo=open(post.attachment_path, 'rb'),
                        caption=caption if caption else None
                    )
                else:
                    await context.bot.send_video(
                        chat_id=settings.target_channel,
                        video=open(post.attachment_path, 'rb'),
                        caption=caption if caption.strip() else None  # Полностью пустая подпись, если нет текста
                    )
                
                await context.bot.send_message(
                    chat_id=post.owner_id,
                    text='🎉 ну всё готово малой, чекай постик'
                )
                
                await query.edit_message_text('✅ Пост опубликован!')
            except Exception as e:
                logger.error(f"Ошибка при публикации поста: {e}")
                await query.edit_message_text('❌ Ошибка при публикации поста!')
        
        elif action == 'reject':
            await context.bot.send_message(
                chat_id=post.owner_id,
                text='❌ братан, ну ты тоже хуйню не предлагай да'
            )
            
            await query.edit_message_text('❌ Пост отклонён.')
        
        try:
            if os.path.exists(post.attachment_path):
                os.remove(post.attachment_path)
        except Exception as e:
            logger.error(f"Ошибка при удалении файла: {e}")
        
        session.delete(post)
        session.commit()

def main():
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    if not token:
        logger.error('Токен бота не найден! Укажите его в переменной окружения TELEGRAM_BOT_TOKEN')
        return
    
    application = Application.builder().token(token).build()
    
    application.add_handler(CommandHandler('start', start))
    application.add_handler(CommandHandler('init', init_bot))
    application.add_handler(CommandHandler('ban', ban_user))
    application.add_handler(CommandHandler('unban', unban_user))
    
    application.add_handler(MessageHandler(filters.PHOTO & filters.ChatType.PRIVATE, media_handler))
    application.add_handler(MessageHandler(filters.VIDEO & filters.ChatType.PRIVATE, media_handler))
    
    application.add_handler(CallbackQueryHandler(moderation_handler, pattern=r'^(approve|reject)_\d+$'))
    
    application.run_polling()

if __name__ == '__main__':
    main()