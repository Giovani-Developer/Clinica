from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, make_response, send_file
import sqlite3
from datetime import datetime
import re
import json
import threading
import csv
from io import StringIO
import os
import sys
from werkzeug.utils import secure_filename
import webbrowser
from threading import Timer
import subprocess


def resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")

    return os.path.join(base_path, relative_path)

app = Flask(__name__, template_folder=resource_path("templates"), static_folder=resource_path("static"))
app.secret_key = 'chave_secreta_reabilitacao_2024'

UPLOAD_FOLDER = resource_path("uploads")
ALLOWED_EXTENSIONS = {'pdf', 'jpg', 'jpeg', 'png', 'doc', 'docx', 'txt'}

if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB max file size

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

_thread_local = threading.local()

def get_db():
    """Obtém conexão SQLite com configurações otimizadas para evitar locks"""
    if not hasattr(_thread_local, 'db'):
        conn = sqlite3.connect('reabilitacao.db', timeout=30.0, check_same_thread=False)
        conn.execute('PRAGMA journal_mode = WAL')  
        conn.execute('PRAGMA synchronous = NORMAL')
        conn.execute('PRAGMA cache_size = -64000')  
        conn.execute('PRAGMA temp_store = MEMORY')
        conn.row_factory = sqlite3.Row
        _thread_local.db = conn
    return _thread_local.db

