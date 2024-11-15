import uuid
from datetime import datetime
from flask import Flask, request, jsonify
import json
import os
import sys

app = Flask(__name__)

# Constants
MAX_HISTORY_SIZE = 3
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
    try:
        # Validate request data
        if not request.json:
            return jsonify({
                'status': 'error',
                'code': 'INVALID_REQUEST',
                'message': 'Request body is missing. Please provide command details in JSON format.',
                'details': 'The request must contain a JSON payload with at least a "command" field.'
            }), 400

        # Extract command and parameters
        command = request.json.get('command')
        params = request.json.get('params', {})

        # Validate command
        if not command:
            return jsonify({
                'status': 'error',
                'code': 'MISSING_COMMAND',
                'message': 'Command field is required.',
                'details': 'You must specify a "command" field in the request body. This should be a string describing the command to be executed.'
            }), 400

        # Validate params
        if not isinstance(params, dict):
            return jsonify({
                'status': 'error',
                'code': 'INVALID_PARAMS',
                'message': 'Command parameters must be a JSON object.',
                'details': 'The "params" field must be a valid JSON object. Current value is not a valid dictionary.'
            }), 400

        # Load existing commands
        data = load_commands()

        # Create new command entry
        new_command = {
            'id': str(uuid.uuid4()),
            'command': command,
            'params': params,
            'time_created': datetime.now().isoformat()
        }

        # Add to new commands list
        data['new_commands'].append(new_command)

        # Save updated commands
        save_commands(data)

        return jsonify({
            'status': 'success', 
            'message': f'Command "{command}" added successfully',
            'command': new_command
        }), 201

    except Exception as e:
        # Catch any unexpected errors
        return jsonify({
            'status': 'error',
            'code': 'INTERNAL_SERVER_ERROR',
            'message': 'An unexpected error occurred while processing the command.',
            'details': str(e)
        }), 500

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
    try:
        # Validate request data
        if not request.json:
            return jsonify({
                'status': 'error',
                'code': 'INVALID_REQUEST',
                'message': 'Request body is missing. Please provide command ID.',
                'details': 'The request must contain a JSON payload with an "id" field.'
            }), 400

        # Extract command ID
        command_id = request.json.get('id')
        
        # Validate command ID
        if not command_id:
            return jsonify({
                'status': 'error',
                'code': 'MISSING_COMMAND_ID',
                'message': 'Command ID is required to move a command to history.',
                'details': 'You must provide a valid "id" field corresponding to an existing new command.'
            }), 400

        # Load existing commands
        data = load_commands()

        # Find command to move
        command_to_move = None
        remaining_new_commands = []
        for cmd in data['new_commands']:
            if cmd['id'] == command_id:
                command_to_move = cmd
                # Add time started when moving to history
                command_to_move['time_started'] = datetime.now().isoformat()
            else:
                remaining_new_commands.append(cmd)
        
        # Check if command was found
        if not command_to_move:
            return jsonify({
                'status': 'error',
                'code': 'COMMAND_NOT_FOUND',
                'message': f'Command with ID {command_id} not found in new commands.',
                'details': 'Ensure the command ID is correct and the command exists in the new commands list.',
                'available_commands': [cmd['id'] for cmd in data['new_commands']]
            }), 404

        # Update commands data
        data['new_commands'] = remaining_new_commands
        data['history'].insert(0, command_to_move)
        data['history'] = data['history'][:MAX_HISTORY_SIZE]

        # Save updated commands
        save_commands(data)

        return jsonify({
            'status': 'success', 
            'message': f'Command {command_id} successfully moved to history',
            'command': command_to_move,
            'history_size': len(data['history'])
        }), 200

    except Exception as e:
        # Catch any unexpected errors
        return jsonify({
            'status': 'error',
            'code': 'INTERNAL_SERVER_ERROR',
            'message': 'An unexpected error occurred while moving command to history.',
            'details': str(e)
        }), 500

if __name__ == '__main__':
    app.run(debug=True)
