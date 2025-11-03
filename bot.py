import asyncio
import logging
import feedparser
import os
from datetime import datetime, time
import pytz
from telegram import Update, BotCommand
from telegram.constants import ChatAction
from telegram.ext import Application, CommandHandler, ContextTypes

# ==== CẤU HÌNH BOT ====
TOKEN = os.getenv("BOT_TOKEN")  # Đọc token từ biến môi trường
if not TOKEN:
    raise ValueError("BOT_TOKEN not found! Please set environment variable.")
    
USER_CHAT_ID = None  # sẽ tự động lưu ID người chat lần đầu
TIME_ZONE = pytz.timezone("Asia/Ho_Chi_Minh")

# ==== CẤU HÌNH NGUỒN TIN ====
RSS_FEEDS = [
    "https://vnexpress.net/rss/bat-dong-san.rss",
    "https://cafef.vn/bat-dong-san.rss",
    "https://vietnamfinance.vn/rss/bat-dong-san.rss",
    "https://laodong.vn/rss/bat-dong-san.rss",
    "https://nguoiquansat.vn/rss/bat-dong-san.rss",
]

# ==== CÀI ĐẶT LOG ====
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def filter_articles(articles, month=None, year=None):
    """
    Lọc tin tức theo tiêu chí:
    1. Phải có từ khóa "nhà ở xã hội" hoặc "NOXH"
    2. Phải có "Hà Nội" hoặc "hà nội"
    3. Ưu tiên "Long Biên" hoặc "Đông Anh"
    """
    filtered = []

    for entry in articles:
        title = entry.title.lower()
        summary = entry.get("summary", "").lower()
        combined_text = f"{title} {summary}"
        
        # Kiểm tra published date
        published = entry.get("published_parsed")
        if not published:
            continue

        pub_date = datetime(*published[:6])
        if month and year:
            if pub_date.month != month or pub_date.year != year:
                continue

        # Bước 1: Phải có nhà ở xã hội
        if not ("nhà ở xã hội" in combined_text or "noxh" in combined_text):
            continue
        
        # Bước 2: Phải có Hà Nội
        if "hà nội" not in combined_text and "ha noi" not in combined_text:
            continue
        
        # Bước 3: Ưu tiên Long Biên và Đông Anh
        is_priority = "long biên" in combined_text or "đông anh" in combined_text or \
                      "long bien" in combined_text or "dong anh" in combined_text
        
        # Đánh dấu tin ưu tiên
        prefix = "⭐ " if is_priority else "📰 "
        filtered.append(f"{prefix}<b>{entry.title}</b>\n{entry.link}")

    # Sắp xếp: tin ưu tiên lên đầu
    filtered.sort(key=lambda x: x.startswith("⭐"), reverse=True)
    
    return filtered


async def get_articles():
    all_entries = []
    for url in RSS_FEEDS:
        feed = feedparser.parse(url)
        all_entries.extend(feed.entries)
    return all_entries


