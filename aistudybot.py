import os
import json
import base64
import time
import urllib.request
import urllib.error

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters
)


# ============================================================
# ENVIRONMENT VARIABLES
# ============================================================

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")


if not TELEGRAM_BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN is missing")


if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY is missing")


# ============================================================
# SETTINGS
# ============================================================

# Primary model
PRIMARY_MODEL = "gemini-3.8-flash"

# Fallback model
FALLBACK_MODEL = "gemini-3.5-flash"

# Retry count for temporary errors such as 503
MAX_RETRIES = 3

# Telegram message limit is 4096.
# We keep some space below it.
TELEGRAM_LIMIT = 3900


# ============================================================
# BOT PERSONALITY
# ============================================================

SYSTEM_PROMPT = """
You are AI Study Bot, a friendly and highly useful AI study assistant.

Your creator is Furkan.

If the user asks:
- who created you
- who made you
- who is your creator
- who developed you
- who built this bot
- who is the owner
- who is behind this bot
- who are you made by
- who programmed you
- or anything similar

always answer:

"I was created by Furkan."

Do not claim that Google created this Telegram bot.
Gemini is only the AI technology powering the bot.

GENERAL RESPONSE STYLE:

Give clear, organized and easy-to-read answers.

Use:
• headings
• numbered steps
• bullet points
• short paragraphs
• examples when useful
• equations clearly when needed

Do not make every answer unnecessarily long.

For educational questions, explain concepts at an appropriate student level.

When solving mathematics:
1. Show the formula if useful.
2. Show the steps.
3. Give the final answer clearly.

When explaining science:
1. Definition
2. How it works
3. Important points
4. Example
5. Short summary

Use Markdown formatting where useful.
"""


# ============================================================
# CREATOR QUESTION DETECTION
# ============================================================

def is_creator_question(text):

    text = text.lower().strip()

    creator_words = [
        "who created you",
        "who made you",
        "who is your creator",
        "who created this bot",
        "who made this bot",
        "who built you",
        "who built this bot",
        "who developed you",
        "who developed this bot",
        "who programmed you",
        "who programmed this bot",
        "who is your owner",
        "who owns this bot",
        "who is behind this bot",
        "who are you made by",
        "who made u",
        "who created u"
    ]

    return any(
        phrase in text
        for phrase in creator_words
    )


# ============================================================
# SPLIT LONG TELEGRAM MESSAGES
# ============================================================

def split_message(text):

    if len(text) <= TELEGRAM_LIMIT:
        return [text]

    chunks = []

    while len(text) > TELEGRAM_LIMIT:

        cut = text.rfind(
            "\n",
            0,
            TELEGRAM_LIMIT
        )

        if cut < 1000:
            cut = TELEGRAM_LIMIT

        chunks.append(
            text[:cut]
        )

        text = text[cut:].lstrip()

    if text:
        chunks.append(text)

    return chunks


async def send_long_message(
    update,
    text,
    parse_mode="Markdown"
):

    chunks = split_message(text)

    for chunk in chunks:

        try:

            await update.message.reply_text(
                chunk,
                parse_mode=parse_mode
            )

        except Exception:

            # If Markdown causes a formatting problem,
            # send the same text without Markdown.

            await update.message.reply_text(
                chunk
            )


# ============================================================
# GEMINI REQUEST
# ============================================================

