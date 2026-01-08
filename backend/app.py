from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_bcrypt import Bcrypt
import mysql.connector, os, jwt
from datetime import datetime, timedelta, date
from functools import wraps
import time

app = Flask(__name__)
CORS(app)
bcrypt = Bcrypt(app)

# Configuration JWT
app.config['SECRET_KEY'] = os.getenv('JWT_SECRET_KEY', 'default_secret_key_change_in_production')
app.config['JWT_ACCESS_TOKEN_EXPIRES'] = int(os.getenv('JWT_ACCESS_TOKEN_EXPIRES', 3600))

def get_db_connection(max_retries=10, retry_delay=2):
    """Établit une connexion à la base de données avec retry"""
    for attempt in range(max_retries):
        try:
            conn = mysql.connector.connect(
                host=os.getenv('DB_HOST'),
                user=os.getenv('DB_USER'),
                password=os.getenv('DB_PASSWORD'),
                database=os.getenv('DB_NAME'),
                port=os.getenv('DB_PORT')
            )
            print(f"✅ Connexion MySQL réussie (tentative {attempt + 1}/{max_retries})")
            return conn
        except mysql.connector.errors.DatabaseError as e:
            if attempt < max_retries - 1:
                print(f"⏳ MySQL pas encore prêt, nouvelle tentative dans {retry_delay}s...")
                time.sleep(retry_delay)
            else:
                print(f"❌ Impossible de se connecter à MySQL après {max_retries} tentatives")
                raise e

def initialize_database():
    """Initialise la base de données avec la nouvelle structure (date de début)"""
    print("🔧 Initialisation de la base de données avec date de début...")
    
    try:
        conn = get_db_connection()
        cursor = conn.cursor()
        
        # Table users (inchangée)
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS users (
                id INT AUTO_INCREMENT PRIMARY KEY,
                username VARCHAR(50) UNIQUE NOT NULL,
                email VARCHAR(100) UNIQUE NOT NULL,
                password_hash VARCHAR(255) NOT NULL,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        ''')
        print("✅ Table 'users' vérifiée/créée")
        
        # Table tasks AVEC DATE DE DÉBUT
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS tasks (
                id INT AUTO_INCREMENT PRIMARY KEY,
                user_id INT NOT NULL,
                title VARCHAR(255) NOT NULL,
                status ENUM('todo', 'in_progress', 'done') DEFAULT 'todo',
                start_date DATE NULL,  -- NOUVEAU : Date de début
                createdAt TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                INDEX idx_user_id (user_id),
                INDEX idx_status (status),
                INDEX idx_start_date (start_date),  -- Index pour le tri
                FOREIGN KEY (user_id) REFERENCES users(id) ON DELETE CASCADE
            ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4 COLLATE=utf8mb4_unicode_ci
        ''')
        print("✅ Table 'tasks' créée avec start_date")
        
        # Migration : ajouter la colonne start_date si elle n'existe pas
        try:
            cursor.execute("SHOW COLUMNS FROM tasks LIKE 'start_date'")
            if not cursor.fetchone():
                cursor.execute("ALTER TABLE tasks ADD COLUMN start_date DATE NULL")
                print("✅ Colonne 'start_date' ajoutée")
                
                # Pour les tâches existantes, définir start_date = date de création
                cursor.execute("UPDATE tasks SET start_date = DATE(createdAt) WHERE start_date IS NULL")
                print("✅ Dates de début initialisées pour les tâches existantes")
        except Exception as e:
            print(f"ℹ️  Gestion de la colonne start_date: {e}")
        
        conn.commit()
        cursor.close()
        conn.close()
        
        print("🎉 Base de données initialisée avec date de début!")
        return True
        
    except Exception as e:
        print(f"❌ Erreur lors de l'initialisation: {e}")
        return False

