@echo off
echo Deploying BetterSaved bot to EC2...

REM Create media directory on the server if it doesn't exist
REM ssh -i "bot-key.pem" ubuntu@ec2-15-188-73-146.eu-west-3.compute.amazonaws.com "mkdir -p ~/telegram-bot/media"

REM Transfer the updated Python files
scp -i "bot-key.pem" bot.py main.py database.py google_auth.py client_secret.json ubuntu@ec2-15-188-73-146.eu-west-3.compute.amazonaws.com:~/telegram-bot/

REM Transfer the media files
scp -i "bot-key.pem" media/bot-banner.png ubuntu@ec2-15-188-73-146.eu-west-3.compute.amazonaws.com:~/telegram-bot/media/

echo Files transferred successfully!

echo.
echo Restarting the bot...

REM Check if screen session exists and restart the bot
ssh -i "bot-key.pem" ubuntu@ec2-15-188-73-146.eu-west-3.compute.amazonaws.com "cd ~/telegram-bot && if screen -list | grep -q 'telegram-bot'; then screen -S telegram-bot -X quit; fi && screen -dmS telegram-bot bash -c 'cd ~/telegram-bot && source venv/bin/activate && python3 main.py'"

echo.
echo Bot has been restarted in a screen session!
echo To view the bot's console output:
echo ssh -i "bot-key.pem" ubuntu@ec2-15-188-73-146.eu-west-3.compute.amazonaws.com
echo screen -r telegram-bot
echo.
echo To detach from the screen session: press Ctrl+A, D
echo.
pause