def gemini_request(
    prompt,
    image_bytes=None,
    image_mime_type=None,
    model=PRIMARY_MODEL
):

    url = (
        "https://generativelanguage.googleapis.com/"
        "v1beta/models/"
        + model
        + ":generateContent"
    )

    full_prompt = (
        SYSTEM_PROMPT
        + "\n\n"
        + prompt
    )

    parts = []

    parts.append(
        {
            "text": full_prompt
        }
    )

    # --------------------------------------------------------
    # IMAGE INPUT
    # --------------------------------------------------------

    if image_bytes is not None:

        encoded_image = base64.b64encode(
            image_bytes
        ).decode("utf-8")

        parts.append(
            {
                "inlineData": {
                    "mimeType": image_mime_type,
                    "data": encoded_image
                }
            }
        )

    data = {
        "contents": [
            {
                "parts": parts
            }
        ]
    }

    body = json.dumps(
        data
    ).encode("utf-8")

    request = urllib.request.Request(
        url,
        data=body,
        method="POST"
    )

    request.add_header(
        "x-goog-api-key",
        GEMINI_API_KEY
    )

    request.add_header(
        "Content-Type",
        "application/json"
    )

    with urllib.request.urlopen(
        request,
        timeout=90
    ) as response:

        response_body = response.read().decode(
            "utf-8"
        )

        result = json.loads(
            response_body
        )

    candidates = result.get(
        "candidates",
        []
    )

    if not candidates:

        return (
            "❌ Gemini ne koi answer nahi diya.\n\n"
            + response_body[:2000]
        )

    content = candidates[0].get(
        "content",
        {}
    )

    response_parts = content.get(
        "parts",
        []
    )

    texts = []

    for part in response_parts:

        if "text" in part:
            texts.append(
                part["text"]
            )

    if not texts:
        return "❌ Gemini ne empty response diya."

    return "\n".join(texts)


# ============================================================
# AI FUNCTION WITH RETRY + FALLBACK
# ============================================================

def ask_ai(
    prompt,
    image_bytes=None,
    image_mime_type=None
):

    models_to_try = [
        PRIMARY_MODEL,
        FALLBACK_MODEL
    ]

    last_error = None

    for model in models_to_try:

        for attempt in range(
            MAX_RETRIES
        ):

            try:

                print(
                    "Gemini request:",
                    model,
                    "attempt:",
                    attempt + 1
                )

                answer = gemini_request(
                    prompt=prompt,
                    image_bytes=image_bytes,
                    image_mime_type=image_mime_type,
                    model=model
                )

                print(
                    "Gemini response received from:",
                    model
                )

                return answer

            except urllib.error.HTTPError as e:

                error_body = e.read().decode(
                    "utf-8",
                    errors="replace"
                )

                print(
                    "\n===== GEMINI API ERROR ====="
                )

                print(
                    "MODEL:",
                    model
                )

                print(
                    "HTTP STATUS:",
                    e.code
                )

                print(
                    "ERROR:",
                    error_body
                )

                print(
                    "============================\n"
                )

                last_error = (
                    e.code,
                    error_body
                )

                # ------------------------------------------------
                # 503 = temporary model overload
                # ------------------------------------------------

                if e.code == 503:

                    if attempt < MAX_RETRIES - 1:

                        time.sleep(
                            2 ** attempt
                        )

                        continue

                    # Try fallback model
                    break

                # ------------------------------------------------
                # 429 = rate limit
                # ------------------------------------------------

                if e.code == 429:

                    if attempt < MAX_RETRIES - 1:

                        time.sleep(
                            3
                        )

                        continue

                    break

                # ------------------------------------------------
                # Other HTTP errors
                # ------------------------------------------------

                break

            except urllib.error.URLError as e:

                print(
                    "\n===== NETWORK ERROR ====="
                )

                print(
                    str(e)
                )

                print(
                    "=========================\n"
                )

                last_error = (
                    "NETWORK",
                    str(e)
                )

                if attempt < MAX_RETRIES - 1:

                    time.sleep(
                        2
                    )

                    continue

                break

            except Exception as e:

                print(
                    "\n===== GENERAL ERROR ====="
                )

                print(
                    str(e)
                )

                print(
                    "========================\n"
                )

                last_error = (
                    "GENERAL",
                    str(e)
                )

                break

    # ========================================================
    # FINAL ERROR
    # ========================================================

    if last_error:

        status = last_error[0]
        details = last_error[1]

        return (
            "❌ Gemini temporarily unavailable.\n\n"
            "Status: "
            + str(status)
            + "\n\n"
            "Please try again in a little while."
        )

    return (
        "❌ AI response lene me problem aa gayi."
    )


