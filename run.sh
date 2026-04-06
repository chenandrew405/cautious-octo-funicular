#!/bin/bash

# iMessage Spammer via macOS Messages app
# Uses AppleScript to send messages through the Messages application

echo "============================="
echo "   iMessage Sender Script"
echo "============================="
echo ""

# Prompt for recipient (phone number or email)
read -p "Enter recipient (phone number or Apple ID email): " RECIPIENT

if [ -z "$RECIPIENT" ]; then
  echo "Error: Recipient cannot be empty."
  exit 1
fi

# Prompt for custom message
read -p "Enter your message: " MESSAGE

if [ -z "$MESSAGE" ]; then
  echo "Error: Message cannot be empty."
  exit 1
fi

# Prompt for number of times to send
read -p "How many times to send? [default: 1000]: " COUNT
COUNT=${COUNT:-1000}

# Validate count is a positive integer
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
echo "  5) Fastest  - no delay between messages"
echo ""
read -p "Choose speed (1-5) [default: 3]: " SPEED
SPEED=${SPEED:-3}

case "$SPEED" in
  1) DELAY=2.0 ; SPEED_LABEL="Slowest (2.0s)" ;;
  2) DELAY=1.0 ; SPEED_LABEL="Slow (1.0s)" ;;
  3) DELAY=0.5 ; SPEED_LABEL="Normal (0.5s)" ;;
  4) DELAY=0.2 ; SPEED_LABEL="Fast (0.2s)" ;;
  5) DELAY=0   ; SPEED_LABEL="Fastest (no delay)" ;;
  *)
    echo "Error: Invalid speed. Choose 1-5."
    exit 1
    ;;
esac

echo ""
echo "Recipient : $RECIPIENT"
echo "Message   : $MESSAGE"
echo "Count     : $COUNT"
echo "Speed     : $SPEED_LABEL"
echo ""
read -p "Confirm send? (y/n): " CONFIRM

if [[ "$CONFIRM" != "y" && "$CONFIRM" != "Y" ]]; then
  echo "Cancelled."
  exit 0
fi

echo ""
echo "Sending messages..."

for (( i=1; i<=COUNT; i++ )); do
  osascript <<EOF
tell application "Messages"
  set targetService to 1st account whose service type = iMessage
  set targetBuddy to participant "$RECIPIENT" of targetService
  send "$MESSAGE" to targetBuddy
end tell
EOF

  if [ $? -eq 0 ]; then
    echo "  [$i/$COUNT] Sent"
  else
    echo "  [$i/$COUNT] Failed - retrying with alternate method..."
    # Fallback: use buddy instead of participant
    osascript <<EOF2
tell application "Messages"
  set targetService to 1st account whose service type = iMessage
  set targetBuddy to buddy "$RECIPIENT" of targetService
  send "$MESSAGE" to targetBuddy
end tell
EOF2
    if [ $? -eq 0 ]; then
      echo "  [$i/$COUNT] Sent (fallback)"
    else
      echo "  [$i/$COUNT] Failed"
    fi
  fi

  # Delay based on chosen speed
  if [ "$DELAY" != "0" ]; then
    sleep "$DELAY"
  fi
done

echo ""
echo "Done! Sent $COUNT message(s) to $RECIPIENT."
