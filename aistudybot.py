# This file is generated as a complete replacement for the user's current bot.
# It adds:
# - cleaner Telegram HTML formatting
# - inline menu buttons
# - admin-only /stats dashboard
# - /myid for finding Telegram user ID
# - SQLite usage tracking
# - cleaner AI prompt/answers
# - existing Gemini model discovery, fallback and image support
# - existing study commands
import os
import json
import base64
import time
import random
import sqlite3
import re
import urllib.request
import urllib.error
from datetime import datetime, timezone

from telegram import Update, InlineKeyboardButton, InlineKeyboardMarkup
from telegram.constants import ParseMode
from telegram.helpers import escape
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    CallbackQueryHandler,
    ContextTypes,
    filters,
)

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
ADMIN_USER_ID = re.sub(r"\D", "", os.getenv("ADMIN_USER_ID", "7362097945").strip())

if not TELEGRAM_BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN is missing")
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY is missing")

TELEGRAM_LIMIT = 3900
MAX_RETRIES = 4
REQUEST_TIMEOUT = 90
MODEL_CACHE_SECONDS = 600
DB_PATH = os.getenv("STATS_DB_PATH", "studybot_stats.db")

_cached_models = []
_model_cache_time = 0

SYSTEM_PROMPT = """
You are AI Study Bot, a friendly, highly useful and polished AI study assistant.

Your creator is Furkan.

IMPORTANT CREATOR RULE:
If the user asks who created, made, built, developed, programmed,
owns, or is behind this bot, answer exactly:
"I was created by Furkan."

Do not say Google created this Telegram bot.
Gemini is only the AI technology powering the bot.

LANGUAGE:
Always communicate in English. Never use Hindi or Hinglish.

OUTPUT FORMAT — VERY IMPORTANT:
Return PLAIN TEXT suitable for Telegram. Do NOT use LaTeX or TeX syntax.
Never put mathematics inside $...$, $$...$$, \(...\), or \[...\].
Never output commands such as \frac, \times, \Rightarrow, \sqrt, \cdot, or other LaTeX commands.
Never use raw HTML tags. Do not use Markdown tables.
For fractions write them like 3/5 or use a simple stacked explanation such as:
  numerator / denominator
For powers use normal Unicode when practical: x², x³, xⁿ.
For multiplication use ×, division use ÷, and arrows use →.
Keep equations on separate lines.

CLEAN ANSWER STYLE:
Make every response easy to scan on a phone and visually clean.

Use:
• Short headings
• Numbered steps when useful
• Bullet points when useful
• Short paragraphs
• Clear spacing
• Equations on separate lines
• Examples when useful
• A clearly labeled final answer

Avoid:
• Huge walls of text
• Repeating the question unnecessarily
• Excessive emojis
• Decorative lines made from many repeated characters
• Tables unless they genuinely improve clarity
• Markdown code fences unless code is requested
• Dollar signs used as math delimiters

For mathematics:
1. State the formula when useful.
2. Show the working clearly, one step per line.
3. Give a clearly labeled final answer.

For science:
1. Definition
2. How it works
3. Important points
4. Example
5. Quick recap

For study answers, prioritize correctness, clarity and student-friendly explanations.
"""