# ============================================================
# START
# ============================================================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    await update.message.reply_text(
        "📚 *AI Study Bot*\n\n"
        "Hello! 👋\n\n"
        "Main tumhari studies me help kar sakta hoon.\n\n"

        "🧠 *AI*\n"
        "/ask <question>\n\n"

        "📖 *Study*\n"
        "/explain <topic>\n"
        "/quiz <topic>\n"
        "/mcq <topic>\n"
        "/summarize <text>\n"
        "/solve <question>\n\n"

        "📝 *Exam Paper*\n"
        "/exam <chapters/topics>\n\n"

        "🖼️ *Image Questions*\n"
        "Mujhe koi image/photo bhejo aur uske saath question likho.\n\n"

        "Example:\n"
        "`/exam Motion, Force and Gravitation`\n\n"

        "Ya simply normal message bhejo.",
        parse_mode="Markdown"
    )


# ============================================================
# HELP
# ============================================================

async def help_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    await update.message.reply_text(
        "📚 *AI Study Bot Commands*\n\n"

        "🤖 `/ask` — Any question\n"
        "📖 `/explain` — Explain a topic\n"
        "🧠 `/quiz` — Create a quiz\n"
        "📝 `/mcq` — Create MCQs\n"
        "📄 `/summarize` — Summarize text\n"
        "🧮 `/solve` — Solve a question\n"
        "📋 `/exam` — Create an exam paper\n\n"

        "🖼️ *Images:*\n"
        "Photo bhejo + question likho.\n"
        "Example: 'Solve this question.'\n\n"

        "👤 Creator:\n"
        "Ask me who created me.",
        parse_mode="Markdown"
    )


# ============================================================
# ASK
# ============================================================

async def ask_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not context.args:

        await update.message.reply_text(
            "Example:\n"
            "/ask What is gravity?"
        )

        return

    question = " ".join(
        context.args
    )

    if is_creator_question(question):

        await update.message.reply_text(
            "I was created by Furkan."
        )

        return

    await update.message.reply_text(
        "🤔 Thinking..."
    )

    answer = ask_ai(
        question
    )

    await send_long_message(
        update,
        answer
    )


# ============================================================
# EXPLAIN
# ============================================================

async def explain_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not context.args:

        await update.message.reply_text(
            "Example:\n"
            "/explain photosynthesis"
        )

        return

    topic = " ".join(
        context.args
    )

    prompt = f"""
Explain this topic to a student:

{topic}

Use this format:

📖 Definition

⚙️ How it works

⭐ Important points

💡 Example

📝 Short summary

Keep the explanation clear and easy to understand.
"""

    await update.message.reply_text(
        "📖 Preparing explanation..."
    )

    answer = ask_ai(
        prompt
    )

    await send_long_message(
        update,
        answer
    )


# ============================================================
# QUIZ
# ============================================================

async def quiz_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not context.args:

        await update.message.reply_text(
            "Example:\n"
            "/quiz solar system"
        )

        return

    topic = " ".join(
        context.args
    )

    prompt = f"""
Create a 5-question educational quiz about:

{topic}

For every question provide:

A)
B)
C)
D)

Then provide:

Correct Answer:
Explanation:

Make the questions appropriate for a student.
"""

    await update.message.reply_text(
        "🧠 Creating quiz..."
    )

    answer = ask_ai(
        prompt
    )

    await send_long_message(
        update,
        answer
    )


# ============================================================
# MCQ
# ============================================================

async def mcq_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not context.args:

        await update.message.reply_text(
            "Example:\n"
            "/mcq class 10 mathematics"
        )

        return

    topic = " ".join(
        context.args
    )

    prompt = f"""
Create 10 useful MCQs about:

{topic}

For every question provide:

A)
B)
C)
D)

Correct Answer:
Explanation:

Make the questions educational and clear.
"""

    await update.message.reply_text(
        "📝 Generating MCQs..."
    )

    answer = ask_ai(
        prompt
    )

    await send_long_message(
        update,
        answer
    )


