from flask import Flask, request, jsonify
from typing import Dict, List, Literal, Optional
from datetime import datetime
import threading
from collections import deque
from enum import Enum
import time
import json
import os

app = Flask(__name__)

COMMANDS_FILE = "commands.json"  # Файл для хранения команд

# Настройки времени хранения команд (в секундах)
RETENTION_SETTINGS = {
    'completed': 3600,  # 1 час для выполненных
    'failed': 86400,    # 24 часа для ошибочных
    'processing': 300   # 5 минут для зависших в обработке
}

class CommandType(str, Enum):
    CLICK = 'click'
    INPUT = 'input'
    SCROLL = 'scroll'
    WAIT = 'wait'

class CommandStatus(str, Enum):
    PENDING = 'pending'
    PROCESSING = 'processing'
    COMPLETED = 'completed'
    FAILED = 'failed'

class Command:
    def __init__(self, command_type: CommandType, target: str, params: Optional[Dict] = None):
        self.id = str(int(time.time() * 1000))
        self.type = command_type
        self.target = target
        self.params = params or {}
        self.status = CommandStatus.PENDING
        self.timestamp = int(time.time() * 1000)
        self.status_changed_at = self.timestamp

    def to_dict(self) -> Dict:
        return {
            'id': self.id,
            'type': self.type,
            'target': self.target,
            'params': self.params,
            'status': self.status,
            'timestamp': self.timestamp,
            'status_changed_at': self.status_changed_at
        }

    def update_status(self, new_status: CommandStatus):
        self.status = new_status
        self.status_changed_at = int(time.time() * 1000)

class CommandQueue:
    def __init__(self):
        self.commands: List[Command] = []
        self.lock = threading.Lock()
        self.load_commands()  # Загружаем команды при инициализации

    def load_commands(self):
        """Загружает команды из файла"""
        if not os.path.exists(COMMANDS_FILE):
            return
        
        try:
            with open(COMMANDS_FILE, 'r') as f:
                data = json.load(f)
                # Сортируем команды по порядку выполнения
                sorted_commands = sorted(data['commands'], key=lambda x: x['order'])
                for cmd_data in sorted_commands:
                    command = Command(
                        command_type=cmd_data['type'],
                        target=cmd_data['target'],
                        params=cmd_data.get('params', {})
                    )
                    self.commands.append(command)
        except Exception as e:
            print(f"Error loading commands: {e}")

    def save_commands(self):
        """Сохраняет оставшиеся команды в файл"""
        with self.lock:
            # Сохраняем только PENDING команды
            pending_commands = [
                {
                    'type': cmd.type,
                    'target': cmd.target,
                    'params': cmd.params,
                    'order': idx + 1
                }
                for idx, cmd in enumerate(self.commands)
                if cmd.status == CommandStatus.PENDING
            ]
            
            try:
                with open(COMMANDS_FILE, 'w') as f:
                    json.dump({'commands': pending_commands}, f, indent=2)
            except Exception as e:
                print(f"Error saving commands: {e}")

    def cleanup_commands(self):
        """Очищает команды на основе их статуса и времени последнего обновления"""
        current_time = int(time.time() * 1000)
        with self.lock:
            old_length = len(self.commands)
            self.commands = [
                cmd for cmd in self.commands
                if self._should_keep_command(cmd, current_time)
            ]
            # Если были удалены команды, сохраняем обновленный список
            if len(self.commands) != old_length:
                self.save_commands()

    def _should_keep_command(self, command: Command, current_time: int) -> bool:
        if command.status == CommandStatus.PENDING:
            return True

        age_ms = current_time - command.status_changed_at
        
        if command.status == CommandStatus.COMPLETED:
            return age_ms <= RETENTION_SETTINGS['completed'] * 1000
        elif command.status == CommandStatus.FAILED:
            return age_ms <= RETENTION_SETTINGS['failed'] * 1000
        elif command.status == CommandStatus.PROCESSING:
            if age_ms > RETENTION_SETTINGS['processing'] * 1000:
                command.update_status(CommandStatus.FAILED)
                command.params['error'] = 'Processing timeout'
            return True
        
        return False

    def add_command(self, command: Command) -> str:
        with self.lock:
            self.cleanup_commands()
            self.commands.append(command)
            self.save_commands()  # Сохраняем после добавления
            return command.id

    def get_next_pending_command(self) -> Optional[Command]:
        with self.lock:
            self.cleanup_commands()
            for command in self.commands:
                if command.status == CommandStatus.PENDING:
                    command.update_status(CommandStatus.PROCESSING)
                    return command
            return None

    def update_command_status(self, command_id: str, status: CommandStatus) -> bool:
        with self.lock:
            self.cleanup_commands()
            for command in self.commands:
                if command.id == command_id:
                    command.update_status(status)
                    self.save_commands()  # Сохраняем после обновления статуса
                    return True
            return False

    def get_all_commands(self) -> List[Dict]:
        with self.lock:
            self.cleanup_commands()
            return [cmd.to_dict() for cmd in self.commands]

# Initialize the command queue
command_queue = CommandQueue()

@app.route("/command", methods=['POST'])
def add_command():
    """Endpoint for Service A to add new commands"""
    data = request.get_json()
    if not data or 'type' not in data or 'target' not in data:
        return jsonify({"status": "error", "message": "Missing required fields"}), 400
    
    try:
        command = Command(
            command_type=CommandType(data['type']),
            target=data['target'],
            params=data.get('params')
        )
    except ValueError:
        return jsonify({"status": "error", "message": "Invalid command type"}), 400

    command_id = command_queue.add_command(command)
    return jsonify({"status": "success", "command_id": command_id})

@app.route("/next-command", methods=['GET'])
def get_next_command():
    """Endpoint for Service B to poll for new commands"""
    command = command_queue.get_next_pending_command()
    if command is None:
        return jsonify({"status": "no_command"})
    return jsonify({
        "status": "success",
        "command": command.to_dict()
    })

@app.route("/complete/<string:command_id>", methods=['POST'])
def complete_command(command_id: str):
    """Endpoint for Service B to mark a command as completed"""
    data = request.get_json()
    status = CommandStatus.COMPLETED if data.get('success', True) else CommandStatus.FAILED

    if command_queue.update_command_status(command_id, status):
        return jsonify({"status": "success", "message": f"Command {command_id} marked as {status}"})
    return jsonify({"status": "error", "message": "Command not found"}), 404

@app.route("/queue-status", methods=['GET'])
def get_queue_status():
    """Get current queue status"""
    return jsonify({
        "status": "success",
        "commands": command_queue.get_all_commands()
    })

if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000, debug=True)