def db_connect():
    conn = sqlite3.connect(DB_PATH)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            first_name TEXT,
            username TEXT,
            first_seen TEXT NOT NULL,
            last_seen TEXT NOT NULL,
            messages INTEGER DEFAULT 0,
            ai_requests INTEGER DEFAULT 0,
            images INTEGER DEFAULT 0,
            quizzes INTEGER DEFAULT 0,
            mcqs INTEGER DEFAULT 0,
            exams INTEGER DEFAULT 0,
            explains INTEGER DEFAULT 0,
            solves INTEGER DEFAULT 0,
            summaries INTEGER DEFAULT 0
        )
    """)
    return conn

def track_user(update, kind="message"):
    user = update.effective_user
    if not user:
        return
    now = datetime.now(timezone.utc).isoformat()
    first_name = user.first_name or ""
    username = user.username or ""

    conn = db_connect()
    row = conn.execute(
        "SELECT user_id FROM users WHERE user_id = ?", (user.id,)
    ).fetchone()

    message_increment = 0 if kind == "start" else 1
    if row is None:
        conn.execute("""
            INSERT INTO users
            (user_id, first_name, username, first_seen, last_seen, messages)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (user.id, first_name, username, now, now, message_increment))
    else:
        conn.execute("""
            UPDATE users
            SET first_name = ?, username = ?, last_seen = ?,
                messages = messages + ?
            WHERE user_id = ?
        """, (first_name, username, now, message_increment, user.id))

    event_columns = {
        "ai": "ai_requests", "image": "images", "quiz": "quizzes",
        "mcq": "mcqs", "exam": "exams", "explain": "explains",
        "solve": "solves", "summary": "summaries"
    }
    column = event_columns.get(kind)
    if column:
        conn.execute(
            f"UPDATE users SET {column} = {column} + 1 WHERE user_id = ?",
            (user.id,)
        )

    conn.commit()
    conn.close()

def get_stats():
    conn = db_connect()
    total_users = conn.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    today_users = conn.execute(
        "SELECT COUNT(*) FROM users WHERE date(first_seen) = date('now')"
    ).fetchone()[0]
    week_users = conn.execute(
        "SELECT COUNT(*) FROM users WHERE first_seen >= datetime('now', '-7 days')"
    ).fetchone()[0]
    row = conn.execute("""
        SELECT
            COALESCE(SUM(messages), 0),
            COALESCE(SUM(ai_requests), 0),
            COALESCE(SUM(images), 0),
            COALESCE(SUM(quizzes), 0),
            COALESCE(SUM(mcqs), 0),
            COALESCE(SUM(exams), 0),
            COALESCE(SUM(explains), 0),
            COALESCE(SUM(solves), 0),
            COALESCE(SUM(summaries), 0)
        FROM users
    """).fetchone()
    conn.close()
    return {
        "users": total_users,
        "today": today_users,
        "week": week_users,
        "messages": row[0],
        "ai": row[1],
        "images": row[2],
        "quizzes": row[3],
        "mcqs": row[4],
        "exams": row[5],
        "explains": row[6],
        "solves": row[7],
        "summaries": row[8],
    }

def is_admin(update):
    if not ADMIN_USER_ID:
        return False
    user = update.effective_user
    return bool(user and str(user.id) == ADMIN_USER_ID)

def is_creator_question(text):
    text = text.lower().strip()
    creator_phrases = [
        "who created you", "who made you", "who is your creator",
        "who created this bot", "who made this bot", "who built you",
        "who built this bot", "who developed you", "who developed this bot",
        "who programmed you", "who programmed this bot", "who is your owner",
        "who owns this bot", "who is behind this bot", "who are you made by",
        "who made u", "who created u", "who made this", "who created this",
        "who built this",
    ]
    return any(phrase in text for phrase in creator_phrases)

def _replace_braced_command(text, command, replacement):
    """Replace simple LaTeX commands with one braced argument."""
    pattern = re.compile(r"\\" + re.escape(command) + r"\{([^{}]*)\}")
    while pattern.search(text):
        text = pattern.sub(lambda m: replacement(m.group(1)), text)
    return text