def token_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        token = None
        
        if 'Authorization' in request.headers:
            auth_header = request.headers['Authorization']
            if auth_header.startswith('Bearer '):
                token = auth_header.split(' ')[1]
        
        if not token:
            return jsonify({'error': 'Token manquant'}), 401
        
        try:
            data = jwt.decode(token, app.config['SECRET_KEY'], algorithms=['HS256'])
            current_user_id = data['user_id']
            
            conn = get_db_connection()
            cursor = conn.cursor(dictionary=True)
            cursor.execute('SELECT id, username, email FROM users WHERE id = %s', (current_user_id,))
            current_user = cursor.fetchone()
            cursor.close()
            conn.close()
            
            if not current_user:
                return jsonify({'error': 'Utilisateur non trouvé'}), 401
                
        except jwt.ExpiredSignatureError:
            return jsonify({'error': 'Token expiré'}), 401
        except jwt.InvalidTokenError:
            return jsonify({'error': 'Token invalide'}), 401
        
        return f(current_user, *args, **kwargs)
    
    return decorated

# Fonction utilitaire pour valider les dates
def validate_date(date_str):
    """Valide et parse une date au format YYYY-MM-DD"""
    if not date_str:
        return None
    
    try:
        # Vérifier le format
        if len(date_str) != 10 or date_str[4] != '-' or date_str[7] != '-':
            raise ValueError("Format invalide")
        
        year, month, day = map(int, date_str.split('-'))
        
        # Vérifier que c'est une date valide
        datetime(year, month, day)
        
        # Optionnel : vérifier que la date n'est pas trop ancienne
        # input_date = date(year, month, day)
        # if input_date < date.today():
        #     return None  # Ou raise ValueError selon vos besoins
        
        return date_str
    except (ValueError, TypeError):
        return None

# ============================================
# ROUTES D'AUTHENTIFICATION (inchangées)
# ============================================

@app.route('/api/register', methods=['POST'])
def register():
    data = request.json
    
    if not data or not data.get('username') or not data.get('email') or not data.get('password'):
        return jsonify({'error': 'Nom d\'utilisateur, email et mot de passe requis'}), 400
    
    username = data['username']
    email = data['email']
    password = data['password']
    
    if len(password) < 6:
        return jsonify({'error': 'Le mot de passe doit contenir au moins 6 caractères'}), 400
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT id FROM users WHERE username = %s OR email = %s', (username, email))
    if cursor.fetchone():
        cursor.close()
        conn.close()
        return jsonify({'error': 'Nom d\'utilisateur ou email déjà utilisé'}), 400
    
    password_hash = bcrypt.generate_password_hash(password).decode('utf-8')
    
    cursor.execute(
        'INSERT INTO users (username, email, password_hash) VALUES (%s, %s, %s)',
        (username, email, password_hash)
    )
    
    user_id = cursor.lastrowid
    conn.commit()
    
    token = jwt.encode({
        'user_id': user_id,
        'username': username,
        'exp': datetime.utcnow() + timedelta(seconds=app.config['JWT_ACCESS_TOKEN_EXPIRES'])
    }, app.config['SECRET_KEY'])
    
    cursor.close()
    conn.close()
    
    return jsonify({
        'message': 'Utilisateur créé avec succès',
        'token': token,
        'user': {
            'id': user_id,
            'username': username,
            'email': email
        }
    }), 201

@app.route('/api/login', methods=['POST'])
def login():
    data = request.json
    
    if not data or not data.get('username') or not data.get('password'):
        return jsonify({'error': 'Nom d\'utilisateur et mot de passe requis'}), 400
    
    username = data['username']
    password = data['password']
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute('SELECT id, username, email, password_hash FROM users WHERE username = %s', (username,))
    user = cursor.fetchone()
    
    if not user or not bcrypt.check_password_hash(user['password_hash'], password):
        cursor.close()
        conn.close()
        return jsonify({'error': 'Identifiants incorrects'}), 401
    
    token = jwt.encode({
        'user_id': user['id'],
        'username': user['username'],
        'exp': datetime.utcnow() + timedelta(seconds=app.config['JWT_ACCESS_TOKEN_EXPIRES'])
    }, app.config['SECRET_KEY'])
    
    cursor.close()
    conn.close()
    
    return jsonify({
        'message': 'Connexion réussie',
        'token': token,
        'user': {
            'id': user['id'],
            'username': user['username'],
            'email': user['email']
        }
    })

@app.route('/api/profile', methods=['GET'])
@token_required
def get_profile(current_user):
    return jsonify({
        'id': current_user['id'],
        'username': current_user['username'],
        'email': current_user['email']
    })

# ============================================
# ROUTES POUR LES TÂCHES AVEC DATE DE DÉBUT
# ============================================

