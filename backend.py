from flask import Flask, request, jsonify
from flask_cors import CORS
import psycopg2
import psycopg2.extras
import os
import string
import random
from datetime import datetime

app = Flask(__name__)
CORS(app)

def get_db_connection():
    """Crea una connessione al database PostgreSQL"""
    DATABASE_URL = os.environ.get('DATABASE_URL')
    if not DATABASE_URL:
        raise Exception("DATABASE_URL non configurata")
    conn = psycopg2.connect(DATABASE_URL)
    return conn

def init_db():
    """Crea le tabelle se non esistono"""
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Tabella gruppi
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS groups (
            id SERIAL PRIMARY KEY,
            code TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    
    # Tabella partecipanti
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS participants (
            id SERIAL PRIMARY KEY,
            group_id INTEGER,
            name TEXT NOT NULL,
            joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (group_id) REFERENCES groups(id) ON DELETE CASCADE
        )
    ''')
    
    # Tabella spese
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS expenses (
            id SERIAL PRIMARY KEY,
            group_id INTEGER,
            description TEXT NOT NULL,
            amount REAL NOT NULL,
            payer TEXT NOT NULL,
            participants TEXT NOT NULL,
            date TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (group_id) REFERENCES groups(id) ON DELETE CASCADE
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
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT id FROM groups WHERE code = %s', (code,))
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

@app.route('/api/groups', methods=['POST'])
def create_group():
    try:
        data = request.get_json()
        name = data.get('name')
        description = data.get('description', '')
        
        if not name:
            return jsonify({'success': False, 'error': 'Nome gruppo richiesto'}), 400
        
        code = generate_group_code()
        
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO groups (code, name, description) VALUES (%s, %s, %s)',
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
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute('SELECT id, code, name, description FROM groups WHERE code = %s', (code,))
        group = cursor.fetchone()
        
        if not group:
            conn.close()
            return jsonify({'success': False, 'error': 'Gruppo non trovato'}), 404
        
        group_data = {
            'id': group['id'],
            'code': group['code'],
            'name': group['name'],
            'description': group['description']
        }
        
        # Ottieni partecipanti
        cursor.execute('SELECT name FROM participants WHERE group_id = %s', (group['id'],))
        participants = [row['name'] for row in cursor.fetchall()]
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
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Verifica che il gruppo esista
        cursor.execute('SELECT id FROM groups WHERE id = %s', (group_id,))
        if not cursor.fetchone():
            conn.close()
            return jsonify({'success': False, 'error': 'Gruppo non trovato'}), 404
        
        # Verifica che il partecipante non esista già
        cursor.execute('SELECT id FROM participants WHERE group_id = %s AND name = %s', (group_id, name))
        if cursor.fetchone():
            conn.close()
            return jsonify({'success': False, 'error': 'Partecipante già presente'}), 400
        
        cursor.execute(
            'INSERT INTO participants (group_id, name) VALUES (%s, %s)',
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

@app.route('/api/groups/<int:group_id>/participants/<participant_name>', methods=['PUT'])
def update_participant(group_id, participant_name):
    """Modifica il nome di un partecipante"""
    try:
        data = request.get_json()
        new_name = data.get('new_name')
        
        if not new_name:
            return jsonify({'success': False, 'error': 'Nuovo nome richiesto'}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Verifica che il gruppo esista
        cursor.execute('SELECT id FROM groups WHERE id = %s', (group_id,))
        if not cursor.fetchone():
            conn.close()
            return jsonify({'success': False, 'error': 'Gruppo non trovato'}), 404
        
        # Verifica che il partecipante esista
        cursor.execute('SELECT id FROM participants WHERE group_id = %s AND name = %s', (group_id, participant_name))
        if not cursor.fetchone():
            conn.close()
            return jsonify({'success': False, 'error': 'Partecipante non trovato'}), 404
        
        # Verifica che il nuovo nome non sia già in uso
        cursor.execute('SELECT id FROM participants WHERE group_id = %s AND name = %s', (group_id, new_name))
        if cursor.fetchone():
            conn.close()
            return jsonify({'success': False, 'error': 'Nome già in uso'}), 400
        
        # Aggiorna il nome del partecipante
        cursor.execute(
            'UPDATE participants SET name = %s WHERE group_id = %s AND name = %s',
            (new_name, group_id, participant_name)
        )
        
        # Aggiorna anche le spese dove questo partecipante è il pagatore
        cursor.execute(
            'UPDATE expenses SET payer = %s WHERE group_id = %s AND payer = %s',
            (new_name, group_id, participant_name)
        )
        
        # Aggiorna le spese dove questo partecipante è tra i partecipanti
        cursor.execute('SELECT id, participants FROM expenses WHERE group_id = %s', (group_id,))
        expenses = cursor.fetchall()
        for expense in expenses:
            participants_list = expense['participants'].split(',')
            if participant_name in participants_list:
                participants_list = [new_name if p == participant_name else p for p in participants_list]
                new_participants = ','.join(participants_list)
                cursor.execute(
                    'UPDATE expenses SET participants = %s WHERE id = %s',
                    (new_participants, expense['id'])
                )
        
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True,
            'message': 'Partecipante modificato'
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/groups/<int:group_id>/participants/<participant_name>', methods=['DELETE'])
def delete_participant(group_id, participant_name):
    """Elimina un partecipante e le spese associate"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Verifica che il gruppo esista
        cursor.execute('SELECT id FROM groups WHERE id = %s', (group_id,))
        if not cursor.fetchone():
            conn.close()
            return jsonify({'success': False, 'error': 'Gruppo non trovato'}), 404
        
        # Verifica che il partecipante esista
        cursor.execute('SELECT id FROM participants WHERE group_id = %s AND name = %s', (group_id, participant_name))
        if not cursor.fetchone():
            conn.close()
            return jsonify({'success': False, 'error': 'Partecipante non trovato'}), 404
        
        # Elimina il partecipante
        cursor.execute(
            'DELETE FROM participants WHERE group_id = %s AND name = %s',
            (group_id, participant_name)
        )
        
        # Elimina le spese dove questo partecipante è il pagatore
        cursor.execute(
            'DELETE FROM expenses WHERE group_id = %s AND payer = %s',
            (group_id, participant_name)
        )
        
        # Aggiorna le spese dove questo partecipante è tra i partecipanti
        cursor.execute('SELECT id, participants FROM expenses WHERE group_id = %s', (group_id,))
        expenses = cursor.fetchall()
        for expense in expenses:
            participants_list = expense['participants'].split(',')
            if participant_name in participants_list:
                participants_list = [p for p in participants_list if p != participant_name]
                if len(participants_list) == 0:
                    # Se non ci sono più partecipanti, elimina la spesa
                    cursor.execute('DELETE FROM expenses WHERE id = %s', (expense['id'],))
                else:
                    new_participants = ','.join(participants_list)
                    cursor.execute(
                        'UPDATE expenses SET participants = %s WHERE id = %s',
                        (new_participants, expense['id'])
                    )
        
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True,
            'message': 'Partecipante eliminato'
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
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Verifica che il gruppo esista
        cursor.execute('SELECT id FROM groups WHERE id = %s', (group_id,))
        if not cursor.fetchone():
            conn.close()
            return jsonify({'success': False, 'error': 'Gruppo non trovato'}), 404
        
        participants_str = ','.join(participants)
        
        cursor.execute(
            'INSERT INTO expenses (group_id, description, amount, payer, participants, date) VALUES (%s, %s, %s, %s, %s, %s)',
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

@app.route('/api/groups/<int:group_id>/expenses/<int:expense_id>', methods=['PUT'])
def update_expense(group_id, expense_id):
    """Modifica una spesa esistente"""
    try:
        data = request.get_json()
        description = data.get('description')
        amount = data.get('amount')
        payer = data.get('payer')
        participants = data.get('participants', [])
        date = data.get('date')
        
        if not all([description, amount, payer, participants, date]):
            return jsonify({'success': False, 'error': 'Tutti i campi sono richiesti'}), 400
        
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Verifica che il gruppo esista
        cursor.execute('SELECT id FROM groups WHERE id = %s', (group_id,))
        if not cursor.fetchone():
            conn.close()
            return jsonify({'success': False, 'error': 'Gruppo non trovato'}), 404
        
        # Verifica che la spesa esista
        cursor.execute('SELECT id FROM expenses WHERE id = %s AND group_id = %s', (expense_id, group_id))
        if not cursor.fetchone():
            conn.close()
            return jsonify({'success': False, 'error': 'Spesa non trovata'}), 404
        
        participants_str = ','.join(participants)
        
        cursor.execute(
            'UPDATE expenses SET description = %s, amount = %s, payer = %s, participants = %s, date = %s WHERE id = %s AND group_id = %s',
            (description, amount, payer, participants_str, date, expense_id, group_id)
        )
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True,
            'message': 'Spesa modificata'
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/groups/<int:group_id>/expenses/<int:expense_id>', methods=['DELETE'])
def delete_expense(group_id, expense_id):
    """Elimina una spesa"""
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Verifica che il gruppo esista
        cursor.execute('SELECT id FROM groups WHERE id = %s', (group_id,))
        if not cursor.fetchone():
            conn.close()
            return jsonify({'success': False, 'error': 'Gruppo non trovato'}), 404
        
        # Verifica che la spesa esista
        cursor.execute('SELECT id FROM expenses WHERE id = %s AND group_id = %s', (expense_id, group_id))
        if not cursor.fetchone():
            conn.close()
            return jsonify({'success': False, 'error': 'Spesa non trovata'}), 404
        
        # Elimina la spesa
        cursor.execute('DELETE FROM expenses WHERE id = %s AND group_id = %s', (expense_id, group_id))
        conn.commit()
        conn.close()
        
        return jsonify({
            'success': True,
            'message': 'Spesa eliminata'
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/groups/<int:group_id>/expenses')
def get_expenses(group_id):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        cursor.execute(
            'SELECT id, description, amount, payer, participants, date FROM expenses WHERE group_id = %s ORDER BY created_at DESC',
            (group_id,)
        )
        
        expenses = []
        for row in cursor.fetchall():
            expenses.append({
                'id': row['id'],
                'description': row['description'],
                'amount': row['amount'],
                'payer': row['payer'],
                'participants': row['participants'].split(','),
                'date': row['date']
            })
        
        conn.close()
        
        return jsonify({
            'success': True,
            'expenses': expenses
        })
        
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)}), 500

if __name__ == '__main__':
    import os
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)