def clean_ai_text(text):
    """Turn Gemini's output into clean Telegram-friendly text.

    Telegram HTML does not render LaTeX, so math delimiters and common
    LaTeX commands are converted to readable plain text before escaping.
    """
    if not text:
        return "I could not generate an answer."

    text = str(text).replace("\r\n", "\n").replace("\r", "\n")

    # Remove fenced Markdown wrappers while keeping their contents.
    text = re.sub(r"```(?:[A-Za-z0-9_+-]+)?\n?", "", text)
    text = text.replace("```", "")

    # Convert common LaTeX commands before removing math delimiters.
    # Handle the common \frac{a}{b} form first.
    text = re.sub(r"\\frac\{([^{}]*)\}\{([^{}]*)\}", r"\1/\2", text)
    text = _replace_braced_command(text, "frac", lambda x: x + "/")
    text = _replace_braced_command(text, "sqrt", lambda x: "√(" + x + ")")
    text = _replace_braced_command(text, "text", lambda x: x)
    text = _replace_braced_command(text, "mathrm", lambda x: x)
    text = _replace_braced_command(text, "mathbf", lambda x: x)
    text = _replace_braced_command(text, "operatorname", lambda x: x)

    replacements = {
        r"\\times": "×",
        r"\\cdot": "·",
        r"\\div": "÷",
        r"\\Rightarrow": "→",
        r"\\rightarrow": "→",
        r"\\Leftarrow": "←",
        r"\\leftarrow": "←",
        r"\\leq": "≤",
        r"\\le": "≤",
        r"\\geq": "≥",
        r"\\ge": "≥",
        r"\\neq": "≠",
        r"\\pm": "±",
        r"\\approx": "≈",
        r"\\infty": "∞",
        r"\\pi": "π",
        r"\\sum": "Σ",
        r"\\theta": "θ",
        r"\\alpha": "α",
        r"\\beta": "β",
        r"\\gamma": "γ",
        r"\\Delta": "Δ",
        r"\\degree": "°",
        r"\\quad": " ",
        r"\\,": " ",
    }
    for pattern, replacement in replacements.items():
        text = re.sub(pattern, replacement, text)

    # Remove math delimiters. These are the source of the visible $...$ mess.
    text = re.sub(r"\$\$(.*?)\$\$", r"\1", text, flags=re.S)
    text = re.sub(r"\$(.*?)\$", r"\1", text, flags=re.S)
    text = re.sub(r"\\\((.*?)\\\)", r"\1", text, flags=re.S)
    text = re.sub(r"\\\[(.*?)\\\]", r"\1", text, flags=re.S)

    # Remove remaining LaTeX grouping braces and common commands.
    text = text.replace("{", "").replace("}", "")
    text = re.sub(r"\\([A-Za-z]+)", r"\1", text)

    # Convert simple superscripts/subscripts such as x^{2}, x^2, a_{n}.
    supers = str.maketrans("0123456789+-=()", "⁰¹²³⁴⁵⁶⁷⁸⁹⁺⁻⁼⁽⁾")
    def sup(m):
        value = m.group(1)
        return "".join(ch.translate(supers) for ch in value)
    text = re.sub(r"\^([A-Za-z0-9()+\-=]+)", sup, text)
    text = re.sub(r"_\{([^{}]+)\}", r"_\1", text)

    # Strip Markdown emphasis markers. Telegram HTML below will provide the
    # actual clean bold/italic formatting for headings and emphasis.
    text = re.sub(r"\*\*(.*?)\*\*", r"\1", text, flags=re.S)
    text = re.sub(r"(?<!\*)\*([^*\n]+)\*(?!\*)", r"\1", text)
    text = re.sub(r"^#{1,6}\s*", "", text, flags=re.M)

    # Clean repeated whitespace without destroying intentional line breaks.
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = text.strip()

    # Escape after all transformations so Telegram HTML remains safe.
    text = escape(text)

    # Add consistent visual hierarchy to common study labels.
    text = re.sub(r"(?im)^(correct answer|final answer|answer|solution|explanation)(\s*:?)(.*)$",
                  lambda m: "<b>" + m.group(1).title() + "</b>" + m.group(2) + m.group(3), text)
    text = re.sub(r"(?im)^(question\s+\d+)(\s*:?)$",
                  lambda m: "<b>" + m.group(1).title() + "</b>" + m.group(2), text)
    return text

