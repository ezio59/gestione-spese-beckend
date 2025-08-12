#!/usr/bin/env python3
"""
Backend Flask per Gestione spese by Ezio - Modalità Condivisa
Fornisce API per sincronizzazione in tempo reale tra dispositivi
"""

from flask import Flask, request, jsonify, send_from_directory
from flask_cors import CORS
import sqlite3
import json
import string
import random
from datetime import datetime
import os

app = Flask(__name__)
CORS(app)  # Abilita CORS per tutte le route

# Configurazione database
DATABASE = 'spese_condivise.db'

def init_db():
    """Inizializza il database con le tabelle necessarie"""
    conn = sqlite3.connect(DATABASE)
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
            group_code TEXT NOT NULL,
            name TEXT NOT NULL,
            joined_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (group_code) REFERENCES groups (code),
            UNIQUE(group_code, name)
        )
    ''')
    
    # Tabella spese
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS expenses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            group_code TEXT NOT NULL,
            description TEXT NOT NULL,
            amount REAL NOT NULL,
            payer TEXT NOT NULL,
            participants TEXT NOT NULL,
            date TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (group_code) REFERENCES groups (code)
        )
    ''')
    
    conn.commit()
    conn.close()

def generate_group_code():
    """Genera un codice gruppo univoco"""
    while True:
        code = 'SPESE-' + ''.join(random.choices(string.ascii_uppercase + string.digits, k=8))
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        cursor.execute('SELECT code FROM groups WHERE code = ?', (code,))
        if not cursor.fetchone():
            conn.close()
            return code
        conn.close()

# Route per servire l'app frontend
@app.route('/')
def serve_app():
    """Serve l'applicazione principale"""
    return send_from_directory('.', 'index.html')

@app.route('/<path:filename>')
def serve_static(filename):
    """Serve file statici"""
    return send_from_directory('.', filename)

# API Health Check
@app.route('/api/health')
def health_check():
    """Endpoint per verificare lo stato del server"""
    return jsonify({
        'status': 'healthy',
        'service': 'Gestione spese by Ezio - Backend',
        'version': '2.0',
        'timestamp': datetime.now().isoformat()
    })

