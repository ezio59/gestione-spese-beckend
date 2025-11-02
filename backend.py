from flask import Flask, request, jsonify
from flask_cors import CORS
import psycopg2
from psycopg2.extras import RealDictCursor
import os
import string
import random
from datetime import datetime
from urllib.parse import urlparse

app = Flask(__name__)
CORS(app)

# Ottieni l'URL del database da Heroku
DATABASE_URL = os.environ.get('DATABASE_URL')

# Fix per Heroku: sostituisci postgres:// con postgresql://
if DATABASE_URL and DATABASE_URL.startswith('postgres://'):
    DATABASE_URL = DATABASE_URL.replace('postgres://', 'postgresql://', 1)

def get_db_connection():
    """Crea una connessione al database PostgreSQL"""
    try:
        conn = psycopg2.connect(DATABASE_URL, sslmode='require')
        return conn
    except Exception as e:
        print(f"Errore connessione database: {e}")
        raise

# Inizializzazione database
def init_db():
    """Crea le tabelle se non esistono"""
    try:
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
                group_id INTEGER REFERENCES groups(id) ON DELETE CASCADE,
                name TEXT NOT NULL,
                joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        # Tabella spese
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS expenses (
                id SERIAL PRIMARY KEY,
                group_id INTEGER REFERENCES groups(id) ON DELETE CASCADE,
                description TEXT NOT NULL,
                amount REAL NOT NULL,
                payer TEXT NOT NULL,
                participants TEXT NOT NULL,
                date TEXT NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            )
        ''')
        
        conn.commit()
        cursor.close()
        conn.close()
        print("Database inizializzato con successo!")
    except Exception as e:
        print(f"Errore inizializzazione database: {e}")
        raise

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
        cursor.close()
        conn.close()
        
        if not exists:
            return code

@app.route('/')
def home():
    return jsonify({
        'message': 'Gestione spese by Ezio - Backend attivo',
        'status': 'ok',
        'database': 'PostgreSQL'
    })

@app.route('/api/health')
def health():
    return jsonify({
        'status': 'ok',
        'message': 'Backend attivo',
        'database': 'PostgreSQL'
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
            'INSERT INTO groups (code, name, description) VALUES (%s, %s, %s) RETURNING id',
            (code, name, description)
        )
        
        group_id = cursor.fetchone()[0]
        conn.commit()
        cursor.close()
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
        print(f"Errore create_group: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

@app.route('/api/groups/<code>')
def get_group(code):
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        cursor.execute('SELECT id, code, name, description FROM groups WHERE code = %s', (code,))
        group = cursor.fetchone()
        
        if not group:
            cursor.close()
            conn.close()
            return jsonify({'success': False, 'error': 'Gruppo non trovato'}), 404
        
        group_data = {
            'id': group[0],
            'code': group[1],
            'name': group[2],
            'description': group[3]
        }
        
        # Ottieni partecipanti
        cursor.execute('SELECT name FROM participants WHERE group_id = %s', (group[0],))
        participants = [row[0] for row in cursor.fetchall()]
        group_data['participants'] = participants
        
        cursor.close()
        conn.close()
        
        return jsonify({
            'success': True,
            'group': group_data
        })
        
    except Exception as e:
        print(f"Errore get_group: {e}")
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
            cursor.close()
            conn.close()
            return jsonify({'success': False, 'error': 'Gruppo non trovato'}), 404
        
        # Verifica che il partecipante non esista già
        cursor.execute('SELECT id FROM participants WHERE group_id = %s AND name = %s', (group_id, name))
        if cursor.fetchone():
            cursor.close()
            conn.close()
            return jsonify({'success': False, 'error': 'Partecipante già presente'}), 400
        
        cursor.execute(
            'INSERT INTO participants (group_id, name) VALUES (%s, %s)',
            (group_id, name)
        )
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({
            'success': True,
            'message': 'Partecipante aggiunto'
        })
        
    except Exception as e:
        print(f"Errore add_participant: {e}")
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
            cursor.close()
            conn.close()
            return jsonify({'success': False, 'error': 'Gruppo non trovato'}), 404
        
        participants_str = ','.join(participants)
        
        cursor.execute(
            'INSERT INTO expenses (group_id, description, amount, payer, participants, date) VALUES (%s, %s, %s, %s, %s, %s)',
            (group_id, description, amount, payer, participants_str, date)
        )
        
        conn.commit()
        cursor.close()
        conn.close()
        
        return jsonify({
            'success': True,
            'message': 'Spesa aggiunta'
        })
        
    except Exception as e:
        print(f"Errore add_expense: {e}")
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
                'id': row[0],
                'description': row[1],
                'amount': row[2],
                'payer': row[3],
                'participants': row[4].split(','),
                'date': row[5]
            })
        
        cursor.close()
        conn.close()
        
        return jsonify({
            'success': True,
            'expenses': expenses
        })
        
    except Exception as e:
        print(f"Errore get_expenses: {e}")
        return jsonify({'success': False, 'error': str(e)}), 500

if __name__ == '__main__':
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)