def split_message(text):
    if len(text) <= TELEGRAM_LIMIT:
        return [text]
    chunks = []
    while len(text) > TELEGRAM_LIMIT:
        cut = text.rfind("\n", 0, TELEGRAM_LIMIT)
        if cut < 1000:
            cut = TELEGRAM_LIMIT
        chunks.append(text[:cut])
        text = text[cut:].lstrip()
    if text:
        chunks.append(text)
    return chunks

async def send_long_message(update, text, parse_mode=ParseMode.HTML):
    for chunk in split_message(text):
        try:
            await update.message.reply_text(
                chunk,
                parse_mode=parse_mode,
                disable_web_page_preview=True
            )
        except Exception:
            await update.message.reply_text(re.sub(r"<[^>]+>", "", chunk))

def main_menu():
    return InlineKeyboardMarkup([
        [
            InlineKeyboardButton("🤖 Ask AI", callback_data="ask_help"),
            InlineKeyboardButton("📖 Explain", callback_data="explain_help"),
        ],
        [
            InlineKeyboardButton("🧠 Quiz", callback_data="quiz_help"),
            InlineKeyboardButton("📝 MCQs", callback_data="mcq_help"),
        ],
        [
            InlineKeyboardButton("🧮 Solve", callback_data="solve_help"),
            InlineKeyboardButton("📄 Summarize", callback_data="summary_help"),
        ],
        [
            InlineKeyboardButton("📋 Exam Paper", callback_data="exam_help"),
            InlineKeyboardButton("❓ Help", callback_data="help"),
        ],
    ])

async def button_handler(update, context):
    query = update.callback_query
    await query.answer()
    messages = {
        "ask_help": "<b>🤖 Ask AI</b>\n\nUse:\n<code>/ask What is gravity?</code>",
        "explain_help": "<b>📖 Explain</b>\n\nUse:\n<code>/explain photosynthesis</code>",
        "quiz_help": "<b>🧠 Quiz</b>\n\nUse:\n<code>/quiz solar system</code>",
        "mcq_help": "<b>📝 MCQs</b>\n\nUse:\n<code>/mcq Class 10 Mathematics</code>",
        "solve_help": "<b>🧮 Solve</b>\n\nUse:\n<code>/solve 2x + 5 = 15</code>",
        "summary_help": "<b>📄 Summarize</b>\n\nUse:\n<code>/summarize Your text here</code>",
        "exam_help": "<b>📋 Exam Paper</b>\n\nUse:\n<code>/exam Motion, Force and Gravitation</code>",
    }
    if query.data == "help":
        await query.edit_message_text(
            "<b>📚 AI Study Bot</b>\n\n"
            "Choose a feature below, or type any question normally.\n\n"
            "🖼️ You can also send a study image.",
            parse_mode=ParseMode.HTML,
            reply_markup=main_menu()
        )
        return
    await query.edit_message_text(
        messages.get(query.data, "Choose an option."),
        parse_mode=ParseMode.HTML,
        reply_markup=main_menu()
    )

def get_available_models(force_refresh=False):
    global _cached_models, _model_cache_time
    now = time.time()
    if not force_refresh and _cached_models and now - _model_cache_time < MODEL_CACHE_SECONDS:
        return _cached_models

    url = "https://generativelanguage.googleapis.com/v1beta/models"
    request = urllib.request.Request(url, method="GET")
    request.add_header("x-goog-api-key", GEMINI_API_KEY)

    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            body = response.read().decode("utf-8")
        data = json.loads(body)
        models = data.get("models", [])
        usable_models = [
            model for model in models
            if model.get("name")
            and "generateContent" in model.get("supportedGenerationMethods", [])
        ]
        _cached_models = usable_models
        _model_cache_time = now
        print("Gemini models discovered:", len(usable_models))
        for model in usable_models:
            print(" -", model.get("name"))
        return usable_models
    except urllib.error.HTTPError as e:
        print("MODEL LIST ERROR:", e.code, e.read().decode("utf-8", errors="replace"))
        return []
    except Exception as e:
        print("MODEL LIST ERROR:", str(e))
        return []