@app.route('/api/tasks', methods=['GET'])
@token_required
def get_tasks(current_user):
    status = request.args.get('status', 'all')
    
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    if status == 'all':
        # Toutes les tâches
        cursor.execute('''
            SELECT * FROM tasks 
            WHERE user_id = %s 
            ORDER BY 
                CASE status
                    WHEN 'todo' THEN 1
                    WHEN 'in_progress' THEN 2
                    WHEN 'done' THEN 3
                END,
                createdAt DESC
        ''', (current_user['id'],))
    
    elif status == 'todo':
        # Tâches à faire : tri par date de début la plus proche
        # Les tâches sans date (NULL) viennent en dernier
        cursor.execute('''
            SELECT * FROM tasks 
            WHERE user_id = %s AND status = 'todo'
            ORDER BY 
                CASE 
                    WHEN start_date IS NULL THEN 1
                    ELSE 0
                END,
                start_date ASC,
                createdAt ASC
        ''', (current_user['id'],))
    
    elif status == 'in_progress':
        # Tâches en cours : tri par date de début
        cursor.execute('''
            SELECT * FROM tasks 
            WHERE user_id = %s AND status = 'in_progress'
            ORDER BY 
                CASE 
                    WHEN start_date IS NULL THEN 1
                    ELSE 0
                END,
                start_date ASC,
                createdAt ASC
        ''', (current_user['id'],))
    
    elif status == 'done':
        # Tâches terminées : tri chronologique inverse
        cursor.execute('''
            SELECT * FROM tasks 
            WHERE user_id = %s AND status = 'done'
            ORDER BY createdAt DESC
        ''', (current_user['id'],))
    
    else:
        cursor.close()
        conn.close()
        return jsonify({'error': 'Status invalide. Valeurs acceptées: all, todo, in_progress, done'}), 400
    
    tasks = cursor.fetchall()
    
    # Convertir les dates en format ISO pour le JSON
    for task in tasks:
        if task['start_date']:
            task['start_date'] = task['start_date'].isoformat()
        if task['createdAt']:
            task['createdAt'] = task['createdAt'].isoformat()
    
    cursor.close()
    conn.close()
    
    return jsonify(tasks)

@app.route('/api/tasks', methods=['POST'])
@token_required
def create_task(current_user):
    data = request.json
    
    if not data or 'title' not in data:
        return jsonify({'error': 'Le titre est requis'}), 400
    
    # Valider et parser la date de début
    start_date = validate_date(data.get('start_date'))
    
    # Si la date est invalide, on peut soit rejeter soit utiliser None
    if data.get('start_date') and not start_date:
        return jsonify({'error': 'Format de date invalide. Utilisez YYYY-MM-DD'}), 400
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Statut par défaut: 'todo'
    status = data.get('status', 'todo')
    if status not in ['todo', 'in_progress', 'done']:
        status = 'todo'
    
    # Construire la requête en fonction de la présence de la date
    if start_date:
        cursor.execute(
            'INSERT INTO tasks (user_id, title, status, start_date) VALUES (%s, %s, %s, %s)',
            (current_user['id'], data['title'], status, start_date)
        )
    else:
        cursor.execute(
            'INSERT INTO tasks (user_id, title, status) VALUES (%s, %s, %s)',
            (current_user['id'], data['title'], status)
        )
    
    conn.commit()
    task_id = cursor.lastrowid
    
    cursor.execute('SELECT * FROM tasks WHERE id = %s', (task_id,))
    task = cursor.fetchone()
    
    cursor.close()
    conn.close()
    
    # Formater la réponse
    response = {
        'id': task[0],
        'user_id': task[1],
        'title': task[2],
        'status': task[3],
        'start_date': task[4].isoformat() if task[4] else None,
        'createdAt': task[5].isoformat() if task[5] else None
    }
    
    return jsonify(response), 201

