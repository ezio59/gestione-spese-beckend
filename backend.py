from flask import Flask, request, jsonify
from flask_cors import CORS
import sqlite3
import json
import os
import uuid
from datetime import datetime

app = Flask(__name__)
CORS(app)

def init_db():
    conn = sqlite3.connect('spese.db')
    cursor = conn.cursor()
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS groups (
        id TEXT PRIMARY KEY, name TEXT NOT NULL, description TEXT,
        code TEXT UNIQUE NOT NULL, created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS participants (
        id TEXT PRIMARY KEY, group_id TEXT NOT NULL, name TEXT NOT NULL,
        FOREIGN KEY (group_id) REFERENCES groups (id))''')
    
    cursor.execute('''CREATE TABLE IF NOT EXISTS expenses (
        id TEXT PRIMARY KEY, group_id TEXT NOT NULL, description TEXT NOT NULL,
        amount REAL NOT NULL, payer_id TEXT NOT NULL, participants TEXT NOT NULL,
        created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (group_id) REFERENCES groups (id))''')
    
    conn.commit()
    conn.close()

@app.route('/')
def home():
    return jsonify({"message": "Gestione spese by Ezio - Backend attivo", "status": "ok"})

@app.route('/api/health')
def health_check():
    return jsonify({"status": "ok", "message": "Backend attivo"})

@app.route('/api/groups', methods=['POST'])
def create_group():
    try:
        data = request.json
        group_id = str(uuid.uuid4())
        code = f"SPESE-{str(uuid.uuid4())[:8].upper()}"
        
        conn = sqlite3.connect('spese.db')
        cursor = conn.cursor()
        cursor.execute("INSERT INTO groups (id, name, description, code) VALUES (?, ?, ?, ?)",
                      (group_id, data['name'], data.get('description', ''), code))
        conn.commit()
        conn.close()
        
        return jsonify({"success": True, "group": {"id": group_id, "name": data['name'], 
                       "description": data.get('description', ''), "code": code}})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/groups/<code>')
def get_group(code):
    try:
        conn = sqlite3.connect('spese.db')
        cursor = conn.cursor()
        cursor.execute("SELECT * FROM groups WHERE code = ?", (code,))
        group = cursor.fetchone()
        
        if not group:
            return jsonify({"success": False, "error": "Gruppo non trovato"}), 404
        
        cursor.execute("SELECT * FROM participants WHERE group_id = ?", (group[0],))
        participants = cursor.fetchall()
        
        cursor.execute("SELECT * FROM expenses WHERE group_id = ?", (group[0],))
        expenses = cursor.fetchall()
        
        conn.close()
        
        return jsonify({
            "success": True,
            "group": {"id": group[0], "name": group[1], "description": group[2], "code": group[3]},
            "participants": [{"id": p[0], "name": p[2]} for p in participants],
            "expenses": [{"id": e[0], "description": e[2], "amount": e[3], 
                        "payer_id": e[4], "participants": json.loads(e[5])} for e in expenses]
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/groups/<group_id>/participants', methods=['POST'])
def add_participant(group_id):
    try:
        data = request.json
        participant_id = str(uuid.uuid4())
        
        conn = sqlite3.connect('spese.db')
        cursor = conn.cursor()
        cursor.execute("INSERT INTO participants (id, group_id, name) VALUES (?, ?, ?)",
                      (participant_id, group_id, data['name']))
        conn.commit()
        conn.close()
        
        return jsonify({"success": True, "participant": {"id": participant_id, "name": data['name']}})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/groups/<group_id>/expenses', methods=['POST'])
def add_expense(group_id):
    try:
        data = request.json
        expense_id = str(uuid.uuid4())
        
        conn = sqlite3.connect('spese.db')
        cursor = conn.cursor()
        cursor.execute("INSERT INTO expenses (id, group_id, description, amount, payer_id, participants) VALUES (?, ?, ?, ?, ?, ?)",
                      (expense_id, group_id, data['description'], data['amount'], 
                       data['payer_id'], json.dumps(data['participants'])))
        conn.commit()
        conn.close()
        
        return jsonify({"success": True, "expense": {"id": expense_id, "description": data['description'],
                       "amount": data['amount'], "payer_id": data['payer_id'], "participants": data['participants']}})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/api/groups/<group_id>/balance')
def get_balance(group_id):
    try:
        conn = sqlite3.connect('spese.db')
        cursor = conn.cursor()
        
        cursor.execute("SELECT id, name FROM participants WHERE group_id = ?", (group_id,))
        participants = {p[0]: p[1] for p in cursor.fetchall()}
        
        cursor.execute("SELECT amount, payer_id, participants FROM expenses WHERE group_id = ?", (group_id,))
        expenses = cursor.fetchall()
        
        conn.close()
        
        balances = {pid: 0 for pid in participants.keys()}
        
        for amount, payer_id, expense_participants in expenses:
            expense_parts = json.loads(expense_participants)
            per_person = amount / len(expense_parts)
            
            balances[payer_id] += amount
            for participant_id in expense_parts:
                balances[participant_id] -= per_person
        
        settlements = []
        debtors = [(pid, -balance) for pid, balance in balances.items() if balance < -0.01]
        creditors = [(pid, balance) for pid, balance in balances.items() if balance > 0.01]
        
        debtors.sort(key=lambda x: x[1], reverse=True)
        creditors.sort(key=lambda x: x[1], reverse=True)
        
        i, j = 0, 0
        while i < len(debtors) and j < len(creditors):
            debtor_id, debt = debtors[i]
            creditor_id, credit = creditors[j]
            
            amount = min(debt, credit)
            settlements.append({"from": participants[debtor_id], "to": participants[creditor_id], "amount": round(amount, 2)})
            
            debtors[i] = (debtor_id, debt - amount)
            creditors[j] = (creditor_id, credit - amount)
            
            if debtors[i][1] < 0.01: i += 1
            if creditors[j][1] < 0.01: j += 1
        
        return jsonify({
            "success": True,
            "balances": {participants[pid]: round(balance, 2) for pid, balance in balances.items()},
            "settlements": settlements
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

if __name__ == '__main__':
    init_db()
    # CORREZIONE: Usa la porta fornita da Railway
    port = int(os.environ.get('PORT', 5000))
    app.run(host='0.0.0.0', port=port, debug=False)

