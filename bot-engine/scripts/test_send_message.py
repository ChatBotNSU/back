#!/usr/bin/env python3
"""
Скрипт для отправки тестового сообщения в Redis
"""

import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import redis
import json
import time

def send_test_message(user_message="start"):
    r = redis.Redis(host='localhost', port=6379, decode_responses=True)
    
    # Убедитесь что используете правильные названия полей (camelCase)
    message = {
        'message': user_message,
        'botId': 'simple-support-bot',      # ← camelCase
        'blockId': 'welcome',               # ← camelCase  
        'userId': 'test-user-123',
        'sessionId': 'test-session-456'
    }
    
    message_id = r.xadd('bot-messages', message)
    print(f"✅ Sent test message with ID: {message_id}")
    print(f"📨 Message: {user_message}")
    print(f"🔧 Details: botId={message['botId']}, blockId={message['blockId']}")
    print(f"📋 Full message: {json.dumps(message, indent=2, ensure_ascii=False)}")
    
    return message_id

def listen_for_responses():
    """Слушаем ответы бота"""
    r = redis.Redis(host='localhost', port=6379, decode_responses=True)
    
    print("🎧 Listening for bot responses in stream: bot-responses")
    print("⏹️  Press Ctrl+C to stop")
    
    last_id = '0'
    try:
        while True:
            # Слушаем stream с ответами бота
            responses = r.xread({'bot-responses': last_id}, count=10, block=5000)
            if responses:
                for stream, messages in responses:
                    for message_id, message_data in messages:
                        print(f"\n🤖 [{message_id}] Bot response received:")
                        
                        # Ответ приходит в JSON формате в поле 'response'
                        if 'response' in message_data:
                            try:
                                response_obj = json.loads(message_data['response'])
                                print("📋 Response details:")
                                for key, value in response_obj.items():
                                    if value:  # Показываем только непустые значения
                                        print(f"   {key}: {value}")
                            except json.JSONDecodeError:
                                print(f"   Raw response: {message_data['response']}")
                        
                        last_id = message_id
            else:
                print("⏳ Waiting for bot responses...")
                time.sleep(1)
    except KeyboardInterrupt:
        print("\n👋 Stopped listening")

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "listen":
        listen_for_responses()
    else:
        message = sys.argv[1] if len(sys.argv) > 1 else "start"
        send_test_message(message)