@app.route('/api/tasks/<int:task_id>/status', methods=['PUT'])
@token_required
def update_task_status(current_user, task_id):
    """Mettre à jour uniquement le status d'une tâche"""
    data = request.json
    
    if not data or 'status' not in data:
        return jsonify({'error': 'Le status est requis'}), 400
    
    if data['status'] not in ['todo', 'in_progress', 'done']:
        return jsonify({'error': 'Status invalide. Valeurs acceptées: todo, in_progress, done'}), 400
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Vérifier que la tâche appartient à l'utilisateur
    cursor.execute('SELECT id FROM tasks WHERE id = %s AND user_id = %s', 
                  (task_id, current_user['id']))
    if not cursor.fetchone():
        cursor.close()
        conn.close()
        return jsonify({'error': 'Tâche non trouvée ou non autorisée'}), 404
    
    # Mettre à jour le status
    cursor.execute(
        'UPDATE tasks SET status = %s WHERE id = %s AND user_id = %s',
        (data['status'], task_id, current_user['id'])
    )
    
    conn.commit()
    
    # Récupérer la tâche mise à jour
    cursor.execute('SELECT * FROM tasks WHERE id = %s', (task_id,))
    task = cursor.fetchone()
    
    cursor.close()
    conn.close()
    
    return jsonify({
        'id': task[0],
        'user_id': task[1],
        'title': task[2],
        'status': task[3],
        'start_date': task[4].isoformat() if task[4] else None,
        'createdAt': task[5].isoformat() if task[5] else None
    })

@app.route('/api/tasks/<int:task_id>', methods=['PUT'])
@token_required
def update_task(current_user, task_id):
    """Mettre à jour le titre et/ou la date de début d'une tâche"""
    data = request.json
    
    conn = get_db_connection()
    cursor = conn.cursor()
    
    # Vérifier que la tâche appartient à l'utilisateur
    cursor.execute('SELECT id FROM tasks WHERE id = %s AND user_id = %s', 
                  (task_id, current_user['id']))
    if not cursor.fetchone():
        cursor.close()
        conn.close()
        return jsonify({'error': 'Tâche non trouvée ou non autorisée'}), 404
    
    updates = []
    values = []
    
    if 'title' in data:
        updates.append('title = %s')
        values.append(data['title'])
    
    if 'status' in data:
        if data['status'] in ['todo', 'in_progress', 'done']:
            updates.append('status = %s')
            values.append(data['status'])
    
    # Gérer la date de début
    if 'start_date' in data:
        start_date = validate_date(data['start_date'])
        if start_date:
            updates.append('start_date = %s')
            values.append(start_date)
        elif data['start_date'] is None:
            # Permettre de supprimer la date
            updates.append('start_date = NULL')
        else:
            cursor.close()
            conn.close()
            return jsonify({'error': 'Format de date invalide. Utilisez YYYY-MM-DD'}), 400
    
    if not updates:
        cursor.close()
        conn.close()
        return jsonify({'error': 'Aucun champ à mettre à jour'}), 400
    
    values.append(task_id)
    values.append(current_user['id'])
    query = f'UPDATE tasks SET {", ".join(updates)} WHERE id = %s AND user_id = %s'
    
    cursor.execute(query, values)
    conn.commit()
    
    cursor.execute('SELECT * FROM tasks WHERE id = %s', (task_id,))
    task = cursor.fetchone()
    
    cursor.close()
    conn.close()
    
    return jsonify({
        'id': task[0],
        'user_id': task[1],
        'title': task[2],
        'status': task[3],
        'start_date': task[4].isoformat() if task[4] else None,
        'createdAt': task[5].isoformat() if task[5] else None
    })

@app.route('/api/tasks/<int:task_id>', methods=['DELETE'])
@token_required
def delete_task(current_user, task_id):
    conn = get_db_connection()
    cursor = conn.cursor()
    
    cursor.execute('SELECT id FROM tasks WHERE id = %s AND user_id = %s', (task_id, current_user['id']))
    if not cursor.fetchone():
        cursor.close()
        conn.close()
        return jsonify({'error': 'Tâche non trouvée ou non autorisée'}), 404
    
    cursor.execute('DELETE FROM tasks WHERE id = %s AND user_id = %s', (task_id, current_user['id']))
    conn.commit()
    
    cursor.close()
    conn.close()
    
    return jsonify({'message': 'Tâche supprimée avec succès'})