def choose_models():
    models = get_available_models()
    if not models:
        return []

    blocked_words = ["embedding", "aqa", "tts", "image-generation", "imagen", "veo"]
    candidates = [
        model for model in models
        if not any(word in model.get("name", "").lower() for word in blocked_words)
        and "flash" in model.get("name", "").lower()
    ]
    if not candidates:
        candidates = models

    def model_score(model):
        name = model.get("name", "").lower()
        score = 0
        if "flash" in name:
            score += 100
        if "lite" in name:
            score += 20
        if "preview" in name:
            score -= 10
        if "experimental" in name:
            score -= 20
        if "latest" in name:
            score += 5
        return score

    candidates.sort(key=model_score, reverse=True)

    selected = []
    seen = set()
    for model in candidates:
        name = model.get("name", "")
        if name not in seen:
            seen.add(name)
            selected.append(name)
    return selected[:5]

def gemini_request(prompt, model, image_bytes=None, image_mime_type=None):
    model_name = model[7:] if model.startswith("models/") else model
    url = (
        "https://generativelanguage.googleapis.com/"
        "v1beta/models/" + model_name + ":generateContent"
    )
    full_prompt = SYSTEM_PROMPT + "\n\n" + prompt
    parts = [{"text": full_prompt}]

    if image_bytes is not None:
        encoded_image = base64.b64encode(image_bytes).decode("utf-8")
        parts.append({
            "inlineData": {
                "mimeType": image_mime_type,
                "data": encoded_image
            }
        })

    data = {"contents": [{"parts": parts}]}
    request = urllib.request.Request(
        url, data=json.dumps(data).encode("utf-8"), method="POST"
    )
    request.add_header("x-goog-api-key", GEMINI_API_KEY)
    request.add_header("Content-Type", "application/json")

    with urllib.request.urlopen(request, timeout=REQUEST_TIMEOUT) as response:
        result = json.loads(response.read().decode("utf-8"))

    candidates = result.get("candidates", [])
    if not candidates:
        return "The AI returned no answer."

    response_parts = candidates[0].get("content", {}).get("parts", [])
    texts = [part["text"] for part in response_parts if "text" in part]
    return "\n".join(texts) if texts else "The AI returned an empty response."

def ask_ai(prompt, image_bytes=None, image_mime_type=None):
    models = choose_models()
    if not models:
        return "❌ Gemini could not provide a usable model for this API key.\n\nPlease check the Gemini API configuration."

    last_error_status = None
    for model in models:
        for attempt in range(MAX_RETRIES):
            try:
                print("Gemini request:", model, "attempt:", attempt + 1)
                answer = gemini_request(
                    prompt=prompt, model=model,
                    image_bytes=image_bytes,
                    image_mime_type=image_mime_type
                )
                print("Gemini response received:", model)
                return answer
            except urllib.error.HTTPError as e:
                error_body = e.read().decode("utf-8", errors="replace")
                last_error_status = e.code
                print("===== GEMINI API ERROR =====")
                print("MODEL:", model)
                print("HTTP STATUS:", e.code)
                print("ERROR:", error_body)
                print("============================")

                if e.code in (408, 429, 500, 502, 503, 504):
                    if attempt < MAX_RETRIES - 1:
                        time.sleep(3 * (2 ** attempt) + random.uniform(0, 1.5))
                        continue
                    break
                if e.code == 404:
                    get_available_models(force_refresh=True)
                    break
                break
            except urllib.error.URLError as e:
                last_error_status = "NETWORK"
                print("NETWORK ERROR:", str(e))
                if attempt < MAX_RETRIES - 1:
                    time.sleep(2 ** attempt + random.uniform(0, 1))
                    continue
                break
            except Exception as e:
                last_error_status = "GENERAL"
                print("GENERAL ERROR:", str(e))
                break

    if last_error_status == 401:
        return "❌ Gemini authentication failed. Please check the API key in Render."
    if last_error_status == 403:
        return "❌ Gemini access was denied. Please check the API key permissions."
    if last_error_status == 429:
        return "❌ Gemini rate limit reached. Please wait a little and try again."
    if last_error_status in (408, 500, 502, 503, 504):
        return "❌ Gemini is temporarily unavailable.\n\nI retried the request automatically. Please try again shortly."
    if last_error_status == "NETWORK":
        return "❌ Network error while contacting Gemini. Please try again."
    return "❌ I could not get an AI response right now."

