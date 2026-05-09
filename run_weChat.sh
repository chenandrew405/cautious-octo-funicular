#!/bin/bash

# WeChat Message Sender for macOS
# Uses AppleScript UI automation via System Events
# Finds contacts by NAME using Edit > Search menu
# Sends messages via clipboard paste (Cmd+V) + Enter
#
# Prerequisites:
#   - WeChat must be installed, open, and logged in on macOS
#   - Grant Accessibility permissions:
#     System Settings > Privacy & Security > Accessibility > Terminal (or iTerm2)
#   - WeChat window must be visible (not minimized)
#   - Send key in WeChat settings must be set to "Enter" (default)

echo "============================="
echo "  WeChat Message Sender"
echo "============================="
echo ""

# Prompt for contact name
read -p "Enter contact name (as it appears in WeChat): " CONTACT_NAME

if [ -z "$CONTACT_NAME" ]; then
  echo "Error: Contact name cannot be empty."
  exit 1
fi

# Prompt for message
read -p "Enter your message: " MESSAGE

if [ -z "$MESSAGE" ]; then
  echo "Error: Message cannot be empty."
  exit 1
fi

# Prompt for number of times to send
read -p "How many times to send? [default: 1]: " COUNT
COUNT=${COUNT:-1}

if ! [[ "$COUNT" =~ ^[0-9]+$ ]] || [ "$COUNT" -le 0 ]; then
  echo "Error: Count must be a positive number."
  exit 1
fi

# Prompt for sending speed
echo ""
echo "Select sending speed:"
echo "  1) Slowest  - 2.0s delay between messages"
echo "  2) Slow     - 1.0s delay between messages"
echo "  3) Normal   - 0.5s delay between messages"
echo "  4) Fast     - 0.2s delay between messages"
echo ""
read -p "Choose speed (1-4) [default: 2]: " SPEED
SPEED=${SPEED:-2}

case "$SPEED" in
  1) DELAY=2.0 ; SPEED_LABEL="Slowest (2.0s)" ;;
  2) DELAY=1.0 ; SPEED_LABEL="Slow (1.0s)" ;;
  3) DELAY=0.5 ; SPEED_LABEL="Normal (0.5s)" ;;
  4) DELAY=0.2 ; SPEED_LABEL="Fast (0.2s)" ;;
  *)
    echo "Error: Invalid speed. Choose 1-4."
    exit 1
    ;;
esac

echo ""
echo "-----------------------------"
echo "  Contact : $CONTACT_NAME"
echo "  Message : $MESSAGE"
echo "  Count   : $COUNT"
echo "  Speed   : $SPEED_LABEL"
echo "-----------------------------"
echo ""
read -p "Confirm send? (y/n): " CONFIRM

if [[ "$CONFIRM" != "y" && "$CONFIRM" != "Y" ]]; then
  echo "Cancelled."
  exit 0
fi

# Save current clipboard so we can restore it later
OLD_CLIPBOARD="$(pbpaste 2>/dev/null)"

echo ""
echo "Activating WeChat and searching for contact '$CONTACT_NAME'..."

# -------------------------------------------------------
# Step 1: Activate WeChat, open search via menu, find contact
# -------------------------------------------------------
# Put the contact name on the clipboard for pasting
echo -n "$CONTACT_NAME" | pbcopy

SEARCH_RESULT=$(/usr/bin/osascript 2>&1 <<'APPLESCRIPT'
on run
    tell application "WeChat"
        activate
    end tell

    delay 1.5

    tell application "System Events"
        tell process "WeChat"
            set frontmost to true
            delay 0.5

            -- Open search via the Edit > Search menu item
            -- This reliably opens the contact/chat search bar in the sidebar
            click menu item "Search" of menu "Edit" of menu bar item "Edit" of menu bar 1
            delay 0.8

            -- Clear any previous search text and paste contact name from clipboard
            keystroke "a" using {command down}
            delay 0.1
            keystroke "v" using {command down}
            delay 1.5

            -- Press Down arrow to highlight the first search result
            key code 125
            delay 0.3

            -- Press Return to open the conversation
            key code 36
            delay 1.0

            -- Press Escape to close the search overlay and land in the chat
            key code 53
            delay 0.5

        end tell
    end tell

    return "OK"
end run
APPLESCRIPT
)

if [[ "$SEARCH_RESULT" != "OK" ]]; then
  echo "Error: Failed to search for contact."
  echo "AppleScript output: $SEARCH_RESULT"
  echo ""
  echo "Troubleshooting:"
  echo "  1. Make sure WeChat is open and logged in"
  echo "  2. Make sure the WeChat window is visible (not minimized)"
  echo "  3. Grant Accessibility permissions to your terminal app:"
  echo "     System Settings > Privacy & Security > Accessibility"
  echo ""
  echo -n "$OLD_CLIPBOARD" | pbcopy 2>/dev/null
  exit 1
fi

echo "Conversation opened. Sending messages..."
echo ""

# -------------------------------------------------------
# Step 2: Send the message N times, one at a time
# -------------------------------------------------------
# Uses pbcopy + Cmd+V to paste into the message input,
# then Enter to send. Each message is sent individually.

SENT=0
FAILED=0

for (( i=1; i<=COUNT; i++ )); do
  # Copy message to clipboard before each send
  echo -n "$MESSAGE" | pbcopy

  RESULT=$(/usr/bin/osascript 2>&1 <<'APPLESCRIPT'
on run
    tell application "System Events"
        tell process "WeChat"
            set frontmost to true
            delay 0.15

            -- Paste the message from clipboard into the chat input
            keystroke "v" using {command down}
            delay 0.15

            -- Press Enter (Return) to send the message
            key code 36
            delay 0.1
        end tell
    end tell
    return "OK"
end run
APPLESCRIPT
)

  if [ "$RESULT" = "OK" ]; then
    echo "  [$i/$COUNT] Sent"
    SENT=$((SENT + 1))
  else
    echo "  [$i/$COUNT] Failed"
    echo "    Error: $RESULT"
    FAILED=$((FAILED + 1))
  fi

  # Delay between messages
  if [ "$i" -lt "$COUNT" ]; then
    sleep "$DELAY"
  fi
done

# Restore original clipboard
echo -n "$OLD_CLIPBOARD" | pbcopy 2>/dev/null

echo ""
echo "============================="
echo "  Done!"
echo "  Sent    : $SENT"
echo "  Failed  : $FAILED"
echo "  Total   : $COUNT"
echo "============================="