def init_db():
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS clientes (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            cpf TEXT NOT NULL UNIQUE,
            email TEXT NOT NULL,
            telefone TEXT NOT NULL
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS fichas (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente_id INTEGER NOT NULL,
            data_entrada TEXT NOT NULL,
            data_saida TEXT,
            observacoes TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (cliente_id) REFERENCES clientes(id) ON DELETE CASCADE
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS medicamentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            ficha_id INTEGER NOT NULL,
            nome TEXT NOT NULL,
            dosagem TEXT NOT NULL,
            frequencia TEXT NOT NULL,
            observacoes TEXT,
            FOREIGN KEY (ficha_id) REFERENCES fichas(id) ON DELETE CASCADE
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS familiares (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente_id INTEGER NOT NULL,
            nome TEXT NOT NULL,
            parentesco TEXT NOT NULL,
            telefone TEXT NOT NULL,
            email TEXT,
            endereco TEXT,
            observacoes TEXT,
            FOREIGN KEY (cliente_id) REFERENCES clientes(id) ON DELETE CASCADE
        )
    ''')
    
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS documentos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            cliente_id INTEGER NOT NULL,
            nome_arquivo TEXT NOT NULL,
            nome_original TEXT NOT NULL,
            tipo_documento TEXT NOT NULL,
            tamanho INTEGER,
            data_upload TEXT DEFAULT CURRENT_TIMESTAMP,
            observacoes TEXT,
            FOREIGN KEY (cliente_id) REFERENCES clientes(id) ON DELETE CASCADE
        )
    ''')
    
    conn.commit()

def validar_cpf(cpf):
    cpf = re.sub(r'\D', '', cpf)
    return len(cpf) == 11

def validar_email(email):
    pattern = r'^[\w\.-]+@[\w\.-]+\.\w+$'
    return re.match(pattern, email) is not None

@app.route('/')
def index():
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        busca = request.args.get('busca', '')
        status = request.args.get('status', '')
        data_inicio = request.args.get('data_inicio', '')
        data_fim = request.args.get('data_fim', '')
        
        # Limpar fichas órfãs (sem cliente)
        cursor.execute('''
            DELETE FROM fichas 
            WHERE cliente_id NOT IN (SELECT id FROM clientes)
        ''')
        conn.commit()
        
        query = '''
            SELECT c.id, c.nome, c.cpf, c.email, c.telefone,
                   f.id as ficha_id, f.data_entrada, f.data_saida, f.created_at
            FROM clientes c
            LEFT JOIN fichas f ON c.id = f.cliente_id
            WHERE 1=1
        '''
        params = []
        
        if busca:
            query += ' AND (c.nome LIKE ? OR c.cpf LIKE ? OR c.email LIKE ?)'
            busca_param = f'%{busca}%'
            params.extend([busca_param, busca_param, busca_param])
        
        if status == 'ativo':
            query += ' AND f.data_saida IS NULL AND f.id IS NOT NULL'
        elif status == 'finalizado':
            query += ' AND f.data_saida IS NOT NULL'
        
        if data_inicio:
            query += ' AND f.data_entrada >= ?'
            params.append(data_inicio)
        
        if data_fim:
            query += ' AND f.data_entrada <= ?'
            params.append(data_fim)
        
        query += ' ORDER BY c.id DESC, f.created_at DESC'
        
        cursor.execute(query, params)
        resultados = cursor.fetchall()
        
        clientes_dict = {}
        for row in resultados:
            cliente_id = row[0]
            if cliente_id not in clientes_dict:
                clientes_dict[cliente_id] = {
                    'id': row[0],
                    'nome': row[1],
                    'cpf': row[2],
                    'email': row[3],
                    'telefone': row[4],
                    'fichas': []
                }
            
            if row[5]:
                clientes_dict[cliente_id]['fichas'].append({
                    'id': row[5],
                    'data_entrada': row[6],
                    'data_saida': row[7],
                    'created_at': row[8]
                })
        
        clientes = list(clientes_dict.values())
        
        cursor.execute('SELECT COUNT(*) FROM clientes')
        total = cursor.fetchone()[0]
        
        cursor.execute('''
            SELECT COUNT(*) FROM fichas 
            WHERE data_saida IS NULL 
            AND cliente_id IN (SELECT id FROM clientes)
        ''')
        ativos = cursor.fetchone()[0]
        
        cursor.execute('''
            SELECT COUNT(*) FROM fichas 
            WHERE data_saida IS NOT NULL
            AND cliente_id IN (SELECT id FROM clientes)
        ''')
        finalizados = cursor.fetchone()[0]
        
        return render_template('index.html', 
                             clientes=clientes, 
                             total=total, 
                             ativos=ativos, 
                             finalizados=finalizados,
                             busca=busca,
                             status=status,
                             data_inicio=data_inicio,
                             data_fim=data_fim)
    except Exception as e:
        flash(f'Erro ao carregar página: {str(e)}', 'error')
        return render_template('index.html', clientes=[], total=0, ativos=0, finalizados=0)

@app.route('/cadastrar', methods=['GET', 'POST'])
def cadastrar():
    if request.method == 'POST':
        nome = request.form.get('nome', '').strip()
        cpf = request.form.get('cpf', '').strip()
        email = request.form.get('email', '').strip()
        telefone = request.form.get('telefone', '').strip()
        data_entrada = request.form.get('data_entrada', '').strip()
        data_saida = request.form.get('data_saida', '').strip() or None
        observacoes = request.form.get('observacoes', '').strip()
        
        if not nome or not cpf or not email or not telefone or not data_entrada:
            flash('Todos os campos obrigatórios devem ser preenchidos!', 'error')
            return redirect(url_for('cadastrar'))
        
        medicamentos_json = request.form.get('medicamentos_data', '[]')
        try:
            medicamentos = json.loads(medicamentos_json)
        except:
            medicamentos = []
        
        familiares_json = request.form.get('familiares_data', '[]')
        try:
            familiares = json.loads(familiares_json)
        except:
            familiares = []
        
        if not validar_cpf(cpf):
            flash('CPF inválido! Deve conter 11 dígitos.', 'error')
            return redirect(url_for('cadastrar'))
        
        if not validar_email(email):
            flash('Email inválido!', 'error')
            return redirect(url_for('cadastrar'))
        
        cpf_limpo = re.sub(r'\D', '', cpf)
        
        try:
            conn = get_db()
            cursor = conn.cursor()
            
            cursor.execute('SELECT id, nome FROM clientes WHERE cpf = ?', (cpf_limpo,))
            cliente_existente = cursor.fetchone()
            
            if cliente_existente:
                flash(f'Erro: CPF já cadastrado para o cliente "{cliente_existente[1]}". Use a opção "Nova Ficha" para adicionar uma nova internação.', 'error')
                return redirect(url_for('cadastrar'))
            
            cursor.execute('BEGIN IMMEDIATE')
            
            cursor.execute('''
                INSERT INTO clientes (nome, cpf, email, telefone)
                VALUES (?, ?, ?, ?)
            ''', (nome, cpf_limpo, email, telefone))
            cliente_id = cursor.lastrowid
            
            cursor.execute('''
                INSERT INTO fichas (cliente_id, data_entrada, data_saida, observacoes)
                VALUES (?, ?, ?, ?)
            ''', (cliente_id, data_entrada, data_saida, observacoes))
            ficha_id = cursor.lastrowid
            
            for med in medicamentos:
                nome_med = med.get('nome', '').strip()
                if nome_med:
                    dosagem = med.get('dosagem', '').strip()
                    frequencia = med.get('frequencia', '').strip()
                    obs_med = med.get('observacoes', '').strip()
                    
                    cursor.execute('''
                        INSERT INTO medicamentos (ficha_id, nome, dosagem, frequencia, observacoes)
                        VALUES (?, ?, ?, ?, ?)
                    ''', (ficha_id, nome_med, dosagem, frequencia, obs_med))
            
            for fam in familiares:
                nome_fam = fam.get('nome', '').strip()
                if nome_fam:
                    parentesco = fam.get('parentesco', '').strip()
                    telefone_fam = fam.get('telefone', '').strip()
                    email_fam = fam.get('email', '').strip()
                    endereco = fam.get('endereco', '').strip()
                    obs_fam = fam.get('observacoes', '').strip()
                    
                    cursor.execute('''
                        INSERT INTO familiares (cliente_id, nome, parentesco, telefone, email, endereco, observacoes)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    ''', (cliente_id, nome_fam, parentesco, telefone_fam, email_fam, endereco, obs_fam))
            
            conn.commit()
            flash('Novo cliente cadastrado com sucesso!', 'success')
            return redirect(url_for('ver_cliente', cliente_id=cliente_id))
            
        except sqlite3.IntegrityError as e:
            conn.rollback()
            flash(f'Erro de integridade no banco de dados: {str(e)}', 'error')
            return redirect(url_for('cadastrar'))
        except Exception as e:
            conn.rollback()
            flash(f'Erro ao cadastrar: {str(e)}', 'error')
            return redirect(url_for('cadastrar'))
    
    return render_template('cadastrar.html')

@app.route('/nova-ficha/<int:cliente_id>', methods=['GET', 'POST'])
def nova_ficha(cliente_id):
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM clientes WHERE id=?', (cliente_id,))
    cliente = cursor.fetchone()
    
    if not cliente:
        flash('Cliente não encontrado!', 'error')
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        data_entrada = request.form['data_entrada']
        data_saida = request.form['data_saida'] if request.form['data_saida'] else None
        observacoes = request.form.get('observacoes', '')
        
        medicamentos_json = request.form.get('medicamentos_data', '[]')
        try:
            medicamentos = json.loads(medicamentos_json)
        except:
            medicamentos = []
        
        try:
            cursor.execute('BEGIN IMMEDIATE')
            
            cursor.execute('''
                INSERT INTO fichas (cliente_id, data_entrada, data_saida, observacoes)
                VALUES (?, ?, ?, ?)
            ''', (cliente_id, data_entrada, data_saida, observacoes))
            ficha_id = cursor.lastrowid
            
            for med in medicamentos:
                nome_med = med.get('nome', '').strip()
                if nome_med:
                    dosagem = med.get('dosagem', '').strip()
                    frequencia = med.get('frequencia', '').strip()
                    obs_med = med.get('observacoes', '').strip()
                    
                    cursor.execute('''
                        INSERT INTO medicamentos (ficha_id, nome, dosagem, frequencia, observacoes)
                        VALUES (?, ?, ?, ?, ?)
                    ''', (ficha_id, nome_med, dosagem, frequencia, obs_med))
            
            conn.commit()
            flash('Nova ficha criada com sucesso!', 'success')
            return redirect(url_for('ver_cliente', cliente_id=cliente_id))
        except Exception as e:
            conn.rollback()
            flash(f'Erro ao criar ficha: {str(e)}', 'error')
            return redirect(url_for('nova_ficha', cliente_id=cliente_id))
    
    return render_template('nova_ficha.html', cliente=cliente)

@app.route('/cliente/<int:cliente_id>')
def ver_cliente(cliente_id):
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('SELECT * FROM clientes WHERE id=?', (cliente_id,))
    cliente = cursor.fetchone()
    
    if not cliente:
        flash('Cliente não encontrado!', 'error')
        return redirect(url_for('index'))
    
    cursor.execute('''
        SELECT id, data_entrada, data_saida, observacoes, created_at
        FROM fichas
        WHERE cliente_id = ?
        ORDER BY created_at DESC
    ''', (cliente_id,))
    fichas = cursor.fetchall()
    
    fichas_com_medicamentos = []
    for ficha in fichas:
        cursor.execute('''
            SELECT id, nome, dosagem, frequencia, observacoes
            FROM medicamentos
            WHERE ficha_id = ?
        ''', (ficha[0],))
        medicamentos = cursor.fetchall()
        
        fichas_com_medicamentos.append({
            'id': ficha[0],
            'data_entrada': ficha[1],
            'data_saida': ficha[2],
            'observacoes': ficha[3],
            'created_at': ficha[4],
            'medicamentos': medicamentos
        })
    
    cursor.execute('''
        SELECT id, nome, parentesco, telefone, email, endereco, observacoes
        FROM familiares
        WHERE cliente_id = ?
        ORDER BY nome
    ''', (cliente_id,))
    familiares = cursor.fetchall()
    
    cursor.execute('''
        SELECT id, nome_original, tipo_documento, tamanho, data_upload, observacoes
        FROM documentos
        WHERE cliente_id = ?
        ORDER BY data_upload DESC
    ''', (cliente_id,))
    documentos = cursor.fetchall()
    
    return render_template('ver_cliente.html', cliente=cliente, fichas=fichas_com_medicamentos, familiares=familiares, documentos=documentos)

@app.route('/editar/<int:id>', methods=['GET', 'POST'])
def editar(id):
    conn = get_db()
    cursor = conn.cursor()
    
    if request.method == 'POST':
        nome = request.form['nome']
        email = request.form['email']
        telefone = request.form['telefone']
        
        familiares_json = request.form.get('familiares_data', '[]')
        try:
            familiares = json.loads(familiares_json)
        except:
            familiares = []
        
        if not validar_email(email):
            flash('Email inválido!', 'error')
            return redirect(url_for('editar', id=id))
        
        try:
            cursor.execute('BEGIN IMMEDIATE')
            cursor.execute('''
                UPDATE clientes 
                SET nome=?, email=?, telefone=?
                WHERE id=?
            ''', (nome, email, telefone, id))
            
            cursor.execute('DELETE FROM familiares WHERE cliente_id=?', (id,))
            
            for fam in familiares:
                nome_fam = fam.get('nome', '').strip()
                if nome_fam:
                    parentesco = fam.get('parentesco', '').strip()
                    telefone_fam = fam.get('telefone', '').strip()
                    email_fam = fam.get('email', '').strip()
                    endereco = fam.get('endereco', '').strip()
                    obs_fam = fam.get('observacoes', '').strip()
                    
                    cursor.execute('''
                        INSERT INTO familiares (cliente_id, nome, parentesco, telefone, email, endereco, observacoes)
                        VALUES (?, ?, ?, ?, ?, ?, ?)
                    ''', (id, nome_fam, parentesco, telefone_fam, email_fam, endereco, obs_fam))
            
            conn.commit()
            flash('Cliente atualizado com sucesso!', 'success')
            return redirect(url_for('ver_cliente', cliente_id=id))
        except Exception as e:
            conn.rollback()
            flash(f'Erro ao atualizar: {str(e)}', 'error')
            return redirect(url_for('editar', id=id))
    
    cursor.execute('SELECT * FROM clientes WHERE id=?', (id,))
    cliente = cursor.fetchone()
    
    cursor.execute('SELECT * FROM familiares WHERE cliente_id=?', (id,))
    familiares = cursor.fetchall()
    familiares_json = json.dumps([dict(f) for f in familiares])
    
    return render_template('editar.html', cliente=cliente, familiares_json=familiares_json)

@app.route('/editar-ficha/<int:ficha_id>', methods=['GET', 'POST'])
def editar_ficha(ficha_id):
    conn = get_db()
    cursor = conn.cursor()
    
    cursor.execute('''
        SELECT f.*, c.nome, c.cpf
        FROM fichas f
        JOIN clientes c ON f.cliente_id = c.id
        WHERE f.id = ?
    ''', (ficha_id,))
    ficha = cursor.fetchone()
    
    if not ficha:
        flash('Ficha não encontrada!', 'error')
        return redirect(url_for('index'))
    
    if request.method == 'POST':
        data_entrada = request.form['data_entrada']
        data_saida = request.form['data_saida'] if request.form['data_saida'] else None
        observacoes = request.form.get('observacoes', '')
        
        medicamentos_json = request.form.get('medicamentos_data', '[]')
        try:
            medicamentos = json.loads(medicamentos_json)
        except:
            medicamentos = []
        
        try:
            cursor.execute('BEGIN IMMEDIATE')
            
            cursor.execute('''
                UPDATE fichas
                SET data_entrada=?, data_saida=?, observacoes=?
                WHERE id=?
            ''', (data_entrada, data_saida, observacoes, ficha_id))
            
            cursor.execute('DELETE FROM medicamentos WHERE ficha_id=?', (ficha_id,))
            
            for med in medicamentos:
                nome_med = med.get('nome', '').strip()
                if nome_med:
                    dosagem = med.get('dosagem', '').strip()
                    frequencia = med.get('frequencia', '').strip()
                    obs_med = med.get('observacoes', '').strip()
                    
                    cursor.execute('''
                        INSERT INTO medicamentos (ficha_id, nome, dosagem, frequencia, observacoes)
                        VALUES (?, ?, ?, ?, ?)
                    ''', (ficha_id, nome_med, dosagem, frequencia, obs_med))
            
            conn.commit()
            flash('Ficha atualizada com sucesso!', 'success')
            return redirect(url_for('ver_cliente', cliente_id=ficha[1]))
        except Exception as e:
            conn.rollback()
            flash(f'Erro ao atualizar ficha: {str(e)}', 'error')
            return redirect(url_for('editar_ficha', ficha_id=ficha_id))
    
    cursor.execute('SELECT * FROM medicamentos WHERE ficha_id=?', (ficha_id,))
    medicamentos = cursor.fetchall()
    medicamentos_json = json.dumps([dict(m) for m in medicamentos])
    
    return render_template('editar_ficha.html', ficha=ficha, medicamentos_json=medicamentos_json)

@app.route('/deletar/<int:id>')
def deletar(id):
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('BEGIN IMMEDIATE')
        cursor.execute('DELETE FROM clientes WHERE id=?', (id,))
        conn.commit()
        flash('Cliente removido com sucesso!', 'success')
    except Exception as e:
        conn.rollback()
        flash(f'Erro ao deletar: {str(e)}', 'error')
    
    response = redirect(url_for('index'))
    response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response

@app.route('/deletar-ficha/<int:ficha_id>')
def deletar_ficha(ficha_id):
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute('SELECT cliente_id FROM fichas WHERE id=?', (ficha_id,))
        result = cursor.fetchone()
        
        if result:
            cliente_id = result[0]
            cursor.execute('BEGIN IMMEDIATE')
            cursor.execute('DELETE FROM fichas WHERE id=?', (ficha_id,))
            conn.commit()
            flash('Ficha removida com sucesso!', 'success')
            response = redirect(url_for('ver_cliente', cliente_id=cliente_id))
            response.headers['Cache-Control'] = 'no-cache, no-store, must-revalidate'
            response.headers['Pragma'] = 'no-cache'
            response.headers['Expires'] = '0'
            return response
    except Exception as e:
        conn.rollback()
        flash(f'Erro ao deletar ficha: {str(e)}', 'error')
    
    flash('Ficha não encontrada!', 'error')
    return redirect(url_for('index'))

@app.route('/exportar-csv')
def exportar_csv():
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute('''
            SELECT c.nome, c.cpf, c.email, c.telefone,
                   f.data_entrada, f.data_saida, f.observacoes,
                   m.nome as medicamento, m.dosagem, m.frequencia
            FROM clientes c
            LEFT JOIN fichas f ON c.id = f.cliente_id
            LEFT JOIN medicamentos m ON f.id = m.ficha_id
            ORDER BY c.nome, f.data_entrada DESC
        ''')
        
        dados = cursor.fetchall()
        
        output = StringIO()
        writer = csv.writer(output)
        writer.writerow(['Nome', 'CPF', 'Email', 'Telefone', 'Data Entrada', 'Data Saida', 'Observacoes', 'Medicamento', 'Dosagem', 'Frequencia'])
        
        for row in dados:
            writer.writerow(row)
        
        output.seek(0)
        response = make_response(output.getvalue())
        response.headers['Content-Disposition'] = 'attachment; filename=clientes_export.csv'
        response.headers['Content-Type'] = 'text/csv; charset=utf-8'
        
        return response
    except Exception as e:
        flash(f'Erro ao exportar: {str(e)}', 'error')
        return redirect(url_for('index'))

@app.route('/upload-documento/<int:cliente_id>', methods=['POST'])
def upload_documento(cliente_id):
    if 'arquivo' not in request.files:
        flash('Nenhum arquivo selecionado!', 'error')
        return redirect(url_for('ver_cliente', cliente_id=cliente_id))
    
    arquivo = request.files['arquivo']
    
    if arquivo.filename == '':
        flash('Nenhum arquivo selecionado!', 'error')
        return redirect(url_for('ver_cliente', cliente_id=cliente_id))
    
    if arquivo and allowed_file(arquivo.filename):
        tipo_documento = request.form.get('tipo_documento', 'Outro')
        observacoes = request.form.get('observacoes_doc', '')
        
        nome_original = secure_filename(arquivo.filename)
        extensao = nome_original.rsplit('.', 1)[1].lower()
        nome_arquivo = f"cliente_{cliente_id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.{extensao}"
        
        caminho_arquivo = os.path.join(app.config['UPLOAD_FOLDER'], nome_arquivo)
        arquivo.save(caminho_arquivo)
        
        tamanho = os.path.getsize(caminho_arquivo)
        
        try:
            conn = get_db()
            cursor = conn.cursor()
            cursor.execute('''
                INSERT INTO documentos (cliente_id, nome_arquivo, nome_original, tipo_documento, tamanho, observacoes)
                VALUES (?, ?, ?, ?, ?, ?)
            ''', (cliente_id, nome_arquivo, nome_original, tipo_documento, tamanho, observacoes))
            conn.commit()
            flash('Documento enviado com sucesso!', 'success')
        except Exception as e:
            flash(f'Erro ao salvar documento: {str(e)}', 'error')
            if os.path.exists(caminho_arquivo):
                os.remove(caminho_arquivo)
    else:
        flash('Tipo de arquivo não permitido! Use: PDF, JPG, PNG, DOC, DOCX, TXT', 'error')
    
    return redirect(url_for('ver_cliente', cliente_id=cliente_id))

@app.route('/download-documento/<int:doc_id>')
def download_documento(doc_id):
    try:
        conn = get_db()
        cursor = conn.cursor()
        cursor.execute('SELECT nome_arquivo, nome_original FROM documentos WHERE id=?', (doc_id,))
        documento = cursor.fetchone()
        
        if not documento:
            flash('Documento não encontrado!', 'error')
            return redirect(url_for('index'))
        
        caminho_arquivo = os.path.join(app.config['UPLOAD_FOLDER'], documento[0])
        
        if os.path.exists(caminho_arquivo):
            return send_file(caminho_arquivo, as_attachment=True, download_name=documento[1])
        else:
            flash('Arquivo não encontrado no servidor!', 'error')
            return redirect(url_for('index'))
    except Exception as e:
        flash(f'Erro ao baixar documento: {str(e)}', 'error')
        return redirect(url_for('index'))

@app.route('/deletar-documento/<int:doc_id>')
def deletar_documento(doc_id):
    try:
        conn = get_db()
        cursor = conn.cursor()
        
        cursor.execute('SELECT nome_arquivo, cliente_id FROM documentos WHERE id=?', (doc_id,))
        documento = cursor.fetchone()
        
        if not documento:
            flash('Documento não encontrado!', 'error')
            return redirect(url_for('index'))
        
        cliente_id = documento[1]
        caminho_arquivo = os.path.join(app.config['UPLOAD_FOLDER'], documento[0])
        
        cursor.execute('DELETE FROM documentos WHERE id=?', (doc_id,))
        conn.commit()
        
        if os.path.exists(caminho_arquivo):
            os.remove(caminho_arquivo)
        
        flash('Documento removido com sucesso!', 'success')
        return redirect(url_for('ver_cliente', cliente_id=cliente_id))
    except Exception as e:
        flash(f'Erro ao deletar documento: {str(e)}', 'error')
        return redirect(url_for('index'))

def abrir_navegador_fullscreen():
    chrome_path = r"C:\Program Files\Google\Chrome\Application\chrome.exe"

    if os.path.exists(chrome_path):
        subprocess.Popen([
            chrome_path,
            "--start-fullscreen",       # abre em fullscreen sem F11
            "--kiosk",                  # modo quiosque (sem barra de endereço)
            "http://127.0.0.1:5000"
        ])
    else:
        # fallback caso o chrome não exista
        webbrowser.open("http://127.0.0.1:5000")

if __name__ == "__main__":
    threading.Timer(1, abrir_navegador_fullscreen).start()
    app.run()