async def start(update, context):
    track_user(update, "start")
    await update.message.reply_text(
        "<b>📚 AI Study Bot</b>\n\n"
        "Welcome! 👋\n\n"
        "I can help with:\n"
        "• 🤖 Questions\n"
        "• 📖 Topic explanations\n"
        "• 🧮 Step-by-step solutions\n"
        "• 🧠 Quizzes\n"
        "• 📝 MCQs\n"
        "• 📄 Summaries\n"
        "• 📋 Exam papers\n"
        "• 🖼️ Study images\n\n"
        "<b>Just type a question to begin.</b>",
        parse_mode=ParseMode.HTML,
        reply_markup=main_menu()
    )

async def help_command(update, context):
    track_user(update)
    await update.message.reply_text(
        "<b>📚 AI Study Bot — Commands</b>\n\n"
        "🤖 <code>/ask</code> — Ask any question\n"
        "📖 <code>/explain</code> — Explain a topic\n"
        "🧠 <code>/quiz</code> — Create a quiz\n"
        "📝 <code>/mcq</code> — Generate MCQs\n"
        "📄 <code>/summarize</code> — Summarize text\n"
        "🧮 <code>/solve</code> — Solve step by step\n"
        "📋 <code>/exam</code> — Create an exam paper\n\n"
        "🖼️ Send a photo with a question to analyze it.\n\n"
        "You can also simply type a normal question.",
        parse_mode=ParseMode.HTML,
        reply_markup=main_menu()
    )

async def stats_command(update, context):
    if not is_admin(update):
        await update.message.reply_text("❌ This command is available to the bot administrator only.")
        return
    track_user(update)
    s = get_stats()
    await update.message.reply_text(
        "<b>📊 AI Study Bot — Dashboard</b>\n\n"
        f"👤 <b>Total users:</b> {s['users']}\n"
        f"🆕 <b>New today:</b> {s['today']}\n"
        f"📅 <b>New in 7 days:</b> {s['week']}\n\n"
        f"💬 <b>Messages:</b> {s['messages']}\n"
        f"🤖 <b>AI requests:</b> {s['ai']}\n"
        f"🖼️ <b>Images:</b> {s['images']}\n\n"
        f"🧠 <b>Quizzes:</b> {s['quizzes']}\n"
        f"📝 <b>MCQs:</b> {s['mcqs']}\n"
        f"📋 <b>Exams:</b> {s['exams']}\n"
        f"📖 <b>Explanations:</b> {s['explains']}\n"
        f"🧮 <b>Solutions:</b> {s['solves']}\n"
        f"📄 <b>Summaries:</b> {s['summaries']}",
        parse_mode=ParseMode.HTML
    )

async def myid_command(update, context):
    await update.message.reply_text(
        f"Your Telegram user ID is:\n<code>{update.effective_user.id}</code>",
        parse_mode=ParseMode.HTML
    )

async def ask_command(update, context):
    track_user(update)
    if not context.args:
        await update.message.reply_text(
            "Example:\n<code>/ask What is gravity?</code>",
            parse_mode=ParseMode.HTML
        )
        return
    question = " ".join(context.args)
    if is_creator_question(question):
        await update.message.reply_text("I was created by Furkan.")
        return
    track_user(update, "ai")
    await update.message.reply_text("🤔 <b>Thinking...</b>", parse_mode=ParseMode.HTML)
    await send_long_message(update, clean_ai_text(ask_ai(question)))

