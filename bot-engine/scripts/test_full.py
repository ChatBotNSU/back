#!/usr/bin/env python3
"""
Тестирование полного диалога с ботом
"""

import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', 'src'))

import redis
import json
import time

def test_full_conversation():
    r = redis.Redis(host='localhost', port=6379, decode_responses=True)
    
    # Последовательность тестовых сообщений
    test_steps = [
        {"message": "start", "blockId": "welcome", "description": "🚀 Старт диалога"},
        {"message": "Иван", "blockId": "get_name", "description": "👤 Отправляем имя"},
        {"message": "1", "blockId": "main_menu", "description": "🔧 Выбираем техподдержку"},
    ]
    
    for step in test_steps:
        print(f"\n{step['description']}")
        print("=" * 50)
        
        # Отправляем сообщение
        message_data = {
            'message': step['message'],
            'botId': 'simple-support-bot',
            'blockId': step['blockId'],
            'userId': 'test-user-123',
            'sessionId': 'test-session-456'
        }
        
        message_id = r.xadd('bot-messages', message_data)
        print(f"📨 Sent: {step['message']}")
        print(f"📋 To block: {step['blockId']}")
        
        # Ждем ответ
        time.sleep(2)
        
        # Проверяем последний ответ
        responses = r.xrevrange('bot-responses', count=1)
        if responses:
            for response_id, response_data in responses:
                if 'response' in response_data:
                    try:
                        response_obj = json.loads(response_data['response'])
                        if response_obj.get('response'):
                            print(f"🤖 Bot: {response_obj['response']}")
                        if response_obj.get('next_block_id'):
                            print(f"➡️ Next block: {response_obj['next_block_id']}")
                    except:
                        pass
        
        time.sleep(1)

if __name__ == "__main__":
    print("🧪 Testing full conversation flow...")
    test_full_conversation()
    print("\n🎉 Conversation test completed!")