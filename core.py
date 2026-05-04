import os, hashlib, base64, json
from datetime import datetime
from cryptography.fernet import Fernet
import psycopg2
from psycopg2.extras import RealDictCursor

# ─── CONEXÃO ───────────────────────────────────────────────────────────

def get_conn():
    return psycopg2.connect(
        os.environ.get("DATABASE_URL"),
        sslmode="require",
        connect_timeout=10
    )

def init_db():
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS config (
            chave TEXT PRIMARY KEY,
            valor TEXT
        );
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            username    TEXT PRIMARY KEY,
            senha       TEXT,
            tipo        TEXT,
            setores     TEXT,
            permissoes  TEXT
        );
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS cofre (
            setor   TEXT,
            dados   TEXT
        );
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS auditoria (
            id        SERIAL PRIMARY KEY,
            data_hora TEXT,
            usuario   TEXT,
            acao      TEXT,
            detalhes  TEXT
        );
    """)

    # Admin padrão com senha em HASH
    cur.execute("SELECT * FROM usuarios WHERE username = 'admin'")
    if not cur.fetchone():
        cur.execute("""
            INSERT INTO usuarios (username, senha, tipo, setores, permissoes)
            VALUES ('admin', %s, 'admin', '[]', '[]')
        """, (_hash_senha("admin123"),))

    conn.commit()
    cur.close()
    conn.close()


SETORES_PADRAO = [
    "Produção", "Qualidade", "Comercial", "Engenharia",
    "RH", "Fiscal", "Assistência Técnica", "Almoxarifado", "Outros"
]

PERMISSOES_TODAS = ["ver", "copiar", "adicionar", "editar", "excluir"]


# ─── HELPERS ───────────────────────────────────────────────────────────

def _hash(s):
    return hashlib.sha256(s.encode()).hexdigest()

def _hash_senha(senha):
    """Hash seguro para senhas de usuários."""
    return hashlib.sha256(senha.encode()).hexdigest()

def _fernet_key(s):
    return base64.urlsafe_b64encode(hashlib.sha256(s.encode()).digest())


# ─── CONFIG ────────────────────────────────────────────────────────────

def carregar_config():
    conn = get_conn()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT chave, valor FROM config")
    rows = cur.fetchall()
    cur.close()
    conn.close()

    config = {"setores": SETORES_PADRAO, "senha_master_hash": None}
    for row in rows:
        if row["chave"] == "setores":
            config["setores"] = json.loads(row["valor"])
        elif row["chave"] == "senha_master_hash":
            config["senha_master_hash"] = row["valor"]
    return config

def salvar_config(config: dict):
    conn = get_conn()
    cur = conn.cursor()
    for chave, valor in config.items():
        v = json.dumps(valor) if isinstance(valor, list) else (valor or "")
        cur.execute("""
            INSERT INTO config (chave, valor) VALUES (%s, %s)
            ON CONFLICT (chave) DO UPDATE SET valor = EXCLUDED.valor
        """, (chave, v))
    conn.commit()
    cur.close()
    conn.close()

def definir_senha_master(nova):
    c = carregar_config()
    c["senha_master_hash"] = _hash(nova)
    salvar_config(c)

def verificar_senha_master(s):
    c = carregar_config()
    if not c.get("senha_master_hash"):
        return False
    return _hash(s) == c["senha_master_hash"]


# ─── COFRE ─────────────────────────────────────────────────────────────

def carregar_cofre(senha_master, config):
    if config.get("senha_master_hash"):
        if not verificar_senha_master(senha_master):
            raise Exception("Senha master incorreta.")

    fernet = Fernet(_fernet_key(senha_master))
    conn = get_conn()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT setor, dados FROM cofre")
    rows = cur.fetchall()
    cur.close()
    conn.close()

    dados = {}
    for row in rows:
        try:
            decrypted = fernet.decrypt(row["dados"].encode()).decode()
            dados[row["setor"]] = json.loads(decrypted)
        except:
            dados[row["setor"]] = []

    for s in config["setores"]:
        dados.setdefault(s, [])

    return {"setores": dados}

def salvar_cofre(dados, senha_master):
    fernet = Fernet(_fernet_key(senha_master))
    conn = get_conn()
    cur = conn.cursor()

    cur.execute("DELETE FROM cofre")

    for setor, itens in dados.items():
        encrypted = fernet.encrypt(
            json.dumps(itens, ensure_ascii=False).encode()
        ).decode()
        cur.execute(
            "INSERT INTO cofre (setor, dados) VALUES (%s, %s)",
            (setor, encrypted)
        )

    conn.commit()
    cur.close()
    conn.close()


# ─── USUÁRIOS ──────────────────────────────────────────────────────────

def carregar_usuarios():
    conn = get_conn()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM usuarios")
    rows = cur.fetchall()
    cur.close()
    conn.close()

    usuarios = {}
    for row in rows:
        usuarios[row["username"]] = {
            "senha":      row["senha"],
            "tipo":       row["tipo"],
            "setores":    json.loads(row["setores"]    or "[]"),
            "permissoes": json.loads(row["permissoes"] or "[]")
        }
    return usuarios

def salvar_usuarios(usuarios: dict):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("DELETE FROM usuarios")
    for username, u in usuarios.items():
        cur.execute("""
            INSERT INTO usuarios (username, senha, tipo, setores, permissoes)
            VALUES (%s, %s, %s, %s, %s)
        """, (
            username,
            u["senha"],
            u["tipo"],
            json.dumps(u.get("setores", [])),
            json.dumps(u.get("permissoes", []))
        ))
    conn.commit()
    cur.close()
    conn.close()

def criar_usuario(username, senha, tipo, setores, permissoes=None):
    u = carregar_usuarios()
    if username in u:
        raise ValueError("Usuário já existe.")
    u[username] = {
        "senha":      _hash_senha(senha),  # ✅ Senha com hash!
        "tipo":       tipo,
        "setores":    setores    if tipo != "admin" else [],
        "permissoes": permissoes if (tipo != "admin" and permissoes) else []
    }
    salvar_usuarios(u)

def editar_usuario(username, senha, tipo, setores, permissoes=None):
    u = carregar_usuarios()
    if username not in u:
        raise ValueError("Usuário não encontrado.")
    dados = u[username]
    dados["tipo"]       = tipo
    dados["setores"]    = setores    if tipo != "admin" else []
    dados["permissoes"] = permissoes if (tipo != "admin" and permissoes) else []
    if senha:
        dados["senha"] = _hash_senha(senha)  # ✅ Senha com hash!
    u[username] = dados
    salvar_usuarios(u)

def excluir_usuario(username):
    u = carregar_usuarios()
    if username == "admin":
        raise ValueError("Não é permitido excluir o admin.")
    if username not in u:
        raise ValueError("Usuário não encontrado.")
    del u[username]
    salvar_usuarios(u)

def verificar_senha_usuario(username, senha):
    """Verifica se a senha do usuário está correta."""
    u = carregar_usuarios()
    if username not in u:
        return False
    return u[username]["senha"] == _hash_senha(senha)


# ─── AUDITORIA ─────────────────────────────────────────────────────────

def carregar_auditoria():
    conn = get_conn()
    cur = conn.cursor(cursor_factory=RealDictCursor)
    cur.execute("SELECT * FROM auditoria ORDER BY id DESC")
    rows = cur.fetchall()
    cur.close()
    conn.close()
    return [dict(r) for r in rows]

def registrar_evento(usuario, acao, detalhes):
    conn = get_conn()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO auditoria (data_hora, usuario, acao, detalhes)
        VALUES (%s, %s, %s, %s)
    """, (
        datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        usuario, acao, detalhes
    ))
    conn.commit()
    cur.close()
    conn.close()