async def explain_command(update, context):
    track_user(update)
    if not context.args:
        await update.message.reply_text(
            "Example:\n<code>/explain photosynthesis</code>",
            parse_mode=ParseMode.HTML
        )
        return
    topic = " ".join(context.args)
    prompt = f"""
Explain this topic to a student:

{topic}

Use this structure:
Definition
How it works
Important points
Example
Quick recap
"""
    track_user(update, "explain")
    await update.message.reply_text("📖 <b>Preparing your explanation...</b>", parse_mode=ParseMode.HTML)
    await send_long_message(update, clean_ai_text(ask_ai(prompt)))

async def quiz_command(update, context):
    track_user(update)
    if not context.args:
        await update.message.reply_text(
            "Example:\n<code>/quiz solar system</code>",
            parse_mode=ParseMode.HTML
        )
        return
    topic = " ".join(context.args)
    prompt = f"""
Create a 5-question educational quiz about:
{topic}

For each question provide A, B, C and D choices.
Then provide the correct answer and a short explanation.
Keep it clear and student-friendly.
"""
    track_user(update, "quiz")
    await update.message.reply_text("🧠 <b>Creating your quiz...</b>", parse_mode=ParseMode.HTML)
    await send_long_message(update, clean_ai_text(ask_ai(prompt)))

async def mcq_command(update, context):
    track_user(update)
    if not context.args:
        await update.message.reply_text(
            "Example:\n<code>/mcq Class 10 Mathematics</code>",
            parse_mode=ParseMode.HTML
        )
        return
    topic = " ".join(context.args)
    prompt = f"""
Create 10 useful MCQs about:
{topic}

For every question provide:
A)
B)
C)
D)

Then provide:
Correct Answer:
Explanation:

Make the questions educational and clear.
"""
    track_user(update, "mcq")
    await update.message.reply_text("📝 <b>Generating your MCQs...</b>", parse_mode=ParseMode.HTML)
    await send_long_message(update, clean_ai_text(ask_ai(prompt)))

async def summarize_command(update, context):
    track_user(update)
    if not context.args:
        await update.message.reply_text(
            "Example:\n<code>/summarize Your text here</code>",
            parse_mode=ParseMode.HTML
        )
        return
    text = " ".join(context.args)
    prompt = f"""
Summarize this text:

{text}

Use:
Summary
Important points
Key terms

Keep it concise but useful.
"""
    track_user(update, "summary")
    await update.message.reply_text("📄 <b>Summarizing...</b>", parse_mode=ParseMode.HTML)
    await send_long_message(update, clean_ai_text(ask_ai(prompt)))

async def solve_command(update, context):
    track_user(update)
    if not context.args:
        await update.message.reply_text(
            "Example:\n<code>/solve 2x + 5 = 15</code>",
            parse_mode=ParseMode.HTML
        )
        return
    question = " ".join(context.args)
    prompt = f"""
Solve this question step by step:

{question}

Use:
Given
Working
Step-by-step solution
Final Answer

Explain important steps clearly.
"""
    track_user(update, "solve")
    await update.message.reply_text("🧮 <b>Solving...</b>", parse_mode=ParseMode.HTML)
    await send_long_message(update, clean_ai_text(ask_ai(prompt)))

async def exam_command(update, context):
    track_user(update)
    if not context.args:
        await update.message.reply_text(
            "<b>📋 Exam Paper Generator</b>\n\n"
            "Example:\n<code>/exam Motion, Force and Gravitation</code>",
            parse_mode=ParseMode.HTML
        )
        return
    topics = " ".join(context.args)
    prompt = f"""
Create a complete school-style examination paper.

Topics:
{topics}

Format:
EXAMINATION PAPER
Subject: Based on the provided topics
Topics: {topics}
Time: 2 Hours
Maximum Marks: 50

SECTION A — MCQs
10 questions × 1 mark = 10 marks

SECTION B — VERY SHORT ANSWERS
5 questions × 2 marks = 10 marks

SECTION C — SHORT ANSWERS
5 questions × 3 marks = 15 marks

SECTION D — LONG ANSWERS
3 questions × 5 marks = 15 marks

TOTAL = 50 MARKS

Requirements:
- Cover the provided topics fairly.
- Mix easy, medium and challenging questions.
- Avoid duplicates.
- Include numerical/problem-solving questions when appropriate.
- Do not include answers.
- Keep formatting clean and readable.
"""
    track_user(update, "exam")
    await update.message.reply_text(
        "📋 <b>Creating your exam paper...</b>\n\n⏳ This may take a little time.",
        parse_mode=ParseMode.HTML
    )
    await send_long_message(update, clean_ai_text(ask_ai(prompt)))

