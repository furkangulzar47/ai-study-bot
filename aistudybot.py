import os
import json
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

# ==============================
# KEYS
# ==============================

TELEGRAM_BOT_TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

if not TELEGRAM_BOT_TOKEN:
    raise ValueError("TELEGRAM_BOT_TOKEN is missing")

if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY is missing")


# ==============================
# GEMINI AI
# ==============================

def ask_ai(prompt):

    url = (
        "https://generativelanguage.googleapis.com/"
        "v1beta/models/gemini-3.8-flash:generateContent"
    )

    data = {
        "contents": [
            {
                "parts": [
                    {
                        "text": (
                            "You are an AI Study Assistant. "
                            "Answer clearly and helpfully. "
                            "Explain difficult topics simply. "
                            "You can help with mathematics, science, "
                            "history, programming, technology and "
                            "general knowledge.\n\n"
                            "User question:\n"
                            + prompt
                        )
                    }
                ]
            }
        ]
    }

    body = json.dumps(data).encode("utf-8")

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

    try:

        with urllib.request.urlopen(
            request,
            timeout=60
        ) as response:

            result = json.loads(
                response.read().decode("utf-8")
            )

        return (
            result["candidates"][0]
            ["content"]["parts"][0]["text"]
        )

    except urllib.error.HTTPError as e:

        error = e.read().decode("utf-8")

        print("\n===== GEMINI API ERROR =====")
        print(error)
        print("============================\n")

        return "❌ Gemini API error. Termux console check karo."

    except Exception as e:

        print("\nERROR:", e)

        return "❌ AI response lene me problem aa gayi."


# ==============================
# /START
# ==============================

async def start(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    await update.message.reply_text(
        "📚 AI Study Bot\n\n"
        "Hello! 👋\n\n"
        "Mujhse koi bhi educational question pucho.\n\n"
        "Commands:\n"
        "/ask <question>\n"
        "/explain <topic>\n"
        "/quiz <topic>\n"
        "/mcq <topic>\n"
        "/summarize <text>\n"
        "/solve <question>\n"
        "/help\n\n"
        "Ya simply normal message bhejo."
    )


# ==============================
# /HELP
# ==============================

async def help_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    await update.message.reply_text(
        "📚 Commands\n\n"
        "/ask - Question pucho\n"
        "/explain - Topic explain karo\n"
        "/quiz - Quiz banao\n"
        "/mcq - MCQs banao\n"
        "/summarize - Text summarize karo\n"
        "/solve - Question solve karo\n\n"
        "Ya simply normal message bhejo."
    )


# ==============================
# /ASK
# ==============================

async def ask_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not context.args:

        await update.message.reply_text(
            "Example:\n/ask What is gravity?"
        )

        return

    question = " ".join(context.args)

    await update.message.reply_text(
        "🤔 Thinking..."
    )

    answer = ask_ai(question)

    await update.message.reply_text(answer)


# ==============================
# /EXPLAIN
# ==============================

async def explain_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not context.args:

        await update.message.reply_text(
            "Example:\n/explain photosynthesis"
        )

        return

    topic = " ".join(context.args)

    prompt = f"""
Explain this topic to a student:

{topic}

Use:

1. Simple definition
2. How it works
3. Important points
4. Example
5. Short summary
"""

    await update.message.reply_text(
        "📖 Preparing explanation..."
    )

    answer = ask_ai(prompt)

    await update.message.reply_text(answer)


# ==============================
# /QUIZ
# ==============================

async def quiz_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not context.args:

        await update.message.reply_text(
            "Example:\n/quiz solar system"
        )

        return

    topic = " ".join(context.args)

    prompt = f"""
Create a 5-question quiz about:

{topic}

Each question must have:

A)
B)
C)
D)

After each question give:

Correct Answer:
Explanation:
"""

    await update.message.reply_text(
        "🧠 Creating quiz..."
    )

    answer = ask_ai(prompt)

    await update.message.reply_text(answer)


# ==============================
# /MCQ
# ==============================

async def mcq_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not context.args:

        await update.message.reply_text(
            "Example:\n/mcq class 10 mathematics"
        )

        return

    topic = " ".join(context.args)

    prompt = f"""
Create 10 MCQs about:

{topic}

Each question must have:

A)
B)
C)
D)

Also give:

Correct Answer:
Explanation:
"""

    await update.message.reply_text(
        "📝 Generating MCQs..."
    )

    answer = ask_ai(prompt)

    await update.message.reply_text(answer)


# ==============================
# /SUMMARIZE
# ==============================

async def summarize_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not context.args:

        await update.message.reply_text(
            "Example:\n/summarize Your text here"
        )

        return

    text = " ".join(context.args)

    prompt = f"""
Summarize this text:

{text}

Give:

• Short summary
• Important points
• Key terms
"""

    await update.message.reply_text(
        "📄 Summarizing..."
    )

    answer = ask_ai(prompt)

    await update.message.reply_text(answer)


# ==============================
# /SOLVE
# ==============================

async def solve_command(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    if not context.args:

        await update.message.reply_text(
            "Example:\n/solve 2x + 5 = 15"
        )

        return

    question = " ".join(context.args)

    prompt = f"""
Solve this question step by step:

{question}

Explain every step clearly.

Give the final answer at the end.
"""

    await update.message.reply_text(
        "🧮 Solving..."
    )

    answer = ask_ai(prompt)

    await update.message.reply_text(answer)


# ==============================
# NORMAL MESSAGE
# ==============================

async def normal_message(
    update: Update,
    context: ContextTypes.DEFAULT_TYPE
):

    text = update.message.text

    await update.message.reply_text(
        "🤖 Thinking..."
    )

    answer = ask_ai(text)

    await update.message.reply_text(answer)


# ==============================
# MAIN
# ==============================

def main():

    app = (
        Application
        .builder()
        .token(TELEGRAM_BOT_TOKEN)
        .build()
    )

    app.add_handler(
        CommandHandler("start", start)
    )

    app.add_handler(
        CommandHandler("help", help_command)
    )

    app.add_handler(
        CommandHandler("ask", ask_command)
    )

    app.add_handler(
        CommandHandler("explain", explain_command)
    )

    app.add_handler(
        CommandHandler("quiz", quiz_command)
    )

    app.add_handler(
        CommandHandler("mcq", mcq_command)
    )

    app.add_handler(
        CommandHandler("summarize", summarize_command)
    )

    app.add_handler(
        CommandHandler("solve", solve_command)
    )

    app.add_handler(
        MessageHandler(
            filters.TEXT & ~filters.COMMAND,
            normal_message
        )
    )

    print("==============================")
    print("🤖 AI Study Bot is running!")
    print("🟢 Gemini AI connected")
    print("==============================")

    app.run_polling()


if __name__ == "__main__":
    main()