async def send_noxh(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Lấy tin theo tháng hoặc hiện tại"""
    await context.bot.send_chat_action(chat_id=update.effective_chat.id, action=ChatAction.TYPING)

    now = datetime.now(TIME_ZONE)
    text = update.message.text.strip().lower()
    args = text.split()

    if len(args) == 2 and "/" in args[1]:
        try:
            month, year = map(int, args[1].split("/"))
        except ValueError:
            await update.message.reply_text("⚠️ Định dạng không hợp lệ. Hãy nhập dạng: /noxh 10/2025")
            return
    else:
        month, year = now.month, now.year

    logger.info(f"Fetching articles for {month}/{year}")
    articles = await get_articles()
    logger.info(f"Total articles fetched: {len(articles)}")
    
    filtered = filter_articles(articles, month, year)
    logger.info(f"Filtered articles: {len(filtered)}")

    if not filtered:
        await update.message.reply_text(
            f"❌ Không tìm thấy tin nhà ở xã hội tại Hà Nội trong {month}/{year}.\n"
            f"(Ưu tiên: Long Biên & Đông Anh)\n"
            f"📊 Tổng tin đã quét: {len(articles)}"
        )
    else:
        await update.message.reply_text(
            f"📅 Tin nhà ở xã hội tại Hà Nội trong {month}/{year}:\n"
            f"⭐ = Long Biên/Đông Anh | 📰 = Khu vực khác\n\n" + "\n\n".join(filtered[:10]),
            parse_mode="HTML"
        )


async def daily_send(context: ContextTypes.DEFAULT_TYPE):
    """Gửi tự động mỗi sáng"""
    if not USER_CHAT_ID:
        return

    now = datetime.now(TIME_ZONE)
    articles = await get_articles()
    filtered = filter_articles(articles, now.month, now.year)

    if filtered:
        await context.bot.send_message(
            chat_id=USER_CHAT_ID,
            text="🌅 Tin nhà ở xã hội Hà Nội hôm nay:\n"
                 "⭐ = Long Biên/Đông Anh | 📰 = Khu vực khác\n\n" + "\n\n".join(filtered[:10]),
            parse_mode="HTML"
        )


async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Khi người dùng bắt đầu chat"""
    global USER_CHAT_ID
    USER_CHAT_ID = update.effective_chat.id
    await update.message.reply_text(
        "👋 Xin chào! Gõ /help để xem hướng dẫn sử dụng."
    )


async def help_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """Hiển thị hướng dẫn sử dụng"""
    help_text = (
        "📖 <b>HƯỚNG DẪN SỬ DỤNG BOT</b>\n\n"
        "🔹 <b>/start</b> - Khởi động bot và đăng ký nhận tin tự động\n\n"
        "🔹 <b>/noxh</b> - Xem tin nhà ở xã hội Hà Nội tháng hiện tại\n\n"
        "🔹 <b>/noxh [tháng/năm]</b> - Xem tin tháng cụ thể\n"
        "   Ví dụ: /noxh 10/2025\n\n"
        "🔹 <b>/help</b> - Xem hướng dẫn này\n\n"
        "━━━━━━━━━━━━━━━━━━━━\n"
        "📍 <b>Khu vực:</b> Hà Nội (ưu tiên Long Biên & Đông Anh)\n"
        "⏰ <b>Tin tự động:</b> Mỗi sáng 8h\n"
        "⭐ = Long Biên/Đông Anh | 📰 = Khu vực khác"
    )
    await update.message.reply_text(help_text, parse_mode="HTML")


async def post_init(application: Application):
    """Set up bot commands menu"""
    commands = [
        BotCommand("start", "Khởi động bot"),
        BotCommand("noxh", "Xem tin tháng hiện tại"),
        BotCommand("help", "Hướng dẫn sử dụng"),
    ]
    await application.bot.set_my_commands(commands)


async def setup_scheduler(application: Application):
    """Setup scheduler after bot starts"""
    scheduler = AsyncIOScheduler(timezone=TIME_ZONE)
    scheduler.add_job(daily_send, "cron", hour=8, minute=0, args=[application])
    scheduler.start()
    logger.info("⏰ Scheduler đã được khởi động")


def main():
    app = Application.builder().token(TOKEN).post_init(post_init).build()

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("noxh", send_noxh))
    app.add_handler(CommandHandler("help", help_command))

    # Dùng job_queue của telegram-bot để gửi tin hàng ngày
    job_queue = app.job_queue
    job_queue.run_daily(
        daily_send, 
        time=time(hour=8, minute=0, tzinfo=TIME_ZONE),
        name="daily_news"
    )

    logger.info("✅ Bot đang chạy...")
    logger.info("⏰ Đã đặt lịch gửi tin mỗi ngày lúc 8:00 AM")
    
    app.run_polling()


if __name__ == "__main__":
    main()