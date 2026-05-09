#!/usr/bin/env python3
"""
iMessage Style Imitator - AI-powered reply generator
Reads conversations from Mac Messages, analyzes texting style (slang, tone, behavior),
and generates replies that imitate the other person's communication patterns.

Uses Text Style Transfer (TST) principles to match:
- Slang and abbreviations
- Capitalization patterns
- Punctuation habits
- Emoji usage
- Message length tendencies
- Tone (casual, formal, enthusiastic, dry, etc.)
"""

import sqlite3
import os
import sys
import subprocess
import json
from datetime import datetime
from pathlib import Path

try:
    from rich.console import Console
    from rich.table import Table
    from rich.panel import Panel
    from rich.text import Text
    from rich.prompt import Prompt, Confirm
    from rich.markdown import Markdown
    from rich.layout import Layout
    from rich.live import Live
    from rich.columns import Columns
    from rich import box
except ImportError:
    print("Missing 'rich' package. Install with: pip3 install rich")
    sys.exit(1)

try:
    import requests
except ImportError:
    print("Missing 'requests' package. Install with: pip3 install requests")
    sys.exit(1)

# Ollama API endpoint
OLLAMA_BASE_URL = os.environ.get("OLLAMA_HOST", "http://localhost:11434")

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

MESSAGES_DB = os.path.expanduser("~/Library/Messages/chat.db")
APPLE_EPOCH = 978307200  # Jan 1, 2001 (Apple's epoch offset from Unix)

console = Console()

# ─────────────────────────────────────────────────────────────────────────────
# Database Functions
# ─────────────────────────────────────────────────────────────────────────────