# ============================================================
# SUMMARIZE
# ============================================================

async def summarize_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not context.args:

        await update.message.reply_text(
            "Example:\n"
            "/summarize Your text here"
        )

        return

    text = " ".join(
        context.args
    )

    prompt = f"""
Summarize this text:

{text}

Use this format:

📄 Summary

⭐ Important points

🔑 Key terms

Keep it concise but useful.
"""

    await update.message.reply_text(
        "📄 Summarizing..."
    )

    answer = ask_ai(
        prompt
    )

    await send_long_message(
        update,
        answer
    )


# ============================================================
# SOLVE
# ============================================================

async def solve_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not context.args:

        await update.message.reply_text(
            "Example:\n"
            "/solve 2x + 5 = 15"
        )

        return

    question = " ".join(
        context.args
    )

    prompt = f"""
Solve this question step by step:

{question}

Use this structure:

📌 Given

🧮 Working

➡️ Step-by-step solution

✅ Final Answer

Explain every important step clearly.
"""

    await update.message.reply_text(
        "🧮 Solving..."
    )

    answer = ask_ai(
        prompt
    )

    await send_long_message(
        update,
        answer
    )


# ============================================================
# EXAM PAPER
# ============================================================

async def exam_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not context.args:

        await update.message.reply_text(
            "📋 *Exam Paper Generator*\n\n"
            "Example:\n"
            "`/exam Motion, Force and Gravitation`\n\n"
            "You can give:\n"
            "• One chapter\n"
            "• Multiple chapters\n"
            "• A topic\n"
            "• Multiple topics",
            parse_mode="Markdown"
        )

        return

    topics = " ".join(
        context.args
    )

    prompt = f"""
Create a complete school-style examination paper.

Topics / Chapters:
{topics}

Make a balanced paper based only on these topics.

Use this format:

━━━━━━━━━━━━━━━━━━━━
📚 EXAMINATION PAPER
━━━━━━━━━━━━━━━━━━━━

Subject: Based on the provided topics
Topics: {topics}

Time: 2 Hours
Maximum Marks: 50

━━━━━━━━━━━━━━━━━━━━
SECTION A — MCQs
━━━━━━━━━━━━━━━━━━━━

10 questions × 1 mark = 10 marks

Each question must have:
A)
B)
C)
D)

━━━━━━━━━━━━━━━━━━━━
SECTION B — VERY SHORT ANSWERS
━━━━━━━━━━━━━━━━━━━━

5 questions × 2 marks = 10 marks

━━━━━━━━━━━━━━━━━━━━
SECTION C — SHORT ANSWERS
━━━━━━━━━━━━━━━━━━━━

5 questions × 3 marks = 15 marks

━━━━━━━━━━━━━━━━━━━━
SECTION D — LONG ANSWERS
━━━━━━━━━━━━━━━━━━━━

3 questions × 5 marks = 15 marks

━━━━━━━━━━━━━━━━━━━━
TOTAL = 50 MARKS
━━━━━━━━━━━━━━━━━━━━

Important requirements:

• Cover the provided chapters/topics fairly.
• Mix easy, medium and challenging questions.
• Avoid duplicate questions.
• Make questions suitable for students.
• Include numerical/problem-solving questions when appropriate.
• Do not include answers in the question paper.
• Keep formatting clean and readable.
"""

    await update.message.reply_text(
        "📝 Creating your exam paper...\n"
        "⏳ This may take a little time."
    )

    answer = ask_ai(
        prompt
    )

    await send_long_message(
        update,
        answer
    )


# ============================================================
# IMAGE HANDLER
# ============================================================