@app.route('/api/tasks/stats', methods=['GET'])
@token_required
def get_task_stats(current_user):
    """Récupérer les statistiques des tâches"""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    # Nombre de tâches par status
    cursor.execute('''
        SELECT 
            status,
            COUNT(*) as count
        FROM tasks 
        WHERE user_id = %s 
        GROUP BY status
    ''', (current_user['id'],))
    
    stats = cursor.fetchall()
    
    # Tâches en retard (date de début dépassée et status != 'done')
    cursor.execute('''
        SELECT COUNT(*) as overdue_count
        FROM tasks 
        WHERE user_id = %s 
        AND status != 'done'
        AND start_date IS NOT NULL
        AND start_date < CURDATE()
    ''', (current_user['id'],))
    
    overdue = cursor.fetchone()
    
    # Tâches pour aujourd'hui
    cursor.execute('''
        SELECT COUNT(*) as today_count
        FROM tasks 
        WHERE user_id = %s 
        AND status != 'done'
        AND start_date = CURDATE()
    ''', (current_user['id'],))
    
    today = cursor.fetchone()
    
    cursor.close()
    conn.close()
    
    # Formatage des résultats
    result = {
        'todo': 0,
        'in_progress': 0,
        'done': 0,
        'total': 0,
        'overdue': overdue['overdue_count'] if overdue else 0,
        'today': today['today_count'] if today else 0
    }
    
    for stat in stats:
        result[stat['status']] = stat['count']
        result['total'] += stat['count']
    
    return jsonify(result)

# ============================================
# ROUTES UTILES
# ============================================

@app.route('/api/tasks/upcoming', methods=['GET'])
@token_required
def get_upcoming_tasks(current_user):
    """Récupérer les tâches à venir (prochains 7 jours)"""
    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)
    
    cursor.execute('''
        SELECT * FROM tasks 
        WHERE user_id = %s 
        AND status != 'done'
        AND start_date IS NOT NULL
        AND start_date >= CURDATE()
        AND start_date <= DATE_ADD(CURDATE(), INTERVAL 7 DAY)
        ORDER BY start_date ASC, createdAt ASC
    ''', (current_user['id'],))
    
    tasks = cursor.fetchall()
    
    # Convertir les dates en format ISO
    for task in tasks:
        if task['start_date']:
            task['start_date'] = task['start_date'].isoformat()
        if task['createdAt']:
            task['createdAt'] = task['createdAt'].isoformat()
    
    cursor.close()
    conn.close()
    
    return jsonify(tasks)

# ============================================
# ROUTES DE TEST ET SANTÉ
# ============================================

@app.route('/api/health', methods=['GET'])
def health_check():
    """Route de vérification de santé"""
    return jsonify({
        'status': 'OK', 
        'message': 'API Flask avec date de début pour les tâches',
        'timestamp': datetime.now().isoformat(),
        'today': date.today().isoformat()
    })

@app.route('/', methods=['GET'])
def index():
    return jsonify({
        'API Status': 'API Flask avec authentification JWT et date de début pour les tâches',
        'version': '3.0',
        'features': [
            'Authentification JWT',
            '3 colonnes Kanban (To Do, In Progress, Done)',
            'Date de début pour chaque tâche',
            'Tri par date de début dans To Do et In Progress',
            'Tri chronologique inverse dans Done',
            'Drag & drop entre colonnes'
        ],
        'endpoints': {
            'auth': ['POST /api/register', 'POST /api/login', 'GET /api/profile'],
            'tasks': [
                'GET /api/tasks?status=all|todo|in_progress|done',
                'POST /api/tasks (avec start_date optionnel)',
                'PUT /api/tasks/{id}',
                'PUT /api/tasks/{id}/status',
                'DELETE /api/tasks/{id}',
                'GET /api/tasks/stats',
                'GET /api/tasks/upcoming'
            ]
        }
    })

# ============================================
# POINT D'ENTRÉE PRINCIPAL
# ============================================

if __name__ == '__main__':
    print("🚀 Démarrage de l'application Flask avec dates de début...")
    print("=" * 60)
    
    # Initialiser la base de données
    if initialize_database():
        print("✅ Base de données prête")
        print("📊 Structure: users, tasks(status, start_date)")
        print("📅 Tri: To Do → par start_date ASC, Done → par createdAt DESC")
        print("🌐 Démarrage du serveur Flask...")
        print("=" * 60)
        app.run(host='0.0.0.0', port=5000, debug=True)
    else:
        print("❌ Échec de l'initialisation de la base de données")