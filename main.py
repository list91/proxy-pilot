import uuid
from datetime import datetime
from flask import Flask, request, jsonify
import json
import os
import sys

app = Flask(__name__)

# Constants
MAX_HISTORY_SIZE = 9
DATA_FILE = 'commands_data.json'

def load_commands():
    """Load commands from JSON file."""
    try:
        with open(DATA_FILE, 'r') as f:
            data = json.load(f)
            return data
    except (FileNotFoundError, json.JSONDecodeError) as e:
        return {'new_commands': [], 'history': []}

def save_commands(data):
    """Save commands to JSON file."""
    try:
        with open(DATA_FILE, 'w') as f:
            json.dump(data, f, indent=2)
    except Exception as e:
        print(f"DEBUG: Error saving data: {e}", file=sys.stderr)

def read_first_commands(count='1'):
    """Read first few commands from the database."""
    data = load_commands()
    
    if count == 'all':
        return data['new_commands']
    else:
        try:
            count = int(count)
            return data['new_commands'][:count]
        except ValueError:
            raise ValueError('Invalid count parameter')

def select_last_commands(count='all'):
    """Select last few commands from the database."""
    data = load_commands()
    
    if count == 'all':
        return data['new_commands']
    else:
        try:
            count = int(count)
            result = data['new_commands'][-count:] if count <= len(data['new_commands']) else data['new_commands']
            return result
        except ValueError:
            raise ValueError('Invalid count parameter')

def move_commands_to_history(command_ids):
    """Move specified commands to history."""
    data = load_commands()
    
    for command_id in command_ids:
        for command in data['new_commands']:
            if command['id'] == command_id:
                command['time_started'] = datetime.now().isoformat()
                data['history'].append(command)
                data['new_commands'].remove(command)
                break
    
    # Manage history size
    if len(data['history']) > MAX_HISTORY_SIZE:
        data['history'] = data['history'][-MAX_HISTORY_SIZE:]
    
    save_commands(data)

@app.route('/add_command', methods=['POST'])
def add_command():
    data = load_commands()
    command_data = request.json
    
    # Валидация формата запроса
    if not isinstance(command_data, dict):
        return jsonify({'error': 'Некорректный формат запроса'}), 400
    
    # Проверка обязательных полей
    scenario = command_data.get('scenario')
    actions = command_data.get('actions')
    if not scenario or not isinstance(actions, list):
        return jsonify({'error': 'Сценарий и действия обязательны'}), 400
    
    # Обработка действий
    for action in actions:
        action_name = action.get('name')
        action_func = action.get('func')
        # Реализуйте логику обработки действий здесь
    
    command_id = str(uuid.uuid4())
    
    new_command = {
        'id': command_id,
        'scenario': scenario,
        'actions': actions,
        'time_created': datetime.now().isoformat()
    }
    
    data['new_commands'].append(new_command)
    save_commands(data)
    
    return jsonify({
        'status': 'success', 
        'id': command_id, 
        'scenario': new_command['scenario']
    })

@app.route('/read_first', methods=['GET'])
def read_first():
    data = load_commands()
    
    # Параметры запроса
    count = request.args.get('count', '1')
    source = request.args.get('source', 'new_commands')
    command_type = request.args.get('type')
    
    # Выбор источника команд
    if source not in ['new_commands', 'history']:
        return jsonify({'error': 'Invalid source. Use "new_commands" or "history"'}), 400
    
    commands = data.get(source, [])
    
    # Фильтрация по типу команды
    if command_type:
        commands = [cmd for cmd in commands if cmd.get('command') == command_type]
    
    # Обработка количества команд
    try:
        if count.lower() == 'all':
            result = commands
        else:
            count = int(count)
            result = commands[:count]
    except ValueError:
        return jsonify({'error': 'Count must be a number or "all"'}), 400
    
    return jsonify(result)

@app.route('/select_last', methods=['GET'])
def select_last():
    count = request.args.get('count', 'all')
    
    try:
        commands = select_last_commands(count)
        return jsonify(commands)
    except ValueError as e:
        return jsonify({'error': str(e)}), 400

@app.route('/move_to_history', methods=['POST'])
def move_to_history():
    command_ids = request.json.get('ids', [])
    
    try:
        move_commands_to_history(command_ids)
        return jsonify({'status': 'success'})
    except Exception as e:
        return jsonify({'error': str(e)}), 400

@app.route('/get_command', methods=['GET'])
def get_command():
    data = load_commands()
    if data['new_commands']:
        # Получаем и удаляем первую команду
        command = data['new_commands'].pop(0)
        save_commands(data)
        return jsonify(command), 200
    return jsonify({}), 204

@app.route('/get_latest_commands', methods=['GET'])
def get_latest_commands():
    try:
        commands = select_last_commands(count='all')  # Получаем все команды
        return jsonify({'new_commands': commands}), 200
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)