# API Gruppi
@app.route('/api/groups', methods=['POST'])
def create_group():
    """Crea un nuovo gruppo di spese"""
    try:
        data = request.get_json()
        name = data.get('name', '').strip()
        description = data.get('description', '').strip()
        
        if not name:
            return jsonify({'error': 'Nome gruppo richiesto'}), 400
        
        code = generate_group_code()
        
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        cursor.execute(
            'INSERT INTO groups (code, name, description) VALUES (?, ?, ?)',
            (code, name, description)
        )
        conn.commit()
        conn.close()
        
        return jsonify({
            'code': code,
            'name': name,
            'description': description,
            'message': 'Gruppo creato con successo'
        }), 201
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/groups/<code>')
def get_group(code):
    """Ottieni informazioni su un gruppo"""
    try:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        cursor.execute('SELECT * FROM groups WHERE code = ?', (code,))
        group = cursor.fetchone()
        
        if not group:
            return jsonify({'error': 'Gruppo non trovato'}), 404
        
        # Ottieni partecipanti
        cursor.execute('SELECT name FROM participants WHERE group_code = ?', (code,))
        participants = [row[0] for row in cursor.fetchall()]
        
        # Ottieni spese
        cursor.execute('SELECT * FROM expenses WHERE group_code = ?', (code,))
        expenses = []
        for row in cursor.fetchall():
            expenses.append({
                'id': row[0],
                'description': row[2],
                'amount': row[3],
                'payer': row[4],
                'participants': json.loads(row[5]),
                'date': row[6]
            })
        
        conn.close()
        
        return jsonify({
            'code': group[1],
            'name': group[2],
            'description': group[3],
            'participants': participants,
            'expenses': expenses
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# API Partecipanti
@app.route('/api/groups/<code>/participants', methods=['POST'])
def add_participant(code):
    """Aggiungi un partecipante al gruppo"""
    try:
        data = request.get_json()
        name = data.get('name', '').strip()
        
        if not name:
            return jsonify({'error': 'Nome partecipante richiesto'}), 400
        
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        
        # Verifica che il gruppo esista
        cursor.execute('SELECT code FROM groups WHERE code = ?', (code,))
        if not cursor.fetchone():
            return jsonify({'error': 'Gruppo non trovato'}), 404
        
        # Aggiungi partecipante
        cursor.execute(
            'INSERT INTO participants (group_code, name) VALUES (?, ?)',
            (code, name)
        )
        conn.commit()
        conn.close()
        
        return jsonify({'message': f'Partecipante {name} aggiunto con successo'}), 201
        
    except sqlite3.IntegrityError:
        return jsonify({'error': 'Partecipante già presente nel gruppo'}), 400
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/groups/<code>/participants/<name>', methods=['DELETE'])
def remove_participant(code, name):
    """Rimuovi un partecipante dal gruppo"""
    try:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        cursor.execute(
            'DELETE FROM participants WHERE group_code = ? AND name = ?',
            (code, name)
        )
        
        if cursor.rowcount == 0:
            return jsonify({'error': 'Partecipante non trovato'}), 404
        
        conn.commit()
        conn.close()
        
        return jsonify({'message': f'Partecipante {name} rimosso con successo'})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# API Spese
@app.route('/api/groups/<code>/expenses', methods=['POST'])
def add_expense(code):
    """Aggiungi una spesa al gruppo"""
    try:
        data = request.get_json()
        description = data.get('description', '').strip()
        amount = float(data.get('amount', 0))
        payer = data.get('payer', '').strip()
        participants = data.get('participants', [])
        date = data.get('date', datetime.now().strftime('%Y-%m-%d'))
        
        if not description or amount <= 0 or not payer or not participants:
            return jsonify({'error': 'Tutti i campi sono richiesti'}), 400
        
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        
        # Verifica che il gruppo esista
        cursor.execute('SELECT code FROM groups WHERE code = ?', (code,))
        if not cursor.fetchone():
            return jsonify({'error': 'Gruppo non trovato'}), 404
        
        # Aggiungi spesa
        cursor.execute(
            'INSERT INTO expenses (group_code, description, amount, payer, participants, date) VALUES (?, ?, ?, ?, ?, ?)',
            (code, description, amount, payer, json.dumps(participants), date)
        )
        conn.commit()
        conn.close()
        
        return jsonify({'message': 'Spesa aggiunta con successo'}), 201
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

@app.route('/api/groups/<code>/expenses/<int:expense_id>', methods=['DELETE'])
def remove_expense(code, expense_id):
    """Rimuovi una spesa dal gruppo"""
    try:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        cursor.execute(
            'DELETE FROM expenses WHERE group_code = ? AND id = ?',
            (code, expense_id)
        )
        
        if cursor.rowcount == 0:
            return jsonify({'error': 'Spesa non trovata'}), 404
        
        conn.commit()
        conn.close()
        
        return jsonify({'message': 'Spesa rimossa con successo'})
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

# API Bilanci
@app.route('/api/groups/<code>/balances')
def get_balances(code):
    """Calcola i bilanci del gruppo"""
    try:
        conn = sqlite3.connect(DATABASE)
        cursor = conn.cursor()
        
        # Ottieni tutte le spese del gruppo
        cursor.execute('SELECT * FROM expenses WHERE group_code = ?', (code,))
        expenses = cursor.fetchall()
        
        # Ottieni tutti i partecipanti
        cursor.execute('SELECT name FROM participants WHERE group_code = ?', (code,))
        all_participants = [row[0] for row in cursor.fetchall()]
        
        conn.close()
        
        if not all_participants:
            return jsonify({
                'balances': {},
                'settlements': [],
                'total_amount': 0
            })
        
        # Calcola bilanci
        balances = {name: 0.0 for name in all_participants}
        total_amount = 0
        
        for expense in expenses:
            amount = expense[3]
            payer = expense[4]
            participants = json.loads(expense[5])
            
            total_amount += amount
            
            # Il pagatore ha speso
            if payer in balances:
                balances[payer] += amount
            
            # Dividi la spesa tra i partecipanti
            if participants:
                share = amount / len(participants)
                for participant in participants:
                    if participant in balances:
                        balances[participant] -= share
        
        # Calcola rimborsi ottimali
        settlements = []
        creditors = [(name, balance) for name, balance in balances.items() if balance > 0.01]
        debtors = [(name, -balance) for name, balance in balances.items() if balance < -0.01]
        
        creditors.sort(key=lambda x: x[1], reverse=True)
        debtors.sort(key=lambda x: x[1], reverse=True)
        
        i, j = 0, 0
        while i < len(creditors) and j < len(debtors):
            creditor, credit = creditors[i]
            debtor, debt = debtors[j]
            
            amount = min(credit, debt)
            if amount > 0.01:
                settlements.append({
                    'from': debtor,
                    'to': creditor,
                    'amount': round(amount, 2)
                })
            
            creditors[i] = (creditor, credit - amount)
            debtors[j] = (debtor, debt - amount)
            
            if creditors[i][1] <= 0.01:
                i += 1
            if debtors[j][1] <= 0.01:
                j += 1
        
        # Arrotonda i bilanci
        for name in balances:
            balances[name] = round(balances[name], 2)
        
        return jsonify({
            'balances': balances,
            'settlements': settlements,
            'total_amount': round(total_amount, 2)
        })
        
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    # Inizializza database
    init_db()
    
    # Configurazione per Railway
    port = int(os.environ.get('PORT', 8000))
    
    # Avvia server
    print("🚀 Avvio Gestione spese by Ezio - Backend")
    print("📊 Modalità: Condivisa con sincronizzazione in tempo reale")
    print(f"🌐 Server: http://0.0.0.0:{port}")
    print(f"🔧 API: http://0.0.0.0:{port}/api/health")
    
    app.run(host='0.0.0.0', port=port, debug=False)