async def image_message(update, context):
    track_user(update)
    photo = update.message.photo
    if not photo:
        await update.message.reply_text("❌ No image was received.")
        return
    image = photo[-1]
    caption = update.message.caption or (
        "Analyze this image. If it contains a study question, "
        "solve it step by step. Explain the answer clearly."
    )
    if is_creator_question(caption):
        await update.message.reply_text("I was created by Furkan.")
        return
    track_user(update, "image")
    await update.message.reply_text(
        "🖼️ <b>Image received.</b>\n🔍 <b>Analyzing...</b>",
        parse_mode=ParseMode.HTML
    )
    try:
        telegram_file = await context.bot.get_file(image.file_id)
        image_bytes = await telegram_file.download_as_bytearray()
        answer = ask_ai(
            prompt=caption,
            image_bytes=bytes(image_bytes),
            image_mime_type="image/jpeg"
        )
        await send_long_message(update, clean_ai_text(answer))
    except Exception as e:
        print("IMAGE ERROR:", str(e))
        await update.message.reply_text("❌ There was a problem processing the image.")

async def normal_message(update, context):
    track_user(update)
    text = update.message.text
    if not text:
        return
    if is_creator_question(text):
        await update.message.reply_text("I was created by Furkan.")
        return
    track_user(update, "ai")
    await update.message.reply_text("🤖 <b>Thinking...</b>", parse_mode=ParseMode.HTML)
    await send_long_message(update, clean_ai_text(ask_ai(text)))

def main():
    app = (
        Application.builder()
        .token(TELEGRAM_BOT_TOKEN)
        .build()
    )

    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("help", help_command))
    app.add_handler(CommandHandler("ask", ask_command))
    app.add_handler(CommandHandler("explain", explain_command))
    app.add_handler(CommandHandler("quiz", quiz_command))
    app.add_handler(CommandHandler("mcq", mcq_command))
    app.add_handler(CommandHandler("summarize", summarize_command))
    app.add_handler(CommandHandler("solve", solve_command))
    app.add_handler(CommandHandler("exam", exam_command))
    app.add_handler(CommandHandler("stats", stats_command))
    app.add_handler(CommandHandler("myid", myid_command))

    app.add_handler(CallbackQueryHandler(button_handler))
    app.add_handler(MessageHandler(filters.PHOTO, image_message))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, normal_message))

    port = int(os.environ.get("PORT", "10000"))
    render_url = os.environ.get("RENDER_EXTERNAL_URL")
    if not render_url:
        raise ValueError("RENDER_EXTERNAL_URL is missing")

    webhook_url = render_url + "/telegram"

    print("======================================")
    print("🤖 AI Study Bot is starting!")
    print("🧠 Gemini AI enabled")
    print("🖼️ Image understanding enabled")
    print("📋 Exam generator enabled")
    print("📊 Statistics enabled")
    print("🎛️ Inline menu enabled")
    print("🔄 Automatic model discovery enabled")
    print("🌐 Render webhook enabled")
    print("🔗", webhook_url)
    print("======================================")

    app.run_webhook(
        listen="0.0.0.0",
        port=port,
        url_path="telegram",
        webhook_url=webhook_url,
        drop_pending_updates=True
    )

if __name__ == "__main__":
    main()
