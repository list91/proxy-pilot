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
    
    # Более гибкая валидация
    if not isinstance(command_data, dict):
        return jsonify({'error': 'Invalid request format'}), 400
    
    # Проверка обязательных полей с более мягким подходом
    if not command_data.get('command'):
        return jsonify({'error': 'Command is required'}), 400
    
    # Params необязателен, но если есть - должен быть словарем
    params = command_data.get('params', {})
    if params is not None and not isinstance(params, dict):
        return jsonify({'error': 'Params must be a dictionary'}), 400
    
    command_id = str(uuid.uuid4())
    
    new_command = {
        'id': command_id,
        'command': command_data['command'],
        'params': params,
        'time_created': datetime.now().isoformat()
    }
    
    data['new_commands'].append(new_command)
    save_commands(data)
    
    return jsonify({
        'status': 'success', 
        'id': command_id, 
        'command': new_command['command']
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

if __name__ == '__main__':
    app.run(debug=True)