def get_db_connection():
    """Connect to the Messages database (read-only)."""
    if not os.path.exists(MESSAGES_DB):
        console.print("[red]Error:[/red] Messages database not found at:")
        console.print(f"  {MESSAGES_DB}")
        console.print("\nMake sure you have Full Disk Access enabled for your terminal.")
        sys.exit(1)

    try:
        conn = sqlite3.connect(f"file:{MESSAGES_DB}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        return conn
    except sqlite3.OperationalError as e:
        console.print(f"[red]Error accessing database:[/red] {e}")
        console.print("\n[yellow]Fix:[/yellow] Grant Full Disk Access to your terminal app:")
        console.print("  System Settings > Privacy & Security > Full Disk Access")
        sys.exit(1)


def get_conversations(conn, limit=30):
    """Fetch recent conversations with message counts."""
    query = """
    SELECT
        c.ROWID as chat_id,
        c.chat_identifier,
        c.display_name,
        c.service_name,
        COUNT(cmj.message_id) as message_count,
        MAX(m.date) as last_message_date
    FROM chat c
    JOIN chat_message_join cmj ON cmj.chat_id = c.ROWID
    JOIN message m ON m.ROWID = cmj.message_id
    WHERE m.text IS NOT NULL AND m.text != ''
    GROUP BY c.ROWID
    HAVING message_count > 5
    ORDER BY last_message_date DESC
    LIMIT ?
    """
    cursor = conn.execute(query, (limit,))
    return cursor.fetchall()


def get_messages_for_chat(conn, chat_id, limit=200):
    """Fetch messages for a specific chat, ordered by date."""
    query = """
    SELECT
        m.ROWID,
        m.text,
        m.is_from_me,
        m.date,
        m.attributedBody,
        h.id as sender_id
    FROM message m
    JOIN chat_message_join cmj ON cmj.message_id = m.ROWID
    LEFT JOIN handle h ON h.ROWID = m.handle_id
    WHERE cmj.chat_id = ?
      AND m.text IS NOT NULL
      AND m.text != ''
      AND m.is_system_message = 0
    ORDER BY m.date DESC
    LIMIT ?
    """
    cursor = conn.execute(query, (chat_id, limit))
    rows = cursor.fetchall()

    messages = []
    for row in rows:
        text = row["text"]

        # Try to extract text from attributedBody if text is empty
        if not text and row["attributedBody"]:
            try:
                blob = row["attributedBody"]
                text = extract_text_from_attributed_body(blob)
            except Exception:
                continue

        if text and text.strip():
            # Convert Apple epoch to Unix timestamp
            date_val = row["date"]
            if date_val:
                # Dates after 2000 are in nanoseconds
                if date_val > 1000000000000:
                    date_val = date_val / 1000000000
                unix_ts = date_val + APPLE_EPOCH
            else:
                unix_ts = 0

            messages.append({
                "text": text.strip(),
                "is_from_me": bool(row["is_from_me"]),
                "date": unix_ts,
                "sender": row["sender_id"] if not row["is_from_me"] else "me",
            })

    # Return in chronological order
    messages.reverse()
    return messages


def extract_text_from_attributed_body(blob):
    """Extract plain text from NSAttributedString blob."""
    try:
        # The text is usually embedded as a UTF-8 string in the blob
        text = blob.decode("utf-8", errors="ignore")
        # Find the actual text content between known markers
        if "NSString" in text:
            start = text.find("NSString")
            # Look for the text after the marker
            chunk = text[start:]
            # Extract printable characters
            result = ""
            for ch in chunk:
                if ch.isprintable() or ch in "\n\t":
                    result += ch
            return result[:500] if result else None
    except Exception:
        pass
    return None


# ─────────────────────────────────────────────────────────────────────────────
# Style Analysis
# ─────────────────────────────────────────────────────────────────────────────


def analyze_texting_style(messages):
    """Analyze the texting style of the other person in the conversation."""
    other_messages = [m for m in messages if not m["is_from_me"]]
    my_messages = [m for m in messages if m["is_from_me"]]

    if not other_messages:
        return None

    # Collect style metrics
    texts = [m["text"] for m in other_messages]

    analysis = {
        "total_messages": len(texts),
        "avg_length": sum(len(t) for t in texts) / len(texts),
        "uses_caps": sum(1 for t in texts if t.isupper() and len(t) > 2) / len(texts),
        "uses_lowercase": sum(1 for t in texts if t.islower()) / len(texts),
        "uses_emojis": sum(1 for t in texts if any(ord(c) > 0x1F600 for c in t)) / len(texts),
        "avg_words": sum(len(t.split()) for t in texts) / len(texts),
        "uses_punctuation": sum(1 for t in texts if any(c in t for c in ".,!?;:")) / len(texts),
        "exclamation_rate": sum(t.count("!") for t in texts) / len(texts),
        "question_rate": sum(t.count("?") for t in texts) / len(texts),
        "ellipsis_rate": sum(1 for t in texts if "..." in t or ".." in t) / len(texts),
    }

    # Detect common slang/abbreviations
    slang_patterns = [
        "lol", "lmao", "bruh", "ngl", "fr", "ong", "bet", "lowkey",
        "highkey", "deadass", "no cap", "cap", "sus", "finna", "ion",
        "wya", "wyd", "hbu", "tbh", "imo", "smh", "omg", "wtf",
        "idk", "idc", "ight", "aight", "rn", "nvm", "fs", "ard",
        "yea", "yeah", "ye", "yuh", "nah", "naw", "prolly", "tryna",
        "gonna", "wanna", "gotta", "kinda", "sorta", "haha", "hehe",
        "lmk", "otw", "mb", "icl", "istg"
    ]

    found_slang = {}
    for slang in slang_patterns:
        count = sum(1 for t in texts if slang.lower() in t.lower().split()
                    or t.lower().startswith(slang) or t.lower().endswith(slang))
        if count > 0:
            found_slang[slang] = count

    analysis["slang"] = found_slang
    analysis["sample_messages"] = texts[-50:]  # Last 50 messages for context
    analysis["my_sample_messages"] = [m["text"] for m in my_messages[-30:]]

    return analysis


def build_style_profile(analysis):
    """Build a human-readable style profile from the analysis."""
    if not analysis:
        return "No messages from the other person found."

    profile_parts = []

    # Message length
    avg_len = analysis["avg_length"]
    if avg_len < 20:
        profile_parts.append("Very short/terse messages")
    elif avg_len < 50:
        profile_parts.append("Short, casual messages")
    elif avg_len < 100:
        profile_parts.append("Medium-length messages")
    else:
        profile_parts.append("Longer, detailed messages")

    # Capitalization
    if analysis["uses_lowercase"] > 0.7:
        profile_parts.append("Mostly lowercase (no caps)")
    elif analysis["uses_caps"] > 0.2:
        profile_parts.append("Uses ALL CAPS frequently for emphasis")

    # Punctuation
    if analysis["uses_punctuation"] < 0.3:
        profile_parts.append("Rarely uses punctuation")
    if analysis["exclamation_rate"] > 0.5:
        profile_parts.append("Heavy exclamation mark user!")
    if analysis["ellipsis_rate"] > 0.1:
        profile_parts.append("Uses ellipsis (...)  often")

    # Emojis
    if analysis["uses_emojis"] > 0.3:
        profile_parts.append("Frequent emoji user")
    elif analysis["uses_emojis"] < 0.05:
        profile_parts.append("Rarely/never uses emojis")

    # Slang
    if analysis["slang"]:
        top_slang = sorted(analysis["slang"].items(), key=lambda x: x[1], reverse=True)[:8]
        slang_str = ", ".join(f'"{s}"' for s, _ in top_slang)
        profile_parts.append(f"Common slang: {slang_str}")

    return "\n".join(f"  - {p}" for p in profile_parts)


# ─────────────────────────────────────────────────────────────────────────────
# LLM Integration
# ─────────────────────────────────────────────────────────────────────────────


def check_ollama_connection():
    """Verify Ollama is running and return available models."""
    try:
        resp = requests.get(f"{OLLAMA_BASE_URL}/api/tags", timeout=5)
        if resp.status_code == 200:
            models = resp.json().get("models", [])
            return [m["name"] for m in models]
        else:
            return None
    except requests.ConnectionError:
        console.print("[red]Error:[/red] Cannot connect to Ollama.")
        console.print(f"\nMake sure Ollama is running at: {OLLAMA_BASE_URL}")
        console.print("  Start it with: [bold]ollama serve[/bold]")
        console.print("  Install from:  https://ollama.com")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error connecting to Ollama:[/red] {e}")
        sys.exit(1)


def select_ollama_model(models):
    """Let user pick an Ollama model from available ones."""
    if not models:
        console.print("[red]No models found.[/red] Pull one with:")
        console.print("  ollama pull llama3.1")
        console.print("  ollama pull mistral")
        sys.exit(1)

    table = Table(
        title="Available Ollama Models",
        box=box.ROUNDED,
        border_style="green",
    )
    table.add_column("#", style="bold yellow", width=4)
    table.add_column("Model", style="bold white")

    for i, model in enumerate(models, 1):
        table.add_row(str(i), model)

    console.print(table)
    console.print()

    while True:
        choice = Prompt.ask(
            "[bold yellow]Select model #[/bold yellow]",
            default="1"
        )
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(models):
                return models[idx]
            console.print("[red]Invalid selection.[/red]")
        except ValueError:
            console.print("[red]Enter a number.[/red]")


def generate_reply(model, conversation_context, style_analysis, tone="neutral", custom_prompt=None):
    """
    Generate a reply using Ollama that imitates the other person's style.

    Uses Text Style Transfer (TST) approach:
    1. Analyze source style attributes
    2. Generate content with target style constraints
    3. Match slang, tone, and behavioral patterns
    """

    # Build the conversation history for context
    recent_messages = conversation_context[-30:]
    convo_text = "\n".join(
        f"{'ME' if m['is_from_me'] else 'THEM'}: {m['text']}"
        for m in recent_messages
    )

    # Build style instructions from analysis
    style_instructions = build_style_profile(style_analysis)

    # Sample messages for few-shot learning
    sample_msgs = style_analysis.get("sample_messages", [])[-20:]
    samples_text = "\n".join(f'  "{msg}"' for msg in sample_msgs)

    system_prompt = f"""You are a Text Style Transfer (TST) engine. Your job is to generate a reply 
to the latest message in a conversation, perfectly imitating the texting style of the person labeled "ME" 
in the conversation below.

## STYLE ANALYSIS OF "ME":
{style_instructions}

## SAMPLE MESSAGES FROM "ME" (study these carefully):
{samples_text}

## RULES:
1. Match their EXACT texting patterns: capitalization, punctuation, slang, abbreviations
2. Match their message length tendencies (avg ~{style_analysis['avg_length']:.0f} chars)
3. Match their emoji usage patterns
4. Match their tone and energy level
5. If they use no punctuation, you use no punctuation
6. If they use lowercase only, you use lowercase only
7. If they use specific slang, incorporate it naturally
8. Sound NATURAL - like a real text message, not an AI
9. DO NOT be overly formal or polite unless that's their style
10. Generate ONLY the reply text, nothing else. No quotes, no labels, no explanation.

## TONE DIRECTION: {tone}
{"## ADDITIONAL INSTRUCTIONS: " + custom_prompt if custom_prompt else ""}
"""

    user_prompt = f"""Here is the recent conversation:

{convo_text}

Generate a reply as "ME" to the last message from "THEM". 
Match the style perfectly. Only output the message text."""

    try:
        resp = requests.post(
            f"{OLLAMA_BASE_URL}/api/chat",
            json={
                "model": model,
                "messages": [
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": user_prompt},
                ],
                "stream": False,
                "options": {
                    "temperature": 0.9,
                    "num_predict": 200,
                },
            },
            timeout=60,
        )
        if resp.status_code == 200:
            content = resp.json().get("message", {}).get("content", "").strip()
            # Clean up any quotes the model might wrap around the response
            content = content.strip('"').strip("'")
            return content
        else:
            console.print(f"[red]Ollama Error ({resp.status_code}):[/red] {resp.text[:200]}")
            return None
    except requests.Timeout:
        console.print("[red]Ollama request timed out.[/red] The model may be too large.")
        return None
    except Exception as e:
        console.print(f"[red]LLM Error:[/red] {e}")
        return None


# ─────────────────────────────────────────────────────────────────────────────
# iMessage Sending
# ─────────────────────────────────────────────────────────────────────────────


def send_imessage(recipient, message):
    """Send an iMessage using AppleScript (same method as run.sh)."""
    script = f'''
    tell application "Messages"
        set targetService to 1st account whose service type = iMessage
        set targetBuddy to participant "{recipient}" of targetService
        send "{message}" to targetBuddy
    end tell
    '''

    # Try primary method
    result = subprocess.run(
        ["osascript", "-e", script],
        capture_output=True, text=True
    )

    if result.returncode == 0:
        return True

    # Fallback method
    script_fallback = f'''
    tell application "Messages"
        set targetService to 1st account whose service type = iMessage
        set targetBuddy to buddy "{recipient}" of targetService
        send "{message}" to targetBuddy
    end tell
    '''
    result = subprocess.run(
        ["osascript", "-e", script_fallback],
        capture_output=True, text=True
    )
    return result.returncode == 0


# ─────────────────────────────────────────────────────────────────────────────
# Terminal UI
# ─────────────────────────────────────────────────────────────────────────────


def display_header():
    """Display the application header."""
    header = Text()
    header.append("  iMessage Style Imitator  ", style="bold white on blue")
    header.append("\n  AI-powered reply generator using Text Style Transfer", style="dim")
    console.print(Panel(header, border_style="blue", box=box.DOUBLE))
    console.print()


def display_conversations(conversations):
    """Display available conversations in a table."""
    table = Table(
        title="Select a Conversation",
        box=box.ROUNDED,
        border_style="cyan",
        show_lines=False,
    )
    table.add_column("#", style="bold yellow", width=4)
    table.add_column("Contact", style="bold white", min_width=20)
    table.add_column("Service", style="dim", width=10)
    table.add_column("Messages", style="green", width=10)
    table.add_column("Last Active", style="dim", width=16)

    for i, conv in enumerate(conversations, 1):
        # Format display name
        name = conv["display_name"] or conv["chat_identifier"] or "Unknown"

        # Format date
        last_date = conv["last_message_date"]
        if last_date:
            if last_date > 1000000000000:
                last_date = last_date / 1000000000
            unix_ts = last_date + APPLE_EPOCH
            date_str = datetime.fromtimestamp(unix_ts).strftime("%m/%d %I:%M %p")
        else:
            date_str = "Unknown"

        service = conv["service_name"] or "iMessage"

        table.add_row(
            str(i),
            name[:30],
            service[:10],
            str(conv["message_count"]),
            date_str,
        )

    console.print(table)
    console.print()


def display_style_analysis(analysis, profile):
    """Display the style analysis results."""
    panel_content = Text()
    panel_content.append("Texting Behavior Profile:\n\n", style="bold")
    panel_content.append(profile)
    panel_content.append(f"\n\n  Messages analyzed: {analysis['total_messages']}", style="dim")
    panel_content.append(f"\n  Avg message length: {analysis['avg_length']:.0f} chars", style="dim")
    panel_content.append(f"\n  Avg words/message: {analysis['avg_words']:.1f}", style="dim")

    if analysis["slang"]:
        panel_content.append("\n\n  Slang frequency:", style="bold")
        top_slang = sorted(analysis["slang"].items(), key=lambda x: x[1], reverse=True)[:10]
        for slang, count in top_slang:
            bar = "=" * min(count, 20)
            panel_content.append(f"\n    {slang:>8} [{bar}] {count}x", style="yellow")

    console.print(Panel(
        panel_content,
        title="[bold cyan]Style Analysis (TST Profile)[/bold cyan]",
        border_style="cyan",
        box=box.ROUNDED,
    ))
    console.print()


def display_conversation_preview(messages, count=15):
    """Show recent messages from the conversation."""
    console.print("[bold]Recent conversation:[/bold]\n")

    recent = messages[-count:]
    for msg in recent:
        if msg["is_from_me"]:
            style = "bold green"
            prefix = "  YOU"
        else:
            style = "bold magenta"
            prefix = " THEM"

        timestamp = ""
        if msg["date"]:
            try:
                timestamp = datetime.fromtimestamp(msg["date"]).strftime("%H:%M")
            except (ValueError, OSError):
                timestamp = ""

        console.print(f"  [{style}]{prefix}[/{style}] [dim]{timestamp}[/dim]  {msg['text'][:100]}")

    console.print()


def display_generated_reply(reply, tone):
    """Display the generated reply in a styled panel."""
    reply_text = Text()
    reply_text.append(reply, style="bold white")

    console.print(Panel(
        reply_text,
        title=f"[bold green]Generated Reply ({tone})[/bold green]",
        border_style="green",
        box=box.HEAVY,
        padding=(1, 2),
    ))
    console.print()


# ─────────────────────────────────────────────────────────────────────────────
# Main Loop
# ─────────────────────────────────────────────────────────────────────────────


def main():
    """Main application loop."""
    os.system("clear")
    display_header()

    # Connect to database
    console.print("[dim]Connecting to Messages database...[/dim]")
    conn = get_db_connection()
    console.print("[green]Connected.[/green]\n")

    # Initialize Ollama
    console.print("[dim]Connecting to Ollama...[/dim]")
    models = check_ollama_connection()
    console.print(f"[green]Ollama connected.[/green] ({len(models)} model{'s' if len(models) != 1 else ''} available)\n")

    # Select model
    model = select_ollama_model(models)
    console.print(f"\n[bold]Using model:[/bold] {model}\n")

    # Fetch conversations
    conversations = get_conversations(conn)
    if not conversations:
        console.print("[red]No conversations found with enough messages.[/red]")
        sys.exit(1)

    # Display conversation picker
    display_conversations(conversations)

    # Select conversation
    while True:
        choice = Prompt.ask(
            "[bold yellow]Select conversation #[/bold yellow]",
            default="1"
        )
        try:
            idx = int(choice) - 1
            if 0 <= idx < len(conversations):
                break
            console.print("[red]Invalid selection.[/red]")
        except ValueError:
            console.print("[red]Enter a number.[/red]")

    selected = conversations[idx]
    chat_id = selected["chat_id"]
    recipient = selected["chat_identifier"]
    contact_name = selected["display_name"] or recipient

    console.print(f"\n[bold]Selected:[/bold] {contact_name}")
    console.print("[dim]Loading messages and analyzing style...[/dim]\n")

    # Load messages
    messages = get_messages_for_chat(conn, chat_id, limit=200)
    if len(messages) < 5:
        console.print("[red]Not enough messages to analyze style.[/red]")
        sys.exit(1)

    # Analyze style
    analysis = analyze_texting_style(messages)
    if not analysis:
        console.print("[red]No messages from the other person found.[/red]")
        sys.exit(1)

    profile = build_style_profile(analysis)

    # Display analysis
    display_conversation_preview(messages)
    display_style_analysis(analysis, profile)

    console.print(Panel(
        "[bold]Commands:[/bold]\n"
        "  [green]p[/green] = positive reply    [red]n[/red] = negative reply    [yellow]c[/yellow] = custom tone\n"
        "  [cyan]r[/cyan] = regenerate        [magenta]v[/magenta] = view convo       [dim]q[/dim] = quit",
        title="[bold]Reply Generator[/bold]",
        border_style="white",
        box=box.ROUNDED,
    ))
    console.print()

    # ─── Interactive Reply Loop ───────────────────────────────────────────
    current_reply = None
    current_tone = None

    while True:
        action = Prompt.ask(
            "\n[bold]Action[/bold] [dim](p/n/c/r/v/q)[/dim]"
        ).strip().lower()

        if action == "q":
            console.print("\n[dim]Goodbye.[/dim]")
            break

        elif action == "v":
            display_conversation_preview(messages, count=20)
            continue

        elif action in ("p", "n", "c"):
            if action == "p":
                tone = "positive, friendly, enthusiastic, agreeable"
                tone_label = "Positive"
            elif action == "n":
                tone = "negative, disagreeing, dismissive, uninterested"
                tone_label = "Negative"
            else:
                tone = Prompt.ask("[yellow]Enter custom tone/instructions[/yellow]")
                tone_label = f"Custom: {tone[:30]}"

            console.print(f"\n[dim]Generating {tone_label} reply...[/dim]")

            reply = generate_reply(model, messages, analysis, tone=tone)
            if reply:
                current_reply = reply
                current_tone = tone_label
                display_generated_reply(reply, tone_label)

                # Y/N to send
                send_it = Prompt.ask(
                    "[bold]Send this message?[/bold] [dim](y/n/edit)[/dim]",
                    choices=["y", "n", "edit"],
                    default="n",
                )

                if send_it == "y":
                    console.print(f"[dim]Sending to {contact_name}...[/dim]")
                    if send_imessage(recipient, reply):
                        console.print("[bold green]Message sent![/bold green]")
                        # Add to our conversation context
                        messages.append({
                            "text": reply,
                            "is_from_me": True,
                            "date": datetime.now().timestamp(),
                            "sender": "me",
                        })
                    else:
                        console.print("[bold red]Failed to send.[/bold red]")
                        console.print("[dim]Make sure Messages app is running.[/dim]")

                elif send_it == "edit":
                    # Allow user to provide additional instructions
                    custom_prompt = Prompt.ask(
                        "[yellow]Give the AI additional instructions[/yellow]"
                    )
                    console.print("[dim]Regenerating with your guidance...[/dim]")

                    reply = generate_reply(
                        model, messages, analysis,
                        tone=tone,
                        custom_prompt=custom_prompt
                    )
                    if reply:
                        current_reply = reply
                        display_generated_reply(reply, f"{tone_label} + edited")

                        send_edited = Prompt.ask(
                            "[bold]Send this message?[/bold] [dim](y/n)[/dim]",
                            choices=["y", "n"],
                            default="n",
                        )
                        if send_edited == "y":
                            console.print(f"[dim]Sending to {contact_name}...[/dim]")
                            if send_imessage(recipient, reply):
                                console.print("[bold green]Message sent![/bold green]")
                                messages.append({
                                    "text": reply,
                                    "is_from_me": True,
                                    "date": datetime.now().timestamp(),
                                    "sender": "me",
                                })
                            else:
                                console.print("[bold red]Failed to send.[/bold red]")
                        else:
                            console.print("[dim]Discarded.[/dim]")
                else:
                    console.print("[dim]Discarded.[/dim]")
            else:
                console.print("[red]Failed to generate reply.[/red]")

        elif action == "r":
            if current_tone:
                console.print("[dim]Regenerating...[/dim]")
                reply = generate_reply(model, messages, analysis, tone=current_tone)
                if reply:
                    current_reply = reply
                    display_generated_reply(reply, current_tone)

                    send_it = Prompt.ask(
                        "[bold]Send this message?[/bold] [dim](y/n/edit)[/dim]",
                        choices=["y", "n", "edit"],
                        default="n",
                    )
                    if send_it == "y":
                        console.print(f"[dim]Sending to {contact_name}...[/dim]")
                        if send_imessage(recipient, reply):
                            console.print("[bold green]Message sent![/bold green]")
                            messages.append({
                                "text": reply,
                                "is_from_me": True,
                                "date": datetime.now().timestamp(),
                                "sender": "me",
                            })
                        else:
                            console.print("[bold red]Failed to send.[/bold red]")
                    elif send_it == "edit":
                        custom_prompt = Prompt.ask(
                            "[yellow]Give the AI additional instructions[/yellow]"
                        )
                        console.print("[dim]Regenerating with guidance...[/dim]")
                        reply = generate_reply(
                            model, messages, analysis,
                            tone=current_tone,
                            custom_prompt=custom_prompt
                        )
                        if reply:
                            current_reply = reply
                            display_generated_reply(reply, f"{current_tone} + edited")
                            send_edited = Prompt.ask(
                                "[bold]Send?[/bold] [dim](y/n)[/dim]",
                                choices=["y", "n"],
                                default="n",
                            )
                            if send_edited == "y":
                                if send_imessage(recipient, reply):
                                    console.print("[bold green]Sent![/bold green]")
                                    messages.append({
                                        "text": reply,
                                        "is_from_me": True,
                                        "date": datetime.now().timestamp(),
                                        "sender": "me",
                                    })
                                else:
                                    console.print("[bold red]Failed.[/bold red]")
                    else:
                        console.print("[dim]Discarded.[/dim]")
            else:
                console.print("[yellow]Generate a reply first (p/n/c).[/yellow]")

        else:
            console.print("[dim]Unknown command. Use p/n/c/r/v/q[/dim]")

    conn.close()


if __name__ == "__main__":
    main()
