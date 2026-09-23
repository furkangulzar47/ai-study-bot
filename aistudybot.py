import os
import json
import base64
import time
import random
import urllib.request
import urllib.error

from telegram import Update
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    ContextTypes,
    filters,
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

TELEGRAM_LIMIT = 3900

# Maximum number of attempts for a single model
MAX_RETRIES = 4

# How long the HTTP request can wait
REQUEST_TIMEOUT = 90

# Cache discovered models for this many seconds
MODEL_CACHE_SECONDS = 600

_cached_models = []
_model_cache_time = 0


# ============================================================
# BOT PERSONALITY
# ============================================================

SYSTEM_PROMPT = """
You are AI Study Bot, a friendly and highly useful AI study assistant.

Your creator is Furkan.

IMPORTANT CREATOR RULE:

If the user asks who created, made, built, developed, programmed,
owns, or is behind this bot, answer exactly:

"I was created by Furkan."

Do not say that Google created this Telegram bot.
Gemini is only the AI technology powering the bot.

LANGUAGE RULE:

Always communicate with the user in English.

Do not use Hindi, Hinglish, or Hindi transliteration in your replies,
including error messages, explanations, examples, commands, and study
content.

GENERAL RESPONSE STYLE:

Give clear, organized and easy-to-read answers.

Use:
- headings
- numbered steps
- bullet points
- short paragraphs
- examples when useful
- equations clearly when needed

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

    creator_phrases = [
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
        "who created u",
        "who made this",
        "who created this",
        "who built this",
    ]

    return any(
        phrase in text
        for phrase in creator_phrases
    )


# ============================================================
# TELEGRAM MESSAGE SPLITTER
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

        chunks.append(text[:cut])

        text = text[cut:].lstrip()

    if text:
        chunks.append(text)

    return chunks


async def send_long_message(
    update,
    text,
    parse_mode="Markdown"
):

    for chunk in split_message(text):

        try:
            await update.message.reply_text(
                chunk,
                parse_mode=parse_mode
            )

        except Exception:
            await update.message.reply_text(chunk)


# ============================================================
# GEMINI: DISCOVER AVAILABLE MODELS
# ============================================================

def get_available_models(force_refresh=False):

    global _cached_models
    global _model_cache_time

    now = time.time()

    if (
        not force_refresh
        and _cached_models
        and now - _model_cache_time < MODEL_CACHE_SECONDS
    ):
        return _cached_models

    url = (
        "https://generativelanguage.googleapis.com/"
        "v1beta/models"
    )

    request = urllib.request.Request(
        url,
        method="GET"
    )

    request.add_header(
        "x-goog-api-key",
        GEMINI_API_KEY
    )

    try:

        with urllib.request.urlopen(
            request,
            timeout=30
        ) as response:

            body = response.read().decode(
                "utf-8"
            )

        data = json.loads(body)

        models = data.get(
            "models",
            []
        )

        usable_models = []

        for model in models:

            name = model.get(
                "name",
                ""
            )

            methods = model.get(
                "supportedGenerationMethods",
                []
            )

            if (
                name
                and "generateContent" in methods
            ):

                usable_models.append(
                    model
                )

        _cached_models = usable_models
        _model_cache_time = now

        print(
            "Gemini models discovered:",
            len(usable_models)
        )

        for model in usable_models:
            print(
                " -",
                model.get("name")
            )

        return usable_models

    except urllib.error.HTTPError as e:

        error_body = e.read().decode(
            "utf-8",
            errors="replace"
        )

        print(
            "MODEL LIST ERROR:",
            e.code,
            error_body
        )

        return []

    except Exception as e:

        print(
            "MODEL LIST ERROR:",
            str(e)
        )

        return []


# ============================================================
# CHOOSE BEST AVAILABLE MODELS
# ============================================================

def choose_models():

    models = get_available_models()

    if not models:
        return []

    candidates = []

    for model in models:

        full_name = model.get(
            "name",
            ""
        )

        name = full_name.lower()

        # Ignore non-chat/generation models
        blocked_words = [
            "embedding",
            "aqa",
            "tts",
            "image-generation",
            "imagen",
            "veo",
        ]

        if any(
            word in name
            for word in blocked_words
        ):
            continue

        # Prefer Flash models because this is a study bot
        if "flash" in name:
            candidates.append(
                model
            )

    # If no Flash model was found, use any usable
    # generateContent model.
    if not candidates:
        candidates = models

    # Prefer stable-looking models over experimental ones.
    def model_score(model):

        name = model.get(
            "name",
            ""
        ).lower()

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

    candidates.sort(
        key=model_score,
        reverse=True
    )

    # Remove duplicates
    selected = []
    seen = set()

    for model in candidates:

        name = model.get(
            "name",
            ""
        )

        if name not in seen:

            seen.add(name)
            selected.append(name)

    # Try several available models.
    return selected[:5]


# ============================================================
# GEMINI GENERATE CONTENT
# ============================================================

def gemini_request(
    prompt,
    model,
    image_bytes=None,
    image_mime_type=None
):

    # API model names are normally returned as:
    # models/example-model
    model_name = model

    if model_name.startswith("models/"):
        model_name = model_name[len("models/"):]

    url = (
        "https://generativelanguage.googleapis.com/"
        "v1beta/models/"
        + model_name
        + ":generateContent"
    )

    full_prompt = (
        SYSTEM_PROMPT
        + "\n\n"
        + prompt
    )

    parts = [
        {
            "text": full_prompt
        }
    ]

    # --------------------------------------------------------
    # IMAGE
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
        timeout=REQUEST_TIMEOUT
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
            "The AI returned no answer."
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

        return (
            "The AI returned an empty response."
        )

    return "\n".join(texts)


# ============================================================
# AI FUNCTION
# ============================================================

def ask_ai(
    prompt,
    image_bytes=None,
    image_mime_type=None
):

    models = choose_models()

    if not models:

        return (
            "❌ Gemini could not provide any usable "
            "generateContent models for this API key.\n\n"
            "Please check the Gemini API configuration."
        )

    print(
        "Models selected for request:"
    )

    for model in models:
        print(
            " -",
            model
        )

    last_error_status = None
    last_error_body = ""

    # --------------------------------------------------------
    # Try each available model
    # --------------------------------------------------------

    for model in models:

        for attempt in range(
            MAX_RETRIES
        ):

            try:

                print(
                    "\nGemini request:",
                    model,
                    "attempt:",
                    attempt + 1
                )

                answer = gemini_request(
                    prompt=prompt,
                    model=model,
                    image_bytes=image_bytes,
                    image_mime_type=image_mime_type
                )

                print(
                    "Gemini response received:",
                    model
                )

                return answer

            except urllib.error.HTTPError as e:

                error_body = e.read().decode(
                    "utf-8",
                    errors="replace"
                )

                last_error_status = e.code
                last_error_body = error_body

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

                # ------------------------------------------------
                # Temporary errors
                # ------------------------------------------------

                if e.code in (
                    408,
                    429,
                    500,
                    502,
                    503,
                    504
                ):

                    if attempt < MAX_RETRIES - 1:

                        # 3, 6, 12, 24 seconds
                        # + small random jitter
                        delay = (
                            3 * (2 ** attempt)
                            + random.uniform(0, 1.5)
                        )

                        print(
                            "Temporary error.",
                            "Retrying in",
                            round(delay, 1),
                            "seconds..."
                        )

                        time.sleep(
                            delay
                        )

                        continue

                    print(
                        "Retries exhausted for:",
                        model
                    )

                    # Try the next available model
                    break

                # ------------------------------------------------
                # Model not found
                # ------------------------------------------------

                if e.code == 404:

                    print(
                        "Model unavailable:",
                        model
                    )

                    # Refresh model list
                    get_available_models(
                        force_refresh=True
                    )

                    break

                # ------------------------------------------------
                # Authentication / permission / bad request
                # ------------------------------------------------

                break

            except urllib.error.URLError as e:

                last_error_status = "NETWORK"
                last_error_body = str(e)

                print(
                    "\n===== NETWORK ERROR ====="
                )

                print(
                    str(e)
                )

                print(
                    "=========================\n"
                )

                if attempt < MAX_RETRIES - 1:

                    delay = (
                        2 ** attempt
                        + random.uniform(0, 1)
                    )

                    time.sleep(
                        delay
                    )

                    continue

                break

            except Exception as e:

                last_error_status = "GENERAL"
                last_error_body = str(e)

                print(
                    "\n===== GENERAL ERROR ====="
                )

                print(
                    str(e)
                )

                print(
                    "========================\n"
                )

                break

    # ========================================================
    # FRIENDLY ERROR
    # ========================================================

    if last_error_status == 401:

        return (
            "❌ Gemini API authentication failed.\n\n"
            "Please check the GEMINI_API_KEY in Render."
        )

    if last_error_status == 403:

        return (
            "❌ Gemini API access was denied.\n\n"
            "Please check the API key permissions "
            "and project configuration."
        )

    if last_error_status == 429:

        return (
            "❌ Gemini rate limit reached.\n\n"
            "Please wait a little and try again."
        )

    if last_error_status in (
        408,
        500,
        502,
        503,
        504
    ):

        return (
            "❌ Gemini is temporarily unavailable.\n\n"
            "The request was retried automatically, "
            "but the available models did not respond.\n\n"
            "Please try again shortly."
        )

    if last_error_status == "NETWORK":

        return (
            "❌ Network error while contacting Gemini.\n\n"
            "Please try again."
        )

    return (
        "❌ I could not get an AI response right now."
    )


# ============================================================
# /START
# ============================================================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    await update.message.reply_text(
        "📚 *AI Study Bot*\n\n"
        "Hello! 👋\n\n"
        "I can help you with studying, "
        "questions, quizzes, exams, mathematics, "
        "science, and images.\n\n"

        "🧠 *AI*\n"
        "`/ask <question>`\n\n"

        "📖 *Study*\n"
        "`/explain <topic>`\n"
        "`/quiz <topic>`\n"
        "`/mcq <topic>`\n"
        "`/summarize <text>`\n"
        "`/solve <question>`\n\n"

        "📝 *Exam Paper*\n"
        "`/exam <chapters/topics>`\n\n"

        "🖼️ *Image Questions*\n"
        "Send me a photo with a question or instruction.\n\n"

        "Example:\n"
        "`/exam Motion, Force and Gravitation`\n\n"

        "You can also simply send me a normal message.",
        parse_mode="Markdown"
    )


# ============================================================
# /HELP
# ============================================================

async def help_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    await update.message.reply_text(
        "📚 *AI Study Bot Commands*\n\n"

        "🤖 `/ask` — Ask any question\n"
        "📖 `/explain` — Explain a topic\n"
        "🧠 `/quiz` — Create a quiz\n"
        "📝 `/mcq` — Create MCQs\n"
        "📄 `/summarize` — Summarize text\n"
        "🧮 `/solve` — Solve a question\n"
        "📋 `/exam` — Create an exam paper\n\n"

        "🖼️ *Images*\n"
        "Send a photo with your question.\n\n"

        "👤 *Creator*\n"
        "Ask me who created me.",
        parse_mode="Markdown"
    )


# ============================================================
# /ASK
# ============================================================

async def ask_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not context.args:

        await update.message.reply_text(
            "Example:\n"
            "`/ask What is gravity?`",
            parse_mode="Markdown"
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
# /EXPLAIN
# ============================================================

async def explain_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not context.args:

        await update.message.reply_text(
            "Example:\n"
            "`/explain photosynthesis`",
            parse_mode="Markdown"
        )

        return

    topic = " ".join(
        context.args
    )

    prompt = f"""
