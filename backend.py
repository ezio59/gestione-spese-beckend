from flask import Flask, request, jsonify
from flask_cors import CORS
import sqlite3
import os
import string
import random
from datetime import datetime

app = Flask(__name__)
CORS(app)

# Inizializzazione database
def init_db():
    conn = sqlite3.connect('expenses.db')
    cursor = conn.cursor()
    
    # Tabella gruppi
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS groups (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            code TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Tabella partecipanti
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS participants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER,
            name TEXT NOT NULL,
            joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (group_id) REFERENCES groups (id)
        )
    ''')
    
    # Tabella spese
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_id INTEGER,
            description TEXT NOT NULL,
            amount REAL NOT NULL,
            payer TEXT NOT NULL,
            participants TEXT NOT NULL,
            date TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (group_id) REFERENCES groups (id)
        )
    ''')
    
    conn.commit()
    conn.close()

# Inizializza il database all'avvio
init_db()

def generate_group_code():
    """Genera un codice gruppo univoco"""
    while True:
        code = 'SPESE-' + ''.join(random.choices(string.ascii_uppercase + string.digits, k=6))
        
        conn = sqlite3.connect('expenses.db')
        cursor = conn.cursor()
        cursor.execute('SELECT id FROM groups WHERE code = ?', (code,))
        exists = cursor.fetchone()
        conn.close()
        
        if not exists:
            return code

@app.route('/')
def home():
    return jsonify({
        'message': 'Gestione spese by Ezio - Backend attivo',
        'status': 'ok'
    })

@app.route('/api/health')
def health():
    return jsonify({
        'status': 'ok',
        'message': 'Backend attivo'
    })

@app.route('/api/groups', methods=['POST'])
def create_group():
    try:
        data = request.get_json()
        name = data.get('name')
        description = data.get('description', '')
        
        if not name:
            return jsonify({'success': False, 'error': 'Nome gruppo richiesto'}), 400
        
        code = generate_group_code()
        
        conn = sqlite3.connect('expenses.db')
        cursor = conn.cursor()
        
        cursor.execute(
            'INSERT INTO groups (code, name, description) VALUES (?, ?, ?)',
            (code, name, description)
        )
        
        group_id = cursor.lastrowid
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True,
            'group': {
                'id': group_id,
                'code': code,
                'name': name,
                'description': description
            }
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/groups/<code>')
def get_group(code):
    try:
        conn = sqlite3.connect('expenses.db')
        cursor = conn.cursor()
        
        cursor.execute('SELECT id, code, name, description FROM groups WHERE code = ?', (code,))
        group = cursor.fetchone()
        
        if not group:
            conn.close()
            return jsonify({'success': False, 'error': 'Gruppo non trovato'}), 404
        
        group_data = {
            'id': group[0],
            'code': group[1],
            'name': group[2],
            'description': group[3]
        }
        
        # Ottieni partecipanti
        cursor.execute('SELECT name FROM participants WHERE group_id = ?', (group[0],))
        participants = [row[0] for row in cursor.fetchall()]
        group_data['participants'] = participants
        
        conn.close()
        
        return jsonify({
            'success': True,
            'group': group_data
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/groups/<int:group_id>/participants', methods=['POST'])
def add_participant(group_id):
    try:
        data = request.get_json()
        name = data.get('name')
        
        if not name:
            return jsonify({'success': False, 'error': 'Nome partecipante richiesto'}), 400
        
        conn = sqlite3.connect('expenses.db')
        cursor = conn.cursor()
        
        # Verifica che il gruppo esista
        cursor.execute('SELECT id FROM groups WHERE id = ?', (group_id,))
        if not cursor.fetchone():
            conn.close()
            return jsonify({'success': False, 'error': 'Gruppo non trovato'}), 404
        
        # Verifica che il partecipante non esista già
        cursor.execute('SELECT id FROM participants WHERE group_id = ? AND name = ?', (group_id, name))
        if cursor.fetchone():
            conn.close()
            return jsonify({'success': False, 'error': 'Partecipante già presente'}), 400
        
        cursor.execute(
            'INSERT INTO participants (group_id, name) VALUES (?, ?)',
            (group_id, name)
        )
        
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True,
            'message': 'Partecipante aggiunto'
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/groups/<int:group_id>/expenses', methods=['POST'])
def add_expense(group_id):
    try:
        data = request.get_json()
        description = data.get('description')
        amount = data.get('amount')
        payer = data.get('payer')
        participants = data.get('participants', [])
        date = data.get('date')
        
        if not all([description, amount, payer, participants, date]):
            return jsonify({'success': False, 'error': 'Tutti i campi sono richiesti'}), 400
        
        conn = sqlite3.connect('expenses.db')
        cursor = conn.cursor()
        
        # Verifica che il gruppo esista
        cursor.execute('SELECT id FROM groups WHERE id = ?', (group_id,))
        if not cursor.fetchone():
            conn.close()
            return jsonify({'success': False, 'error': 'Gruppo non trovato'}), 404
        
        participants_str = ','.join(participants)
        
        cursor.execute(
            'INSERT INTO expenses (group_id, description, amount, payer, participants, date) VALUES (?, ?, ?, ?, ?, ?)',
            (group_id, description, amount, payer, participants_str, date)
        )
        
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True,
            'message': 'Spesa aggiunta'
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/groups/<int:group_id>/expenses')
def get_expenses(group_id):
    try:
        conn = sqlite3.connect('expenses.db')
        cursor = conn.cursor()
        
        cursor.execute(
            'SELECT id, description, amount, payer, participants, date FROM expenses WHERE group_id = ? ORDER BY created_at DESC',
            (group_id,)
        )
        
        expenses = []
        for row in cursor.fetchall():
            expenses.append({
                'id': row[0],
                'description': row[1],
                'amount': row[2],
                'payer': row[3],
                'participants': row[4].split(','),
                'date': row[5]
            })
        
        conn.close()
        
        return jsonify({
            'success': True,
            'expenses': expenses
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)

