web: gunicorn 'bot.admin_app:create_app()' --bind 0.0.0.0:${PORT:-8080} --access-logfile -
worker: python main.py bot