async def image_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    photo = update.message.photo

    if not photo:

        await update.message.reply_text(
            "❌ Image receive nahi hui."
        )

        return

    # Highest available resolution
    image = photo[-1]

    caption = update.message.caption

    if not caption:

        caption = (
            "Analyze this image and explain what "
            "you see. If it contains a study question, "
            "solve it step by step."
        )

    if is_creator_question(caption):

        await update.message.reply_text(
            "I was created by Furkan."
        )

        return

    await update.message.reply_text(
        "🖼️ Image received.\n"
        "🤔 Analyzing..."
    )

    try:

        telegram_file = await context.bot.get_file(
            image.file_id
        )

        image_bytes = await telegram_file.download_as_bytearray()

        mime_type = "image/jpeg"

        answer = ask_ai(
            prompt=caption,
            image_bytes=bytes(image_bytes),
            image_mime_type=mime_type
        )

        await send_long_message(
            update,
            answer
        )

    except Exception as e:

        print(
            "IMAGE ERROR:",
            str(e)
        )

        await update.message.reply_text(
            "❌ Image process karne me problem aa gayi."
        )


# ============================================================
# NORMAL TEXT MESSAGE
# ============================================================

async def normal_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    text = update.message.text

    if not text:
        return

    # Creator question
    if is_creator_question(text):

        await update.message.reply_text(
            "I was created by Furkan."
        )

        return

    await update.message.reply_text(
        "🤖 Thinking..."
    )

    answer = ask_ai(
        text
    )

    await send_long_message(
        update,
        answer
    )


# ============================================================
# MAIN
# ============================================================

def main():

    app = (
        Application
        .builder()
        .token(
            TELEGRAM_BOT_TOKEN
        )
        .build()
    )


    # --------------------------------------------------------
    # COMMANDS
    # --------------------------------------------------------

    app.add_handler(
        CommandHandler(
            "start",
            start
        )
    )

    app.add_handler(
        CommandHandler(
            "help",
            help_command
        )
    )

    app.add_handler(
        CommandHandler(
            "ask",
            ask_command
        )
    )

    app.add_handler(
        CommandHandler(
            "explain",
            explain_command
        )
    )

    app.add_handler(
        CommandHandler(
            "quiz",
            quiz_command
        )
    )

    app.add_handler(
        CommandHandler(
            "mcq",
            mcq_command
        )
    )

    app.add_handler(
        CommandHandler(
            "summarize",
            summarize_command
        )
    )

    app.add_handler(
        CommandHandler(
            "solve",
            solve_command
        )
    )

    app.add_handler(
        CommandHandler(
            "exam",
            exam_command
        )
    )


    # --------------------------------------------------------
    # IMAGE HANDLER
    # --------------------------------------------------------

    app.add_handler(
        MessageHandler(
            filters.PHOTO,
            image_message
        )
    )


    # --------------------------------------------------------
    # NORMAL TEXT
    # --------------------------------------------------------

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            normal_message
        )
    )


    # --------------------------------------------------------
    # RENDER PORT
    # --------------------------------------------------------

    port = int(
        os.environ.get(
            "PORT",
            "10000"
        )
    )


    # --------------------------------------------------------
    # RENDER URL
    # --------------------------------------------------------

    render_url = os.environ.get(
        "RENDER_EXTERNAL_URL"
    )

    if not render_url:

        raise ValueError(
            "RENDER_EXTERNAL_URL is missing"
        )


    webhook_url = (
        render_url
        + "/telegram"
    )


    print(
        "======================================"
    )

    print(
        "🤖 AI Study Bot is starting!"
    )

    print(
        "👤 Creator: Furkan"
    )

    print(
        "🧠 Gemini AI enabled"
    )

    print(
        "🖼️ Image understanding enabled"
    )

    print(
        "📝 Exam generator enabled"
    )

    print(
        "🔄 Retry + fallback enabled"
    )

    print(
        "🌐 Render webhook enabled"
    )

    print(
        "🔗",
        webhook_url
    )

    print(
        "======================================"
    )


    # --------------------------------------------------------
    # START WEBHOOK
    # --------------------------------------------------------

    app.run_webhook(
        listen="0.0.0.0",
        port=port,
        url_path="telegram",
        webhook_url=webhook_url,
        drop_pending_updates=True
    )


# ============================================================
# START PROGRAM
# ============================================================

if __name__ == "__main__":
    main()