Explain this topic to a student:

{topic}

Use this structure:

📖 Definition

⚙️ How it works

⭐ Important points

💡 Example

📝 Short summary

Keep the explanation clear and easy to understand.
"""

    await update.message.reply_text(
        "📖 Preparing the explanation..."
    )

    answer = ask_ai(
        prompt
    )

    await send_long_message(
        update,
        answer
    )


# ============================================================
# /QUIZ
# ============================================================

async def quiz_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not context.args:

        await update.message.reply_text(
            "Example:\n"
            "`/quiz solar system`",
            parse_mode="Markdown"
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
        "🧠 Creating your quiz..."
    )

    answer = ask_ai(
        prompt
    )

    await send_long_message(
        update,
        answer
    )


# ============================================================
# /MCQ
# ============================================================

async def mcq_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not context.args:

        await update.message.reply_text(
            "Example:\n"
            "`/mcq Class 10 Mathematics`",
            parse_mode="Markdown"
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
# /SUMMARIZE
# ============================================================

async def summarize_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not context.args:

        await update.message.reply_text(
            "Example:\n"
            "`/summarize Your text here`",
            parse_mode="Markdown"
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
# /SOLVE
# ============================================================

async def solve_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not context.args:

        await update.message.reply_text(
            "Example:\n"
            "`/solve 2x + 5 = 15`",
            parse_mode="Markdown"
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
# /EXAM
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
            "You can provide one or multiple chapters/topics.",
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

Requirements:

- Cover the provided chapters/topics fairly.
- Mix easy, medium, and challenging questions.
- Avoid duplicate questions.
- Make questions suitable for students.
- Include numerical/problem-solving questions when appropriate.
- Do not include answers in the question paper.
- Keep formatting clean and readable.
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
            "❌ No image was received."
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

        # Telegram photo uploads are normally JPEG.
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
            "❌ There was a problem processing the image."
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

    # --------------------------------------------------------
    # STARTUP LOG
    # --------------------------------------------------------

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
        "🔄 Automatic model discovery enabled"
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
# PROGRAM START
# ============================================================

if __name__ == "__main__":
    main()
